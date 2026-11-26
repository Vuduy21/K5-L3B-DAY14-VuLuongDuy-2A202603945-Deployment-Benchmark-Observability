# Benchmark & Observability Report — Day 14

**Họ tên:** Vũ Lương Duy (MSSV 2A202603945)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11, Python 3.11.9, 22 logical CPU. Phần 2–3 chạy local: agent là **một process uvicorn** (`06-lab-complete/benchmark-observability/develop`), load generator `load_test.py` chạy trên cùng máy. Phần 4–5: Docker Desktop, stack Compose (2 agent 0,5 CPU/256 MB + Nginx + Prometheus + Grafana + Jaeger + Locust).

> Mọi con số trong các bảng lấy từ file trong [reports/](reports/) (JSON) và `benchmark-results/` (CSV).
> Agent chạy ở cổng 8011 (v1) và 8012 (v2) vì cổng 8001 đang có chương trình khác của máy chiếm.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Gấp khoảng 2 lần p50 (~200 ms) của mock LLM; người dùng chat thấy "nhanh" khi phản hồi dưới nửa giây. Dùng p95 (không dùng avg) để không bỏ sót tail latency |
| Error rate `/ask` | < 2 % | Mock LLM cố ý lỗi ~1% (`MOCK_ERROR_RATE`) giống upstream thật; ngưỡng 2% chừa ngân sách lỗi gấp đôi mức nền để không báo động vì dao động |
| Accuracy trên golden dataset | ≥ 85 % và không regression | Ngưỡng CI cho phép bản mới tệ đi chút ít khi thêm tính năng nhưng chặn mọi câu đã đúng mà nay sai. Mục tiêu thực tế trên tập 23 câu là 100% |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Lệnh: `python load_test.py --url http://localhost:8012 --requests 300 --concurrency N --out reports/load_v2_cN.json`

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.98 | 203.3 | 247.4 | 1718.3 | 1.00 % | PASS |
| 10 | 39.49 | 200.0 | 484.4 | 1707.2 | 1.33 % | PASS |
| 50 | 79.38 | 256.4 | 874.8 | 1701.9 | 0.67 % | **FAIL** (p95) |
| 100 | 38.97 | 1175.1 | 5415.9 | 5625.7 | 0.67 % | **FAIL** (p95) |

Nguồn: [load_v2_c1.json](reports/load_v2_c1.json), [load_v2_c10.json](reports/load_v2_c10.json), [load_v2_c50.json](reports/load_v2_c50.json), [load_v2_c100.json](reports/load_v2_c100.json).

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency.
- 1 → 10: RPS tăng gần đúng 10 lần (3,98 → 39,49) vì mỗi request chủ yếu *chờ* LLM (~200 ms), nhiều request chờ song song. Ở concurrency 1, RPS ≈ 1 / latency trung bình (1 / 0,2527 s ≈ 3,96).
- 10 → 50: chỉ tăng khoảng 2 lần (39,49 → 79,38), trong khi concurrency tăng 5 lần; p95 vọt từ 484 lên 875 ms (vượt SLO). Agent đã bắt đầu **bão hòa**: toàn bộ request chạy trong một process Python đơn luồng event-loop, còn phải tốn CPU cho JSON, ghi log, cập nhật metric.
- 50 → 100: RPS **giảm một nửa** (79 → 39) và p95 lên 5,4 s. Hiện tượng này lặp lại ổn định ở ba lần chạy riêng (38,97 / 41,24 / 41,05 RPS; p95 5,2–5,4 s), nên không phải nhiễu. Nguyên nhân chính xác tôi **chưa kiểm chứng**; giả thuyết hợp lý là hàng đợi kết nối của một process đơn (hoặc chính load generator chạy chung máy) bị quá tải, gây trễ theo bậc vài giây ở p90. Thêm thông lượng ở mức này phải scale ngang nhiều instance (xem mục 5), không phải tăng concurrency.
- Error rate dao động quanh 1% theo cấu hình mock (`MOCK_ERROR_RATE=0.01`), không đổi theo tải; toàn bộ là mã `503` do LLM mô phỏng.

### 2.2 Tail latency

Lệnh: khởi động lại v2 với `MOCK_SLOW_RATE=r`, rồi `python load_test.py --url http://localhost:8012 --requests 500 --concurrency 20 --out reports/load_v2_slow_r.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 211.2 | 261.1 | 503.8 |
| 0.03 (mặc định) | 249.3 | 475.1 | 1720.7 |
| 0.1 | 382.2 | 1703.0 | 1737.1 |

Nguồn: [load_v2_slow_0.json](reports/load_v2_slow_0.json), [load_v2_slow_0.03.json](reports/load_v2_slow_0.03.json), [load_v2_slow_0.1.json](reports/load_v2_slow_0.1.json).

**Nhận xét:** từ 0 lên 0.1, avg chỉ tăng khoảng 1,8 lần (211 → 382 ms) nhưng p95 tăng khoảng 6,5 lần (261 → 1703 ms). Percentile chỉ "nhảy" khi tỉ lệ request chậm vượt phần đuôi mà nó đo: ở 3% request chậm thì **p99** đã vọt lên 1721 ms (vì 3% > 1%) trong khi p95 mới 475 ms (3% < 5%); khi lên 10% thì cả p95 cũng vọt (10% > 5%). Trung bình bị "pha loãng" bởi đa số request nhanh nên trông vẫn ổn (249 ms ở mức 3% trong khi cứ 100 người có 3 người chờ gần 2 giây). Vì vậy SLO nên đặt theo **p95 hoặc p99**, không đặt theo average.
Lưu ý: ở `0.1` error rate đo được 2,20% (11/500) và ở `0` là 1,80% (9/500), cao hơn mức nền 1% do cỡ mẫu nhỏ (500 request); đây là dao động ngẫu nhiên của mock chứ không phải do slow rate.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Lệnh (trên Windows cần `PYTHONUTF8=1`, vì `run_eval.py` ghi file bằng `write_text()` không chỉ định encoding và lỗi `UnicodeEncodeError` với tiếng Việt):

```
python eval/run_eval.py --url http://localhost:8011 --out reports/eval_v1.json
python eval/run_eval.py --url http://localhost:8012 --out reports/eval_v2.json --baseline reports/eval_v1.json
# sau khi sửa KNOWLEDGE_BASE:
python eval/run_eval.py --url http://localhost:8012 --out reports/eval_v2_fixed.json --baseline reports/eval_v2.json --min-accuracy 1.0
```

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4,3 % (1/23) | 91,3 % (21/23) | **100 % (23/23)** |
| Avg tokens / câu | 56,9 | 108,8 | 113,7 |
| Tổng cost (USD) | 0,000402 | 0,000757 | 0,000790 |
| Cost / câu đúng (USD) | 0,00040155 | 0,00003607 | 0,00003436 |
| Quality gate | FAIL (exit 1) | PASS (exit 0) | PASS (exit 0, ngưỡng 100 %) |

Nguồn: [eval_v1.json](reports/eval_v1.json), [eval_v2.json](reports/eval_v2.json), [eval_v2_fixed.json](reports/eval_v2_fixed.json). `eval_v2.json` (baseline v1) và `eval_v2_fixed.json` (baseline `eval_v2.json`) đều có 0 regression; `eval_v1.json` là baseline gốc nên không có phép so sánh.

**Những câu v2 trả lời sai ban đầu và cách tôi sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `scaling-03` ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | `KNOWLEDGE_BASE` chưa có tài liệu nào khớp "hpa/kubernetes" nên retriever trả rỗng và agent trả câu chung chung. Thêm tài liệu kích hoạt bởi `["hpa", "kubernetes", "autoscal"]`, nội dung nêu scale theo CPU, memory và custom metrics |
| `security-02` ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu kích hoạt bởi `["jwt"]`, nêu API key cố định không tự hết hạn, JWT là token có chữ ký số và thời điểm hết hạn |

Sửa trong `develop/utils/mock_llm.py` (đồng bộ sang `production/utils/mock_llm.py` để stack Docker dùng cùng KB). Kết quả: 2 câu được cải thiện, **0 regression**.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Chất lượng tăng vọt: 4,3 % → 91,3 % → 100 %.
- Chi phí mỗi *request* tăng khoảng 1,9 lần (token trung bình 56,9 → 108,8) vì prompt dài hơn do chèn tài liệu retrieve được.
- Nhưng **chi phí trên mỗi câu trả lời đúng** giảm khoảng 11 lần (0,00040155 → 0,00003607 USD): v1 rẻ hơn mỗi lần gọi nhưng gần như toàn câu sai nên tiền bỏ ra không mua được giá trị.
- Latency: p95 trong eval v1 189 ms → v2 219 ms, tăng chút ít (+29,8 ms, trong đó bước retrieval mặc định khoảng 20 ms). Giá trị p95 1558 ms của `eval_v2_fixed` là do có một request chậm trong tổng 23 câu: mẫu quá nhỏ để kết luận về latency, đúng như README cảnh báo. Latency phải đo bằng load test (phần 2).

**Quality gate trong CI:** `run_eval.py` trả exit code 1 khi accuracy dưới ngưỡng hoặc có regression, nên job CI fail và chặn merge. Thử v1 với baseline `eval_v2_fixed.json`: accuracy 4,3 % (so với 100 %), **22 câu regression**, `Quality gate: FAIL`, **exit code 1**. Mẫu job GitHub Actions (đặt ở `.github/workflows/eval.yml`):

```yaml
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Run agent + eval
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose up --build -d` trong `06-lab-complete/benchmark-observability/production`: 2 agent (giới hạn 0,5 CPU / 256 MB mỗi cái) sau Nginx, Prometheus, Grafana, Jaeger, Locust. Tải nền: Locust 30 user (về sau 12 user, xem 4.2). Cổng Grafana đổi thành **3001** vì 3000 bị một dev server khác của máy chiếm.

**Baseline với 30 user (Prometheus, cửa sổ 1 phút):** 15,2 req/s `/ask`; p95 294 ms, avg 236 ms; error rate 0,46%; traffic chia đều giữa hai instance (7,81 và 7,68 req/s); input tokens 1202/s so với output 632/s; không có alert nào.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png) (Golden Signals: traffic 16,2 req/s, error rate 19,08%, p95 695,71 ms, 2 instance up, chi phí 1h $4,74; panel cost burn rate vượt ngưỡng)
- [x] Một trace chậm trong Jaeger: [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger: [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với hai alert đang **firing** cùng lúc (`LLMCostBurnRateHigh` và `AgentHighErrorRate`): [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

Unit test alert rules: `promtool test rules alert_rules_test.yml` cho kết quả `SUCCESS`.

Trả lời Exercise 7.4:
1. **p95 và avg:** ở baseline p95 = 294 ms, avg = 236 ms; khoảng cách nhỏ nghĩa là ít request chậm. Khi có sự cố khoảng cách này tách ra (ở ảnh Grafana lúc chạy sự cố, p95 là 695,71 ms; ở thí nghiệm B p95 vọt lên 1,92 s). Khoảng cách giữa avg và p95/p99 chính là tail latency.
2. **Nginx có chia đều không?** Có: 7,81 và 7,68 req/s cho hai instance.
3. **Vì sao input tokens/s lớn hơn output tokens/s?** Input gồm system prompt, tài liệu retrieve được (RAG) và câu hỏi (1202 token/s), còn output chỉ là câu trả lời (632 token/s), nên input gấp khoảng 1,9 lần.
4. **`curl http://localhost:8080/metrics`:** trả **404**. `nginx.conf` chặn `/metrics` để người ngoài không đọc được số liệu nội bộ; Prometheus scrape thẳng vào từng agent trong mạng Docker.

### 4.2 Thí nghiệm "phá hệ thống"

Thời gian đo bằng script gọi `GET /api/v1/alerts` của Prometheus mỗi 3 giây, tính từ lúc tôi sửa `.env` (gồm cả khoảng 5 giây tạo lại container agent và vài giây agent khởi động). Mỗi alert đi qua `inactive → pending → firing`; `pending` là lúc điều kiện bắt đầu đúng, `firing` là sau khi đủ thời gian `for`.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (giá trị lúc firing 21,0%) | pending sau 39,5 s, **firing sau 99,7 s** (`for: 1m`) | Stat **Error rate** (đỏ, 19,08%) và **Requests/s theo status code** (đường 503) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (p95 = 1,92 s) | pending sau 36,2 s, **firing sau 156,6 s** (`for: 2m`) | **Latency /ask p50/p95/p99** (p95, p99 vọt, avg tăng ít hơn) |
| C | `LLM_MODEL=mock-llm-large` (tải 12 user) | `LLMCostBurnRateHigh` | pending sau 57,2 s, **firing sau 177,5 s** (`for: 2m`) | **Cost burn rate (USD/giờ)**: từ $0,52 lên $13,27/giờ (khoảng 16 lần); **LLM latency p95 theo model** (mock-llm-large ~0,49 s) |
| D | `docker pause production-agent-1` | `AgentInstanceDown` (`up == 0`) | pending sau 15,4 s, **firing sau 45,5 s** (`for: 30s`) | Stat **Instances up** giảm từ 2 xuống 1 |
| E | `AGENT_VERSION=v1` | **Không có alert nào** (theo dõi 150 s) | không firing | **Retrieval hit ratio** biến mất, **Tokens/s** giảm (input 495 → 270 /s), bảng version đổi sang `v1` |

Ghi chú để số liệu không bị hiểu sai:
- **A** chạy khi tải nền là 30 user.
- **C đã được làm hai lần.** Lần đầu (chồng lên A, tải 30 user) alert firing sau 155,1 s, nhưng đó **không phải kết quả sạch**: tôi phát hiện ngay cả cấu hình bình thường (`mock-llm-small`) với 30 user (khoảng 19 req/s) cũng đã đạt $2,40/giờ, vượt ngưỡng $2/giờ, nên `LLMCostBurnRateHigh` vẫn firing sau khi khôi phục. Lần hai giảm tải xuống 12 user (baseline $0,52–0,82/giờ, dưới ngưỡng) rồi mới đổi model; bảng ghi kết quả lần hai. Bài học: ngưỡng cost alert phải hiệu chỉnh theo tải thật, nếu không sẽ gây alert fatigue.
- **B, C, D, E** chạy với tải nền 12 user.
- Ở mọi thí nghiệm, `AgentInstanceDown` còn nhấp nháy `pending` khoảng 10–20 giây ngay lúc container agent được tạo lại, nhưng không lên `firing` vì chưa đủ `for: 30s`.
- **D:** trong lúc pause, Locust ghi **19/246 request lỗi** (11 lỗi `504 Gateway Time-out` do Nginx chờ instance bị pause, 8 lỗi `503`), nhưng error rate phía agent chỉ 3,5%. Request 504 xảy ra ở Nginx, chưa từng được agent xử lý xong nên không có trong metric của agent: metric chỉ phản ánh những gì chính service đó thấy. Dùng `docker pause` thay vì `docker stop` vì container bị stop biến mất khỏi DNS, Prometheus coi target không còn tồn tại (không phải "down") nên không có alert.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Metric hạ tầng (latency, error, saturation) chỉ cho biết agent *chạy*, không cho biết agent trả lời *đúng*. Ở thí nghiệm E, p95 còn giảm nhẹ (0,29 → 0,27 s), chi phí giảm từ $0,82 xuống $0,46/giờ, nên mọi chỉ số "xanh" trong khi accuracy rơi từ 100% xuống khoảng 4% (kết quả eval ở mục 3). Cách phát hiện:
1. **Eval định kỳ trên golden dataset** với production (hoặc canary): chạy `run_eval.py` theo lịch và sau mỗi lần deploy, so với baseline; accuracy giảm hoặc có regression thì báo động.
2. **Metric nghiệp vụ riêng cho chất lượng**, như `agent_retrieval_total{result="hit|miss"}`: ở E, retrieval hit ratio từ 1,0 mất hẳn, đó là dấu hiệu sớm và có thể đặt alert.
3. **Synthetic check** (hỏi vài câu có đáp án đã biết mỗi vài phút), cộng với phản hồi người dùng (thumbs up/down, tỉ lệ hỏi lại) và LLM-as-judge lấy mẫu.
4. Gắn `agent_info{version=...}` vào dashboard để thấy ngay phiên bản nào đang chạy khi chất lượng thay đổi.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được (Jaeger, service `observable-agent`, sắp xếp theo thời gian giảm dần; lúc đó đang chạy cấu hình `mock-llm-large`):

- `trace_id`: `dda76d4124b8e9e13f65acb5d06a20bf`
- Tổng thời gian: **1982,4 ms**
- Span chiếm nhiều thời gian nhất: `chat mock-llm-large`, **1955,4 ms (98,6%)**. Các span còn lại: `agent.run` 1980,0 ms (bao trùm), `agent.retrieve_context` 24,4 ms. Nút thắt là LLM (upstream), không phải code của agent.
- Dòng log tương ứng (`docker compose logs agent | grep <trace_id>`):

```json
{"ts": "2026-11-26T15:55:55.356569+00:00", "level": "INFO", "service": "observable-agent", "instance": "617da501ac56", "event": "llm_call", "trace_id": "dda76d4124b8e9e13f65acb5d06a20bf", "span_id": "b8c18eb41b0d1d7b", "request_id": "830aabce6540", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 73, "output_tokens": 35, "cost_usd": 0.000532, "llm_ms": 1955.1}
{"ts": "2026-11-26T15:55:55.357183+00:00", "level": "INFO", "service": "observable-agent", "instance": "617da501ac56", "event": "http_request", "trace_id": "dda76d4124b8e9e13f65acb5d06a20bf", "span_id": "b8c18eb41b0d1d7b", "request_id": "830aabce6540", "method": "POST", "route": "/ask", "status": 200, "ms": 1981.6}
```
`llm_ms` = 1955,1 trong log khớp với span `chat mock-llm-large` = 1955,4 ms trong Jaeger.

Trace lỗi: `trace_id` `8d22d218b81c29c0625c14a8361b82b5`, 978,4 ms, status 503. Span `chat mock-llm-large` (949,6 ms) và span cha `agent.run` đều đánh dấu lỗi và có event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`. Log tương ứng:

```json
{"ts": "2026-11-26T15:55:51.585671+00:00", "level": "INFO", "service": "observable-agent", "instance": "e62624d83a98", "event": "llm_error", "trace_id": "8d22d218b81c29c0625c14a8361b82b5", "request_id": "f268efc78ebe", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Lệnh: `docker compose run --no-deps --rm locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_N`, sau `docker compose up -d --scale agent=N`. Số liệu của dòng `/ask` trong [benchmark-results/scale_1_stats.csv](benchmark-results/scale_1_stats.csv) và [benchmark-results/scale_3_stats.csv](benchmark-results/scale_3_stats.csv).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58,94 | 200 | 370 | 1700 | 54 / 7022 (0,77 %) |
| 3 | 60,32 | 190 | 230 | 1700 | 73 / 7181 (1,02 %) |

**Giải thích kết quả:**
- **RPS gần như không đổi** (58,9 → 60,3, tăng 2,3%) dù tăng gấp ba số instance. Locust mô phỏng *người dùng thật* có thời gian nghĩ 0,5–2 s giữa các request, nên thông lượng bị giới hạn bởi số user chứ không phải năng lực server: 100 user chia cho khoảng 1,5 s mỗi vòng (1,25 s nghĩ cộng 0,25 s xử lý) cho khoảng 66 req/s tổng. Một instance (0,5 CPU) đã đủ cho 100 user nên thêm instance không tạo thêm RPS.
- **p95 cải thiện rõ**: 370 → 230 ms (giảm 38%), vì mỗi instance bớt xếp hàng khi hai request đến cùng lúc.
- **p99 không đổi (1700 ms)** và failures vẫn khoảng 1%: đó là tail latency do LLM mô phỏng (`MOCK_SLOW_RATE=0.03` cộng 1,5 s, `MOCK_ERROR_RATE=0.01`), nằm ngoài khả năng của instance agent. Thêm instance không làm nhanh hơn một cuộc gọi LLM đã chậm. Nút thắt nằm ở **LLM upstream** (xem panel "LLM latency p95" và trace chậm ở 4.3), nên muốn giảm p99 phải xử lý ở LLM (timeout, retry/hedging, model nhanh hơn, cache), không phải scale.
- Failures 1,02% so với 0,77% là dao động ngẫu nhiên của lỗi mock (khoảng 1%), không phải tác dụng của scale.
- Nginx phân phối chưa đều tuyệt đối (12 request thử: 2/6/4), có thể do keepalive và cách Nginx phân giải DNS `agent`.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Dùng percentile, không dùng trung bình.** Khi `MOCK_SLOW_RATE` tăng từ 0 lên 0,1, avg chỉ tăng khoảng 1,8 lần nhưng p95 tăng khoảng 6,5 lần; SLO phải đặt theo p95/p99.
  2. **Observability hạ tầng không thay thế eval chất lượng.** Đổi sang v1 làm accuracy rơi từ 100% xuống khoảng 4% mà không có alert nào; cần eval định kỳ, metric nghiệp vụ (retrieval hit ratio) và quality gate trong CI. Ngược lại, scale ngang không giải quyết tail latency do LLM: p99 vẫn 1700 ms dù có 3 instance.
  3. **Alert phải hiệu chỉnh theo tải thật và theo cách đo.** Ngưỡng $2/giờ bị chạm ngay ở baseline 30 user; lỗi 504 ở Nginx không hiện trong metric của agent; thời gian `for` quyết định độ trễ phát hiện (từ 45 s đến 178 s ở năm thí nghiệm).
- Nếu đưa agent này lên production thật, sẽ thêm:
  - Alert cho **accuracy/regression** (eval định kỳ) và cho **retrieval hit ratio** giảm.
  - Giám sát ở **tầng load balancer** (tỉ lệ 5xx của Nginx) và synthetic check từ bên ngoài, để bắt các lỗi mà agent không tự thấy (như 504).
  - Alert cho **tỉ lệ lỗi theo từng upstream/model**, **timeout/retry** khi gọi LLM, và **budget theo user** (cost guard) thay vì chỉ tổng chi phí.
  - **Sampling** trace (ví dụ giữ 10% và giữ toàn bộ trace lỗi/chậm) để giảm chi phí khi lưu lượng lớn.

### Thay đổi so với bài mẫu (để chạy được trên máy này)
- `production/Dockerfile`: thêm `ENV PYTHONUSERBASE=/home/agent/.local`. Nếu thiếu, container `agent` lỗi `ModuleNotFoundError: No module named 'uvicorn'` và khởi động lại liên tục, vì user `agent` có `HOME=/app` nên Python tìm thư viện ở `/app/.local` thay vì `/home/agent/.local` nơi chúng được copy tới.
- `production/docker-compose.yml` và `.env.example`: cổng Grafana đọc từ `GRAFANA_PORT` (mặc định vẫn 3000); trên máy này đặt 3001 trong `.env` (không commit) vì cổng 3000 bị chiếm.
- Sau khi tạo lại container agent, Nginx đôi khi giữ trạng thái "no live upstreams" (502) nên phải `docker compose restart nginx`.

## Phụ lục: Exercise 7.1 — đọc metrics

Chạy agent v2 và gọi `POST /ask`, rồi `GET /metrics`:
- **Counter** (chỉ tăng): `http_requests_total{method="POST",route="/ask",status="200"}`, `llm_tokens_total{type="input"}`.
- **Gauge** (lên xuống): `agent_in_flight_requests`, `agent_info{version="v2"}`.
- **Histogram** (chia bucket để tính percentile): `http_request_duration_seconds_bucket{le=...}`, `llm_request_duration_seconds`.
- **Dùng `route.path` thay vì URL thật làm label**: nếu dùng `request.url.path`, mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`...) tạo ra một giá trị label mới, tức một time series mới. Hàng nghìn URL lạ làm số series bùng nổ (cardinality explosion), Prometheus tốn RAM và chậm. Gán `unmatched` cho mọi URL không khớp route giữ số series hữu hạn.
- **Metric thêm vào:** `agent_question_length_chars` là Histogram (bucket 20/50/100/200/500/1000/2000) gọi `QUESTION_LENGTH.observe(len(body.question))` đầu `ask()`. Dùng Histogram thay vì label `length=...` vì độ dài có vô số giá trị. Kết quả khi gọi câu hỏi 40 ký tự: `agent_question_length_chars_count 1.0`, `agent_question_length_chars_sum 40.0`.
- **So sánh v1 và v2 cho cùng câu hỏi:** v2 trả đúng tài liệu (`input_tokens` 91, `cost_usd` 4,665e-05), v1 trả câu chung chung (36 token, 1,98e-05).
- Lưu ý khi chạy trên Windows: nếu gửi tiếng Việt bằng `curl -d "..."` từ shell, body bị hỏng và server trả `400` (metric `http_requests_total{status="400"}` ghi nhận); nên gửi body từ file UTF-8 (`--data-binary @file.json`).
