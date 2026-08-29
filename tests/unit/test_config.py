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


def test_production_rejects_insecure_default_secret() -> None:
    """生产环境携带开发默认 JWT 密钥必须拒绝启动（P2-B）。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="CARE_JWT_SECRET"):
        Settings(care_env="production")


def test_production_with_custom_secret_ok() -> None:
    settings = Settings(care_env="production", jwt_secret="a" * 48)
    assert settings.jwt_secret == "a" * 48


def test_dev_allows_default_secret() -> None:
    settings = Settings(care_env="dev")
    assert settings.jwt_secret.startswith("dev-insecure")
