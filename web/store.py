import json
import re
import shutil
import time
import uuid
from pathlib import Path

import redis

from config import appsetting
from config import redis as redis_config

_slug_re = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_ADVANCE_LUA = """
local state_key = KEYS[1]
local zkey = KEYS[2]
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])

local ids = redis.call('ZRANGE', zkey, 0, -1)
local n = #ids
if n == 0 then
  redis.call('DEL', state_key)
  return {'', tostring(now), tostring(now), tostring(interval), '0'}
end

local index = tonumber(redis.call('HGET', state_key, 'index') or '0')
local show_until = tonumber(redis.call('HGET', state_key, 'show_until') or '0')

if show_until == nil or show_until == 0 then
  index = 0
  show_until = now + interval
elseif now >= show_until then
  local steps = math.floor((now - show_until) / interval) + 1
  index = (index + steps) % n
  show_until = show_until + steps * interval
  if show_until <= now then
    show_until = now + interval
  end
end

if index < 0 or index >= n then
  index = index % n
end

local photo_id = ids[index + 1]
redis.call('HSET', state_key,
  'index', index,
  'photo_id', photo_id,
  'show_until', show_until,
  'interval', interval)
return {photo_id, tostring(now), tostring(show_until), tostring(interval), tostring(n)}
"""

_pool = None
_advance = None


def r():
    global _pool
    if _pool is None:
        _pool = redis.Redis.from_url(redis_config.url, decode_responses=True)
    return _pool


def advance_script():
    global _advance
    if _advance is None:
        _advance = r().register_script(_ADVANCE_LUA)
    return _advance


def ttl_seconds():
    return appsetting.record_ttl_days * 86400


def photo_dir(project_id):
    return Path(appsetting.photo_dir) / project_id


def photo_path(project_id, photo_id):
    return photo_dir(project_id) / f"{photo_id}.jpg"


def photo_url(project_id, photo_id):
    return f"/photos/{project_id}/{photo_id}.jpg"


def valid_slug(slug):
    return bool(slug) and len(slug) <= 64 and _slug_re.match(slug)


def make_slug():
    return uuid.uuid4().hex[:10]


def get_project(project_id):
    data = r().hgetall(f"project:{project_id}")
    if not data:
        return None
    data["id"] = project_id
    return data


def project_by_slug(slug):
    pid = r().get(f"slug:{slug}")
    if not pid:
        return None
    return get_project(pid)


def list_projects():
    ids = sorted(r().smembers("projects"))
    out = []
    for pid in ids:
        p = get_project(pid)
        if not p:
            continue
        p["photo_count"] = r().zcard(f"photos:{pid}")
        out.append(p)
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def create_project(name, slug):
    name = (name or "").strip()
    slug = (slug or "").strip().lower()
    if not name:
        raise ValueError("請輸入專案名稱")
    if not slug:
        slug = make_slug()
    if not valid_slug(slug):
        raise ValueError("slug 只能用小寫英文、數字與連字號")
    conn = r()
    if conn.exists(f"slug:{slug}"):
        raise ValueError("這個 URL slug 已被使用")
    pid = uuid.uuid4().hex
    conn.sadd("projects", pid)
    conn.hset(
        f"project:{pid}",
        mapping={
            "name": name,
            "slug": slug,
            "created_at": str(int(time.time())),
        },
    )
    conn.set(f"slug:{slug}", pid)
    photo_dir(pid).mkdir(parents=True, exist_ok=True)
    return get_project(pid)


def delete_project(project_id, delete_files):
    p = get_project(project_id)
    if not p:
        raise ValueError("專案不存在")
    conn = r()
    ids = conn.zrange(f"photos:{project_id}", 0, -1)
    pipe = conn.pipeline()
    for pid in ids:
        pipe.delete(f"photo:{project_id}:{pid}")
    pipe.delete(f"photos:{project_id}")
    pipe.delete(f"slideshow:{project_id}")
    pipe.delete(f"project:{project_id}")
    pipe.delete(f"slug:{p['slug']}")
    pipe.srem("projects", project_id)
    pipe.execute()
    if delete_files:
        d = photo_dir(project_id)
        if d.exists():
            shutil.rmtree(d)
    return p


def add_photo(project_id, photo_id, caption):
    now = time.time()
    conn = r()
    conn.set(
        f"photo:{project_id}:{photo_id}",
        json.dumps({"caption": caption, "ts": now}, ensure_ascii=False),
        ex=ttl_seconds(),
    )
    conn.zadd(f"photos:{project_id}", {photo_id: now})


def load_photo(project_id, photo_id):
    raw = r().get(f"photo:{project_id}:{photo_id}")
    if not raw:
        return None
    data = json.loads(raw)
    data["id"] = photo_id
    data["url"] = photo_url(project_id, photo_id)
    return data


def drop_photo(project_id, photo_id):
    r().zrem(f"photos:{project_id}", photo_id)
    r().delete(f"photo:{project_id}:{photo_id}")
    photo_path(project_id, photo_id).unlink(missing_ok=True)


def sweep_expired(project_id):
    ids = r().zrange(f"photos:{project_id}", 0, -1)
    kept = []
    for pid in ids:
        item = load_photo(project_id, pid)
        if item is None:
            drop_photo(project_id, pid)
            continue
        kept.append(item)
    return kept


def _empty_state(server_now, interval):
    return {
        "photo_id": None,
        "url": None,
        "caption": "",
        "server_now": float(server_now),
        "show_until": float(server_now),
        "interval": int(interval),
    }


def slideshow_state(project_id):
    for _ in range(8):
        sweep_expired(project_id)
        now = time.time()
        result = advance_script()(
            keys=[f"slideshow:{project_id}", f"photos:{project_id}"],
            args=[now, appsetting.slideshow_interval],
        )
        photo_id, server_now, show_until, interval, n = result
        if not photo_id or n == "0":
            return _empty_state(server_now, interval)
        item = load_photo(project_id, photo_id)
        if item is None:
            drop_photo(project_id, photo_id)
            continue
        return {
            "photo_id": photo_id,
            "url": item["url"],
            "caption": item.get("caption") or "",
            "server_now": float(server_now),
            "show_until": float(show_until),
            "interval": int(float(interval)),
        }
    return _empty_state(time.time(), appsetting.slideshow_interval)
