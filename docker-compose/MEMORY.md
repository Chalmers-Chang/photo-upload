# docker-compose

## GOTCHA

- Tagging the app image with a Dockerfile hash and skipping `compose pull` when that tag already exists on the Mac leaves stale app code running. Tag with `GITHUB_SHA` and always `compose pull` before `up -d`.
- Photo files live on the host (`/Volumes/OWC Envoy Pro FX/photo-upload`). Both `app` and `nginx` must bind-mount that path; putting photos only in the image will not work.

## TASTE

- Public port 8000 is nginx. It `alias` `/photos/` to the volume and proxies everything else to gunicorn on `app:8000`.
- `PHOTO_DIR=/data/photos` inside the container; host path stays in compose (`HOST_PHOTO_DIR` / default OWC volume).
- Install Python deps with `uv sync --frozen` from `python/pyproject.toml` + `python/uv.lock`, not a root `requirements.txt`.
