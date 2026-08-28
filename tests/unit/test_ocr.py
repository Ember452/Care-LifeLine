from care_lifeline.tools.ocr import PillboxVision


def test_pillbox_returns_placeholder_items_with_note() -> None:
    result = PillboxVision().interpret(b"\x89PNG fake image bytes")
    assert isinstance(result.items, list)
    assert result.items[0]["name"]
    assert "占位" in result.note
