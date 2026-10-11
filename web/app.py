import io
import uuid
from datetime import timedelta
from functools import wraps

import qrcode
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
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
    app.config["MAX_CONTENT_LENGTH"] = appsetting.max_upload_mb * 5 * 1024 * 1024
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
        return {
            "is_admin": bool(session.get("admin")),
            "msg": msg,
            "cfg": appsetting,
        }

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
        try:
            p = store.delete_project(project_id, delete_files=True)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        flash(msg.project_deleted.format(name=p["name"]), "ok")
        return redirect(url_for("admin_home"))

    @app.post("/admin/projects/<project_id>/asset/<kind>")
    @admin_required
    def admin_save_asset(project_id, kind):
        if not store.get_project(project_id):
            flash(msg.project_missing, "error")
            return redirect(url_for("admin_home"))
        f = request.files.get("photo")
        if not f or not f.filename:
            flash(msg.need_photo, "error")
            return redirect(url_for("admin_home"))
        try:
            dest = store.asset_path(project_id, kind)
            thumb = store.asset_thumb_path(project_id, kind)
            images.save_jpeg_and_thumb(f, dest, thumb)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        except Exception:
            flash(msg.bad_image, "error")
            return redirect(url_for("admin_home"))
        flash(msg.asset_saved, "ok")
        return redirect(url_for("admin_home"))

    @app.post("/admin/projects/<project_id>/asset/<kind>/delete")
    @admin_required
    def admin_delete_asset(project_id, kind):
        if not store.get_project(project_id):
            flash(msg.project_missing, "error")
            return redirect(url_for("admin_home"))
        try:
            store.asset_path(project_id, kind).unlink(missing_ok=True)
            store.asset_thumb_path(project_id, kind).unlink(missing_ok=True)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        flash(msg.asset_removed, "ok")
        return redirect(url_for("admin_home"))

    @app.post("/admin/projects/<project_id>/settings")
    @admin_required
    def admin_save_settings(project_id):
        try:
            store.update_project_settings(project_id, request.form)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin_home"))
        flash(msg.settings_saved, "ok")
        return redirect(url_for("admin_home"))

    @app.post("/p/<slug>/lottery/reset")
    @admin_required
    def lottery_reset(slug):
        project = load_project(slug)
        store.reset_lottery_winners(project["id"])
        return redirect(url_for("lottery", slug=slug))

    _qr_pages = {
        "home": "project_home",
        "upload": "upload",
        "slideshow": "slideshow",
    }

    @app.get("/admin/projects/<project_id>/qr/<kind>.png")
    @admin_required
    def admin_qr(project_id, kind):
        endpoint = _qr_pages.get(kind)
        p = store.get_project(project_id)
        if not endpoint or not p:
            abort(404)
        qr = qrcode.QRCode(border=2, box_size=10)
        qr.add_data(url_for(endpoint, slug=p["slug"], _external=True))
        qr.make(fit=True)
        buf = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    @app.get("/p/<slug>/")
    def project_home(slug):
        return render_template("project_home.html", project=load_project(slug))

    @app.route("/p/<slug>/upload", methods=["GET", "POST"])
    def upload(slug):
        project = load_project(slug)
        if request.method == "POST":
            xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"

            def reply(text, error=False):
                if xhr:
                    key = "error" if error else "message"
                    return jsonify({key: text}), (400 if error else 200)
                flash(text, "error" if error else "ok")
                return redirect(request.path)

            files = [f for f in request.files.getlist("photo") if f and f.filename]
            caption = (request.form.get("caption") or "").strip()
            if not files:
                return reply(msg.need_photo, error=True)
            if len(files) > 5:
                return reply(msg.upload_too_many, error=True)
            if len(caption) > 500:
                return reply(msg.caption_too_long, error=True)
            did, _ = device_id()
            saved = 0
            serial = ""
            chances = 0
            at_cap = False
            for f in files:
                photo_id = uuid.uuid4().hex
                dest = store.photo_path(project["id"], photo_id)
                try:
                    images.save_jpeg(f, dest)
                except Exception:
                    dest.unlink(missing_ok=True)
                    continue
                serial, chances, capped = store.add_photo(
                    project["id"], photo_id, caption, did, rebuild=False
                )
                saved += 1
                at_cap = at_cap or capped
            if not saved:
                return reply(msg.bad_image, error=True)
            store.rebuild_slideshow_queue(project["id"])
            cap = appsetting.lottery_chance_max
            if at_cap:
                text = msg.upload_ok_capped.format(max=cap, serial=serial, n=saved)
            elif saved == 1:
                text = msg.upload_ok.format(chances=chances, serial=serial)
            else:
                text = msg.upload_ok_many.format(
                    n=saved, chances=chances, serial=serial
                )
            return reply(text)
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
        project = load_project(slug)
        return render_template(
            "lottery.html",
            project=project,
            seconds=project["lottery_seconds"],
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
