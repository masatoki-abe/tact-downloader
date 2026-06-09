import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

THERS_UPN = os.environ.get("THERS_UPN", "")
THERS_PASSWORD = os.environ.get("THERS_PASSWORD", "")
TOTP_SEED = os.environ.get("TOTP_SEED", "")
TACT_BASE_URL = os.environ.get("TACT_BASE_URL", "https://tact.ac.thers.ac.jp").rstrip("/")
VAULT_ROOT = os.environ.get("VAULT_ROOT", str(Path.home() / "document" / "obsidian-vault"))
DOWNLOAD_BASE = os.environ.get("DOWNLOAD_BASE", "大学")
SITE_TITLE_PATTERNS = os.environ.get(
    "SITE_TITLE_PATTERNS",
    "春1期,春2期,秋1期,秋2期,春学期,秋学期,前期,後期,通年",
)
HISTORY_FILE = str(Path(VAULT_ROOT) / ".tact_history.json")


def parse_totp_seed(raw: str) -> str:
    """TOTPシード値の前処理。
    - OTP Auth URL (otpauth://) から secret パラメータを抽出
    - 空白・ハイフンを除去
    """
    if not raw:
        return raw
    if raw.startswith("otpauth://"):
        params = parse_qs(urlparse(raw).query)
        seed = params.get("secret", [""])[0]
        if seed:
            return seed
    return raw.replace(" ", "").replace("-", "")
