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
    # API key de DripFiles del bot: se usa en todas las subidas por defecto.
    # Vacío = plan free (salvo key propia del usuario si está permitido).
    dripfiles_api_key: str | None
    # Si True, los usuarios pueden guardar su propia key con /apikey.
    # Si False, siempre se usa la del bot (o free si no hay DRIPFILES_API_KEY).
    allow_user_api_keys: bool
    # plantilla del mensaje/descripción en DripFiles
    # placeholders: {filename} {size} {count}
    dripfiles_message: str
    # minutos sin actividad antes de cancelar una sesión /zip
    zip_timeout_minutes: int
    # tope de transferencias simultáneas (bot público)
    max_concurrent_per_user: int
    max_concurrent_global: int
    # 0 = no comprobar. Si el disco libre baja de esto, se rechazan descargas.
    min_free_disk_bytes: int
    # jobs de resubida por usuario (el global 2000 sigue en db.py)
    pending_jobs_per_user: int


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on", "y", "si", "sí")


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    if minimum is not None and n < minimum:
        return default
    return n


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
        dripfiles_api_key=_env("DRIPFILES_API_KEY"),
        # Por defecto True: cualquiera puede poner /apikey. Pon false para
        # forzar siempre la key del bot (o free).
        allow_user_api_keys=_env_bool("ALLOW_USER_API_KEYS", True),
        # Solo el nombre: el tamaño ya se ve en la página de DripFiles
        dripfiles_message=_env("DRIPFILES_MESSAGE") or "{filename}",
        zip_timeout_minutes=timeout,
        max_concurrent_per_user=_env_int("MAX_CONCURRENT_PER_USER", 2, minimum=1),
        max_concurrent_global=_env_int("MAX_CONCURRENT_GLOBAL", 8, minimum=1),
        min_free_disk_bytes=_env_int("MIN_FREE_DISK_GB", 2, minimum=0) * 1024**3,
        pending_jobs_per_user=_env_int("PENDING_JOBS_PER_USER", 20, minimum=1),
    )
