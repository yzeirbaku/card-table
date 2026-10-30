---
name: deploy
description: Deploy the card-table backend to the live Oracle Cloud VM. Use when the user says "deploy", "deploy card-table", "ship it", "push to prod", "redeploy", or similar. Pulls origin/main on the VM over SSH, rebuilds the Docker image, restarts the container and Caddy, and checks the public endpoint. The frontend (Cloudflare Pages) deploys itself on every push to main.
---

# Deploy card-table to production

- **Backend:** Docker on the shared Oracle Cloud Always-Free VM (with net-tracker
  and gold-price-tracker), behind the shared Caddy, at
  `https://yzeir-cards.duckdns.org`.
- **Frontend:** Cloudflare Pages project `card-table` at
  `https://card-table-e61.pages.dev` (`card-table.pages.dev` was taken). Builds
  from `main`, root `frontend`, output `.`, build command
  `echo "window.BACKEND_URL = 'https://yzeir-cards.duckdns.org';" > config.js`.
  Every push to `main` redeploys it; nothing to do here.

**A backend deploy ends every live game** (rooms are in memory). Ask before
deploying and never during a game night. Accounts, sign-ins and stats are in
`data/cards.db` on the VM and survive deploys.

## VM layout

```
~/apps/card-table/
├── repo/                       # this repo, cloned via deploy key (ssh alias github-cards)
│   └── backend/Dockerfile      # VM-local, untracked: python:3.12-slim, uvicorn --workers 1 --proxy-headers
├── data/
│   ├── cards.db                # accounts, sessions, finished games (SQLite; outside repo/, never in git)
│   └── backups/                # nightly copies, last 14 kept
├── docker-compose.yml          # backend only (container card-table-backend), joins external network apps_web
└── .env                        # CORS_ORIGIN_REGEX='https://([a-z0-9-]+\.)?card-table-e61\.pages\.dev'
```

### The database (one-time setup, before the first deploy with accounts)

The compose file mounts `data/` as a plain folder (not a named volume, which
`docker compose down -v` or a prune would delete) and points the app at it:

```yaml
services:
  backend:
    volumes:
      - ./data:/data
    environment:
      - DB_PATH=/data/cards.db
```

```bash
mkdir -p ~/apps/card-table/data/backups
sudo apt-get install -y sqlite3   # for the backup job
crontab -e   # add:
# 30 4 * * * sqlite3 ~/apps/card-table/data/cards.db ".backup '$HOME/apps/card-table/data/backups/cards-$(date +\%F).db'" && find ~/apps/card-table/data/backups -name 'cards-*.db' -mtime +14 -delete
```

The container runs as root, so `cards.db` is root-owned; the backup job reads
it fine. The app creates the tables and applies new migrations on startup.

**Forgotten password** (there's no email):
`sudo docker exec -it card-table-backend python -m app.accounts reset-password <username>`.
It signs that account out on every phone.

Caddy lives in `~/apps/net-tracker/` (root-owned Caddyfile, edit with sudo):
`yzeir-cards.duckdns.org { reverse_proxy card-table-backend:8000; encode gzip }`.
VM deploy key: `~/.ssh/github_card_table`, registered at
https://github.com/yzeirbaku/card-table/settings/keys.

## Procedure

1. **Pre-flight:** the code must be committed and pushed (`git log origin/main..HEAD`
   empty). The VM deploys origin/main, not local commits.
2. **Read** `.claude/skills/deploy/deploy.env.local` (gitignored): `SSH_HOST`,
   `SSH_USER`, `SSH_KEY`, `REMOTE_PATH`, `HEALTH_URL`. If missing, stop and ask.
   Use the key path as written; don't `source` the file in Git Bash (backslashes
   get eaten).
3. **Confirm** with the user (live games will end), then run:

   ```bash
   ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" \
     "cd $REMOTE_PATH/repo && git pull && cd .. && sudo docker compose up -d --build 2>&1 | tail -20 && sudo docker compose -f ~/apps/net-tracker/docker-compose.yml restart caddy"
   ```

   The Caddy restart is needed so it re-resolves the recreated container (see the
   sibling repos' deploy skills). It blips the other two apps for a few seconds.
4. **Verify:** `curl -sS "$HEALTH_URL"` returns the games list (JSON with
   `murlan`), `curl -sS https://yzeir-cards.duckdns.org/stats/nobody` returns a
   404 JSON (`No such player`, so the database opened), and `https://yzeir-net.duckdns.org/` and
   `https://yzeir-gold.duckdns.org/` still return 200.
5. **On failure:** `ssh ... "sudo docker logs card-table-backend --tail 60"`.

## Notes

- Changing the Pages address: update `.env` on the VM, then
  `sudo docker compose up -d --force-recreate backend`.
- Changing the backend host: update the Pages build command and `connect-src`
  in `frontend/_headers`.
- Memory: the VM has 954 MB shared by three backends and Caddy; card-table uses
  about 40 MB. Check `free -h` and `sudo docker stats --no-stream` if unsure.
