# Telegram Pay Ops

## Real Start Payment Smoke

1. Start local services:
   - `.\run_django.ps1`
   - `.\run_bot.ps1`
2. Open `http://127.0.0.1:8000/studio/pay/` or the CherryX Pay page in the app.
3. Click the `Start` package payment button.
4. Telegram should open `@cherryxconverter_bot` with a `pay_<token>` deep link.
5. Press `Start` in Telegram.
6. Bot should send an official Telegram Stars invoice.
7. Pay the small Start invoice.
8. Expected result:
   - linked web user: package activates immediately;
   - unlinked Telegram user: bot asks for email, creates account, applies payment;
   - admin `/admin/telegram-finance/` shows the intent as `applied`.

## Telegram Finance Admin

Open:

```text
/admin/telegram-finance/
```

Use it for:

- current Stars rate cache and manual sync;
- total Stars paid and CherryX credited;
- `needs_email` / link support queue;
- manual application of a paid Telegram intent to a Django User ID.
- admin-only test simulation for pending claimed intents, without charging Telegram Stars.

## Production Process Safety

The project now has a production-ready Windows harness:

- `scripts/prod/cherryx_process.ps1` keeps one component alive and restarts it after crashes.
- `scripts/prod/cherryx_watchdog.ps1` checks web health and stale heartbeat files.
- `scripts/prod/install_windows_tasks.ps1` installs Windows Scheduled Tasks for web, worker, bot, and watchdog.

Runtime signals:

- Web health: `/health/`
- Bot heartbeat: `data/bot_heartbeat.json`
- Worker heartbeat: `data/worker_heartbeat.json`
- Logs: `logs/prod/*.log`

The wrapper restarts a component when it exits. The watchdog handles the harder case: process is still alive but stuck. It kills stale web/bot/worker processes, then the wrapper task starts them again.

## Windows Production Autostart

Dry-run manually first:

```powershell
$root = "C:\Users\UserJMC\Desktop\Game"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod\cherryx_process.ps1" -Component web -Root "$root" -Bind "127.0.0.1:8000"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod\cherryx_process.ps1" -Component worker -Root "$root"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod\cherryx_process.ps1" -Component bot -Root "$root"
```

Install scheduled tasks from elevated PowerShell:

```powershell
$root = "C:\Users\UserJMC\Desktop\Game"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod\install_windows_tasks.ps1" -Root "$root" -Bind "127.0.0.1:8000"
```

On a real public server we should decide:

- final project path;
- public domain;
- reverse proxy choice;
- whether to keep Windows Scheduled Tasks or switch to NSSM services;
- whether web should use Django `runserver` temporarily or a real WSGI/ASGI server.

Recommended production option on Windows: NSSM service wrappers around the same `cherryx_process.ps1` commands. On Linux: use `systemd` units for `gunicorn`, `manage.py run_worker`, and `python -m src.bot`, with `Restart=always` and a separate timer/watchdog.

To restart all Windows scheduled tasks as one group:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\prod\restart_cherryx_group.ps1"
```

## Linux Production With Gunicorn/Uvicorn

Ready templates are in `deploy/systemd/`.

Recommended default:

- `cherryx-web.service` runs Django through Gunicorn/WSGI.
- `cherryx-bot.service` runs `python -m src.bot`.
- `cherryx-worker.service` runs `manage.py run_worker`.

Important restart behavior:

- bot and worker have `PartOf=cherryx-web.service`;
- when the site is restarted with `systemctl restart cherryx-web.service`, systemd restarts bot and worker too;
- if bot, worker, or web crashes independently, `Restart=always` starts it again after 5 seconds.

Install on the server after adjusting paths/user/domain:

```bash
sudo cp deploy/systemd/cherryx-web.service /etc/systemd/system/
sudo cp deploy/systemd/cherryx-bot.service /etc/systemd/system/
sudo cp deploy/systemd/cherryx-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cherryx-web cherryx-bot cherryx-worker
sudo systemctl start cherryx-web cherryx-bot cherryx-worker
```

Normal deploy restart:

```bash
sudo systemctl restart cherryx-web.service
sudo systemctl status cherryx-web.service cherryx-bot.service cherryx-worker.service --no-pager
```

If the server uses ASGI/Uvicorn instead of Gunicorn, copy `cherryx-web-uvicorn.service` as the web unit or rename it to `cherryx-web.service`. Keep the bot and worker `PartOf=` pointed at the final active web service name.
