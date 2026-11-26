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

### Exercise 2.1: Dockerfile questions
Dựa trên [02-docker/develop/Dockerfile](02-docker/develop/Dockerfile):
1. **Base image:** `python:3.11` (dòng 8), bản Python đầy đủ trên Debian. Nặng vì chứa nhiều công cụ build (trong `docker history` có một layer `apt-get` riêng 696 MB).
2. **Working directory:** `/app` (dòng 11). Các lệnh `COPY`/`RUN`/`CMD` phía sau tính từ đây.
3. **Vì sao `COPY requirements.txt` trước:** tận dụng layer cache. Code đổi thường xuyên, `requirements.txt` hiếm khi đổi. Đặt `COPY requirements.txt` + `pip install` trước `COPY app.py` thì khi chỉ sửa code, bước cài thư viện được dùng lại từ cache (xem bảng đo ở Exercise 2.2).
4. **`CMD` vs `ENTRYPOINT`:** `CMD` là lệnh mặc định, bị thay thế khi truyền lệnh vào `docker run`. `ENTRYPOINT` là chương trình cố định của container, tham số của `docker run` được nối vào sau. Dockerfile này dùng `CMD ["python", "app.py"]` (dạng exec) nên `python` là PID 1 và nhận SIGTERM trực tiếp.

### Exercise 2.2: Build và run (bản develop)
```
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d -p 8000:8000 --name agent-dev my-agent:develop
curl http://localhost:8000/health   → {"status":"ok","uptime_seconds":207.9,"container":true}
curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
  → {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```
- Vào trong container (`docker exec -it agent-dev sh`): `pwd` = `/app`, thư mục có `app.py`, `requirements.txt`, `utils/mock_llm.py`; `whoami` = **`root`** (điểm yếu bảo mật của bản develop).
- `docker history my-agent:develop`: phần lớn dung lượng nằm ở base image Python; `pip install` chỉ 53,3 MB, `COPY app.py` / `COPY utils` chỉ ~12–16 KB mỗi layer.
- Lưu ý: gọi `curl` ngay lúc `docker run` vừa xong trả `Empty reply from server`, vì uvicorn chưa khởi động xong. Container "Up" chưa có nghĩa là app sẵn sàng, nên cần HEALTHCHECK/readiness.

**Thí nghiệm layer cache** (build lại 3 lần, bản develop):

| Lần | Thay đổi | Thời gian | Bước dùng cache | Bước chạy lại |
|---|---|---|---|---|
| 1 | Không đổi | 2,0 s | `[2/7]`–`[7/7]` đều `CACHED` | Không có |
| 2 | Sửa `app.py` | 2,8 s | `[2/7]`, `[3/7]` COPY requirements, `[4/7]` pip install | Từ `[5/7]` COPY app.py |
| 3 | Sửa `requirements.txt` | 17,8 s | Chỉ `[2/7]` | Từ `[3/7]`, gồm cả `pip install` (11,7 s) |

Kết luận: một layer đổi thì mọi layer sau nó phải build lại. Đặt phần ít đổi (dependencies) lên trước giúp sửa code chỉ mất vài giây.

### Exercise 2.3: Multi-stage build
Dựa trên [02-docker/production/Dockerfile](02-docker/production/Dockerfile):
- **Stage 1 (`builder`):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev` (công cụ build) rồi `pip install --user` các thư viện. Chỉ để build, không được deploy. Trong log build, `apt-get` mất 26,0 s và `pip install` 13,7 s.
- **Stage 2 (`runtime`):** bắt đầu lại từ `python:3.11-slim` sạch, tạo user không phải root `appuser`, chỉ `COPY --from=builder /root/.local` (thư viện đã cài) cùng `main.py` và `mock_llm.py`; có `HEALTHCHECK`, chạy `uvicorn --workers 2` bằng `appuser`.
- **Vì sao nhỏ hơn:** (1) base `-slim` thay vì `python:3.11` đầy đủ; (2) `gcc`, `libpq-dev`, cache `apt` ở lại stage builder và bị bỏ đi, stage runtime chỉ lấy kết quả cài đặt.

Kiểm tra bản advanced: `/health` trả 200 (`version: 2.0.0`), `docker exec agent-adv whoami` = **`appuser`** (không còn root), `docker inspect` health = **`healthy`**.

### Image size comparison
Đo bằng `docker images my-agent` (Docker dùng đơn vị thập phân):
- Develop (`python:3.11`, single-stage): **1.67 GB** (≈ 1670 MB)
- Production (`python:3.11-slim`, multi-stage): **240 MB**
- Difference: giảm **≈ 86%** (nhỏ hơn khoảng 7 lần), thấp hơn nhiều so với ngưỡng 500 MB.

### Exercise 2.4: Docker Compose stack
Dựa trên [02-docker/production/docker-compose.yml](02-docker/production/docker-compose.yml) (`docker compose -f ... up --build`):

```
        Client (curl / trình duyệt)
                   │  :80 (và :443)
                   ▼
            ┌─────────────┐
            │   nginx     │  reverse proxy + load balancer
            │  (alpine)   │  rate limit 10 req/s, security headers
            └──────┬──────┘
   ═══════ network "internal" (bridge, không map cổng ra ngoài) ═══════
                   │  http://agent:8000  (upstream agent_backend)
                   ▼
            ┌─────────────┐
            │   agent     │  FastAPI + uvicorn (2 workers), user appuser
            └───┬─────┬───┘
   REDIS_URL    │     │   QDRANT_URL
 redis://redis  ▼     ▼   http://qdrant:6333
         ┌────────┐ ┌─────────┐
         │ redis  │ │ qdrant  │   volumes: redis_data, qdrant_data
         └────────┘ └─────────┘
```

- **4 service được start:** `nginx`, `agent`, `redis`, `qdrant`.
- **Giao tiếp:** các service nối với nhau trong network `internal` và gọi nhau **bằng tên service** (Docker DNS), ví dụ `agent:8000`, `redis:6379`, `qdrant:6333`. Chỉ `nginx` được map cổng ra máy (`80`, `443`); `agent`, `redis`, `qdrant` chỉ có cổng nội bộ.
- **Thứ tự khởi động:** `agent` có `depends_on` với `condition: service_healthy` cho `redis` và `qdrant`, nên chờ hai service này `healthy` rồi mới chạy; `nginx` chạy sau `agent`. Log cho thấy đúng thứ tự: redis/qdrant → agent → nginx.
- Cần tạo file rỗng `02-docker/production/.env.local` (compose có `env_file`, file nằm trong `.gitignore`).

Kết quả test (`docker compose ps`: `agent`, `redis`, `qdrant` đều `healthy`):
```
curl http://localhost/health      → {"status":"ok","uptime_seconds":3.4,"version":"2.0.0",...}   (qua Nginx)
curl -X POST http://localhost/ask → {"answer":"Agent đang hoạt động tốt! (mock response) ..."}   (200, qua Nginx)
curl http://localhost:8000/health → Failed to connect (agent không map cổng ra ngoài, đúng thiết kế)
docker compose exec nginx wget -qO- http://agent:8000/health → {"status":"ok",...}   (nginx gọi agent bằng tên service)
docker compose exec redis redis-cli ping → PONG
```
Lưu ý khi test: dùng PowerShell 5.1, chuỗi JSON có dấu cách bị tách nên `/ask` lỗi 500 (`JSONDecodeError`); truyền body qua pipe (`'{"question":"..."}' | curl.exe ... -d "@-"`) thì chạy đúng.

**Debug container:** `docker logs <tên>`, `docker exec -it <tên> sh`, `docker compose ps`, `docker inspect --format "{{.State.Health.Status}}" <tên>`.

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

### Exercise 4.1: API Key authentication
Dựa trên [04-api-gateway/develop/app.py](04-api-gateway/develop/app.py) (chạy `AGENT_API_KEY=my-secret-key python app.py`):
- **Check ở đâu:** hàm `verify_api_key` (dòng 39–54), dùng làm dependency `Depends(verify_api_key)` của `/ask`. Đọc header `X-API-Key` bằng `APIKeyHeader`, so với `API_KEY` lấy từ biến môi trường `AGENT_API_KEY`. `/` và `/health` không có dependency nên công khai.
- **Sai key:** thiếu key → **401** `Missing API key`; sai key → **403** `Invalid API key`.
- **Rotate key:** đổi biến môi trường `AGENT_API_KEY` rồi restart, không sửa code. Hạn chế: chỉ có một key và so sánh bằng `!=` (bản Part 6 dùng `secrets.compare_digest`).

Output test (3 trường hợp):
```
(không có key)   POST /ask → HTTP/1.1 401 Unauthorized   {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
(sai key)        POST /ask → HTTP/1.1 403 Forbidden      {"detail":"Invalid API key."}
(đúng key)       POST /ask → HTTP/1.1 200 OK             {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) ..."}
```

### Exercise 4.2: JWT authentication
Dựa trên [production/auth.py](04-api-gateway/production/auth.py) và `app.py`. Lưu ý endpoint thật là `/auth/token` và user mẫu là `student`/`demo123`, `teacher`/`teach456` (đề trong `CODE_LAB.md` ghi `/token` và `admin`/`secret`, không khớp code).

**Luồng JWT:** `POST /auth/token` với username/password → server `authenticate_user` rồi `create_token` ký token HS256 chứa `sub`, `role`, `iat`, `exp` (60 phút) → client gửi `Authorization: Bearer <token>` → `verify_token` kiểm tra chữ ký và hạn, lấy `username`/`role` mà không cần tra database (stateless).

```
POST /auth/token {"username":"student","password":"demo123"}
  → 200 {"access_token":"<token đã che>","token_type":"bearer","expires_in_minutes":60,...}
POST /ask  (Authorization: Bearer <token>)
  → HTTP/1.1 200 OK  {"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
POST /ask  (không có token)          → HTTP/1.1 401 Unauthorized  www-authenticate: Bearer
                                       {"detail":"Authentication required. Include: Authorization: Bearer <token>"}
POST /ask  (Bearer abc.def.ghi)      → HTTP/1.1 403 Forbidden     {"detail":"Invalid token."}
POST /auth/token (sai mật khẩu)      → HTTP/1.1 401 Unauthorized  {"detail":"Invalid credentials"}
```
Ghi chú: token hết hạn trả 401, token sai chữ ký trả 403. Trường `budget_remaining_usd` trong code thực ra là số tiền **đã dùng** (`usage.total_cost_usd`), tên gây hiểu nhầm.

### Exercise 4.3: Rate limiting
Dựa trên [production/rate_limiter.py](04-api-gateway/production/rate_limiter.py):
- **Algorithm:** sliding window. Mỗi user có một `deque` lưu timestamp; mỗi lần gọi xoá timestamp cũ hơn 60 giây rồi đếm số còn lại.
- **Limit:** user **10 req/phút**, admin **100 req/phút** (dòng 86–87).
- **Bypass cho admin:** không bỏ qua hẳn; `app.py` dòng 141 chọn `rate_limiter_admin` (limit cao hơn) khi `role == "admin"`.
- **Hạn chế:** bộ đếm nằm trong RAM của một process, nên nhiều worker/instance đếm riêng và restart là mất. Vì vậy Part 6 dùng Redis.

Gọi liên tục 20 lần bằng token của `student`:
```
1 : 200 ... 10 : 200
11 : 429 ... 20 : 429
```
(10 lần 200 vì request thành công trước đó đã ngoài cửa sổ 60 giây.) Chi tiết một phản hồi 429:
```
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795704834
retry-after: 48
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":48}}
```
Gọi 20 lần bằng token của `teacher` (admin): tất cả `200`. `student` gọi `/admin/stats` → `403 {"detail":"Admin only"}`. `/me/usage` của `student` sau 11 request: `requests: 11`, `cost_usd: 0.000211`, `budget_used_pct: 0.0`.

### Exercise 4.4: Cost guard implementation
**Bản demo** ([production/cost_guard.py](04-api-gateway/production/cost_guard.py)): class `CostGuard` lưu trong RAM, ngân sách $1/ngày cho mỗi user và $10/ngày toàn hệ thống. `check_budget` chạy **trước** khi gọi LLM: vượt ngân sách user → **402** Payment Required, vượt ngân sách toàn cục → **503**, đạt 80% thì ghi cảnh báo. `record_usage` chạy **sau** khi gọi LLM để cộng token (đổi ra USD theo giá/1K token).

**Cách tôi làm ở Part 6** ([06-lab-complete/app/cost_guard.py](06-lab-complete/app/cost_guard.py)), lưu trong Redis để dùng chung giữa các worker và không mất khi restart:
- `record_cost(input_tokens, output_tokens)` tính chi phí rồi `INCRBYFLOAT` vào hai key `cost:day:YYYY-MM-DD` và `cost:month:YYYY-MM` (gói trong một pipeline), kèm `EXPIRE` (2 ngày và 32 ngày) để tự reset khi sang ngày/tháng mới.
- `check_budget()` gọi `MGET` đọc hai key trước khi gọi LLM; nếu tổng vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` thì trả **402**.
- Khi Redis lỗi, trả **503** (fail closed) thay vì cho qua, để không mất kiểm soát chi phí.
- Kiểm chứng: script `check_production_ready.py` đặt budget `0.000001` USD và nhận 402 ở request đầu tiên.

Hạn chế: bước kiểm tra và bước ghi là hai lệnh tách nhau, nên các request đồng thời có thể vượt ngân sách một chút; production thật thường gộp vào một script Lua hoặc dùng cơ chế "đặt chỗ" (reserve) trước khi gọi LLM. Chi phí chỉ là ước lượng theo số từ nên chưa chính xác như số token thật của nhà cung cấp.

**Rate limit và cost guard bổ sung cho nhau:** rate limit bảo vệ *tốc độ* (chống spam, DoS), cost guard bảo vệ *tiền* (một user gọi chậm nhưng prompt rất dài vẫn có thể đốt ngân sách).

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
