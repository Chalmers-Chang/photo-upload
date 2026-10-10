import uuid
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import admin as admin_config
from config import appsetting
from config import msg
from web import images, store


def create_app():
    app = Flask(__name__)
    app.secret_key = appsetting.secret_key
    app.config["MAX_CONTENT_LENGTH"] = appsetting.max_upload_mb * 1024 * 1024
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    def admin_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("admin_login", next=request.path))
            return fn(*args, **kwargs)

        return wrapped

    def load_project(slug):
        p = store.project_by_slug(slug)
        if not p:
            abort(404)
        return p

    def device_id():
        if getattr(g, "device_id", None):
            return g.device_id, g.device_id_new
        did = request.cookies.get("device_id") or ""
        if did and len(did) <= 64:
            g.device_id = did
            g.device_id_new = False
            return did, False
        g.device_id = uuid.uuid4().hex
        g.device_id_new = True
        return g.device_id, True

    def with_device_cookie(resp, did, is_new):
        if is_new:
            resp.set_cookie(
                "device_id",
                did,
                max_age=60 * 60 * 24 * 400,
                httponly=True,
                samesite="Lax",
            )
        return resp

    @app.context_processor
    def inject_admin():
        return {"is_admin": bool(session.get("admin")), "msg": msg}

    @app.after_request
    def remember_device(resp):
        did, is_new = device_id()
        return with_device_cookie(resp, did, is_new)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/profile")
    def profile_get():
        did, _ = device_id()
        return {"nickname": store.nickname_of(did)}

    @app.post("/api/profile")
    def profile_post():
        did, _ = device_id()
        payload = request.get_json(silent=True) or request.form
        try:
            name = store.set_nickname(did, payload.get("nickname"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"nickname": name})

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        nxt = request.args.get("next") or url_for("admin_home")
        if session.get("admin"):
            return redirect(nxt)
        error = None
        if request.method == "POST":
            user = request.form.get("username") or ""
            pw = request.form.get("password") or ""
            if user == admin_config.username and pw == admin_config.password:
                session.clear()
                session["admin"] = True
                session.permanent = True
                return redirect(nxt)
            error = msg.login_failed
        return render_template("admin_login.html", error=error)

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        session.clear()
        return redirect(url_for("index"))

    @app.get("/admin")
    @admin_required
    def admin_home():
        return render_template("admin.html", projects=store.list_projects())

    @app.post("/admin/projects")
    @admin_required
    def admin_create_project():
        try:
            p = store.create_project(
                request.form.get("name"),
                request.form.get("slug"),
            )
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        flash(msg.project_created.format(name=p["name"]), "ok")
        return redirect(url_for("admin_home"))

    @app.post("/admin/projects/<project_id>/delete")
    @admin_required
    def admin_delete_project(project_id):
        mode = request.form.get("mode")
        delete_files = mode == "redis_and_files"
        try:
            p = store.delete_project(project_id, delete_files=delete_files)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        if delete_files:
            flash(msg.project_deleted.format(name=p["name"]), "ok")
        else:
            flash(msg.project_deleted_redis.format(name=p["name"]), "ok")
        return redirect(url_for("admin_home"))

    @app.get("/p/<slug>/")
    def project_home(slug):
        return render_template("project_home.html", project=load_project(slug))

    @app.route("/p/<slug>/upload", methods=["GET", "POST"])
    def upload(slug):
        project = load_project(slug)
        if request.method == "POST":
            f = request.files.get("photo")
            caption = (request.form.get("caption") or "").strip()
            if not f or not f.filename:
                flash(msg.need_photo, "error")
                return redirect(request.path)
            if len(caption) > 500:
                flash(msg.caption_too_long, "error")
                return redirect(request.path)
            photo_id = uuid.uuid4().hex
            dest = store.photo_path(project["id"], photo_id)
            try:
                images.save_jpeg(f, dest)
            except Exception:
                flash(msg.bad_image, "error")
                dest.unlink(missing_ok=True)
                return redirect(request.path)
            did, _ = device_id()
            serial, chances = store.add_photo(
                project["id"], photo_id, caption, did
            )
            flash(msg.upload_ok.format(chances=chances, serial=serial), "ok")
            return redirect(request.path)
        return render_template("upload.html", project=project)

    @app.get("/p/<slug>/slideshow")
    def slideshow(slug):
        return render_template("slideshow.html", project=load_project(slug))

    @app.get("/p/<slug>/api/slideshow")
    def slideshow_api(slug):
        project = load_project(slug)
        return jsonify(store.slideshow_state(project["id"]))

    @app.get("/p/<slug>/lottery")
    @admin_required
    def lottery(slug):
        return render_template(
            "lottery.html",
            project=load_project(slug),
            seconds=appsetting.lottery_seconds,
        )

    @app.post("/p/<slug>/api/lottery/draw")
    @admin_required
    def lottery_draw(slug):
        project = load_project(slug)
        try:
            return jsonify(store.draw_lottery(project["id"]))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    return app
