import unittest

from adapters.quick_parser import compile_quick


CONTEXT = {
    "scene": {"active_object": "Girl_Main"},
    "actors": [{"id": "actor_girl_01", "name": "Girl_Main"}],
    "current_shot": {"subject": "actor_girl_01"},
}


class QuickParserTests(unittest.TestCase):
    def test_lens(self):
        intent = compile_quick("当前摄影机改成 55mm", CONTEXT)
        self.assertEqual(intent["operations"][0]["lens_mm"], 55)

    def test_speed_semantics(self):
        intent = compile_quick("人物走慢到原来的 0.7 倍", CONTEXT)
        self.assertEqual(intent["operations"][0]["speed_factor"], 0.7)

    def test_undo(self):
        self.assertEqual(compile_quick("撤销刚才修改", CONTEXT)["operations"][0]["type"], "previz_undo")

    def test_material_color_by_alias(self):
        context = {"actors": [], "products": [], "entities": [{"id": "car_red", "name": "CAR_Red", "aliases": ["汽车", "红车"]}]}
        operation = compile_quick("汽车改成绿色", context)["operations"][0]
        self.assertEqual(operation["type"], "material_set_color")
        self.assertEqual(operation["target"], "car_red")
        self.assertGreater(operation["green"], operation["red"])


if __name__ == "__main__":
    unittest.main()
