import json
import random
import re
import shutil
import time
import uuid
from pathlib import Path

import redis
from werkzeug.security import check_password_hash, generate_password_hash

from config import admin as admin_config
from config import appsetting
from config import msg
from config import redis as redis_config

_slug_re = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_USER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$")
_GUEST_JPG = re.compile(r"^[0-9a-f]{32}\.jpg$")
ROLES = ("admin", "maintainer", "guest")
STAFF_ROLES = ("admin", "maintainer")
VISITED_MAX = 40

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

KUJI_GRADES = ("A", "B", "C", "D", "E")
KUJI_TOTAL_MAX = 999
KUJI_PER_USER_MAX = 50
KUJI_LABEL_MAX = 40

_KUJI_DRAW_LUA = """
local cfg, drawn, used, earned, mine, draws, seq =
  KEYS[1], KEYS[2], KEYS[3], KEYS[4], KEYS[5], KEYS[6], KEYS[7]
local per = tonumber(redis.call('HGET', cfg, 'per_user') or ARGV[4])
local have = tonumber(redis.call('GET', earned) or '0')
local done = tonumber(redis.call('GET', used) or '0')
if done >= math.min(have, per) then
  return {'no_chance'}
end
local grades = {'A', 'B', 'C', 'D', 'E'}
local left = {}
local sum = 0
for i, g in ipairs(grades) do
  local l = tonumber(redis.call('HGET', cfg, g) or '0')
    - tonumber(redis.call('HGET', drawn, g) or '0')
  if l < 0 then l = 0 end
  left[i] = l
  sum = sum + l
end
if sum == 0 then
  return {'sold_out'}
end
local pick = math.floor(tonumber(ARGV[1]) * sum)
if pick >= sum then pick = sum - 1 end
local grade
for i, g in ipairs(grades) do
  if pick < left[i] then
    grade = g
    break
  end
  pick = pick - left[i]
end
redis.call('HINCRBY', drawn, grade, 1)
redis.call('INCR', used)
local id = tostring(redis.call('INCR', seq))
redis.call('HSET', draws, id, cjson.encode({grade = grade, device_id = ARGV[3], ts = tonumber(ARGV[2])}))
redis.call('RPUSH', mine, id)
return {'ok', grade, id}
"""

_KUJI_SAVE_LUA = """
local grades = {'A', 'B', 'C', 'D', 'E'}
for i, g in ipairs(grades) do
  if tonumber(ARGV[i + 1]) < tonumber(redis.call('HGET', KEYS[2], g) or '0') then
    return g
  end
end
redis.call('HSET', KEYS[1], 'per_user', ARGV[1],
  'A', ARGV[2], 'B', ARGV[3], 'C', ARGV[4], 'D', ARGV[5], 'E', ARGV[6])
return ''
"""

DETECT_Q = "detect_q"
DETECT_BUSY = "detect_busy"

_pool = None
_advance = None
_scripts = {}


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


def _script(name, src):
    if name not in _scripts:
        _scripts[name] = r().register_script(src)
    return _scripts[name]


def ttl_seconds():
    return appsetting.record_ttl_days * 86400


def photo_dir(project_id):
    return Path(appsetting.photo_dir) / project_id


def photo_path(project_id, photo_id):
    return photo_dir(project_id) / f"{photo_id}.jpg"


def photo_url(project_id, photo_id):
    return f"/photos/{project_id}/{photo_id}.jpg"


ASSETS = {
    "pjt-mark": "pjt-mark.png",
    "pjt-desktop": "pjt-desktop.jpg",
    "pjt-mobile": "pjt-mobile.jpg",
    "bkg-desktop": "bkg-desktop.jpg",
    "bkg-mobile": "bkg-mobile.jpg",
    "lot-desktop": "lot-desktop.jpg",
    "lot-mobile": "lot-mobile.jpg",
    "kuji-mark": "kuji-mark.png",
    "kuji-ticket": "kuji-ticket.png",
    "kuji-desktop": "kuji-desktop.jpg",
    "kuji-mobile": "kuji-mobile.jpg",
    "kuji-a": "kuji-a.jpg",
    "kuji-b": "kuji-b.jpg",
    "kuji-c": "kuji-c.jpg",
    "kuji-d": "kuji-d.jpg",
    "kuji-e": "kuji-e.jpg",
}


def asset_is_png(kind):
    return ASSETS.get(kind, "").endswith(".png")

_LEGACY = {
    "pjt": "pjt-home.jpg",
    "bkg": "bkg-slideshow.jpg",
}


def asset_path(project_id, kind):
    name = ASSETS.get(kind)
    if not name:
        raise ValueError(msg.bad_asset)
    return photo_dir(project_id) / name


def asset_thumb_path(project_id, kind):
    p = asset_path(project_id, kind)
    return p.with_name(f"{p.stem}-sm.jpg")


def _file_url(project_id, path: Path):
    if not path.is_file():
        return None
    return f"/photos/{project_id}/{path.name}?t={int(path.stat().st_mtime)}"


def asset_url(project_id, kind):
    return _file_url(project_id, asset_path(project_id, kind))


def asset_thumb_url(project_id, kind):
    return _file_url(project_id, asset_thumb_path(project_id, kind)) or asset_url(
        project_id, kind
    )


def attach_assets(project):
    if not project:
        return project
    pid = project["id"]
    for kind in ASSETS:
        key = kind.replace("-", "_")
        project[f"{key}_url"] = asset_url(pid, kind)
        project[f"{key}_thumb_url"] = asset_thumb_url(pid, kind)
    if not project["pjt_mark_url"]:
        project["pjt_mark_url"] = _file_url(pid, photo_dir(pid) / "pjt-mark.jpg")
        project["pjt_mark_thumb_url"] = project["pjt_mark_url"]
    legacy_pjt = _file_url(pid, photo_dir(pid) / _LEGACY["pjt"])
    legacy_bkg = _file_url(pid, photo_dir(pid) / _LEGACY["bkg"])
    project["pjt_desktop_show"] = (
        project["pjt_desktop_url"] or project["pjt_mobile_url"] or legacy_pjt
    )
    project["pjt_mobile_show"] = (
        project["pjt_mobile_url"] or project["pjt_desktop_url"] or legacy_pjt
    )
    project["bkg_desktop_show"] = (
        project["bkg_desktop_url"] or project["bkg_mobile_url"] or legacy_bkg
    )
    project["bkg_mobile_show"] = (
        project["bkg_mobile_url"] or project["bkg_desktop_url"] or legacy_bkg
    )
    project["lot_desktop_show"] = (
        project["lot_desktop_url"] or project["lot_mobile_url"]
    )
    project["lot_mobile_show"] = (
        project["lot_mobile_url"] or project["lot_desktop_url"]
    )
    project["kuji_desktop_show"] = (
        project["kuji_desktop_url"]
        or project["kuji_mobile_url"]
        or project["pjt_desktop_show"]
    )
    project["kuji_mobile_show"] = (
        project["kuji_mobile_url"]
        or project["kuji_desktop_url"]
        or project["pjt_mobile_show"]
    )
    return project


def valid_slug(slug):
    return bool(slug) and len(slug) <= 64 and _slug_re.match(slug)


def make_slug():
    return uuid.uuid4().hex[:10]


def slug_from_name(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:64]


SETTINGS = {
    "slideshow_interval": "slideshow_interval",
    "slideshow_queue_max": "slideshow_queue_max",
    "slideshow_per_device": "slideshow_per_device",
    "slideshow_fade": "slideshow_fade",
    "slideshow_mode": "slideshow_mode",
    "lottery_sphere_max": "lottery_sphere_max",
    "lottery_seconds": "lottery_seconds",
}

SETTING_BOUNDS = {
    "slideshow_interval": (1, 120),
    "slideshow_queue_max": (1, 500),
    "slideshow_per_device": (1, 50),
    "slideshow_fade": (0.0, 3.0),
    "lottery_sphere_max": (1, 200),
    "lottery_seconds": (1, 60),
}

SETTING_ENUMS = {
    "slideshow_mode": ("wall", "full"),
}


def default_settings():
    return {k: getattr(appsetting, k) for k in SETTINGS}


def _parse_setting(k, v):
    allowed = SETTING_ENUMS.get(k)
    if allowed:
        s = str(v or "").strip()
        if s not in allowed:
            raise ValueError(msg.bad_setting)
        return s
    lo, hi = SETTING_BOUNDS[k]
    if isinstance(lo, float):
        n = round(float(v), 1)
    else:
        n = int(v)
    if n < lo or n > hi:
        raise ValueError(msg.bad_setting)
    return n


def settings_of(project_id, raw=None):
    if raw is None:
        raw = r().hgetall(f"project:{project_id}") or {}
    out = default_settings()
    for k in SETTINGS:
        try:
            out[k] = _parse_setting(k, raw[k])
        except (KeyError, TypeError, ValueError):
            pass
    return out


def update_project_settings(project_id, form):
    if not r().exists(f"project:{project_id}"):
        raise ValueError(msg.project_missing)
    mapping = {}
    for k in SETTINGS:
        if k not in form:
            continue
        try:
            n = _parse_setting(k, form.get(k))
        except (TypeError, ValueError):
            raise ValueError(msg.bad_setting)
        mapping[k] = str(n)
    if not mapping:
        raise ValueError(msg.bad_setting)
    r().hset(f"project:{project_id}", mapping=mapping)
    cfgp = settings_of(project_id)
    rebuild_slideshow_queue(project_id, cfgp)
    return cfgp


def get_project(project_id):
    data = r().hgetall(f"project:{project_id}")
    if not data:
        return None
    data["id"] = project_id
    data.update(settings_of(project_id, raw=data))
    return attach_assets(data)


def project_by_slug(slug):
    pid = r().get(f"slug:{slug}")
    if not pid:
        return None
    return get_project(pid)


def list_projects_for_ids(ids):
    out = []
    seen = set()
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        p = get_project(pid)
        if not p:
            continue
        p["photo_count"] = r().zcard(f"photos:{pid}")
        p["kuji"] = kuji_state(pid)
        out.append(p)
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def list_projects():
    return list_projects_for_ids(sorted(r().smembers("projects")))


def projects_by_slugs(slugs):
    out = []
    seen = set()
    for slug in slugs:
        p = project_by_slug(slug)
        if p and p["id"] not in seen:
            seen.add(p["id"])
            out.append(p)
    return out


def parse_visited(cookie):
    slugs = []
    for s in (cookie or "").split(","):
        s = s.strip().lower()
        if valid_slug(s) and s not in slugs:
            slugs.append(s)
        if len(slugs) >= VISITED_MAX:
            break
    return slugs


def create_project(name, slug, owner=None):
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
    mapping = {
        "name": name,
        "slug": slug,
        "created_at": str(int(time.time())),
    }
    mapping.update({k: str(v) for k, v in default_settings().items()})
    conn.hset(f"project:{pid}", mapping=mapping)
    conn.set(f"slug:{slug}", pid)
    photo_dir(pid).mkdir(parents=True, exist_ok=True)
    if owner and not is_root(owner):
        set_user_role(owner, pid, "admin")
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
    pipe.delete(f"lottery_won:{project_id}")
    for device_id in devices:
        pipe.delete(f"device_photos:{project_id}:{device_id}")
        pipe.delete(f"device_chance:{project_id}:{device_id}")
        pipe.delete(f"device_eligible:{project_id}:{device_id}")
        pipe.delete(f"device_pending:{project_id}:{device_id}")
        pipe.delete(f"kuji_earned:{project_id}:{device_id}")
    pipe.execute()
    kuji_reset(project_id)
    conn.delete(f"devices:{project_id}")


def wipe_photos(project_id, delete_files):
    conn = r()
    ids = conn.zrange(f"photos:{project_id}", 0, -1)
    pipe = conn.pipeline()
    for pid in ids:
        pipe.delete(f"photo:{project_id}:{pid}")
    pipe.delete(f"photos:{project_id}")
    pipe.delete(f"slideshow:{project_id}")
    pipe.delete(f"slideshow_q:{project_id}")
    pipe.execute()
    wipe_tickets(project_id)
    if delete_files:
        d = photo_dir(project_id)
        if d.exists():
            shutil.rmtree(d)


def reset_guest_photos(project_id):
    p = get_project(project_id)
    if not p:
        raise ValueError(msg.project_missing)
    wipe_photos(project_id, delete_files=False)
    d = photo_dir(project_id)
    if d.exists():
        for path in d.iterdir():
            if path.is_file() and _GUEST_JPG.match(path.name):
                path.unlink(missing_ok=True)
    return p


def delete_project(project_id, delete_files):
    p = get_project(project_id)
    if not p:
        raise ValueError(msg.project_missing)
    wipe_photos(project_id, delete_files=delete_files)
    conn = r()
    users = conn.smembers(f"project_users:{project_id}")
    pipe = conn.pipeline()
    for name in users:
        pipe.hdel(f"user_projects:{name}", project_id)
    pipe.delete(f"project_users:{project_id}")
    pipe.delete(f"project:{project_id}")
    pipe.delete(f"kuji:{project_id}")
    pipe.delete(f"slug:{p['slug']}")
    pipe.srem("projects", project_id)
    pipe.execute()
    return p


def ensure_root():
    name = (admin_config.username or "").strip()
    if not name:
        return
    try:
        conn = r()
    except redis.exceptions.ConnectionError:
        return
    if conn.exists(f"user:{name}"):
        return
    conn.sadd("users", name)
    conn.hset(
        f"user:{name}",
        mapping={
            "password": generate_password_hash(admin_config.password),
            "is_root": "1",
            "created_at": str(int(time.time())),
        },
    )


def valid_username(name):
    return bool(name) and bool(_USER_RE.match(name))


def get_user(name):
    if not name:
        return None
    data = r().hgetall(f"user:{name}")
    if not data or not data.get("password"):
        return None
    data["name"] = name
    data["is_root"] = data.get("is_root") == "1"
    return data


def authenticate(name, password):
    u = get_user((name or "").strip())
    if not u or not check_password_hash(u["password"], password or ""):
        return None
    return u


def create_user(name, password):
    name = (name or "").strip()
    if not valid_username(name):
        raise ValueError(msg.bad_username)
    if not 4 <= len(password or "") <= 72:
        raise ValueError(msg.bad_password)
    conn = r()
    if conn.exists(f"user:{name}"):
        raise ValueError(msg.username_taken)
    conn.sadd("users", name)
    conn.hset(
        f"user:{name}",
        mapping={
            "password": generate_password_hash(password),
            "is_root": "0",
            "created_at": str(int(time.time())),
        },
    )
    return get_user(name)


def set_password(name, password):
    if not get_user(name):
        raise ValueError(msg.user_missing)
    if not 4 <= len(password or "") <= 72:
        raise ValueError(msg.bad_password)
    r().hset(f"user:{name}", "password", generate_password_hash(password))


def change_password(name, old, new):
    if not authenticate(name, old):
        raise ValueError(msg.wrong_password)
    set_password(name, new)


def delete_user(name):
    u = get_user(name)
    if not u:
        raise ValueError(msg.user_missing)
    if u["is_root"]:
        raise ValueError(msg.cannot_delete_root)
    conn = r()
    pids = conn.hkeys(f"user_projects:{name}")
    pipe = conn.pipeline()
    for pid in pids:
        pipe.srem(f"project_users:{pid}", name)
    pipe.delete(f"user_projects:{name}")
    pipe.delete(f"user:{name}")
    pipe.srem("users", name)
    pipe.execute()


def user_roles(name):
    return r().hgetall(f"user_projects:{name}") or {}


def list_users():
    names = sorted(r().smembers("users"), key=str.lower)
    out = []
    for name in names:
        u = get_user(name)
        if not u:
            continue
        u["roles"] = user_roles(name)
        out.append(u)
    return out


def is_root(name):
    u = get_user(name)
    return bool(u and u["is_root"])


def user_role(name, project_id):
    u = get_user(name)
    if not u:
        return None
    if u["is_root"]:
        return "root"
    role = r().hget(f"user_projects:{name}", project_id)
    return role if role in ROLES else None


def set_user_role(name, project_id, role):
    u = get_user(name)
    if not u:
        raise ValueError(msg.user_missing)
    if u["is_root"]:
        raise ValueError(msg.cannot_assign_root)
    if not r().exists(f"project:{project_id}"):
        raise ValueError(msg.project_missing)
    role = (role or "").strip()
    conn = r()
    if not role:
        conn.hdel(f"user_projects:{name}", project_id)
        conn.srem(f"project_users:{project_id}", name)
        return
    if role not in ROLES:
        raise ValueError(msg.bad_role)
    conn.hset(f"user_projects:{name}", project_id, role)
    conn.sadd(f"project_users:{project_id}", name)


def save_user_roles(name, form, project_ids):
    for pid in project_ids:
        set_user_role(name, pid, form.get(f"role_{pid}"))


def visible_ids(name):
    u = get_user(name)
    if not u:
        return []
    if u["is_root"]:
        return sorted(r().smembers("projects"))
    return list(user_roles(name).keys())


def staff_ids(name):
    u = get_user(name)
    if not u:
        return []
    if u["is_root"]:
        return sorted(r().smembers("projects"))
    return [pid for pid, role in user_roles(name).items() if role in STAFF_ROLES]


def can_staff(name):
    u = get_user(name)
    if not u:
        return False
    if u["is_root"]:
        return True
    return any(role in STAFF_ROLES for role in user_roles(name).values())


def can_create_project(name):
    u = get_user(name)
    if not u:
        return False
    if u["is_root"]:
        return True
    return any(role == "admin" for role in user_roles(name).values())


def can_edit(name, project_id):
    return user_role(name, project_id) in ("root", "admin", "maintainer")


def can_delete_project(name, project_id):
    return user_role(name, project_id) in ("root", "admin")


def can_lottery(name, project_id):
    return user_role(name, project_id) in ("root", "admin", "maintainer", "guest")


def chance_count(project_id, device_id):
    conn = r()
    key = f"device_chance:{project_id}:{device_id}"
    raw = conn.get(key)
    if raw is not None:
        return int(raw)
    n = 0
    for serial in conn.zrange(f"tickets:{project_id}", 0, -1):
        t = _ticket(project_id, serial)
        if t and t.get("device_id") == device_id:
            n += 1
    conn.set(key, n, ex=ttl_seconds())
    return n


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
    n = conn.incr(f"device_chance:{project_id}:{device_id}")
    conn.expire(f"device_chance:{project_id}:{device_id}", ttl)
    return serial, int(n)


def add_photo(project_id, photo_id, caption, device_id, rebuild=True):
    """Save the photo record; chances are granted later by the detector."""
    now = time.time()
    ttl = ttl_seconds()
    conn = r()
    conn.set(
        f"photo:{project_id}:{photo_id}",
        json.dumps(
            {"caption": caption, "ts": now, "device_id": device_id, "person": None},
            ensure_ascii=False,
        ),
        ex=ttl,
    )
    conn.zadd(f"photos:{project_id}", {photo_id: now})
    conn.sadd(f"devices:{project_id}", device_id)
    conn.zadd(f"device_photos:{project_id}:{device_id}", {photo_id: now})
    conn.sadd(f"device_pending:{project_id}:{device_id}", photo_id)
    conn.expire(f"device_pending:{project_id}:{device_id}", ttl)
    conn.lpush(
        DETECT_Q,
        json.dumps(
            {"project_id": project_id, "photo_id": photo_id, "device_id": device_id}
        ),
    )
    if rebuild:
        rebuild_slideshow_queue(project_id)


def grant_person(project_id, photo_id, device_id, ts):
    cap = appsetting.lottery_chance_max
    ttl = ttl_seconds()
    conn = r()
    if chance_count(project_id, device_id) >= cap:
        drop_oldest_ticket(project_id, device_id)
    _, n = add_ticket(project_id, photo_id, device_id)
    if n > cap:
        drop_oldest_ticket(project_id, device_id)
        conn.set(f"device_chance:{project_id}:{device_id}", cap, ex=ttl)
    conn.zadd(f"device_eligible:{project_id}:{device_id}", {photo_id: ts})
    conn.expire(f"device_eligible:{project_id}:{device_id}", ttl)
    conn.incr(f"kuji_earned:{project_id}:{device_id}")
    conn.expire(f"kuji_earned:{project_id}:{device_id}", ttl)


def set_person(project_id, photo_id, device_id, person):
    """Record the detector result once; a person grants lottery + kuji chances."""
    conn = r()
    key = f"photo:{project_id}:{photo_id}"
    raw = conn.get(key)
    if not raw:
        return
    data = json.loads(raw)
    if data.get("person") is not None:
        return
    data["person"] = bool(person)
    conn.set(key, json.dumps(data, ensure_ascii=False), keepttl=True)
    did = data.get("device_id") or device_id
    conn.srem(f"device_pending:{project_id}:{did}", photo_id)
    if person:
        grant_person(project_id, photo_id, did, data.get("ts") or time.time())


def photo_status(project_id, device_id, photo_ids):
    out = {}
    for pid in photo_ids[:20]:
        raw = r().get(f"photo:{project_id}:{pid}")
        if not raw:
            continue
        data = json.loads(raw)
        if data.get("device_id") != device_id:
            continue
        out[pid] = data.get("person")
    return {
        "photos": out,
        "chances": chance_count(project_id, device_id),
        "kuji": kuji_me(project_id, device_id),
    }


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


def drop_photo(project_id, photo_id, rebuild=True):
    r().zrem(f"photos:{project_id}", photo_id)
    r().delete(f"photo:{project_id}:{photo_id}")
    photo_path(project_id, photo_id).unlink(missing_ok=True)
    if rebuild:
        rebuild_slideshow_queue(project_id)


def sweep_expired(project_id):
    ids = r().zrange(f"photos:{project_id}", 0, -1)
    kept = []
    for pid in ids:
        item = load_photo(project_id, pid)
        if item is None:
            drop_photo(project_id, pid, rebuild=False)
            continue
        kept.append(item)
    return kept


def rebuild_slideshow_queue(project_id, cfgp=None):
    conn = r()
    zkey = f"photos:{project_id}"
    qkey = f"slideshow_q:{project_id}"
    total = conn.zcard(zkey)
    cfgp = cfgp or settings_of(project_id)
    cap = cfgp["slideshow_queue_max"]
    per = cfgp["slideshow_per_device"]
    if total <= cap:
        mapping = dict(conn.zrange(zkey, 0, -1, withscores=True))
    else:
        picked = {}
        for did in conn.smembers(f"devices:{project_id}"):
            for pid, score in conn.zrevrange(
                f"device_photos:{project_id}:{did}", 0, per - 1, withscores=True
            ):
                picked[pid] = score
        mapping = dict(
            sorted(picked.items(), key=lambda x: x[1], reverse=True)[:cap]
        )
    pipe = conn.pipeline()
    pipe.delete(qkey)
    if mapping:
        pipe.zadd(qkey, mapping)
    pipe.execute()


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
    cfgp = settings_of(project_id)
    interval = cfgp["slideshow_interval"]
    qkey = f"slideshow_q:{project_id}"
    conn = r()
    if conn.zcard(qkey) == 0 and conn.zcard(f"photos:{project_id}") > 0:
        rebuild_slideshow_queue(project_id, cfgp)
    for _ in range(8):
        now = time.time()
        result = advance_script()(
            keys=[f"slideshow:{project_id}", qkey],
            args=[now, interval],
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
    return _empty_state(time.time(), interval)


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
    if t and t.get("device_id"):
        key = f"device_chance:{project_id}:{t['device_id']}"
        n = conn.decr(key)
        if n < 0:
            conn.set(key, 0, ex=ttl_seconds())


def drop_oldest_ticket(project_id, device_id):
    for serial in r().zrange(f"tickets:{project_id}", 0, -1):
        t = _ticket(project_id, serial)
        if t and t.get("device_id") == device_id:
            drop_ticket(project_id, serial)
            return True
    return False


def latest_photo_ids(project_id, device_id, n):
    return set(
        r().zrevrange(f"device_eligible:{project_id}:{device_id}", 0, n - 1)
    )


def device_photos(project_id, device_id, exclude=None, limit=None):
    key = f"device_photos:{project_id}:{device_id}"
    if limit is None:
        ids = r().zrange(key, 0, -1)
    else:
        ids = r().zrevrange(key, 0, max(0, limit - 1))
    out = []
    for pid in ids:
        if exclude and pid == exclude:
            continue
        item = load_photo(project_id, pid)
        if item is None:
            r().zrem(key, pid)
            continue
        out.append({"id": item["id"], "url": item["url"]})
    return out


def won_devices(project_id):
    return r().smembers(f"lottery_won:{project_id}")


def mark_won(project_id, device_id):
    if device_id:
        r().sadd(f"lottery_won:{project_id}", device_id)


def reset_lottery_winners(project_id):
    if not r().exists(f"project:{project_id}"):
        raise ValueError(msg.project_missing)
    r().delete(f"lottery_won:{project_id}")


def lottery_pool(project_id):
    cap = appsetting.lottery_chance_max
    won = won_devices(project_id)
    out = []
    for did in r().smembers(f"devices:{project_id}"):
        if did in won:
            continue
        for pid in r().zrevrange(f"device_eligible:{project_id}:{did}", 0, cap - 1):
            item = load_photo(project_id, pid)
            if item:
                out.append(item)
    return out


def sphere_photos(project_id, limit):
    items = lottery_pool(project_id)
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
    cap = appsetting.lottery_chance_max
    won = won_devices(project_id)
    serials = list(r().zrange(f"tickets:{project_id}", 0, -1))
    random.shuffle(serials)
    winner = None
    for serial in serials:
        t = _ticket(project_id, serial)
        if not t:
            drop_ticket(project_id, serial)
            continue
        if t.get("device_id") in won:
            continue
        latest = latest_photo_ids(project_id, t.get("device_id"), cap)
        if t.get("photo_id") not in latest:
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
    others = device_photos(
        project_id, t["device_id"], exclude=photo["id"], limit=cap
    )
    total = int(r().zcard(f"device_photos:{project_id}:{t['device_id']}") or 0)
    cfgp = settings_of(project_id)
    sphere = sphere_photos(project_id, cfgp["lottery_sphere_max"])
    mark_won(project_id, t.get("device_id"))
    return {
        "serial": t["serial"],
        "seconds": cfgp["lottery_seconds"],
        "winner": {
            "id": photo["id"],
            "url": photo["url"],
            "caption": photo.get("caption") or "",
            "nickname": photo.get("nickname") or "",
            "upload_count": total or len(others) + 1,
        },
        "device_photos": others,
        "sphere": sphere,
    }


def kuji_label_default(grade):
    return msg.kuji_grade.format(grade=grade)


def kuji_label_raw(raw, grade):
    s = (raw.get(f"label_{grade}") or "").strip()
    if not s or len(s) > KUJI_LABEL_MAX:
        return ""
    return s


def kuji_settings(project_id):
    raw = r().hgetall(f"kuji:{project_id}") or {}
    out = {
        "per_user": appsetting.kuji_per_user,
        "totals": {},
        "labels": {},
        "label_raws": {},
    }
    try:
        out["per_user"] = int(raw["per_user"])
    except (KeyError, ValueError):
        pass
    for g in KUJI_GRADES:
        try:
            out["totals"][g] = int(raw.get(g) or 0)
        except ValueError:
            out["totals"][g] = 0
        out["label_raws"][g] = kuji_label_raw(raw, g)
        out["labels"][g] = out["label_raws"][g] or kuji_label_default(g)
    return out


def kuji_save(project_id, form):
    if not r().exists(f"project:{project_id}"):
        raise ValueError(msg.project_missing)
    try:
        per = int(form.get("per_user"))
        totals = [int(form.get(f"total_{g}") or 0) for g in KUJI_GRADES]
    except (TypeError, ValueError):
        raise ValueError(msg.bad_setting)
    if not 0 <= per <= KUJI_PER_USER_MAX:
        raise ValueError(msg.bad_setting)
    if any(not 0 <= t <= KUJI_TOTAL_MAX for t in totals):
        raise ValueError(msg.bad_setting)
    labels = {}
    for g in KUJI_GRADES:
        s = (form.get(f"label_{g}") or "").strip()
        if len(s) > KUJI_LABEL_MAX:
            raise ValueError(msg.kuji_label_too_long)
        labels[f"label_{g}"] = s
    bad = _script("kuji_save", _KUJI_SAVE_LUA)(
        keys=[f"kuji:{project_id}", f"kuji_drawn:{project_id}"],
        args=[per, *totals],
    )
    if bad:
        raise ValueError(msg.kuji_total_below_drawn.format(grade=bad))
    r().hset(f"kuji:{project_id}", mapping=labels)


def kuji_reset(project_id):
    conn = r()
    pipe = conn.pipeline()
    for k in ("kuji_drawn", "kuji_draws", "kuji_claimed", "kuji_seq"):
        pipe.delete(f"{k}:{project_id}")
    for did in conn.smembers(f"devices:{project_id}"):
        pipe.delete(f"kuji_used:{project_id}:{did}")
        pipe.delete(f"kuji_mine:{project_id}:{did}")
    pipe.execute()


def _prize_urls(project_id, grade):
    kind = f"kuji-{grade.lower()}"
    return asset_url(project_id, kind), asset_thumb_url(project_id, kind)


def kuji_state(project_id):
    cfgk = kuji_settings(project_id)
    drawn = r().hgetall(f"kuji_drawn:{project_id}") or {}
    grades = []
    for g in KUJI_GRADES:
        total = cfgk["totals"][g]
        d = min(total, int(drawn.get(g) or 0))
        url, thumb = _prize_urls(project_id, g)
        grades.append(
            {"grade": g, "label": cfgk["labels"][g],
             "label_raw": cfgk["label_raws"][g],
             "total": total, "drawn": d, "left": total - d,
             "url": url, "thumb": thumb}
        )
    return {
        "per_user": cfgk["per_user"],
        "grades": grades,
        "total": sum(x["total"] for x in grades),
        "left": sum(x["left"] for x in grades),
    }


def kuji_me(project_id, device_id):
    conn = r()
    per = kuji_settings(project_id)["per_user"]
    earned = int(conn.get(f"kuji_earned:{project_id}:{device_id}") or 0)
    used = int(conn.get(f"kuji_used:{project_id}:{device_id}") or 0)
    return {
        "earned": earned,
        "used": used,
        "per_user": per,
        "left": max(0, min(earned, per) - used),
        "pending": int(conn.scard(f"device_pending:{project_id}:{device_id}") or 0),
    }


def kuji_draw(project_id, device_id):
    res = _script("kuji_draw", _KUJI_DRAW_LUA)(
        keys=[
            f"kuji:{project_id}",
            f"kuji_drawn:{project_id}",
            f"kuji_used:{project_id}:{device_id}",
            f"kuji_earned:{project_id}:{device_id}",
            f"kuji_mine:{project_id}:{device_id}",
            f"kuji_draws:{project_id}",
            f"kuji_seq:{project_id}",
        ],
        args=[random.random(), time.time(), device_id, appsetting.kuji_per_user],
    )
    if res[0] == "sold_out":
        raise ValueError(msg.kuji_sold_out)
    if res[0] != "ok":
        me = kuji_me(project_id, device_id)
        if me["used"] >= me["per_user"]:
            raise ValueError(msg.kuji_cap_reached.format(n=me["per_user"]))
        if me["pending"]:
            raise ValueError(msg.kuji_pending)
        raise ValueError(msg.kuji_need_photo)
    _, grade, draw_id = res
    url, thumb = _prize_urls(project_id, grade)
    return {
        "id": draw_id,
        "grade": grade,
        "label": kuji_settings(project_id)["labels"][grade],
        "url": url,
        "thumb": thumb,
        "me": kuji_me(project_id, device_id),
    }


def kuji_mine(project_id, device_id):
    conn = r()
    ids = conn.lrange(f"kuji_mine:{project_id}:{device_id}", 0, -1)
    if not ids:
        return []
    labels = kuji_settings(project_id)["labels"]
    draws = conn.hmget(f"kuji_draws:{project_id}", ids)
    claimed = conn.hmget(f"kuji_claimed:{project_id}", ids)
    out = []
    for draw_id, raw, at in zip(ids, draws, claimed):
        if not raw:
            continue
        d = json.loads(raw)
        url, thumb = _prize_urls(project_id, d["grade"])
        out.append(
            {"id": draw_id, "grade": d["grade"],
             "label": labels.get(d["grade"]) or kuji_label_default(d["grade"]),
             "ts": d.get("ts"),
             "url": url, "thumb": thumb,
             "claimed_at": int(at) if at else None}
        )
    return out


def kuji_claim(project_id, device_id, draw_id):
    conn = r()
    raw = conn.hget(f"kuji_draws:{project_id}", draw_id)
    if not raw or json.loads(raw).get("device_id") != device_id:
        raise ValueError(msg.kuji_claim_missing)
    now = int(time.time())
    if not conn.hsetnx(f"kuji_claimed:{project_id}", draw_id, now):
        raise ValueError(msg.kuji_already_claimed)
    return now
