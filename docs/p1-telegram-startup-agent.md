# P1 Telegram Startup Agent

This service sends a daily P1 startup review queue to Telegram.

Default behavior:

- every day at `10:00 Asia/Nicosia`;
- send 30 Europe/UK AI-native startup candidates;
- attach inline `Approve` and `Reject` buttons;
- `Approve` appends to local TSV and, when Google credentials are configured, appends to Google Sheets;
- `Reject` asks for a comment and stores it in feedback memory;
- future scoring includes recent reject comments so the agent avoids similar startups.

## Required Environment

`/opt/p1/.env` on the server must contain:

```sh
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_MESSAGE_THREAD_ID=... # optional forum topic id for p1
P1_STARTUP_DAILY_TIME=10:00
P1_STARTUP_TIMEZONE=Asia/Nicosia
P1_STARTUP_BATCH_SIZE=30
```

For Google Sheets writes:

```sh
P1_STARTUP_GOOGLE_SHEET_ID=...
P1_STARTUP_GOOGLE_SHEET_TAB=P1 Approved Startups
GOOGLE_SA_PATH=/opt/p1/runtime/google-service-account.json
```

Without Google credentials, approvals are still saved locally:

```sh
/opt/p1/out/p1_approved_startups.tsv
```

Reject feedback is saved here:

```sh
/opt/p1/runtime/p1_telegram_startup_agent/reject_feedback.jsonl
```

## Commands

In Telegram:

- `/send_today` sends a batch immediately.
- `/p1_status` shows local approval/feedback counts and Google Sheet config status.

## Manual Run

```sh
P1_TELEGRAM_ENV_FILE=/opt/p1/.env uv run python scripts/p1-telegram-startup-agent.py
```
