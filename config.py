"""
Configuration settings for Dify SSE Proxy API
"""
from pydantic_settings import BaseSettings
from os import getenv


class Settings(BaseSettings):
    # Dify API Configuration
    DIFY_BASE_URL: str = getenv("DIFY_BASE_URL")
    DIFY_API_KEY: str = getenv("DIFY_API_KEY")
    DIFY_ENDPOINT: str = "/workflows/run"
    
    # API Configuration
    API_TITLE: str = "Dify SSE Simplified Proxy API"
    API_DESCRIPTION: str = "A FastAPI wrapper for Dify SSE streaming with simplified output"
    API_VERSION: str = "1.0.0"
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # SSE Configuration
    SSE_KEEPALIVE_TIMEOUT: int = 30  # seconds
    SSE_CHUNK_TIMEOUT: int = 60      # seconds
    
    class Config:
        env_file = ".env"


settings = Settings()