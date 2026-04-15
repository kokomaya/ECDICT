"""
_ocr_capture.py — OCR 截屏取词。

职责单一：截取鼠标周围区域，调用 RapidOCR 识别文字，
根据鼠标相对位置定位最近的英文单词。
不含 UI Automation 逻辑或弹窗逻辑。
"""
import ctypes
import re

from quickdict._word_utils import clean_word, extract_word_at_position
from quickdict._ocr_preprocess import preprocess_variants
from quickdict.config import logger

# 截图区域：鼠标周围的半宽/半高（逻辑像素，会根据 DPI 缩放）
_HALF_W = 200
_HALF_H = 80

# OCR 置信度阈值
_MIN_CONFIDENCE = 0.25

# 结果框到鼠标中心的最大距离（像素），超出则忽略
_MAX_BOX_DISTANCE = 200


def _get_screen_scale() -> float:
    """获取主显示器的 DPI 缩放因子（1.0 = 100%, 1.5 = 150%）。"""
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


class OcrCapture:
    """OCR 截屏取词器（懒加载模型）。"""

    def __init__(self):
        self._ocr = None
        self._available: bool | None = None  # None = 未检测

    # ── 公开接口 ──────────────────────────────────────────

    def capture(self, x: int, y: int) -> str | None:
        """
        截取 (x, y) 周围区域并 OCR 识别，返回鼠标位置处的英文单词。

        截图一次，生成多种预处理变体，依次识别直到首个有效结果。
        如果 RapidOCR 未安装或所有变体均识别失败，返回 None。
        """
        if not self._ensure_available():
            return None

        img, hw, hh = self._grab_region(x, y)
        if img is None:
            return None

        variants = preprocess_variants(img)
        for idx, variant in enumerate(variants):
            results = self._recognize(variant)
            if not results:
                continue
            word = self._pick_word(results, hw, hh)
            if word:
                logger.debug("OCR 命中变体№%d → %s", idx + 1, word)
                return word

        logger.debug("OCR 所有变体均未命中")
        return None

    # ── 懒加载 ────────────────────────────────────────────

    def _ensure_available(self) -> bool:
        """检查并懒加载 OCR 引擎。加载失败后不再重试。"""
        if self._available is False:
            return False
        if self._ocr is not None:
            return True
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR(
                det_box_thresh=0.3,
                det_unclip_ratio=2.0,
            )
            self._available = True
            logger.info("OCR 引擎已加载")
            return True
        except Exception as e:
            self._available = False
            logger.info("OCR 引擎不可用，跳过 OCR 取词: %s", e)
            return False

    # ── 截图 ──────────────────────────────────────────────

    @staticmethod
    def _grab_region(x: int, y: int):
        """截取鼠标周围区域（DPI 自适应），返回 (PIL Image, half_w, half_h) 或 (None, 0, 0)。"""
        try:
            from PIL import ImageGrab
            scale = _get_screen_scale()
            hw = int(_HALF_W * scale)
            hh = int(_HALF_H * scale)
            bbox = (x - hw, y - hh, x + hw, y + hh)
            img = ImageGrab.grab(bbox=bbox)
            return img, img.width // 2, img.height // 2
        except Exception:
            return None, 0, 0

    # ── OCR 识别 ──────────────────────────────────────────

    def _recognize(self, img) -> list[tuple] | None:
        """
        调用 RapidOCR 识别图片。

        返回 [(box, text, confidence), ...] 或 None。
        box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        """
        try:
            result, _ = self._ocr(img)
            return result if result else None
        except Exception:
            return None

    # ── 定位单词 ──────────────────────────────────────────

    @staticmethod
    def _pick_word(results: list[tuple], cursor_rel_x: float,
                   cursor_rel_y: float) -> str | None:
        """
        从 OCR 结果中找到距离鼠标最近的文本框，
        再根据鼠标在框内的相对位置提取对应单词。
        """
        best_word: str | None = None
        best_dist = float("inf")

        for box, text, confidence in results:
            if confidence < _MIN_CONFIDENCE:
                continue

            # 跳过不含英文字母的结果
            if not re.search(r"[a-zA-Z]{2,}", text):
                continue

            # 文本框中心
            cx = sum(p[0] for p in box) / 4
            cy = sum(p[1] for p in box) / 4
            dist = ((cx - cursor_rel_x) ** 2 + (cy - cursor_rel_y) ** 2) ** 0.5

            if dist > _MAX_BOX_DISTANCE or dist >= best_dist:
                continue

            # 鼠标在文本框内的相对 X 位置 → 字符位置
            box_left = min(p[0] for p in box)
            box_right = max(p[0] for p in box)
            box_width = box_right - box_left

            if box_width > 0 and len(text) > 0:
                char_pos = int(
                    (cursor_rel_x - box_left) / box_width * len(text)
                )
                char_pos = max(0, min(char_pos, len(text) - 1))
                raw = extract_word_at_position(text, char_pos)
            else:
                # 框太窄，取整段中第一个英文单词
                m = re.search(r"[a-zA-Z]{2,}", text)
                raw = m.group(0) if m else None

            word = clean_word(raw)
            if word:
                best_dist = dist
                best_word = word

        return best_word
