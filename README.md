# photo-upload

訪客上傳照片、多螢幕同步輪播、管理員抽獎。正式跑法是 Docker Compose（nginx + gunicorn + Redis）。

## 運行條件

- Docker 與 Compose（Apple Silicon / `linux/arm64` 映像）
- 主機上有一塊 **Docker 可掛載** 的照片目錄（檔案不進 image）
- 對外 **8000** 沒被佔用
- 能拉 `ghcr.io/chalmers-chang/photo-upload` 與 `photo-upload-nginx`
- Redis 由 compose 起，資料在 named volume `redis-data`

本機用 Flask 直接跑 **不會** 提供 `/photos/`（那是 nginx）。除錯也請走 compose。

## 啟動

在 `docker-compose/`：

```bash
# 可選：改照片目錄、映像 tag
# echo 'HOST_PHOTO_DIR=/your/photo/path' >> .env

docker compose pull
docker compose up -d
```

瀏覽器開 `http://localhost:8000`。管理後台 `/admin`。

推到 `main` 或 `feature/**` 會由 GitHub Actions 建 arm64 image，並在 self-hosted Mac runner 上 `compose pull && compose up -d`。

## 要改的地方

**換機器時幾乎一定要改**

| 項目 | 位置 | 說明 |
| --- | --- | --- |
| 照片目錄 | compose 的 `HOST_PHOTO_DIR`（或 `.env`） | 預設是 `/Volumes/OWC Envoy Pro FX/photo-upload`。`app` 與 `nginx` 都要掛同一路徑 |
| 管理帳密 | `app` 環境變數 `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 預設在 `config/admin.py`，不要沿用 |
| `SECRET_KEY` | 同上 | 預設在 `config/appsetting.py`，cookie 會用它 |

**看需求再改（環境變數，寫在 compose `app.environment`）**

| 變數 | 預設 | 用途 |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | compose 內不用改 |
| `PHOTO_DIR` | 容器內 `/data/photos` | 對應掛載點，不要改成主機路徑 |
| `SLIDESHOW_INTERVAL` | `8` | 輪播秒數 |
| `RECORD_TTL_DAYS` | `20` | Redis 紀錄過期天數（檔案不會自動刪） |
| `MAX_UPLOAD_MB` | `20` | 單張上限；nginx 是 `client_max_body_size 25m` |
| `JPEG_MAX_EDGE` | `2560` | 上傳後長邊像素 |
| `GUNICORN_WORKERS` | `2` | |
| `GUNICORN_TIMEOUT` | `120` | |
| `LOTTERY_SECONDS` | `7` | 抽獎球體旋轉秒數 |
| `LOTTERY_SPHERE_MAX` | `60` | 球體照片數 |

**改產品文案或依賴**

- 中英字串：`config/msg.py`
- Python 套件：`python/` 裡 `uv add` / `uv lock`，提交 `pyproject.toml` 與 `uv.lock`
- nginx 設定：`docker-compose/nginx.conf`（烤進 nginx image，改完要重建）

## 使用

1. `/admin` 建專案（可填 slug，空白則從名稱產生）
2. 訪客走 `/p/<slug>/` → 上傳或輪播
3. 每個專案可傳 `pjt-`（首頁兩顆按鈕底圖）與 `bkg-`（輪播背景）
4. 抽獎僅管理員：`/p/<slug>/lottery`

## 目錄

```
config/           設定與文案
web/              Flask 應用
python/           uv 依賴（程式不在這裡）
docker-compose/   Dockerfile、compose、nginx.conf
```
