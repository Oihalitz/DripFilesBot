"""DripFilesBot — archivo → enlace DripFiles (key del bot o del usuario).

ZIP · botones · resubir · /apikey · /expire · /dev (wget|curl) · i18n · SQLite
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiohttp
from pyrogram import Client, enums, filters, idle
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    MessageEntity,
)

# kurigram depreca disable_web_page_preview
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _utf16_len(s: str) -> int:
    """Longitud en unidades UTF-16 (offsets de entidades de Telegram)."""
    return len(s.encode("utf-16-le")) // 2

import dripfiles as dripfiles_mod
from config import load_config
from db import Database, MediaRef, PendingJob, UserSettings
from i18n import DEFAULT_LANG, LANG_LABELS, LANGS, normalize_lang, t

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
if LOG_LEVEL != "DEBUG":
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
log = logging.getLogger("bot")

cfg = load_config()

app = Client(
    "dripfiles_bot",
    api_id=cfg.api_id,
    api_hash=cfg.api_hash,
    bot_token=cfg.bot_token,
)

http: aiohttp.ClientSession
database: Database

background_tasks: set[asyncio.Task] = set()
zip_sessions: dict[int, "ZipSession"] = {}

ZIP_SESSION_TIMEOUT = cfg.zip_timeout_minutes * 60
_SAFE_NAME_RE = re.compile(r"[^\w.\- ()\[\]]+", re.UNICODE)


@dataclass
class StagedFile:
    path: str
    filename: str
    size: int
    file_id: str = ""


@dataclass
class ZipSession:
    user_id: int
    work_dir: str
    files: list[StagedFile] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    status_msg: Message | None = None
    busy: bool = False

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def expired(self) -> bool:
        return (time.monotonic() - self.last_activity) > ZIP_SESSION_TIMEOUT


def _auth(_, __, update) -> bool:
    user = update.from_user
    return bool(user) and (not cfg.allowed_users or user.id in cfg.allowed_users)


auth = filters.create(_auth)


def human_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TB"


def progress_bar(pct: float) -> str:
    filled = min(20, int(pct / 5))
    return "█" * filled + "░" * (20 - filled)


def spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task


def safe_filename(name: str | None, fallback: str = "file") -> str:
    base = (name or fallback).strip() or fallback
    base = base.replace("/", "_").replace("\\", "_").replace("\x00", "")
    base = _SAFE_NAME_RE.sub("_", base).strip(" ._") or fallback
    return base[:200]


async def safe_edit(message: Message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except MessageNotModified:
        pass
    except Exception:
        log.debug("safe_edit falló", exc_info=True)


async def lang_of(user_id: int) -> str:
    user = await database.get_user(user_id)
    return normalize_lang(user.lang)


def mask_key(key: str | None, lang: str) -> str:
    if not key:
        return t(lang, "no_api_key")
    k = key.strip()
    if len(k) <= 8:
        return "`" + ("*" * len(k)) + "`"
    return f"`{k[:4]}…{k[-4:]}`"


def user_own_api_key(user: UserSettings) -> str | None:
    """Key propia del usuario solo si el host lo permite."""
    if not cfg.allow_user_api_keys:
        return None
    if not user.api_key:
        return None
    return user.api_key.strip() or None


def effective_api_key(user: UserSettings) -> str | None:
    """Key efectiva: propia (si se permite) → key del bot → free (None)."""
    own = user_own_api_key(user)
    if own:
        return own
    bot_key = cfg.dripfiles_api_key
    return bot_key.strip() if bot_key else None


def display_api_key(user: UserSettings, lang: str) -> str:
    """Texto de la key en /settings y /apikey (sin revelar la del bot en claro)."""
    if user_own_api_key(user):
        return mask_key(user.api_key, lang)
    if cfg.dripfiles_api_key:
        return t(lang, "using_bot_key")
    return t(lang, "no_api_key")


def open_note(lang: str) -> str:
    if cfg.allowed_users:
        return t(lang, "open_whitelist", n=len(cfg.allowed_users))
    return t(lang, "open_public")


def help_text(lang: str) -> str:
    if cfg.allow_user_api_keys:
        api_note = t(lang, "help_api_own_ok")
        apikey_cmd = t(lang, "help_apikey_cmd")
    else:
        api_note = t(lang, "help_api_own_off")
        apikey_cmd = ""
    return t(
        lang,
        "help",
        open_note=open_note(lang),
        api_note=api_note,
        apikey_cmd=apikey_cmd,
    )


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(LANG_LABELS[code], callback_data=f"lang:{code}")
                for code in LANGS
            ]
        ]
    )


def help_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "btn_zip_start"), callback_data="zip:start"
                )
            ],
            [
                InlineKeyboardButton(
                    t(lang, "btn_settings"), callback_data="ui:settings"
                ),
                InlineKeyboardButton(t(lang, "btn_dev"), callback_data="ui:dev"),
            ],
            [
                InlineKeyboardButton(t(lang, "btn_lang"), callback_data="ui:lang"),
            ],
        ]
    )


def zip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "btn_zip_done"), callback_data="zip:done"
                ),
                InlineKeyboardButton(
                    t(lang, "btn_zip_cancel"), callback_data="zip:cancel"
                ),
            ]
        ]
    )


def success_keyboard(lang: str, url: str, token: str | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(lang, "btn_open"), url=url)]]
    if token:
        rows.append(
            [InlineKeyboardButton(t(lang, "btn_reup"), callback_data=f"reup:{token}")]
        )
    return InlineKeyboardMarkup(rows)


def dev_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(lang, "btn_dev_wget"), callback_data="dev:wget"
                ),
                InlineKeyboardButton(
                    t(lang, "btn_dev_curl"), callback_data="dev:curl"
                ),
                InlineKeyboardButton(
                    t(lang, "btn_dev_off"), callback_data="dev:off"
                ),
            ]
        ]
    )


def media_filter(_, __, message: Message) -> bool:
    return bool(
        message.document
        or message.video
        or message.audio
        or message.voice
        or message.video_note
        or message.animation
        or message.photo
        or message.sticker
    )


has_media = filters.create(media_filter)


def media_file_id(message: Message) -> str | None:
    if message.document:
        return message.document.file_id
    if message.video:
        return message.video.file_id
    if message.audio:
        return message.audio.file_id
    if message.voice:
        return message.voice.file_id
    if message.video_note:
        return message.video_note.file_id
    if message.animation:
        return message.animation.file_id
    if message.sticker:
        return message.sticker.file_id
    if message.photo:
        return message.photo.file_id
    return None


def media_meta(message: Message) -> tuple[int | None, str]:
    if message.document:
        d = message.document
        return d.file_size, d.file_name or f"document_{d.file_unique_id}"
    if message.video:
        v = message.video
        return v.file_size, v.file_name or f"video_{v.file_unique_id}.mp4"
    if message.audio:
        a = message.audio
        name = a.file_name
        if not name:
            ext = ".mp3"
            if a.mime_type and "/" in a.mime_type:
                sub = a.mime_type.split("/", 1)[1].split(";")[0].strip()
                if sub and sub != "mpeg":
                    ext = f".{sub}"
            name = f"audio_{a.file_unique_id}{ext}"
        return a.file_size, name
    if message.voice:
        v = message.voice
        return v.file_size, f"voice_{v.file_unique_id}.ogg"
    if message.video_note:
        v = message.video_note
        return v.file_size, f"videonote_{v.file_unique_id}.mp4"
    if message.animation:
        a = message.animation
        return a.file_size, a.file_name or f"animation_{a.file_unique_id}.mp4"
    if message.sticker:
        s = message.sticker
        ext = ".tgs" if s.is_animated else (".webm" if s.is_video else ".webp")
        return s.file_size, f"sticker_{s.file_unique_id}{ext}"
    if message.photo:
        p = message.photo
        return p.file_size, f"photo_{p.file_unique_id}.jpg"
    return None, f"file_{uuid.uuid4().hex[:8]}"


def user_work_dir(user_id: int, kind: str = "single") -> str:
    path = os.path.join(
        cfg.download_dir, f"{kind}_{user_id}_{uuid.uuid4().hex[:10]}"
    )
    os.makedirs(path, exist_ok=True)
    return path


def rmtree_quiet(path: str | None) -> None:
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


async def free_limits_capped() -> dripfiles_mod.AccountLimits:
    limits = await dripfiles_mod.get_free_limits(http)
    return dripfiles_mod.AccountLimits(
        tier="free",
        max_size_bytes=min(limits.max_size_bytes, dripfiles_mod.FREE_MAX_SIZE),
        max_files=limits.max_files,
        expire_seconds=limits.expire_seconds,
        chunk_size=limits.chunk_size,
        raw=limits.raw,
    )


async def user_limits(
    user: UserSettings,
) -> tuple[dripfiles_mod.AccountLimits, int | None, str | None]:
    """Devuelve (límites, expire_seconds, aviso_failover).

    Key efectiva = del usuario o del bot. Si falla → free + aviso.
    """
    api_key = effective_api_key(user)
    if not api_key:
        limits = await free_limits_capped()
        return limits, None, None

    try:
        limits = await dripfiles_mod.get_account(http, api_key)
    except dripfiles_mod.DripFilesAuthError:
        free = await free_limits_capped()
        return free, None, "auth"
    except dripfiles_mod.DripFilesError:
        # red / 5xx al consultar /me: no tumbar la subida si free sirve
        free = await free_limits_capped()
        return free, None, "me_error"

    effective_max = min(limits.max_size_bytes, dripfiles_mod.TELEGRAM_MAX_SIZE)
    if user.expire_days and user.expire_days > 0:
        expire = int(user.expire_days * 86400)
    else:
        expire = limits.expire_seconds
    return (
        dripfiles_mod.AccountLimits(
            tier=limits.tier,
            max_size_bytes=effective_max,
            max_files=limits.max_files,
            expire_seconds=limits.expire_seconds,
            chunk_size=limits.chunk_size,
            raw=limits.raw,
        ),
        expire,
        None,
    )


async def settings_text(user_id: int) -> str:
    user = await database.get_user(user_id)
    lang = normalize_lang(user.lang)
    try:
        limits, expire, failover = await user_limits(user)
        want = ""
        if effective_api_key(user) and expire and not failover:
            want = t(lang, "want_expire", days=expire / 86400)
        lim_line = t(
            lang,
            "limits_block",
            tier=limits.tier,
            max_size=human_size(limits.max_size_bytes),
            expire_days=limits.expire_days,
            want_expire=want,
        )
        if failover == "auth":
            lim_line += t(lang, "failover_auth_note")
        elif failover == "me_error":
            lim_line += t(lang, "failover_me_note")
    except dripfiles_mod.DripFilesError as exc:
        lim_line = t(lang, "limits_error", err=exc)

    if user.expire_days:
        expire_s = t(lang, "expire_days", n=user.expire_days)
    else:
        expire_s = t(lang, "expire_default")

    if user.dev_mode:
        dev_s = t(lang, "dev_state_tool", tool=user.dev_tool)
    else:
        dev_s = t(lang, "dev_state_off")

    return t(
        lang,
        "settings",
        lang_label=LANG_LABELS.get(lang, lang),
        api_key=display_api_key(user, lang),
        expire=expire_s,
        dev=dev_s,
        limits=lim_line,
    )


# ── Download / upload ──────────────────────────────────────────────────────


async def download_to_path(
    *,
    message: Message | None = None,
    file_id: str | None = None,
    dest: str,
    filename: str,
    size_hint: int | None,
    max_size: int,
    progress: Message | None,
    lang: str,
) -> StagedFile:
    if size_hint and size_hint > max_size:
        raise dripfiles_mod.DripFilesError(
            t(
                lang,
                "err_file_too_big",
                size=human_size(size_hint),
                limit=human_size(max_size),
            )
        )

    last_edit = [0.0]

    async def on_progress(current: int, total: int) -> None:
        if not progress:
            return
        now = time.monotonic()
        if now - last_edit[0] < 2.5 and current < total:
            return
        last_edit[0] = now
        total = total or size_hint or 0
        head = t(lang, "downloading", filename=filename)
        if total:
            pct = min(99.0, current * 100 / total)
            text = (
                f"{head}\n"
                f"`[{progress_bar(pct)}]` {pct:.1f}% "
                f"({human_size(current)}/{human_size(total)})"
            )
        else:
            text = f"{head}\n{human_size(current)}"
        await safe_edit(progress, text)

    if message is not None:
        path = await message.download(file_name=dest, progress=on_progress)
        fid = media_file_id(message) or ""
    elif file_id:
        path = await app.download_media(
            file_id, file_name=dest, progress=on_progress
        )
        fid = file_id
    else:
        raise RuntimeError("message or file_id required")

    if not path or not os.path.isfile(path):
        raise RuntimeError("Telegram did not return the file")

    real_size = os.path.getsize(path)
    if real_size <= 0:
        os.remove(path)
        raise dripfiles_mod.DripFilesError(t(lang, "err_empty"))
    if real_size > max_size:
        os.remove(path)
        raise dripfiles_mod.DripFilesError(
            t(
                lang,
                "err_file_too_big",
                size=human_size(real_size),
                limit=human_size(max_size),
            )
        )
    return StagedFile(path=path, filename=filename, size=real_size, file_id=fid)


async def download_telegram_media(
    message: Message,
    dest_dir: str,
    *,
    max_size: int,
    lang: str,
    progress: Message | None = None,
) -> StagedFile:
    size_hint, raw_name = media_meta(message)
    filename = safe_filename(raw_name)
    dest = os.path.join(dest_dir, filename)
    if os.path.exists(dest):
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        filename = f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"
        dest = os.path.join(dest_dir, filename)

    return await download_to_path(
        message=message,
        dest=dest,
        filename=filename,
        size_hint=size_hint,
        max_size=max_size,
        progress=progress,
        lang=lang,
    )


async def upload_to_dripfiles(
    path: str,
    filename: str,
    size: int,
    progress: Message,
    *,
    user: UserSettings,
    limits: dripfiles_mod.AccountLimits,
    expire_seconds: int | None,
    lang: str,
    count: int = 1,
    prefer_free: bool = False,
) -> dict:
    """Sube a DripFiles.

    · Key del usuario o del bot → API autenticada.
    · Si la key falla (401/403) y el archivo ≤ free → reintenta free (failover).
    · `prefer_free=True` si /me ya falló por auth (no reintentar la key rota).
    """
    last_edit = [0.0]
    api_key = effective_api_key(user)

    def on_progress(uploaded: int, total: int) -> None:
        now = time.monotonic()
        if now - last_edit[0] < 3 and uploaded < total:
            return
        last_edit[0] = now
        head = t(lang, "uploading", filename=filename)
        if total:
            pct = min(99.0, uploaded * 100 / total)
            text = (
                f"{head}\n"
                f"`[{progress_bar(pct)}]` {pct:.1f}% "
                f"({human_size(uploaded)}/{human_size(total)})"
            )
        else:
            text = f"{head}\n{human_size(uploaded)}"
        spawn(safe_edit(progress, text))

    await safe_edit(progress, t(lang, "uploading_prep", filename=filename))
    msg = drip_message_for(filename, size, count=count)

    async def _do(
        *,
        api_key: str | None,
        expire: int | None,
        max_size: int,
        chunk: int,
    ) -> dict:
        result = await dripfiles_mod.upload_path(
            http,
            path,
            filename,
            api_key=api_key,
            message=msg,
            expire_seconds=expire,
            max_size=max_size,
            on_progress=on_progress,
            chunk_size=chunk,
        )
        if not result.get("url"):
            raise dripfiles_mod.DripFilesError("DripFiles returned no URL")
        return result

    async def _upload_free(*, reason: str | None) -> dict:
        free = await free_limits_capped()
        if size > free.max_size_bytes:
            raise dripfiles_mod.DripFilesError(
                t(
                    lang,
                    "failover_too_big",
                    limit=human_size(free.max_size_bytes),
                )
            )
        if reason:
            await safe_edit(
                progress, t(lang, "failover_retry_free", filename=filename)
            )
        result = await _do(
            api_key=None,
            expire=None,
            max_size=free.max_size_bytes,
            chunk=free.chunk_size,
        )
        result["_used_key"] = False
        result["_failover"] = bool(reason)
        result["_failover_reason"] = reason
        return result

    # Ya sabemos que la key no vale → free directo
    if prefer_free or not api_key:
        return await _upload_free(reason="auth" if prefer_free else None)

    # Intento autenticado (key del usuario o del bot)
    try:
        result = await _do(
            api_key=api_key,
            expire=expire_seconds,
            max_size=limits.max_size_bytes,
            chunk=limits.chunk_size,
        )
        result["_used_key"] = True
        result["_failover"] = False
        return result
    except dripfiles_mod.DripFilesAuthError:
        return await _upload_free(reason="auth")


def drip_message_for(filename: str, size: int, count: int = 1) -> str:
    template = cfg.dripfiles_message or "{filename}"
    try:
        return template.format(
            filename=filename or "file",
            size=human_size(size),
            count=count,
        ).strip()
    except (KeyError, ValueError):
        return filename or "file"


async def show_success(
    progress: Message,
    *,
    url: str,
    filename: str,
    size: int,
    count: int,
    token: str | None,
    user: UserSettings,
    expire_seconds: int | None = None,
    expires_at: int | float | None = None,
    tier: str = "free",
    failover: bool = False,
) -> None:
    lang = normalize_lang(user.lang)
    eff_expire = expire_seconds
    if not eff_expire and isinstance(expires_at, (int, float)):
        remaining = int(expires_at - time.time())
        if remaining > 0:
            eff_expire = remaining

    count_line = (
        t(lang, "count_line", count=count) if count > 1 else ""
    )
    if eff_expire and eff_expire > 0:
        days = eff_expire / 86400
        if days >= 1:
            expire_note = f"⏱ {t(lang, 'expire_days', n=int(round(days)))}."
        else:
            expire_note = f"⏱ **{eff_expire // 3600}** h."
    else:
        # free ~2 días
        expire_note = f"⏱ {t(lang, 'expire_days', n=2)}."

    tier_note = t(lang, "tier_note", tier=tier) if tier else ""
    failover_note = f"\n{t(lang, 'failover_success_note')}" if failover else ""
    text = t(
        lang,
        "success",
        filename=filename,
        count_line=count_line,
        url=url,
        expire_note=expire_note,
        tier_note=tier_note,
    ) + failover_note
    await safe_edit(
        progress,
        text,
        link_preview_options=_NO_PREVIEW,
        reply_markup=success_keyboard(lang, url, token),
    )
    if user.dev_mode:
        tool = user.dev_tool if user.dev_tool in ("wget", "curl") else "wget"
        cmd = dripfiles_mod.download_command(tool, url, filename)
        # Entidad PRE (no markdown ```): evita línea vacía + etiqueta "shell"
        # que mete el cliente al parsear fences.
        header = t(lang, "dev_header", tool=tool)
        # texto plano: quitar markdown residual del header
        header_plain = (
            header.replace("**", "").replace("`", "").replace("__", "").strip()
        )
        body = f"{header_plain}\n{cmd}"
        pre_offset = _utf16_len(header_plain) + 1  # +1 por el \n
        pre_length = _utf16_len(cmd)
        await progress.reply_text(
            body,
            entities=[
                MessageEntity(
                    type=enums.MessageEntityType.PRE,
                    offset=pre_offset,
                    length=pre_length,
                    language="",  # vacío = sin badge "shell" ni intro fantasma
                )
            ],
            link_preview_options=_NO_PREVIEW,
        )


async def register_job(
    user_id: int,
    *,
    kind: str,
    output_name: str,
    files: list[MediaRef],
) -> str | None:
    usable = [f for f in files if f.file_id]
    if not usable:
        return None
    token = uuid.uuid4().hex[:12]
    await database.save_job(
        PendingJob(
            token=token,
            user_id=user_id,
            kind=kind,
            output_name=output_name,
            files=usable,
            created_at=time.time(),
        )
    )
    return token


async def ensure_lang(message: Message) -> UserSettings | None:
    """Si no hay idioma, pide elegir y devuelve None."""
    user = await database.get_user(message.from_user.id)
    if user.lang:
        return user
    await message.reply_text(
        t(DEFAULT_LANG, "choose_lang"),
        reply_markup=lang_keyboard(),
    )
    return None


# ── Handlers ───────────────────────────────────────────────────────────────


@app.on_message(filters.command(["start", "help"]) & filters.private & auth)
async def cmd_help(_: Client, message: Message):
    user = await database.get_user(message.from_user.id)
    if not user.lang:
        await message.reply_text(
            t(DEFAULT_LANG, "choose_lang"),
            reply_markup=lang_keyboard(),
        )
        return
    lang = normalize_lang(user.lang)
    await message.reply_text(
        help_text(lang),
        link_preview_options=_NO_PREVIEW,
        reply_markup=help_keyboard(lang),
    )


@app.on_message(filters.command("lang") & filters.private & auth)
async def cmd_lang(_: Client, message: Message):
    await message.reply_text(
        t(await lang_of(message.from_user.id), "choose_lang"),
        reply_markup=lang_keyboard(),
    )


@app.on_message(filters.command("settings") & filters.private & auth)
async def cmd_settings(_: Client, message: Message):
    if not await ensure_lang(message):
        return
    await message.reply_text(
        await settings_text(message.from_user.id),
        link_preview_options=_NO_PREVIEW,
    )


@app.on_message(filters.command("me") & filters.private & auth)
async def cmd_me(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    status = await message.reply_text(t(lang, "me_loading"))
    try:
        api_key = effective_api_key(user)
        limits = await dripfiles_mod.resolve_limits(http, api_key)
        if user_own_api_key(user):
            mode = t(lang, "me_mode_key")
        elif cfg.dripfiles_api_key:
            mode = t(lang, "me_mode_bot")
        else:
            mode = t(lang, "me_mode_free")
        await safe_edit(
            status,
            t(
                lang,
                "me_ok",
                mode=mode,
                tier=limits.tier,
                max_size=human_size(limits.max_size_bytes),
                max_files=limits.max_files,
                expire_days=limits.expire_days,
                chunk=human_size(limits.chunk_size),
                key=display_api_key(user, lang),
            ),
        )
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(status, t(lang, "err_drip", err=exc))


@app.on_message(filters.command("apikey") & filters.private & auth)
async def cmd_apikey(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    user_id = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not cfg.allow_user_api_keys:
        await message.reply_text(
            t(lang, "apikey_disabled", key=display_api_key(user, lang)),
            link_preview_options=_NO_PREVIEW,
        )
        return

    async def scrub():
        try:
            await message.delete()
        except Exception:
            pass

    if not arg:
        await message.reply_text(
            t(lang, "apikey_help", key=display_api_key(user, lang)),
            link_preview_options=_NO_PREVIEW,
        )
        return

    if arg.lower() in ("clear", "del", "delete", "remove", "none", "free"):
        await database.upsert_user(user_id, api_key=None)
        await scrub()
        if cfg.dripfiles_api_key:
            await message.reply_text(t(lang, "apikey_cleared_bot"))
        else:
            await message.reply_text(t(lang, "apikey_cleared"))
        return

    key = arg.strip().strip("\"'")
    status = await message.reply_text(t(lang, "apikey_validating"))
    try:
        limits = await dripfiles_mod.get_account(http, key)
        await database.upsert_user(user_id, api_key=key)
        await scrub()
        await safe_edit(
            status,
            t(
                lang,
                "apikey_ok",
                tier=limits.tier,
                max_size=human_size(limits.max_size_bytes),
                expire_days=limits.expire_days,
                key=mask_key(key, lang),
            ),
        )
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(status, t(lang, "apikey_bad", err=exc))


@app.on_message(filters.command("expire") & filters.private & auth)
async def cmd_expire(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    user_id = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        cur = (
            t(lang, "expire_days", n=user.expire_days)
            if user.expire_days
            else t(lang, "expire_default")
        )
        await message.reply_text(t(lang, "expire_help", cur=cur))
        return

    if arg.lower() in ("clear", "default", "reset", "0"):
        await database.upsert_user(user_id, expire_days=None)
        await message.reply_text(t(lang, "expire_cleared"))
        return

    try:
        days = int(arg)
    except ValueError:
        await message.reply_text(t(lang, "expire_bad_num"))
        return
    if days < 1 or days > 3650:
        await message.reply_text(t(lang, "expire_range"))
        return

    await database.upsert_user(user_id, expire_days=days)
    note = (
        t(lang, "expire_no_key_note") if not effective_api_key(user) else ""
    )
    await message.reply_text(t(lang, "expire_set", days=days, note=note))


@app.on_message(filters.command("dev") & filters.private & auth)
async def cmd_dev(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if arg in ("wget", "curl"):
        await database.upsert_user(
            message.from_user.id, dev_mode=True, dev_tool=arg
        )
        await message.reply_text(t(lang, f"dev_on_{arg}"))
        return
    if arg in ("off", "0", "false", "no"):
        await database.upsert_user(message.from_user.id, dev_mode=False)
        await message.reply_text(t(lang, "dev_off"))
        return

    state = (
        t(lang, "dev_state_tool", tool=user.dev_tool)
        if user.dev_mode
        else t(lang, "dev_state_off")
    )
    await message.reply_text(
        t(lang, "dev_pick") + "\n" + t(lang, "dev_current", state=state),
        reply_markup=dev_keyboard(lang),
    )


@app.on_message(filters.command("zip") & filters.private & auth)
async def cmd_zip(_: Client, message: Message):
    if not await ensure_lang(message):
        return
    await start_zip_session(message)


@app.on_message(filters.command("cancel") & filters.private & auth)
async def cmd_cancel(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    user_id = message.from_user.id
    if user_id not in zip_sessions:
        await message.reply_text(t(lang, "zip_none"))
        return
    await clear_zip_session(user_id)
    await message.reply_text(t(lang, "zip_cancelled"))


@app.on_message(filters.command("done") & filters.private & auth)
async def cmd_done(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    lang = normalize_lang(user.lang)
    user_id = message.from_user.id
    session = zip_sessions.get(user_id)
    if not session or session.expired():
        if session:
            await clear_zip_session(user_id)
        await message.reply_text(t(lang, "zip_none_done"))
        return

    custom_name = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        custom_name = parts[1].strip()

    spawn(finish_zip(message, session, custom_name=custom_name))


@app.on_callback_query(filters.regex(r"^lang:(es|en|pt)$") & auth)
async def lang_callback(_: Client, query: CallbackQuery):
    code = query.data.split(":", 1)[1]
    await database.upsert_user(query.from_user.id, lang=code)
    await query.answer()
    try:
        await query.message.edit_text(t(code, "lang_set"))
    except Exception:
        pass
    await query.message.reply_text(
        help_text(code),
        link_preview_options=_NO_PREVIEW,
        reply_markup=help_keyboard(code),
    )


@app.on_callback_query(filters.regex(r"^ui:(settings|dev|lang)$") & auth)
async def ui_callback(_: Client, query: CallbackQuery):
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    user = await database.get_user(user_id)
    if not user.lang:
        await query.answer()
        await query.message.reply_text(
            t(DEFAULT_LANG, "choose_lang"),
            reply_markup=lang_keyboard(),
        )
        return
    lang = normalize_lang(user.lang)
    await query.answer()

    if action == "settings":
        await query.message.reply_text(
            await settings_text(user_id), link_preview_options=_NO_PREVIEW
        )
    elif action == "dev":
        state = (
            t(lang, "dev_state_tool", tool=user.dev_tool)
            if user.dev_mode
            else t(lang, "dev_state_off")
        )
        await query.message.reply_text(
            t(lang, "dev_pick") + "\n" + t(lang, "dev_current", state=state),
            reply_markup=dev_keyboard(lang),
        )
    elif action == "lang":
        await query.message.reply_text(
            t(lang, "choose_lang"), reply_markup=lang_keyboard()
        )


@app.on_callback_query(filters.regex(r"^dev:(wget|curl|off)$") & auth)
async def dev_callback(_: Client, query: CallbackQuery):
    action = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    lang = await lang_of(user_id)
    if action == "off":
        await database.upsert_user(user_id, dev_mode=False)
        await query.answer("OFF")
        try:
            await query.message.edit_text(t(lang, "dev_off"))
        except Exception:
            await query.message.reply_text(t(lang, "dev_off"))
        return
    await database.upsert_user(user_id, dev_mode=True, dev_tool=action)
    await query.answer(action)
    text = t(lang, f"dev_on_{action}")
    try:
        await query.message.edit_text(text)
    except Exception:
        await query.message.reply_text(text)


@app.on_callback_query(filters.regex(r"^zip:(done|cancel|start)$") & auth)
async def zip_callback(_: Client, query: CallbackQuery):
    user_id = query.from_user.id
    user = await database.get_user(user_id)
    lang = normalize_lang(user.lang)
    action = query.data.split(":", 1)[1]
    session = zip_sessions.get(user_id)

    if action == "start":
        await query.answer()
        if not user.lang:
            await query.message.reply_text(
                t(DEFAULT_LANG, "choose_lang"),
                reply_markup=lang_keyboard(),
            )
            return
        await start_zip_session(query.message, reply_to_user_id=user_id)
        return

    if action == "cancel":
        if user_id in zip_sessions:
            await clear_zip_session(user_id)
            await query.answer("OK")
            try:
                await query.message.edit_text(t(lang, "zip_cancelled"))
            except Exception:
                pass
        else:
            await query.answer(t(lang, "zip_none"), show_alert=True)
        return

    if not session or session.expired():
        if session:
            await clear_zip_session(user_id)
        await query.answer(t(lang, "zip_none_done"), show_alert=True)
        return
    await query.answer(t(lang, "packing_answer"))
    spawn(finish_zip(query.message, session, custom_name=None, from_callback=True))


@app.on_callback_query(filters.regex(r"^reup:[a-f0-9]{12}$") & auth)
async def reup_callback(_: Client, query: CallbackQuery):
    token = query.data.split(":", 1)[1]
    lang = await lang_of(query.from_user.id)
    job = await database.get_job(token)
    if not job:
        await query.answer(t(lang, "reup_gone"), show_alert=True)
        return
    if query.from_user.id != job.user_id:
        await query.answer(t(lang, "reup_not_yours"), show_alert=True)
        return
    await query.answer(t(lang, "reup_answer"))
    spawn(do_reupload(query.message, job))


@app.on_message(filters.private & auth & has_media)
async def handle_media(_: Client, message: Message):
    user = await ensure_lang(message)
    if not user:
        return
    user_id = message.from_user.id
    session = zip_sessions.get(user_id)
    lang = normalize_lang(user.lang)

    if session:
        if session.expired():
            await clear_zip_session(user_id)
            await message.reply_text(t(lang, "zip_expired"))
            return
        spawn(stage_for_zip(message, session))
        return

    spawn(handle_single_file(message))


async def start_zip_session(
    message: Message, *, reply_to_user_id: int | None = None
) -> None:
    user_id = reply_to_user_id or message.from_user.id
    user = await database.get_user(user_id)
    lang = normalize_lang(user.lang)
    existing = zip_sessions.get(user_id)
    if existing and not existing.expired():
        await message.reply_text(
            t(
                lang,
                "zip_already",
                n=len(existing.files),
                size=human_size(existing.total_size),
            ),
            reply_markup=zip_keyboard(lang),
        )
        return
    if existing:
        await clear_zip_session(user_id)

    work = user_work_dir(user_id, "zip")
    session = ZipSession(user_id=user_id, work_dir=work)
    try:
        limits, _, _ = await user_limits(user)
        lim = human_size(limits.max_size_bytes)
    except Exception:
        lim = "2 GB"

    status = await message.reply_text(
        t(
            lang,
            "zip_active",
            limit=lim,
            timeout=cfg.zip_timeout_minutes,
            n=0,
            size="0 B",
        ),
        reply_markup=zip_keyboard(lang),
    )
    session.status_msg = status
    zip_sessions[user_id] = session


async def stage_for_zip(message: Message, session: ZipSession) -> None:
    session.touch()
    user = await database.get_user(session.user_id)
    lang = normalize_lang(user.lang)
    try:
        limits, _, _ = await user_limits(user)
    except dripfiles_mod.DripFilesError as exc:
        await message.reply_text(t(lang, "err_drip", err=exc))
        return

    size_hint, raw_name = media_meta(message)
    name = safe_filename(raw_name)

    if size_hint and session.total_size + size_hint > limits.max_size_bytes:
        await message.reply_text(
            t(
                lang,
                "zip_too_big",
                limit=human_size(limits.max_size_bytes),
                current=human_size(session.total_size),
                extra=human_size(size_hint),
            )
        )
        return

    progress = await message.reply_text(t(lang, "zip_add", name=name))
    try:
        staged = await download_telegram_media(
            message,
            session.work_dir,
            max_size=limits.max_size_bytes,
            progress=progress,
            lang=lang,
        )
        if session.total_size + staged.size > limits.max_size_bytes:
            os.remove(staged.path)
            await safe_edit(
                progress,
                t(
                    lang,
                    "zip_too_big_short",
                    limit=human_size(limits.max_size_bytes),
                ),
            )
            return

        session.files.append(staged)
        session.touch()
        n = len(session.files)
        await safe_edit(
            progress,
            t(
                lang,
                "zip_added",
                n=n,
                name=staged.filename,
                size=human_size(staged.size),
                total=human_size(session.total_size),
            ),
        )
        await refresh_zip_status(session, lang)
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(progress, t(lang, "err_drip", err=exc))
    except Exception as exc:
        log.exception("Error añadiendo archivo al zip")
        await safe_edit(progress, t(lang, "err_download", err=exc))


async def refresh_zip_status(session: ZipSession, lang: str) -> None:
    if not session.status_msg:
        return
    n = len(session.files)
    lines = [
        t(
            lang,
            "zip_active",
            limit="—",
            timeout=cfg.zip_timeout_minutes,
            n=n,
            size=human_size(session.total_size),
        ).split("\n\n")[0],  # header only-ish; rebuild cleanly below
    ]
    # rebuild clean status
    body = [
        f"📦 **ZIP** · **{n}** · {human_size(session.total_size)}",
        "",
    ]
    for i, f in enumerate(session.files[-12:], start=max(1, n - 11)):
        body.append(f"{i}. `{f.filename}` ({human_size(f.size)})")
    if n > 12:
        body.append(f"… {n - 12}")
    body.append(t(lang, "zip_status_footer").strip())
    await safe_edit(
        session.status_msg,
        "\n".join(body),
        reply_markup=zip_keyboard(lang),
    )


async def finish_zip(
    message: Message,
    session: ZipSession,
    *,
    custom_name: str | None,
    from_callback: bool = False,
) -> None:
    user_id = session.user_id
    user = await database.get_user(user_id)
    lang = normalize_lang(user.lang)

    if session.busy:
        if not from_callback:
            await message.reply_text(t(lang, "zip_busy"))
        return
    if not session.files:
        await message.reply_text(t(lang, "zip_empty"))
        return

    session.busy = True
    session.touch()
    zip_sessions.pop(user_id, None)

    refs = [
        MediaRef(file_id=f.file_id, filename=f.filename, size=f.size)
        for f in session.files
        if f.file_id
    ]

    progress = await message.reply_text(
        t(lang, "zip_packing", n=len(session.files))
    )
    try:
        limits, expire, failover = await user_limits(user)
        prefer_free = failover in ("auth", "me_error")

        if custom_name:
            zip_name = safe_filename(custom_name)
            if not zip_name.lower().endswith(".zip"):
                zip_name += ".zip"
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"drip_{stamp}.zip"

        zip_path = os.path.join(session.work_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            for staged in session.files:
                zf.write(staged.path, arcname=staged.filename)

        zip_size = os.path.getsize(zip_path)
        if zip_size > limits.max_size_bytes:
            await safe_edit(
                progress,
                t(
                    lang,
                    "zip_too_big_result",
                    size=human_size(zip_size),
                    limit=human_size(limits.max_size_bytes),
                ),
            )
            return

        await safe_edit(
            progress,
            t(
                lang,
                "zip_ready",
                name=zip_name,
                size=human_size(zip_size),
            ),
        )
        result = await upload_to_dripfiles(
            zip_path,
            zip_name,
            zip_size,
            progress,
            user=user,
            limits=limits,
            expire_seconds=expire,
            lang=lang,
            count=len(session.files),
            prefer_free=prefer_free,
        )
        token = await register_job(
            user_id, kind="zip", output_name=zip_name, files=refs
        )
        used_tier = "free" if result.get("_failover") or prefer_free else limits.tier
        await show_success(
            progress,
            url=result["url"],
            filename=zip_name,
            size=zip_size,
            count=len(session.files),
            token=token,
            user=user,
            expire_seconds=result.get("expire") or (
                None if result.get("_failover") or prefer_free else expire
            ),
            expires_at=result.get("expires_at"),
            tier=used_tier,
            failover=bool(result.get("_failover") or prefer_free),
        )
        if session.status_msg:
            try:
                await session.status_msg.edit_text(
                    t(lang, "zip_closed", name=zip_name)
                )
            except Exception:
                pass
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(progress, t(lang, "err_drip", err=exc))
    except Exception as exc:
        log.exception("Error finalizando zip")
        await safe_edit(progress, t(lang, "err_generic", err=exc))
    finally:
        rmtree_quiet(session.work_dir)


async def clear_zip_session(user_id: int) -> None:
    session = zip_sessions.pop(user_id, None)
    if session:
        rmtree_quiet(session.work_dir)


async def handle_single_file(message: Message) -> None:
    size_hint, raw_name = media_meta(message)
    name = safe_filename(raw_name)
    user_id = message.from_user.id
    user = await database.get_user(user_id)
    lang = normalize_lang(user.lang)
    work = user_work_dir(user_id, "single")
    progress = await message.reply_text(
        t(lang, "downloading", filename=name) + "…"
    )
    try:
        limits, expire, failover = await user_limits(user)
        prefer_free = failover in ("auth", "me_error")
        staged = await download_telegram_media(
            message,
            work,
            max_size=limits.max_size_bytes,
            progress=progress,
            lang=lang,
        )
        result = await upload_to_dripfiles(
            staged.path,
            staged.filename,
            staged.size,
            progress,
            user=user,
            limits=limits,
            expire_seconds=expire,
            lang=lang,
            prefer_free=prefer_free,
        )
        token = await register_job(
            user_id,
            kind="single",
            output_name=staged.filename,
            files=[
                MediaRef(
                    file_id=staged.file_id,
                    filename=staged.filename,
                    size=staged.size,
                )
            ],
        )
        used_tier = "free" if result.get("_failover") or prefer_free else limits.tier
        await show_success(
            progress,
            url=result["url"],
            filename=staged.filename,
            size=staged.size,
            count=1,
            token=token,
            user=user,
            expire_seconds=result.get("expire") or (
                None if result.get("_failover") or prefer_free else expire
            ),
            expires_at=result.get("expires_at"),
            tier=used_tier,
            failover=bool(result.get("_failover") or prefer_free),
        )
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(progress, t(lang, "err_drip", err=exc))
    except Exception as exc:
        log.exception("Error con archivo suelto")
        await safe_edit(progress, t(lang, "err_generic", err=exc))
    finally:
        rmtree_quiet(work)


async def do_reupload(origin: Message, job: PendingJob) -> None:
    work = user_work_dir(job.user_id, "reup")
    user = await database.get_user(job.user_id)
    lang = normalize_lang(user.lang)
    progress = await origin.reply_text(
        t(lang, "reup_start", name=job.output_name)
    )
    try:
        limits, expire, failover = await user_limits(user)
        prefer_free = failover in ("auth", "me_error")
        staged_files: list[StagedFile] = []
        n = len(job.files)
        for i, ref in enumerate(job.files, start=1):
            dest_name = safe_filename(ref.filename)
            dest = os.path.join(work, dest_name)
            if os.path.exists(dest):
                stem = Path(dest_name).stem
                suffix = Path(dest_name).suffix
                dest_name = f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"
                dest = os.path.join(work, dest_name)

            if n > 1:
                await safe_edit(
                    progress,
                    t(lang, "reup_progress", i=i, n=n, name=dest_name),
                )
            staged = await download_to_path(
                file_id=ref.file_id,
                dest=dest,
                filename=dest_name,
                size_hint=ref.size or None,
                max_size=limits.max_size_bytes,
                progress=progress if n == 1 else None,
                lang=lang,
            )
            staged.filename = safe_filename(ref.filename) or staged.filename
            staged_files.append(staged)

        if job.kind == "zip" or len(staged_files) > 1:
            zip_name = safe_filename(job.output_name)
            if not zip_name.lower().endswith(".zip"):
                zip_name += ".zip"
            zip_path = os.path.join(work, zip_name)
            await safe_edit(
                progress, t(lang, "zip_packing", n=len(staged_files))
            )
            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_STORED
            ) as zf:
                for staged in staged_files:
                    zf.write(staged.path, arcname=staged.filename)
            out_path = zip_path
            out_name = zip_name
            out_size = os.path.getsize(zip_path)
            count = len(staged_files)
        else:
            staged = staged_files[0]
            out_path = staged.path
            out_name = job.output_name or staged.filename
            out_size = staged.size
            count = 1

        if out_size > limits.max_size_bytes:
            await safe_edit(
                progress,
                t(
                    lang,
                    "file_too_big_result",
                    size=human_size(out_size),
                    limit=human_size(limits.max_size_bytes),
                ),
            )
            return

        result = await upload_to_dripfiles(
            out_path,
            out_name,
            out_size,
            progress,
            user=user,
            limits=limits,
            expire_seconds=expire,
            lang=lang,
            count=count,
            prefer_free=prefer_free,
        )
        used_tier = "free" if result.get("_failover") or prefer_free else limits.tier
        await show_success(
            progress,
            url=result["url"],
            filename=out_name,
            size=out_size,
            count=count,
            token=job.token,
            user=user,
            expire_seconds=result.get("expire") or (
                None if result.get("_failover") or prefer_free else expire
            ),
            expires_at=result.get("expires_at"),
            tier=used_tier,
            failover=bool(result.get("_failover") or prefer_free),
        )
        await database.touch_job(job.token)
    except dripfiles_mod.DripFilesError as exc:
        await safe_edit(progress, t(lang, "err_drip", err=exc))
    except Exception as exc:
        log.exception("Error en resubida %s", job.token)
        await safe_edit(progress, t(lang, "err_reup", err=exc))
    finally:
        rmtree_quiet(work)


async def zip_janitor() -> None:
    while True:
        await asyncio.sleep(60)
        expired = [
            uid
            for uid, s in list(zip_sessions.items())
            if s.expired() and not s.busy
        ]
        for uid in expired:
            session = zip_sessions.get(uid)
            lang = await lang_of(uid)
            await clear_zip_session(uid)
            if session and session.status_msg:
                try:
                    await session.status_msg.edit_text(
                        t(lang, "zip_expired_idle", m=cfg.zip_timeout_minutes)
                    )
                except Exception:
                    pass
            log.info("Sesión ZIP expirada para user %s", uid)
        try:
            await database.prune_jobs()
        except Exception:
            log.debug("prune_jobs falló", exc_info=True)


async def main() -> None:
    global http, database
    os.makedirs(cfg.download_dir, exist_ok=True)

    database = Database(cfg.database_path)
    await database.connect()

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=60, sock_read=600)
    http = aiohttp.ClientSession(timeout=timeout)

    if cfg.allowed_users:
        log.info("Whitelist: %s user(s)", len(cfg.allowed_users))
    else:
        log.info("Public bot (ALLOWED_USER_IDS empty)")
    if cfg.dripfiles_api_key:
        log.info(
            "DripFiles bot key: set (uploads auth by default); "
            "user keys: %s",
            "allowed" if cfg.allow_user_api_keys else "disabled",
        )
    else:
        log.info(
            "DripFiles bot key: none (free unless user /apikey); "
            "user keys: %s",
            "allowed" if cfg.allow_user_api_keys else "disabled",
        )

    await app.start()
    commands = [
        BotCommand("start", "Help / Ayuda"),
        BotCommand("help", "Help / Ayuda"),
        BotCommand("lang", "Language / Idioma"),
        BotCommand("zip", "ZIP mode"),
        BotCommand("done", "Finish ZIP"),
        BotCommand("cancel", "Cancel ZIP"),
    ]
    if cfg.allow_user_api_keys:
        commands.append(BotCommand("apikey", "DripFiles API key"))
    commands.extend(
        [
            BotCommand("expire", "Preferred expiry days"),
            BotCommand("dev", "Dev: wget / curl"),
            BotCommand("settings", "Settings"),
            BotCommand("me", "DripFiles account limits"),
        ]
    )
    await app.set_bot_commands(commands)
    me = await app.get_me()
    log.info("DripFilesBot @%s (db=%s)", me.username, cfg.database_path)
    janitor = asyncio.create_task(zip_janitor())
    try:
        await idle()
    finally:
        janitor.cancel()
        for uid in list(zip_sessions.keys()):
            await clear_zip_session(uid)
        await app.stop()
        await http.close()
        await database.close()


if __name__ == "__main__":
    app.loop.run_until_complete(main())
