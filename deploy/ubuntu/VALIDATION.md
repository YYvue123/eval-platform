# 部署工具验证记录

日期：2026-10-25。环境：Windows、Python 3.11。范围仅为部署工具及配置静态检查。

| 检查 | 结果 |
| --- | --- |
| `python -m unittest discover -s deploy/ubuntu -p test_manage.py -v` | 15 项：14 通过、1 跳过 |
| 生产业务数据库 | 未访问；测试仅创建临时隔离 SQLite |
| Python 编译与 CLI 帮助 | 通过 |
| Compose YAML 解析、后端无对外端口映射检查 | 通过；不等于 Docker Compose 运行验证 |
| 新文件 LF 与已有部署索引 diff 空白检查 | 通过 |
| 真实 OpenSSL 加密/解密往返 | 缺少 OpenSSL，跳过 |
| Bash 语法、镜像构建、Docker Compose config/up | 缺少 Bash/Docker，未执行 |
| Nginx 加载、HTTPS、真实登录、SSE | 未部署，未执行 |
| Ubuntu/systemd 定时器、更新/回滚/整机恢复 | 未执行 |
| 生产并发、真实模型及多模态验收 | 未执行 |

回归覆盖：版本路径约束、跨表活跃工作只读阻断、维护状态保留/恢复、停机后新任务竞态、损坏数据库、密文 HMAC 变化、篡改快照拒绝、归档路径越界、恢复默认预览、禁止覆盖已有安装、镜像/Compose 清单校验、就绪失败处理。

部分控制流测试使用替身模拟 Docker、解密或就绪失败，仅证明对应工具逻辑分支，不作生产准入通过依据。上线前必须在隔离 Ubuntu 测试主机完成手册第 10 节，并补充真实证据。
