from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import tempfile
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from .task_context import build_task_request


class GeminiBlenderAgentAdapter:
    """Run an Antigravity Gemini agent against the configured Blender MCP."""

    def __init__(self, project_root: str | Path, timeout: int = 900):
        self.project_root = Path(project_root).resolve()
        self.timeout = timeout
        home = Path(os.environ.get("USERPROFILE", str(Path.home())))
        self.agentapi = home / ".gemini/antigravity/bin/agentapi.bat"
        self.antigravity = home / "AppData/Local/Programs/Antigravity/Antigravity.exe"
        self.projects_dir = home / ".gemini/config/projects"
        self.brain_dir = home / ".gemini/antigravity/brain"
        app_dir = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local"))) / "AI-Previz-Director"
        self.session_path = app_dir / "gemini_session.json"
        self._session_lock = threading.Lock()

    @staticmethod
    def _powershell_json(script: str) -> dict:
        # Force UTF-8 on the pipeline: on Chinese Windows the console default
        # (GBK/GB18030) would corrupt non-ASCII values (e.g. user paths) when
        # the subprocess side decodes with encoding="utf-8".
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise RuntimeError("未检测到 Antigravity 服务，请先打开 Antigravity")
        return json.loads(completed.stdout)

    def _discover_running_service(self) -> tuple[str, str]:
        info = self._powershell_json(
            "$p=Get-CimInstance Win32_Process | Where-Object {"
            "$_.Name -eq 'language_server.exe' -and $_.CommandLine -like '*Antigravity*'"
            "} | Select-Object -First 1; if(-not $p){exit 2}; "
            "$ports=Get-NetTCPConnection -State Listen -OwningProcess $p.ProcessId | "
            "Select-Object -ExpandProperty LocalPort; "
            "[pscustomobject]@{commandLine=$p.CommandLine;ports=@($ports)} | ConvertTo-Json -Compress"
        )
        match = re.search(r"--csrf_token\s+(\S+)", info.get("commandLine", ""))
        if not match:
            raise RuntimeError("无法读取 Antigravity 本地认证信息，请重启 Antigravity")
        for port in info.get("ports", []):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                    if response.status == 200:
                        return f"127.0.0.1:{port}", match.group(1)
            except (OSError, urllib.error.URLError):
                continue
        raise RuntimeError("Antigravity Agent API 未就绪，请稍后重试")

    def _discover_service(self) -> tuple[str, str]:
        try:
            return self._discover_running_service()
        except RuntimeError as initial_error:
            if not self.antigravity.is_file():
                raise initial_error
            subprocess.Popen(
                [str(self.antigravity), str(self.project_root)],
                cwd=self.project_root,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                time.sleep(0.5)
                try:
                    return self._discover_running_service()
                except RuntimeError:
                    continue
            raise RuntimeError("Antigravity 已启动，但 Agent API 在 20 秒内未就绪") from initial_error

    def _project_id(self) -> str:
        wanted = str(self.project_root).casefold()
        for path in self.projects_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            resources = data.get("projectResources", {}).get("resources", [])
            for resource in resources:
                uri = resource.get("folderUri", "")
                parsed = urlparse(uri)
                candidate = unquote(parsed.path).lstrip("/").replace("/", "\\")
                if candidate.casefold() == wanted:
                    return data.get("id") or path.stem
        raise RuntimeError("当前 Blender 工程尚未注册到 Antigravity")

    def _resolve_agentapi_cmd(self) -> list[str]:
        # On Windows, agentapi.bat forwards through cmd.exe which enforces an 8191 character
        # limit. If the underlying language_server.exe is discovered or specified in the batch file,
        # invoke it directly with 'agentapi' to allow standard CreateProcess limits (~32k chars).
        if os.name == "nt" and self.agentapi.suffix.lower() in {".bat", ".cmd"}:
            try:
                if self.agentapi.exists():
                    batch_content = self.agentapi.read_text(encoding="utf-8", errors="replace")
                    match = re.search(r'"([^"]*language_server\.exe)"', batch_content, re.IGNORECASE)
                    if match and Path(match.group(1)).exists():
                        return [match.group(1), "agentapi"]
            except Exception:
                pass
        return [str(self.agentapi)]

    def _run_agentapi_via_tempfile(self, args: list[str], env: dict[str, str]) -> dict:
        prompt_arg = args[-1]
        other_args = args[:-1]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
            tf.write(prompt_arg)
            temp_path = tf.name
        try:
            escaped_temp = temp_path.replace("'", "''")
            ps_script = (
                "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                f"$prompt = Get-Content -Raw -Encoding UTF8 '{escaped_temp}'; "
                f"& '{self.agentapi}' " + " ".join(f"'{a}'" for a in other_args) + " $prompt"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                cwd=self.project_root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = completed.stdout.strip() or completed.stderr.strip()
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                raise RuntimeError(f"Antigravity 返回了无法识别的结果: {raw[-800:]}") from exc
            if completed.returncode != 0 or payload.get("error"):
                raise RuntimeError(payload.get("error") or raw[-800:])
            return payload
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def _run_agentapi(self, args: list[str], env: dict[str, str]) -> dict:
        cmd_prefix = self._resolve_agentapi_cmd()
        total_len = sum(len(a) for a in args) + sum(len(c) for c in cmd_prefix)
        # Windows command line limit handling: If invoking a batch file on Windows
        # and total length exceeds 7500 chars, cmd.exe would truncate.
        # Fall back to PowerShell with temporary UTF-8 file (BUG-11).
        if os.name == "nt" and cmd_prefix == [str(self.agentapi)] and total_len > 7500:
            return self._run_agentapi_via_tempfile(args, env)

        completed = subprocess.run(
            [*cmd_prefix, *args],
            cwd=self.project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = completed.stdout.strip() or completed.stderr.strip()
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise RuntimeError(f"Antigravity 返回了无法识别的结果: {raw[-800:]}") from exc
        if completed.returncode != 0 or payload.get("error"):
            raise RuntimeError(payload.get("error") or raw[-800:])
        return payload

    def _transcript_row_count(self, conversation_id: str) -> int:
        transcript = self.brain_dir / conversation_id / ".system_generated/logs/transcript.jsonl"
        try:
            return len([line for line in transcript.read_text(encoding="utf-8").splitlines() if line])
        except OSError:
            return 0

    def _wait_for_result(self, conversation_id: str, after_row: int = 0) -> str:
        transcript = self.brain_dir / conversation_id / ".system_generated/logs/transcript.jsonl"
        deadline = time.monotonic() + self.timeout
        last_error = ""
        current_rows: list[dict] = []
        file_pos = 0

        while time.monotonic() < deadline:
            if transcript.exists():
                try:
                    size = transcript.stat().st_size
                    if size < file_pos:
                        file_pos = 0
                        current_rows.clear()
                    with open(transcript, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(file_pos)
                        new_lines = f.readlines()
                        file_pos = f.tell()
                    for line in new_lines:
                        line = line.strip()
                        if line:
                            try:
                                current_rows.append(json.loads(line))
                            except ValueError:
                                pass
                except OSError:
                    pass

                for row in reversed(current_rows[after_row:]):
                    content = row.get("content") or ""
                    if row.get("status") in {"ERROR", "FAILED"} and content:
                        last_error = content
                    if (
                        row.get("source") == "MODEL"
                        and row.get("type") == "PLANNER_RESPONSE"
                        and row.get("status") == "DONE"
                        and content.strip()
                        and not row.get("tool_calls")
                    ):
                        return content.strip()
            time.sleep(1)
        if last_error:
            raise RuntimeError(f"Gemini Agent 失败: {last_error[-1200:]}")
        raise TimeoutError("Gemini Agent 执行超时")

    def _load_conversation_id(self, project_id: str) -> str | None:
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        if data.get("project_id") != project_id:
            return None
        conversation_id = data.get("conversation_id")
        return conversation_id if isinstance(conversation_id, str) and conversation_id else None

    def _load_session_stage(self, project_id: str) -> str | None:
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        if data.get("project_id") != project_id:
            return None
        stage = data.get("stage")
        return stage if isinstance(stage, str) and stage else None

    def _save_session_stage(self, project_id: str, stage: str) -> None:
        data = {}
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = {}
        if data.get("project_id") != project_id:
            data = {"project_id": project_id}
        data["stage"] = stage
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _save_conversation_id(self, project_id: str, conversation_id: str) -> None:
        data = {}
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = {}
        if data.get("project_id") != project_id:
            data = {"project_id": project_id}
        data["conversation_id"] = conversation_id
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _new_conversation(self, instruction: str, project_id: str, env: dict[str, str]) -> tuple[str, int]:
        response = self._run_agentapi(
            ["new-conversation", "--model=pro", "--title=Blender Director", "--", instruction], env
        )
        conversation_id = response["response"]["newConversation"]["conversationId"]
        self._save_conversation_id(project_id, conversation_id)
        return conversation_id, 0

    def _send_to_persistent_conversation(
        self, bootstrap_instruction: str, user_instruction: str, project_id: str, env: dict[str, str],
        conversation_id: str | None = None,
    ) -> tuple[str, int, bool]:
        if not conversation_id:
            conversation_id = self._load_conversation_id(project_id)
        if not conversation_id:
            conversation_id, after_row = self._new_conversation(bootstrap_instruction, project_id, env)
            return conversation_id, after_row, False

        after_row = self._transcript_row_count(conversation_id)
        try:
            self._run_agentapi(["send-message", conversation_id, user_instruction], env)
            return conversation_id, after_row, True
        except RuntimeError:
            # Antigravity may discard a conversation after an update or manual deletion.
            # Recover once by creating a new persistent session instead of failing the panel.
            conversation_id, after_row = self._new_conversation(bootstrap_instruction, project_id, env)
            return conversation_id, after_row, False

    @staticmethod
    def _build_instruction(prompt: str) -> str:
        # agentapi.bat forwards through cmd.exe. Embedded newlines are truncated by
        # the batch-file argument boundary, so the full instruction must stay on one line.
        normalized_prompt = " ".join(prompt.splitlines()).strip()
        return (
            "你是嵌入Blender Director面板的Gemini Blender Agent。必须在当前已打开的Blender工程中真正执行具体任务，不能只解释步骤。"
            "所有场景读取和修改必须调用blender MCP；不要使用桌面鼠标键盘控制、浏览器或shell操作Blender，不要修改无关文件。"
            "绝对禁止调用bpy.ops.wm.read_factory_settings、read_homefile、open_mainfile、quit_blender、addon_disable，"
            "也不得注销任何插件或用工厂重置清空场景。需要清理时，只能选择性删除任务范围内的对象或集合，"
            "必须保留Blender MCP与Director服务。"
            "先调用get_addon_status和get_scene_info；调用get_scene_info以及其他要求user_prompt的工具时，必须把具体任务原文作为user_prompt。"
            "需要外部资产时，分别调用get_polyhaven_status、get_polypizza_status、get_sketchfab_status或生成器状态工具确认，"
            "不要仅凭get_addon_status是否列出资产能力来判断。已启用时优先搜索并导入合适的真实资产；搜索得到多个结果时，"
            "根据任务、授权、可下载状态、面数和风格自主选择最合适的一项，不要因为出现选择器提示就停止任务。"
            "只有状态工具明确不可用、搜索无合适结果或下载失败时才可改用execute_blender_code自建；必须在最终说明中如实指出降级。"
            "用户要求创建现实中有明确外观的物品时，成品必须一眼可识别，不能用单个立方体、球体或仅改比例的占位物冒充。"
            "车辆自建至少应有可辨识车身轮廓、车头/驾驶舱、车窗、车门、四个车轮和基础灯具；其他物品也应包含决定身份的主要结构。"
            "如果具体任务包含创建、修改、删除、动画、运镜、镜头切换或渲染，必须调用能产生对应实际效果的MCP工具，"
            "不得把状态检查和截图当作任务完成。完成后再次调用get_scene_info和get_viewport_screenshot核验；"
            "核验要检查身份可识别性、比例、位置、材质和是否穿插，不只是确认对象存在。"
            "只执行具体任务要求的改动，不得顺便重命名对象、改动其他属性或扩大任务范围。"
            "除非用户明确要求保存，否则不要覆盖.blend文件。最终用简短中文说明实际完成内容、使用的资产来源和任何真实限制。"
            f"【用户的具体任务，必须执行：{normalized_prompt}】"
        )

    def execute(self, prompt: str, reference_image: str | None = None, stage: str = "single") -> dict:
        if not self.agentapi.exists():
            raise RuntimeError("未找到 Antigravity Agent API，请安装并打开 Antigravity")
        address, token = self._discover_service()
        project_id = self._project_id()
        env = os.environ.copy()
        env.update(
            ANTIGRAVITY_LS_ADDRESS=address,
            ANTIGRAVITY_CSRF_TOKEN=token,
            ANTIGRAVITY_PROJECT_ID=project_id,
        )
        task_request = build_task_request(prompt, stage, reference_image)
        instruction = self._build_instruction(task_request)
        natural_instruction = task_request
        with self._session_lock:
            # Start a fresh conversation whenever the workflow stage changes:
            # long-lived sessions accumulate stale task context that dilutes
            # instruction adherence (agents start touching unrelated objects).
            session_stage = self._load_session_stage(project_id)
            if session_stage is not None and session_stage != stage:
                conversation_id = None
            else:
                conversation_id = self._load_conversation_id(project_id)
            conversation_id, after_row, reused = self._send_to_persistent_conversation(
                instruction, natural_instruction, project_id, env, conversation_id
            )
            self._save_session_stage(project_id, stage)
            message = self._wait_for_result(conversation_id, after_row)
        return {
            "ok": True,
            "agent": True,
            "agent_backend": "gemini",
            "conversation_id": conversation_id,
            "conversation_reused": reused,
            "message": message,
        }
