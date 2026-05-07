from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    anthropic_api_key: str = ""
    amc_client_id: str = ""
    amc_client_secret: str = ""
    amc_refresh_token: str = ""
    amc_instance_id: str = ""
    amc_advertiser_id: str = ""

    amc_base_url: str = "https://advertising-api.amazon.com"
    amc_api_version: str = "v1"

    cache_ttl_hours: int = 6


def load_settings() -> Settings:
    return Settings()
