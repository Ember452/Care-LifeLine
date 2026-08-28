from __future__ import annotations

from pydantic import BaseModel


class PillboxResult(BaseModel):
    items: list[dict]
    note: str


class PillboxVision:
    """拍药盒识别（P2，离线占位实现）。

    生产环境应接入真实 OCR / 多模态模型；此处返回确定性占位结果，
    保证接口与下游流程可用且可测试。不执行任何诊断。
    """

    def interpret(self, image_bytes: bytes) -> PillboxResult:
        _ = image_bytes  # 真实实现会在此调用 OCR 模型
        return PillboxResult(
            items=[
                {"name": "示例药品（占位）", "dosage": "未知", "confidence": 0.0},
            ],
            note="OCR 为占位实现，请由药师/医生核对实物标签，本结果不可作为用药依据。",
        )
