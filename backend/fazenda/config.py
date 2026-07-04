"""
Configurações centrais da aplicação — lidas de variáveis de ambiente / .env
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fazenda.db"
    secret_key: str = "change-me"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
