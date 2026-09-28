# U1 · Agent 会话交互基础 + MCP 来源互斥

> 承接 U0；范围 F05–F07（不扩 U2/U3 完整工作台）。

## Exit

- 切换会话立即重置 run/events/delegations/evidence/审批上下文，停止旧轮询；generation 丢弃过期响应
- 轮询单飞、按 runId+seq 去重；写按钮独立 loading；确认复用 client_invocation_id 至成功
- MCP 探测：已注册 / 临时远程互斥；服务端拒绝双参；前端展示实际目标

## Files

| 路径 | 改动 |
|---|---|
| `frontend/src/views/Agents.vue` | F05/F06 |
| `frontend/src/views/Resources.vue` | F07 UI |
| `backend/app/api/resources.py` mcp_probe | F07 互斥校验 |
| `docs/delivery/frontend-ux/U1.md` | 证据 |
| 可选：前端轻量单测或后端 mcp_probe 负例 |

## Tasks

1. Agents：loadSession 切换重置 + generation
2. Agents：轮询单飞 / 事件去重 / 写锁
3. Resources + API：MCP 来源互斥
4. 测试 + STATUS 追加
