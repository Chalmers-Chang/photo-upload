import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import appsetting

_NAME = re.compile(r"^(.+)_(\d{8})\.log$")
_SAFE = re.compile(r"[^a-zA-Z0-9-]")
_last_purge = 0.0


def _dir():
    path = Path(appsetting.log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def purge_old():
    global _last_purge
    now = time.monotonic()
    if now - _last_purge < 3600:
        return
    _last_purge = now
    keep = max(1, appsetting.log_keep_days)
    cutoff = datetime.now().date() - timedelta(days=keep)
    try:
        folder = _dir()
    except OSError:
        return
    for path in folder.glob("*.log"):
        m = _NAME.match(path.name)
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(2), "%Y%m%d").date()
        except ValueError:
            continue
        if day < cutoff:
            path.unlink(missing_ok=True)


def write(project_id, line):
    pid = _SAFE.sub("", str(project_id or ""))[:64]
    if not pid:
        return
    try:
        purge_old()
        now = datetime.now()
        dest = _dir() / f"{pid}_{now.strftime('%Y%m%d')}.log"
        with dest.open("a", encoding="utf-8") as f:
            f.write(f"{now.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        return
