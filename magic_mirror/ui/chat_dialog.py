"""聊天对话框 — Claude Code 风格多轮对话 UI（支持 Markdown 富文本）。

职责单一：只负责聊天界面的展示与用户交互，
聊天逻辑委托给 ChatSession，模型管理委托给 model_service，
Markdown 渲染委托给 md_renderer。
"""

from __future__ import annotations

import html as html_mod
import logging
from typing import List

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from magic_mirror.chat.chat_service import ChatSession
from magic_mirror.chat.model_service import (
    list_models,
    load_selected_model,
    save_selected_model,
)
from magic_mirror.ui.md_renderer import MESSAGE_CSS, render_markdown

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 色彩系统（Claude Code 风格：深色、沉稳、高对比度）
# ------------------------------------------------------------------
_BG_WINDOW = "#181825"
_BG_CHAT = "#1e1e2e"
_BG_INPUT = "#242438"
_BG_SIDEBAR = "#1a1a2e"
_BG_HUMAN = "#2a2a3e"         # 用户消息行
_BG_AI = "transparent"        # AI 消息行
_BG_SYSTEM = "#2c1a1a"
_TEXT = "#cdd6f4"
_TEXT_DIM = "#6c7086"
_TEXT_HUMAN = "#89b4fa"        # 用户名标签
_TEXT_AI = "#a6e3a1"           # AI 名标签
_TEXT_ERR = "#f38ba8"
_ACCENT = "#cba6f7"            # 紫色强调
_ACCENT_DIM = "#45475a"
_BORDER = "#313244"
_INPUT_BORDER = "#45475a"
_INPUT_FOCUS = "#cba6f7"
_BTN_BG = "#cba6f7"
_BTN_TEXT = "#1e1e2e"
_BTN_HOVER = "#b4befe"
_SCROLLBAR = "#45475a"

_STYLE = f"""
QDialog {{
    background: {_BG_WINDOW};
    color: {_TEXT};
}}
QLabel {{
    background: transparent;
    color: {_TEXT_DIM};
}}

/* ── 顶部栏 ── */
QWidget#topBar {{
    background: {_BG_WINDOW};
    border-bottom: 1px solid {_BORDER};
}}
QLabel#logoLabel {{
    color: {_ACCENT};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#tokenBadge {{
    color: {_TEXT_DIM};
    font-size: 10px;
    background: {_ACCENT_DIM};
    border-radius: 9px;
    padding: 2px 8px;
}}
QComboBox {{
    background: {_BG_INPUT};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
}}
QComboBox:hover {{ border-color: {_ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {_BG_INPUT};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    selection-background-color: {_ACCENT_DIM};
    outline: 0;
}}

/* ── 对话区 ── */
QTextEdit#chatView {{
    background: {_BG_CHAT};
    border: none;
    padding: 0;
    selection-background-color: rgba(203,166,247,0.25);
}}

/* ── 输入区 ── */
QPlainTextEdit#inputBox {{
    background: {_BG_INPUT};
    color: {_TEXT};
    border: 1px solid {_INPUT_BORDER};
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: rgba(203,166,247,0.3);
}}
QPlainTextEdit#inputBox:focus {{ border-color: {_INPUT_FOCUS}; }}

QPushButton#sendBtn {{
    background: {_BTN_BG};
    color: {_BTN_TEXT};
    border: none;
    border-radius: 10px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#sendBtn:hover {{ background: {_BTN_HOVER}; }}
QPushButton#sendBtn:disabled {{ background: {_ACCENT_DIM}; color: {_TEXT_DIM}; }}

QPushButton#clearBtn {{
    background: transparent;
    color: {_TEXT_DIM};
    border: 1px solid {_BORDER};
    border-radius: 10px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton#clearBtn:hover {{ color: {_TEXT}; border-color: {_TEXT_DIM}; }}

/* ── 侧栏 ── */
QPlainTextEdit#ctxEdit {{
    background: {_BG_SIDEBAR};
    color: {_TEXT_DIM};
    border: none;
    padding: 8px;
    font-size: 11px;
    border-radius: 6px;
}}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {_SCROLLBAR};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

# 单条消息 HTML 模板
_MSG_TEMPLATE = """\
<div style="padding:10px 16px; margin:0; background:{bg}; border-bottom:1px solid #313244;">
  <div style="margin-bottom:3px;">
    <span style="color:{label_color}; font-weight:700; font-size:12px;">{icon} {label}</span>
    {extra}
  </div>
  <div style="color:#cdd6f4; font-size:13px; line-height:1.6;">
    {content}
  </div>
</div>
"""


# ------------------------------------------------------------------
# 后台工作线程
# ------------------------------------------------------------------

class _ModelListWorker(QRunnable):
    """后台加载可用模型列表。"""

    class Signals(QObject):
        finished = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.signals = self.Signals()

    def run(self) -> None:
        self.signals.finished.emit(list_models())


class _ChatStreamWorker(QRunnable):
    """后台流式发送聊天消息。"""

    class Signals(QObject):
        chunk = pyqtSignal(str)
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, session: ChatSession, user_input: str) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._session = session
        self._input = user_input

    def run(self) -> None:
        try:
            for piece in self._session.send_stream(self._input):
                self.signals.chunk.emit(piece)
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


# ------------------------------------------------------------------
# ChatDialog
# ------------------------------------------------------------------

class ChatDialog(QDialog):
    """Claude Code 风格多轮对话窗口。"""

    def __init__(self, context_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Magic Mirror Chat")
        self.setMinimumSize(700, 540)
        self.resize(820, 640)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_STYLE)

        self._context_text = context_text
        self._session: ChatSession | None = None
        self._streaming = False

        # 消息列表：[{"role": ..., "text": ...}, ...]
        self._messages: List[dict] = []
        # 流式累积文本
        self._stream_buf = ""
        # 防抖定时器（流式渲染）
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(80)
        self._render_timer.timeout.connect(self._render_all)

        self._build_ui()
        self._load_models()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部栏 ──
        top = QWidget()
        top.setObjectName("topBar")
        top.setFixedHeight(44)
        tb = QHBoxLayout(top)
        tb.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("⬡ Magic Mirror Chat")
        logo.setObjectName("logoLabel")
        tb.addWidget(logo)
        tb.addStretch()

        tb.addWidget(QLabel("Model"))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._combo.currentTextChanged.connect(self._on_model_changed)
        tb.addWidget(self._combo)

        self._token_badge = QLabel("0 tok")
        self._token_badge.setObjectName("tokenBadge")
        tb.addWidget(self._token_badge)

        root.addWidget(top)

        # ── 中间 (对话 + 侧栏) ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 对话区
        self._chat = QTextEdit()
        self._chat.setObjectName("chatView")
        self._chat.setReadOnly(True)
        body.addWidget(self._chat, 7)

        # 侧栏 — 原文参考
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background:{_BG_SIDEBAR}; border-left:1px solid {_BORDER};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(10, 10, 10, 10)
        sl.setSpacing(6)
        sl.addWidget(QLabel("📄 Reference Text"))
        ctx = QPlainTextEdit()
        ctx.setObjectName("ctxEdit")
        ctx.setReadOnly(True)
        ctx.setPlainText(self._context_text)
        ctx.setFont(QFont("Cascadia Code", 9))
        sl.addWidget(ctx)
        body.addWidget(sidebar)

        root.addLayout(body, 1)

        # ── 底部输入栏 ──
        bottom = QWidget()
        bottom.setStyleSheet(f"background:{_BG_WINDOW}; border-top:1px solid {_BORDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 8, 14, 10)
        bl.setSpacing(8)

        self._input = _ChatInputEdit()
        self._input.setObjectName("inputBox")
        self._input.sig_submit.connect(self._send)
        self._input.setPlaceholderText("Message Magic Mirror…    (Enter ↵ send · Shift+Enter ↵ newline)")
        self._input.setMaximumHeight(72)
        self._input.setFont(QFont("Microsoft YaHei", 10))
        bl.addWidget(self._input, 1)

        btns = QVBoxLayout()
        btns.setSpacing(4)
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.clicked.connect(self._send)
        btns.addWidget(self._send_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("clearBtn")
        self._clear_btn.clicked.connect(self._clear)
        btns.addWidget(self._clear_btn)
        bl.addLayout(btns)

        root.addWidget(bottom)

    # ------------------------------------------------------------------
    # 模型
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        self._combo.clear()
        self._combo.addItem("Loading…")
        self._combo.setEnabled(False)
        w = _ModelListWorker()
        w.signals.finished.connect(self._on_models_loaded)
        QThreadPool.globalInstance().start(w)

    @pyqtSlot(list)
    def _on_models_loaded(self, models: list) -> None:
        self._combo.clear()
        self._combo.setEnabled(True)
        if not models:
            self._combo.addItem("(no models)")
            return
        self._combo.addItems(models)
        saved = load_selected_model()
        if saved and saved in models:
            self._combo.setCurrentText(saved)
        self._init_session()

    def _on_model_changed(self, name: str) -> None:
        if not name or name in ("Loading…", "(no models)"):
            return
        save_selected_model(name)
        if self._session:
            self._session.model = name

    def _init_session(self) -> None:
        model = self._combo.currentText()
        if not model or model in ("Loading…", "(no models)"):
            return
        self._session = ChatSession(self._context_text, model)
        self._update_tokens()

    # ------------------------------------------------------------------
    # 发送 / 流式接收
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _send(self) -> None:
        if self._streaming:
            return
        text = self._input.toPlainText().strip()
        if not text or not self._session:
            if not self._session:
                self._init_session()
            if not text:
                return

        self._input.clear()
        self._messages.append({"role": "human", "text": text})
        self._messages.append({"role": "assistant", "text": ""})
        self._stream_buf = ""
        self._render_all()

        self._streaming = True
        self._send_btn.setEnabled(False)

        w = _ChatStreamWorker(self._session, text)
        w.signals.chunk.connect(self._on_chunk)
        w.signals.finished.connect(self._on_done)
        w.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(w)

    @pyqtSlot(str)
    def _on_chunk(self, piece: str) -> None:
        self._stream_buf += piece
        self._messages[-1]["text"] = self._stream_buf
        # 防抖：不是每个 chunk 都渲染，80ms 合并一次
        if not self._render_timer.isActive():
            self._render_timer.start()

    @pyqtSlot()
    def _on_done(self) -> None:
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._render_timer.stop()
        self._render_all()
        self._update_tokens()
        self._input.setFocus()

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._messages.append({"role": "error", "text": msg})
        self._render_timer.stop()
        self._render_all()
        self._update_tokens()

    @pyqtSlot()
    def _clear(self) -> None:
        if self._session:
            self._session.clear_history()
        self._messages.clear()
        self._chat.clear()
        self._update_tokens()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def _render_all(self) -> None:
        """将所有消息渲染为 HTML 并更新 chat view。"""
        parts: List[str] = [f"<style>{MESSAGE_CSS}</style>"]
        for msg in self._messages:
            parts.append(self._render_msg(msg))
        # 流式光标指示
        if self._streaming:
            parts.append(
                '<div style="padding:2px 18px; color:#6c7086; font-size:11px;">● generating…</div>'
            )
        full_html = "".join(parts)

        # 保持滚动到底部
        sb = self._chat.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 20
        self._chat.setHtml(full_html)
        if at_bottom:
            sb.setValue(sb.maximum())

    def _render_msg(self, msg: dict) -> str:
        role = msg["role"]
        text = msg["text"]

        if role == "human":
            escaped = html_mod.escape(text).replace("\n", "<br>")
            return _MSG_TEMPLATE.format(
                bg=_BG_HUMAN, label_color=_TEXT_HUMAN,
                icon="❯", label="Human", extra="",
                content=escaped,
            )
        elif role == "assistant":
            rendered = render_markdown(text) if text else '<span style="color:#6c7086;">…</span>'
            return _MSG_TEMPLATE.format(
                bg=_BG_AI, label_color=_TEXT_AI,
                icon="✦", label="Assistant", extra="",
                content=rendered,
            )
        else:  # error
            escaped = html_mod.escape(text)
            return _MSG_TEMPLATE.format(
                bg=_BG_SYSTEM, label_color=_TEXT_ERR,
                icon="⚠", label="Error", extra="",
                content=f'<span style="color:{_TEXT_ERR}">{escaped}</span>',
            )

    def _update_tokens(self) -> None:
        if self._session:
            t = self._session.estimate_tokens()
            self._token_badge.setText(f"{t} tok")
        else:
            self._token_badge.setText("0 tok")


# ------------------------------------------------------------------
# Enter = 发送，Shift+Enter = 换行
# ------------------------------------------------------------------

class _ChatInputEdit(QPlainTextEdit):
    sig_submit = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sig_submit.emit()
        else:
            super().keyPressEvent(event)
