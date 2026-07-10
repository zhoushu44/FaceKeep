# FaceKeep 文件管理与任务 API

FaceKeep 提供网页版文件管理系统，并支持任务模式 API：提交图片任务、查询任务状态、按任务 ID 提取处理后的 JPG 图片。

## 启动

```powershell
pip install -r requirements.txt
npm install
python -m uvicorn api:app --host 0.0.0.0 --port 8000
npm run dev -- --host 0.0.0.0 --port 5173
```

前端地址：`http://127.0.0.1:5173/`

后端地址：`http://127.0.0.1:8000/`

## 管理页面

访问 `http://127.0.0.1:5173/admin` 可进入用户与积分管理页面。

管理页面支持：

- 创建用户：输入登录用户名、姓名、密码、初始积分
- 自动生成 API Key
- 修改用户姓名、用户名、密码和 API Key
- 增加积分
- 减少积分
- 直接设置积分余额
- 查看积分流水
- 复制用户 API Key

## 用户页面

访问 `http://127.0.0.1:5173/login` 可进入用户登录页面。

用户登录后可访问 `http://127.0.0.1:5173/user` 查看：

- 用户名和姓名
- 当前积分余额
- API Key
- 个人积分流水

## 输出规格

任务模式和 JPG 下载接口输出：

- 格式：JPG
- 宽度：1500 像素
- 高度：按原图比例自适应
- DPI：96

任务模式会先调用头像抠图模型生成真实抠图结果，再合成白底 JPG 输出。

## 任务模式 API

### 1. 提交任务

上传一张图片，创建后台处理任务。该接口必须提供 API Key，系统会检测图片中的头部/人脸数量，按数量扣积分；最少扣 1 积分。

```http
POST /api/tasks/submit
Content-Type: multipart/form-data
```

参数：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 图片文件 |
| `api_key` | string | 否 | 可选，表单传 Key；也可用 `X-API-Key` 请求头 |

PowerShell 示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/tasks/submit" -H "X-API-Key: fk_xxx" -F "file=@input.jpg"
```

返回示例：

```json
{
  "taskId": "6e09b2f4e10d4f2b8a2b5cfe8de99a51",
  "statusUrl": "/api/tasks/6e09b2f4e10d4f2b8a2b5cfe8de99a51",
  "imageUrl": "/api/tasks/6e09b2f4e10d4f2b8a2b5cfe8de99a51/image"
}
```

### 2. 查询任务状态

```http
GET /api/tasks/{task_id}
```

PowerShell 示例：

```powershell
curl.exe "http://127.0.0.1:8000/api/tasks/6e09b2f4e10d4f2b8a2b5cfe8de99a51"
```

返回示例：

```json
{
  "taskId": "6e09b2f4e10d4f2b8a2b5cfe8de99a51",
  "status": "completed",
  "progress": 100,
  "fileName": "input.jpg",
  "imageUrl": "/api/tasks/6e09b2f4e10d4f2b8a2b5cfe8de99a51/image",
  "outputWidth": 1500,
  "outputHeight": 1000,
  "dpi": 96,
  "error": null,
  "createdAt": "2026-07-06T15:00:00+00:00",
  "updatedAt": "2026-07-06T15:00:01+00:00"
}
```

状态说明：

| 状态 | 说明 |
|------|------|
| `queued` | 已进入任务队列 |
| `processing` | 正在处理 |
| `completed` | 已完成，可提取图片 |
| `failed` | 处理失败，查看 `error` 字段 |

### 3. 提取图片

任务完成后，通过 `task_id` 下载处理后的 JPG 图片。

```http
GET /api/tasks/{task_id}/image
```

PowerShell 示例：

```powershell
curl.exe "http://127.0.0.1:8000/api/tasks/6e09b2f4e10d4f2b8a2b5cfe8de99a51/image" --output output.jpg
```

如果任务未完成，会返回：

```json
{
  "detail": "Task is not completed"
}
```

HTTP 状态码为 `409`。

## 文件管理 API

### 创建或恢复分片上传会话

```http
POST /api/uploads/session
Content-Type: application/json
```

### 上传分片

```http
POST /api/uploads/chunk
Content-Type: multipart/form-data
```

### 完成上传并合并文件

```http
POST /api/uploads/complete
Content-Type: application/json
```

### 获取文件列表

```http
GET /api/files
```

### 下载原图

```http
GET /api/files/{file_id}
```

### 下载 JPG 1500 像素宽 96 DPI 图片

```http
GET /api/files/{file_id}/jpg
```

### 批量下载原图 ZIP

```http
GET /api/files.zip
```

### 删除文件

```http
DELETE /api/files/{file_id}
```

## 管理 API

### 用户列表

```http
GET /api/admin/users
```

### 创建用户

```http
POST /api/admin/users
Content-Type: application/json
```

请求体：

```json
{
  "username": "user001",
  "name": "客户A",
  "password": "123456",
  "credits": 10
}
```

`apiKey` 由系统自动生成。

### 修改用户资料、密码或 Key

```http
PATCH /api/admin/users/{user_id}
Content-Type: application/json
```

```json
{
  "username": "user001_new",
  "name": "客户A-新名称",
  "password": "new_password_optional",
  "apiKey": "fk_new_key"
}
```

### 增减积分

```http
POST /api/admin/users/{user_id}/credits/adjust
Content-Type: application/json
```

加积分：

```json
{
  "amount": 10,
  "reason": "manual_add"
}
```

减积分：

```json
{
  "amount": -5,
  "reason": "manual_subtract"
}
```

### 设置积分余额

```http
POST /api/admin/users/{user_id}/credits/set
Content-Type: application/json
```

```json
{
  "credits": 100,
  "reason": "admin_set"
}
```

### 积分流水

```http
GET /api/admin/credit-records
GET /api/admin/credit-records?userId={user_id}
```

流水字段说明：

| 字段 | 说明 |
|------|------|
| `amount` | 变动积分，正数为增加，负数为扣除 |
| `balance` | 变动后的余额 |
| `reason` | 变动原因，任务扣费为 `task_image_cost` |
| `taskId` | 关联任务 ID |

## 登录 API

### 用户登录

```http
POST /api/auth/login
Content-Type: application/json
```

```json
{
  "username": "user001",
  "password": "123456"
}
```

返回用户信息和 API Key。

### 获取当前用户

```http
GET /api/users/me
X-API-Key: fk_xxx
```

### 获取当前用户积分流水

```http
GET /api/users/me/credit-records
X-API-Key: fk_xxx
```

## 健康检查

```http
GET /health
```
