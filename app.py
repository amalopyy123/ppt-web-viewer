import hmac
import ipaddress
import os
import shutil
import tempfile
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CURRENT_PDF = DATA_DIR / "presentation.pdf"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_admin_networks():
    configured = os.environ.get("ADMIN_IP_WHITELIST", "127.0.0.1,::1")
    networks = []
    for item in configured.split(","):
        item = item.strip()
        if item:
            networks.append(ipaddress.ip_network(item, strict=False))
    return networks


ADMIN_NETWORKS = parse_admin_networks()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-before-production"),
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,
)

if env_bool("TRUST_PROXY"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def validate_bind_config(host: str) -> None:
    if host in {"0.0.0.0", "::"} and not env_bool("ALLOW_PUBLIC_BIND"):
        raise RuntimeError(
            "Public binding is disabled. Set ALLOW_PUBLIC_BIND=true to use HOST=0.0.0.0 or HOST=::."
        )


def admin_ip_is_allowed(address: str | None) -> bool:
    if not address:
        return False
    try:
        client_ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(client_ip in network for network in ADMIN_NETWORKS)


@app.before_request
def restrict_admin_by_ip():
    if request.path.startswith("/admin") and not admin_ip_is_allowed(request.remote_addr):
        abort(403)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


def has_valid_pdf(path: Path) -> bool:
    with path.open("rb") as uploaded:
        return uploaded.read(5) == b"%PDF-"


@app.get("/")
def index():
    return render_template("index.html", pdf_exists=CURRENT_PDF.is_file())


@app.get("/document.pdf")
def document():
    if not CURRENT_PDF.is_file():
        return "No PDF has been uploaded yet.", 404
    return send_file(
        CURRENT_PDF,
        mimetype="application/pdf",
        conditional=True,
        max_age=0,
        download_name="presentation.pdf",
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_upload"))

    if request.method == "POST":
        expected_password = os.environ.get("ADMIN_PASSWORD", "")
        if not expected_password:
            flash("管理员密码尚未配置，请设置 ADMIN_PASSWORD。", "error")
            return render_template("admin_login.html"), 503
        submitted_password = request.form.get("password", "")
        if hmac.compare_digest(submitted_password, expected_password):
            session.clear()
            session["is_admin"] = True
            return redirect(url_for("admin_upload"))
        flash("密码错误。", "error")

    return render_template("admin_login.html")


@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def admin_upload():
    if request.method == "POST":
        uploaded = request.files.get("pdf")
        if not uploaded or not uploaded.filename:
            flash("请选择一个 PDF 文件。", "error")
            return redirect(url_for("admin_upload"))

        if Path(uploaded.filename).suffix.lower() != ".pdf":
            flash("只允许上传 .pdf 文件。", "error")
            return redirect(url_for("admin_upload"))

        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".presentation-", suffix=".pdf", dir=DATA_DIR, delete=False
            ) as temporary:
                replacement = Path(temporary.name)
                shutil.copyfileobj(uploaded.stream, temporary)

            if not has_valid_pdf(replacement):
                replacement.unlink(missing_ok=True)
                raise ValueError("文件内容不是有效的 PDF 格式。")

            os.replace(replacement, CURRENT_PDF)
            flash("PDF 已上传并发布。", "success")
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")

        return redirect(url_for("admin_upload"))

    return render_template(
        "admin_upload.html",
        pdf_exists=CURRENT_PDF.is_file(),
    )


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.errorhandler(413)
def file_too_large(_error):
    flash("文件过大，最大允许 100 MB。", "error")
    return redirect(url_for("admin_upload")), 413


@app.errorhandler(403)
def forbidden(_error):
    return "Your IP address is not allowed to access the administrator area.", 403


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    validate_bind_config(host)
    app.run(host=host, port=port, debug=debug)
