from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 开发默认密钥：生产环境（care_env="production"）携带该值必须拒绝启动（P2-B）。
_INSECURE_DEV_SECRET = "dev-insecure-secret-change-me-please-rotate-in-prod"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    All variables are prefixed with ``CARE_`` (e.g. ``CARE_LLM_MODE``).
    Sensible defaults allow the full stack to run in ``mock`` mode without
    any external services.
    """

    model_config = SettingsConfigDict(
        env_prefix="CARE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_mode: Literal["mock", "real"] = "mock"
    # Real LLM (OpenAI-compatible): 火山方舟 Doubao / DeepSeek 均兼容此协议。
    # 切换模型只需改 base_url + model + api_key。
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_api_key: str = ""  # 占位：sk-......
    llm_model: str = "doubao-seed-1-6-250615"
    llm_model_mini: str = "doubao-seed-1-6-250615"
    database_url: str = "sqlite+aiosqlite:///./care.db"
    qc_risk_threshold: float = Field(default=0.75, gt=0.0, le=1.0)
    api_port: int = 8000
    # 运行环境：production 下强制校验 jwt_secret 等安全配置。
    care_env: Literal["dev", "production"] = "dev"
    jwt_secret: str = _INSECURE_DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # RAG：默认关闭（零依赖内存库）。配置 qdrant_url 后启用 Qdrant 向量库。
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    rag_collection: str = "care_guidelines"
    rag_enabled: bool = False
    # 外部药物相互作用数据源（openFDA 药品标签）。默认关闭走本地 DDI 表；
    # 开启后查询失败/超时自动降级回本地表，不影响可用性。
    external_ddi_enabled: bool = False
    openfda_base_url: str = "https://api.fda.gov"
    openfda_timeout_seconds: float = Field(default=3.0, gt=0)
    # 数据飞轮反馈集路径：测试必须重定向到临时目录，避免污染真实评测数据。
    feedback_data_path: str = "data/eval/feedback_cases.json"
    # 主动触发调度间隔（秒）
    proactive_interval_seconds: int = Field(default=300, gt=10)
    # 单会话 token 预算护栏（§10.4）：累计超过即拒绝新请求；0 = 不限额。
    session_token_budget: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _reject_insecure_secret_in_production(self) -> "Settings":
        if self.care_env == "production" and self.jwt_secret == _INSECURE_DEV_SECRET:
            raise ValueError("CARE_JWT_SECRET 仍为开发默认值：生产环境必须通过环境变量注入强密钥")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
