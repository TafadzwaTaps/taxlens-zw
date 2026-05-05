"""
database.py — Supabase client initialisation.

Uses the official supabase-py client.
All DB operations go through `supabase_client` imported from here.

No SQLAlchemy. No ORM. Direct Supabase PostgREST calls.
"""

import sys
import logging
from pathlib import Path

# ── Load .env by absolute path ────────────────────────────────────────────────
# dotenv's load_dotenv() normally searches upward from the CWD.
# On Windows with uvicorn --reload the CWD is not always backend/, so we
# resolve the path relative to THIS file — always correct regardless of
# where uvicorn was launched from.
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

from supabase import create_client, Client
from config import settings

logger = logging.getLogger(__name__)

# ── Guard: fail with a clear message if credentials are missing ───────────────
if not settings.supabase_url or not settings.supabase_service_key:
    logger.error(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  MISSING SUPABASE CREDENTIALS\n"
        "\n"
        "  Create the file:  backend\\.env\n"
        "  Add these two lines:\n"
        "\n"
        "    SUPABASE_URL=https://your-project-ref.supabase.co\n"
        "    SUPABASE_SERVICE_KEY=your-service-role-secret-key\n"
        "\n"
        "  Get both from:\n"
        "  Supabase Dashboard → Project Settings → API\n"
        "  (use the 'service_role' key, NOT the anon key)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    sys.exit(1)

# ── Create the shared Supabase client ─────────────────────────────────────────
supabase_client: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_key,
)

logger.info("Supabase connected → %s", settings.supabase_url)
