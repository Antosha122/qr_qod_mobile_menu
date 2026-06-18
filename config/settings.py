from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Bot Configuration
    guest_bot_token: str
    staff_bot_token: str
    
    # Database Configuration
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "tokio_bar"
    db_user: str = "postgres"
    db_password: str

    # Database connection pool tuning (high-load resilience).
    # These map directly to asyncpg.create_pool() arguments.
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_command_timeout: int = 60
    
    # Application Settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "Europe/Moscow"
    
    # Restaurant Settings
    total_tables: int = 7
    
    # Network (optional proxy for regions where Telegram API is blocked)
    proxy_url: str = ""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    @property
    def database_url(self) -> str:
        """Construct database connection URL."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


# Global settings instance
settings = Settings()