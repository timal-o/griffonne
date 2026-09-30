#!/usr/bin/env python3
"""Serveur local : `python app.py` puis ouvrir http://localhost:8765"""
import io
import json
import mimetypes
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fontcreator import build as B
from fontcreator import layout as L
from fontcreator import project, scan

STATIC = Path(__file__).parent / "static"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silencieux, sauf erreurs
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("%s\n" % (fmt % args))

    # --- helpers ---
    def _send(self, code, body: bytes, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _file(self, path: Path, download_as=None):
        if not path.is_file():
            return self._send(404, b'{"error":"introuvable"}')
        ctype = {".otf": "font/otf", ".ttf": "font/ttf"}.get(path.suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extra = {"Content-Disposition": f'attachment; filename="{download_as}"'} if download_as else None
        self._send(200, path.read_bytes(), ctype, extra)

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    # --- routes ---
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._file(STATIC / "index.html")
            if u.path.startswith("/static/"):
                return self._file(STATIC / Path(u.path).name)
            if u.path == "/api/state":
                return self._json(project.status(int(q.get("t", 150))))
            if u.path == "/api/charsets":
                return self._json({k: {"label": v[0], "chars": v[1]} for k, v in L.CHARSETS.items()})
            if u.path == "/api/cell":
                return self._send(200, project.cell_png(int(q["i"]), int(q.get("t", 150))), "image/png")
            if u.path == "/api/template.pdf":
                return self._file(project.make_pdf(), "feuille-modele.pdf")
            if u.path == "/api/template.png":
                items = project.load_items()
                img = L.render_page(items, int(q.get("page", 1)), L.page_count(items), dpi=70)
                buf = io.BytesIO()
                img.save(buf, "PNG")
                return self._send(200, buf.getvalue(), "image/png")
            if u.path.startswith("/out/"):
                name = Path(u.path).name
                return self._file(project.OUT / name, name if "dl" in q else None)
            self._send(404, b'{"error":"introuvable"}')
        except Exception as e:  # noqa: BLE001
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/spec":
                d = json.loads(self._body())
                items = project.save_spec(d.get("groups", []), d.get("variants", 3))
                return self._json({"cells": len(items), "pages": L.page_count(items)})
            if u.path == "/api/upload":
                return self._json(project.ingest(self._body()))
            if u.path == "/api/reset":
                project.reset_pages()
                return self._json({"ok": True})
            if u.path == "/api/build":
                d = json.loads(self._body())
                s = B.Settings(**{k: v for k, v in d.items() if k in B.Settings.__dataclass_fields__})
                return self._json(project.build(s))
            self._send(404, b'{"error":"introuvable"}')
        except scan.ScanError as e:
            self._json({"error": str(e)}, 422)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Griffonne → {url}   (Ctrl+C pour arrêter)")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
