# U2 · Agent 评测助手工作台（第 4 节）

> 承接 U1；范围 Agents 布局 + 产品态主动作 + 资源选择器；保留 U0/U1 的 live/generation/轮询逻辑。

## Exit

- 目标→澄清→审批→执行→结果可在 UI 演示（无手填内部 ID）
- 产品态驱动唯一主动作；知识/Runtime 进高级区
- `?session=` 路由同步；无规划模型时不可执行并引导配置

## Files

| 路径 | 改动 |
|---|---|
| `components/StatusBadge.vue` | 状态徽标 |
| `components/ResourcePicker.vue` | 数据集/模型远程搜索 |
| `views/Agents.vue` | 工作台布局重写 |
| `docs/delivery/frontend-ux/U2.md` | 证据 |

## Tasks

1. StatusBadge + ResourcePicker
2. Agents 工作台
3. build + STATUS
