# Deployment Information

## Public URL

https://ai-agent-o0tr.onrender.com

> Gói Render free ngủ sau ~15 phút không có request. Request đầu sau khi ngủ có thể mất 30–60 giây; hãy gọi `/health` một lần để đánh thức app trước khi test.

## Platform

Render (Blueprint `06-lab-complete/render.yaml`): web service `ai-agent` (Docker, gói free) + Redis `agent-redis` (Key Value, gói free).

## Test Commands

### Health Check
```bash
curl https://ai-agent-o0tr.onrender.com/health
# {"status":"ok"}   (HTTP 200)
```

### Readiness (kiểm tra kết nối Redis)
```bash
curl https://ai-agent-o0tr.onrender.com/ready
# {"status":"ready"}   (HTTP 200)
```

### Không có API key → 401
```bash
curl -X POST https://ai-agent-o0tr.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"detail":"Invalid or missing API key."}   (HTTP 401)
```

### Có API key → 200
```bash
curl -X POST https://ai-agent-o0tr.onrender.com/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Rate limiting → 429
Giới hạn 10 request/phút cho mỗi API key (state trong Redis). Gửi 15 request liên tiếp:
```
200 200 200 200 200 200 200 200 200 429 429 429 429 429 429
```
(Chỉ có 9 lần `200` vì một request test trước đó vẫn nằm trong cửa sổ 60 giây.)

## Environment Variables Set (trên Render)

| Biến | Cách đặt |
|---|---|
| `AGENT_API_KEY` | `generateValue: true` — Render tự sinh, không ghi trong code |
| `REDIS_URL` | `fromService` → connection string của `agent-redis` |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |
| `PORT` | Render tự cấp; `CMD` trong Dockerfile đọc `${PORT:-8000}` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
