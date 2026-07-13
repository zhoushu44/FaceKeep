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

### 镜像架构与数据持久化

镜像采用单容器架构，由 Supervisor 同时管理 Nginx 和 Uvicorn：

- Nginx 监听 `0.0.0.0:9966`，提供前端静态文件，并将 API、健康检查和 Swagger 等请求反向代理到 Uvicorn。
- FastAPI/Uvicorn 在容器内部监听 `0.0.0.0:7333`。
- 部署时只暴露并映射 Nginx 的 `9966` 端口，不直接将容器的 `7333` 端口暴露到宿主机或公网。

**必须将 `/app/uploads` 持久化挂载到宿主机。** metadata、用户、任务、积分、图像 API 配置、备份配置，以及任务输入和输出文件均保存在该目录。未挂载时，这些数据会随容器删除而丢失。

### 环境变量

在宿主机创建 `.env.production`，示例：

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置高强度管理员密码
CUTOUT_MODE=api
IMAGE_API_MODEL=gpt-image-2
```

推荐登录管理后台 `/admin/image-api-settings` 保存图像服务 Endpoint 和 Key。也可以在宿主机环境文件中配置：

```dotenv
IMAGE_API_BASE_URL=https://你的图像服务地址
IMAGE_API_KEY=你的图像服务密钥
```

密钥不要提交到 Git，也不要写入 Dockerfile 或构建进镜像。仓库 `.dockerignore` 已排除 `.env`；使用 `.env.production` 时同样不得提交，并应在镜像构建完成后创建，或将它放在 Docker 构建上下文之外。

### 本地构建并运行

PowerShell（在项目根目录执行）：

```powershell
docker build -t facekeep:local .
New-Item -ItemType Directory -Force .\uploads | Out-Null
@"
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置高强度管理员密码
CUTOUT_MODE=api
IMAGE_API_MODEL=gpt-image-2
"@ | Set-Content -Encoding utf8 .\.env.production
docker run -d --name facekeep --restart unless-stopped -p 9966:9966 --env-file .\.env.production --mount "type=bind,source=$((Resolve-Path .\uploads).Path),target=/app/uploads" facekeep:local
```

Linux/macOS（在项目根目录执行）：

```bash
docker build -t facekeep:local .
mkdir -p ./uploads
cat > .env.production <<'EOF'
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请设置高强度管理员密码
CUTOUT_MODE=api
IMAGE_API_MODEL=gpt-image-2
EOF
docker run -d --name facekeep --restart unless-stopped -p 9966:9966 --env-file ./.env.production --mount type=bind,source="$(pwd)/uploads",target=/app/uploads facekeep:local
```

本地访问地址为 `http://localhost:9966/`。以上本地构建只生成 `facekeep:local`，不会推送镜像到 Docker Hub。

### 使用 Docker Hub 镜像部署

先在服务器准备持久化目录和环境文件：

```bash
sudo mkdir -p /opt/facekeep/uploads
sudo nano /opt/facekeep/.env.production
```

将上面的环境变量示例写入 `/opt/facekeep/.env.production`，然后拉取并运行镜像。请将命令中的 `<DOCKER_HUB_USERNAME>` 替换为实际 Docker Hub 用户名；完整镜像占位符为 **`<DOCKER_HUB_USERNAME>/facekeep:1.0`**，不要原样执行。

```bash
docker pull <DOCKER_HUB_USERNAME>/facekeep:1.0
docker run -d \
  --name facekeep \
  --restart unless-stopped \
  -p 9966:9966 \
  --env-file /opt/facekeep/.env.production \
  --mount type=bind,source=/opt/facekeep/uploads,target=/app/uploads \
  <DOCKER_HUB_USERNAME>/facekeep:1.0
```

标准部署统一使用 `-p 9966:9966`。若宿主机 `9966` 端口已被占用，请先释放该端口；也可以选择其他空闲的宿主机端口映射到容器 `9966`，例如 `-p <其他宿主机端口>:9966`。

### 安全更新容器

更新前建议先备份 `/opt/facekeep/uploads`。拉取新镜像后停止并删除旧容器，再使用**相同的环境文件和 uploads 挂载**重新创建：

```bash
docker pull <DOCKER_HUB_USERNAME>/facekeep:1.0
docker stop facekeep
docker rm facekeep
docker run -d \
  --name facekeep \
  --restart unless-stopped \
  -p 9966:9966 \
  --env-file /opt/facekeep/.env.production \
  --mount type=bind,source=/opt/facekeep/uploads,target=/app/uploads \
  <DOCKER_HUB_USERNAME>/facekeep:1.0
```

不要使用会删除 volume 或宿主机 uploads 数据的命令。删除并重建容器不会影响正确 bind mount 到 `/opt/facekeep/uploads` 的数据。

### 健康验证与日志

```bash
docker ps
docker logs --tail 200 facekeep
curl http://localhost:9966/health
curl -I http://localhost:9966/
curl -I http://localhost:9966/docs
```

若将其他宿主机端口映射到容器 `9966`，请将验证地址中的 `9966` 相应替换为所选宿主机端口。持续查看日志可执行 `docker logs -f facekeep`。

### 常见问题

- **图像 API 调用失败**：先执行 `docker logs --tail 200 facekeep` 查看后端错误，再核对管理后台或环境变量中的 Endpoint、Key 和模型。
- **重建容器后数据丢失**：检查 `docker inspect facekeep`，确认宿主机 uploads 目录确实 bind mount 到 `/app/uploads`，并确认重新运行时使用了同一路径。
- **已配置 API 但仍未调用**：API 模式要求 `CUTOUT_MODE=api`；修改环境文件后必须停止并重新创建容器，单纯重启不会重新读取已变化的 `--env-file`。
- **第三方图像服务不兼容**：Endpoint 应兼容 OpenAI 的 `/v1/images/edits` 接口。
- **上传返回 `413 Request Entity Too Large`**：当前容器 Nginx 的 `client_max_body_size` 上限为 `100m`，需缩小单次上传内容；如需提高上限，应同步调整 `docker/nginx.conf` 并重新构建镜像。

### GitHub Actions 自动发布

工作流 `.github/workflows/docker-publish.yml` 会在代码 push 到 `main` 或 `master` 分支时运行。仓库需要配置以下 GitHub Actions Secrets：

- `DOCKER_HUB_USERNAME`：Docker Hub 用户名。
- `DOCKER_HUB_TOKEN`：Docker Hub Access Token。

同一次构建会推送 `${DOCKER_HUB_USERNAME}/facekeep:1.0` 和 `${DOCKER_HUB_USERNAME}/facekeep:latest` 两个标签。前述本地 `docker build` 命令不会执行推送。

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
