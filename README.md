# photo-upload

Guests upload photos. Multiple screens play the same slideshow. Admins run a lottery. The supported way to run it is Docker Compose: nginx + gunicorn + Redis.

## Requirements

- Docker and Compose, **linux/arm64** images (Apple Silicon)
- A photo directory the Docker VM can mount (files stay on the host, not in the image)
- Port **8000** free
- Pull access to `ghcr.io/chalmers-chang/photo-upload` and `photo-upload-nginx`
- Redis is started by Compose (`redis-data` named volume)

Flask alone does **not** serve `/photos/` — nginx does. Use Compose for local debugging too.

## Start

From `docker-compose/`:

```bash
# optional: photo path and image tag
# echo 'HOST_PHOTO_DIR=/your/photo/path' >> .env

docker compose pull
docker compose up -d
```

Open `http://localhost:8000`. Admin is `/admin`.

Pushes to `main` or `feature/**` build `linux/arm64` on the self-hosted Mac runner (native, no QEMU), then `compose pull && compose up -d`.

## What to change

**Almost always, when moving machines**

| Item | Where | Notes |
| --- | --- | --- |
| Photo directory | Compose `HOST_PHOTO_DIR` (or `.env`) | Default `/Volumes/OWC Envoy Pro FX/photo-upload`. Bind the same path on **app** and **nginx**. |
| App logs | `$HOST_PHOTO_DIR/logs` | One file per project per day. Deploy also symlinks `/opt/app/photo-upload/logs`. Older than 30 days are deleted. |
| Admin login | `ADMIN_USERNAME` / `ADMIN_PASSWORD` on `app` | Defaults live in `config/admin.py`. Change them. |
| `SECRET_KEY` | `app` environment | Default in `config/appsetting.py`. Signs cookies. |

**Site-wide defaults** (Compose `app.environment`, or `config/appsetting.py`). New projects copy the slideshow/lottery values; each project can override them in Admin → Settings.

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Leave as-is in Compose |
| `PHOTO_DIR` | `/data/photos` | Path **inside** the container |
| `LOG_DIR` | `/logs` | Per-project daily logs inside the container (`$HOST_PHOTO_DIR/logs` on the host) |
| `LOG_KEEP_DAYS` | `30` | Delete log files older than this many days |
| `SLIDESHOW_INTERVAL` | `8` | Seconds each slideshow photo stays |
| `SLIDESHOW_FADE` | `0.8` | Slideshow crossfade seconds (0 = hard cut) |
| `SLIDESHOW_MODE` | `wall` | Default slideshow layout: `wall` (name + caption) or `full` (photo only) |
| `SLIDESHOW_QUEUE_MAX` | `100` | Slideshow queue cap |
| `SLIDESHOW_PER_DEVICE` | `5` | Newest photos per device when over the cap |
| `RECORD_TTL_DAYS` | `20` | Redis record TTL (files are not auto-deleted) |
| `MAX_UPLOAD_MB` | `20` | Per-photo cap; batch is 5 photos; nginx `client_max_body_size` is 110m |
| `JPEG_MAX_EDGE` | `2560` | Longest edge after upload |
| `GUNICORN_WORKERS` | `2` | |
| `GUNICORN_TIMEOUT` | `120` | Keep high for large uploads |
| `LOTTERY_SECONDS` | `10` | Sphere spin duration |
| `LOTTERY_SPHERE_MAX` | `60` | Photos on the lottery sphere |
| `LOTTERY_CHANCE_MAX` | `10` | Lottery tickets per device (newest photos) |

Look-and-feel (`PJT_FADE`, `BKG_FADE`, button colors, glass padding, `LOTTERY_PAD_CM`) is also in `config/appsetting.py`.

**Copy and dependencies**

- Guest-facing strings: `config/msg.py`
- Python packages: `cd python && uv add …` / `uv lock`; commit `pyproject.toml` and `uv.lock`
- nginx: `docker-compose/nginx.conf` (baked into the nginx image)

## Use

1. `/admin` — create a project (slug optional)
2. Guests: `/p/<slug>/` → upload or slideshow
3. Per project, optional covers: `pjt-mark` (2cm home mark), `pjt-desktop`, `pjt-mobile`, `bkg-desktop`, `bkg-mobile`, `lot-desktop`, `lot-mobile`
4. Lottery is admin-only: `/p/<slug>/lottery`
5. Project settings (slideshow mode, interval, queue, lottery spin) are on the project card, bottom left

## Layout

```
config/           env defaults, admin login, copy
web/              Flask app, Redis store, templates
web/static/favicon.png   site icon (replace this PNG to swap)
art/              source art (favicon zip, etc.)
python/           uv lockfile only (app code is not here)
docker-compose/   Dockerfile, compose, nginx.conf
```

Request flow: browser → nginx `:8000` → `/photos/*` from disk, everything else to gunicorn. Redis holds projects, photo records, tickets, and the slideshow playhead. JPEG files live on the host bind.

## Architecture notes

The split is small and enough: **routes in `web/app.py`**, **Redis + files in `web/store.py`**, **resize in `web/images.py`**, **defaults in `config/`**. Do not wrap `appsetting` in a class for speed — import-time constants are already cheap.

`/p/<slug>/api/slideshow` only advances the Redis playhead (Lua). The queue is rebuilt on upload, photo drop, and settings save — not on every TV poll.

Uploads are the other cost: Pillow on the gunicorn worker. `JPEG_MAX_EDGE` 2560 and quality 80 (no `optimize=True`) are the right tradeoff. Photos themselves are served by nginx, not Flask.

Tickets and the slideshow playhead belong in Redis (Lua already advances the playhead atomically). Do not put the JPEGs in Redis or in the image.
