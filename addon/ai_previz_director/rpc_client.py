from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .dispatcher import DispatchRequest, submit

def _local_appdata() -> str:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return configured
    return os.path.join(os.path.expanduser("~"), "AppData", "Local")


APP_DIR = os.path.join(_local_appdata(), "AI-Previz-Director")
RUNTIME_PATH = os.path.join(APP_DIR, "runtime.json")
UI_RESULTS: queue.Queue[dict] = queue.Queue()


def load_runtime() -> dict:
    try:
        with open(RUNTIME_PATH, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"host": "127.0.0.1", "port": 8765, "token": ""}


def _request(method: str, path: str, payload: dict | None = None, timeout: float = 5.0) -> dict | None:
    cfg = load_runtime()
    url = f"http://{cfg.get('host', '127.0.0.1')}:{cfg.get('port', 8765)}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "X-AI-Previz-Token": cfg.get("token", "")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bridge HTTP {exc.code}: {body}") from exc


class BridgeClient:
    def __init__(self):
        self.client_id = f"blender-{uuid.uuid4()}"
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.connected = False

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="AI-Previz-Bridge-Poll", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.connected = False

    def _post_result(self, request_id: str, result: dict):
        def worker():
            try:
                _request("POST", "/blender/result", {"client_id": self.client_id, "request_id": request_id, "result": result}, 10)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                _request("POST", "/blender/register", {"client_id": self.client_id}, 3)
                self.connected = True
                query = urllib.parse.urlencode({"client_id": self.client_id})
                item = _request("GET", f"/blender/next?{query}", timeout=3)
                if item:
                    submit(DispatchRequest(item["request_id"], item["method"], item.get("payload", {}), lambda result, rid=item["request_id"]: self._post_result(rid, result)))
            except Exception:
                self.connected = False
                time.sleep(1.0)


CLIENT = BridgeClient()


def send_prompt_async(prompt: str, mode: str):
    def worker():
        try:
            result = _request("POST", "/execute", {"prompt": prompt, "mode": mode}, timeout=180)
            UI_RESULTS.put(result or {"ok": False, "error": "Empty bridge response"})
        except Exception as exc:
            UI_RESULTS.put({"ok": False, "error": str(exc)})
    threading.Thread(target=worker, name="AI-Previz-Prompt", daemon=True).start()

