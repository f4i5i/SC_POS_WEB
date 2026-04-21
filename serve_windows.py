"""
Windows production entrypoint.

Launches the Flask app under Waitress (pure-Python WSGI, Windows-safe) and
explicitly starts the background services that run.py normally gates behind
Werkzeug's reloader flag.

Run directly: `python serve_windows.py`
Or via start_pos.bat / Task Scheduler / NSSM.

Environment overrides:
    POS_HOST     (default 0.0.0.0)
    POS_PORT     (default 5001)
    POS_THREADS  (default 8)
"""

import os

os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('FLASK_USE_RELOADER', 'false')

from waitress import serve

from run import app, start_background_services
from app import db

HOST = os.environ.get('POS_HOST', '0.0.0.0')
PORT = int(os.environ.get('POS_PORT', '5001'))
THREADS = int(os.environ.get('POS_THREADS', '8'))

with app.app_context():
    db.create_all()
    start_background_services()

print(f'Serving POS on http://{HOST}:{PORT} (threads={THREADS})', flush=True)
serve(app, host=HOST, port=PORT, threads=THREADS)
