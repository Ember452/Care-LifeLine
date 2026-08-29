"""药盒 OCR 双引擎（stub / rapidocr 可选依赖）的行为测试。"""


from care_lifeline.config import get_settings
from care_lifeline.tools.ocr import PillboxVision, RapidOcrVision, StubVision, build_vision


def test_pillbox_returns_placeholder_items_with_note() -> None:
    result = PillboxVision().interpret(b"\x89PNG fake image bytes")
    assert isinstance(result.items, list)
    assert result.items[0]["name"]
    assert "占位" in result.note


def test_default_engine_is_stub() -> None:
    vision = build_vision()
    assert isinstance(vision, StubVision)


def test_rapidocr_unavailable_falls_back_to_stub(monkeypatch) -> None:
    """选 rapidocr 但引擎初始化失败（未安装 ocr 依赖组）：回落占位并记警告。"""

    def _boom(self) -> None:
        raise ModuleNotFoundError("rapidocr_onnxruntime not installed")

    monkeypatch.setattr(RapidOcrVision, "__init__", _boom)
    vision = build_vision("rapidocr")
    assert isinstance(vision, StubVision)


def test_rapidocr_engine_parses_lines_with_dose_markers(monkeypatch) -> None:
    """引擎输出的文本行解析为候选条目：含剂量单位的行被标记、置信度保留。"""
    vision = RapidOcrVision.__new__(RapidOcrVision)  # 跳过真实引擎初始化

    class _FakeEngine:
        def __call__(self, image_bytes: bytes):
            return (
                [
                    ["box1", "阿托伐他汀钙片 20mg", 0.97],
                    ["box2", "每日一次", 0.85],
                    ["box3", "", 0.9],
                ],
                [0.1, 0.2],
            )

    vision._engine = _FakeEngine()
    result = vision.interpret(b"fake")
    assert len(result.items) == 2
    first = result.items[0]
    assert first["name"] == "阿托伐他汀钙片 20mg"
    assert "mg" in first["dosage"]
    assert first["confidence"] == 0.97
    assert "药师" in result.note


def test_rapidocr_engine_empty_result_is_honest() -> None:
    vision = RapidOcrVision.__new__(RapidOcrVision)

    class _EmptyEngine:
        def __call__(self, image_bytes: bytes):
            return (None, None)

    vision._engine = _EmptyEngine()
    result = vision.interpret(b"fake")
    assert result.items == []
    assert "未从图片中识别出文本" in result.note


def test_engine_config_selects_stub_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("CARE_OCR_ENGINE", "stub")
    get_settings.cache_clear()
    try:
        assert isinstance(build_vision(), StubVision)
    finally:
        get_settings.cache_clear()
