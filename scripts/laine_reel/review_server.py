"""A tiny local web server for the review page (Python standard library).

Only listens on 127.0.0.1 (this computer). Serves:
    /                 the review page (tools/review/index.html)
    /app/<file>       its script and styles
    /api/reel         everything the page shows (review.reel_data)
    /api/draft  POST  autosave (review/draft.json)
    /api/feedback POST save feedback (review/feedback-<time>.json)
    /media/<path>     videos inside the reel folder, with byte ranges so the
                      player can seek
Nothing outside the reel folder and tools/review/ can be read, and the only
files it writes are in the reel's review/ folder.
"""

import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import brand, config, library, review, versions

APP_DIR = config.PROJECT_ROOT / "tools" / "review"
MAX_BODY = 5_000_000
MAX_UPLOAD = 41 * 1024 * 1024
MIME = {".ttf": "font/ttf", ".otf": "font/otf", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".png": "image/png", ".jpg": "image/jpeg"}


def _inside(base, rel):
    """Resolve rel under base, refusing anything that escapes it."""
    base = Path(base).resolve()
    p = (base / rel).resolve()
    return p if p == base or base in p.parents else None


def make_handler(reel):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LaineReview/1"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, code, body=b"", ctype="application/json", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode())

        def _file(self, path):
            if not path or not path.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            size = path.stat().st_size
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a) if a else max(0, size - int(b))
                end = int(b) if (a and b) else size - 1
                end = min(end, size - 1)
                if start > end:
                    return self._send(416, b"", "text/plain",
                                      {"Content-Range": f"bytes */{size}"})
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                if self.command == "HEAD":
                    return
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(1 << 20, left))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        left -= len(chunk)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                try:
                    while chunk := f.read(1 << 20):
                        self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            url = urlparse(self.path)
            p = unquote(url.path)
            if p in ("/", "/index.html"):
                return self._file(APP_DIR / "index.html")
            if p.startswith("/app/"):
                return self._file(_inside(APP_DIR, p[5:]))
            if p == "/api/brand":
                return self._json(brand_settings(reel))
            if p == "/api/library":
                return self._json({"items": library.items(include_archived=True),
                                   "sound_events": brand.SOUND_EVENTS,
                                   "image_categories": library.IMAGE_CATEGORIES,
                                   "sound_categories": library.SOUND_CATEGORIES})
            if p.startswith("/library/file/"):
                a = library.get(p[14:])
                f = _inside(library.library_dir(), a["file"]) if a else None
                if f and f.suffix.lower() in MIME:
                    mimetypes.add_type(MIME[f.suffix.lower()], f.suffix.lower())
                return self._file(f)
            if p == "/api/status":
                return self._json(versions.get_status(reel))
            if p.startswith("/download/"):
                f = _inside(reel.output / "approved", p[10:])
                if not f or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(f.stat().st_size))
                self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
                self.end_headers()
                with open(f, "rb") as fh:
                    try:
                        while chunk := fh.read(1 << 20):
                            self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                return
            if p == "/api/reel":
                try:
                    return self._json(review.reel_data(reel))
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 500)
            if p.startswith("/sfx/") and p[5:] in ("pop", "whoosh", "ding", "click"):
                from .sfx import resolve
                f = resolve(p[5:])
                return self._file(Path(f) if f else None)
            if p.startswith("/media/"):
                rel = p[7:]
                if not rel.lower().endswith((".mp4", ".png", ".jpg")):
                    return self._send(403, b"forbidden", "text/plain")
                return self._file(_inside(reel.root, rel))
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            p = url.path
            n = int(self.headers.get("Content-Length") or 0)
            if p == "/api/library/upload":
                from urllib.parse import parse_qs
                if n <= 0 or n > MAX_UPLOAD:
                    return self._json({"error": "The file is empty or over 40 MB."}, 400)
                qs = parse_qs(url.query)
                fname = unquote(self.headers.get("X-Filename") or qs.get("filename", [""])[0])
                try:
                    a = library.add(Path(fname).name, self.rfile.read(n),
                                    name=(qs.get("name") or [None])[0],
                                    category=(qs.get("category") or [None])[0])
                except library.LibraryError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "asset": a})
            if n <= 0 or n > MAX_BODY:
                return self._json({"error": "empty or too large"}, 400)
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                return self._json({"error": "not JSON"}, 400)
            if p == "/api/draft":
                review.save_draft(reel, data)
                return self._json({"ok": True})
            if p == "/api/feedback":
                path = review.save_feedback(reel, data)
                versions.set_status(reel, "waiting", "Feedback saved. Waiting for Claude to apply it.",
                                    version=versions.current_number(reel))
                return self._json({"ok": True, "file": str(path.relative_to(reel.root))})
            if p == "/api/library/update":
                try:
                    a = library.update(data["id"], name=data.get("name"),
                                       category=data.get("category"), archived=data.get("archived"))
                except (KeyError, library.LibraryError) as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "asset": a})
            if p == "/api/brand":
                try:
                    parsed = brand.save_settings(data.get("changes") or {}, data.get("scope"),
                                                 reel.root)
                except (brand.AnswerError, ValueError) as e:
                    return self._json({"error": str(e)}, 400)
                review.mark_settings_changed(reel, parsed, data.get("scope"))
                where = "your saved defaults" if data.get("scope") == "default" else "this reel only"
                versions.set_status(reel, "waiting", f"Brand settings saved for {where}. "
                                    "Tell Claude “apply my review” to see them.",
                                    version=versions.current_number(reel))
                return self._json({"ok": True, "saved": sorted(parsed)})
            if p == "/api/brand/history/restore":
                try:
                    brand.restore_history(str(data.get("id") or ""))
                except brand.AnswerError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True})
            if p == "/api/brand/use-defaults":
                try:
                    changed = brand.use_current_defaults(reel.root)
                except brand.AnswerError as e:
                    return self._json({"error": str(e)}, 400)
                if changed:
                    review.mark_settings_changed(reel, changed, "default")
                    versions.set_status(reel, "waiting", "This reel now uses your current saved "
                                        "defaults. Tell Claude “apply my review” to see them.",
                                        version=versions.current_number(reel))
                return self._json({"ok": True, "changed": changed})
            if p == "/api/restore":
                try:
                    n = versions.restore(reel, int(data["version"]),
                                         reel.output / f"{reel.slug}-final.mp4")
                except (KeyError, ValueError) as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "version": n})
            if p == "/api/finalize":
                try:
                    dest = versions.approve(reel, int(data["version"]))
                except (KeyError, ValueError, FileNotFoundError) as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "file": f"output/approved/{dest.name}",
                                   "download": f"/download/{dest.name}"})
            return self._json({"error": "unknown"}, 404)

    return Handler


PIDFILE = config.PROJECT_ROOT / "workspace" / ".review-server.json"


def stop_previous():
    """Stop this project's previous review server (one reel at a time on the
    same address). Only a process started by `reel.py review` is touched."""
    import signal
    import subprocess
    import time
    if not PIDFILE.exists():
        return None
    try:
        info = json.loads(PIDFILE.read_text())
        pid = int(info["pid"])
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True).stdout
        if "reel.py" in cmd and " review" in cmd and pid != os.getpid():
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                time.sleep(0.1)
                if subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode:
                    break
            return info
    except (ValueError, KeyError, OSError):
        pass
    finally:
        if PIDFILE.exists():
            PIDFILE.unlink()
    return None


def brand_settings(reel):
    """Everything the Brand settings panel shows."""
    defaults = (config.load_brand() or {}).get("answers", {})
    base = (brand.reel_base(reel.root) or {}).get("answers", {})
    mine = brand.reel_answers(reel.root)
    eff = brand.effective(reel.root) or {}
    qs = [{"id": q["id"], "section": q["section"], "prompt": q["prompt"], "kind": q["kind"],
           "options": q["options"]} for q in brand.QUESTIONS if q["id"] in brand.EDITABLE]
    hist = [{k: e[k] for k in ("id", "saved_at", "replaced_by", "changed_after", "differs_from_now")}
            for e in brand.history()]
    return {"defaults": defaults, "reel": mine, "effective": dict(base, **mine),
            "snapshot": brand.snapshot_info(reel.root), "history": hist,
            "neutral": not brand.is_onboarded(),
            "questions": qs, "sound_events": brand.SOUND_EVENTS,
            "logo_positions": brand.LOGO_POSITIONS,
            "fonts_in_use": {k: eff.get("fonts", {}).get(k) for k in ("headline", "body", "graphics")}}


def serve(reel, port=8765, open_browser=True, ready=None):
    """Run until Ctrl+C. Replaces this project's previous review server, then
    takes `port` (or the next free one)."""
    stop_previous()
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(reel))
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No free port for the review page.")
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    PIDFILE.parent.mkdir(exist_ok=True)
    PIDFILE.write_text(json.dumps({"pid": os.getpid(), "port": httpd.server_address[1],
                                   "reel": str(reel.root)}))
    if ready:
        ready(url, httpd)
    if open_browser and not os.environ.get("LAINE_NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return url
