import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.blender_agent import BlenderAgentAdapter


class BlenderAgentTests(unittest.TestCase):
    def test_reference_image_is_passed_as_real_codex_image_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "city.png"
            image.write_bytes(b"image")
            adapter = BlenderAgentAdapter(root)
            captured = {}

            def fake_run(command, **_kwargs):
                captured["command"] = command
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text("done", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("adapters.blender_agent.subprocess.run", side_effect=fake_run):
                result = adapter.execute("按图搭建", reference_image=str(image), stage="layout")

            command = captured["command"]
            self.assertEqual(result["message"], "done")
            self.assertIn("-i", command)
            self.assertEqual(command[command.index("-i") + 1], str(image.resolve()))
            self.assertIn("白模布局阶段", command[-1])
            self.assertIn("Never call bpy.ops.wm.read_factory_settings", command[-1])


if __name__ == "__main__":
    unittest.main()
