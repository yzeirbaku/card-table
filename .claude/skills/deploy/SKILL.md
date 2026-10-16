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
deploying and never during a game night.

## VM layout

```
~/apps/card-table/
├── repo/                       # this repo, cloned via deploy key (ssh alias github-cards)
│   └── backend/Dockerfile      # VM-local, untracked: python:3.12-slim, uvicorn --workers 1 --proxy-headers
├── docker-compose.yml          # backend only (container card-table-backend), joins external network apps_web
└── .env                        # CORS_ORIGIN_REGEX='https://([a-z0-9-]+\.)?card-table-e61\.pages\.dev'
```

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
   `murlan`), and `https://yzeir-net.duckdns.org/` and
   `https://yzeir-gold.duckdns.org/` still return 200.
5. **On failure:** `ssh ... "sudo docker logs card-table-backend --tail 60"`.

## Notes

- Changing the Pages address: update `.env` on the VM, then
  `sudo docker compose up -d --force-recreate backend`.
- Changing the backend host: update the Pages build command and `connect-src`
  in `frontend/_headers`.
- Memory: the VM has 954 MB shared by three backends and Caddy; card-table uses
  about 40 MB. Check `free -h` and `sudo docker stats --no-stream` if unsure.
