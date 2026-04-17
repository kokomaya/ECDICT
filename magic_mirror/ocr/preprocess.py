"""OCR 图像预处理变体生成。

职责单一：接收 BGR numpy 数组，生成多种预处理变体列表，
供 OCR 引擎多策略重试使用。不含截图、OCR 识别或翻译逻辑。
仅依赖 cv2 和 numpy。
"""

from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_UPSCALE_FACTOR = 2


def generate_variants(image: np.ndarray) -> List[np.ndarray]:
    """将 BGR 图像转换为预处理变体列表。

    返回 BGR numpy array 列表，按优先级排列。

    当前策略：仅使用原图（GPU 加速后速度足够，多变体收益低）。
    对低分辨率文字（行高 < 30px），额外添加 2× 放大变体。

    Args:
        image: BGR 格式 numpy 数组。

    Returns:
        预处理变体列表（均为 BGR numpy 数组）。
    """
    variants: List[np.ndarray] = [image]

    # 低分辨率图像补充 2× 放大变体
    h = image.shape[0]
    if h < 80:
        try:
            upscaled = cv2.resize(
                image, None,
                fx=_UPSCALE_FACTOR, fy=_UPSCALE_FACTOR,
                interpolation=cv2.INTER_CUBIC,
            )
            variants.append(upscaled)
        except Exception as e:
            logger.debug("2x 放大失败: %s", e)

    return variants