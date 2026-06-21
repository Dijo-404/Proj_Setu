# LAN HTTPS Guide

Phone cameras require HTTPS unless the site is opened as `localhost`. For staff phones on the factory LAN, run a local reverse proxy in front of FastAPI.

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

## Certificate

Use a locally trusted certificate tool such as `mkcert`, then install the local root CA on staff phones.

The deployment should remain LAN-only unless the client explicitly asks for remote access.

