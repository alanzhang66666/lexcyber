# LexCyber ECS 上传包

把**本目录的全部内容**放到 ECS 的 `/opt/lexcyber`（不要多套一层 `ecs-upload`）。

本机 Docker 代理不通时未重新 `--build`；镜像 tar 已注入当前前端 `web/dist`、engine 与 `demo_cases`。ECS 上仍建议跑一次 `fix_*`，与仓库文件对齐。

## 上传

在 Windows 本机（把 `<ECS_IP>` 换成实际地址）：

```powershell
scp -r D:\lexcyber\deploy\ecs-upload\* root@<ECS_IP>:/opt/lexcyber/
```

或打包后再传：

```powershell
tar -C D:\lexcyber\deploy\ecs-upload -cf D:\lexcyber\deploy\ecs-upload.tar .
scp D:\lexcyber\deploy\ecs-upload.tar root@<ECS_IP>:/opt/
```

ECS：

```bash
mkdir -p /opt/lexcyber
tar -xf /opt/ecs-upload.tar -C /opt/lexcyber
```

## ECS 一次性准备

- 安全组：`22` 限自己 IP；`18080` 限观众 IP
- 安装 Docker 与 Compose 插件
- 4G swap（2G 内存机器必需）

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 起栈

```bash
cd /opt/lexcyber
# 先打开 demo-account.env 与 .env.v03，确认密码
chmod +x start-on-ecs.sh deploy/*.sh
./start-on-ecs.sh
```

浏览器：`http://<ECS_IP>:18080`

登录账号见同目录 `demo-account.env`（不要提交到 git）。

## 目录里有什么

| 路径 | 用途 |
| --- | --- |
| `lexcyber-demo-images.tar` | 离线 9 个镜像，ECS 零拉取 |
| `.env.v03` | Compose 密钥；已打开量刑/法源开关 |
| `demo-account.env` | `demo_owner` 登录密码 |
| `docker-compose.yml` + `deploy/docker-compose.demo-cloud.yml` | 公网绑定 `0.0.0.0:18080` |
| `web/dist` | 演示前端 |
| `engine/` `demo_cases/` `contracts/` `scripts/` | 注入 runtime + 三案导入 |
| `法学材料/` | 三案 zip + 042 两份 docx |
| `nginx/` `infra/postgres/init/` `engine/migrations/` | Compose 挂载 |

不要在 ECS 上 `docker compose up --build`。演示结束：`docker compose --env-file .env.v03 -f docker-compose.yml -f deploy/docker-compose.demo-cloud.yml down -v`。
