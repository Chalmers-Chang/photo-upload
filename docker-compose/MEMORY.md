# docker-compose

## GOTCHA

- Tagging the app image with a Dockerfile hash and skipping `compose pull` when that tag already exists on the Mac leaves stale app code running. Tag with `GITHUB_SHA` and always `compose pull` before `up -d`.
- Photo files live on the host (`/Volumes/OWC Envoy Pro FX/photo-upload`). Both `app` and `nginx` must bind-mount that path; putting photos only in the image will not work.
- Docker Desktop on the Mac runner does not share `/opt/app`. Bind-mounting `./nginx.conf` from the rsync dest fails with "Mounts denied". Bake nginx.conf into `photo-upload-nginx` instead; do not mount compose files from `/opt`.
- `mkdir -p /opt/photo-upload/logs` fails with Permission denied on the runner. Logs go under `/opt/app/photo-upload/logs` (the rsync dest the runner already owns). Rsync must `--exclude logs/` or `--delete` wipes them. Compose bind is relative `../logs`.

## TASTE

- Baked `photo-upload-nginx` plus the OWC photo bind is enough for `compose up`; confirmed the stack starts on the Mac runner.
- `PHOTO_DIR=/data/photos` inside the container; host path stays in compose (`HOST_PHOTO_DIR` / default OWC volume).
- App logs: container `LOG_DIR=/opt/app/photo-upload/logs`, host bind `../logs` from compose (that folder on the Mac). Files are `<project-id>_yyyyMMdd.log`; the app deletes names older than 30 days. Do not log `/api/slideshow` polls.
- Install Python deps with `uv sync --frozen` from `python/pyproject.toml` + `python/uv.lock`, not a root `requirements.txt`.
