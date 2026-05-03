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
5. Go to **OAuth consent screen** and set the publishing status to
   **In production** (not "Testing"). In Testing mode, refresh
   tokens expire after 7 days and calendar access will break.

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

### Continuous deployment (automatic)

Merging to `main` triggers CI, which runs tests and then deploys
automatically via the `deploy` job in `.github/workflows/ci.yml`.

Requires a `FLY_API_TOKEN` GitHub Actions secret. One-time setup:

```bash
# Create a deploy token scoped to the app
flyctl tokens create deploy -a planning-agent
```

Add the output token as a repository secret named `FLY_API_TOKEN`
under Settings → Secrets and variables → Actions.

### Manual deploy

```bash
flyctl deploy --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)
```

After deploy, verify the new version is running:

```bash
curl -s https://planning-agent.fly.dev/health
# → {"status":"ok","version":"abc1234"}
```

## How auth works

- Visiting the app redirects to `/login` if not signed in.
- Clicking **Sign in with Google** starts an OAuth2 flow with PKCE.
- Only the `ALLOWED_GOOGLE_EMAIL` account is admitted; all others
  get 403.
- On first login the Google OAuth tokens (access + refresh) are
  saved to the data volume. Google Calendar reads use these
  automatically.
- Access tokens are refreshed transparently and persisted back to
  disk after each successful calendar API call.
- If the refresh token itself expires or is revoked, a reconnect
  banner appears in the chat UI linking to `/login/google`.
- Session cookies are signed with `WEB_SECRET` and expire after
  30 days.

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

## Nightly replan (scheduled Machine)

The nightly replan job runs as a `POST /internal/nightly-replan`
endpoint on the web Machine, triggered by a separate Fly scheduled
Machine that curls it with a bearer token. This avoids needing a
second copy of the `/data` volume (Fly volumes attach to one Machine
at a time).

### 1. Set the shared bearer token

```bash
flyctl secrets set \
  NIGHTLY_REPLAN_TOKEN="$(openssl rand -hex 32)" \
  -a planning-agent
```

When `NIGHTLY_REPLAN_TOKEN` is unset the endpoint returns 503, so
nothing fires by accident.

### 2. Manual ad-hoc trigger

```bash
flyctl secrets list -a planning-agent  # confirm NIGHTLY_REPLAN_TOKEN set

# Dry-run (requires the token value — copy from a secure store):
curl -X POST \
  -H "Authorization: Bearer <token>" \
  "https://planning-agent.fly.dev/internal/nightly-replan?dry_run=true"

# Real run:
curl -X POST \
  -H "Authorization: Bearer <token>" \
  https://planning-agent.fly.dev/internal/nightly-replan
```

### 3. Scheduled Machine

Run a tiny Alpine Machine on a schedule (no volume, no app code).
The Machine inherits app-level Fly secrets automatically — **never
pass the token via `--env`**, which stores it in plaintext in the
Machine config (visible via `flyctl machine status -d`).

```bash
flyctl machine run \
  --schedule daily \
  --region ord \
  --name nightly-replan-cron \
  --env "NIGHTLY_URL=https://planning-agent.fly.dev/internal/nightly-replan" \
  alpine/curl:latest \
  -a planning-agent \
  -- sh -c 'curl -fsS -X POST -H "Authorization: Bearer $NIGHTLY_REPLAN_TOKEN" "$NIGHTLY_URL"'
```

`--schedule daily` runs once every 24 hours (Fly picks the time).
Use `--schedule hourly` to test, then update.

After creating the Machine, verify no secrets leaked into its env:

```bash
flyctl machine status -d <machine-id> -a planning-agent
# Confirm: no NIGHTLY_REPLAN_TOKEN in the env block.
# The token is injected at runtime from Fly secrets.
```

Verify the schedule:

```bash
flyctl machine list -a planning-agent
flyctl logs -a planning-agent -i <machine-id>
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
