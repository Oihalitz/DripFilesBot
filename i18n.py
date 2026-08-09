"""Multi-language strings (es / en / pt)."""

from __future__ import annotations

from typing import Any

LANGS = ("es", "en", "pt")
LANG_LABELS = {
    "es": "🇪🇸 Español",
    "en": "🇬🇧 English",
    "pt": "🇧🇷 Português",
}
DEFAULT_LANG = "es"

# key -> {lang: text}. Use {name} placeholders.
STRINGS: dict[str, dict[str, str]] = {
    "choose_lang": {
        "es": "🌍 **Elige idioma / Choose language**",
        "en": "🌍 **Choose language / Elige idioma**",
        "pt": "🌍 **Escolha o idioma / Choose language**",
    },
    "lang_set": {
        "es": "✅ Idioma: **Español**",
        "en": "✅ Language: **English**",
        "pt": "✅ Idioma: **Português**",
    },
    "help": {
        "es": (
            "💧 **DripFilesBot**\n\n"
            "Mándame un **archivo** y te devuelvo un enlace de "
            "[DripFiles](https://dripfiles.com).\n\n"
            "**Sin API key** → plan free (~2 GB, ~2 días).\n"
            "**Con tu API key** → límites de **tu** cuenta.\n"
            "Telegram Premium: hasta **~4 GB** al bot.\n\n"
            "**Comandos**\n"
            "• `/zip` — acumular y empaquetar\n"
            "• `/done` `[nombre.zip]` · `/cancel`\n"
            "• `/apikey TU_KEY` · `/apikey clear`\n"
            "• `/expire 7` — caducidad preferida (con key)\n"
            "• `/dev` — wget / curl / off (comando copiable)\n"
            "• `/lang` — cambiar idioma\n"
            "• `/settings` · `/me`\n\n"
            "Tras subir: **💧 Abrir** · **🔄 Resubir**\n\n"
            "{open_note}"
        ),
        "en": (
            "💧 **DripFilesBot**\n\n"
            "Send me a **file** and I'll give you a "
            "[DripFiles](https://dripfiles.com) link.\n\n"
            "**No API key** → free plan (~2 GB, ~2 days).\n"
            "**Your API key** → your account limits.\n"
            "Telegram Premium: up to **~4 GB** to the bot.\n\n"
            "**Commands**\n"
            "• `/zip` — collect files into a zip\n"
            "• `/done` `[name.zip]` · `/cancel`\n"
            "• `/apikey YOUR_KEY` · `/apikey clear`\n"
            "• `/expire 7` — preferred expiry (with key)\n"
            "• `/dev` — wget / curl / off (copyable command)\n"
            "• `/lang` — change language\n"
            "• `/settings` · `/me`\n\n"
            "After upload: **💧 Open** · **🔄 Re-upload**\n\n"
            "{open_note}"
        ),
        "pt": (
            "💧 **DripFilesBot**\n\n"
            "Envie um **arquivo** e eu devolvo um link do "
            "[DripFiles](https://dripfiles.com).\n\n"
            "**Sem API key** → plano free (~2 GB, ~2 dias).\n"
            "**Com sua API key** → limites da **sua** conta.\n"
            "Telegram Premium: até **~4 GB** para o bot.\n\n"
            "**Comandos**\n"
            "• `/zip` — juntar arquivos num zip\n"
            "• `/done` `[nome.zip]` · `/cancel`\n"
            "• `/apikey SUA_KEY` · `/apikey clear`\n"
            "• `/expire 7` — validade preferida (com key)\n"
            "• `/dev` — wget / curl / off (comando copiável)\n"
            "• `/lang` — mudar idioma\n"
            "• `/settings` · `/me`\n\n"
            "Após enviar: **💧 Abrir** · **🔄 Reenviar**\n\n"
            "{open_note}"
        ),
    },
    "open_public": {
        "es": "🌍 Bot **abierto** (cualquiera puede usarlo).",
        "en": "🌍 Bot is **public** (anyone can use it).",
        "pt": "🌍 Bot **aberto** (qualquer um pode usar).",
    },
    "open_whitelist": {
        "es": "🔒 Whitelist activa ({n} usuario(s)).",
        "en": "🔒 Whitelist on ({n} user(s)).",
        "pt": "🔒 Whitelist ativa ({n} usuário(s)).",
    },
    "btn_zip_start": {
        "es": "📦 Empezar modo ZIP",
        "en": "📦 Start ZIP mode",
        "pt": "📦 Iniciar modo ZIP",
    },
    "btn_settings": {
        "es": "⚙️ Ajustes",
        "en": "⚙️ Settings",
        "pt": "⚙️ Ajustes",
    },
    "btn_dev": {
        "es": "🛠 Modo dev",
        "en": "🛠 Dev mode",
        "pt": "🛠 Modo dev",
    },
    "btn_lang": {
        "es": "🌍 Idioma",
        "en": "🌍 Language",
        "pt": "🌍 Idioma",
    },
    "btn_zip_done": {
        "es": "✅ Listo",
        "en": "✅ Done",
        "pt": "✅ Pronto",
    },
    "btn_zip_cancel": {
        "es": "❌ Cancelar",
        "en": "❌ Cancel",
        "pt": "❌ Cancelar",
    },
    "btn_open": {
        "es": "💧 Abrir en DripFiles",
        "en": "💧 Open on DripFiles",
        "pt": "💧 Abrir no DripFiles",
    },
    "btn_reup": {
        "es": "🔄 Resubir a DripFiles",
        "en": "🔄 Re-upload to DripFiles",
        "pt": "🔄 Reenviar ao DripFiles",
    },
    "btn_dev_wget": {
        "es": "wget",
        "en": "wget",
        "pt": "wget",
    },
    "btn_dev_curl": {
        "es": "curl",
        "en": "curl",
        "pt": "curl",
    },
    "btn_dev_off": {
        "es": "Dev OFF",
        "en": "Dev OFF",
        "pt": "Dev OFF",
    },
    "success": {
        "es": (
            "✅ **Listo**\n\n"
            "📄 `{filename}`\n"
            "{count_line}"
            "💧 [Descargar en DripFiles]({url})\n"
            "{expire_note} {tier_note}\n"
            "🔄 Si caduca, pulsa **Resubir**."
        ),
        "en": (
            "✅ **Done**\n\n"
            "📄 `{filename}`\n"
            "{count_line}"
            "💧 [Download on DripFiles]({url})\n"
            "{expire_note} {tier_note}\n"
            "🔄 If it expires, tap **Re-upload**."
        ),
        "pt": (
            "✅ **Pronto**\n\n"
            "📄 `{filename}`\n"
            "{count_line}"
            "💧 [Baixar no DripFiles]({url})\n"
            "{expire_note} {tier_note}\n"
            "🔄 Se expirar, toque em **Reenviar**."
        ),
    },
    "count_line": {
        "es": "📦 Archivos en el zip: **{count}**\n",
        "en": "📦 Files in zip: **{count}**\n",
        "pt": "📦 Arquivos no zip: **{count}**\n",
    },
    "tier_note": {
        "es": "· plan **{tier}**",
        "en": "· plan **{tier}**",
        "pt": "· plano **{tier}**",
    },
    "dev_header": {
        # Sin backticks alrededor de {tool}: si no, rompen el bloque ``` del comando
        "es": "🛠 **Modo dev** — {tool} listo para copiar:",
        "en": "🛠 **Dev mode** — copy-ready {tool}:",
        "pt": "🛠 **Modo dev** — {tool} pronto para copiar:",
    },
    "dev_on_wget": {
        "es": "🛠 **Modo dev: wget**\nTras cada subida te mando un `wget` copiable.",
        "en": "🛠 **Dev mode: wget**\nAfter each upload you'll get a copyable `wget`.",
        "pt": "🛠 **Modo dev: wget**\nApós cada envio você recebe um `wget` copiável.",
    },
    "dev_on_curl": {
        "es": "🛠 **Modo dev: curl**\nTras cada subida te mando un `curl` copiable.",
        "en": "🛠 **Dev mode: curl**\nAfter each upload you'll get a copyable `curl`.",
        "pt": "🛠 **Modo dev: curl**\nApós cada envio você recebe um `curl` copiável.",
    },
    "dev_off": {
        "es": "🛠 **Modo dev OFF**",
        "en": "🛠 **Dev mode OFF**",
        "pt": "🛠 **Modo dev OFF**",
    },
    "dev_pick": {
        "es": "🛠 **Modo dev** — elige la herramienta (o apágalo):",
        "en": "🛠 **Dev mode** — pick a tool (or turn off):",
        "pt": "🛠 **Modo dev** — escolha a ferramenta (ou desligue):",
    },
    "dev_current": {
        "es": "Actual: **{state}**",
        "en": "Current: **{state}**",
        "pt": "Atual: **{state}**",
    },
    "settings": {
        "es": (
            "⚙️ **Tu configuración**\n\n"
            "Idioma: **{lang_label}**\n"
            "API key: {api_key}\n"
            "Caducidad preferida: {expire}\n"
            "Modo dev: {dev}\n\n"
            "{limits}"
            "\n`/apikey` · `/expire` · `/dev` · `/lang` · `/me`"
        ),
        "en": (
            "⚙️ **Your settings**\n\n"
            "Language: **{lang_label}**\n"
            "API key: {api_key}\n"
            "Preferred expiry: {expire}\n"
            "Dev mode: {dev}\n\n"
            "{limits}"
            "\n`/apikey` · `/expire` · `/dev` · `/lang` · `/me`"
        ),
        "pt": (
            "⚙️ **Suas configurações**\n\n"
            "Idioma: **{lang_label}**\n"
            "API key: {api_key}\n"
            "Validade preferida: {expire}\n"
            "Modo dev: {dev}\n\n"
            "{limits}"
            "\n`/apikey` · `/expire` · `/dev` · `/lang` · `/me`"
        ),
    },
    "expire_default": {
        "es": "(plan por defecto)",
        "en": "(plan default)",
        "pt": "(padrão do plano)",
    },
    "expire_days": {
        "es": "**{n}** día(s)",
        "en": "**{n}** day(s)",
        "pt": "**{n}** dia(s)",
    },
    "dev_state_off": {
        "es": "**OFF**",
        "en": "**OFF**",
        "pt": "**OFF**",
    },
    "dev_state_tool": {
        "es": "**ON** (`{tool}`)",
        "en": "**ON** (`{tool}`)",
        "pt": "**ON** (`{tool}`)",
    },
    "limits_block": {
        "es": (
            "· Plan DripFiles: **{tier}**\n"
            "· Máx. tamaño: **{max_size}**\n"
            "· Caducidad plan: **{expire_days:.0f}** día(s)\n"
            "{want_expire}"
        ),
        "en": (
            "· DripFiles plan: **{tier}**\n"
            "· Max size: **{max_size}**\n"
            "· Plan expiry: **{expire_days:.0f}** day(s)\n"
            "{want_expire}"
        ),
        "pt": (
            "· Plano DripFiles: **{tier}**\n"
            "· Tamanho máx.: **{max_size}**\n"
            "· Validade do plano: **{expire_days:.0f}** dia(s)\n"
            "{want_expire}"
        ),
    },
    "want_expire": {
        "es": "· Caducidad que pediremos: **{days:.0f}** día(s)\n",
        "en": "· Expiry we will request: **{days:.0f}** day(s)\n",
        "pt": "· Validade que pediremos: **{days:.0f}** dia(s)\n",
    },
    "limits_error": {
        "es": "· ⚠️ No pude leer límites: {err}\n",
        "en": "· ⚠️ Could not read limits: {err}\n",
        "pt": "· ⚠️ Não consegui ler limites: {err}\n",
    },
    "no_api_key": {
        "es": "(sin API key → plan free)",
        "en": "(no API key → free plan)",
        "pt": "(sem API key → plano free)",
    },
    "downloading": {
        "es": "⬇️ Descargando · `{filename}`",
        "en": "⬇️ Downloading · `{filename}`",
        "pt": "⬇️ Baixando · `{filename}`",
    },
    "uploading": {
        "es": "💧 Subiendo a **DripFiles** · `{filename}`",
        "en": "💧 Uploading to **DripFiles** · `{filename}`",
        "pt": "💧 Enviando ao **DripFiles** · `{filename}`",
    },
    "uploading_prep": {
        "es": "💧 Subiendo a **DripFiles** · `{filename}`\nPreparando...",
        "en": "💧 Uploading to **DripFiles** · `{filename}`\nPreparing...",
        "pt": "💧 Enviando ao **DripFiles** · `{filename}`\nPreparando...",
    },
    "zip_active": {
        "es": (
            "📦 **Modo ZIP activo**\n\n"
            "Mándame archivos a lo bestia.\n"
            "Cuando acabes: **✅ Listo** o `/done`\n"
            "Límite: **{limit}** · timeout {timeout} min.\n\n"
            "_{n} archivos · {size}_"
        ),
        "en": (
            "📦 **ZIP mode active**\n\n"
            "Send me files freely.\n"
            "When done: **✅ Done** or `/done`\n"
            "Limit: **{limit}** · timeout {timeout} min.\n\n"
            "_{n} file(s) · {size}_"
        ),
        "pt": (
            "📦 **Modo ZIP ativo**\n\n"
            "Envie arquivos à vontade.\n"
            "Quando terminar: **✅ Pronto** ou `/done`\n"
            "Limite: **{limit}** · timeout {timeout} min.\n\n"
            "_{n} arquivo(s) · {size}_"
        ),
    },
    "zip_status_footer": {
        "es": "\n\nManda más archivos, **✅ Listo** o `/done` · `/cancel` para abortar.",
        "en": "\n\nSend more files, **✅ Done** or `/done` · `/cancel` to abort.",
        "pt": "\n\nEnvie mais arquivos, **✅ Pronto** ou `/done` · `/cancel` para abortar.",
    },
    "zip_already": {
        "es": (
            "📦 Ya tienes un modo ZIP activo con **{n}** archivo(s) "
            "({size}).\nSigue mandando, o usa /done / /cancel."
        ),
        "en": (
            "📦 You already have an active ZIP session with **{n}** file(s) "
            "({size}).\nKeep sending, or use /done / /cancel."
        ),
        "pt": (
            "📦 Você já tem um modo ZIP ativo com **{n}** arquivo(s) "
            "({size}).\nContinue enviando, ou use /done / /cancel."
        ),
    },
    "zip_none": {
        "es": "No hay ninguna sesión /zip activa.",
        "en": "No active /zip session.",
        "pt": "Nenhuma sessão /zip ativa.",
    },
    "zip_none_done": {
        "es": "No hay sesión /zip activa. Usa `/zip` para empezar.",
        "en": "No active /zip session. Use `/zip` to start.",
        "pt": "Nenhuma sessão /zip ativa. Use `/zip` para começar.",
    },
    "zip_cancelled": {
        "es": "❌ Sesión ZIP cancelada. Archivos temporales borrados.",
        "en": "❌ ZIP session cancelled. Temp files deleted.",
        "pt": "❌ Sessão ZIP cancelada. Arquivos temporários apagados.",
    },
    "zip_expired": {
        "es": "⏱ La sesión /zip expiró. Usa `/zip` de nuevo.",
        "en": "⏱ ZIP session expired. Use `/zip` again.",
        "pt": "⏱ Sessão /zip expirou. Use `/zip` de novo.",
    },
    "zip_expired_idle": {
        "es": "⏱ Sesión ZIP expirada por inactividad ({m} min).",
        "en": "⏱ ZIP session expired due to inactivity ({m} min).",
        "pt": "⏱ Sessão ZIP expirada por inatividade ({m} min).",
    },
    "zip_empty": {
        "es": "No hay archivos en el zip. Manda alguno o /cancel.",
        "en": "No files in the zip yet. Send some or /cancel.",
        "pt": "Nenhum arquivo no zip. Envie algum ou /cancel.",
    },
    "zip_busy": {
        "es": "⏳ Ya estoy empaquetando este zip…",
        "en": "⏳ Already packing this zip…",
        "pt": "⏳ Já estou empacotando este zip…",
    },
    "zip_packing": {
        "es": "🗜️ Empaquetando **{n}** archivo(s)…",
        "en": "🗜️ Packing **{n}** file(s)…",
        "pt": "🗜️ Empacotando **{n}** arquivo(s)…",
    },
    "zip_ready": {
        "es": "🗜️ Zip listo · `{name}` ({size})\nPreparando subida…",
        "en": "🗜️ Zip ready · `{name}` ({size})\nPreparing upload…",
        "pt": "🗜️ Zip pronto · `{name}` ({size})\nPreparando envio…",
    },
    "zip_closed": {
        "es": "✅ Sesión ZIP cerrada → `{name}`",
        "en": "✅ ZIP session closed → `{name}`",
        "pt": "✅ Sessão ZIP fechada → `{name}`",
    },
    "zip_add": {
        "es": "⬇️ Añadiendo al zip · `{name}`…",
        "en": "⬇️ Adding to zip · `{name}`…",
        "pt": "⬇️ Adicionando ao zip · `{name}`…",
    },
    "zip_added": {
        "es": (
            "✅ **{n}.** `{name}` ({size})\n"
            "Total: **{n}** archivo(s) · {total}"
        ),
        "en": (
            "✅ **{n}.** `{name}` ({size})\n"
            "Total: **{n}** file(s) · {total}"
        ),
        "pt": (
            "✅ **{n}.** `{name}` ({size})\n"
            "Total: **{n}** arquivo(s) · {total}"
        ),
    },
    "zip_too_big": {
        "es": (
            "❌ Con este archivo el zip superaría tu límite "
            "({limit}).\nActual: {current} + ~{extra}.\n"
            "Usa /done, /cancel o `/apikey`."
        ),
        "en": (
            "❌ This file would push the zip over your limit "
            "({limit}).\nCurrent: {current} + ~{extra}.\n"
            "Use /done, /cancel or `/apikey`."
        ),
        "pt": (
            "❌ Com este arquivo o zip ultrapassaria seu limite "
            "({limit}).\nAtual: {current} + ~{extra}.\n"
            "Use /done, /cancel ou `/apikey`."
        ),
    },
    "zip_too_big_short": {
        "es": "❌ Con este archivo el zip superaría el límite ({limit}).",
        "en": "❌ This file would exceed the limit ({limit}).",
        "pt": "❌ Com este arquivo o zip ultrapassaria o limite ({limit}).",
    },
    "err_file_too_big": {
        "es": (
            "el archivo pesa {size} y supera tu límite ({limit}). "
            "Con API key de pago / Telegram Premium puedes subir más."
        ),
        "en": (
            "file is {size} and exceeds your limit ({limit}). "
            "A paid API key / Telegram Premium allows larger files."
        ),
        "pt": (
            "o arquivo tem {size} e supera seu limite ({limit}). "
            "Com API key paga / Telegram Premium você pode enviar mais."
        ),
    },
    "err_empty": {
        "es": "el archivo está vacío",
        "en": "file is empty",
        "pt": "o arquivo está vazio",
    },
    "err_generic": {
        "es": "❌ Error: {err}",
        "en": "❌ Error: {err}",
        "pt": "❌ Erro: {err}",
    },
    "err_drip": {
        "es": "❌ DripFiles: {err}",
        "en": "❌ DripFiles: {err}",
        "pt": "❌ DripFiles: {err}",
    },
    "err_download": {
        "es": "❌ Error al descargar: {err}",
        "en": "❌ Download error: {err}",
        "pt": "❌ Erro ao baixar: {err}",
    },
    "err_reup": {
        "es": "❌ No pude resubir (¿archivo borrado de Telegram?): {err}",
        "en": "❌ Could not re-upload (file removed from Telegram?): {err}",
        "pt": "❌ Não consegui reenviar (arquivo apagado do Telegram?): {err}",
    },
    "reup_start": {
        "es": "🔄 Resubiendo · `{name}`…",
        "en": "🔄 Re-uploading · `{name}`…",
        "pt": "🔄 Reenviando · `{name}`…",
    },
    "reup_progress": {
        "es": "🔄 Resubiendo zip ({i}/{n})\n⬇️ `{name}`…",
        "en": "🔄 Re-uploading zip ({i}/{n})\n⬇️ `{name}`…",
        "pt": "🔄 Reenviando zip ({i}/{n})\n⬇️ `{name}`…",
    },
    "reup_gone": {
        "es": "Ya no puedo resubir este envío (caducó el índice).",
        "en": "Can't re-upload this one anymore (index expired).",
        "pt": "Não posso mais reenviar este (índice expirou).",
    },
    "reup_not_yours": {
        "es": "Este botón no es tuyo.",
        "en": "This button isn't yours.",
        "pt": "Este botão não é seu.",
    },
    "reup_answer": {
        "es": "Resubiendo…",
        "en": "Re-uploading…",
        "pt": "Reenviando…",
    },
    "packing_answer": {
        "es": "Empaquetando…",
        "en": "Packing…",
        "pt": "Empacotando…",
    },
    "apikey_help": {
        "es": (
            "🔑 **API key de DripFiles**\n\n"
            "Actual: {key}\n\n"
            "Uso:\n"
            "• `/apikey TU_API_KEY` — guardar y validar\n"
            "• `/apikey clear` — borrar y usar plan free\n\n"
            "La key se crea en [dripfiles.com](https://dripfiles.com)."
        ),
        "en": (
            "🔑 **DripFiles API key**\n\n"
            "Current: {key}\n\n"
            "Usage:\n"
            "• `/apikey YOUR_API_KEY` — save & validate\n"
            "• `/apikey clear` — remove and use free plan\n\n"
            "Create a key at [dripfiles.com](https://dripfiles.com)."
        ),
        "pt": (
            "🔑 **API key do DripFiles**\n\n"
            "Atual: {key}\n\n"
            "Uso:\n"
            "• `/apikey SUA_API_KEY` — salvar e validar\n"
            "• `/apikey clear` — remover e usar plano free\n\n"
            "Crie a key em [dripfiles.com](https://dripfiles.com)."
        ),
    },
    "apikey_cleared": {
        "es": "✅ API key eliminada. Usarás el plan **free** (~2 GB / ~2 días).",
        "en": "✅ API key removed. You'll use the **free** plan (~2 GB / ~2 days).",
        "pt": "✅ API key removida. Você usará o plano **free** (~2 GB / ~2 dias).",
    },
    "apikey_validating": {
        "es": "🔎 Validando API key…",
        "en": "🔎 Validating API key…",
        "pt": "🔎 Validando API key…",
    },
    "apikey_ok": {
        "es": (
            "✅ **API key guardada**\n\n"
            "· Plan: **{tier}**\n"
            "· Máx.: **{max_size}**\n"
            "· Caducidad plan: **{expire_days:.0f}** día(s)\n"
            "· Key: {key}\n\n"
            "Opcional: `/expire 7` para pedir 7 días en cada subida.\n"
            "(Se intentó borrar el mensaje con la key en claro.)"
        ),
        "en": (
            "✅ **API key saved**\n\n"
            "· Plan: **{tier}**\n"
            "· Max: **{max_size}**\n"
            "· Plan expiry: **{expire_days:.0f}** day(s)\n"
            "· Key: {key}\n\n"
            "Optional: `/expire 7` to request 7-day links.\n"
            "(Tried to delete the message containing the plain key.)"
        ),
        "pt": (
            "✅ **API key salva**\n\n"
            "· Plano: **{tier}**\n"
            "· Máx.: **{max_size}**\n"
            "· Validade do plano: **{expire_days:.0f}** dia(s)\n"
            "· Key: {key}\n\n"
            "Opcional: `/expire 7` para pedir 7 dias em cada envio.\n"
            "(Tentei apagar a mensagem com a key em texto.)"
        ),
    },
    "apikey_bad": {
        "es": "❌ No se pudo validar la key: {err}",
        "en": "❌ Could not validate key: {err}",
        "pt": "❌ Não foi possível validar a key: {err}",
    },
    "failover_auth_note": {
        "es": "⚠️ Tu API key no es válida → usando plan **free** (failover).\n",
        "en": "⚠️ Your API key is invalid → using **free** plan (failover).\n",
        "pt": "⚠️ Sua API key é inválida → usando plano **free** (failover).\n",
    },
    "failover_me_note": {
        "es": "⚠️ No pude verificar tu API key → usando plan **free** por ahora.\n",
        "en": "⚠️ Could not verify your API key → using **free** plan for now.\n",
        "pt": "⚠️ Não consegui verificar sua API key → usando plano **free** por agora.\n",
    },
    "failover_retry_free": {
        "es": "⚠️ API key rechazada. Reintentando con plan **free** · `{filename}`…",
        "en": "⚠️ API key rejected. Retrying with **free** plan · `{filename}`…",
        "pt": "⚠️ API key rejeitada. Tentando de novo com plano **free** · `{filename}`…",
    },
    "failover_too_big": {
        "es": (
            "API key inválida y el archivo supera el free "
            "({limit}). Actualiza la key con `/apikey`."
        ),
        "en": (
            "API key invalid and file exceeds free limit "
            "({limit}). Update the key with `/apikey`."
        ),
        "pt": (
            "API key inválida e o arquivo supera o free "
            "({limit}). Atualize a key com `/apikey`."
        ),
    },
    "failover_success_note": {
        "es": "⚠️ Subido con plan **free** (tu API key falló). Revisa `/apikey`.",
        "en": "⚠️ Uploaded on **free** plan (your API key failed). Check `/apikey`.",
        "pt": "⚠️ Enviado no plano **free** (sua API key falhou). Veja `/apikey`.",
    },
    "expire_help": {
        "es": (
            "⏱ **Caducidad preferida** (solo con API key de pago)\n\n"
            "Actual: {cur}\n\n"
            "Ejemplos:\n"
            "• `/expire 7` — 7 días\n"
            "• `/expire 30` — 30 días\n"
            "• `/expire clear` — usar la del plan\n\n"
            "El plan free fuerza ~2 días aunque lo cambies."
        ),
        "en": (
            "⏱ **Preferred expiry** (paid API key only)\n\n"
            "Current: {cur}\n\n"
            "Examples:\n"
            "• `/expire 7` — 7 days\n"
            "• `/expire 30` — 30 days\n"
            "• `/expire clear` — use plan default\n\n"
            "The free plan always forces ~2 days."
        ),
        "pt": (
            "⏱ **Validade preferida** (somente com API key paga)\n\n"
            "Atual: {cur}\n\n"
            "Exemplos:\n"
            "• `/expire 7` — 7 dias\n"
            "• `/expire 30` — 30 dias\n"
            "• `/expire clear` — usar a do plano\n\n"
            "O plano free força ~2 dias mesmo se mudar."
        ),
    },
    "expire_cleared": {
        "es": "✅ Caducidad preferida borrada (plan por defecto).",
        "en": "✅ Preferred expiry cleared (plan default).",
        "pt": "✅ Validade preferida removida (padrão do plano).",
    },
    "expire_bad_num": {
        "es": "❌ Usa un número de días, p. ej. `/expire 7`.",
        "en": "❌ Use a number of days, e.g. `/expire 7`.",
        "pt": "❌ Use um número de dias, ex. `/expire 7`.",
    },
    "expire_range": {
        "es": "❌ Días entre 1 y 3650.",
        "en": "❌ Days must be between 1 and 3650.",
        "pt": "❌ Dias entre 1 e 3650.",
    },
    "expire_set": {
        "es": "✅ Caducidad preferida: **{days}** día(s).{note}",
        "en": "✅ Preferred expiry: **{days}** day(s).{note}",
        "pt": "✅ Validade preferida: **{days}** dia(s).{note}",
    },
    "expire_no_key_note": {
        "es": "\n\n⚠️ No tienes API key: el free sigue en ~2 días. Añade una con `/apikey`.",
        "en": "\n\n⚠️ No API key: free stays ~2 days. Add one with `/apikey`.",
        "pt": "\n\n⚠️ Sem API key: o free continua ~2 dias. Adicione com `/apikey`.",
    },
    "me_loading": {
        "es": "🔎 Consultando DripFiles…",
        "en": "🔎 Querying DripFiles…",
        "pt": "🔎 Consultando DripFiles…",
    },
    "me_ok": {
        "es": (
            "💧 **Cuenta DripFiles** ({mode})\n\n"
            "· Tier/plan: **{tier}**\n"
            "· Máx. tamaño: **{max_size}**\n"
            "· Máx. archivos: **{max_files}**\n"
            "· Caducidad por defecto: **{expire_days:.1f}** día(s)\n"
            "· Chunk: {chunk}\n\n"
            "API key: {key}"
        ),
        "en": (
            "💧 **DripFiles account** ({mode})\n\n"
            "· Tier/plan: **{tier}**\n"
            "· Max size: **{max_size}**\n"
            "· Max files: **{max_files}**\n"
            "· Default expiry: **{expire_days:.1f}** day(s)\n"
            "· Chunk: {chunk}\n\n"
            "API key: {key}"
        ),
        "pt": (
            "💧 **Conta DripFiles** ({mode})\n\n"
            "· Tier/plano: **{tier}**\n"
            "· Tamanho máx.: **{max_size}**\n"
            "· Máx. arquivos: **{max_files}**\n"
            "· Validade padrão: **{expire_days:.1f}** dia(s)\n"
            "· Chunk: {chunk}\n\n"
            "API key: {key}"
        ),
    },
    "me_mode_key": {
        "es": "API key",
        "en": "API key",
        "pt": "API key",
    },
    "me_mode_free": {
        "es": "free (sin key)",
        "en": "free (no key)",
        "pt": "free (sem key)",
    },
    "file_too_big_result": {
        "es": "❌ El archivo pesa {size} y supera tu límite ({limit}).",
        "en": "❌ File is {size} and exceeds your limit ({limit}).",
        "pt": "❌ O arquivo tem {size} e supera seu limite ({limit}).",
    },
    "zip_too_big_result": {
        "es": "❌ El zip pesa {size} y supera tu límite ({limit}).",
        "en": "❌ Zip is {size} and exceeds your limit ({limit}).",
        "pt": "❌ O zip tem {size} e supera seu limite ({limit}).",
    },
}


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    lang = lang.lower().strip()
    if lang in LANGS:
        return lang
    return DEFAULT_LANG


def t(lang: str | None, msg_id: str, **kwargs: Any) -> str:
    """Traduce `msg_id`. No uses kwargs llamados `lang` (primer arg).

    El segundo parámetro se llama `msg_id` (no `key`) para poder pasar
    `key=...` en plantillas como la de `/me` y `/apikey`.
    """
    lang = normalize_lang(lang)
    block = STRINGS.get(msg_id) or {}
    text = block.get(lang) or block.get(DEFAULT_LANG) or msg_id
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
