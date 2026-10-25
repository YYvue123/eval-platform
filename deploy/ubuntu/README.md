# Ubuntu 生产部署与更新手册

适用：Ubuntu Server 24.04 LTS，单服务器，Docker Compose，Nginx HTTPS，单进程 FastAPI，SQLite。本目录是正式使用入口；上级目录的旧 systemd/Compose 示例不与本方案混用。

本文交付的是部署工具与操作流程，不代表已完成 Ubuntu 实机部署、生产压测或真实模型验收。首次上线前须完成文末验收表。所有自动回归必须使用隔离库，本工具测试采用临时目录隔离，不接触 `backend/eval_platform.db`。

## 1. 准备条件

- 建议起步 4 核、8GB 内存、100GB SSD；容量与吞吐需要实测。无需本机 GPU。
- 服务器为 Ubuntu 24.04，有 sudo/root 权限。默认架构为 amd64；ARM 构建指定 `--platform linux/arm64`。
- 域名已解析到服务器；准备有效的完整证书链和对应私钥，内网可使用组织 CA。
- 80、443 未被其他程序使用。已有 Nginx、Docker、容器平台的机器先协调端口及运行环境，脚本不会卸载现有运行时。
- 网络安装需要 Ubuntu/Docker 软件源；镜像构建需要 Python/npm/镜像源网络。目标服务器可离线加载发布镜像，但运行时及依赖必须预装，模型服务和 MCP 的网络需另行放行。
- 为数据库、文件、镜像、备份、升级副本预留空间。更新期间除原始数据外还有完整备份和迁移副本；恢复会保留原始数据，不能只按数据库文件大小估算。
- 主机与云安全组只开放必要的 SSH、80、443。SSH 限制来源；Docker 发布端口应以云安全组及 Docker 防火墙规则共同控制，不能仅假定 UFW 会拦截 Docker 映射。
- 单机故障会中断服务；本方案采用维护窗口更新，长任务完成后再操作。

## 2. 文件与命令

| 文件 | 用途 |
| --- | --- |
| `bootstrap.sh` | Ubuntu 24.04 运行时准备，安装运维工具 |
| `manage.py` | 发布包构建、安装、更新、备份、验证、恢复、回滚、诊断 |
| `backend.Dockerfile` | Python 3.11，按 lock 安装后端依赖，UID 10001，单进程 |
| `web.Dockerfile` | Node 22 构建 Vue，Nginx 提供静态页面 |
| `compose.yaml` | 后端内部网络、前端入口、持久化和日志轮转 |
| `nginx.conf.template` | HTTPS、SPA、SSE、维护模式；指标及接口文档默认禁止外部访问 |
| `eval-platform-backup.service/.timer` | 每日备份与成功后保留策略 |
| `test_manage.py` | 部署工具隔离回归 |

服务器命令统一使用：

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py --help
```

部署目录固定如下，不要手动移动：

```text
/usr/local/lib/eval-platform/    运维工具与Nginx模板
/etc/eval-platform/backup.key   备份加密与认证密钥，必须单独离线保管
/opt/eval-platform/
  current -> releases/版本号
  releases/版本号/              镜像引用、Compose、发布清单
  shared/config/backend.env     生产环境变量，root 0600
  shared/config/tls/            fullchain.pem、privkey.pem
  shared/config/certs/          模型mTLS证书，按UID/GID 10001设置读取权限
  shared/data/                  SQLite及业务API产生的备份
  shared/uploads/               上传文件、报告、证据、资源快照
  shared/logs/                  应用日志
  shared/control/               维护标记和维护页面
  backups/时间戳/               加密快照和认证清单
  pending.json                  未完成更新记录（如有）
  last-update.json              最近成功更新的来源及备份
  rescue-时间戳/                恢复前保留的原始数据（如有）
```

## 3. 构建发布包

在装有 Docker 和 Git 的构建机执行，可在 Linux 或使用 Linux 容器的 Windows Docker Desktop 中构建。应先在隔离环境执行后端回归；前端构建会自动运行权限采集。

```bash
python deploy/ubuntu/manage.py build 2026.10.25-1 --output ./dist/releases
```

输出 `dist/releases/2026.10.25-1/`，包含镜像归档、Compose、镜像环境文件、运维脚本、模板和清单。清单记录提交、工作区是否存在修改、镜像 ID、架构、构建时间、镜像归档及 Compose 的 SHA256。

构建使用当前工作区中的应用源代码（包括尚未提交的业务改动），不会把开发数据库、`.env`、上传目录、日志和 node_modules 加入构建上下文。正式发布建议先提交并评审源代码；`dirty=true` 只说明有改动，不表示通过评审。版本号不可复用。

基础镜像构建时会拉取标签对应版本，产出镜像 ID 随发布包冻结；重新构建不保证字节相同，必须使用新版本号。保留原始发布包才能在新服务器恢复原镜像。

只从可信渠道接收发布包。清单及校验值用于发现传输损坏和版本错配，不代替发布者数字签名。

## 4. 首次部署

先上传 `deploy/ubuntu/` 工具目录和完整发布包，例如分别放到 `/srv/eval-tools/` 和 `/srv/eval-releases/2026.10.25-1/`。

### 4.1 准备运行时

在 Ubuntu 上运行，避免从 Windows 复制后出现 CRLF；仓库已为该目录声明 LF。

```bash
sudo bash /srv/eval-tools/bootstrap.sh
sudo python3 /usr/local/lib/eval-platform/manage.py doctor
sudo ss -lntp
```

bootstrap 通过 Docker 官方 apt 仓库安装 Docker/Compose，已有 Docker 时检查 Compose，不卸载已有软件、不自动配置防火墙、不添加普通用户到 docker 组。docker 组拥有很高的主机权限。

若服务器禁止联网，由管理员预装 Docker Engine、Compose v2、Python 3.12、OpenSSL 及 CA；手动安装 `manage.py` 和 `nginx.conf.template` 到 `/usr/local/lib/eval-platform/` 即可。不要在离线服务器执行 bootstrap 的联网安装步骤。

### 4.2 安装应用

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py install \
  /srv/eval-releases/2026.10.25-1 \
  --domain eval.example.com \
  --cert /srv/certificates/fullchain.pem \
  --key /srv/certificates/privkey.pem
```

交互设置至少 16 字符的管理员密码。脚本生成随机 SECRET_KEY 和备份密钥；管理员首次创建成功后从环境文件移除初始化密码，并重新创建后端验证就绪。初始化密码不会写入发布包或命令行。

安装遇到已有 `shared/` 会退出，禁止重复初始化覆盖生产数据。安装中途失败时保留现场，用 `status`、`doctor` 和日志诊断，修复后用 `resume` 启动当前版本；不要删除目录重装。若失败发生在 `current` 创建之前，先修复配置/发布包，再由管理员核对后建立正确版本链接，或在确认尚无业务数据后另行清理失败安装现场。

默认创建全新生产数据库；不导入本机开发数据。数据库初始化会执行项目既有种子逻辑，不能把内置示例资源的存在当作真实评测验收。

### 4.3 上线配置及验收

```bash
curl --fail https://eval.example.com/api/live
curl --fail https://eval.example.com/api/ready
sudo python3 /usr/local/lib/eval-platform/manage.py status
```

登录并修改管理员密码，配置真实模型、远程服务及必要证书。自定义配置写入 `/opt/eval-platform/shared/config/backend.env`，包含：

| 配置 | 使用方式 |
| --- | --- |
| `SECRET_KEY` | 已随机生成；更新时保持稳定，不能换回示例值 |
| `APP_ENV` | 固定 production |
| `SERVICE_MODEL_HOSTS` | 按业务配置客户模型域名白名单 |
| `MTLS_CERT_FILE` / `MTLS_KEY_FILE` / `MTLS_CA_FILE` | 使用 `/state/certs/` 下的容器路径 |
| `LOG_LEVEL` | 默认 INFO |
| `AUDIT_RETENTION_DAYS` 等 | 按现有运维规范配置 |

Compose 环境文件使用单引号值，包含单引号时按 Compose 规则转义；不要把它当 shell 文件 `source`。不要把密钥提交到 Git。mTLS 文件须允许容器 UID/GID 10001 读取，例如目录 `root:10001 0750`、文件 `root:10001 0640`。

修改环境变量后必须重新创建后端容器，单纯 restart 不加载新环境。先安排维护窗口，检查活动任务，再执行；配置变更同样需要备份。不要额外增加后端副本或 worker。

## 5. 更新发布

1. 在构建机完成隔离回归，生成新的不可复用版本号发布包。
2. 上传新发布包，确认维护窗口、磁盘空间与备份密钥可用。
3. 在 UI/API 中检查任务和 Agent，等待活跃工作完成；需要取消时由有权限操作者通过业务流程取消。
4. 执行更新：

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py update \
  /srv/eval-releases/2026.10.26-1 --username admin
```

输入已有账号的密码，用于新版真实登录烟测。更新依次执行：

- 校验并加载镜像，准备版本目录，记录更新来源。
- Nginx 开启维护，等待 5 秒，使用 SQLite **只读连接**跨租户检查 queued/running/pending 任务、queued/running/waiting Agent 及活跃批次。
- 发现活动工作立即中止；尚未停止服务时恢复原来的访问状态，不修改任何业务行。等待审批的 Agent 也会保守阻止更新，需通过业务流程处置。
- 停止后端后再次检查活动工作，避免检查与停机之间出现新任务。
- 生成数据库、上传文件、配置及旧发布清单的一致性加密快照。
- 将数据和上传文件复制到隔离目录，在无网络、禁用 Agent worker 的临时容器中执行数据库初始化/升级及种子逻辑，检查 SQLite 完整性。副本用后删除。
- 副本验证通过后切换程序版本，启动后端及前端，等待 ready，验证 Nginx 配置、真实登录和前端构建文件。
- 验证通过才关闭维护，记录最近成功更新及关联备份。

当前数据库升级机制是项目内置 `create_all + ALTER TABLE`，没有完整的版本化降级机制。副本启动成功只证明本次检查范围内可启动；仍须通过隔离回归及业务验收确认数据语义。

脚本不自动执行会创建评测、调用付费模型的准入或真实演示脚本，不直接写调度字段或评分事实。真实任务需经受控工具/TaskService。

更新后的人工确认：登录、核心页面、权限、上传下载、历史报告、Agent SSE、模型真实调用、多模态工具；每项按实测记录，缺少依赖写明未测/阻塞。

## 6. 更新失败与恢复访问

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py status
sudo python3 /usr/local/lib/eval-platform/manage.py doctor
```

进入当前版本目录，再查看日志（不要把含客户内容的原始日志公开）：

```bash
cd /opt/eval-platform/current
sudo docker compose --project-name eval-platform --env-file images.env -f compose.yaml logs --tail 100 backend web
```

若失败发生在活动工作检查阶段、尚未停止后端，脚本保留原服务并恢复原访问状态。后续阶段失败时保留维护，不自动恢复数据库，也不假定旧代码兼容新数据库。

若当前版本尚未升级数据库，或已修复当前版本配置，可显式验证并恢复当前版本：

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py resume --username admin
```

`resume` 不更换版本、不恢复数据库，运行 ready/登录/Nginx/前端文件检查后开放访问。未完成更新记录会保留以便调查。不要直接删除维护标记绕过检查。

## 7. 回滚程序或恢复快照

### 7.1 仅回滚程序

只有确认旧代码与当前数据库及业务数据语义兼容时才使用。脚本要求显式确认目标版本，但该确认不能代替人工兼容性评审。

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py rollback 2026.10.25-1
# 上一条只检查镜像并提示；确认兼容后：
sudo python3 /usr/local/lib/eval-platform/manage.py rollback 2026.10.25-1 \
  --confirm 2026.10.25-1 --username admin
```

脚本会停写、备份当前状态、验证副本启动，再切回镜像；不会自动降级数据库。

### 7.2 恢复数据库、文件和配置

先从 `pending.json`、`last-update.json` 或备份目录确定更新前快照：

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py verify-backup \
  /opt/eval-platform/backups/替换为实际快照目录名

sudo python3 /usr/local/lib/eval-platform/manage.py restore \
  /opt/eval-platform/backups/替换为实际快照目录名
```

第一条解密至隔离目录，检查 HMAC、归档安全及 SQLite 完整性，并记录实测耗时。第二条默认仅预览要恢复的版本及数据丢失边界，不停机、不改活动数据，并以非零退出码结束。

确认接受快照之后所有数据库/上传文件写入丢失，再执行：

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py restore \
  /opt/eval-platform/backups/替换为实际快照目录名 \
  --confirm 替换为实际快照目录名 --username admin
```

恢复使用**快照中的账号密码、配置与证书**。所需镜像必须仍在本机，或提前从保留的原发布包 `images.tar` 执行 `docker load -i`。旧状态会移动到 root 专用 `rescue-时间戳/`，不会被直接删除；该目录含明文密钥，验证完成后按组织数据销毁策略处理。

恢复过程中若出现故障，保持维护，保留 rescue 和失败现场；不要反复运行覆盖目录。核对 data/uploads/config 是否来自同一快照，再恢复完整匹配集合。证书可能已过期，恢复后须检查。

### 7.3 整机丢失

在新 Ubuntu 主机安装运行时，恢复 `/etc/eval-platform/backup.key`（root 0600），加载原发布镜像，取回加密备份。`restore` 命令面向已有安装；空主机灾难恢复须先按首次部署创建目录与基本运行配置，然后在未开放业务前恢复快照。域名、证书、备份密钥、镜像和业务快照缺一项都可能阻塞恢复，必须实际演练。

## 8. 定时备份、保留与异机副本

```bash
sudo python3 /usr/local/lib/eval-platform/manage.py backup
```

备份会短暂维护并停止后端，保证数据库与上传文件一致；存在活动工作时失败退出并保留服务。每日备份安排在业务低峰，无法完成时需要运维跟进重试，不能认为定时器存在就已备份成功。

备份采用 OpenSSL AES-256-CBC + PBKDF2（200000 次）加密，并以独立 HMAC-SHA256 验证密文。完整快照含配置和 TLS 私钥，使用前先验 HMAC。备份密钥不在快照中；必须放入组织密码库或单独离线介质，丢失后无法解密，泄露后需要制定轮换及历史备份处理方案。

安装定时器：

```bash
sudo install -m 0644 /srv/eval-tools/eval-platform-backup.service /etc/systemd/system/
sudo install -m 0644 /srv/eval-tools/eval-platform-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eval-platform-backup.timer
sudo systemctl list-timers eval-platform-backup.timer
```

默认每天北京时间 02:30 起，随机延后最多 5 分钟；不在开机时补跑，避免工作时段意外维护。成功后自动保留最近 7 个有快照的日期、4 个有快照的自然周，以及最近成功/未完成更新引用的快照；保留的总份数可能大于 11。失败无自动数据恢复，service 标记失败。

```bash
sudo systemctl status eval-platform-backup.service
sudo journalctl -u eval-platform-backup.service --since yesterday
# 手动检查清理候选；默认不删除
sudo python3 /usr/local/lib/eval-platform/manage.py prune
# 确认执行同一保留规则
sudo python3 /usr/local/lib/eval-platform/manage.py prune --confirm
```

运维监控须接入该 service 的失败状态，并监控最近成功快照时间、磁盘余量、HTTPS 证书到期与 ready。这里没有配置外部通知账号，也没有自动发送消息。

将**完整的快照目录**（snapshot.enc 和 manifest.json）及可信发布包复制到另一台服务器或备份存储。示例目标需替换为组织真实地址并预配 SSH 身份：

```bash
sudo rsync -a /opt/eval-platform/backups/ backup-user@backup-host:/srv/backup/eval-platform/
```

不要把 `/etc/eval-platform/backup.key` 与同一份异机快照放在一起。不要对目标使用 `--delete`，避免本机轮转同步删除异机历史。异机副本应有独立保留策略和访问控制。定期将异机副本取回隔离机器执行 `verify-backup`，并安排完整应用恢复演练；文件校验耗时不能直接宣称为完整 RTO，RPO 取决于最近一次成功且可恢复的快照。

## 9. HTTPS 续期及日常运维

证书申请使用组织既有流程或 ACME DNS 验证。默认配置不开放 HTTP challenge 文件路径，不要直接假定 certbot HTTP 插件可用。

续期后将新证书和私钥复制到 `shared/config/tls/`，保留旧文件后验证和重载：

```bash
cd /opt/eval-platform/current
sudo docker compose --project-name eval-platform --env-file images.env -f compose.yaml exec -T web nginx -t
sudo docker compose --project-name eval-platform --env-file images.env -f compose.yaml exec -T web nginx -s reload
```

证书复制仅替换 tls 目录中的文件，不替换挂载的整个目录。私钥维持 root 0600。检查公网证书链、主机名及有效期；验证失败立即恢复旧证书。模型 mTLS 证书单独管理。

应用日志位于 `shared/logs/`，Docker stdout 日志每服务最多 5×10MB；上传文件与备份需要容量监控。不要用 `docker compose down -v`、全局 image prune 或清空 shared 目录做常规更新。

修改配置或升级运维工具应保留旧版本。bootstrap 会拒绝覆盖已有运维脚本，后续工具升级应评审后通过 `install` 命令复制文件，并保留此前版本；业务更新不会静默替换主机运维工具。

## 10. 上线验收与当前验证边界

| 检查 | 通过依据 |
| --- | --- |
| 生产安全配置 | 非默认 SECRET_KEY、无默认引导密码、后端不映射公网端口 |
| 服务运行 | Docker 重启策略、重启后 ready、HTTPS 证书有效 |
| 前端与权限 | 真实登录、核心页面、授权/未授权操作行为 |
| Agent | SSE 流式内容、审批、长任务跟进符合业务要求 |
| 评测与多模态 | 真实模型调用与媒体检查证据，不使用固定成功结果 |
| 更新 | 隔离副本升级成功，实际维护更新后业务可用 |
| 失败回滚 | 在测试主机验证镜像回滚和快照恢复；记录真实恢复耗时及数据边界 |
| 备份 | 本机加密快照、异机副本、单独密钥托管、可恢复演练 |

本次开发环境为 Windows，未提供 Docker、Ubuntu/WSL 和 OpenSSL，因此未执行镜像构建、Compose 启动、Nginx 实际加载、systemd 定时器、加密备份往返及 Ubuntu 实机恢复。这些项目保持未验证，不作为正式上线通过项。

可在 Ubuntu/构建机执行部署工具回归：

```bash
python3 -m unittest discover -s deploy/ubuntu -p test_manage.py -v
bash -n deploy/ubuntu/bootstrap.sh
```

测试仅使用临时目录中的独立 SQLite。依赖 OpenSSL 的真实加密往返用例在缺少 OpenSSL 时明确跳过；使用替身验证的失败分支仅算工具逻辑回归，不等于生产验收。

项目业务测试按现有 `tests/isolated_env.py` 运行，不得连接生产库。真实开发演示、真实模型验收走业务 API，不能拿演示脚本当隔离回归或改写评分事实。
