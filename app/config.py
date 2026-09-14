import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def csv_env(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


def origins() -> list[str]:
    return csv_env("CORS_ORIGINS", "http://localhost:3000,https://jobsi-ten.vercel.app")


def integer_env(name: str, default: int, minimum: int = 1) -> int:
    return max(minimum, int(os.getenv(name, str(default))))
