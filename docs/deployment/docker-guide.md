# Docker deployment guide — Setu QR Tally Bridge

Deploy Setu on **one Windows LAN server** with Docker. The app keeps **SQLite**
(file-backed, single-writer) and sits behind a **Caddy** reverse proxy that
terminates HTTPS on the LAN.

> **Single replica only.** SQLite is a single-writer database, so exactly one
> `app` container is supported. Do **not** add a second `app` replica or a
> `deploy: replicas:` setting — concurrent writers will corrupt the file.
> Scaling horizontally would require switching to PostgreSQL, which is **out of
> scope** for this deployment. The SRS target is ~10 users on one machine.

## Prerequisites

- **Docker Desktop for Windows** (with the Compose v2 CLI — `docker compose`,
  not the legacy `docker-compose`). Verify: `docker --version` and
  `docker compose version`.
- This repository checked out on the server.
- A LAN hostname for the server (the example Caddyfile uses `setu.local`).

## 1. Create the environment file

```sh
cp .env.example .env
```

Edit `.env` and set a **strong** `APP_SECRET_KEY` (sessions are signed with it).
On the server you can generate one with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Also review `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` and change
the default admin password before first run.

You do **not** need to set `SESSION_COOKIE_SECURE` in `.env` — `docker-compose.yml`
forces `SESSION_COOKIE_SECURE=true` for the `app` service, because all real
traffic arrives over Caddy HTTPS and the session cookie must be marked `Secure`.
(`DATABASE_URL` can stay at the default `sqlite:///./data/setu.db`; it resolves
to `/app/data/setu.db` inside the container, which is the persisted volume.)

## 2. Configure Caddy

Copy the example and point it at the app container:

```sh
cp deployment/caddy/Caddyfile.example deployment/caddy/Caddyfile
```

Edit `deployment/caddy/Caddyfile` so the reverse-proxy target is the **app
service on the compose network** (not `127.0.0.1`):

```caddy
setu.local {
    reverse_proxy app:8000
}
```

Replace `setu.local` with your server's LAN hostname if different. Caddy will
provision a certificate (internal/self-signed for `.local` or ACME if the name
is publicly resolvable). The `caddy` service mounts this file read-only at
`/etc/caddy/Caddyfile`.

## 3. Build and start

```sh
docker compose build
docker compose up -d
```

Check it is healthy:

```sh
docker compose ps            # app should be "healthy" after ~10-40s
curl -k https://setu.local/health      # -> {"status":"ok"}
```

The app also binds to `127.0.0.1:8000` on the host for direct (non-Caddy)
debugging: `curl http://127.0.0.1:8000/health`.

Log in with the bootstrap admin credentials from `.env`.

## Where the data lives

The SQLite database and its WAL/SHM sidecar files live on the named Docker
volume **`setu-data`**, mounted at **`/app/data`** inside the container
(`/app/data/setu.db`, plus `setu.db-wal` / `setu.db-shm` while running).

Because it is a named volume — not a bind mount or an image layer — the data
**persists across** `docker compose down` and `docker compose up` and across
image rebuilds. It is removed only if you explicitly delete the volume
(`docker volume rm setu-data` or `docker compose down -v`).

Inspect it:

```sh
docker volume inspect setu-data
docker compose exec app ls -la /app/data
```

## Backup and restore

Three options, in order of convenience:

1. **In-app Maintenance page** — the built-in backup/export on the Maintenance
   page still works exactly as before; it runs inside the container against the
   same `/app/data` volume.

2. **`docker cp`** — copy the DB file out of the running container:

   ```sh
   docker compose cp app:/app/data/setu.db ./setu-backup.db
   ```

   For a consistent copy, prefer doing this while the app is stopped, or grab
   the `-wal`/`-shm` files too.

3. **Volume tarball** (good for full, offline backups):

   ```sh
   # Backup the whole volume to a tar.gz in the current directory
   docker run --rm -v setu-data:/data -v "$PWD:/backup" alpine \
     tar czf /backup/setu-data-backup.tar.gz -C /data .

   # Restore into the volume (stop the app first: docker compose stop app)
   docker run --rm -v setu-data:/data -v "$PWD:/backup" alpine \
     sh -c "cd /data && tar xzf /backup/setu-data-backup.tar.gz"
   ```

   On Windows PowerShell, use `${PWD}` instead of `$PWD`.

## Common operations

```sh
docker compose logs -f app        # follow app logs
docker compose restart app        # restart the app
docker compose pull && docker compose up -d   # update Caddy image
docker compose build app && docker compose up -d app   # rebuild app after code change
docker compose down               # stop (data volume is kept)
docker compose down -v            # stop AND delete volumes (DESTROYS the DB)
```

## Notes

- **Non-root:** the image runs as the unprivileged `setu` user (uid 10001).
- **Health:** the container `HEALTHCHECK` probes `GET /health` with the Python
  stdlib (the slim base image has no `curl`).
- **Secrets/DB never baked in:** `.env`, `data/`, and `*.db*` are excluded via
  `.dockerignore`, so credentials and the database are not part of the image.
