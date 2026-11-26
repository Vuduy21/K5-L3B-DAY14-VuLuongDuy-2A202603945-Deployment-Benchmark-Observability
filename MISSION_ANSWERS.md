# Day 14 Lab - Mission Answers

> Student: Vũ Lương Duy · MSSV: 2A202603945

## Part 1: Localhost vs Production

> TODO — chạy `01-localhost-vs-production/develop` và `production`, điền các mục dưới đây.

### Exercise 1.1: Anti-patterns found
1. _TODO_ (ít nhất 5, kèm dòng code trong `develop/app.py`)

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| _TODO_  |         |            |                |

## Part 2: Docker

> TODO — số MB phải đo bằng `docker images`, không chép từ README.

### Exercise 2.1: Dockerfile questions
1. Base image: _TODO_
2. Working directory: _TODO_
3. Vì sao `COPY requirements.txt` đứng trước `COPY . .`: _TODO_
4. `CMD` vs `ENTRYPOINT`: _TODO_

### Exercise 2.3: Image size comparison
- Develop: _TODO_ MB
- Production: _TODO_ MB
- Difference: _TODO_ %

### Exercise 2.4: Docker Compose stack
_TODO — sơ đồ các service và kết quả test qua Nginx._

## Part 3: Cloud Deployment

### Exercise 3.2: Render deployment (nền tảng chính)
- URL: https://ai-agent-o0tr.onrender.com
- Agent được deploy là agent Part 6 (`06-lab-complete/`), chi tiết lệnh test và biến môi trường trong [DEPLOYMENT.md](DEPLOYMENT.md).
- Screenshots: [dashboard](screenshots/dashboard.png) · [service running](screenshots/running.png) · [test results](screenshots/test.png)
- Kết quả 4 lệnh tự kiểm: `/health` 200, `/ready` 200, `/ask` không key 401, `/ask` có key 200; gửi 15 request liên tiếp → `200 ×9` rồi `429 ×6` (RATE_LIMIT_PER_MINUTE=10, request test trước đó vẫn nằm trong cửa sổ 60 giây).
- Ghi chú khi deploy: `render.yaml` nằm trong `06-lab-complete/` nên `dockerfilePath` và `dockerContext` phải tính từ **gốc repo** (`./06-lab-complete/...`), nếu không Render không tìm thấy Dockerfile (lần deploy đầu bị Failed deploy vì lỗi này).

### Nền tảng còn lại: so sánh `railway.toml` với `render.yaml`

| Khía cạnh | `railway.toml` | `render.yaml` | Vì sao khác |
|---|---|---|---|
| Phạm vi | Chỉ mô tả build + deploy của **một** service | Blueprint mô tả **cả hệ thống**: web service + Redis + biến môi trường | Railway tách hạ tầng (plugin Redis, biến) ra dashboard/CLI; Render theo hướng Infrastructure as Code, một file dựng cả stack |
| Build | `[build] builder = "DOCKERFILE"` (hoặc `NIXPACKS` tự dò) | `runtime: docker` + `dockerfilePath` / `dockerContext` | Cùng ý nghĩa; Render yêu cầu đường dẫn tính từ gốc repo |
| Health check | `[deploy] healthcheckPath`, `healthcheckTimeout` | `healthCheckPath` | Cùng chức năng: nền tảng chỉ chuyển traffic khi `/health` trả 200 |
| Restart | `restartPolicyType`, `restartPolicyMaxRetries` khai báo trong file | Render tự restart, không cấu hình ở đây | Railway cho tinh chỉnh chính sách restart |
| Secret | Không có trong file; đặt bằng `railway variables set` | `generateValue: true` (Render tự sinh) hoặc `sync: false` (nhập tay) | Render quản lý được vòng đời secret ngay trong blueprint mà không lộ giá trị |
| Redis | Thêm plugin rồi tham chiếu `${{Redis.REDIS_URL}}` | `type: keyvalue` + `fromService` → `REDIS_URL` | Render nối sẵn connection string trong YAML |
| Cổng | Railway cấp `$PORT` | Render cấp `PORT` (thường 10000) | Cả hai đều cấp cổng động, nên `CMD` phải đọc `${PORT:-8000}` |
| Gói miễn phí | Trial/credit giới hạn | Free nhưng ngủ sau ~15 phút không có request | Ảnh hưởng đến cold start khi chấm |

### Exercise 3.3: Cloud Run (`cloudbuild.yaml` + `service.yaml`)
- Pipeline `cloudbuild.yaml` chạy tự động khi push lên `main`, gồm 4 bước nối nhau bằng `waitFor`: **test** (cài dependencies, chạy `pytest`) → **build** image Docker, gắn tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` để tận dụng layer cache → **push** lên Container Registry → **deploy** lên Cloud Run (`gcloud run deploy`, region `asia-southeast1`).
- Test lỗi thì dừng, không build hay deploy. Secret (`OPENAI_API_KEY`) lấy từ Secret Manager bằng `--set-secrets`, không hard-code.
- `service.yaml` là cấu hình dạng IaC của service: `minScale: 1` (tránh cold start), `maxScale: 10`, `containerConcurrency: 80`, giới hạn CPU/RAM, secret từ `secretKeyRef`, `livenessProbe` ở `/health` và `startupProbe` ở `/ready`.

## Part 4: API Security

> TODO — chạy `04-api-gateway/`, dán output `curl -i` cho 401, 200, 429 (che token).

### Exercise 4.1-4.3: Test results
_TODO_

### Exercise 4.4: Cost guard implementation
_TODO — có thể mô tả cách làm ở Part 6: cộng dồn chi phí vào Redis (`INCRBYFLOAT`) theo ngày và tháng, `check_budget()` trước khi gọi LLM trả 402 khi vượt, `record_cost()` sau khi gọi, key tự hết hạn bằng `EXPIRE`. Xem `06-lab-complete/app/cost_guard.py`._

## Part 5: Scaling & Reliability

> TODO — chạy `05-scaling-reliability/`.

### Exercise 5.1-5.5: Implementation notes
_TODO_

## Part 6: Final Project

Code: [06-lab-complete/](06-lab-complete/) — URL public: https://ai-agent-o0tr.onrender.com

### Cách dùng Redis
- `redis_client.py`: client tạo lazy (`redis.from_url`), nên app vẫn khởi động được khi Redis chưa sẵn sàng; `redis_healthy()` (PING) phục vụ `/ready`.
- Rate limit: sorted set `rl:<sha256(api key)>`, sliding window 60 giây (`ZREMRANGEBYSCORE` → `ZCARD` → `ZADD` → `EXPIRE`); vượt giới hạn → 429 kèm `Retry-After`.
- Cost guard: `INCRBYFLOAT` trên key theo ngày và theo tháng; vượt budget → 402.
- Khi Redis lỗi, `/ask` trả 503 thay vì bỏ qua giới hạn.

### Output `check_production_ready.py`
Lần chạy đầy đủ trên Windows (có Docker): **11/12 tiêu chí ✅, 42/42 checks đạt**. Tiêu chí 11 (Graceful shutdown) ở trạng thái ⚠️ vì script không gửi được SIGTERM trên Windows. Phần `docker stop` của tiêu chí này đạt (exit code 0, 0.9s).

```
📋 Checklist Deliverable
   ✅ Dockerfile (multi-stage, < 500 MB)
   ✅ docker-compose.yml (agent + redis)
   ✅ .dockerignore
   ✅ Health check endpoint (GET /health)
   ✅ Readiness endpoint (GET /ready)
   ✅ API Key authentication
   ✅ Rate limiting
   ✅ Cost guard
   ✅ Config từ environment variables
   ✅ Structured logging
   ⚠️  Graceful shutdown
   ✅ Public URL ready (Railway / Render config)
Result: 11/12 tiêu chí đạt · 42/42 checks passed
```

Check SIGTERM ở runtime đã chạy riêng trong container Linux (`python:3.11-slim`, cùng script chấm, `--skip-docker`) và đạt: _"SIGTERM lúc đang có request → request vẫn 200, process tự thoát — exit code 0"_.

> TODO — chạy lại bản đầy đủ trên Linux/WSL2 có Docker để dán output `PASS 12/12` thay cho đoạn trên.

## AI Usage Log

- Công cụ: Claude Code (Claude Sonnet 5.5).
- Dùng cho: phân tích đề, viết code Part 6 (`app/*`, `Dockerfile`, `docker-compose.yml`, `render.yaml`...), sửa lỗi deploy Render, soạn `DEPLOYMENT.md` và phần Part 3/6 của file này.
- Tự kiểm chứng: chạy `check_production_ready.py`, tự gọi các lệnh `curl` trên URL public và chụp ảnh kết quả.
