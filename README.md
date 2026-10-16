# AI Previz Director for Blender 5.2

本机优先的 Blender 预演控制层与 Agent 结构化工具体系。Quick 把常用自然语言编译成受限 JSON Intent；Director Agent 为 Codex / Antigravity Gemini 等 AI Agent 提供高可靠、结构化、支持原子回滚的 Blender 场景搭建、修改与核验工具集。

---

## 核心架构与工具能力

### 1. 结构化场景树与层级拓扑 (P0)
- `previz_get_scene_graph(cursor, limit, collection, include_hidden, include_materials)`:
  - **分页与防截断**：基于稳定游标与确定性排序分页（默认单页 200 项，支持 1~1000 项），返回 `total`、`cursor`、`next_cursor` 与明确的 `truncated` 标志，杜绝大型城市场景中对象静默遗漏。
  - **丰富对象元数据**：每个对象均输出稳定引用、名称、类型、父级对象（Parent）、直接子级列表（Children）、所属集合列表（Collections）、本地位置/旋转/缩放、世界变换矩阵（4x4）、对象尺寸、世界空间 AABB 包围盒（含 `min`、`max`、`center`、`size`）、可见性状态、材质列表、网格顶点与多边形面数，以及持久语义标签。

### 2. 通用安全变换与批量原子执行 (P0)
- `previz_set_object_transform(reference, location, rotation, scale, mode, space, keyframe, frame)`:
  - **灵活引用**：支持 Blender 对象名、持久语义 ID（如 `actor_girl_01`）或中文父级名称。
  - **世界 / 本地坐标系解算**：支持 `absolute` 与 `relative` 模式。针对有父级绑定的子对象（Parented Objects），写入世界坐标时自动逆向求解局部坐标，确保父子关系、约束和骨骼不受破坏。
  - **可选打帧**：支持指定帧或当前帧的安全关键帧记录（`keyframe=True`）。
- `previz_batch_transform(changes)`:
  - **全量前置校验**：执行前必须通过全部目标对象的存在性与参数合法性检查；任一目标非法时立即中止。
  - **原子失败回滚**：进入 Director 事务机制，若执行失败立即将所有已变动对象精确还原回原世界/本地变换。

### 3. 多视角视觉核验 (P0)
- `previz_capture_views(views, camera, output_dir)`:
  - **五视角全景核验**：自动批量捕获 `top`（顶视）、`front`（前视）、`right`（侧视）、`perspective`（透视）及 `camera`（当前或指定相机视角）。
  - **非侵入式渲染**：采用轻量级 Workbench 引擎进行清晰无 UI 静帧渲染，计算场景整体包围盒自适应机位距离，完全兼容后台 Headless 运行模式。
  - **严格现场恢复**：渲染完成后在 `finally` 块中立即恢复用户的原始相机、分辨率、帧号与渲染引擎，绝不扰乱工作区 UI。
- `previz_set_viewport_view(view, camera)`:
  - 在交互界面中安全调整 3D 视图方位。

### 4. 集合管理、对象复制与资产导入 (P1)
- `previz_collection_create(name, parent_collection)`: 幂等创建或获取集合，支持指定父集合层级。
- `previz_collection_move_objects(objects, target_collection)`: 批量移动对象至指定集合，自动解除原集合关联。
- `previz_collection_set_visibility(collection, hide_viewport, hide_render)`: 切换集合的视口与渲染可见性。
- `previz_duplicate_object(reference, linked, name, collection)`: 明确区分关联复制（`linked=True`，共享 Mesh 数据块）与独立深拷贝（`linked=False`，独立深复制 Mesh 数据块）。
- `previz_import_file(filepath, collection, parent_name)`:
  - **白名单限制**：严格仅支持 `.glb`、`.gltf`、`.fbx`、`.obj`、`.usd`、`.usda`、`.usdc` 格式的绝对路径导入。
  - **隔离与归类**：导入资产自动分配至目标集合。
  - **中文顶层父级**：支持传入 `parent_name`（如 `父级_校车`、`父级_建筑群`），自动将导入根对象挂接在独立顶层 Empty 下，严禁篡改内部骨骼、材质、约束和子构件原始命名。

### 5. 材质与贴图平铺控制 (P1)
- `previz_set_texture_tiling(target, scale_x, scale_y, rotation_degrees, mapping_mode, material_slot)`:
  - 支持 Principled BSDF 材质与已有的 Mapping 节点。
  - 自动检测并安全链接 `Texture Coordinate` -> `Mapping` -> `Image Texture`。
  - 仅修改目标材质槽，非破坏性输出修改前后的节点名、旧数值与新数值。

### 6. 统一任务状态与进度跟踪 (P1)
- `previz_get_task_status(task_id)`:
  - 针对 Poly Haven、Poly Pizza、Sketchfab 及 3D 生成器任务，统一生命周期阶段：`queued` / `downloading` / `importing` / `verifying` / `succeeded` / `failed` / `cancelled`。
  - 提供已耗时、真实百分比进度（不可获取时明确为 `unknown`，严禁伪造进度）、错误类型与可重试次数计数。

---

## 恢复边界与双层容灾机制

系统严格区分两类性质完全不同的恢复能力：

1. **结构化操作事务回滚 (Transaction Rollback)**:
   - 适用于变换（Transform）、集合（Collection）、复制（Duplicate）、材质调整等受控操作。
   - 记录 `before_state` 与 `after_state` 快照。验证或操作失败时在内存中自动恢复，用户无需重新打开文件。
   - **已删除对象拦截保护**：常规事务无法凭空重建任意被删除网格的几何拓扑。若操作中存在已删除对象，事务回滚将明确报错阻断，并提示用户切换至完整工程恢复点。
2. **完整工程恢复点 (Full Project Checkpoint)**:
   - 适用于外部模型导入、复杂跨阶段 Agent 自动化操作或高风险变更。
   - 每次任务前自动使用 `save_as_mainfile(copy=True)` 导出独立 `.blend` 副本，记录时间戳、路径与任务 ID。
   - **强确认安全底线**：恢复工程涉及重载整份工程文件，属于高影响动作，**必须由用户在 Blender 侧边栏面板中手动确认后恢复**，严禁 Agent 静默执行 `bpy.ops.wm.open_mainfile`。

---

## 隐私与安全边界 (Security & Safety)

1. **环回监听与鉴权**：本地 Bridge 仅监听 `127.0.0.1`，所有外部请求必须携带 `X-AI-Previz-Token` 认证头，禁止暴露给公网。
2. **零敏感泄漏**：日志与通信载荷中脱敏处理，绝不暴露用户系统账号、Token、API Key 或工作区非相关路径。
3. **危险 API 防御**：
   - 严禁调用 `bpy.ops.wm.read_factory_settings`、`read_homefile`、`open_mainfile`、`revert_mainfile`、`quit_blender`、`addon_disable`。
   - 严禁注销插件或通过工厂模式清空用户场景。
   - 严禁通过 `.blend` 格式导入直接替换当前打开的工程。
4. **沙箱边界如实声明**：静态 AST 分析与关键词过滤无法 100% 阻止 Python 动态反射（如 `getattr`、动态 `exec`）。系统通过受控的高频结构化工具全面覆盖 Agent 的操作面，最大限度减少对裸 `execute_blender_code` 的依赖。

---

## 自动化测试与验证

本项目所有测试均遵循安全隔离标准，采用后台 `factory-startup` 临时场景运行，绝不触碰用户当前打开的实际工程：

1. **单元测试套件**：
   ```powershell
   $env:PYTHONPATH="D:\123codex\2026-09-29\b\blender-ai-previz-director\.venv\Lib\site-packages;D:\123codex\2026-09-29\b\blender-ai-previz-director"
   pytest tests/unit
   ```
2. **Blender 后台综合 Smoke 测试**（验证 200+ 对象拓扑、分页完整性、父子变换、原子批量失败、5视角渲染、事务回滚、检查点与危险拦截）：
   ```powershell
   & 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python tests/blender/test_structured_tools_smoke.py
   ```
3. **全流程 MVP 回归测试**：
   ```powershell
   & 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python tests/blender/test_mvp.py
   ```

---

## Agent Skill 安装与同步

仓库内的 [`skills/blender-operator/SKILL.md`](skills/blender-operator/SKILL.md) 是 Codex、Gemini/Antigravity、WorkBuddy 与 Hermes 共用的单一母版。它融合通用 Blender MCP 与 AI Previz Director MCP，并明确事务、完整工程检查点、坐标/约束、层级包围盒和独立核验边界。

将整个 `skills/blender-operator` 文件夹复制到对应 Skill 根目录：

| 客户端 | Windows 默认目录 |
|---|---|
| Codex | `%USERPROFILE%\.codex\skills\blender-operator` |
| Gemini / Antigravity | `%USERPROFILE%\.gemini\config\skills\blender-operator` |
| WorkBuddy | `%USERPROFILE%\.workbuddy-ai\skills\blender-operator` |
| Hermes | `%USERPROFILE%\.hermes\skills\blender-operator` |

安装后重启或重新加载对应客户端，再做只读验收：确认 Skill 被运行时发现，调用通用 Blender MCP 状态与场景读取，获取一张视口图；Director 另行报告 Bridge、连接和鉴权状态。文件复制成功不等于运行时已经加载，也不等于 Director 鉴权成功。
