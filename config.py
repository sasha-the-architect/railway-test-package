"""
NEO Controller Configuration
=============================
Railway deployment configuration and environment variables.

All configuration is loaded from environment variables with sensible defaults.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Railway Deployment:
    - DATABASE_URL: PostgreSQL connection string (auto-provided by Railway)
    - REDIS_URL: Redis connection for caching (optional)
    - BTC_RPC_URL: Bitcoin Core RPC endpoint
    - BTC_RPC_USER: RPC username
    - BTC_RPC_PASSWORD: RPC password
    """
    
    # Application
    app_name: str = "NEO Controller"
    version: str = "1.0.0"
    environment: str = "production"
    debug: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = "/var/log/neo_controller.log"
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Database (Railway PostgreSQL)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/neo_controller"
    )
    
    # Redis (optional, for caching)
    redis_url: Optional[str] = os.getenv("REDIS_URL")
    
    # Bitcoin RPC Configuration
    bitcoin_rpc_url: str = os.getenv("BTC_RPC_URL", "http://localhost:8332")
    bitcoin_rpc_user: str = os.getenv("BTC_RPC_USER", "")
    bitcoin_rpc_password: str = os.getenv("BTC_RPC_PASSWORD", "")
    bitcoin_wallet_name: str = os.getenv("BTC_WALLET_NAME", "neo_controller")
    
    # Security
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "change-this-in-production")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-in-production")
    neo_public_key: str = os.getenv("NEO_PUBLIC_KEY", "")
    
    # CORS
    cors_origins: List[str] = ["*"]
    
    # Distribution Settings
    distribution_epoch_hours: int = 24
    distribution_instances_share: float = 0.50  # 50% to instances
    distribution_working_capital: float = 0.30   # 30% to treasury
    distribution_legal_defense: float = 0.20      # 20% to legal defense
    min_confirmations: int = 6
    max_batch_size: int = 50
    retry_attempts: int = 3
    retry_delay_seconds: int = 60
    
    # Monitoring
    wallet_change_threshold_btc: float = 0.001
    bank_change_threshold_fiat: float = 100.0
    monitoring_interval_seconds: int = 10
    
    # Enforcement
    auto_disconnect_on_tamper: bool = True
    log_ip_on_violation: bool = True
    quarantine_enabled: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
