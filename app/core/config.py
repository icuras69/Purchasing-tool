from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_FRONTEND_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _split_csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    app_name: str = "Purchasing AI"
    debug: bool = True
    database_url: str = "postgresql://postgres@localhost:5432/purchasing_ai"
    database_auto_create_tables: bool = False
    frontend_origin: str = ""
    cors_origins: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    llm_provider: str = "mock"
    enable_real_llm: bool = False
    orderpro_api_base_url: str = ""
    orderpro_api_token: str = ""
    orderpro_sync_enabled: bool = False
    orderpro_base_url: str = ""
    orderpro_api_key: str = ""
    orderpro_inventory_endpoint: str = ""
    orderpro_timeout_seconds: int = 30
    orderpro_rate_limit_max_retries: int = 3
    forecast_demand_lookback_days: int = 90
    forecast_min_history_days: int = 14
    orderpro_historical_demand_statuses: str = "shipped"
    orderpro_open_demand_statuses: str = "confirmed,packed,backorder"
    orderpro_excluded_demand_statuses: str = "cancelled"
    orderpro_demand_included_statuses: str = "shipped"
    legacy_demand_quantity_mode: str = "net_qty"
    legacy_demand_stale_days: int = 180
    legacy_demand_lookback_days: int | None = None
    allow_stale_demand_recommendations: bool = False
    recommendation_require_pack_size: bool = False
    recommendation_require_cost: bool = False
    recommendation_allow_stale_demand: bool = False
    auth_enabled: bool = True
    admin_email: str = ""
    admin_password_hash: str = ""
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.legacy_demand_quantity_mode not in {"net_qty", "qty_used"}:
            raise ValueError("LEGACY_DEMAND_QUANTITY_MODE must be either 'net_qty' or 'qty_used'.")
        if self.legacy_demand_stale_days <= 0:
            raise ValueError("LEGACY_DEMAND_STALE_DAYS must be greater than zero.")
        if self.legacy_demand_lookback_days is not None and self.legacy_demand_lookback_days <= 0:
            raise ValueError("LEGACY_DEMAND_LOOKBACK_DAYS must be greater than zero or unset.")
        if not self.debug and self.auth_enabled:
            missing = [
                name
                for name, value in (
                    ("ADMIN_EMAIL", self.admin_email),
                    ("ADMIN_PASSWORD_HASH", self.admin_password_hash),
                    ("JWT_SECRET_KEY", self.jwt_secret_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Missing required security environment variables when DEBUG=false: "
                    + ", ".join(missing)
                )
        return self

    def allowed_cors_origins(self) -> list[str]:
        origins = list(LOCAL_FRONTEND_ORIGINS)
        origins.extend(_split_csv(self.frontend_origin))
        origins.extend(_split_csv(self.cors_origins))

        unique_origins: list[str] = []
        for origin in origins:
            if origin and origin not in unique_origins:
                unique_origins.append(origin)
        return unique_origins


settings = Settings()
