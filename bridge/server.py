from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import queue
import secrets
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from adapters.codex_adapter import CodexAdapter
from adapters.blender_agent import BlenderAgentAdapter
from adapters.gemini_agent import GeminiBlenderAgentAdapter
from adapters.quick_parser import compile_quick

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AI-Previz-Director"
RUNTIME_PATH = APP_DIR / "runtime.json"
LOG_PATH = ROOT / "logs" / "bridge.log"


def load_or_create_runtime(port: int) -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    current = {}
    if RUNTIME_PATH.exists():
        try:
            current = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
    runtime = {"host": "127.0.0.1", "port": port, "token": current.get("token") or secrets.token_urlsafe(32)}
    RUNTIME_PATH.write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    return runtime


@dataclass
class BrokerRequest:
    request_id: str
    method: str
    payload: dict
    created_at: float = field(default_factory=time.time)
    event: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    cancelled: bool = False


class Broker:
    def __init__(self):
        self.pending: queue.Queue[BrokerRequest] = queue.Queue()
        self.requests: dict[str, BrokerRequest] = {}
        self.clients: dict[str, float] = {}
        self.lock = threading.Lock()
        self.mutation_lock = threading.Lock()

    def register(self, client_id: str):
        self.clients[client_id] = time.time()

    def next(self, client_id: str) -> BrokerRequest | None:
        self.register(client_id)
        try:
            while True:
                item = self.pending.get_nowait()
                if not item.cancelled:
                    return item
        except queue.Empty:
            return None

    def submit(self, method: str, payload: dict, timeout: float = 120) -> dict:
        req = BrokerRequest(str(uuid.uuid4()), method, payload)
        with self.lock:
            self.requests[req.request_id] = req
        self.pending.put(req)
        if not req.event.wait(timeout):
            req.cancelled = True
            raise TimeoutError(f"Blender request timed out: {method}")
        if req.result is None:
            raise RuntimeError("Blender returned no result")
        return req.result

    def complete(self, request_id: str, result: dict):
        req = self.requests.get(request_id)
        if req:
            req.result = result
            req.event.set()

    def cancel(self, request_id: str) -> bool:
        req = self.requests.get(request_id)
        if not req or req.event.is_set():
            return False
        req.cancelled = True
        req.event.set()
        return True

    def status(self) -> dict:
        now = time.time()
        active = [cid for cid, seen in self.clients.items() if now - seen < 5]
        return {"blender_connected": bool(active), "clients": active, "queued": self.pending.qsize()}


BROKER = Broker()
ADAPTER = CodexAdapter(ROOT)
AGENT = BlenderAgentAdapter(ROOT)
GEMINI_AGENT = GeminiBlenderAgentAdapter(ROOT)
RUNTIME = {}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".exr", ".hdr"}


def validate_reference_image(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("参考图必须使用绝对路径")
    if not path.is_file():
        raise ValueError(f"找不到参考图：{path}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的参考图格式：{path.suffix}")
    return str(path.resolve())


def new_checkpoint_path() -> Path:
    directory = APP_DIR / "checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return directory / f"previz-{stamp}-{uuid.uuid4().hex[:8]}.blend"


def blender_mcp_is_listening() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9876), timeout=0.3):
            return True
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "AIPrevizBridge/0.4.0"
    legacy_warning_emitted = False

    def log_message(self, fmt, *args):
        logging.info("%s %s", self.client_address[0], fmt % args)

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise ValueError("Request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def _authorized(self) -> bool:
        if self.path == "/health":
            return True
        origin = self.headers.get("Origin")
        if origin and not (origin.startswith("http://127.0.0.1") or origin.startswith("http://localhost")):
            return False
        received = self.headers.get("X-AI-Previz-Token", "")
        authorized = secrets.compare_digest(received, RUNTIME["token"])
        # Older Blender sessions can keep the pre-token rpc_client module in
        # memory even after the installed add-on has been upgraded.  The bridge
        # only listens on loopback, so keep those already-running panels usable
        # until Blender is restarted.  A non-empty but incorrect token is still
        # rejected.
        legacy_loopback_path = self.path.startswith(
            (
                "/blender/register",
                "/blender/next",
                "/blender/result",
                "/status",
                "/execute",
                "/compile",
                "/director",
                "/cancel",
                "/logs",
            )
        )
        if not authorized and not received and legacy_loopback_path and self.client_address[0] in {"127.0.0.1", "::1"}:
            if not Handler.legacy_warning_emitted:
                logging.warning("Accepted tokenless legacy panel client on loopback; restart Blender to restore token authentication")
                Handler.legacy_warning_emitted = True
            return True
        if not authorized:
            fingerprint = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:10] if value else "empty"
            logging.warning(
                "Authentication mismatch path=%s received=%s expected=%s",
                self.path,
                fingerprint(received),
                fingerprint(RUNTIME["token"]),
            )
        return authorized

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json(403, {"ok": False, "error": "Forbidden"})
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "ai-previz-bridge", "version": "0.4.0"})
            return
        if not self._require_auth():
            return
        if parsed.path == "/status":
            self._json(200, {"ok": True, **BROKER.status(), "codex_available": bool(os.environ.get("PATH"))})
            return
        if parsed.path == "/blender/next":
            client_id = parse_qs(parsed.query).get("client_id", [""])[0]
            if not client_id:
                self._json(400, {"ok": False, "error": "client_id required"})
                return
            item = BROKER.next(client_id)
            if not item:
                self.send_response(204)
                self.end_headers()
            else:
                self._json(200, {"request_id": item.request_id, "method": item.method, "payload": item.payload})
            return
        if parsed.path == "/logs":
            lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-100:] if LOG_PATH.exists() else []
            self._json(200, {"ok": True, "lines": lines})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self._require_auth():
            return
        try:
            payload = self._read()
            if parsed.path == "/blender/register":
                BROKER.register(payload["client_id"])
                self._json(200, {"ok": True})
                return
            if parsed.path == "/blender/result":
                BROKER.complete(payload["request_id"], payload["result"])
                self._json(200, {"ok": True})
                return
            if parsed.path == "/cancel":
                ok = BROKER.cancel(payload["request_id"])
                self._json(200, {"ok": ok})
                return
            if parsed.path == "/compile":
                context = payload.get("context") or BROKER.submit("get_state", {}, 15).get("state", {})
                quick_mode = payload.get("mode") == "quick"
                intent = compile_quick(payload["prompt"], context) if quick_mode else None
                if quick_mode and not intent:
                    self._json(422, {"ok": False, "error": "Quick 模式不支持这条指令，请改用 Director 模式"})
                    return
                intent = intent or ADAPTER.compile_intent(payload["prompt"], context, payload.get("screenshot"))
                self._json(200, {"ok": True, "intent": intent})
                return
            if parsed.path == "/execute":
                if payload.get("mode") == "director":
                    backend = payload.get("agent", "codex")
                    if backend not in {"codex", "gemini"}:
                        self._json(400, {"ok": False, "error": f"Unknown agent backend: {backend}"})
                        return
                    with BROKER.mutation_lock:
                        reference_image = validate_reference_image(payload.get("reference_image"))
                        stage = payload.get("workflow_stage", "single")
                        if stage not in {"single", "layout", "detail", "finish"}:
                            raise ValueError(f"未知任务阶段：{stage}")
                        if not blender_mcp_is_listening():
                            mcp_status = BROKER.submit("ensure_blender_mcp", {}, 30)
                            if not mcp_status.get("ok") or not blender_mcp_is_listening():
                                raise RuntimeError(
                                    "Blender MCP 未运行。请点击 MCP for Blender 面板中的 Start MCP Server；"
                                    "若按钮无效，请重启 Blender 以加载自动恢复功能。"
                                )
                        checkpoint_path = new_checkpoint_path()
                        checkpoint = BROKER.submit(
                            "create_checkpoint",
                            {"output_path": str(checkpoint_path)},
                            300,
                        )
                        if not checkpoint.get("ok"):
                            raise RuntimeError(checkpoint.get("error", "创建恢复点失败"))
                        result = (GEMINI_AGENT if backend == "gemini" else AGENT).execute(
                            payload["prompt"],
                            reference_image=reference_image,
                            stage=stage,
                        )
                        result["checkpoint"] = checkpoint.get("checkpoint", str(checkpoint_path))
                    self._json(200, result)
                    return
                with BROKER.mutation_lock:
                    context_result = BROKER.submit("get_state", {}, 15)
                    if not context_result.get("ok"):
                        raise RuntimeError(context_result.get("error", "Failed to read Blender state"))
                    intent = compile_quick(payload["prompt"], context_result["state"])
                    if not intent:
                        self._json(422, {"ok": False, "error": "Quick 模式不支持这条指令，请改用 Director 模式"})
                        return
                    result = BROKER.submit("execute_intent", {"intent": intent, "prompt": payload["prompt"]}, 60)
                self._json(200 if result.get("ok") else 422, {**result, "intent": intent})
                return
            if parsed.path == "/director":
                with BROKER.mutation_lock:
                    result = BROKER.submit(payload.get("method", "execute_intent"), payload.get("payload", {}), 120)
                self._json(200 if result.get("ok") else 422, result)
                return
            self._json(404, {"ok": False, "error": "Not found"})
        except Exception as exc:
            logging.exception("Request failed: %s", parsed.path)
            self._json(500, {"ok": False, "error": str(exc), "error_type": type(exc).__name__})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    global RUNTIME
    RUNTIME = load_or_create_runtime(args.port)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    logging.info("Bridge listening on 127.0.0.1:%s", args.port)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
