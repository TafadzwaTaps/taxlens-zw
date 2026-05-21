"""
config.py — centralised settings. ADDED: jwt_secret field.
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_key: str = ""
    jwt_secret: str = "taxlens-change-this-in-production"   # NEW
    app_env: str = "development"
    port: int = 8000
    tesseract_cmd: str = ""

    model_config = {"env_file": str(_env_path), "extra": "ignore"}


settings = Settings()

if settings.tesseract_cmd:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
