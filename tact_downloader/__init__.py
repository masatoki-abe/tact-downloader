import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

TACT_BASE_URL = os.environ.get("TACT_BASE_URL", "https://tact.ac.thers.ac.jp").rstrip("/")
VAULT_ROOT = os.environ.get("VAULT_ROOT", str(Path.home() / "document" / "obsidian-vault"))
DOWNLOAD_BASE = os.environ.get("DOWNLOAD_BASE", "大学")
SITE_TITLE_PATTERNS = os.environ.get(
    "SITE_TITLE_PATTERNS",
    "春1期,春2期,秋1期,秋2期,春学期,秋学期,前期,後期,通年",
)
COOKIE_FILE = str(Path.home() / ".tact_cookies.json")
