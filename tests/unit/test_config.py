from care_lifeline.config import Settings


def test_defaults() -> None:
    settings = Settings(llm_mode="mock")
    assert settings.llm_mode == "mock"
    assert settings.qc_risk_threshold == 0.75
    assert settings.api_port == 8000
    assert settings.database_url.startswith("sqlite")


def test_real_mode() -> None:
    settings = Settings(llm_mode="real")
    assert settings.llm_mode == "real"


def test_override() -> None:
    settings = Settings(llm_mode="mock", qc_risk_threshold=0.9, api_port=9000)
    assert settings.qc_risk_threshold == 0.9
    assert settings.api_port == 9000
