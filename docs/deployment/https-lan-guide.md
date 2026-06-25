# LAN HTTPS Guide

Phone cameras usually require HTTPS unless the site is opened as `localhost`. For staff phones on the factory LAN, run a local reverse proxy in front of FastAPI.

## Recommended Shape

```text
Phone browser
  -> https://setu.local
  -> Caddy
  -> http://127.0.0.1:8000
  -> FastAPI
```

## Caddy

Use `deployment/caddy/Caddyfile.example` as the starting point.

Replace:

```text
setu.local
```

with the real LAN hostname.

Keep FastAPI bound to localhost behind the proxy:

```text
start_setu.bat
```

or:

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

## Certificate

Use a locally trusted certificate tool such as `mkcert`, then install the local root CA on staff phones.

The deployment should remain LAN-only unless the client explicitly asks for remote access.

When the app is opened only through HTTPS, set this in `.env` and restart Setu:

```text
SESSION_COOKIE_SECURE=true
```

Leave it `false` while testing over plain `http://127.0.0.1:8000`, otherwise the browser will not send the login cookie over HTTP.
