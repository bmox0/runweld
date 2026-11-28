"""Loopback delivery and per-user dashboard instance control."""

from base64 import b64encode
from hashlib import sha256
from html import escape
import hmac
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import stat
from threading import Thread
from urllib.parse import parse_qs
import webbrowser

from runweld_release import ReleaseError, atomic_write, project_root, regular_bytes
from ui.reader import project_snapshot, read_evidence

LOOPBACK = "127.0.0.1"
ADDRESS = re.compile(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,256}")
TOKEN = re.compile(r"[a-f0-9]{64}")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PREVIEW_CONTROLLER_HASH = b64encode(sha256((FRONTEND / "preview-controller.js").read_bytes()).digest()).decode("ascii")
FRONTEND_CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src data:; "
                f"script-src 'self' 'sha256-{PREVIEW_CONTROLLER_HASH}'; frame-src 'self' blob: data:; "
                "frame-ancestors 'none'; form-action 'none'; base-uri 'none'; object-src 'none'")
PREVIEW_CSP = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
               "frame-ancestors 'none'; form-action 'none'; base-uri 'none'")


def evidence_type(kind, body):
    if kind == "image":
        if body.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if body.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if body.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
            return "image/webp"
    elif kind == "html":
        return "text/html; charset=utf-8"
    elif kind in ("markdown", "diff", "text"):
        return "text/plain; charset=utf-8"
    return None


def proof(record, action, nonce):
    message = json.dumps([record["pid"], record["url"], record["project"], action, nonce]).encode()
    return hmac.digest(bytes.fromhex(record["token"]), message, "sha256").hex()


class Handler(BaseHTTPRequestHandler):
    timeout = 3

    def log_message(self, format, *args):
        pass

    def reply(self, status, body=b"", media="text/plain; charset=utf-8", *, csp=None):
        self.send_response(status)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(body)

    def local(self):
        url = self.server.instance["url"]
        return (self.headers.get_all("Host") == [url.removeprefix("http://")]
                and self.headers.get_all("Origin") in (None, [url])
                and self.headers.get("Sec-Fetch-Site") != "cross-site")

    def do_GET(self):
        if not self.local():
            return self.reply(403)
        path, _, query = self.path.partition("?")
        try:
            if path == "/api/project":
                body = json.dumps(project_snapshot(self.server.project)).encode()
                return self.reply(200, body, "application/json")
            if path == "/api/evidence":
                return self.evidence(query)
            if path in ("/", "/index.html"):
                body = (FRONTEND / "index.html").read_bytes().replace(
                    b"__RUNWELD_PROJECT__", escape(self.server.project.name).encode())
                return self.reply(200, body, "text/html; charset=utf-8", csp=FRONTEND_CSP)
            if re.fullmatch(r"/[A-Za-z0-9_-]+\.(?:css|m?js)", path):
                asset = FRONTEND / path[1:]
                media = "text/css" if asset.suffix == ".css" else "text/javascript"
                return self.reply(200, asset.read_bytes(), media)
        except FileNotFoundError:
            pass
        except (BrokenPipeError, ConnectionResetError):
            return
        except (OSError, ReleaseError, ValueError):
            return self.reply(500)
        return self.reply(404)

    def evidence(self, query):
        try:
            values = parse_qs(query, keep_blank_values=True, strict_parsing=True, errors="strict", max_num_fields=2)
        except ValueError:
            return self.reply(400)
        if values.keys() != {"task", "id"} or any(
            len(items) != 1 or not IDENTIFIER.fullmatch(items[0]) or items[0] in (".", "..")
            for items in values.values()
        ):
            return self.reply(400)
        if result := read_evidence(self.server.project, values["task"][0], values["id"][0]):
            kind, body = result
            if media := evidence_type(kind, body):
                return self.reply(200, body, media, csp=PREVIEW_CSP if kind == "html" else None)
        return self.reply(404)

    def do_POST(self):
        if not self.local():
            return self.reply(403)
        if self.path not in ("/_runweld/id", "/_runweld/down") or self.server.stopping:
            return self.reply(404)
        nonce = self.headers.get("X-Runweld-Nonce", "")
        received = self.headers.get("X-Runweld-Proof", "")
        record = self.server.instance
        if not TOKEN.fullmatch(nonce) or not TOKEN.fullmatch(received) or not hmac.compare_digest(
            proof(record, "request" + self.path, nonce), received
        ):
            return self.reply(404)
        result = proof(record, "response" + self.path, nonce).encode()
        if self.path == "/_runweld/down":
            self.server.stopping = True
            try:
                return self.reply(200, result)
            finally:
                self.server.shutdown()
        return self.reply(200, result)


def registry(*, create=False):
    cache = Path(os.environ.get("XDG_CACHE_HOME", ""))
    root = (cache if cache.is_absolute() else Path.home() / ".cache") / "runweld" / "ui"
    if create:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        info = root.lstat()
    except FileNotFoundError:
        return root
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ReleaseError(f"{root} must be a private directory owned by the current user")
    return root


def control(path, action):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            return None
        record = json.loads(regular_bytes(path))
        if (not isinstance(record, dict) or type(record.get("pid")) is not int or record["pid"] <= 0
                or path.stem != str(record["pid"])
                or not isinstance(record.get("url"), str) or not (address := ADDRESS.fullmatch(record["url"]))
                or not 0 < (port := int(address[1])) <= 65535
                or not isinstance(record.get("project"), str) or not Path(record["project"]).is_absolute()
                or not isinstance(record.get("token"), str) or not TOKEN.fullmatch(record["token"])):
            return None
        route = "/_runweld/" + action
        nonce = secrets.token_hex(32)
        connection = HTTPConnection(LOOPBACK, port, timeout=1)
        try:
            # A stale port can belong to another service, so the token never goes on the wire.
            connection.request("POST", route, headers={"X-Runweld-Nonce": nonce,
                               "X-Runweld-Proof": proof(record, "request" + route, nonce)})
            reply = connection.getresponse()
            if reply.status == 200 and hmac.compare_digest(
                reply.read(65), proof(record, "response" + route, nonce).encode()
            ):
                return record
        finally:
            connection.close()
    except (OSError, ValueError, HTTPException, RecursionError):
        return None
    return None


def open_browser(url):
    try:
        webbrowser.open(url)
    except (OSError, ValueError, webbrowser.Error):
        pass


def up():
    if not (project := project_root(Path.cwd())):
        raise ReleaseError("run `runweld ui up` from a Git checkout or its task worktree")
    project = project.resolve()
    root = registry(create=True)
    with ThreadingHTTPServer((LOOPBACK, 0), Handler) as server:
        pid = os.getpid()
        url = f"http://{LOOPBACK}:{server.server_port}"
        server.project = project
        server.stopping = False
        server.instance = {"pid": pid, "url": url, "project": str(project), "token": secrets.token_hex(32)}
        record = root / f"{pid}.json"
        try:
            atomic_write(record, json.dumps(server.instance).encode(), mode=0o600)
            print(f"URL: {url}\nPID: {pid}", flush=True)
            Thread(target=open_browser, args=(url,), daemon=True).start()
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            pass
        finally:
            record.unlink(missing_ok=True)
    return 0


def command(args):
    try:
        if args.command == "up":
            return up()
        root = registry()
        if args.command == "list":
            instances = [record for path in root.glob("*.json") if (record := control(path, "id"))]
            for record in sorted(instances, key=lambda item: item["pid"]):
                print(f"{record['pid']}\t{record['url']}\t{record['project']}")
            if not instances:
                print("No running Runweld dashboards.")
            return 0
        if control(root / f"{args.pid}.json", "down"):
            print(f"Stopped Runweld dashboard {args.pid}.")
            return 0
        raise ReleaseError(f"No running Runweld dashboard with PID {args.pid}; see `runweld ui list`")
    except OSError as error:
        raise ReleaseError(f"dashboard: {error}") from None
