import os

bind = os.environ.get("BIND", "0.0.0.0")
port = int(os.environ.get("PORT", "8000"))
secret_key = os.environ.get("SECRET_KEY", "photo-upload-homelab-secret")

photo_dir = os.environ.get(
    "PHOTO_DIR",
    "/Volumes/OWC Envoy Pro FX/photo-upload",
)
slideshow_interval = int(os.environ.get("SLIDESHOW_INTERVAL", "8"))
record_ttl_days = int(os.environ.get("RECORD_TTL_DAYS", "20"))
max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", "20"))
jpeg_max_edge = int(os.environ.get("JPEG_MAX_EDGE", "2560"))
gunicorn_workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
gunicorn_timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
lottery_seconds = int(os.environ.get("LOTTERY_SECONDS", "7"))
lottery_sphere_max = int(os.environ.get("LOTTERY_SPHERE_MAX", "60"))
