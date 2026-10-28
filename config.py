import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    MAX_IMAGE_DIMENSION = 5000
    OUTPUT_FOLDER = PROJECT_ROOT / "outputs"
