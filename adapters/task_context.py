from __future__ import annotations


STAGE_INSTRUCTIONS = {
    "single": "完成用户要求的整个任务，但仍要分成小步骤执行并逐步核验。",
    "layout": (
        "当前只执行白模布局阶段：在新的专用集合中建立道路、地块、建筑占地、主要高度和空间关系。"
        "不得清空场景或删除现有对象；需要隔离旧内容时只能隐藏原集合。"
        "不要进入最终资产、精细材质、灯光或渲染；完成多视角核验后停止。"
    ),
    "detail": (
        "当前只执行资产细化阶段：保留已经确认的道路、地块、建筑占地和高度关系，"
        "替换或补充合适资产并降低重复感；完成核验后停止，不进行最终灯光渲染。"
    ),
    "finish": (
        "当前执行最终表现阶段：保留已确认布局，完善材质、灯光、摄像机、运镜和渲染设置，"
        "并从鸟瞰、街道和平视行进视角完成视觉核验。"
    ),
}


def build_task_request(prompt: str, stage: str = "single", reference_image: str | None = None) -> str:
    normalized = " ".join(prompt.splitlines()).strip()
    stage_instruction = STAGE_INSTRUCTIONS.get(stage, STAGE_INSTRUCTIONS["single"])
    parts = [
        f"任务阶段要求：{stage_instruction}",
        "层级命名规则：新建或导入的复杂物体必须有一个顶层Empty父对象，命名为“父级_中文物体名”，"
        "所有部件放在其下；不要为了翻译而改动资产原有子部件名称、骨骼、约束或材质名称。",
    ]
    if reference_image:
        parts.append(
            "参考图绝对路径："
            f"{reference_image}。必须真正分析这张图，而不是只根据文件名猜测。"
            "若当前 Agent 支持直接图像输入，应直接观察；否则必须通过 Blender MCP 将它加载为参考图，"
            "再用视口截图观察布局、比例、轮廓、道路和地标。"
        )
    parts.append(f"用户任务：{normalized}")
    return " ".join(parts)
