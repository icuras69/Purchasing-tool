from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Purchasing AI"
    debug: bool = True
    database_url: str= "postgresql://postgres:12345678@localhost:5432/purchasing_ai"
    openai_api_key: str = ""
    orderpro_base_url: str = ""
    orderpro_api_key: str = ""
    orderpro_inventory_endpoint: str = ""
    orderpro_timeout_seconds: int = 30
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
