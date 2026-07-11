"""
Configurações centrais da aplicação — lidas de variáveis de ambiente / .env
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fazenda.db"
    secret_key: str = "change-me"
    environment: str = "development"

    # Robô do Telegram (intake de documentos financeiros). Vazio = desligado.
    telegram_bot_token: str = ""            # token do @BotFather
    telegram_webhook_secret: str = ""       # segredo que valida chamadas do Telegram
    telegram_allowed_chat_ids: str = ""     # ids de chat liberados, separados por vírgula
    public_base_url: str = ""               # ex.: https://fazendaapp-production.up.railway.app

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
