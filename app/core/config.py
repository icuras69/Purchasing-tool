from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Purchasing AI"
    debug: bool = True
    database_url: str= "postgresql://postgres:12345678@localhost:5432/purchasing_ai"
    database_auto_create_tables: bool = False
    openai_api_key: str = ""
    llm_provider: str = "mock"
    enable_real_llm: bool = False
    orderpro_api_base_url: str = ""
    orderpro_api_token: str = ""
    orderpro_sync_enabled: bool = False
    orderpro_base_url: str = ""
    orderpro_api_key: str = ""
    orderpro_inventory_endpoint: str = ""
    orderpro_timeout_seconds: int = 30
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
