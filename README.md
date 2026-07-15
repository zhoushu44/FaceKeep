# FaceKeep 文件管理与图像任务服务

FaceKeep 提供图片文件管理、后台抠图任务、用户积分及管理员管理功能。图片任务使用全局队列调度，结果为宽 1500 像素、96 DPI 的 PNG。

## 启动

```powershell
pip install -r requirements.txt
npm install
python -m uvicorn api:app --host 0.0.0.0 --port 7333
npm run dev -- --host 0.0.0.0 --port 5173
```

- 前端首页：`http://localhost:5173/`
- 前端 API 文档：`http://localhost:5173/api-docs`
- 后端服务：`http://localhost:7333/`
- FastAPI Swagger：`http://localhost:7333/docs`

## 部署前验证

执行以下检查，确认后端、前端类型检查和生产构建正常：

```powershell
python -m py_compile api.py api_cutout.py
npm run check
npm run build
```

本地运行后可验证：

```powershell
Invoke-RestMethod http://localhost:7333/health
Invoke-WebRequest http://localhost:7333/docs -UseBasicParsing
Invoke-WebRequest http://localhost:5173/ -UseBasicParsing
```

前端使用 SPA 渲染，直接请求首页或 `/api-docs` 返回的是 HTML 应用壳；页面标题和内容会在浏览器加载 JavaScript 后显示。

## Docker 部署

镜像在同一个容器中运行以下服务：

- Nginx：监听 `0.0.0.0:9966`，托管前端并将 `/api`、`/health`、`/docs`、`/openapi.json` 等请求代理到后端。
- FastAPI/Uvicorn：监听容器内部 `0.0.0.0:7333`。
- Supervisor：负责启动和自动重启 Nginx、FastAPI。

### 1. 准备持久化目录和环境变量

必须持久化挂载 `/app/uploads`。用户、任务、积分、管理员图像 API 配置、备份配置及上传/输出文件均保存在该目录；不挂载时，删除容器会丢失这些数据。

创建生产环境文件 `.env.production`：

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置高强度管理员密码
CUTOUT_MODE=api
IMAGE_API_MODEL=gpt-image-2
```

注意：

- `.env` 和 `.env.*` 已被 `.dockerignore` 排除（示例文件 `.env.example` 除外），不会进入 Docker 构建上下文或镜像。
- 推荐通过管理后台 `/admin/image-api-settings` 保存图像 API Endpoint 和 Key。Key 会保存在挂载的 `/app/uploads/metadata.json`，管理接口不会回显 Key。
- 也可通过容器环境变量传入 `IMAGE_API_BASE_URL` 和 `IMAGE_API_KEY`；不要把真实密钥写入 Dockerfile、Git 仓库或镜像。
- 首次部署必须立即修改示例管理员密码。

### 2. 本地构建并运行

PowerShell：

```powershell
docker build -t facekeep:local .
docker run -d `
  --name facekeep `
  --restart unless-stopped `
  -p 8080:9966 `
  --env-file .env.production `
  -v "${PWD}/uploads:/app/uploads" `
  facekeep:local
```

Linux/macOS：

```bash
docker build -t facekeep:local .
docker run -d \
  --name facekeep \
  --restart unless-stopped \
  -p 8080:9966 \
  --env-file .env.production \
  -v "$(pwd)/uploads:/app/uploads" \
  facekeep:local
```

访问地址：

- 应用首页：`http://localhost:8080/`
- 前端 API 文档：`http://localhost:8080/api-docs`
- Swagger：`http://localhost:8080/docs`
- 健康检查：`http://localhost:8080/health`

不要直接暴露容器的 `7333` 端口；外部请求统一通过宿主机 `8080` 端口映射到容器 Nginx 的 `9966` 端口。

### 3. Docker Hub 镜像部署

GitHub Actions 会发布以下两个同内容标签：

```text
DOCKER_HUB_USERNAME/facekeep:3.0
DOCKER_HUB_USERNAME/facekeep:latest
```

服务器部署：

```bash
mkdir -p /opt/facekeep/uploads
cd /opt/facekeep
docker pull DOCKER_HUB_USERNAME/facekeep:3.0
docker run -d \
  --name facekeep \
  --restart unless-stopped \
  -p 8080:9966 \
  --env-file /opt/facekeep/.env.production \
  -v /opt/facekeep/uploads:/app/uploads \
  DOCKER_HUB_USERNAME/facekeep:3.0
```

宿主机 Nginx、宝塔或其他网关应反向代理到 `http://127.0.0.1:8080`，由 Docker 的 `8080:9966` 端口映射进入容器。
外层 Nginx 还应设置 `client_max_body_size 100m;`，否则上传或提交较大的原图时可能返回 `413 Request Entity Too Large`。

### 4. 更新容器

```bash
docker pull DOCKER_HUB_USERNAME/facekeep:3.0
docker stop facekeep
docker rm facekeep
docker run -d \
  --name facekeep \
  --restart unless-stopped \
  -p 8080:9966 \
  --env-file /opt/facekeep/.env.production \
  -v /opt/facekeep/uploads:/app/uploads \
  DOCKER_HUB_USERNAME/facekeep:3.0
```

数据保存在宿主机 `/opt/facekeep/uploads`，重建容器不会删除。升级前建议先在管理员备份页面创建备份，并额外备份该目录。

### 5. 部署验证与排障

```bash
docker ps --filter name=facekeep
docker logs --tail 100 facekeep
curl -f http://127.0.0.1:8080/health
curl -I http://127.0.0.1:8080/
curl -I http://127.0.0.1:8080/docs
```

统一使用 `8080:9966` 映射，健康检查地址为 `http://127.0.0.1:8080/health`，应返回：

```json
{"status":"ok"}
```

常见问题：

- 页面可打开但 API 失败：检查 `docker logs facekeep`，确认 Uvicorn 已监听 `0.0.0.0:7333`。
- 重建容器后数据消失：确认运行参数包含 `-v <宿主机目录>:/app/uploads`。
- 图像任务仍走本地模式：确认容器环境变量为 `CUTOUT_MODE=api`，然后重启容器。
- 图像 API 调用失败：在管理员图像 API 设置页确认 Endpoint、Key 和模型服务兼容 OpenAI `/v1/images/edits` 协议。
- 上传返回 `413`：容器内和宿主机 Nginx 都需要配置 `client_max_body_size 100m;`。

### 6. GitHub Actions 自动发布

工作流位于 `.github/workflows/docker-publish.yml`，push 到 `main` 或 `master` 时自动构建并推送镜像。本地不会执行推送。

在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中配置：

```text
DOCKER_HUB_USERNAME
DOCKER_HUB_TOKEN
```

工作流将同一次构建推送为：

```text
<DOCKER_HUB_USERNAME>/facekeep:3.0
<DOCKER_HUB_USERNAME>/facekeep:latest
```

`.dockerignore` 保持排除 `.env`、`uploads`、`.git`、`node_modules` 和构建产物，防止本地密钥、运行数据和无关文件进入镜像。

## 页面与管理功能

- 首页：上传单张、多张或文件夹图片，支持分片续传、预览和提交抠图任务。
- 用户页面：`/login`、`/user`，用于登录、查看 API Key、积分和积分流水。
- 管理后台：`/admin`，用于用户、积分和备份管理。
- 图像 API 设置：`/admin/image-api-settings`，管理员可配置图像服务端点、服务端 API Key 与**全局任务并发**。
- API 文档：`/api-docs`，提供公开任务 API 的调用说明；更完整的接口定义见后端 Swagger `/docs`。

图像服务 API Key 仅保存在服务端。管理员读取或保存设置时，已保存的 Key 不会回显；留空保存表示保留已有 Key。

## 全局任务队列

任务状态为：

- `queued`：已进入全局等待队列，响应中的 `queuePosition` 表示其前方等待任务数。
- `processing`：服务器正在处理。
- `completed`：任务完成，可下载 PNG。
- `failed`：任务失败，响应中的 `error` 包含失败原因。

全局任务并发由管理员在 `/admin/image-api-settings` 配置，默认 `10`，仅允许整数 `1-32`。该值限制服务器对**所有用户**的最大同时处理数量，不是单用户限制；保存后会立即唤醒调度器。首页没有用户可调的抠图并发设置；浏览器端仅使用固定请求工作池处理上传和批量提交。

## 任务 API

本地开发服务地址：`http://localhost:7333`。所有任务提交、查询和下载均要求使用任务归属用户的 API Key：

```http
X-API-Key: fk_xxx
```

### 提交任务

```http
POST /api/tasks/submit
Content-Type: multipart/form-data
X-API-Key: fk_xxx
```

表单字段：`file`（图片文件）。成功响应包含 `taskId`、`status`、`progress`、`queuePosition`、`imageUrl` 和 `statusUrl`。

```powershell
curl.exe -X POST "http://localhost:7333/api/tasks/submit" -H "X-API-Key: fk_xxx" -F "file=@input.jpg"
```

### 查询任务

```http
GET /api/tasks/{taskId}
X-API-Key: fk_xxx
```

响应包含任务状态、进度、`queuePosition`（仅排队时有值）及完成后的 `imageUrl`。

### 下载结果图片

```http
GET /api/tasks/{taskId}/image
X-API-Key: fk_xxx
```

仅任务归属用户可查询或下载：缺少或无效 Key 返回 `401`，访问他人任务返回 `403`。任务未完成时下载返回 `409`；无效图片或参数返回 `400`。

## 文件管理关键路由

```http
POST   /api/uploads/session
POST   /api/uploads/chunk
POST   /api/uploads/complete
GET    /api/files
GET    /api/files/{file_id}
GET    /api/files/{file_id}/png
GET    /api/files.zip
DELETE /api/files/{file_id}
```

`GET /api/files/{file_id}/png` 返回宽 1500 像素、96 DPI 的 PNG。

## 管理 API

管理接口使用管理员 Bearer Token。关键路由：

```http
POST /api/admin/login
GET  /api/admin/session
GET  /api/admin/users
POST /api/admin/users
PATCH /api/admin/users/{user_id}
GET  /api/admin/image-api-settings
PUT  /api/admin/image-api-settings
GET  /api/admin/backups/config
PUT  /api/admin/backups/config
```

图像 API 设置的 `GET`/`PUT /api/admin/image-api-settings` 返回 `endpointUrl`、`hasApiKey` 和 `maxTaskWorkers`，但绝不返回已保存的图像服务 API Key。更新并发时，`maxTaskWorkers` 必须为 `1-32` 的整数。

## 其他路由

- `POST /api/auth/login`：用户登录。
- `GET /api/users/me`：获取当前用户信息，需 `X-API-Key`。
- `GET /api/users/me/credit-records`：获取当前用户积分流水，需 `X-API-Key`。
- `GET /health`：健康检查。
