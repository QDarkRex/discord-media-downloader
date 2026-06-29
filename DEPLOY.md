# Deploying

Runs as its own Docker container (`tiktokbot`), isolated from anything else on the host.
Replace `USER@SERVER` below with your own SSH target.

## 1. Build the deploy bundle (in this folder)

```bash
tar -czf ../tiktok-deploy.tar.gz \
  --exclude='.git' --exclude='__pycache__' --exclude='.env' \
  --exclude='data' --exclude='*.db' --exclude='.venv' \
  .
```

The bundle is code + Dockerfile + compose.yml + configs.yml + .env.example.
It contains **no secrets** (`.env` is excluded).

## 2. Copy it to the server

```bash
scp ../tiktok-deploy.tar.gz USER@SERVER:~/
```

## 3. Unpack into its own directory

```bash
ssh USER@SERVER
mkdir -p ~/tiktokbot
tar -xzf ~/tiktok-deploy.tar.gz -C ~/tiktokbot
cd ~/tiktokbot
```

## 4. Create the `.env` on the server

```bash
cp .env.example .env
nano .env          # paste BOT_TOKEN; optionally set TIKTOK_COOKIES / IG_COOKIES
chmod 600 .env
```

Optional Instagram cookies (only needed for private posts / stories / if you hit
rate-limits): `scp data/cookies.txt USER@SERVER:~/tiktokbot/data/ig_cookies.txt`
then set `IG_COOKIES=/bot/data/ig_cookies.txt` in `.env`.

## 5. Build & start

```bash
docker compose up -d --build      # first build ~1-2 min
docker compose logs -f            # look for "is online" and "synced N slash command(s)"
```

## Updating later

- **Settings only** (`configs.yml`): `docker compose restart`
- **Code changes / new dependency** (e.g. adding the Instagram feature): re-unpack, then
  `docker compose up -d --build`

## Health check

```bash
docker compose ps                 # tiktokbot should be "running"
```
