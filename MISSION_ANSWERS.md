# Day 14 Lab - Mission Answers

> Student: Vũ Lương Duy · MSSV: 2A202603945

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
Trong [develop/app.py](01-localhost-vs-production/develop/app.py):
1. **API key và mật khẩu DB hard-code** (dòng 17–18): `OPENAI_API_KEY = "sk-..."`, `DATABASE_URL = "postgresql://admin:password123@..."`. Push lên GitHub là lộ ngay, và có trong lịch sử commit thì xoá file cũng không đủ.
2. **Không có config management** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` viết cứng, muốn đổi giữa dev/staging/production phải sửa code.
3. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33, 38): không có mức log, timestamp hay định dạng để máy parse.
4. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Đã thấy key xuất hiện trong log server khi chạy thử.
5. **Không có health check** (dòng 42–43): nền tảng không biết agent còn sống hay đã treo để restart. Gọi `/health` ở bản develop trả 404.
6. **Port và host cố định** (dòng 51–52): `host="localhost"`, `port=8000`. `localhost` không nhận kết nối từ ngoài container, và Railway/Render cấp `PORT` qua biến môi trường.
7. **`reload=True`** (dòng 53): chế độ reload dùng cho phát triển, tốn tài nguyên và không ổn định ở production.
8. **Không xử lý tắt an toàn**: không có `lifespan` hay xử lý SIGTERM, request đang chạy có thể bị cắt ngang khi deploy.
9. **`/ask` nhận `question` qua query string** (dòng 31) và không kiểm tra độ dài hay định dạng đầu vào.

### Exercise 1.2: Chạy bản develop
`python app.py` trong `01-localhost-vs-production/develop`, rồi gọi thử:

```
GET  /                         → {"message":"Hello! Agent is running on my machine :)"}   (200)
POST /ask?question=Hello       → {"answer":"Agent đang hoạt động tốt! (mock response) ..."} (200)
POST /ask  (JSON body như đề)  → {"detail":[{"type":"missing","loc":["query","question"],...}]} (422)
GET  /health                   → {"detail":"Not Found"}  (404)
```

Quan sát:
- Nó chạy được, nhưng **không** production-ready: gọi bằng JSON body như đề bài thì lỗi 422 vì code đọc `question` từ query string, không có `/health`.
- Log server in thẳng secret: `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`.

### Exercise 1.3: Comparison table
Bản production ([production/app.py](01-localhost-vs-production/production/app.py), [config.py](01-localhost-vs-production/production/config.py)) chạy thử cho kết quả: `/health` 200 (có `uptime_seconds`, `version`, `environment`, `timestamp`), `/ready` 200 `{"ready":true}`, `POST /ask` với JSON body 200 và có trường `model`.

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hard-code trong code (`DEBUG = True`, key, URL DB) | Đọc từ biến môi trường qua `Settings` (`os.getenv`), có validate: thiếu `AGENT_API_KEY` khi `ENVIRONMENT=production` thì báo lỗi ngay | Cùng một image chạy ở dev/staging/production, không lộ secret trong repo (12-Factor) |
| Secrets | `sk-...` và mật khẩu DB trong code, còn in ra log | `OPENAI_API_KEY`, `AGENT_API_KEY` lấy từ env; không log secret, chỉ log độ dài câu hỏi | Lộ key = mất tiền và dữ liệu |
| Health check | Không có (`/health` → 404) | `/health` (liveness, kèm uptime/version) và `/ready` (readiness, 503 khi chưa sẵn sàng) | Nền tảng dùng liveness để restart container treo, load balancer dùng readiness để quyết định có route traffic hay không |
| Logging | `print()` | Log có cấu trúc, ghi sự kiện bằng `json.dumps` (`startup`, `agent_request`, `agent_response`) | Công cụ gom log (Datadog, Loki) parse và lọc được; không rò rỉ dữ liệu nhạy cảm |
| Shutdown | Đột ngột, không xử lý | `lifespan` đặt `is_ready = False` rồi dọn dẹp; có handler SIGTERM | Platform gửi SIGTERM khi deploy; request đang chạy không bị cắt ngang |
| Host / Port | `localhost:8000` cố định | `HOST=0.0.0.0`, `PORT` từ env | `0.0.0.0` để nhận kết nối từ ngoài container; Railway/Render cấp `PORT` động |
| Reload | `reload=True` | `reload=settings.debug` (chỉ khi `DEBUG=true`) | Reload không dùng ở production |
| Input | `question` qua query string, không kiểm tra | Đọc JSON body, trả 422 khi thiếu `question` | API rõ ràng, lỗi đầu vào trả mã đúng |
| CORS | Không cấu hình | Chỉ cho phép origin trong `ALLOWED_ORIGINS` | Hạn chế trang web lạ gọi API từ trình duyệt |

**Checkpoint 1:**
- Hard-code secret nguy hiểm vì key nằm trong lịch sử Git, ai có repo đều dùng được, và xoá file không xoá được lịch sử.
- Biến môi trường tách cấu hình khỏi code: cùng một code, mỗi môi trường một giá trị.
- Health check cho nền tảng biết khi nào restart (liveness) và khi nào chuyển traffic vào (readiness).
- Graceful shutdown là nhận SIGTERM, ngừng nhận request mới, xử lý xong request đang chạy rồi mới thoát.

**Câu hỏi thêm khi đọc code production:**

1. *Vì sao `/health` và `/ready` là hai endpoint riêng?*
   Hai endpoint trả lời hai câu hỏi khác nhau. `/health` (liveness) hỏi "process còn sống không?", luôn trả 200 khi process chạy; nếu fail, nền tảng **restart** container. `/ready` (readiness) hỏi "đã sẵn sàng nhận traffic chưa?", trả 503 khi `is_ready = False` (ngay sau khi khởi động hoặc lúc đang shutdown); nếu fail, load balancer **ngừng gửi request** vào instance đó nhưng không restart. Nếu gộp làm một, app đang khởi động hay đang tắt sẽ bị restart oan, hoặc ngược lại app chưa sẵn sàng vẫn bị gửi traffic.

2. *Nếu `ENVIRONMENT=production` mà quên đặt `AGENT_API_KEY` thì chuyện gì xảy ra, và vì sao thiết kế như vậy là tốt?*
   `Settings().validate()` trong `config.py` (dòng 42–43) ném `ValueError: AGENT_API_KEY must be set in production!` ngay khi import, nên app **không khởi động được**. Đây là nguyên tắc *fail fast*: thà lỗi rõ ràng lúc deploy, nền tảng thấy container thất bại và giữ lại bản cũ, còn hơn chạy với cấu hình thiếu và để lộ API không có xác thực cho người dùng thật.

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
