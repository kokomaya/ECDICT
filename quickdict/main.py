"""
main.py — QuickDict 程序入口。

串联各模块：快捷键监听 → 屏幕取词 → 词典查询 → 弹窗显示。
"""
import os
import sys
import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QObject, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from quickdict.config import ensure_db, load_settings, save_settings
from quickdict.config import logger
from quickdict.hotkey import HotkeyListener
from quickdict.word_capture import WordCapture, CaptureMode
from quickdict.popup_widget import PopupWidget
from quickdict.app import TrayManager
from quickdict._lookup_worker import LookupWorker


# ── pynput 线程 → Qt 主线程桥接 ───────────────────────────

class _HotkeyBridge(QObject):
    """将 pynput 线程的回调安全地派发到 Qt 主线程。"""
    activated = pyqtSignal()
    deactivated = pyqtSignal()


# ── 主控制器 ──────────────────────────────────────────────

class QuickDictApp(QObject):
    """主程序控制器：管理各模块的生命周期和信号流。"""

    _sig_lookup = pyqtSignal(str, object)  # → LookupWorker.lookup

    _POLL_INTERVAL_MS = 150  # 取词轮询间隔
    _MOUSE_MOVE_THRESHOLD = 30  # 鼠标移动超过该像素才重新取词
    _DEBOUNCE_MS = 200  # 新词防抖延迟

    def __init__(self):
        super().__init__()

        db_path = ensure_db()

        # 屏幕取词
        self._capture = WordCapture()
        self._settings = load_settings()

        # 恢复上次的取词模式
        saved_mode_key = self._settings.get("capture_mode", "auto")
        saved_mode = self._MODE_MAP.get(saved_mode_key, CaptureMode.AUTO)
        self._capture.set_mode(saved_mode)

        # 翻译弹窗
        self._popup = PopupWidget()

        # 后台查询线程（sqlite3 连接必须在使用线程中创建）
        self._worker = LookupWorker(db_path)
        self._worker_thread = QThread(self)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.init_engine)
        self._sig_lookup.connect(self._worker.lookup)
        self._worker.sig_result.connect(self._on_lookup_result)
        self._worker_thread.start()

        # 取词轮询定时器
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll)
        self._last_word: str | None = None

        # 防抖定时器（新词到达后延迟查询，避免快速移动时频繁查询）
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self._DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounce)
        self._pending_word: str | None = None
        self._pending_parts: list[str] = []

        # 快捷键监听（pynput 线程 → Qt 信号桥接）
        self._bridge = _HotkeyBridge()
        self._bridge.activated.connect(self._on_activate)
        self._bridge.deactivated.connect(self._on_deactivate)
        self._hotkey = HotkeyListener(
            on_activate=self._bridge.activated.emit,
            on_deactivate=self._bridge.deactivated.emit,
        )

        # 系统托盘
        self._tray = TrayManager()
        self._tray.sig_toggle_capture.connect(self._on_tray_toggle)
        self._tray.sig_capture_mode_changed.connect(self._on_capture_mode_changed)
        self._tray.sig_quit.connect(self._quit)
        self._tray.set_capture_mode_checked(saved_mode_key)
        self._tray.show()

        # 启动键盘监听
        self._hotkey.start()
        logger.info("已启动 — 连按两次 Ctrl 激活取词，Esc 退出取词模式")

    # ── 取词模式控制 ──────────────────────────────────────

    def _on_activate(self):
        self._last_word = None
        self._pending_word = None
        self._last_pos = (0, 0)
        self._poll_timer.start()
        self._tray.set_capture_enabled(True)
        self._tray.show_message("QECDict", "取词模式已开启", 500)

    def _on_deactivate(self):
        self._poll_timer.stop()
        self._debounce_timer.stop()
        self._pending_word = None
        self._popup.hide_popup()
        self._last_word = None
        self._tray.set_capture_enabled(False)

    def _on_tray_toggle(self):
        """托盘菜单点击「开启/关闭取词」→ 切换 HotkeyListener 状态。"""
        if self._hotkey.is_active:
            self._hotkey.stop()
            self._on_deactivate()
            self._tray.show_message("QECDict", "取词已关闭", 500)
        else:
            self._hotkey.start()
            self._tray.set_capture_enabled(False)
            self._tray.show_message("QECDict", "快捷键已开启，连按 Ctrl×2 取词", 500)

    _MODE_MAP = {
        "auto": CaptureMode.AUTO,
        "uia": CaptureMode.UIA_ONLY,
        "ocr": CaptureMode.OCR_ONLY,
    }
    _MODE_LABELS = {
        "auto": "自动（UIA→OCR）",
        "uia": "仅 UIA",
        "ocr": "仅 OCR",
    }

    def _on_capture_mode_changed(self, mode_key: str):
        """托盘菜单切换取词模式，保存到设置文件。"""
        mode = self._MODE_MAP.get(mode_key, CaptureMode.AUTO)
        self._capture.set_mode(mode)
        self._settings["capture_mode"] = mode_key
        save_settings(self._settings)
        label = self._MODE_LABELS.get(mode_key, mode_key)
        self._tray.show_message("QECDict", f"取词模式: {label}", 500)

    # ── 取词轮询 & 防抖 ──────────────────────────────────

    def _on_poll(self):
        """每 150ms 检测鼠标下的单词，新词触发防抖后异步查询。"""
        x, y = self._get_cursor_pos()

        # 鼠标未移动足够距离 → 跳过
        lx, ly = getattr(self, '_last_pos', (0, 0))
        if abs(x - lx) < self._MOUSE_MOVE_THRESHOLD and abs(y - ly) < self._MOUSE_MOVE_THRESHOLD:
            return
        self._last_pos = (x, y)

        word = self._capture.capture()
        if not word:
            if self._last_word or self._pending_word:
                self._debounce_timer.stop()
                self._popup.hide_popup()
                self._last_word = None
                self._pending_word = None
            return

        # 与当前展示词或待查词相同 → 跳过
        if word == self._last_word or word == self._pending_word:
            return

        # 新词 → 预先拆分复合词，启动防抖
        self._pending_word = word
        self._pending_parts = self._capture.split_word(word)
        self._debounce_timer.start()

    def _on_debounce(self):
        """防抖到期 → 将查询请求发送到后台线程。"""
        if not self._pending_word:
            return
        self._last_word = self._pending_word
        self._sig_lookup.emit(self._pending_word, self._pending_parts)
        self._pending_word = None

    def _on_lookup_result(self, word: str, data):
        """后台查询完成 → 在主线程显示弹窗。"""
        # 查询期间单词已变 → 丢弃过期结果
        if word != self._last_word:
            return
        if data:
            x, y = self._get_cursor_pos()
            self._popup.show_word(data, x, y)

    @staticmethod
    def _get_cursor_pos() -> tuple[int, int]:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    # ── 退出 ──────────────────────────────────────────────

    def _quit(self):
        self._poll_timer.stop()
        self._debounce_timer.stop()
        self._hotkey.stop()
        self._tray.hide()
        self._worker_thread.quit()
        self._worker_thread.wait(1000)
        QApplication.quit()
        os._exit(0)


# ── 入口 ──────────────────────────────────────────────────

def main():
    # 设置 Per-Monitor DPI 感知（必须在 QApplication 之前调用）
    # 确保多显示器不同 DPI 下坐标正确，UI Automation 取词不受影响
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()  # 回退：System DPI Aware

    app = QApplication(sys.argv)
    app.setApplicationName("QECDict")
    app.setQuitOnLastWindowClosed(False)  # 关闭弹窗不退出程序

    controller = QuickDictApp()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
