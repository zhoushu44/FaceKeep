# Avatar Cutout API

一个最小 FastAPI 服务，用 RetinaFace 检测头像区域，用 RMBG-2.0 生成透明背景头像 PNG。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 下载模型

```powershell
python models_init.py
```

## 启动

```powershell
uvicorn api:app --host 0.0.0.0 --port 8000
```

## 调用

```powershell
curl.exe -X POST "http://127.0.0.1:8000/avatar" -F "file=@input.jpg" --output avatar.png
```
