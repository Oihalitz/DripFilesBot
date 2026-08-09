"""Cliente de la API de DripFiles.

Free (sin key):  https://dripfiles.com/api/v1/free
  · ~2 GB, enlaces ~2 días, rate limit por IP

Autenticada (API key del usuario):  https://dripfiles.com/api/v1
  · límites del plan de la cuenta (tamaño, caducidad, …)
  · Authorization: Bearer <api_key>
  · body de create acepta `expire` (segundos) y `message`

Flujo (idéntico en free y auth):
  1. POST …/uploads              → upload_id + upload_token
  2. POST …/uploads/{id}/files   → trozos multipart (files[]) + Content-Range
  3. POST …/uploads/{id}/complete
  4. GET  …/uploads/{id}         → poll hasta status=ready → url
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import aiohttp

log = logging.getLogger("bot.dripfiles")

FREE_BASE = "https://dripfiles.com/api/v1/free"
AUTH_BASE = "https://dripfiles.com/api/v1"
DEFAULT_CHUNK = 1024 * 1024  # 1 MiB
# límites free conocidos (fallback si la API no responde info)
FREE_MAX_SIZE = 2 * 1024**3
FREE_EXPIRE_SECONDS = 2 * 24 * 3600
FREE_MAX_FILES = 50
# tope práctico por Telegram Premium (bots vía MTProto)
TELEGRAM_MAX_SIZE = 4 * 1024**3
READY_POLL_ATTEMPTS = 60
READY_POLL_DELAY = 0.75

# alias histórico
MAX_SIZE = FREE_MAX_SIZE


class DripFilesError(Exception):
    """Error al crear, subir o finalizar un envío en DripFiles."""


class DripFilesAuthError(DripFilesError):
    """API key inválida, revocada o sin permiso (401/403)."""


@dataclass(frozen=True)
class AccountLimits:
    tier: str
    max_size_bytes: int
    max_files: int
    expire_seconds: int
    chunk_size: int
    raw: dict

    @property
    def expire_days(self) -> float:
        return self.expire_seconds / 86400

    @property
    def is_free(self) -> bool:
        return self.tier == "free" or not self.tier


def _api_message(data: dict | None, fallback: str) -> str:
    if not isinstance(data, dict):
        return fallback
    return str(data.get("message") or data.get("error") or fallback)


async def _read_json(resp: aiohttp.ClientResponse) -> dict:
    try:
        data = await resp.json(content_type=None)
    except Exception as exc:
        text = await resp.text()
        raise DripFilesError(
            f"HTTP {resp.status}: respuesta no JSON ({text[:200]})"
        ) from exc
    if not isinstance(data, dict):
        raise DripFilesError(f"HTTP {resp.status}: JSON inesperado")
    return data


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key.strip()}"}


def _base(api_key: str | None) -> str:
    return AUTH_BASE if api_key else FREE_BASE


def _parse_limits(data: dict, *, fallback_free: bool = False) -> AccountLimits:
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else data
    if not isinstance(limits, dict):
        limits = {}

    def _int(*keys: str, default: int) -> int:
        for k in keys:
            v = limits.get(k)
            if v is None:
                v = data.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return int(v)
        return default

    max_size = _int(
        "max_size_bytes",
        "max_bytes",
        "upload_max_size",
        default=FREE_MAX_SIZE if fallback_free else TELEGRAM_MAX_SIZE,
    )
    # a veces solo viene en GB
    if max_size == (FREE_MAX_SIZE if fallback_free else TELEGRAM_MAX_SIZE):
        gb = limits.get("max_size_gb") or data.get("max_size_gb")
        if isinstance(gb, (int, float)) and gb > 0:
            max_size = int(gb * 1024**3)

    expire = _int(
        "expire_seconds",
        "expire",
        "default_expire",
        "link_expire_seconds",
        default=FREE_EXPIRE_SECONDS if fallback_free else FREE_EXPIRE_SECONDS,
    )
    if expire == FREE_EXPIRE_SECONDS:
        days = limits.get("expire_days") or data.get("expire_days")
        if isinstance(days, (int, float)) and days > 0:
            expire = int(days * 86400)

    max_files = _int("max_files", "files_max", default=FREE_MAX_FILES)
    chunk = _int(
        "recommended_chunk_bytes",
        "chunk_size",
        default=DEFAULT_CHUNK,
    )
    tier = str(
        data.get("tier")
        or data.get("plan")
        or limits.get("tier")
        or ("free" if fallback_free else "authenticated")
    )
    return AccountLimits(
        tier=tier,
        max_size_bytes=max_size,
        max_files=max_files,
        expire_seconds=expire,
        chunk_size=chunk,
        raw=data,
    )


async def get_free_limits(session: aiohttp.ClientSession) -> AccountLimits:
    try:
        async with session.get(f"{FREE_BASE}") as resp:
            data = await _read_json(resp)
            if data.get("ok") is False:
                raise DripFilesError(_api_message(data, "no se pudo leer límites free"))
            return _parse_limits(data, fallback_free=True)
    except DripFilesError:
        raise
    except Exception as exc:
        log.warning("fallback límites free: %s", exc)
        return AccountLimits(
            tier="free",
            max_size_bytes=FREE_MAX_SIZE,
            max_files=FREE_MAX_FILES,
            expire_seconds=FREE_EXPIRE_SECONDS,
            chunk_size=DEFAULT_CHUNK,
            raw={},
        )


def _is_auth_failure(status: int, data: dict | None) -> bool:
    if status in (401, 403):
        return True
    if not isinstance(data, dict):
        return False
    err = str(data.get("error") or "").lower()
    msg = str(data.get("message") or "").lower()
    if err in ("unauthorized", "forbidden", "invalid_api_key", "auth"):
        return True
    if "api key" in msg and any(
        w in msg for w in ("invalid", "missing", "unauthorized", "forbidden", "revoked")
    ):
        return True
    return False


async def get_account(
    session: aiohttp.ClientSession, api_key: str
) -> AccountLimits:
    """Valida la API key y devuelve límites del plan (GET /api/v1/me)."""
    headers = _auth_headers(api_key)
    async with session.get(f"{AUTH_BASE}/me", headers=headers) as resp:
        data = await _read_json(resp)
        if _is_auth_failure(resp.status, data):
            raise DripFilesAuthError(
                "API key inválida o sin permiso. Crea una en https://dripfiles.com"
            )
        if resp.status >= 400 or data.get("ok") is False:
            raise DripFilesError(
                _api_message(data, f"no se pudo leer la cuenta (HTTP {resp.status})")
            )
        return _parse_limits(data, fallback_free=False)


async def resolve_limits(
    session: aiohttp.ClientSession, api_key: str | None
) -> AccountLimits:
    if api_key:
        return await get_account(session, api_key)
    return await get_free_limits(session)


async def create_upload(
    session: aiohttp.ClientSession,
    *,
    api_key: str | None = None,
    message: str | None = None,
    expire_seconds: int | None = None,
) -> dict:
    """Crea un envío. Con API key se puede pedir caducidad (`expire` en segundos)."""
    body: dict = {}
    if message and message.strip():
        body["message"] = message.strip()
    if api_key and expire_seconds and expire_seconds > 0:
        body["expire"] = int(expire_seconds)

    headers = _auth_headers(api_key)
    url = f"{_base(api_key)}/uploads"
    async with session.post(url, json=body, headers=headers or None) as resp:
        data = await _read_json(resp)
        if _is_auth_failure(resp.status, data):
            raise DripFilesAuthError(
                _api_message(data, "API key inválida o sin permiso")
            )
        if resp.status >= 400 or not data.get("ok"):
            raise DripFilesError(
                _api_message(data, f"no se pudo crear el envío (HTTP {resp.status})")
            )
        if not data.get("upload_id") or not data.get("upload_token"):
            raise DripFilesError("la API no devolvió upload_id/upload_token")
        return data


async def _upload_chunk(
    session: aiohttp.ClientSession,
    *,
    api_key: str | None,
    upload_id: str,
    upload_token: str,
    file_uid: str,
    filename: str,
    chunk: bytes,
    start: int,
    total: int,
) -> dict:
    end = start + len(chunk) - 1
    form = aiohttp.FormData()
    form.add_field("upload_id", upload_id)
    form.add_field("file_uid", file_uid)
    form.add_field("original_path", filename)
    form.add_field(
        "files[]",
        chunk,
        filename=filename,
        content_type="application/octet-stream",
    )
    headers = {
        **_auth_headers(api_key),
        "X-Upload-Token": upload_token,
        "X-File-Uid": file_uid,
        "X-File-Name": quote(filename),
        "Content-Range": f"bytes {start}-{end}/{total}",
    }
    url = f"{_base(api_key)}/uploads/{upload_id}/files"
    async with session.post(url, data=form, headers=headers) as resp:
        data = await _read_json(resp)
        if _is_auth_failure(resp.status, data):
            raise DripFilesAuthError(
                _api_message(data, "API key inválida durante la subida")
            )
        if resp.status >= 400 or not data.get("ok"):
            raise DripFilesError(
                _api_message(
                    data, f"error subiendo trozo {start}-{end} (HTTP {resp.status})"
                )
            )
        return data


async def complete_upload(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str,
    *,
    api_key: str | None = None,
    message: str | None = None,
) -> dict:
    headers = {
        **_auth_headers(api_key),
        "X-Upload-Token": upload_token,
    }
    body: dict = {}
    if message and message.strip():
        body["message"] = message.strip()
    async with session.post(
        f"{_base(api_key)}/uploads/{upload_id}/complete",
        json=body,
        headers=headers,
    ) as resp:
        data = await _read_json(resp)
        if _is_auth_failure(resp.status, data):
            raise DripFilesAuthError(
                _api_message(data, "API key inválida al completar el envío")
            )
        if resp.status >= 400 or not data.get("ok"):
            raise DripFilesError(
                _api_message(data, f"error al completar (HTTP {resp.status})")
            )
        return data


async def get_status(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str | None = None,
    *,
    api_key: str | None = None,
) -> dict:
    headers = {**_auth_headers(api_key)}
    if upload_token:
        headers["X-Upload-Token"] = upload_token
    async with session.get(
        f"{_base(api_key)}/uploads/{upload_id}",
        headers=headers or None,
    ) as resp:
        data = await _read_json(resp)
        if resp.status >= 400 or not data.get("ok"):
            raise DripFilesError(
                _api_message(data, f"error consultando estado (HTTP {resp.status})")
            )
        return data


async def wait_ready(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str,
    *,
    api_key: str | None = None,
    attempts: int = READY_POLL_ATTEMPTS,
    delay: float = READY_POLL_DELAY,
) -> dict:
    last: dict | None = None
    for _ in range(attempts):
        last = await get_status(
            session, upload_id, upload_token, api_key=api_key
        )
        status = (last.get("status") or "").lower()
        if status == "ready":
            return last
        if status in ("error", "failed", "expired"):
            raise DripFilesError(
                _api_message(last, f"el envío quedó en estado {status}")
            )
        await asyncio.sleep(delay)
    raise DripFilesError(
        _api_message(last, "timeout esperando a que DripFiles finalice el envío")
    )


async def upload_path(
    session: aiohttp.ClientSession,
    path: str,
    filename: str | None = None,
    *,
    api_key: str | None = None,
    message: str | None = None,
    expire_seconds: int | None = None,
    max_size: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int | None = None,
) -> dict:
    """Sube un archivo local y devuelve el dict de estado listo (incluye `url`)."""
    if not os.path.isfile(path):
        raise DripFilesError(f"no existe el archivo: {path}")
    total = os.path.getsize(path)
    if total <= 0:
        raise DripFilesError("el archivo está vacío")

    limit = max_size or (FREE_MAX_SIZE if not api_key else TELEGRAM_MAX_SIZE)
    if total > limit:
        raise DripFilesError(
            f"supera el límite de DripFiles ({_human(limit)}; archivo {_human(total)})"
        )

    name = filename or os.path.basename(path) or f"file_{uuid.uuid4().hex[:8]}"
    msg = message.strip() if message and message.strip() else None
    meta = await create_upload(
        session,
        api_key=api_key,
        message=msg,
        expire_seconds=expire_seconds,
    )
    upload_id = meta["upload_id"]
    token = meta["upload_token"]
    chunk = int(chunk_size or meta.get("chunk_size") or DEFAULT_CHUNK)
    if chunk < 64 * 1024:
        chunk = DEFAULT_CHUNK
    file_uid = str(uuid.uuid4())

    log.info(
        "DripFiles%s: subiendo %s (%s bytes) → %s",
        " (auth)" if api_key else " (free)",
        name,
        total,
        upload_id,
    )

    sent = 0
    with open(path, "rb") as fh:
        while sent < total:
            data = fh.read(chunk)
            if not data:
                break
            await _upload_chunk(
                session,
                api_key=api_key,
                upload_id=upload_id,
                upload_token=token,
                file_uid=file_uid,
                filename=name,
                chunk=data,
                start=sent,
                total=total,
            )
            sent += len(data)
            if on_progress:
                try:
                    on_progress(sent, total)
                except Exception:
                    log.debug("progress dripfiles falló", exc_info=True)

    await complete_upload(
        session, upload_id, token, api_key=api_key, message=msg
    )
    status = await wait_ready(session, upload_id, token, api_key=api_key)
    url = status.get("url") or f"https://dripfiles.com/{upload_id}"
    status["url"] = url
    # propagar caducidad si la API la da en create o status
    if "expires_at" not in status and meta.get("expires_at"):
        status["expires_at"] = meta["expires_at"]
    if "expire" not in status and meta.get("expire"):
        status["expire"] = meta["expire"]
    log.info("DripFiles listo: %s", url)
    return status


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TB"


def format_expire_note(seconds: int | None, expires_at: int | float | None = None) -> str:
    if seconds and seconds > 0:
        days = seconds / 86400
        if days >= 1:
            if abs(days - round(days)) < 0.05:
                return f"⏱ Caduca en **{int(round(days))}** día(s)."
            return f"⏱ Caduca en **{days:.1f}** días."
        hours = seconds / 3600
        return f"⏱ Caduca en **{hours:.0f}** h."
    if isinstance(expires_at, (int, float)) and expires_at > 0:
        return "⏱ Caduca según el plan de DripFiles."
    return "⏱ Caduca según el plan de DripFiles."


def _sh_single(s: str) -> str:
    """Comillas simples estilo shell (seguro para copiar/pegar)."""
    return "'" + (s or "").replace("'", "'\\''") + "'"


def download_command(tool: str, url: str, filename: str) -> str:
    """Comando listo para copiar: wget o curl (sin ambigüedad -O vs -0)."""
    f = _sh_single(filename or "file")
    u = _sh_single(url or "")
    tool = (tool or "wget").lower().strip()
    if tool == "curl":
        # -L sigue redirects; -o escribe al nombre dado
        return f"curl -L -o {f} {u}"
    # forma larga: en algunas fuentes -O se confunde con -0
    return f"wget --output-document={f} {u}"


def wget_command(url: str, filename: str) -> str:
    """Compat: siempre wget."""
    return download_command("wget", url, filename)
