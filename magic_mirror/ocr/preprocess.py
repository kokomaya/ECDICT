"""OCR 图像预处理变体生成。

职责单一：接收 BGR numpy 数组，生成多种预处理变体列表，
供 OCR 引擎多策略重试使用。不含截图、OCR 识别或翻译逻辑。
仅依赖 cv2 和 numpy。

变体策略：
  1. 原图
  2. CLAHE 对比度增强（提升低对比度文字识别率）
  3. 锐化（提升模糊文字识别率）
  4. 多级放大（低分辨率文字）
  5. 自适应二值化（极低对比度场景）
"""

from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 低分辨率阈值：低于此高度生成 2× 放大变体
_UPSCALE_THRESHOLD = 120
# 极低分辨率阈值：低于此高度额外生成 3× 放大变体
_UPSCALE_TINY_THRESHOLD = 50
# 低对比度阈值：灰度标准差低于此值时生成二值化变体
_LOW_CONTRAST_STD = 50


def generate_variants(image: np.ndarray) -> List[np.ndarray]:
    """将 BGR 图像转换为多种预处理变体列表。

    返回 BGR numpy array 列表，按优先级排列。
    多变体策略通过 OCR 引擎的空间去重合并结果，提升召回率。

    Args:
        image: BGR 格式 numpy 数组。

    Returns:
        预处理变体列表（均为 BGR numpy 数组）。
    """
    variants: List[np.ndarray] = [image]
    h = image.shape[0]

    # ── 1. CLAHE 对比度增强 ──
    clahe_img = _apply_clahe(image)
    if clahe_img is not None:
        variants.append(clahe_img)

    # ── 2. 锐化 ──
    sharp_img = _sharpen(image)
    if sharp_img is not None:
        variants.append(sharp_img)

    # ── 3. 多级放大（低分辨率文字） ──
    if h < _UPSCALE_THRESHOLD:
        up2 = _upscale(image, 2)
        if up2 is not None:
            variants.append(up2)
        if h < _UPSCALE_TINY_THRESHOLD:
            up3 = _upscale(image, 3)
            if up3 is not None:
                variants.append(up3)

    # ── 4. 自适应二值化（低对比度场景） ──
    bin_img = _adaptive_binarize(image)
    if bin_img is not None:
        variants.append(bin_img)

    return variants


# ------------------------------------------------------------------
# 内部变体生成函数
# ------------------------------------------------------------------

def _apply_clahe(image: np.ndarray) -> np.ndarray | None:
    """CLAHE 对比度增强：在 LAB 空间对 L 通道做自适应直方图均衡。"""
    try:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception as e:
        logger.debug("CLAHE 增强失败: %s", e)
        return None


def _sharpen(image: np.ndarray) -> np.ndarray | None:
    """Unsharp Mask 锐化：突出文字边缘。"""
    try:
        blurred = cv2.GaussianBlur(image, (0, 0), 3)
        return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    except Exception as e:
        logger.debug("锐化失败: %s", e)
        return None


def _upscale(image: np.ndarray, factor: int) -> np.ndarray | None:
    """双三次插值放大。"""
    try:
        return cv2.resize(
            image, None,
            fx=factor, fy=factor,
            interpolation=cv2.INTER_CUBIC,
        )
    except Exception as e:
        logger.debug("%dx 放大失败: %s", factor, e)
        return None


def _adaptive_binarize(image: np.ndarray) -> np.ndarray | None:
    """自适应二值化：仅在低对比度场景生成。

    将灰度图做 Gaussian 自适应阈值处理，转回 BGR 供 OCR 使用。
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if gray.std() >= _LOW_CONTRAST_STD:
            return None  # 对比度足够，不需要二值化
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2,
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        logger.debug("自适应二值化失败: %s", e)
        return None