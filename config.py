import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    # Vacío = bot abierto a todo el mundo. Con IDs = solo esos usuarios.
    allowed_users: frozenset[int]
    download_dir: str
    database_path: str
    # plantilla del mensaje/descripción en DripFiles
    # placeholders: {filename} {size} {count}
    dripfiles_message: str
    # minutos sin actividad antes de cancelar una sesión /zip
    zip_timeout_minutes: int


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_config() -> Config:
    missing = [
        name
        for name in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_BOT_TOKEN")
        if not _env(name)
    ]
    if missing:
        raise SystemExit(
            f"Faltan variables de entorno: {', '.join(missing)} (revisa .env.example)"
        )

    raw_users = _env("ALLOWED_USER_IDS") or ""
    allowed = frozenset(
        int(uid) for uid in raw_users.replace(" ", "").split(",") if uid
    )

    timeout = int(_env("ZIP_TIMEOUT_MINUTES") or 30)
    if timeout < 1:
        timeout = 30

    download_dir = _env("DOWNLOAD_DIR") or "downloads"
    db_path = _env("DATABASE_PATH") or os.path.join(download_dir, "dripfiles_bot.db")

    return Config(
        api_id=int(_env("TELEGRAM_API_ID")),
        api_hash=_env("TELEGRAM_API_HASH"),
        bot_token=_env("TELEGRAM_BOT_TOKEN"),
        allowed_users=allowed,
        download_dir=download_dir,
        database_path=db_path,
        # Solo el nombre: el tamaño ya se ve en la página de DripFiles
        dripfiles_message=_env("DRIPFILES_MESSAGE") or "{filename}",
        zip_timeout_minutes=timeout,
    )
