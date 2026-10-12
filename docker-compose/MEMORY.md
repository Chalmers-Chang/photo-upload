# docker-compose

## GOTCHA

- Tagging the app image with a Dockerfile hash and skipping `compose pull` when that tag already exists on the Mac leaves stale app code running. Tag with `GITHUB_SHA` and always `compose pull` before `up -d`.
- Building `linux/arm64` on `ubuntu-latest` uses QEMU and is very slow. Build on the self-hosted Mac ARM64 runner instead; do not add `setup-qemu-action`. Pinning the Docker engine version does not fix that.
- `docker/login-action` on the Mac runner fails with `User interaction is not allowed` (osxkeychain). Write `auths` into `$RUNNER_TEMP/docker-config` and set `DOCKER_CONFIG`; same as deploy.
- Photo files live on the host (`/Volumes/OWC Envoy Pro FX/photo-upload`). Both `app` and `nginx` must bind-mount that path; putting photos only in the image will not work.
- Docker Desktop on the Mac runner does not share `/opt/app`. Bind-mounting anything from `/opt/app` (nginx.conf, `../logs`) fails with "Mounts denied". Bake nginx.conf into `photo-upload-nginx`. Logs bind `$HOST_PHOTO_DIR/logs` (OWC, already shared) to `/logs`. Deploy symlinks `/opt/app/photo-upload/logs` → that folder. nginx must `deny` `/photos/logs/`.

## TASTE

- Baked `photo-upload-nginx` plus the OWC photo bind is enough for `compose up`; confirmed the stack starts on the Mac runner.
- `PHOTO_DIR=/data/photos` inside the container; host path stays in compose (`HOST_PHOTO_DIR` / default OWC volume).
- App logs: `LOG_DIR=/logs` in the container, host `$HOST_PHOTO_DIR/logs`. Files are `<project-id>_yyyyMMdd.log`; the app deletes names older than 30 days. Do not log `/api/slideshow` polls.
- Install Python deps with `uv sync --frozen` from `python/pyproject.toml` + `python/uv.lock`, not a root `requirements.txt`.
