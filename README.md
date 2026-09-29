# PDF Web Viewer

A small Flask website where one administrator uploads a PDF and visitors read it in their browser.

## Requirements

- Python 3.10+

## Local setup

1. Create a virtual environment with python -m venv .venv
2. Activate it with .venv\Scripts\Activate.ps1
3. Install dependencies with pip install -r requirements.txt
4. Copy .env.example to .env and edit the configuration
5. Start the development server with python app.py

Open http://127.0.0.1:5000/ for the public page and http://127.0.0.1:5000/admin for the administrator page.

The administrator login remains unavailable until ADMIN_PASSWORD is configured.

HOST defaults to 127.0.0.1 and PORT defaults to 5000. Binding to 0.0.0.0 or :: is rejected unless ALLOW_PUBLIC_BIND=true is explicitly configured.

## Ubuntu deployment

Create the application environment:

    cd /var/www/ppt-website
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Create .env from .env.example, then start the production server with:

    .venv/bin/python server.py

Use Nginx as the public HTTPS reverse proxy for the domain. The data directory must be writable by the service user because the uploaded PDF is stored there.

Recommended local Nginx configuration in .env:

    HOST=127.0.0.1
    PORT=5000
    TRUST_PROXY=true
    ADMIN_IP_WHITELIST=203.0.113.10

For direct public binding without Nginx, explicitly configure:

    HOST=0.0.0.0
    PORT=5000
    ALLOW_PUBLIC_BIND=true

ADMIN_IP_WHITELIST accepts individual addresses and CIDR ranges separated by commas, for example 203.0.113.10,192.168.1.0/24. It protects only the administrator URLs; the presentation remains public.

## Production

Run waitress-serve --listen=127.0.0.1:5000 app:app behind IIS, Apache, or Nginx, proxy the domain to port 5000, and enable HTTPS.
