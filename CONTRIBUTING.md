# 贡献指南

感谢参与大模型智能评测平台。提交前请阅读 `AGENTS.md` 与对应 `docs/delivery/WPxx.md`。

## 流程

1. 开 Issue / 工单说明动机与影响面（安全相关标 `vuln`）。
2. 小步改动；权限变更同步 `permissions.json`、loader、rbac，并 `npm run collect-permissions`。
3. 测试使用隔离库（`tests/isolated_env.py`），禁止触碰业务 `eval_platform.db`。
4. 新增能力不得用 Mock/常量 True 冒充正式验收。
5. PR 描述含：动机、测试命令与结果、回滚说明、是否涉及数据许可。

## 基准与数据贡献

- 提交样本须附 **license_spdx**、授权方、用途；在平台登记 `DataAuthorization` 或附等价证明。
- 无授权的数据不得合入 `fixtures` 或默认种子。
- 基准生态未定义项见 `docs/operations/benchmark-ecosystem.md`，勿在文档中虚构范围。

## 安全

- 禁止提交密钥、证书私钥、真实租户数据。
- 漏洞请私下告知维护者并开 vuln 工单，勿在公开 Issue 贴利用细节。

## 许可

代码默认见根目录 `LICENSE`。第三方组件见 `docs/licenses/THIRD_PARTY.md`；CI 生成 `sbom.json`。
