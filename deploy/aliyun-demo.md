# LexCyber 阿里云一日演示部署手册

目标形态：ECS **2C2G + 40G**，公网 `http://<ECS_IP>:18080` 单通道访问，演示一天。
2G 内存跑全套栈可行，但**必须离线镜像搬运（不在 ECS 上构建）+ 4G swap**。

## 0. ECS 一次性准备

```bash
# 装 Docker（Alibaba Cloud Linux 3 / Ubuntu 均可）
# 安全组：放行 22（限自己 IP）+ 18080（限观众 IP 或开放）
# 4G swap（2G 内存的兜底，docx 解析有尖峰）
fallocate -l 4G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

不需要配镜像加速器——镜像全部走离线包。

本机打好的完整上传目录：`deploy/ecs-upload/`（含镜像 tar、compose、前端 dist、三案材料、`.env.v03`）。把该目录内容放到 ECS `/opt/lexcyber` 后执行 `./start-on-ecs.sh`。

## 1. 本地打包镜像（Windows 本机执行）

```powershell
cd D:\lexcyber
# 确保镜像含最新代码（engine Dockerfile 已含 demo_cases；如不放心先 build 一次）
docker compose --env-file .env.v03 build web java engine engine-worker
# 打成一个 tar（约 1.5GB）：3 个自建镜像 + 5 个基础镜像，ECS 零拉取
docker save -o lexcyber-demo-images.tar `
  lexcyber-v03-web lexcyber-v03-java lexcyber-v03-engine lexcyber-v03-engine-worker `
  postgres:16.4-alpine redis:7.4.1-alpine minio/minio:RELEASE.2024-10-13T13-34-11Z `
  nginx:1.27.2-alpine flyway/flyway:10.20.1-alpine
scp lexcyber-demo-images.tar root@<ECS_IP>:/opt/
```

## 2. 传 repo + 配置到 ECS

```bash
# repo（git 克隆或打包上传均可），放 /opt/lexcyber
# .env.v03 用新强密码（不要复用本地的），并打开演示开关：
#   SENTENCING_ENABLED=true
#   LEGAL_SOURCE_SEARCH_ENABLED=true
# 另需上传 法学材料/ 目录（或至少其中 3 个案例 zip + 2 个 042 docx）供 stage_materials 使用
```

## 3. 起栈 + 灌数据

```bash
cd /opt/lexcyber
docker load -i /opt/lexcyber-demo-images.tar
docker compose --env-file .env.v03 -f docker-compose.yml -f deploy/docker-compose.demo-cloud.yml up -d
curl http://127.0.0.1:18080/healthz   # {"status":"ok",...}

# 关键：把仓库当前 engine 代码 + demo_cases 注入容器 site-packages
#（镜像内 pip 安装的 engine 包可能是旧版，缺 replay 分支与演示数据）
bash deploy/fix_engine_runtime.sh
# 前端演示页：先本地 npm --prefix web run build，再注入 web 容器（不要在 ECS 上 build）
bash deploy/fix_web_runtime.sh

# 备料 + 导入 + 恢复演示态（需 python3）
python3 deploy/stage_materials.py --src 法学材料 --out .tmp-legal-docs
LEXCYBER_USERNAME=demo_owner LEXCYBER_PASSWORD='<新密码>' \
  python3 scripts/import_three_case_demo.py --docs-dir .tmp-legal-docs --register-account
LEXCYBER_USERNAME=demo_owner LEXCYBER_PASSWORD='<新密码>' \
  python3 deploy/demo_restore.py --docs-dir .tmp-legal-docs
```

完成后应有：3 案全真实材料（B 案含 042）、facts confirmed、模块 v2、
每案至少一份演示文书草稿、6 条 pending 复核（3 定罪 + 3 量刑）。登录 `http://<ECS_IP>:18080`，账号 demo_owner。
首页功能卡不再显示「开发中」；量刑/阅卷页不再出现「示例占位」横幅。

## 4. 演示当天 checklist

- [ ] `curl http://127.0.0.1:18080/healthz` ok
- [ ] 登录页能进，案件中心 3 案可见
- [ ] B 案文档列表：009 输入 + **042输入材料新(1).docx** + 2 标注
- [ ] 定罪页证据定位点击能跳到 042 真实段落
- [ ] 量刑页跑 actor（已预建 waiting_review 结果可直接演示复核）
- [ ] 首页功能卡显示「进入 →」，无「开发中」
- [ ] 定罪 / 量刑 / 文书页能打开真实案件数据
- [ ] 复核队列 6 条 pending

## 5. 结束回收

```bash
docker compose --env-file .env.v03 -f docker-compose.yml -f deploy/docker-compose.demo-cloud.yml down -v
swapoff /swapfile && rm /swapfile   # 如需还原
# 安全组删掉 18080 规则
```

## 注意事项

- **别在 ECS 上 `--build`**：maven/npm/pip 在 2G 上会 OOM，镜像必须本地打好搬过去
- 裸 HTTP 明文，仅适合限时演示；长期对外要走域名+ICP+HTTPS
- 单账号 `trusted-header` 模型：知道密码的人看到的都是 demo_owner 视角
- `demo_restore.py` 依赖 `.t1-three-case-import.checkpoint.json` 取 caseId 映射（同目录下自动生成）
- **必须跑 `fix_engine_runtime.sh`**：engine/worker 可能从 `/app/engine` 或 `site-packages/engine` 解析代码（取决于启动上下文），脚本两处都注入新代码 + `demo_cases`，跳过它量刑任务会走旧路径产出 blocker 或报文件缺失
- **必须跑 `fix_web_runtime.sh`**：web 镜像是构建时打进 nginx 的静态包；演示页改完后用本脚本 docker cp `web/dist`，避免在 ECS 上 npm build

## 已实测（本机彩排 2026-09-19）

完整走通 `down -v → up -d（叠加本 override）→ fix_engine_runtime → stage_materials → import → demo_restore`：
- nginx `ports` 必须用 `!override`（compose 对列表是合并语义，直接写会产生双重绑定）
- 标注文件上传的文件名必须 UTF-8 原样写入 multipart 头，不能 percent-encode
- Docker Desktop 重启后 `unless-stopped` 策略正常拉起全栈
- 终态：6 条 pending 复核（3 定罪 v2 + 3 量刑 replay 结果）
