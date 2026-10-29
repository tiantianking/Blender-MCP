import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from adapters.gemini_agent import GeminiBlenderAgentAdapter


class GeminiAgentInstructionTests(unittest.TestCase):
    def test_asset_workflow_and_quality_gate_are_preserved_on_one_line(self):
        instruction = GeminiBlenderAgentAdapter._build_instruction(
            "放一辆校车\n并按人物比例调整"
        )

        self.assertNotIn("\n", instruction)
        self.assertIn("get_polypizza_status", instruction)
        self.assertIn("优先搜索并导入合适的真实资产", instruction)
        self.assertIn("不能用单个立方体", instruction)
        self.assertIn("车窗、车门、四个车轮", instruction)
        self.assertIn("绝对禁止调用bpy.ops.wm.read_factory_settings", instruction)
        self.assertIn("只能选择性删除任务范围内的对象或集合", instruction)
        self.assertIn("放一辆校车 并按人物比例调整", instruction)

    def test_reuses_saved_conversation_and_waits_only_for_new_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = GeminiBlenderAgentAdapter(Path(temp))
            adapter.session_path = Path(temp) / "session.json"
            adapter.brain_dir = Path(temp) / "brain"
            adapter._save_conversation_id("project-1", "conversation-1")
            transcript = adapter.brain_dir / "conversation-1" / ".system_generated/logs/transcript.jsonl"
            transcript.parent.mkdir(parents=True)
            transcript.write_text('{"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","content":"old"}\n', encoding="utf-8")

            with patch.object(adapter, "_run_agentapi", return_value={}) as run:
                conversation_id, after_row, reused = adapter._send_to_persistent_conversation(
                    "bootstrap", "校车放错了位置", "project-1", {}
                )

            self.assertEqual(conversation_id, "conversation-1")
            self.assertEqual(after_row, 1)
            self.assertTrue(reused)
            self.assertEqual(
                run.call_args.args[0],
                ["send-message", "conversation-1", "校车放错了位置"],
            )

    def test_starts_antigravity_when_service_is_not_running(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = GeminiBlenderAgentAdapter(Path(temp))
            adapter.antigravity = Path(temp) / "Antigravity.exe"
            adapter.antigravity.write_bytes(b"exe")
            with (
                patch.object(
                    adapter,
                    "_discover_running_service",
                    side_effect=[RuntimeError("not running"), ("127.0.0.1:9999", "token")],
                ),
                patch("adapters.gemini_agent.subprocess.Popen") as launch,
                patch("adapters.gemini_agent.time.sleep"),
            ):
                result = adapter._discover_service()

            self.assertEqual(result, ("127.0.0.1:9999", "token"))
            launch.assert_called_once()

    def test_run_agentapi_resolves_direct_exe_or_tempfile(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = GeminiBlenderAgentAdapter(Path(temp))
            # Test direct exe resolution logic
            adapter.agentapi = Path(temp) / "agentapi.bat"
            adapter.agentapi.write_text(
                '@echo off\n"C:\\fake\\language_server.exe" agentapi %*\n', encoding="utf-8"
            )
            with patch("adapters.gemini_agent.Path.exists", return_value=True):
                cmd = adapter._resolve_agentapi_cmd()
                self.assertEqual(cmd, ["C:\\fake\\language_server.exe", "agentapi"])

    def test_wait_for_result_incremental_read(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = GeminiBlenderAgentAdapter(Path(temp), timeout=2)
            adapter.brain_dir = Path(temp) / "brain"
            transcript = adapter.brain_dir / "conv-test" / ".system_generated/logs/transcript.jsonl"
            transcript.parent.mkdir(parents=True)
            # Write initial lines
            transcript.write_text(
                '{"source":"USER","type":"USER_INPUT","status":"DONE","content":"hello"}\n'
                '{"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","content":"result payload"}\n',
                encoding="utf-8",
            )
            result = adapter._wait_for_result("conv-test", after_row=1)
            self.assertEqual(result, "result payload")


if __name__ == "__main__":
    unittest.main()
