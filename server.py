#!/usr/bin/env python3
"""G730 — Simple static file server. All data processing now happens client-side."""

import http.server
import socket
from pathlib import Path

PORT = 3000
PUBLIC_DIR = Path(__file__).resolve().parent / "public"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Quiet


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    local_ip = get_local_ip()
    print(f"G730 Dashboard at http://localhost:{PORT}")
    print(f"  Phone: http://{local_ip}:{PORT}")
    print(f"  Serving: {PUBLIC_DIR}")
    print(f"  Once loaded on your phone, it works offline!")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDone.")
        server.shutdown()
