import os

from waitress import serve

from app import app, validate_bind_config


host = os.environ.get("HOST", "127.0.0.1")
port = int(os.environ.get("PORT", "5000"))
validate_bind_config(host)

serve(app, host=host, port=port)
