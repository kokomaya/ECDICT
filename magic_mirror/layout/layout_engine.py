"""排版引擎 — 将翻译结果映射为可渲染的 RenderBlock 列表。

职责单一：只负责坐标映射、字号计算和颜色采样的编排，
颜色采样委托给 color_sampler，不涉及 UI 渲染。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
from PyQt6.QtGui import QFont, QFontMetrics

from magic_mirror.config.settings import (
    FONT_FAMILY_ZH,
    FONT_SIZE_SCALE,
    MAX_FONT_SHRINK_RATIO,
)
from magic_mirror.interfaces.types import RenderBlock, TranslatedBlock
from magic_mirror.layout.color_sampler import sample_background_color, sample_text_color

logger = logging.getLogger(__name__)

# 当文字缩小到下限仍溢出时，允许宽度扩展的最大比例
_MAX_WIDTH_EXPAND = 1.3


class DefaultLayoutEngine:
    """ILayoutEngine 实现 — 将 TranslatedBlock 列表映射为 RenderBlock 列表。"""

    def compute_layout(
        self,
        blocks: List[TranslatedBlock],
        screenshot: np.ndarray,
        screen_bbox: Tuple[int, int, int, int],
    ) -> List[RenderBlock]:
        """计算每个翻译块的屏幕渲染参数。

        Args:
            blocks: 翻译后的文本块列表。
            screenshot: BGR 格式截图。
            screen_bbox: 截图对应的屏幕区域 (x, y, w, h)。

        Returns:
            可渲染的 RenderBlock 列表。
        """
        if not blocks:
            return []

        screen_x0, screen_y0 = screen_bbox[0], screen_bbox[1]
        results: List[RenderBlock] = []

        for block in blocks:
            src = block.source

            # ── 坐标映射：OCR bbox (相对截图) → 屏幕绝对坐标 ──
            bbox_left, bbox_top, bbox_w, bbox_h = _bbox_rect(src.bbox)
            sx = screen_x0 + bbox_left
            sy = screen_y0 + bbox_top

            # ── 字号计算 ──
            font_size, render_w = _fit_font_size(
                block.translated_text, src.font_size_est, bbox_w,
            )

            # 最终宽度：取 bbox 原宽与渲染宽度中的较大者（受扩展上限约束）
            final_w = max(bbox_w, min(render_w, int(bbox_w * _MAX_WIDTH_EXPAND)))

            # ── 颜色采样 ──
            bg_color = sample_background_color(screenshot, src.bbox)
            text_color = sample_text_color(screenshot, src.bbox, bg_color)

            results.append(RenderBlock(
                screen_x=sx,
                screen_y=sy,
                width=final_w,
                height=bbox_h,
                translated_text=block.translated_text,
                font_size=font_size,
                bg_color=bg_color,
                text_color=text_color,
            ))

        return results


# ------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------

def _bbox_rect(bbox: list) -> Tuple[int, int, int, int]:
    """四角坐标 → (left, top, width, height) 轴对齐矩形。"""
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    left = int(min(xs))
    top = int(min(ys))
    width = max(int(max(xs)) - left, 1)
    height = max(int(max(ys)) - top, 1)
    return left, top, width, height


def _fit_font_size(
    text: str,
    font_size_est: float,
    bbox_width: int,
) -> Tuple[int, int]:
    """计算适合 bbox 宽度的字号。

    Args:
        text: 要渲染的中文文本。
        font_size_est: OCR 估算的原始字号。
        bbox_width: bbox 的像素宽度。

    Returns:
        (final_font_size, text_render_width)
    """
    base_size = max(int(font_size_est * FONT_SIZE_SCALE), 8)
    min_size = max(int(base_size * MAX_FONT_SHRINK_RATIO), 8)

    # 从基础字号开始，如果溢出则逐步缩小
    font_size = base_size
    render_w = _measure_text_width(text, font_size)

    if render_w <= bbox_width:
        return font_size, render_w

    # 按比例缩小到刚好不溢出，但不低于下限
    ratio = bbox_width / max(render_w, 1)
    font_size = max(int(base_size * ratio), min_size)
    render_w = _measure_text_width(text, font_size)

    return font_size, render_w


def _measure_text_width(text: str, font_size: int) -> int:
    """用 QFontMetrics 测量文本渲染宽度。"""
    font = QFont(FONT_FAMILY_ZH, font_size)
    fm = QFontMetrics(font)
    return fm.horizontalAdvance(text)