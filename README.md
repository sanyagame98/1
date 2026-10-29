# DEMO Wallet — Telegram bot (Render)

**This is a demo bot, not @send.** Every new user receives 100 **DEMO USDT** (non-monetary, non-withdrawable virtual units). Supports wallet views, single checks, multi-checks, links, check redemption, cancellation, and refund of unclaimed units.

## Deployment

Render web service: https://dashboard.render.com/web/srv-dbhno4etlv9c7398jro0

Render PostgreSQL: https://dashboard.render.com/d/dpg-dbhnn2flk1mc73d7mqtg-a

This repository branch is deployed automatically with Render. It has no .env file.

### Required settings — Render > Web Service > Environment

1. `BOT_TOKEN`: **reissued** BotFather token (do not send it in chat; revoke any previously exposed token).
2. `DATABASE_URL`: **Internal Database URL** from Render Postgres > Connect. **Keep the entire value secret.**
3. `ADMIN_IDS`: numeric Telegram user ID, e.g. `123456789`, for future admin functionality.
4. `WEBHOOK_SECRET`: configured automatically by the deployment.
5. `PYTHON_VERSION`: set automatically.

After adding BOT_TOKEN and DATABASE_URL, Render automatically redeploys. The webhook is registered on startup. Set the bot's inline mode in BotFather if needed.

Health check at `/healthz` returns a `configured` field. `configured: false` means Telegram functionality is not yet ready. Do not send money to this bot: DEMO balances have no real-world value.

Free Render PostgreSQL will expire after 30 days (created 2026-10-29), and the free web service can sleep when idle. Back up data or move to durable hosting to preserve balances.

## Limitations

This is an independently designed demo interface; exact @send branding, fonts, and transaction processing are not reproduced. Admin control is not enabled without an owner Telegram ID. No real USDT deposits, blockchain operations or withdrawals.
