"""药盒拍照识别（PillboxVision，P2）。

双引擎同接口：
- ``RapidOcrVision``：本地 onnxruntime OCR（可选依赖 ``rapidocr-onnxruntime``，
  模型打包在 wheel 内、离线可用），把识别文本行解析为药品条目；
- ``StubVision``：确定性占位实现（零依赖，CI/未装引擎时回落）。

选择逻辑见 :func:`build_vision`：按配置引擎名，未安装/初始化失败回落占位
并在 note 中如实声明。不执行任何诊断。
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from care_lifeline.config import get_settings

logger = logging.getLogger(__name__)


class PillboxResult(BaseModel):
    items: list[dict]
    note: str


class StubVision:
    """确定性占位实现：保证接口与下游流程可用且可测试。"""

    def interpret(self, image_bytes: bytes) -> PillboxResult:
        _ = image_bytes
        return PillboxResult(
            items=[
                {"name": "示例药品（占位）", "dosage": "未知", "confidence": 0.0},
            ],
            note=(
                "OCR 为占位实现（未安装 rapidocr 引擎），请由药师/医生核对实物标签，"
                "本结果不可作为用药依据。"
            ),
        )


class RapidOcrVision:
    """基于 rapidocr 的本地 OCR 引擎。

    文本行 → 药品条目的解析是启发式的：每行作为一个候选条目，行内含
    「mg/片/粒/胶囊」等剂量线索时标记为疑似剂量。置信度取 OCR 自身的
    文本框得分，仅代表"读到了字"，不代表药品识别正确。
    """

    _DOSE_MARKERS = ("mg", "片", "粒", "胶囊", "袋", "ml", "喷", "贴")

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

        self._engine = RapidOCR()

    def interpret(self, image_bytes: bytes) -> PillboxResult:
        # RapidOCR 接受图片字节；返回 [[box, text, score], ...] 或 None
        raw, _elapsed = self._engine(image_bytes) or (None, None)
        items: list[dict] = []
        for entry in raw or []:
            text = str(entry[1]).strip()
            score = float(entry[2]) if len(entry) > 2 else 0.0
            if not text:
                continue
            lowered = text.lower()
            dosage = next((m for m in self._DOSE_MARKERS if m in lowered), None)
            items.append(
                {
                    "name": text,
                    "dosage": f"疑似剂量单位：{dosage}" if dosage else "未知",
                    "confidence": round(score, 3),
                }
            )
        if not items:
            return PillboxResult(
                items=[],
                note="OCR 未从图片中识别出文本，请确认照片清晰后重试；结果仅供药师/医生核对参考。",
            )
        return PillboxResult(
            items=items,
            note="OCR 结果（rapidocr 本地引擎）仅是文字识别，药品判断请由药师/医生核对实物标签。",
        )


def build_vision(engine: Literal["auto", "stub", "rapidocr"] | None = None):
    """按配置选择识别引擎；rapidocr 不可用时回落占位实现并记警告。"""
    resolved = engine or get_settings().ocr_engine
    if resolved == "rapidocr":
        try:
            return RapidOcrVision()
        except Exception as exc:
            logger.warning(
                "ocr_engine_unavailable", extra={"error_type": type(exc).__name__}
            )
    return StubVision()


class PillboxVision:
    """兼容入口：等价于按配置构建的引擎（既有调用方无需改动）。"""

    def __init__(self) -> None:
        self._engine = build_vision()

    def interpret(self, image_bytes: bytes) -> PillboxResult:
        return self._engine.interpret(image_bytes)
