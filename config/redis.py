import os

# Redis URL (hostname redis inside compose)
url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
