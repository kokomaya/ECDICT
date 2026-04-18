"""OCR 识别引擎 — IOcrEngine 的 RapidOCR 实现。

职责单一：接收 BGR 图像，返回带坐标的文本块列表。
不涉及截图、翻译、排版或渲染逻辑。

改进策略：
  - 多变体预处理（CLAHE、锐化、放大、二值化）
  - 多检测阈值：主阈值 + 低阈值补漏
  - 空间去重 + 文本相似度去重
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

from magic_mirror.config.settings import (
    OCR_CONFIDENCE_THRESHOLD,
    OCR_DET_BOX_THRESH,
    OCR_DET_BOX_THRESH_LOW,
    OCR_USE_GPU,
)
from magic_mirror.interfaces.types import TextBlock
from magic_mirror.ocr.preprocess import generate_variants

logger = logging.getLogger(__name__)


class RapidOcrEngine:
    """IOcrEngine 实现 — 使用 RapidOCR (ONNX Runtime) 进行文字识别。

    惰性加载模型：首次调用 recognize() 时才初始化 OCR 引擎，
    避免启动时占用内存和加载时间。

    识别策略：
      1. 对图像生成多种预处理变体
      2. 每种变体分别用主阈值和低阈值检测
      3. 空间去重合并候选结果
    """

    def __init__(self) -> None:
        self._ocr = None
        self._available: bool | None = None  # None = 尚未检测

    def recognize(self, image: np.ndarray) -> List[TextBlock]:
        """从图像中提取带位置信息的文本块。

        对图像生成多种预处理变体，逐一识别并合并结果。
        每种变体用主阈值和低阈值各跑一遍以提高召回率。

        Args:
            image: BGR 格式 numpy 数组。

        Returns:
            识别到的文本块列表，按 Y 坐标从上到下排序。
        """
        if not self._ensure_available():
            return []

        variants = generate_variants(image)
        candidates: List[TextBlock] = []

        orig_h, orig_w = image.shape[:2]

        # 多阈值检测：主阈值 + 低阈值补漏
        thresholds = [OCR_DET_BOX_THRESH]
        if OCR_DET_BOX_THRESH_LOW < OCR_DET_BOX_THRESH:
            thresholds.append(OCR_DET_BOX_THRESH_LOW)

        for variant in variants:
            vh, vw = variant.shape[:2]
            scale_x = orig_w / vw if vw != orig_w else 1.0
            scale_y = orig_h / vh if vh != orig_h else 1.0

            for thresh in thresholds:
                raw = self._run_ocr(variant, det_box_thresh=thresh)
                if not raw:
                    continue

                for bbox_points, text, confidence in raw:
                    text = text.strip()
                    if not text:
                        continue
                    if confidence < OCR_CONFIDENCE_THRESHOLD:
                        continue

                    # 缩放 bbox 回原图坐标
                    if scale_x != 1.0 or scale_y != 1.0:
                        bbox_points = [
                            [pt[0] * scale_x, pt[1] * scale_y]
                            for pt in bbox_points
                        ]

                    candidates.append(TextBlock(
                        text=text,
                        bbox=bbox_points,
                        font_size_est=self._estimate_font_size(bbox_points),
                        confidence=confidence,
                    ))

        # 空间去重：重叠区域 IoU > 阈值时只保留置信度最高的
        blocks = self._spatial_dedup(candidates)

        # 按 Y 坐标（bbox 左上角）排序，从上到下
        blocks.sort(key=lambda b: b.bbox[0][1])

        logger.debug("OCR 识别到 %d 个文本块 (候选 %d)", len(blocks), len(candidates))
        return blocks

    # ── 惰性加载 ──

    def _ensure_available(self) -> bool:
        """检查并惰性加载 OCR 引擎。加载失败后不再重试。"""
        if self._available is False:
            return False
        if self._ocr is not None:
            return True
        try:
            from rapidocr_onnxruntime import RapidOCR
            use_dml = OCR_USE_GPU and _has_dml_provider()
            self._ocr = RapidOCR(
                det_box_thresh=OCR_DET_BOX_THRESH,
                det_use_dml=use_dml,
                cls_use_dml=use_dml,
                rec_use_dml=use_dml,
            )
            self._available = True
            backend = "DirectML (GPU)" if use_dml else "CPU"
            logger.info("OCR 引擎已加载 (%s)", backend)
            return True
        except Exception as e:
            self._available = False
            logger.warning("OCR 引擎不可用: %s", e)
            return False

    # ── OCR 调用 ──

    def _run_ocr(
        self,
        image: np.ndarray,
        det_box_thresh: float | None = None,
    ) -> list[tuple] | None:
        """调用 RapidOCR 执行识别。

        Args:
            image: BGR 格式 numpy 数组。
            det_box_thresh: 检测框阈值，None 使用引擎默认值。

        Returns:
            [(bbox_points, text, confidence), ...] 或 None。
        """
        try:
            kwargs = {}
            if det_box_thresh is not None:
                kwargs["det_box_thresh"] = det_box_thresh
            result, _ = self._ocr(image, **kwargs)
            return result if result else None
        except Exception as e:
            logger.debug("OCR 调用异常: %s", e)
            return None

    # ── 字号估算 ──

    @staticmethod
    def _spatial_dedup(
        candidates: List[TextBlock],
        iou_threshold: float = 0.3,
    ) -> List[TextBlock]:
        """空间去重：对重叠的文本块只保留置信度最高的。

        两个 bbox 的 IoU（交集/并集）或交集占比超过阈值时认为重复。
        增加包含检测：小框被大框包含时也视为重复。
        """
        # 按置信度降序排列，优先保留高置信度
        sorted_cands = sorted(candidates, key=lambda b: b.confidence, reverse=True)
        kept: List[TextBlock] = []

        for cand in sorted_cands:
            r1 = _bbox_to_rect(cand.bbox)
            is_dup = False
            for existing in kept:
                r2 = _bbox_to_rect(existing.bbox)
                if _iou(r1, r2) > iou_threshold:
                    is_dup = True
                    break
                # 包含检测：候选框被已保留框包含
                if _contains(r2, r1):
                    is_dup = True
                    break
            if not is_dup:
                kept.append(cand)

        return kept

    @staticmethod
    def _estimate_font_size(bbox: list[list[float]]) -> float:
        """根据 bbox 高度估算字号（像素）。

        bbox 四角坐标: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        取左边高度和右边高度的平均值，对旋转文本更稳健。
        """
        left_h = abs(bbox[3][1] - bbox[0][1])
        right_h = abs(bbox[2][1] - bbox[1][1])
        return (left_h + right_h) / 2.0


# ------------------------------------------------------------------
# 模块级辅助
# ------------------------------------------------------------------

def _has_dml_provider() -> bool:
    """检测 ONNX Runtime 是否支持 DirectML。"""
    try:
        import onnxruntime
        return "DmlExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:
        return False


def _bbox_to_rect(bbox: list) -> tuple:
    """四角坐标 → (x_min, y_min, x_max, y_max)。"""
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    return (min(xs), min(ys), max(xs), max(ys))


def _iou(r1: tuple, r2: tuple) -> float:
    """计算两个轴对齐矩形的 IoU (Intersection over Union)。"""
    x1 = max(r1[0], r2[0])
    y1 = max(r1[1], r2[1])
    x2 = min(r1[2], r2[2])
    y2 = min(r1[3], r2[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0

    area1 = (r1[2] - r1[0]) * (r1[3] - r1[1])
    area2 = (r2[2] - r2[0]) * (r2[3] - r2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def _contains(outer: tuple, inner: tuple, margin: float = 2.0) -> bool:
    """判断 outer 矩形是否包含 inner 矩形（允许 margin 像素容差）。"""
    return (
        inner[0] >= outer[0] - margin
        and inner[1] >= outer[1] - margin
        and inner[2] <= outer[2] + margin
        and inner[3] <= outer[3] + margin
    )