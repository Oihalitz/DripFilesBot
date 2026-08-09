"""SQLite persistence: per-user settings + re-upload jobs."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

log = logging.getLogger("bot.db")

PENDING_TTL_SECONDS = 30 * 24 * 3600
PENDING_MAX = 2000


@dataclass
class UserSettings:
    user_id: int
    api_key: str | None = None
    expire_days: int | None = None
    dev_mode: bool = False
    dev_tool: str = "wget"  # wget | curl
    lang: str | None = None  # None = still pick language
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class MediaRef:
    file_id: str
    filename: str
    size: int = 0


@dataclass
class PendingJob:
    token: str
    user_id: int
    kind: str
    output_name: str
    files: list[MediaRef]
    created_at: float


class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                api_key     TEXT,
                expire_days INTEGER,
                dev_mode    INTEGER NOT NULL DEFAULT 0,
                dev_tool    TEXT DEFAULT 'wget',
                lang        TEXT,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pending_jobs (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                kind        TEXT NOT NULL,
                output_name TEXT NOT NULL,
                files_json  TEXT NOT NULL,
                created_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pending_user
                ON pending_jobs(user_id);
            CREATE INDEX IF NOT EXISTS idx_pending_created
                ON pending_jobs(created_at);
            """
        )
        await self._migrate()
        await self._db.commit()
        log.info("DB lista: %s", self.path)

    async def _migrate(self) -> None:
        assert self._db
        async with self._db.execute("PRAGMA table_info(users)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "lang" not in cols:
            await self._db.execute("ALTER TABLE users ADD COLUMN lang TEXT")
        if "dev_tool" not in cols:
            await self._db.execute(
                "ALTER TABLE users ADD COLUMN dev_tool TEXT DEFAULT 'wget'"
            )

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("Database no conectada")
        return self._db

    async def get_user(self, user_id: int) -> UserSettings:
        async with self.db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return UserSettings(user_id=user_id)
        keys = row.keys()
        tool = row["dev_tool"] if "dev_tool" in keys else "wget"
        if tool not in ("wget", "curl"):
            tool = "wget"
        lang = row["lang"] if "lang" in keys else None
        return UserSettings(
            user_id=user_id,
            api_key=(row["api_key"] or None),
            expire_days=row["expire_days"],
            dev_mode=bool(row["dev_mode"]),
            dev_tool=tool or "wget",
            lang=lang or None,
            created_at=row["created_at"] or 0.0,
            updated_at=row["updated_at"] or 0.0,
        )

    async def upsert_user(
        self,
        user_id: int,
        *,
        api_key: str | None | object = ...,
        expire_days: int | None | object = ...,
        dev_mode: bool | object = ...,
        dev_tool: str | object = ...,
        lang: str | None | object = ...,
    ) -> UserSettings:
        current = await self.get_user(user_id)
        now = time.time()

        new_key = current.api_key if api_key is ... else api_key
        new_expire = current.expire_days if expire_days is ... else expire_days
        new_dev = current.dev_mode if dev_mode is ... else bool(dev_mode)
        new_tool = current.dev_tool if dev_tool is ... else str(dev_tool or "wget")
        if new_tool not in ("wget", "curl"):
            new_tool = "wget"
        new_lang = current.lang if lang is ... else lang
        created = current.created_at or now

        await self.db.execute(
            """
            INSERT INTO users (
                user_id, api_key, expire_days, dev_mode, dev_tool, lang,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                api_key = excluded.api_key,
                expire_days = excluded.expire_days,
                dev_mode = excluded.dev_mode,
                dev_tool = excluded.dev_tool,
                lang = excluded.lang,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                new_key,
                new_expire,
                1 if new_dev else 0,
                new_tool,
                new_lang,
                created,
                now,
            ),
        )
        await self.db.commit()
        return await self.get_user(user_id)

    async def save_job(self, job: PendingJob) -> None:
        await self.db.execute(
            """
            INSERT INTO pending_jobs (token, user_id, kind, output_name, files_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
                user_id = excluded.user_id,
                kind = excluded.kind,
                output_name = excluded.output_name,
                files_json = excluded.files_json,
                created_at = excluded.created_at
            """,
            (
                job.token,
                job.user_id,
                job.kind,
                job.output_name,
                json.dumps(
                    [
                        {
                            "file_id": f.file_id,
                            "filename": f.filename,
                            "size": f.size,
                        }
                        for f in job.files
                    ],
                    ensure_ascii=False,
                ),
                job.created_at,
            ),
        )
        await self.db.commit()
        await self.prune_jobs()

    async def get_job(self, token: str) -> PendingJob | None:
        async with self.db.execute(
            "SELECT * FROM pending_jobs WHERE token = ?", (token,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        job = self._row_to_job(row)
        if job and (time.time() - job.created_at) > PENDING_TTL_SECONDS:
            await self.delete_job(token)
            return None
        return job

    async def touch_job(self, token: str) -> None:
        await self.db.execute(
            "UPDATE pending_jobs SET created_at = ? WHERE token = ?",
            (time.time(), token),
        )
        await self.db.commit()

    async def delete_job(self, token: str) -> None:
        await self.db.execute(
            "DELETE FROM pending_jobs WHERE token = ?", (token,)
        )
        await self.db.commit()

    async def prune_jobs(self) -> None:
        cutoff = time.time() - PENDING_TTL_SECONDS
        await self.db.execute(
            "DELETE FROM pending_jobs WHERE created_at < ?", (cutoff,)
        )
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM pending_jobs"
        ) as cur:
            row = await cur.fetchone()
            count = int(row["c"] if row else 0)
        if count > PENDING_MAX:
            overflow = count - PENDING_MAX
            await self.db.execute(
                """
                DELETE FROM pending_jobs WHERE token IN (
                    SELECT token FROM pending_jobs
                    ORDER BY created_at ASC LIMIT ?
                )
                """,
                (overflow,),
            )
        await self.db.commit()

    def _row_to_job(self, row: aiosqlite.Row) -> PendingJob | None:
        try:
            raw = json.loads(row["files_json"] or "[]")
            files = [
                MediaRef(
                    file_id=str(f["file_id"]),
                    filename=str(f["filename"]),
                    size=int(f.get("size") or 0),
                )
                for f in raw
                if f.get("file_id")
            ]
            if not files:
                return None
            return PendingJob(
                token=row["token"],
                user_id=int(row["user_id"]),
                kind=str(row["kind"] or "single"),
                output_name=str(row["output_name"]),
                files=files,
                created_at=float(row["created_at"] or 0),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
