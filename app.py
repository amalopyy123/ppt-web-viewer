import hmac
import hashlib
import ipaddress
import os
import shutil
import tempfile
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
ALLOWED_EXTENSIONS = {"ppt", "pptx"}


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


def has_allowed_extension(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def has_valid_signature(path: Path, extension: str) -> bool:
    with path.open("rb") as uploaded:
        signature = uploaded.read(8)

    if extension == "pptx":
        return signature.startswith(b"PK")
    return signature == bytes.fromhex("D0CF11E0A1B11AE1")


def find_all_presentations() -> list[Path]:
    if not DATA_DIR.is_dir():
        return []
    return [
        *DATA_DIR.glob("presentation-*.ppt"),
        *DATA_DIR.glob("presentation-*.pptx"),
    ]


def find_current_presentation() -> Path | None:
    candidates = find_all_presentations()
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def public_file_url(filename: str) -> str:
    configured_base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured_base:
        return f"{configured_base}{url_for('presentation_file', filename=filename)}"
    return url_for("presentation_file", filename=filename, _external=True, _scheme=request.scheme)


def office_viewer_url(filename: str) -> str:
    source_url = public_file_url(filename)
    return f"https://view.officeapps.live.com/op/embed.aspx?src={quote(source_url, safe='')}"


@app.get("/")
def index():
    presentation = find_current_presentation()
    return render_template(
        "index.html",
        presentation=presentation,
        viewer_url=office_viewer_url(presentation.name) if presentation else None,
    )


@app.get("/files/<filename>")
def presentation_file(filename):
    presentation = find_current_presentation()
    if not presentation or filename != presentation.name:
        return "No presentation has been uploaded yet.", 404

    return send_file(
        presentation,
        mimetype=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if presentation.suffix.lower() == ".pptx"
            else "application/vnd.ms-powerpoint"
        ),
        conditional=True,
        max_age=3600,
        download_name=presentation.name,
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
        uploaded = request.files.get("presentation")
        if not uploaded or not uploaded.filename:
            flash("请选择一个 PPT 或 PPTX 文件。", "error")
            return redirect(url_for("admin_upload"))

        filename = uploaded.filename
        if not has_allowed_extension(filename):
            flash("只允许上传 .ppt 或 .pptx 文件。", "error")
            return redirect(url_for("admin_upload"))

        extension = filename.rsplit(".", 1)[1].lower()
        try:
            with tempfile.TemporaryDirectory(prefix="ppt-upload-") as temp_name:
                temp_dir = Path(temp_name)
                source = temp_dir / f"presentation.{extension}"
                uploaded.save(source)

                if not has_valid_signature(source, extension):
                    raise ValueError("文件内容与 PPT/PPTX 格式不符。")

                digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                destination = DATA_DIR / f"presentation-{digest}.{extension}"
                replacement = DATA_DIR / f".presentation-upload.{extension}"
                shutil.copyfile(source, replacement)
                os.replace(replacement, destination)

                for old_file in find_all_presentations():
                    if old_file != destination:
                        old_file.unlink(missing_ok=True)

            flash("PPT 已上传并发布到微软在线预览。", "success")
        except (OSError, RuntimeError, ValueError) as exc:
            flash(str(exc), "error")

        return redirect(url_for("admin_upload"))

    return render_template(
        "admin_upload.html",
        presentation=find_current_presentation(),
        public_base_url=os.environ.get("PUBLIC_BASE_URL", "").strip(),
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
