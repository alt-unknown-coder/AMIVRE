# AMIVRE Backend - Quick Reference Guide

## 📁 File Structure Summary

```
backend/
├── app/
│   ├── main.py                    ← FastAPI app entry point
│   ├── config.py                  ← Configuration & env vars
│   ├── dependencies.py            ← JWT auth, rate limiting
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── auth.py           ← Login/register/refresh
│   │   │   ├── analysis.py       ← Submit/get/list/delete jobs
│   │   │   └── health.py         ← Health check
│   │   └── websocket.py          ← Real-time progress
│   │
│   ├── db/
│   │   ├── base.py               ← SQLAlchemy base model
│   │   └── session.py            ← Database connection
│   │
│   ├── models/
│   │   ├── user.py               ← User entity
│   │   ├── analysis_job.py       ← Job entity & enums
│   │   └── schemas.py            ← Pydantic validation schemas
│   │
│   ├── orchestrator/
│   │   ├── state.py              ← LangGraph state + output schemas
│   │   └── graph.py              ← LangGraph workflow definition
│   │
│   ├── agents/
│   │   ├── base_agent.py         ← Base class with LLM logic
│   │   ├── master_query_node.py  ← Generate queries
│   │   ├── market_scout.py       ← Market analysis
│   │   ├── sentiment_analyst.py  ← User sentiment
│   │   ├── competitor_tracker.py ← Competitor analysis
│   │   ├── trend_forecaster.py   ← Market trends
│   │   └── risk_modeller.py      ← Risk assessment
│   │
│   ├── scrapers/
│   │   ├── research_pipeline.py  ← Tavily + Crawl4AI pipeline
│   │   └── scraper_runner.py     ← Context builders per agent
│   │
│   └── worker/
│       └── celery_app.py         ← Celery task queue
│
└── requirements.txt               ← Python dependencies
```

---

## 🔄 Request Lifecycle Summary

### 1️⃣ Submit Analysis (2 endpoints, sequential)

**Request**: `POST /api/v1/analysis/submit`
```
User Input: {
  business_idea: "...",        (200+ chars = ~50 words)
  target_market: "...",         (e.g., "B2B SaaS")
  geography: "...",             (e.g., "North America")
  depth: "STANDARD"             (QUICK/STANDARD/DEEP - ignored)
}
↓
JWT validated via get_current_user
↓
Rate limit checked: 10/day per user (Redis)
↓
AnalysisJob created in PostgreSQL with status=PENDING
↓
Celery task queued to Redis broker
↓
Response: {"job_id": "...", "status": "PENDING", "message": "Analysis started"}
```

### 2️⃣ Listen for Progress (optional, WebSocket)

**Connection**: `WS /api/v1/ws/{job_id}?token={jwt}`
```
WebSocket established
↓
JWT validated
↓
Subscribe to Redis channel: progress:{job_id}
↓
Receive messages when agents publish:
  - {"status": "RUNNING", "agent_name": "Market_Scout", "message": "..."}
  - {"status": "AGENT_COMPLETE", "agent_name": "Market_Scout", ...}
  - {"status": "COMPLETED", "message": "Analysis complete"}
↓
Connection closes when status ∈ [COMPLETED, FAILED, PARTIAL]
```

### 3️⃣ Background Processing (Celery Worker)

**Execution Flow**:
```
Celery Worker
├─ Fetch AnalysisJob by ID
├─ Update status → RUNNING
├─ Publish "Initializing agents..." to Redis
│
├─ [ORCHESTRATOR: LangGraph]
│  ├─ Master_Query_Node
│  │  └─ Gemini: Generate 4 × 3-5 search queries
│  │
│  ├─ Market_Scout (sequential)
│  │  ├─ Tavily: Search market queries (3 results each)
│  │  ├─ Crawl4AI: Extract 5 URLs → Markdown (max 3000 chars each)
│  │  ├─ Gemini: Analyze with context → MarketScoutOutput (TAM/SAM/SOM, etc)
│  │  └─ Publish AGENT_COMPLETE
│  │
│  ├─ Sentiment_Analyst (sequential)
│  │  ├─ Tavily: Search sentiment queries
│  │  ├─ Crawl4AI: Extract reviews/forums
│  │  ├─ Gemini: Analyze → SentimentOutput (pain points, desires)
│  │  └─ Publish AGENT_COMPLETE
│  │
│  ├─ Competitor_Tracker (sequential)
│  │  ├─ Tavily: Search competitor queries
│  │  ├─ Crawl4AI: Extract competitor data
│  │  ├─ Gemini: Analyze → CompetitorOutput (5 direct, 3 indirect, features)
│  │  └─ Publish AGENT_COMPLETE
│  │
│  ├─ Trend_Forecaster (sequential)
│  │  ├─ Tavily: Search trend queries
│  │  ├─ Crawl4AI: Extract trends
│  │  ├─ Gemini: Analyze → TrendOutput (phase, sub-topics, seasonality)
│  │  └─ Publish AGENT_COMPLETE
│  │
│  └─ Risk_Modeller
│     ├─ Use ALL previous agent outputs (no scraping)
│     ├─ Gemini: Stress-test BMC, calculate scores
│     └─ Output: RiskModelOutput (risk scores, failures, mitigation, recommendation)
│
├─ Serialize all results to JSON
├─ Store in AnalysisJob.result_json (PostgreSQL)
├─ Update status → COMPLETED
├─ Publish "Analysis complete" to Redis
└─ Commit transaction
```

**Duration**: ~15 minutes (Sequential execution)
- Master_Query_Node: ~1 min
- Each agent: ~3 mins (Tavily search + Crawl4AI + Gemini)
- Risk Modeller: ~2 mins

### 4️⃣ Retrieve Results (GET endpoint)

**Request**: `GET /api/v1/analysis/{job_id}`
```
JWT validated
↓
User ownership check
↓
AnalysisJob fetched from PostgreSQL
↓
Response: AnalysisJobResponse {
  id: UUID,
  status: "COMPLETED",
  result_json: {
    market_data: {...},
    sentiment_data: {...},
    competitor_data: {...},
    trend_data: {...},
    risk_assessment: {
      risk_score: 65,
      market_risk: 60,
      competition_risk: 70,
      financial_risk: 55,
      regulatory_risk: 40,
      failure_points: [...],
      mitigation_strategies: [...],
      recommendation: "Proceed with Caution",
      justification: "..."
    },
    scraped_data: {}
  }
}
```

---

## 📊 Data Input/Output Table

| Component | Input | Output | Processing |
|-----------|-------|--------|-----------|
| **auth/register** | email, password | user_id | Hash password, store in DB |
| **auth/login** | email, password | access_token, refresh_token | Hash compare, JWT sign |
| **analysis/submit** | business_idea (50+ words), market, geography | job_id, status | Validate, create job, queue task |
| **Master_Query_Node** | business_idea, target_market | 4 query lists | Gemini generates optimized queries |
| **Market_Scout** | queries, business_idea, market, geography | MarketScoutOutput | Tavily + Crawl4AI + Gemini |
| **Sentiment_Analyst** | queries, business_idea, market | SentimentOutput | Tavily + Crawl4AI + Gemini |
| **Competitor_Tracker** | queries, business_idea, market | CompetitorOutput | Tavily + Crawl4AI + Gemini |
| **Trend_Forecaster** | queries, business_idea, market | TrendOutput | Tavily + Crawl4AI + Gemini |
| **Risk_Modeller** | All upstream outputs | RiskModelOutput | Gemini stress-test + scoring |
| **Scraper Pipeline** | queries list | Markdown context, raw data | Tavily search, Crawl4AI extract |
| **WebSocket** | JWT, job_id | Progress messages (JSON) | Redis pub/sub delivery |

---

## 🔗 File Dependency Graph (Who Uses What)

### 🟢 High-Level Usage

```
main.py (entry point)
 ├→ config.py (ALL modules depend)
 ├→ api/routes/*
 ├→ orchestrator/graph.py
 ├→ db/session.py
 └→ worker/celery_app.py

API Routes depend on:
 ├→ db/session.py (database access)
 ├→ models/* (ORM entities)
 ├→ dependencies.py (JWT auth, rate limit)
 └→ worker/celery_app.py (task queuing)

Orchestrator (graph.py) depends on:
 ├→ All agents/*
 ├→ orchestrator/state.py (schemas)
 └→ config.py (LLM keys)

Agents depend on:
 ├→ base_agent.py (LLM interface)
 ├→ scrapers/* (data collection)
 ├→ orchestrator/state.py (schemas)
 └→ config.py (keys)

Scrapers depend on:
 ├→ config.py (API keys)
 └→ (Tavily, Crawl4AI external APIs)

Worker depends on:
 ├→ db/session.py (database)
 ├→ models/analysis_job.py (job entity)
 ├→ orchestrator/graph.py (LangGraph execution)
 └→ config.py (Redis, timeouts)
```

### 🔴 Critical Dependencies (Single Point of Failure)

| Dependency | Used By | Impact If Down |
|-----------|---------|----------------|
| config.py | Everything | Entire backend breaks |
| db/session.py | API routes, worker | Cannot persist data |
| orchestrator/graph.py | worker | Jobs cannot execute |
| base_agent.py | All agents | Analysis cannot run |
| Tavily API | All scrapers | No web research |
| Crawl4AI | All scrapers | Cannot extract content |
| Gemini API | All agents | Cannot generate analysis |
| Redis | WebSocket, rate limit, Celery | Real-time + task queuing fails |
| PostgreSQL | API routes, worker | Job storage broken |

---

## 🧩 Agent Output Schemas

### MarketScoutOutput
```python
{
  "total_addressable_market": "12B USD",
  "serviceable_addressable_market": "4B USD",
  "serviceable_obtainable_market": "500M USD",
  "top_verticals": ["Healthcare", "E-commerce", "FinTech"],
  "growth_rate": "15% CAGR",
  "regulatory_considerations": ["HIPAA compliance", "Data privacy"],
  "is_saturated": false,
  "saturation_justification": "Market growing faster than competition",
  "sources": [
    {"title": "...", "url": "...", "platform": "Web Research"},
    ...
  ]
}
```

### SentimentOutput
```python
{
  "pain_points": [
    {
      "description": "Current solutions too expensive",
      "sentiment_score": -0.8
    },
    ...
  ],
  "top_desires": ["Lower cost", "Better UX", "API access", "Mobile app", "Real-time data"],
  "sources": [...]
}
```

### CompetitorOutput
```python
{
  "direct_competitors": [
    {"name": "Competitor A", "description": "Market leader..."},
    ...
  ],
  "indirect_competitors": [
    {"name": "Competitor B", "description": "Adjacent market..."},
    ...
  ],
  "feature_matrix": {
    "Feature X": ["Competitor A", "Competitor C"],
    "Feature Y": ["Competitor B"],
    ...
  },
  "competitor_weaknesses": {
    "Competitor A": "Poor mobile experience",
    ...
  },
  "sources": [...]
}
```

### TrendOutput
```python
{
  "market_phase": "Growing",  # Emerging/Growing/Mature/Declining
  "sub_topics": ["AI integration", "Personalization", "Blockchain"],
  "seasonal_patterns": "Higher demand in Q4",
  "sources": [...]
}
```

### RiskModelOutput
```python
{
  "risk_score": 65,                              # 0-100
  "market_risk": 60,
  "competition_risk": 70,
  "financial_risk": 55,
  "regulatory_risk": 40,
  "failure_points": [
    "Insufficient capital for market penetration",
    "Strong competitor response",
    "Longer sales cycle than expected",
    "Talent acquisition challenges",
    "Regulatory approval delays"
  ],
  "mitigation_strategies": [
    "Secure Series A funding round early",
    "Focus on differentiation vs competitors",
    "Build flexible pricing model",
    "Create strong employer brand",
    "Engage regulatory consultants"
  ],
  "recommendation": "Proceed with Caution",     # Go/Proceed with Caution/No-Go
  "justification": "Market opportunity is real but competition is fierce..."
}
```

---

## 🔐 Security & Authentication

### JWT Token Structure
```
Header: {
  "alg": "HS256",
  "typ": "JWT"
}

Payload (Access Token - 60 min TTL):
{
  "sub": "user-uuid",
  "exp": 1234567890,
  "iat": 1234567800
}

Payload (Refresh Token - 7 day TTL):
{
  "sub": "user-uuid",
  "exp": 1234999999,
  "iat": 1234567800
}

Signature: HMAC-SHA256(header.payload, SECRET_KEY)
```

### Rate Limiting
```
Key: rate_limit:{user_id}:{date}
Value: request_count (incremented on each request)
TTL: 86400 seconds (24 hours)
Limit: 10 requests per day per user

Implementation:
1. Get current value from Redis
2. If >= 10, return 429 Too Many Requests
3. Increment counter
4. Set expiry to 86400s
```

### Password Security
```
Algorithm: Bcrypt
Rounds: default (12)
Storage: hashed_password in users table
Login: Compare bcrypt.verify(password, hashed_password)
```

---

## ⚙️ Environment Variables (config.py)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/amivre

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# APIs
GEMINI_API_KEY=your-gemini-key
TAVILY_API_KEY=your-tavily-key

# JWT
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Celery
ANALYSIS_TIMEOUT_SECONDS=900

# CORS
ALLOWED_ORIGINS=["http://localhost:3000"]

# Optional
QDRANT_URL=http://localhost:6333
OPENAI_FALLBACK_MODEL=gpt-4o-mini
```

---

## 📈 Scalability Bottlenecks & Solutions

| Bottleneck | Current | Problem | Solution |
|-----------|---------|---------|----------|
| Agent Execution | Sequential | 15 min per job | Parallel (2-3 at a time) |
| URL Limits | 5 per agent | Limited context | 8+ for DEEP analysis |
| Content Limit | 15KB total | Truncation loses data | 30KB for DEEP analysis |
| Scraper Errors | No fallback | Job fails completely | Graceful degradation |
| LLM Errors | No retry | Single failure = job fail | Retry + fallback model |
| Results Storage | Temporary | No caching/reuse | Redis cache (24h) |
| Rate Limit | Per-user only | Account abuse | Add IP-based limit |
| Job Polling | Client-side | Inefficient | WebSocket (already has) |

---

## 🚨 Critical Issues & Fixes

### Issue #1: No Scraper Error Recovery
**Risk**: Job fails silently if Tavily/Crawl4AI down
**Fix**: 
```python
try:
    context_string, raw_data = await build_market_scout_context(queries)
except Exception as e:
    logger.warning(f"Scraper failed, using knowledge-only: {e}")
    context_string = ""  # Let Gemini use knowledge base
    raw_data = []
```

### Issue #2: Sequential Agents = Slow
**Risk**: Users abandon after 5+ minutes
**Fix**: Parallelize agents 2-3 at a time
```python
# Run in parallel after Master_Query_Node
tasks = [
    agent1.run(state),
    agent2.run(state)
]
results = await asyncio.gather(*tasks)
```

### Issue #3: No Gemini Fallback
**Risk**: Quota exceeded = complete failure
**Fix**: Implement fallback to GPT-4o-mini
```python
try:
    result = gemini_chain.invoke(state)
except Exception:
    logger.info("Gemini failed, using OpenAI")
    result = openai_chain.invoke(state)
```

---

## 📦 Dependencies (requirements.txt Key Packages)

```
# FastAPI & ASGI
fastapi==0.104.0
uvicorn==0.24.0
pydantic==2.4.0

# Database
sqlalchemy==2.0.0
asyncpg==0.29.0
alembic==1.13.0

# Task Queue
celery==5.3.0
redis==5.0.0

# LLM & Agents
langchain==0.1.0
langchain-google-genai==0.0.10
langgraph==0.0.20
crawl4ai==0.3.0
tavily-python==0.2.0

# Auth
python-jose==3.3.0
passlib==1.7.4
python-multipart==0.0.6

# Utilities
python-dotenv==1.0.0
pydantic-settings==2.0.0
```

---

## 🎯 Testing Endpoints (cURL Examples)

```bash
# Health Check
curl http://localhost:8000/api/v1/health

# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=password123"

# Submit Analysis
curl -X POST http://localhost:8000/api/v1/analysis/submit \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "business_idea": "A platform that uses AI to automate customer service for SaaS companies...",
    "target_market": "B2B SaaS",
    "geography": "North America",
    "depth": "STANDARD"
  }'

# Get Analysis Result
curl -X GET http://localhost:8000/api/v1/analysis/{job_id} \
  -H "Authorization: Bearer {access_token}"

# List Jobs
curl -X GET http://localhost:8000/api/v1/analysis?page=1&limit=10 \
  -H "Authorization: Bearer {access_token}"

# WebSocket Progress
wscat -c "ws://localhost:8000/api/v1/ws/{job_id}?token={access_token}"
```

---

## 📊 Key Metrics to Monitor

1. **Job Success Rate**: `completed_jobs / total_jobs`
2. **Average Duration**: `sum(completed_at - created_at) / completed_jobs`
3. **Failure Breakdown**: By stage (scraper, LLM, parsing)
4. **API Quota Usage**: Gemini + Tavily + Crawl4AI calls/day
5. **Database Size**: PostgreSQL growth rate
6. **Redis Memory**: Pub/sub + cache usage
7. **Celery Queue Depth**: Jobs waiting for processing
8. **Rate Limit Hits**: `429` responses per day

---

## 🔄 Deployment Checklist

- [ ] Configure `.env` with all API keys and URLs
- [ ] Set up PostgreSQL database
- [ ] Run migrations: `alembic upgrade head`
- [ ] Set up Redis (for caching, pub/sub, Celery)
- [ ] Start Celery worker: `celery -A app.worker.celery_app worker --loglevel=info`
- [ ] Start FastAPI: `uvicorn app.main:app --reload`
- [ ] Test health endpoint
- [ ] Test auth flow (register → login)
- [ ] Test analysis submission
- [ ] Monitor Celery worker logs
- [ ] Check WebSocket progress streaming
