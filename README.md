# Discord Auction Gateway

FastAPI + PostgreSQL backend for a Discord bot built on the **Interactions Endpoint** (HTTP webhooks, no gateway websocket).
The bot never needs to be "online" like a regular bot: Discord sends every slash command to `POST /interactions`
on your server, and the server must reply within 3 seconds.

## Commands

| Command | Who | What it does |
|---|---|---|
| `/add-item name [description]` | Admin | List a new item |
| `/bid-item` | Everyone | Pick an item from a dropdown and join its queue |
| `/cancel-bid` | Everyone | Pick one of your own bids to cancel |
| `/delete-item` | Admin | Unlist an item (its bids are removed too) |
| `/status` | Everyone | All items and their bid queues, including items with no bids |
| `/delete-bid` | Admin | Pick an item, then pick which bidder to remove from its queue |

"Admin" = a member with the **Manage Server** or **Administrator** permission.
Discord dropdowns hold at most 25 options, so longer lists are split into pages of 25 with
**◀ Prev / Next ▶** buttons under the dropdown. Every dropdown also has a **🔍 Search** button that opens a
popup to filter the list by name (case-insensitive); **✖ Clear** resets the filter. This applies to every
dropdown, including the bidder list in `/delete-bid`.

---

## 1. Discord Developer Portal setup

1. Go to <https://discord.com/developers/applications> → **New Application** → give it a name → Create.
2. On **General Information**, copy:
   - **Application ID** → `DISCORD_APPLICATION_ID`
   - **Public Key** → `DISCORD_PUBLIC_KEY`
3. **Bot** → **Reset Token** → copy the token → `DISCORD_BOT_TOKEN`.
   The token is shown only once. Keep it safe and never commit it.
   It is only used to register slash commands; the app never logs in as a bot.
   Privileged Gateway Intents are not needed.
4. **Server ID** (optional, for `DISCORD_GUILD_ID`): in Discord, enable
   *User Settings → Advanced → Developer Mode*, then right-click the server name → **Copy Server ID**.
5. **Invite the bot**: under **Installation**, make sure **Guild Install** is checked and the default install
   scopes include `applications.commands` and `bot`. Then use the Install Link, or build the URL yourself:
   ```
   https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=applications.commands+bot
   ```
   A URL without `&scope=...` will not work.

Fill in the **Interactions Endpoint URL** only after the server is running and reachable over HTTPS (step 3.7).

---

## 2. Running locally (development)

1. **Database**: `docker compose up -d` (Postgres on `localhost:5432`, user/password `postgres`),
   or use an existing Postgres and create a `discord_auction` database.
   Tables are created automatically on startup (`schema.sql`).
2. **Env**: `copy .env.example .env` and fill in the values from step 1.
   Set `DISCORD_GUILD_ID` so the commands show up in your server immediately.
3. **Install** (Windows):
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Register commands**: `python -m scripts.register_commands`
5. **Run**: `uvicorn app.main:app --reload --port 8000`
6. **Expose it to the internet** (Discord requires public HTTPS):
   `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`.
7. Set the **Interactions Endpoint URL** in the Developer Portal to `https://<tunnel-url>/interactions` and Save.

Free tunnel URLs change every time they restart, so this is for testing only.

---

## 3. Production deployment (Ubuntu VPS)

The example below uses Ubuntu 22.04/24.04, Python 3.12, PostgreSQL, systemd, and Nginx + Let's Encrypt.
You need a VPS with a public IP and a domain/subdomain (e.g. `auction.yourdomain.com`)
whose **A** record points to the VPS.

Pick a VPS region close to Discord's servers (e.g. Singapore or US). Discord cancels any interaction
that isn't answered within 3 seconds.

### 3.1 Install packages

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv postgresql nginx certbot python3-certbot-nginx git
```

If `python3.12` isn't available in your Ubuntu repo, add the `deadsnakes` PPA or run it in Docker.

### 3.2 Prepare the database

```bash
sudo -u postgres psql
```
```sql
CREATE USER auction WITH PASSWORD 'change_to_a_strong_password';
CREATE DATABASE discord_auction OWNER auction;
\q
```

Postgres only needs to listen on `localhost` (the default). Never expose port 5432 to the internet.

> If you use `docker-compose.yml` in production, **change** `POSTGRES_PASSWORD` and set
> `ports` to `"127.0.0.1:5432:5432"` so the database isn't publicly reachable.

### 3.3 Upload the code and install dependencies

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin auction
sudo mkdir -p /opt/discord-auction
sudo chown auction:auction /opt/discord-auction

# clone the repo (or upload via scp/rsync, without .venv and .env)
sudo -u auction git clone <repo-url> /opt/discord-auction
cd /opt/discord-auction

sudo -u auction python3.12 -m venv .venv
sudo -u auction .venv/bin/pip install -r requirements.txt
```

### 3.4 Fill in `.env`

```bash
sudo -u auction cp .env.example .env
sudo -u auction nano .env
sudo chmod 600 .env
```

```env
DISCORD_APPLICATION_ID=123456789012345678
DISCORD_PUBLIC_KEY=abcdef...
DISCORD_BOT_TOKEN=MTIz...
DISCORD_GUILD_ID=
DATABASE_URL=postgresql://auction:change_to_a_strong_password@localhost:5432/discord_auction
```

- Leave `DISCORD_GUILD_ID` empty to register the commands **globally** (in every server the bot is invited to;
  it can take up to 1 hour to propagate).
- Set `DISCORD_GUILD_ID` if the bot is for a single server; commands appear immediately.

Then register the commands:

```bash
sudo -u auction .venv/bin/python -m scripts.register_commands
```

Re-run this whenever `DEFINITIONS` in `app/commands.py` changes.

### 3.5 Run it as a service (systemd)

Create `/etc/systemd/system/discord-auction.service`:

```ini
[Unit]
Description=Discord Auction Gateway
After=network.target postgresql.service

[Service]
User=auction
Group=auction
WorkingDirectory=/opt/discord-auction
ExecStart=/opt/discord-auction/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-auction
sudo systemctl status discord-auction
curl http://127.0.0.1:8000/health     # must return {"status":"ok"}
```

The app only listens on `127.0.0.1`; outside traffic comes in through Nginx. All state lives in Postgres,
so running more than one worker is safe.

### 3.6 Nginx + HTTPS

Create `/etc/nginx/sites-available/discord-auction`:

```nginx
server {
    listen 80;
    server_name auction.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/discord-auction /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d auction.yourdomain.com   # installs SSL + auto-renewal

sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Check from outside: `curl https://auction.yourdomain.com/health` must return `{"status":"ok"}`.
If you get HTML from another app instead, the domain is routed to the wrong upstream (see Troubleshooting).

**Alternative without a domain/open ports:** use a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
with a *named tunnel* (not a quick tunnel) pointing to `http://localhost:8000`, and skip the Nginx/certbot part.

If the domain is behind Cloudflare, turn off Bot Fight Mode / challenges for this hostname (or add a
*Skip* rule for `/interactions`), otherwise Discord's requests may be blocked.

### 3.7 Connect it to Discord

1. Developer Portal → your application → **General Information**.
2. Set **Interactions Endpoint URL** to `https://auction.yourdomain.com/interactions` → **Save Changes**.
3. Discord sends a signed PING and a request with a fake signature. Saving only succeeds if the server replies
   with PONG and rejects the bad signature (401). If it fails, see Troubleshooting.
4. Make sure the bot has been invited (step 1.5), then type `/` in a channel. The bot's commands will show up.

Done. Try `/add-item` (as an admin), then `/bid-item` and `/status`.

---

## Item seeder

To add many items at once (instead of running `/add-item` one by one), fill in `scripts/data/items.json`:

```json
[
  {"name": "Item Name", "description": "Optional description"},
  {"name": "Another Item"}
]
```

then run:

```
python -m scripts.seed_items                    # uses scripts/data/items.json
python -m scripts.seed_items path/other.json    # or another file
```

Items whose name already exists (case-insensitive) are skipped, so it is safe to re-run.
Names can be at most 100 characters.

---

## 4. Operations

**View logs**
```bash
sudo journalctl -u discord-auction -f
```

**Update the code**
```bash
cd /opt/discord-auction
sudo -u auction git pull
sudo -u auction .venv/bin/pip install -r requirements.txt
sudo -u auction .venv/bin/python -m scripts.register_commands   # if commands changed
sudo systemctl restart discord-auction
```

**Back up the database**
```bash
sudo -u postgres pg_dump discord_auction > backup_$(date +%F).sql
# restore: sudo -u postgres psql discord_auction < backup_YYYY-MM-DD.sql
```

**Health check**: `GET /health` checks the database connection. You can point an uptime monitor at it.

**Security**
- Never commit `.env` (it's already in `.gitignore`). If the token leaks, **Reset Token** under Bot right away.
- `/interactions` verifies Discord's Ed25519 signature, so forged requests are rejected with 401.
- Don't expose Postgres to the internet; use a strong password.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Saving the Interactions Endpoint URL fails ("could not be verified") | The server isn't reachable over HTTPS, `DISCORD_PUBLIC_KEY` is wrong (or from another application), or the service is down. Check `curl https://domain/health` and `journalctl`. |
| `/health` returns HTML from another app, or `POST /interactions` returns 405 | The domain is routed to a different app. Fix the Nginx `server_name`/`proxy_pass`, tunnel route, or hosting panel so it points to `127.0.0.1:8000`. |
| Commands don't show up when typing `/` | `register_commands` hasn't been run, the bot wasn't invited with the `applications.commands` scope, or global commands are still propagating (wait up to 1 hour / use `DISCORD_GUILD_ID`). Also try reloading Discord (Ctrl+R). |
| Members can't see admin commands | Intended: admin commands use `default_member_permissions` Manage Server. You can change this under *Server Settings → Integrations*. |
| "The application did not respond" | The server took longer than 3 seconds or errored. Check the logs and the database connection. |
| App fails to start: `Environment variable ... is not set` | `.env` is missing from the `WorkingDirectory`, or the variable is empty. |
| `register_commands` fails with 401 | `DISCORD_BOT_TOKEN` is wrong or has been reset. |

---

## Project layout

```
app/main.py        /interactions endpoint (signature check + routing) and /health
app/commands.py    slash command definitions + command & dropdown handlers
app/db.py          PostgreSQL queries (asyncpg)
app/discord.py     Interactions API helpers (signature, responses, followups)
app/config.py      reads configuration from .env
schema.sql         items & bids tables (queue = bid id order)
scripts/register_commands.py   registers slash commands with Discord
scripts/seed_items.py          seeds items from scripts/data/items.json
```
