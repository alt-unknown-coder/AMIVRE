# AMIVRE Scraper and API Validation Guide

This guide is intended for local validation after the production scraper fix.

## 1. Backend health

Confirm the backend is live:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{ "status": "ok", "version": "1.0.0" }
```

## 2. Scraper smoke test

Run this from the backend directory:

```bash
cd backend
../.venv/Scripts/python.exe -c "import asyncio; from app.scrapers.free_search import smart_search; print(asyncio.run(smart_search('AI customer service', max_urls=3)))"
```

Expected behavior:

- A list of real URLs is returned.
- No import errors like `urlparse is not defined` or `BeautifulSoup is not defined`.

## 3. Run the focused regression tests

```bash
cd backend
../.venv/Scripts/python.exe -m pytest tests/test_scraper_health.py tests/test_agents.py -q
```

Expected result:

- `4 passed`

## 4. Trigger the analysis API

You need a valid user first, then submit an analysis job.

### Register a user

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"secret123"}'
```

### Log in to get tokens

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=secret123"
```

### Submit a job

```bash
curl -X POST http://localhost:8000/api/v1/analysis/submit \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "business_idea": "A smart inventory and waste tracking platform for specialty coffee shops. It helps owners predict bean usage, compare supplier pricing, reduce waste, and improve daily operations through a simple dashboard. The platform integrates with ordering and point-of-sale data so actions can be recommended automatically. It is designed for independent cafe operators who want better margins, repeat purchase discipline, and less food waste across multiple locations.",
    "target_market": "Specialty coffee shops in the United States",
    "geography": "United States",
    "depth": "STANDARD"
  }'
```

### Poll the job status

```bash
curl "http://localhost:8000/api/v1/analysis/<JOB_ID>" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

## 5. Check live logs

```bash
docker logs --tail=80 docker-worker-1
```

Look for:

- `No URLs found for queries` warnings (these are normal if a specific source is blocked)
- `Executing MarketScoutAgent ...`
- `HTTP Request: POST https://generativelanguage.googleapis.com/...` for LLM calls
- final task result: `succeeded ...`

## 6. What success looks like

A good run has:

- backend health returns `200 OK`
- scraper smoke test returns a non-empty list of URLs
- tests pass
- Celery worker logs show the analysis task succeeded
- the database job ends in `COMPLETED` or `FAILED` with a readable reason

## 7. Known caveat

Some sites such as Trustpilot block automated requests with `403 Forbidden`; this is expected and the scraper includes fallback paths via DuckDuckGo, Hacker News, and Google Play so the pipeline continues.
