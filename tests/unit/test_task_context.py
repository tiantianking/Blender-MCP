import tempfile
import unittest
from pathlib import Path

from adapters.task_context import build_task_request
from bridge.server import validate_reference_image


class TaskContextTests(unittest.TestCase):
    def test_layout_stage_and_reference_are_explicit(self):
        request = build_task_request("按图搭建\n城市", "layout", r"D:\refs\city.png")
        self.assertIn("白模布局阶段", request)
        self.assertIn("不得清空场景或删除现有对象", request)
        self.assertIn("父级_中文物体名", request)
        self.assertIn("不要为了翻译而改动资产原有子部件名称", request)
        self.assertIn(r"D:\refs\city.png", request)
        self.assertIn("必须真正分析这张图", request)
        self.assertIn("按图搭建 城市", request)

    def test_reference_image_requires_supported_existing_absolute_file(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "reference.png"
            image.write_bytes(b"not decoded here")
            self.assertEqual(validate_reference_image(str(image)), str(image.resolve()))
            with self.assertRaisesRegex(ValueError, "不支持"):
                unsupported = Path(temp) / "reference.txt"
                unsupported.write_text("x", encoding="utf-8")
                validate_reference_image(str(unsupported))


if __name__ == "__main__":
    unittest.main()
