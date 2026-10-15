# Changelog

## 0.4.0 - 2026-10-01

- Director 面板新增本地参考图选择；Codex 获得直接图像输入，Gemini 获得参考图路径和 Blender MCP 视觉加载要求。
- 新增单次任务、白模布局、资产细化、灯光运镜四个执行阶段，限制长任务一次性扩张。
- 每个 Director 任务执行前自动创建独立 `.blend` 恢复副本，面板可确认后恢复最近检查点。
- 兼容已经加载旧 RPC 客户端的 Blender 会话，回环地址上的旧面板不再因缺少令牌得到 `Forbidden`。
- 选择 Gemini 时若 Antigravity 尚未运行，会自动启动并等待本地 Agent API 就绪。
- 已选择参考图时允许指令框留空，面板会按当前执行阶段自动生成对应的场景还原任务。
- Agent 明确禁止使用工厂重置、重载文件或注销插件清空场景；只能删除任务范围内对象。
- Director 执行前检查通用 Blender MCP，断开时通过仍在线的本地 Bridge 尝试自动重新启用并启动服务。

## 0.3.0 - 2026-09-30

- Director 模式改为真实自主 Blender MCP Agent，可完成多步建模、材质、灯光、动画、运镜、镜头切换和渲染任务。
- Blender 面板新增 Codex / Gemini Agent 选择；Gemini 通过已登录的 Antigravity 本地 Agent API 工作。
- Antigravity 连接会自动发现动态端口并使用当前项目上下文，不依赖桌面鼠标键盘控制。

## 0.2.1 - 2026-09-30

- Quick 模式新增中文物体颜色修改，支持语义名称和别名。
- Quick 无法理解的指令现在立即提示切换 Director，不再错误回退生成无效操作。
- 面板发送后立即显示处理中状态，并修正 Blender 空闲轮询过快导致的日志和 CPU 占用。
- Companion MCP 新增材质颜色工具，详细状态可返回物体材质颜色。

## 0.2.0 - 2026-09-30

- 新增人物及汽车 `camera_follow` 持续跟拍约束，并纳入事务撤销/重做。
- 镜头段时间线标记现在绑定摄影机，支持播放和渲染时自动切换机位。
- Companion MCP 扩展到 18 个工具，新增跟拍、创建镜头、修改镜头摄影机、设定帧和搭建跟拍测试工程。
- 新增可重复的 120 帧测试场景：人物行走、汽车飞驰、三机位切换及 H.264 导出。

## 0.1.1 - 2026-09-29

- 修正 Blender 进程缺少 `LOCALAPPDATA` 时的运行配置路径回退。
- 兼容带 BOM 的运行配置文件。
- Companion MCP 启动时会自动检查并拉起本地 Bridge，重启 Codex 后无需手工运行脚本。
- 为已经加载旧插件代码的 Blender 会话增加仅限回环地址、仅限内部轮询端点的兼容连接；执行和 MCP 端点仍要求令牌。
- 新增真实 MCP 往返测试：修改焦距、读取验证、干净渲染、撤销并核对恢复。

## 0.1.0 - 2026-09-29

- 初版 Blender 5.2 插件、localhost Bridge 和 Companion MCP。
- 支持语义实体、摄影机、Action 时间编辑、镜头段、事务回滚及撤销/重做。
- 支持干净静帧与 MP4；当 Blender 的 FFmpeg 输出不可用时自动使用本机 FFmpeg。
- 兼容 Blender 5.2 layered Action API。
- 通过复杂中文 Intent 编译、Bridge 实机执行、文件重载和 MCP 标准握手验证。
