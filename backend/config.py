"""
config.py — centralised settings using pydantic-settings.

Env vars are loaded from backend/.env (local dev) or the
Render environment (production).

The .env file is loaded by absolute path so it works correctly
on Windows when uvicorn --reload changes the working directory.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env relative to THIS file — not the CWD
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_key: str = ""
    app_env: str = "development"
    port: int = 8000
    tesseract_cmd: str = ""     # Windows only — path to tesseract.exe

    model_config = {
        "env_file": str(_env_path),
        "extra": "ignore",
    }


settings = Settings()

# Override pytesseract binary path on Windows if set
if settings.tesseract_cmd:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
