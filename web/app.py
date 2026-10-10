import uuid
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import admin as admin_config
from config import appsetting
from web import images, store


def create_app():
    app = Flask(__name__)
    app.secret_key = appsetting.secret_key
    app.config["MAX_CONTENT_LENGTH"] = appsetting.max_upload_mb * 1024 * 1024

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

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("admin"):
            return redirect(url_for("admin_home"))
        error = None
        if request.method == "POST":
            user = request.form.get("username") or ""
            pw = request.form.get("password") or ""
            if user == admin_config.username and pw == admin_config.password:
                session["admin"] = True
                return redirect(request.args.get("next") or url_for("admin_home"))
            error = "帳號或密碼錯誤"
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
        flash(f"已建立「{p['name']}」", "ok")
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
            flash(f"已刪除「{p['name']}」的 Redis 與照片", "ok")
        else:
            flash(f"已刪除「{p['name']}」的 Redis 資料，照片檔仍留在磁碟", "ok")
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
                flash("請選擇照片", "error")
                return redirect(request.path)
            if len(caption) > 500:
                flash("文字太長（最多 500 字）", "error")
                return redirect(request.path)
            photo_id = uuid.uuid4().hex
            dest = store.photo_path(project["id"], photo_id)
            try:
                images.save_jpeg(f, dest)
            except Exception:
                flash("無法讀取這張圖片，請改用 JPG / PNG / HEIC", "error")
                dest.unlink(missing_ok=True)
                return redirect(request.path)
            store.add_photo(project["id"], photo_id, caption)
            flash("已上傳", "ok")
            return redirect(request.path)
        return render_template("upload.html", project=project)

    @app.get("/p/<slug>/slideshow")
    def slideshow(slug):
        return render_template("slideshow.html", project=load_project(slug))

    @app.get("/p/<slug>/api/slideshow")
    def slideshow_api(slug):
        project = load_project(slug)
        return jsonify(store.slideshow_state(project["id"]))

    return app
