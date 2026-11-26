# Benchmark & Observability Report — Day 14

**Họ tên:** Vũ Lương Duy (MSSV 2A202603945)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11, Python 3.11.9, 22 logical CPU. Phần 2–3 chạy local: agent là **một process uvicorn** (`06-lab-complete/benchmark-observability/develop`), load generator `load_test.py` chạy trên cùng máy. Phần 4–5: _TODO (Docker stack)_.

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

> _TODO — làm ở Bước 2 (Docker stack: Grafana, Jaeger, Prometheus, Locust)._

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | _TODO_ | _TODO_ | _TODO_ |
| B | `MOCK_SLOW_RATE=0.3` | _TODO_ | _TODO_ | _TODO_ |
| C | `LLM_MODEL=mock-llm-large` | _TODO_ | _TODO_ | _TODO_ |
| D | `docker pause` 1 instance | _TODO_ | _TODO_ | _TODO_ |
| E | `AGENT_VERSION=v1` | _TODO_ | _TODO_ | _TODO_ |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

_TODO_

### 4.3 Debug bằng trace

_TODO — trace_id, tổng thời gian, span chậm nhất, dòng log JSON tương ứng._

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | _TODO_ | | | | |
| 3 | _TODO_ | | | | |

**Giải thích kết quả:** _TODO_

---

## 6. Kết luận

_TODO — điền sau khi hoàn thành Bước 2._

---

## Phụ lục: Exercise 7.1 — đọc metrics

Chạy agent v2 và gọi `POST /ask`, rồi `GET /metrics`:
- **Counter** (chỉ tăng): `http_requests_total{method="POST",route="/ask",status="200"}`, `llm_tokens_total{type="input"}`.
- **Gauge** (lên xuống): `agent_in_flight_requests`, `agent_info{version="v2"}`.
- **Histogram** (chia bucket để tính percentile): `http_request_duration_seconds_bucket{le=...}`, `llm_request_duration_seconds`.
- **Dùng `route.path` thay vì URL thật làm label**: nếu dùng `request.url.path`, mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`...) tạo ra một giá trị label mới, tức một time series mới. Hàng nghìn URL lạ làm số series bùng nổ (cardinality explosion), Prometheus tốn RAM và chậm. Gán `unmatched` cho mọi URL không khớp route giữ số series hữu hạn.
- **Metric thêm vào:** `agent_question_length_chars` là Histogram (bucket 20/50/100/200/500/1000/2000) gọi `QUESTION_LENGTH.observe(len(body.question))` đầu `ask()`. Dùng Histogram thay vì label `length=...` vì độ dài có vô số giá trị. Kết quả khi gọi câu hỏi 40 ký tự: `agent_question_length_chars_count 1.0`, `agent_question_length_chars_sum 40.0`.
- **So sánh v1 và v2 cho cùng câu hỏi:** v2 trả đúng tài liệu (`input_tokens` 91, `cost_usd` 4,665e-05), v1 trả câu chung chung (36 token, 1,98e-05).
- Lưu ý khi chạy trên Windows: nếu gửi tiếng Việt bằng `curl -d "..."` từ shell, body bị hỏng và server trả `400` (metric `http_requests_total{status="400"}` ghi nhận); nên gửi body từ file UTF-8 (`--data-binary @file.json`).
