<div align="center">

<img src="https://dripfiles.com/assets/img/logo.png" alt="DripFiles" width="160" />

# DripFilesBot

### Telegram companion for [DripFiles](https://dripfiles.com)

**Send a file. Get a share link. Done.**

[![Telegram](https://img.shields.io/badge/Telegram-@DripFilesBot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/DripFilesBot)
[![DripFiles](https://img.shields.io/badge/Powered%20by-DripFiles-0ea5e9?style=for-the-badge)](https://dripfiles.com)
[![Uploads](https://img.shields.io/badge/Uploads-up%20to%204%20GB-22c55e?style=for-the-badge)](https://t.me/DripFilesBot)
[![License](https://img.shields.io/badge/License-MIT-a855f7?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

<br/>

> **[@DripFilesBot](https://t.me/DripFilesBot)** talks to the **official DripFiles API**.  
> Drop any media in the chat and get a shareable download link — with live progress, zip mode, re-upload, multi-language UI, and optional **bring-your-own API key** for higher plan limits.

<br/>

| 💧 Bot | 📦 Max path | ⏱ Free links | 🔑 Your plan |
|:---:|:---:|:---:|:---:|
| **[@DripFilesBot](https://t.me/DripFilesBot)** | **Up to 4 GB**¹ | ~2 days | Account limits |

<sup>¹ Telegram Premium can send large files to the bot; free DripFiles API stays ~2 GB unless you use your own key.</sup>

</div>

---

## Why this bot?

[DripFiles](https://dripfiles.com) hosts the file. **DripFilesBot** is the Telegram front-end so you never leave the chat to share something.

| Without the bot | With the bot |
|---|---|
| Browser → upload → copy link | Send file in Telegram → get link |
| Re-upload manually when free links expire | One tap **Resubir** / **Re-upload** |
| Separate tools for multi-file packs | `/zip` → dump files → one archive |

This repository is the open-source bot you can also self-host.

---

## Highlights

- **Up to 4 GB** path via Telegram Premium + MTProto (kurigram)  
- **Free tier with no key** — uses DripFiles public API (~2 GB, ~2 days)  
- **Bring your own API key** — per-user key in SQLite; your DripFiles plan limits  
- **API key failover** — invalid key → automatic retry on free (if size fits)  
- **Zip mode** — pile files, pack once, share one link  
- **Re-upload button** — revive expired free links without re-sending the file  
- **Dev mode** — copy-ready **`wget`** or **`curl`** after each upload  
- **Multi-language** — Español · English · Português (`/lang` or first-start buttons)  
- **Live progress** — Telegram download + DripFiles upload  
- **Open by default** — optional host whitelist (`ALLOWED_USER_IDS`)  
- **Stack** — kurigram/pyrogram · aiohttp · aiosqlite  

---

## How it works

```text
  You (Telegram)                DripFilesBot                 DripFiles
  ───────────────               ────────────                 ─────────
        │                            │                            │
        │  1. Send file / media      │                            │
        │ ─────────────────────────► │                            │
        │                            │  2. Download via MTProto   │
        │                            │  (up to ~4 GB Premium)     │
        │                            │                            │
        │  3. Progress updates       │  4. Chunked upload API     │
        │ ◄───────────────────────── │ ─────────────────────────► │
        │                            │     create → chunks        │
        │                            │     → complete → ready     │
        │                            │                            │
        │  5. Share link + buttons   │  6. Public download URL    │
        │ ◄───────────────────────── │ ◄───────────────────────── │
        │     💧 Open · 🔄 Re-upload │                            │
```

### Under the hood

1. **Receive** — document, photo, video, audio, voice, sticker, etc.  
2. **Download** — temp workspace under `DOWNLOAD_DIR`.  
3. **Upload** — chunked to the official DripFiles API:
   - Free: `https://dripfiles.com/api/v1/free` (no key)
   - Authenticated: `https://dripfiles.com/api/v1` with `Authorization: Bearer <key>`
4. **Reply** — DripFiles URL, expiry note, **Open** + **Re-upload** buttons.  
5. **Optional zip** — archive locally, then one upload.

Re-upload jobs store Telegram `file_id`s in SQLite (not the file bytes) so the bot can re-fetch media later.

**Failover:** if a saved API key is rejected (401/403), the bot retries the free API when the file is within free limits, and tells the user to fix `/apikey`.

---

## Quick start (as a user)

1. Open **[@DripFilesBot](https://t.me/DripFilesBot)** on Telegram.  
2. `/start` → pick language.  
3. Drop a file (or `/zip` for several).  
4. Share the link. Optional: `/dev` for a copyable `wget` / `curl` command.

### Which DripFiles key is used?

Priority:

1. **User’s own key** — only if the host set `ALLOW_USER_API_KEYS=true` (default) and the user ran `/apikey YOUR_KEY`
2. **Bot key** — `DRIPFILES_API_KEY` (all uploads for everyone else)
3. **Free plan** — if there is no bot key and no user key

| Mode | Size (typical) | Link lifetime | How |
|---|---|---|---|
| **Bot API key** (default) | Operator plan (bot path up to **~4 GB**) | Plan default or `/expire N` | Just send a file (`DRIPFILES_API_KEY`) |
| **Your API key** | Your plan (bot path up to **~4 GB**) | Plan default or `/expire N` | `/apikey YOUR_KEY` (if host allows) |
| **Free** | ~2 GB | ~2 days (fixed by DripFiles) | No bot key and no personal key |

**Host option:** set `ALLOW_USER_API_KEYS=false` so nobody can override your bot key (or free tier). `/apikey` then replies that personal keys are disabled.

Create a personal key in your [DripFiles account](https://dripfiles.com). The bot validates it with `GET /api/v1/me` and stores it **in plain text in SQLite on the bot host**. Self-host if you need full control over key privacy.

---

## Commands

| Command | What it does |
|---|---|
| `/start` · `/help` | Welcome, tips, quick-action buttons |
| `/lang` | Language: ES / EN / PT |
| `/zip` | Start a multi-file session |
| `/done` `[name.zip]` | Pack staged files and upload |
| `/cancel` | Abort zip and wipe temp files |
| `/apikey YOUR_KEY` | Save & validate your own DripFiles API key |
| `/apikey clear` | Remove yours → back to the bot's key |
| `/expire 7` | Preferred link lifetime in days (paid) |
| `/expire clear` | Use plan default expiry |
| `/dev` | Buttons: **wget** · **curl** · **OFF** |
| `/dev wget` · `/dev curl` · `/dev off` | Set directly |
| `/settings` | Your configuration |
| `/me` | Live DripFiles limits (bot key / your key / free) |

### After each successful upload

| Button | Action |
|---|---|
| **💧 Open in DripFiles** | Opens the public share page |
| **🔄 Re-upload** | Re-downloads from Telegram and uploads a fresh link |

---

## Zip mode

```text
/zip
  → send file A
  → send file B
  → send file C
/done my-pack.zip     # or tap ✅ Done
```

- Idle sessions expire after `ZIP_TIMEOUT_MINUTES` (default **30**).  
- Total size respects your DripFiles limit (and the ~4 GB Telegram path).  
- `/cancel` or ❌ deletes temporary files.

---

## Dev mode

```text
/dev              # buttons: wget | curl | OFF
/dev wget
/dev curl
/dev off
```

After a successful upload you get a copy-friendly block, e.g.:

```text
wget --output-document='report.pdf' 'https://dripfiles.com/AbCd1234'
```

```text
curl -L -o 'report.pdf' 'https://dripfiles.com/AbCd1234'
```

Long form for wget avoids `-O` looking like `-0` in some fonts. Tap-to-copy works well on mobile Telegram.

---

## Languages

On first `/start` the bot asks for a language (buttons). Change anytime with `/lang` or the help menu.

| Code | Language |
|---|---|
| `es` | Español |
| `en` | English |
| `pt` | Português |

---

## Self-hosting

### 1. Environment

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_API_ID` | yes | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `TELEGRAM_API_HASH` | yes | Same as above |
| `TELEGRAM_BOT_TOKEN` | yes | [@BotFather](https://t.me/BotFather) |
| `DRIPFILES_API_KEY` | no | Default DripFiles API key for all uploads |
| `ALLOW_USER_API_KEYS` | no | `true` (default) = users may `/apikey`. `false` = always bot key / free |
| `ALLOWED_USER_IDS` | no | Empty = **public**. Comma-separated IDs = whitelist |
| `DOWNLOAD_DIR` | no | Temp workspace (default `downloads`) |
| `DATABASE_PATH` | no | SQLite path (default `downloads/dripfiles_bot.db`) |
| `DRIPFILES_MESSAGE` | no | Description on DripFiles page (`{filename}`, `{size}`, `{count}`). Default: `{filename}` only |
| `ZIP_TIMEOUT_MINUTES` | no | Idle zip timeout (default `30`) |
| `LOG_LEVEL` | no | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

### 2. Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 3. Docker

```bash
docker build -t dripfiles-bot .
docker run -d --name dripfiles-bot \
  --env-file .env \
  -v dripfiles_data:/app/downloads \
  dripfiles-bot
```

Mount `downloads` (or your `DATABASE_PATH`) so the SQLite DB (API keys, prefs, re-upload jobs) survives restarts.

### Private mode

```env
ALLOWED_USER_IDS=123456789,987654321
```

Leave empty for a fully open bot.

---

## Project layout

```text
DripFilesBot/
├── main.py           # Handlers, zip, buttons, progress, failover
├── dripfiles.py      # Free + authenticated DripFiles client
├── db.py             # SQLite: users, prefs, re-upload jobs
├── i18n.py           # ES / EN / PT strings
├── config.py         # Env / .env loading
├── requirements.txt
├── Dockerfile
├── .env.example
├── README.md
└── LICENSE
```

---

## Stack

| Piece | Role |
|---|---|
| **[kurigram](https://github.com/KurimuzonAkuma/kurigram) / Pyrogram** | Telegram MTProto (large downloads) |
| **aiohttp** | Async HTTP to DripFiles |
| **aiosqlite** | Per-user keys, prefs, re-upload tokens |
| **Docker** | Simple deploy |

---

## Related

- **Website:** [dripfiles.com](https://dripfiles.com)  
- **Bot:** [@DripFilesBot](https://t.me/DripFilesBot)  
- **Sister project:** [DebridBot](https://github.com/Oihalitz/DebridBot) — multi-debrid unlocker (also has a DripFiles action)

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

<img src="https://dripfiles.com/assets/img/logo.png" alt="DripFiles" width="72" />

**Drop it. Share it. Done.**

[DripFiles](https://dripfiles.com) · [**@DripFilesBot**](https://t.me/DripFilesBot)

</div>
