import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://tracenet:tracenet_dev_password@localhost:5432/tracenet"

    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
