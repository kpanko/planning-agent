# Deploying to Fly.io

## Prerequisites: Google Cloud OAuth client

1. Go to [Google Cloud Console](https://console.cloud.google.com) →
   APIs & Services → Credentials.
2. Create (or reuse) an **OAuth 2.0 Client ID** of type *Web application*.
3. Under **Authorized redirect URIs** add:
   ```
   https://<your-app>.fly.dev/oauth/callback
   http://localhost:8080/oauth/callback   ← for local dev
   ```
4. Note your **Client ID** and **Client Secret**.

## One-time Fly setup

```bash
# Install flyctl: https://fly.io/docs/flyctl/install/
flyctl auth login
flyctl launch --no-deploy   # creates the app, skips first deploy

# Create persistent volume for app data
flyctl volumes create planning_agent_data --size 1 --region ord

# Set secrets
flyctl secrets set \
  GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com" \
  GOOGLE_CLIENT_SECRET="your-client-secret" \
  ALLOWED_GOOGLE_EMAIL="you@gmail.com" \
  WEB_SECRET="$(openssl rand -hex 32)" \
  BASE_URL="https://your-app.fly.dev" \
  TODOIST_API_KEY="your-todoist-key" \
  ANTHROPIC_API_KEY="your-anthropic-key"
```

## Deploy

```bash
flyctl deploy
```

## How auth works

- Visiting the app redirects to `/login` if not signed in.
- Clicking **Sign in with Google** starts an OAuth2 flow.
- Only the `ALLOWED_GOOGLE_EMAIL` account is admitted; all others get 403.
- On first login the Google OAuth token is saved to the data volume and
  used automatically for Google Calendar — no separate Calendar setup needed.
- Session cookies are signed with `WEB_SECRET` and expire after 30 days.

## Local development

```bash
# Set env vars in .env (already git-ignored)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ALLOWED_GOOGLE_EMAIL=you@gmail.com
WEB_SECRET=dev-secret
BASE_URL=http://localhost:8080

uv run planning-agent-web
```

## Debug mode

Debug mode shows tool calls, tool results, and exceptions in the
chat UI. It is controlled per-session via the **Debug** toggle
button in the web interface.

The `DEBUG_MODE` environment variable sets the default state for
new sessions. When unset (the default on fly.io), debug starts
off and the user can toggle it on. There is no need to add
`DEBUG_MODE` as a fly.io secret — the UI toggle is sufficient
for on-demand debugging.

To default debug on for all sessions (e.g. during development):

```bash
# Local
DEBUG_MODE=1 uv run planning-agent-web

# Fly.io (optional, not recommended for normal use)
flyctl secrets set DEBUG_MODE=1
```

## Regions

The `fly.toml` defaults to `ord` (Chicago). Change `primary_region` to
the closest option: `sea`, `lax`, `iad`, `ewr`, `lhr`, `fra`, etc.

## Cost

With `min_machines_running = 0` the machine stops when idle and restarts
on the next request. You pay only for active compute time, which is very
low for a personal tool with infrequent use. Fly.io no longer has a free
tier, but a shared-cpu-1x machine costs roughly $0.0000022/second when
running.
