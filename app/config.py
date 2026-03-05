from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

load_dotenv()
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    LLM_MODEL: str = os.getenv("LLM_MODEL") or "gemini-flash-latest"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL") or "INFO"
    
    AGENT_BROWSER_STREAM_PORT: int = os.getenv("AGENT_BROWSER_STREAM_PORT") or 9223
    AGENT_BROWSER_CMD: str = os.getenv("AGENT_BROWSER_CMD") or "agent-browser"

settings = Settings()