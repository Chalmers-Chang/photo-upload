import json
import random
import re
import shutil
import time
import uuid
from pathlib import Path

import redis

from config import appsetting
from config import msg
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


def slug_from_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:64]


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
        raise ValueError(msg.need_project_name)
    auto = not slug
    if auto:
        slug = slug_from_name(name) or make_slug()
    if not valid_slug(slug):
        raise ValueError(msg.bad_slug)
    conn = r()
    if conn.exists(f"slug:{slug}"):
        if auto:
            slug = f"{slug[:53]}-{make_slug()}" if slug_from_name(name) else make_slug()
        else:
            raise ValueError(msg.slug_taken)
        if conn.exists(f"slug:{slug}"):
            raise ValueError(msg.slug_taken)
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


def wipe_tickets(project_id):
    conn = r()
    serials = conn.zrange(f"tickets:{project_id}", 0, -1)
    devices = conn.smembers(f"devices:{project_id}")
    pipe = conn.pipeline()
    for serial in serials:
        pipe.delete(f"ticket:{project_id}:{serial}")
    pipe.delete(f"tickets:{project_id}")
    pipe.delete(f"ticket_seq:{project_id}")
    for device_id in devices:
        pipe.delete(f"device_photos:{project_id}:{device_id}")
    pipe.delete(f"devices:{project_id}")
    pipe.execute()


def wipe_photos(project_id, delete_files):
    conn = r()
    ids = conn.zrange(f"photos:{project_id}", 0, -1)
    pipe = conn.pipeline()
    for pid in ids:
        pipe.delete(f"photo:{project_id}:{pid}")
    pipe.delete(f"photos:{project_id}")
    pipe.delete(f"slideshow:{project_id}")
    pipe.execute()
    wipe_tickets(project_id)
    if delete_files:
        d = photo_dir(project_id)
        if d.exists():
            shutil.rmtree(d)


def delete_project(project_id, delete_files):
    p = get_project(project_id)
    if not p:
        raise ValueError(msg.project_missing)
    wipe_photos(project_id, delete_files=delete_files)
    conn = r()
    conn.delete(f"project:{project_id}")
    conn.delete(f"slug:{p['slug']}")
    conn.srem("projects", project_id)
    return p


def add_ticket(project_id, photo_id, device_id):
    now = time.time()
    ttl = ttl_seconds()
    conn = r()
    serial = f"{conn.incr(f'ticket_seq:{project_id}'):06d}"
    conn.set(
        f"ticket:{project_id}:{serial}",
        json.dumps(
            {"photo_id": photo_id, "device_id": device_id, "ts": now},
            ensure_ascii=False,
        ),
        ex=ttl,
    )
    conn.zadd(f"tickets:{project_id}", {serial: now})
    conn.sadd(f"devices:{project_id}", device_id)
    conn.zadd(f"device_photos:{project_id}:{device_id}", {photo_id: now})
    count = conn.zcard(f"device_photos:{project_id}:{device_id}")
    return serial, int(count)


def add_photo(project_id, photo_id, caption, device_id):
    now = time.time()
    conn = r()
    conn.set(
        f"photo:{project_id}:{photo_id}",
        json.dumps(
            {"caption": caption, "ts": now, "device_id": device_id},
            ensure_ascii=False,
        ),
        ex=ttl_seconds(),
    )
    conn.zadd(f"photos:{project_id}", {photo_id: now})
    return add_ticket(project_id, photo_id, device_id)


def nickname_of(device_id):
    if not device_id:
        return ""
    return r().get(f"device_name:{device_id}") or ""


def set_nickname(device_id, name):
    name = (name or "").strip()
    if not name or len(name) > 20:
        raise ValueError(msg.nickname_bad)
    r().set(f"device_name:{device_id}", name)
    return name


def load_photo(project_id, photo_id):
    raw = r().get(f"photo:{project_id}:{photo_id}")
    if not raw:
        return None
    data = json.loads(raw)
    data["id"] = photo_id
    data["url"] = photo_url(project_id, photo_id)
    data["nickname"] = nickname_of(data.get("device_id"))
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
            "nickname": item.get("nickname") or "",
            "server_now": float(server_now),
            "show_until": float(show_until),
            "interval": int(float(interval)),
        }
    return _empty_state(time.time(), appsetting.slideshow_interval)


def _ticket(project_id, serial):
    raw = r().get(f"ticket:{project_id}:{serial}")
    if not raw:
        return None
    data = json.loads(raw)
    data["serial"] = serial
    return data


def drop_ticket(project_id, serial):
    t = _ticket(project_id, serial)
    conn = r()
    conn.zrem(f"tickets:{project_id}", serial)
    conn.delete(f"ticket:{project_id}:{serial}")
    if t:
        conn.zrem(f"device_photos:{project_id}:{t.get('device_id')}", t.get("photo_id"))


def device_photos(project_id, device_id, exclude=None):
    ids = r().zrange(f"device_photos:{project_id}:{device_id}", 0, -1)
    out = []
    for pid in ids:
        if exclude and pid == exclude:
            continue
        item = load_photo(project_id, pid)
        if item is None:
            r().zrem(f"device_photos:{project_id}:{device_id}", pid)
            continue
        out.append({"id": item["id"], "url": item["url"]})
    return out


def sphere_photos(project_id, limit):
    items = sweep_expired(project_id)
    if not items:
        return []
    if len(items) > limit:
        items = random.sample(items, limit)
    photos = [{"id": i["id"], "url": i["url"]} for i in items]
    i = 0
    while len(photos) < limit:
        src = photos[i % len(photos)]
        photos.append(src)
        i += 1
    return photos


def draw_lottery(project_id):
    serials = list(r().zrange(f"tickets:{project_id}", 0, -1))
    random.shuffle(serials)
    winner = None
    for serial in serials:
        t = _ticket(project_id, serial)
        if not t:
            drop_ticket(project_id, serial)
            continue
        photo = load_photo(project_id, t["photo_id"])
        if photo is None:
            drop_ticket(project_id, serial)
            continue
        winner = (t, photo)
        break
    if not winner:
        raise ValueError(msg.lottery_empty)
    t, photo = winner
    others = device_photos(project_id, t["device_id"], exclude=photo["id"])
    return {
        "serial": t["serial"],
        "seconds": appsetting.lottery_seconds,
        "winner": {
            "id": photo["id"],
            "url": photo["url"],
            "caption": photo.get("caption") or "",
            "nickname": photo.get("nickname") or "",
            "upload_count": len(others) + 1,
        },
        "device_photos": others,
        "sphere": sphere_photos(project_id, appsetting.lottery_sphere_max),
    }
