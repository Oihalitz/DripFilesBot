"""Cliente de la API de DripFiles.

Free (sin key):  https://dripfiles.com/api/v1/free
  · ~2 GB, enlaces ~2 días, rate limit por IP
  · create devuelve upload_id + upload_token (header X-Upload-Token)

Autenticada (API key del bot o del usuario):  https://dripfiles.com/api/v1
  · límites del plan de la cuenta (tamaño, caducidad, …)
  · Authorization: Bearer <api_key>
  · create devuelve upload_id (sin upload_token; basta el Bearer)
  · body de create acepta `expire` (segundos) y `message`

Flujo:
  1. POST …/uploads              → upload_id [+ upload_token en free]
  2. POST …/uploads/{id}/files   → trozos multipart (files[]) + Content-Range
  3. POST …/uploads/{id}/complete
  4. GET  …/uploads/{id}         → poll hasta status=ready → url
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from email.message import Message as EmailMessage
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import quote, urljoin, urlparse

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
READY_POLL_TIMEOUT = 600.0
READY_POLL_DELAY = 0.75
READY_POLL_DELAY_MAX = 5.0
HTTP_RETRIES = 5
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
PUBLIC_PAGE_MAX_BYTES = 5 * 1024 * 1024
_PUBLIC_SLUG_RE = re.compile(r"^/[A-Za-z0-9_-]{4,64}/?$")

# alias histórico
MAX_SIZE = FREE_MAX_SIZE


class DripFilesError(Exception):
    """Error al crear, subir o finalizar un envío en DripFiles."""


class DripFilesAuthError(DripFilesError):
    """API key inválida, revocada o sin permiso (401/403)."""


@dataclass(frozen=True)
class PublicFile:
    """Archivo descargable anunciado por un enlace público de DripFiles."""

    name: str
    size: int
    url: str


class _PublicFilesParser(HTMLParser):
    """Extrae archivos de la página pública sin depender del tipo de preview."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.files: list[dict[str, object]] = []
        self._current: dict[str, object] | None = None
        self._file_depth = 0
        self._capture_name = False

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(k): str(v or "") for k, v in attrs}
        classes = set(values.get("class", "").split())

        if tag == "div":
            if self._current is None and "file" in classes:
                self._current = {}
                self._file_depth = 1
            elif self._current is not None:
                self._file_depth += 1

        if self._current is None:
            return

        # Todos los previews actuales usan data-<tipo>-download/name/size.
        for key, value in values.items():
            if key.startswith("data-") and key.endswith("-download") and value:
                prefix = key[: -len("-download")]
                self._current["url"] = value
                name = values.get(prefix + "-name")
                size = values.get(prefix + "-size")
                if name:
                    self._current["name"] = name
                if size and size.isdigit():
                    self._current["size"] = int(size)

        if tag == "a" and "download" in classes and values.get("href"):
            self._current["url"] = values["href"]
        if tag == "span" and "name" in classes:
            self._capture_name = True

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture_name:
            # Los previews modernos ya traen data-<tipo>-name; el <span>
            # visible es solo el fallback para plantillas antiguas.
            if self._current.get("name"):
                return
            name = data.strip()
            if name:
                self._current["name"] = name

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._capture_name = False
        if tag != "div" or self._current is None:
            return
        self._file_depth -= 1
        if self._file_depth <= 0:
            if self._current.get("url"):
                self.files.append(self._current)
            self._current = None
            self._file_depth = 0


def normalize_public_url(url: str) -> str:
    """Valida y canoniza un enlace público (evita convertirlo en un SSRF)."""
    raw = (url or "").strip().rstrip(".,;:!?)]}")
    if raw.lower().startswith(("www.", "dripfiles.com/")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise DripFilesError("el enlace de DripFiles no es válido")
    if (parsed.hostname or "").lower() not in ("dripfiles.com", "www.dripfiles.com"):
        raise DripFilesError("el enlace no pertenece a DripFiles")
    try:
        port = parsed.port
    except ValueError as exc:
        raise DripFilesError("el enlace público de DripFiles no es válido") from exc
    if port not in (None, 80, 443) or not _PUBLIC_SLUG_RE.fullmatch(parsed.path):
        raise DripFilesError("el enlace público de DripFiles no es válido")
    return f"https://dripfiles.com/{parsed.path.strip('/')}"


def _content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    msg = EmailMessage()
    msg["Content-Disposition"] = value
    name = msg.get_filename()
    return str(name).strip() if name else None


def _public_download_url(source_url: str, candidate: str) -> str | None:
    url = urljoin(source_url, candidate)
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in (
        "dripfiles.com",
        "www.dripfiles.com",
    ):
        return None
    if parsed.path != "/handler/file":
        return None
    return url


async def inspect_public_link(
    session: aiohttp.ClientSession, url: str
) -> tuple[str, list[PublicFile]]:
    """Devuelve la URL canónica y los archivos visibles en un enlace público."""
    source_url = normalize_public_url(url)
    headers = {
        "Accept": "text/html,application/octet-stream;q=0.9,*/*;q=0.8",
        "User-Agent": "DripFilesBot/1.0 (+https://t.me/DripFilesBot)",
    }
    try:
        async with session.get(source_url, headers=headers) as resp:
            if resp.status in (404, 410):
                raise DripFilesError("el enlace no existe o ha caducado")
            if resp.status >= 400:
                raise DripFilesError(f"no se pudo abrir el enlace (HTTP {resp.status})")

            content_type = (resp.headers.get("Content-Type") or "").lower()
            disposition = resp.headers.get("Content-Disposition")
            if disposition or "text/html" not in content_type:
                name = _content_disposition_filename(disposition) or "dripfiles_file"
                size = coerce_positive_int(resp.headers.get("Content-Length")) or 0
                return source_url, [PublicFile(name=name, size=size, url=source_url)]

            declared = coerce_positive_int(resp.headers.get("Content-Length")) or 0
            if declared > PUBLIC_PAGE_MAX_BYTES:
                raise DripFilesError("la página del enlace es demasiado grande")
            body = await resp.content.read(PUBLIC_PAGE_MAX_BYTES + 1)
            if len(body) > PUBLIC_PAGE_MAX_BYTES:
                raise DripFilesError("la página del enlace es demasiado grande")
            html = body.decode(resp.charset or "utf-8", errors="replace")
    except DripFilesError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise DripFilesError(f"error de red abriendo el enlace: {exc}") from exc

    parser = _PublicFilesParser()
    parser.feed(html)
    files: list[PublicFile] = []
    seen: set[str] = set()
    for item in parser.files:
        download_url = _public_download_url(source_url, str(item.get("url") or ""))
        if not download_url or download_url in seen:
            continue
        seen.add(download_url)
        raw_size = item.get("size")
        size = int(raw_size) if isinstance(raw_size, int) and raw_size > 0 else 0
        files.append(
            PublicFile(
                name=str(item.get("name") or f"file_{len(files) + 1}"),
                size=size,
                url=download_url,
            )
        )
    if not files:
        raise DripFilesError(
            "el enlace no contiene archivos descargables o requiere contraseña"
        )
    return source_url, files


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


def coerce_positive_int(value: object) -> int | None:
    """Acepta int/float/str numérico; None si no es un entero > 0."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if n > 0 else None
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            n = int(s)
            return n if n > 0 else None
    return None


def _retry_delay(resp: aiohttp.ClientResponse | None, attempt: int) -> float:
    if resp is not None:
        raw = resp.headers.get("Retry-After")
        if raw:
            try:
                return min(max(float(raw.strip()), 0.2), 60.0)
            except ValueError:
                pass
    return min(0.75 * (2**attempt), 20.0)


async def _transient_sleep(
    resp: aiohttp.ClientResponse | None, attempt: int
) -> None:
    delay = _retry_delay(resp, attempt)
    log.info("DripFiles retry in %.1fs (attempt %s)", delay, attempt + 1)
    await asyncio.sleep(delay)


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    retries: int = HTTP_RETRIES,
    **kwargs,
) -> tuple[int, dict]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status in RETRY_STATUSES and attempt + 1 < retries:
                    await _transient_sleep(resp, attempt)
                    continue
                data = await _read_json(resp)
                return resp.status, data
        except DripFilesError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= retries:
                raise DripFilesError(f"error de red: {exc}") from exc
            await _transient_sleep(None, attempt)
    raise DripFilesError("error de red agotando reintentos") from last_exc


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
            # a veces vienen como string numérico
            if isinstance(v, str) and v.strip().isdigit():
                n = int(v.strip())
                if n > 0:
                    return n
        return default

    max_size = _int(
        "max_file_bytes",
        "max_size_bytes",
        "max_bytes",
        "upload_max_size",
        default=FREE_MAX_SIZE if fallback_free else TELEGRAM_MAX_SIZE,
    )
    # a veces solo viene en MB / GB
    if max_size == (FREE_MAX_SIZE if fallback_free else TELEGRAM_MAX_SIZE):
        mb = limits.get("max_size_mb") or data.get("max_size_mb")
        if isinstance(mb, (int, float)) and mb > 0:
            max_size = int(mb * 1024**2)
        else:
            gb = limits.get("max_size_gb") or data.get("max_size_gb")
            if isinstance(gb, (int, float)) and gb > 0:
                max_size = int(gb * 1024**3)

    expire = _int(
        "expire_seconds",
        "expire",
        "default_expire",
        "link_expire_seconds",
        default=0,
    )
    if expire <= 0:
        # planes auth: lista de opciones en segundos (p. ej. ["432000","604800"])
        opts = limits.get("expire_options") or data.get("expire_options")
        if isinstance(opts, (list, tuple)) and opts:
            vals: list[int] = []
            for o in opts:
                try:
                    n = int(o)
                    if n > 0:
                        vals.append(n)
                except (TypeError, ValueError):
                    continue
            if vals:
                expire = min(vals)
    if expire <= 0:
        days = limits.get("expire_days") or data.get("expire_days")
        if isinstance(days, (int, float)) and days > 0:
            expire = int(days * 86400)
    if expire <= 0:
        expire = FREE_EXPIRE_SECONDS

    max_files = _int("max_files", "files_max", default=FREE_MAX_FILES)
    chunk = _int(
        "recommended_chunk_bytes",
        "chunk_size",
        default=DEFAULT_CHUNK,
    )
    tier = str(
        data.get("tier")
        or data.get("plan")
        or data.get("plan_name")
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
    status, data = await _request_json(
        session, "GET", f"{AUTH_BASE}/me", headers=headers
    )
    if _is_auth_failure(status, data):
        raise DripFilesAuthError(
            "API key inválida o sin permiso. Crea una en https://dripfiles.com"
        )
    if status >= 400 or data.get("ok") is False:
        raise DripFilesError(
            _api_message(data, f"no se pudo leer la cuenta (HTTP {status})")
        )
    return _parse_limits(data, fallback_free=False)


async def resolve_limits(
    session: aiohttp.ClientSession, api_key: str | None
) -> AccountLimits:
    if api_key:
        return await get_account(session, api_key)
    return await get_free_limits(session)


def _normalize_upload_meta(data: dict, *, api_key: str | None) -> dict:
    """Normaliza create-upload: exige upload_id; upload_token solo en free."""
    upload_id = data.get("upload_id") or data.get("id")
    token = data.get("upload_token") or data.get("token")
    if not upload_id:
        raise DripFilesError("la API no devolvió upload_id")
    # Free: el token es obligatorio. Auth: basta Authorization Bearer.
    if not api_key and not token:
        raise DripFilesError("la API free no devolvió upload_token")
    out = dict(data)
    out["upload_id"] = str(upload_id)
    out["upload_token"] = str(token) if token else None
    return out


def _request_headers(
    api_key: str | None,
    upload_token: str | None = None,
    **extra: str,
) -> dict[str, str]:
    headers = {**_auth_headers(api_key), **extra}
    if upload_token:
        headers["X-Upload-Token"] = upload_token
    return headers


async def create_upload(
    session: aiohttp.ClientSession,
    *,
    api_key: str | None = None,
    message: str | None = None,
    expire_seconds: int | None = None,
    files: list[dict[str, object]] | None = None,
) -> dict:
    """Crea un envío. Con API key se puede pedir caducidad (`expire` en segundos)."""
    body: dict = {}
    if message and message.strip():
        body["message"] = message.strip()
    if api_key and expire_seconds and expire_seconds > 0:
        body["expire"] = int(expire_seconds)
    if files:
        body["files"] = files

    headers = _auth_headers(api_key)
    url = f"{_base(api_key)}/uploads"
    status, data = await _request_json(
        session, "POST", url, json=body, headers=headers or None
    )
    if _is_auth_failure(status, data):
        raise DripFilesAuthError(
            _api_message(data, "API key inválida o sin permiso")
        )
    if status >= 400 or data.get("ok") is False:
        raise DripFilesError(
            _api_message(data, f"no se pudo crear el envío (HTTP {status})")
        )
    return _normalize_upload_meta(data, api_key=api_key)


async def _upload_chunk(
    session: aiohttp.ClientSession,
    *,
    api_key: str | None,
    upload_id: str,
    upload_token: str | None,
    file_uid: str,
    filename: str,
    chunk: bytes,
    start: int,
    total: int,
) -> dict:
    end = start + len(chunk) - 1
    url = f"{_base(api_key)}/uploads/{upload_id}/files"
    extra = {
        "X-File-Uid": file_uid,
        "X-File-Name": quote(filename),
        "Content-Range": f"bytes {start}-{end}/{total}",
    }
    last_exc: Exception | None = None
    for attempt in range(HTTP_RETRIES):
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
        headers = _request_headers(api_key, upload_token, **extra)
        try:
            async with session.post(url, data=form, headers=headers) as resp:
                if resp.status in RETRY_STATUSES and attempt + 1 < HTTP_RETRIES:
                    await _transient_sleep(resp, attempt)
                    continue
                data = await _read_json(resp)
                if _is_auth_failure(resp.status, data):
                    raise DripFilesAuthError(
                        _api_message(data, "API key inválida durante la subida")
                    )
                if resp.status >= 400 or data.get("ok") is False:
                    raise DripFilesError(
                        _api_message(
                            data,
                            f"error subiendo trozo {start}-{end} (HTTP {resp.status})",
                        )
                    )
                return data
        except DripFilesError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= HTTP_RETRIES:
                raise DripFilesError(
                    f"error de red subiendo trozo {start}-{end}: {exc}"
                ) from exc
            await _transient_sleep(None, attempt)
    raise DripFilesError(
        f"error de red subiendo trozo {start}-{end}"
    ) from last_exc


async def complete_upload(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str | None,
    *,
    api_key: str | None = None,
    message: str | None = None,
) -> dict:
    headers = _request_headers(api_key, upload_token)
    body: dict = {}
    if message and message.strip():
        body["message"] = message.strip()
    status, data = await _request_json(
        session,
        "POST",
        f"{_base(api_key)}/uploads/{upload_id}/complete",
        json=body,
        headers=headers or None,
    )
    if _is_auth_failure(status, data):
        raise DripFilesAuthError(
            _api_message(data, "API key inválida al completar el envío")
        )
    if status >= 400 or data.get("ok") is False:
        raise DripFilesError(
            _api_message(data, f"error al completar (HTTP {status})")
        )
    return data


async def get_status(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str | None = None,
    *,
    api_key: str | None = None,
) -> dict:
    headers = _request_headers(api_key, upload_token)
    status, data = await _request_json(
        session,
        "GET",
        f"{_base(api_key)}/uploads/{upload_id}",
        headers=headers or None,
    )
    if status >= 400 or data.get("ok") is False:
        raise DripFilesError(
            _api_message(data, f"error consultando estado (HTTP {status})")
        )
    return data


async def wait_ready(
    session: aiohttp.ClientSession,
    upload_id: str,
    upload_token: str | None,
    *,
    api_key: str | None = None,
    timeout: float = READY_POLL_TIMEOUT,
    delay: float = READY_POLL_DELAY,
) -> dict:
    last: dict | None = None
    deadline = time.monotonic() + timeout
    current = delay
    while time.monotonic() < deadline:
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
        await asyncio.sleep(current)
        current = min(current * 1.4, READY_POLL_DELAY_MAX)
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
    name = filename or os.path.basename(path) or f"file_{uuid.uuid4().hex[:8]}"
    return await upload_paths(
        session,
        [(path, name)],
        api_key=api_key,
        message=message,
        expire_seconds=expire_seconds,
        max_size=max_size,
        max_files=1,
        on_progress=on_progress,
        chunk_size=chunk_size,
    )


async def upload_paths(
    session: aiohttp.ClientSession,
    paths: list[tuple[str, str]],
    *,
    api_key: str | None = None,
    message: str | None = None,
    expire_seconds: int | None = None,
    max_size: int | None = None,
    max_files: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int | None = None,
) -> dict:
    """Sube varios archivos independientes dentro de un único enlace."""
    if not paths:
        raise DripFilesError("no hay archivos para subir")
    if max_files and len(paths) > max_files:
        raise DripFilesError(
            f"supera el límite de archivos ({len(paths)}/{max_files})"
        )

    prepared: list[tuple[str, str, int]] = []
    total = 0
    for path, filename in paths:
        if not os.path.isfile(path):
            raise DripFilesError(f"no existe el archivo: {path}")
        size = os.path.getsize(path)
        if size <= 0:
            raise DripFilesError(f"el archivo está vacío: {filename}")
        name = filename or os.path.basename(path) or f"file_{uuid.uuid4().hex[:8]}"
        prepared.append((path, name, size))
        total += size

    limit = max_size or (FREE_MAX_SIZE if not api_key else TELEGRAM_MAX_SIZE)
    if total > limit:
        raise DripFilesError(
            f"supera el límite de DripFiles ({_human(limit)}; total {_human(total)})"
        )

    msg = message.strip() if message and message.strip() else None
    meta = await create_upload(
        session,
        api_key=api_key,
        message=msg,
        expire_seconds=expire_seconds,
        files=[{"name": name, "size": size} for _, name, size in prepared],
    )
    upload_id = str(meta["upload_id"])
    token = meta.get("upload_token")  # None en API autenticada
    chunk = int(chunk_size or meta.get("chunk_size") or DEFAULT_CHUNK)
    if chunk < 64 * 1024:
        chunk = DEFAULT_CHUNK
    log.info(
        "DripFiles%s: subiendo %s archivo(s) (%s bytes) → %s",
        " (auth)" if api_key else " (free)",
        len(prepared),
        total,
        upload_id,
    )

    uploaded_total = 0
    for path, name, file_total in prepared:
        file_uid = str(uuid.uuid4())
        file_sent = 0
        with open(path, "rb") as fh:
            while file_sent < file_total:
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
                    start=file_sent,
                    total=file_total,
                )
                file_sent += len(data)
                if on_progress:
                    try:
                        on_progress(uploaded_total + file_sent, total)
                    except Exception:
                        log.debug("progress dripfiles falló", exc_info=True)
        if file_sent != file_total:
            raise DripFilesError(f"lectura incompleta del archivo: {name}")
        uploaded_total += file_total

    await complete_upload(
        session, upload_id, token, api_key=api_key, message=msg
    )
    status = await wait_ready(session, upload_id, token, api_key=api_key)
    url = status.get("url") or f"https://dripfiles.com/{upload_id}"
    status["url"] = url
    # propagar caducidad si la API la da en create o status
    if "expires_at" not in status and meta.get("expires_at"):
        status["expires_at"] = meta["expires_at"]
    expire = coerce_positive_int(status.get("expire") or meta.get("expire"))
    if expire is not None:
        status["expire"] = expire
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


def shell_safe_filename(filename: str | None) -> str:
    """Nombre apto para shell: sin espacios ni saltos (evita intros al copiar en TG)."""
    name = (filename or "file").replace("\\", "/").split("/")[-1]
    name = name.replace("\n", " ").replace("\r", " ").strip() or "file"
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"_+", "_", name).strip("._") or "file"
    return name[:180]


def download_command(tool: str, url: str, filename: str) -> str:
    """Una sola línea lista para copiar (wget o curl).

    Sin espacios en el nombre → Telegram no parte el string a mitad del
    nombre con un intro al copiar desde el móvil.
    """
    name = shell_safe_filename(filename)
    url = (url or "").strip().replace("\n", "").replace("\r", "")
    tool = (tool or "wget").lower().strip()
    if tool == "curl":
        cmd = f"curl -L -o {name} {url}"
    else:
        cmd = f"wget -O {name} {url}"
    return " ".join(cmd.split())


def wget_command(url: str, filename: str) -> str:
    """Compat: siempre wget."""
    return download_command("wget", url, filename)
