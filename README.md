# AI Previz Director for Blender 5.2

一个本机优先的 Blender 预演控制层。它把自然语言先编译成受限 JSON Intent，再由 Blender 主线程执行；不会让模型直接运行任意 Python。现有 `MCP for Blender` 会保留，两套能力可并存。

## 当前能力

- 用持久语义标签识别演员、产品、摄影机和别名。
- 设置焦距、推拉、环绕、看向主体、自动构图。
- 为人物、汽车或其他语义对象建立持续跟拍与看向约束。
- 对受支持的 Action 做移动、缩放时间、变速和停顿。
- 创建及修改镜头段，制作人物或产品特写。
- 把镜头段绑定到时间线摄影机标记，播放和渲染时自动切换机位。
- 原子事务、验证失败回滚、Director 撤销/重做。
- 输出无 UI 的摄影机静帧和 H.264 MP4。
- Blender 侧边栏、localhost Bridge 和 13 个 Companion MCP 工具。

## 使用

1. 如桥接未运行，在 PowerShell 执行：

   ```powershell
   & 'D:\123codex\2026-09-29\b\blender-ai-previz-director\scripts\start_bridge.ps1'
   ```

2. 打开 Blender，在 3D 视图按 `N`，进入 `AI Previz` 页签。
3. 简单指令选 `Quick`；多步骤指令选 `Director`。

示例：

- `把当前摄影机焦距改成 50mm`
- `镜头向右环绕女孩 30 度`
- `把女孩行走动画调整为原速度的 70%`
- `最后一个镜头改成耳机盒特写，并延长 12 帧`

首次操作未标记的对象时，Agent 可先调用 `previz_tag_entity`。稳定 ID 应保持不变，例如 `actor_girl_01`、`product_earbud_case`。

## Agent 接口

Codex 中已注册 `ai-previz-director` MCP，提供：状态读取、实体查找/标记、摄影机控制、演员变速、产品特写、撤销/重做、干净静帧和视频导出。复杂自然语言也可从 Blender 面板走 Director 编译器。

## 检查与卸载

```powershell
& 'D:\123codex\2026-09-29\b\blender-ai-previz-director\scripts\health_check.ps1'
& 'D:\123codex\2026-09-29\b\blender-ai-previz-director\scripts\uninstall.ps1'
```

卸载脚本会关闭插件、移除 MCP 注册并停止 Bridge；插件目录会改名保留，便于恢复。

## 已知边界

- `camera_orbit` 当前是确定性改位；连续跟拍使用 `camera_follow`，动画环绕轨迹仍需后续支持。
- Action 变速适用于普通、非共享的 Action；NLA、驱动器、共享 Action、链接库和复杂程序化 Rig 会被拒绝或需要后续适配。
- 镜头段目前以场景自定义数据和时间线标记保存，不等同于完整剪辑系统。
- Director 模式会调用本机 Codex，速度和可用性取决于当前登录及额度；Quick 模式不依赖模型调用。

## 项目结构

- `addon/ai_previz_director/`：Blender 插件、主线程调度与确定性执行器。
- `bridge/`：仅监听 `127.0.0.1` 的带令牌桥接服务。
- `adapters/`：快捷解析器与隔离的 Codex Intent 编译器。
- `companion_mcp/`：供 Agent 直接调用的细粒度 MCP。
- `tests/`：单元、Blender 5.2、重载、视频和 MCP 握手测试。

