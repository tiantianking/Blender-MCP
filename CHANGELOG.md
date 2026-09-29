# Changelog

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
