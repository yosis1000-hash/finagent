# FinAgent Manual Instance Setup

This application currently runs as a single instance for the Financial Division.
When another division or department adopts it, provision a separate deployment
with its own database and mailbox instead of adding multi-tenant logic.

## Required per-instance configuration

- `GMAIL_ADDRESS`
- `SMTP_FROM`
- `APP_URL`
- `DATABASE_URL`
- `SECRET_KEY`
- `ANTHROPIC_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`

## Provisioning checklist

1. Create a dedicated Gmail mailbox for the adopting unit.
2. Create a new deployment for that unit.
3. Point `DATABASE_URL` to a fresh database for that deployment.
4. Set the mailbox and URL environment variables for that deployment.
5. Start the app once so tables are created and `org_config` is initialized.
6. Log in as the seeded admin user and update organizational settings if needed.

## Notes

- `org_config` is the source of truth for the instance identity shown in the app.
- Differences between units should be expressed through config and environment
  variables, not through forks in application logic.
- The current production mailbox for the Financial Division is
  `boi.finagent@gmail.com`.
