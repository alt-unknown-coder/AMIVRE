# AMIVRE Backend System - Comprehensive Analysis

## 📋 Table of Contents
1. [File-by-File Breakdown](#file-by-file-breakdown)
2. [Data Flow & Dependencies](#data-flow--dependencies)
3. [Workflow Architecture](#workflow-architecture)
4. [Input/Output Matrix](#inputoutput-matrix)
5. [File Usage Graph](#file-usage-graph)
6. [Backend Improvements](#backend-improvements)

---

## File-by-File Breakdown

### 🔧 Core Application Setup

#### **main.py**
- **Purpose**: FastAPI application entry point and middleware configuration
- **Inputs**: Environment configuration, route definitions
- **Outputs**: Configured FastAPI app with CORS, error handlers, and routes
- **Key Responsibilities**:
  - Initialize FastAPI instance
  - Add CORS middleware (allows localhost:3000)
  - Register exception handlers (HTTP, validation, generic)
  - Include routers (auth, analysis, health, websocket)
  - Manage database lifecycle (startup/shutdown)
- **Uses**: `config.py`, `api/routes/*`, `db/session.py`

#### **config.py**
- **Purpose**: Centralized configuration management
- **Inputs**: Environment variables from `.env` file
- **Outputs**: Settings object with API keys, database URLs, model configurations
- **Key Settings**:
  - `DATABASE_URL`: PostgreSQL connection string
  - `REDIS_URL`: Redis connection for pub/sub and caching
  - `QDRANT_URL`: Vector database (currently unused in code)
  - `GEMINI_API_KEY`: Google Gemini API key
  - `TAVILY_API_KEY`: Tavily search API key
  - `CELERY_BROKER_URL/RESULT_BACKEND`: Redis for task queue
  - `ACCESS_TOKEN_EXPIRE_MINUTES`: JWT token TTL (60 min default)
  - `ANALYSIS_TIMEOUT_SECONDS`: Job timeout (900 sec = 15 min)
- **Used By**: All modules requiring configuration

#### **dependencies.py**
- **Purpose**: Dependency injection for authentication and rate limiting
- **Inputs**: JWT tokens, user requests
- **Outputs**: Authenticated user objects, rate limit validation
- **Key Functions**:
  - `get_current_user()`: Decodes JWT, validates user in database
  - `rate_limit()`: Enforces 10 analyses per day per user
- **Uses**: `config.py`, `db/session.py`, `models/user.py`
- **Used By**: `api/routes/analysis.py`, `api/routes/auth.py`

---

### 💾 Database Layer

#### **db/session.py**
- **Purpose**: Database connection management
- **Inputs**: `DATABASE_URL` from config
- **Outputs**: AsyncSessionLocal factory for database sessions
- **Key Components**:
  - `engine`: Async SQLAlchemy engine
  - `AsyncSessionLocal`: Session factory
  - `get_db()`: Async context manager for FastAPI dependencies
- **Used By**: All models and API routes

#### **db/base.py**
- **Purpose**: SQLAlchemy declarative base class
- **Inputs**: None
- **Outputs**: Base class for all ORM models
- **Used By**: `models/user.py`, `models/analysis_job.py`

#### **models/user.py**
- **Purpose**: User entity for authentication
- **Fields**:
  - `id` (UUID): Primary key
  - `email` (String): Unique, indexed
  - `hashed_password` (String): Bcrypt hashed
  - `is_active` (Boolean): Account status
  - `created_at` (DateTime): Auto-generated timestamp
- **Used By**: `api/routes/auth.py`, `dependencies.py`

#### **models/analysis_job.py**
- **Purpose**: Track analysis jobs and their results
- **Enums**:
  - `JobStatus`: PENDING → RUNNING → COMPLETED (or FAILED/PARTIAL)
  - `JobDepth`: QUICK, STANDARD, DEEP (currently not used in logic)
- **Fields**:
  - `id` (UUID): Primary key, job identifier
  - `user_id` (UUID): Foreign key to User
  - `business_idea` (Text): User's business description
  - `target_market` (String): Target market description
  - `geography` (String): Geographic focus
  - `depth` (Enum): Analysis depth level
  - `status` (Enum): Current job status
  - `result_json` (JSONB): Final analysis results (Pydantic serialized)
  - `error_message` (Text): Error details if job fails
  - `created_at` (DateTime): Job submission time
  - `completed_at` (DateTime): Job completion time
- **Used By**: `api/routes/analysis.py`, `worker/celery_app.py`

#### **models/schemas.py**
- **Purpose**: Pydantic validation schemas for API
- **Schemas**:
  - `UserCreate`: Email, password (6+ chars)
  - `UserResponse`: User data without password
  - `Token`: Access & refresh tokens
  - `AnalysisSubmitRequest`: Business idea (200+ chars), target market, geography, depth
  - `AnalysisJobResponse`: Full job details with results
  - `PaginatedAnalysisJobs`: Paginated job list
- **Used By**: `api/routes/auth.py`, `api/routes/analysis.py`

---

### 🔐 Authentication & Authorization

#### **api/routes/auth.py**
- **Purpose**: User authentication endpoints
- **Endpoints**:
  - `POST /api/v1/auth/register`: Create new user
    - Input: `UserCreate` (email, password)
    - Output: User ID, email, success message
  - `POST /api/v1/auth/login`: Authenticate user
    - Input: OAuth2 form data (username/email, password)
    - Output: `Token` (access_token, refresh_token, bearer type)
  - `POST /api/v1/auth/refresh`: Refresh expired access token
    - Input: Refresh token
    - Output: New access and refresh tokens
  - `GET /api/v1/auth/me`: Get current user info
    - Input: JWT token (dependency)
    - Output: `UserResponse` (user details)
- **Security**: Bcrypt password hashing, HS256 JWT signing
- **Uses**: `config.py`, `db/session.py`, `models/user.py`, `dependencies.py`

---

### 📊 Analysis API

#### **api/routes/analysis.py**
- **Purpose**: Manage analysis jobs
- **Endpoints**:
  - `POST /api/v1/analysis/submit`: Submit new analysis
    - Input: `AnalysisSubmitRequest` (business_idea min 50 words, market, geography, depth)
    - Output: Job ID, status (PENDING), message
    - Side Effect: Creates AnalysisJob in DB, queues Celery task
    - Rate Limit: 10 per day per user
  - `GET /api/v1/analysis/{job_id}`: Retrieve job status & results
    - Input: Job UUID, JWT token
    - Output: `AnalysisJobResponse` (full job details)
    - Validation: User ownership check
  - `GET /api/v1/analysis/`: List user's jobs (paginated)
    - Input: JWT token, page, limit, optional status filter
    - Output: `PaginatedAnalysisJobs` with items, total, page, limit
  - `DELETE /api/v1/analysis/{job_id}`: Cancel job
    - Input: Job UUID, JWT token
    - Output: 204 No Content on success
    - Validation: User ownership, cannot delete RUNNING/COMPLETED jobs
- **Uses**: `config.py`, `db/session.py`, `dependencies.py`, `worker/celery_app.py`

#### **api/websocket.py**
- **Purpose**: Real-time progress updates via WebSocket
- **Endpoint**: `GET /api/v1/ws/{job_id}?token={jwt_token}`
- **Flow**:
  1. Client connects with job ID and JWT token
  2. Server validates token
  3. Subscribes to Redis channel: `progress:{job_id}`
  4. Listens for messages published by agents
  5. Forwards messages to WebSocket client
  6. Closes connection when status is COMPLETED/FAILED/PARTIAL
- **Message Format**: 
  ```json
  {"status": "AGENT_RUNNING", "agent_name": "Market_Scout", "message": "..."}
  ```
- **Uses**: `config.py`, `dependencies.py`

#### **api/routes/health.py**
- **Purpose**: Service health check
- **Endpoint**: `GET /api/v1/health`
- **Output**: `{"status": "ok", "version": "1.0.0"}`

---

### 🤖 Agent Orchestration

#### **orchestrator/state.py**
- **Purpose**: Define LangGraph state schema and agent output schemas
- **State Variables**:
  - `business_idea` (str): User's business description
  - `target_market` (str): Target market focus
  - `geography` (str): Geographic region
  - `depth` (str): Analysis depth (QUICK/STANDARD/DEEP)
  - `_job_id` (str): Internal job ID for progress publishing
  - `market_queries`, `sentiment_queries`, `competitor_queries`, `trend_queries` (list[str]): Generated queries
  - `market_data` (MarketScoutOutput): Market analysis results
  - `sentiment_data` (SentimentOutput): User sentiment results
  - `competitor_data` (CompetitorOutput): Competitor analysis results
  - `trend_data` (TrendOutput): Market trend results
  - `risk_assessment` (RiskModelOutput): Risk assessment results
  - `scraped_data` (dict): Raw scraped data for each agent

- **Output Schemas**:
  - `SourceInfo`: title, url, platform (e.g., "Web Research")
  - `MarketScoutOutput`: TAM/SAM/SOM, top verticals, growth rate, regulatory notes, saturation status + sources
  - `SentimentOutput`: Pain points with sentiment scores, top 5 desires + sources
  - `CompetitorOutput`: 5 direct & 3 indirect competitors, feature matrix, weaknesses + sources
  - `TrendOutput`: Market phase (Emerging/Growing/Mature/Declining), sub-topics, seasonal patterns + sources
  - `RiskModelOutput`: Risk scores (overall, market, competition, financial, regulatory), failure points, mitigation strategies, recommendation (Go/Caution/No-Go) + justification

#### **orchestrator/graph.py**
- **Purpose**: Define LangGraph workflow
- **Graph Structure** (Sequential execution):
  1. START → Master_Query_Node
  2. Master_Query_Node → Market_Scout
  3. Market_Scout → Sentiment_Analyst
  4. Sentiment_Analyst → Competitor_Tracker
  5. Competitor_Tracker → Trend_Forecaster
  6. Trend_Forecaster → Risk_Modeller
  7. Risk_Modeller → END

- **Graph Functions**:
  - `build_graph()`: Constructs LangGraph workflow with all nodes and edges
  - `_make_node()`: Wraps agent.run() to publish AGENT_COMPLETE events to Redis
  - `_publish_agent_complete()`: Publishes completion status via Redis pub/sub
  - `graph`: Compiled workflow instance

- **Sequential Design Rationale**:
  - Avoids LLM rate limits (parallel requests to Gemini API)
  - Prevents browser tab explosion from Crawl4AI
  - Allows downstream agents to use upstream results

- **Uses**: All agent files, state.py

---

### 🧠 AI Agents

#### **agents/base_agent.py**
- **Purpose**: Base class with common LLM functionality
- **Key Components**:
  - `llm`: ChatGoogleGenerativeAI instance (Gemini)
  - `_publish_progress()`: Publishes agent progress to Redis for WebSocket
  - `execute_with_structured_output()`:
    - Takes prompt template, input variables, Pydantic output schema
    - Prepends scraped context to ground analysis
    - Creates ChatPromptTemplate with system + human prompts
    - Runs LLM with structured output enforcement
    - Returns parsed Pydantic model instance
- **Uses**: `config.py`

#### **agents/master_query_node.py**
- **Purpose**: Generate optimized search queries
- **Input**: `business_idea`, `target_market` from state
- **Output**: Four lists of 3-5 queries each:
  - `market_queries`: Market sizing, TAM/SAM/SOM, industry reports
  - `sentiment_queries`: Reddit, forums, app store reviews
  - `competitor_queries`: Direct/indirect competitors, features, pricing
  - `trend_queries`: Hacker News, TechCrunch, emerging trends
- **Process**:
  1. Uses Gemini 3.5 Flash with temperature=0 (deterministic)
  2. Enforces structured output via `MasterQueries` schema
  3. Includes advanced search operators (e.g., site:reddit.com)
- **Fallback**: Returns generic queries if generation fails
- **Uses**: `config.py`

#### **agents/market_scout.py**
- **Purpose**: Analyze market sizing and saturation
- **Inputs**: 
  - From state: business_idea, target_market, geography, market_queries
  - From scraper: web intelligence context
- **Process**:
  1. Calls `build_market_scout_context()` to scrape and compile research
  2. Publishes progress updates via Redis
  3. Prompts Gemini with scraped context and business details
  4. Structured output enforces MarketScoutOutput schema
- **Outputs**: 
  - `market_data`: MarketScoutOutput (TAM, SAM, SOM, verticals, growth, regulation, saturation, sources)
  - `scraped_data`: Raw URLs and content
- **Uses**: `base_agent.py`, `scrapers/scraper_runner.py`

#### **agents/sentiment_analyst.py**
- **Purpose**: Extract user pain points and desires
- **Inputs**: 
  - From state: business_idea, target_market, sentiment_queries
  - From scraper: web intelligence (reviews, forums, social media)
- **Process**:
  1. Calls `build_sentiment_context()` to scrape user discussions
  2. Analyzes with Gemini
  3. Extracts pain points with sentiment scores (-1.0 to 1.0)
- **Outputs**:
  - `sentiment_data`: SentimentOutput (pain points, desires, sources)
  - `scraped_data`: Raw scraped content
- **Uses**: `base_agent.py`, `scrapers/scraper_runner.py`

#### **agents/competitor_tracker.py**
- **Purpose**: Competitive landscape analysis
- **Inputs**:
  - From state: business_idea, target_market, competitor_queries
  - From scraper: competitor information
- **Process**:
  1. Calls `build_competitor_context()` to scrape competitor data
  2. Maps 5 direct and 3 indirect competitors
  3. Creates feature matrix
  4. Identifies weaknesses
- **Outputs**:
  - `competitor_data`: CompetitorOutput (competitors, features, weaknesses, sources)
  - `scraped_data`: Raw competitor research
- **Uses**: `base_agent.py`, `scrapers/scraper_runner.py`

#### **agents/trend_forecaster.py**
- **Purpose**: Market trend and seasonality analysis
- **Inputs**:
  - From state: business_idea, target_market, trend_queries
  - From scraper: trend intelligence
- **Process**:
  1. Calls `build_trend_context()` to scrape trend data
  2. Identifies market phase
  3. Detects sub-topics and seasonal patterns
- **Outputs**:
  - `trend_data`: TrendOutput (market_phase, sub_topics, seasonal_patterns, sources)
  - `scraped_data`: Raw trend data
- **Uses**: `base_agent.py`, `scrapers/scraper_runner.py`

#### **agents/risk_modeller.py**
- **Purpose**: Final risk assessment and recommendation
- **Inputs**: All previous agent outputs (market, sentiment, competitor, trend data)
- **Process**:
  1. Takes all gathered intelligence as context
  2. Performs Business Model Canvas stress-test
  3. Identifies ≥5 failure points
  4. Calculates component risk scores (market, competition, financial, regulatory)
  5. Generates mitigation strategies
  6. Makes final recommendation
- **Outputs**:
  - `risk_assessment`: RiskModelOutput (risk_score, component scores, failure_points, mitigations, recommendation, justification)
- **Note**: Does NOT scrape; relies entirely on upstream agents' sources
- **Uses**: `base_agent.py`

---

### 🌐 Data Collection

#### **scrapers/research_pipeline.py**
- **Purpose**: Autonomous research pipeline using Tavily + Crawl4AI
- **Flow**:
  1. **Tavily Search** (`_tavily_search()`):
     - Takes list of queries
     - Calls Tavily API for each query (basic depth, max 3 results)
     - Returns list of URLs (1-second delay between queries)
  2. **URL Cleaning** (`_clean_urls()`):
     - Deduplicates URLs
     - Limits to 5 URLs per agent (MAX_URLS_PER_AGENT)
  3. **Content Extraction** (`_extract_content()`):
     - Uses Crawl4AI to fetch and parse HTML → Markdown
     - Processes URLs in batches of 2 (memory efficiency)
     - Truncates content to 3000 chars per URL (MAX_CHARS_PER_URL)
     - Prepends "### Source URL: {url}" for citation tracking
     - Total limit: 15000 chars (TOTAL_MAX_CHARS)
  4. **Pipeline Orchestration** (`run_pipeline()`):
     - Calls Tavily → Clean URLs → Crawl4AI
     - Returns formatted context string + raw data
- **Inputs**: List of search queries, optional progress callback
- **Outputs**: 
  - Formatted markdown string with source citations
  - Raw data list with URLs and extracted content
- **Rate Limiting**: Staggered delays, URL limits, content truncation
- **Uses**: `config.py`

#### **scrapers/scraper_runner.py**
- **Purpose**: Context builder wrapper for each agent type
- **Functions**:
  - `build_market_scout_context()`: Wraps pipeline with "LIVE WEB INTELLIGENCE (Market Data)" header
  - `build_sentiment_context()`: Wraps with sentiment-focused header
  - `build_competitor_context()`: Wraps with competitor-focused header
  - `build_trend_context()`: Wraps with trend-focused header
- **Inputs**: Queries list, progress callback
- **Outputs**: Formatted context string, raw data
- **Uses**: `research_pipeline.py`

---

### ⚙️ Task Queue & Processing

#### **worker/celery_app.py**
- **Purpose**: Async task processing with Celery
- **Broker**: Redis (CELERY_BROKER_URL)
- **Backend**: Redis (CELERY_RESULT_BACKEND)
- **Configuration**:
  - Serializer: JSON
  - Timezone: UTC
- **Tasks**:
  - `run_analysis_pipeline()` (Celery task):
    - Decorated with `@celery_app.task`
    - Takes job_id as input
    - Runs `_run_analysis_pipeline_stub()` via asyncio thread
- **Process** (`_run_analysis_pipeline_stub()`):
  1. Fetch AnalysisJob from database
  2. Update status to RUNNING
  3. Publish "Initializing intelligence agents..." message
  4. Invoke LangGraph orchestrator
  5. Serialize Pydantic models to JSON
  6. Store result_json in database
  7. Update status to COMPLETED
  8. Publish "Analysis complete" message
  9. On error: Set status to FAILED, store error_message, publish error message
- **Redis Events** (`_publish()`):
  - Publishes to channel: `progress:{job_id}`
  - Format: JSON with status, agent_name, message
- **Uses**: `config.py`, `db/session.py`, `models/analysis_job.py`, `orchestrator/graph.py`

---

### 📦 Database Base Class

#### **db/base.py**
- **Purpose**: SQLAlchemy declarative base with common columns
- **Common Columns** (inherited by all models):
  - `created_at` (DateTime): Auto-populated on insert
  - `updated_at` (DateTime): Auto-updated on modification
- **Used By**: `models/user.py`, `models/analysis_job.py`

---

## Data Flow & Dependencies

### Dependency Graph

```
main.py (entry point)
├── config.py (all modules)
├── api/routes/
│   ├── auth.py
│   │   ├── config.py
│   │   ├── db/session.py
│   │   ├── models/user.py
│   │   └── dependencies.py
│   ├── analysis.py
│   │   ├── db/session.py
│   │   ├── models/analysis_job.py
│   │   ├── models/schemas.py
│   │   ├── dependencies.py
│   │   └── worker/celery_app.py
│   ├── health.py (standalone)
│   └── websocket.py
│       ├── config.py
│       └── dependencies.py
├── orchestrator/
│   ├── state.py (schema definitions)
│   └── graph.py
│       ├── state.py
│       ├── agents/base_agent.py
│       ├── agents/master_query_node.py
│       ├── agents/market_scout.py
│       ├── agents/sentiment_analyst.py
│       ├── agents/competitor_tracker.py
│       ├── agents/trend_forecaster.py
│       └── agents/risk_modeller.py
├── agents/
│   ├── base_agent.py
│   │   └── config.py
│   └── [specialized agents]
│       └── scrapers/scraper_runner.py
└── db/
    ├── session.py (config.py)
    ├── base.py
    └── models/
        ├── user.py
        ├── analysis_job.py
        └── schemas.py
```

---

## Workflow Architecture

### Complete User Journey

```
1. USER REGISTRATION/LOGIN
   ├── POST /api/v1/auth/register
   │   └── Validates, hashes password, stores in User table
   └── POST /api/v1/auth/login
       └── Returns access + refresh tokens

2. ANALYSIS SUBMISSION
   ├── POST /api/v1/analysis/submit
   │   ├── Validates: 50+ word business idea, market, geography
   │   ├── Rate limit check: 10/day
   │   ├── Creates AnalysisJob (status=PENDING)
   │   └── Queues Celery task with job_id
   └── Returns: job_id, status, message

3. REAL-TIME PROGRESS (Optional)
   ├── Frontend connects WebSocket: /api/v1/ws/{job_id}?token={jwt}
   │   ├── Server validates JWT token
   │   ├── Subscribes to Redis channel: progress:{job_id}
   │   └── Forwards agent progress messages to client
   └── Closes when status = COMPLETED/FAILED/PARTIAL

4. ASYNC JOB PROCESSING (Celery Worker)
   ├── Fetch AnalysisJob from DB
   ├── Update status = RUNNING
   ├── Invoke LangGraph orchestrator:
   │   ├── Master_Query_Node
   │   │   └── Generates 4 query sets via Gemini
   │   ├── Market_Scout (Sequential)
   │   │   ├── Scrapes market data via Tavily + Crawl4AI
   │   │   ├── Analyzes with Gemini (grounded on scraped context)
   │   │   └── Publishes progress to Redis
   │   ├── Sentiment_Analyst
   │   │   ├── Scrapes user discussions/reviews
   │   │   ├── Analyzes sentiment + pain points
   │   │   └── Publishes progress
   │   ├── Competitor_Tracker
   │   │   ├── Scrapes competitor data
   │   │   ├── Maps competitors, features, weaknesses
   │   │   └── Publishes progress
   │   ├── Trend_Forecaster
   │   │   ├── Scrapes market trends
   │   │   ├── Analyzes phase, sub-topics, seasonality
   │   │   └── Publishes progress
   │   └── Risk_Modeller
   │       ├── Takes all upstream outputs
   │       ├── Performs stress-test, calculates risk scores
   │       ├── Generates mitigation strategies
   │       └── Makes final recommendation
   ├── Store result_json in AnalysisJob
   ├── Update status = COMPLETED
   ├── Publish "Analysis complete" to Redis
   └── Commit to DB

5. RESULT RETRIEVAL
   ├── GET /api/v1/analysis/{job_id}
   │   ├── Validates user ownership
   │   └── Returns full AnalysisJobResponse (includes result_json)
   └── GET /api/v1/analysis/
       ├── Paginates user's jobs
       └── Optional status filter
```

---

## Input/Output Matrix

| Component | Inputs | Outputs | Side Effects |
|-----------|--------|---------|--------------|
| **Auth Routes** | UserCreate, OAuth2 credentials, refresh token | Token (JWT), UserResponse | User stored in DB, password hashed |
| **Analysis Routes** | AnalysisSubmitRequest, job_id, JWT token | JobResponse, list of jobs, 204 on delete | Job created in DB, Celery task queued, job deleted |
| **Master_Query_Node** | business_idea, target_market | 4 lists of search queries | - |
| **Market_Scout** | business_idea, market, geography, market_queries | MarketScoutOutput (TAM/SAM/SOM, growth, saturation) | Publishes progress to Redis, stores scraped_data |
| **Sentiment_Analyst** | business_idea, market, sentiment_queries | SentimentOutput (pain points, desires) | Publishes progress, stores scraped_data |
| **Competitor_Tracker** | business_idea, market, competitor_queries | CompetitorOutput (competitors, features) | Publishes progress, stores scraped_data |
| **Trend_Forecaster** | business_idea, market, trend_queries | TrendOutput (phase, trends, seasonality) | Publishes progress, stores scraped_data |
| **Risk_Modeller** | market_data, sentiment_data, competitor_data, trend_data | RiskModelOutput (scores, failures, recommendation) | - |
| **Tavily Search** | queries list | URLs list | API call to Tavily |
| **Crawl4AI** | URLs list | Markdown content, extracted text | Browser instances (memory usage) |
| **WebSocket** | JWT token, job_id | Agent progress messages (JSON) | Redis subscription |
| **Celery** | job_id | Task execution, result storage | Publishes to Redis, updates DB |

---

## File Usage Graph

### Who Uses What

```
main.py
├── → config.py
├── → api/routes/auth.py
├── → api/routes/analysis.py
├── → api/routes/health.py
├── → api/websocket.py
└── → db/session.py

api/routes/auth.py
├── → config.py
├── → db/session.py
├── → models/user.py
├── → models/schemas.py
└── → dependencies.py

api/routes/analysis.py
├── → config.py
├── → db/session.py
├── → models/analysis_job.py
├── → models/schemas.py
├── → dependencies.py
└── → worker/celery_app.py

api/websocket.py
├── → config.py
└── → dependencies.py

worker/celery_app.py
├── → config.py
├── → db/session.py
├── → models/analysis_job.py
└── → orchestrator/graph.py

orchestrator/graph.py
├── → config.py
├── → orchestrator/state.py
├── → agents/base_agent.py
├── → agents/master_query_node.py
├── → agents/market_scout.py
├── → agents/sentiment_analyst.py
├── → agents/competitor_tracker.py
├── → agents/trend_forecaster.py
└── → agents/risk_modeller.py

agents/base_agent.py
└── → config.py

agents/market_scout.py
├── → base_agent.py
├── → orchestrator/state.py
└── → scrapers/scraper_runner.py

agents/sentiment_analyst.py
├── → base_agent.py
├── → orchestrator/state.py
└── → scrapers/scraper_runner.py

agents/competitor_tracker.py
├── → base_agent.py
├── → orchestrator/state.py
└── → scrapers/scraper_runner.py

agents/trend_forecaster.py
├── → base_agent.py
├── → orchestrator/state.py
└── → scrapers/scraper_runner.py

agents/risk_modeller.py
├── → base_agent.py
└── → orchestrator/state.py

scrapers/scraper_runner.py
└── → scrapers/research_pipeline.py

scrapers/research_pipeline.py
└── → config.py

dependencies.py
├── → config.py
├── → db/session.py
└── → models/user.py

db/session.py
└── → config.py

models/
├── user.py → db/base.py
├── analysis_job.py → db/base.py
└── schemas.py (standalone Pydantic models)
```

---

## Backend Improvements

### 🚨 Critical Issues & Solutions

#### **1. No Error Handling in Scraper (CRITICAL)**
**Issue**: If Tavily or Crawl4AI fails, agents crash without fallback
```python
# Current: No error recovery
context_string, raw_data = await build_market_scout_context(queries, progress_callback)
# If scraper fails here, entire job fails
```

**Solution**:
```python
# Add try-catch with graceful degradation
try:
    context_string, raw_data = await build_market_scout_context(queries)
except Exception as e:
    logger.warning(f"Scraper failed, using knowledge-only analysis: {e}")
    context_string = ""  # Let LLM use knowledge base
    raw_data = []
    # Continue execution instead of failing
```

#### **2. No Fallback When Gemini API Fails**
**Issue**: If Gemini returns error, no retry logic or fallback model
```python
# Currently uses OPENAI_FALLBACK_MODEL in config but never uses it
```

**Solution**:
```python
# In base_agent.py - add fallback chain
try:
    result = chain.invoke(safe_input_vars)
except Exception as e:
    logger.warning(f"Primary model failed, trying fallback: {e}")
    # Retry with fallback model (GPT-4o-mini)
    self.llm = ChatOpenAI(model=settings.OPENAI_FALLBACK_MODEL)
    structured_llm = self.llm.with_structured_output(output_schema)
    chain = prompt | structured_llm
    result = chain.invoke(safe_input_vars)
```

#### **3. Sequential Agent Execution is Slow**
**Issue**: Agents run one-at-a-time, taking 5-15 minutes per analysis
**Root Cause**: Sequential edges in graph.py to "avoid rate limits"

**Solution Options**:
- **Option A (Best)**: Implement exponential backoff + parallelization
  ```python
  # Run agents 2-3 at a time instead of strictly sequential
  # Master_Query_Node first (required)
  # Then run Market_Scout + Competitor_Tracker in parallel
  # Wait for completion, run Sentiment_Analyst + Trend_Forecaster in parallel
  # Finally Risk_Modeller
  ```
- **Option B**: Implement rate limit aware queuing
  ```python
  # Track API calls, queue agents if approaching limit
  # Gemini has 1,500 req/min free quota
  ```

#### **4. No Timeout Enforcement on Scraper**
**Issue**: If Crawl4AI hangs, entire job stalls
```python
# Currently no timeout on _extract_content()
```

**Solution**:
```python
async def _extract_content(urls, progress_callback=None, timeout=300):
    try:
        async with asyncio.timeout(timeout):  # Python 3.11+
            # existing code
    except asyncio.TimeoutError:
        logger.error(f"Scraper timeout after {timeout}s")
        return "", raw_data[:2]  # Return partial results
```

#### **5. Hardcoded Query Limits Too Aggressive**
**Issue**: MAX_URLS_PER_AGENT=5 may miss important data
```python
MAX_URLS_PER_AGENT = 5  # Only 5 URLs per agent type
TOTAL_MAX_CHARS = 15000  # Only 15KB of content total
```

**Solution**: Make configurable based on analysis depth
```python
# In state.py - use depth parameter
DEPTH_CONFIG = {
    "QUICK": {"urls": 3, "chars": 8000},
    "STANDARD": {"urls": 5, "chars": 15000},
    "DEEP": {"urls": 8, "chars": 30000},  # More content for deep analysis
}
```

---

### ⚡ Performance Optimizations

#### **1. Cache Market Research Results**
**Issue**: Repeated queries for popular businesses waste API quota
```python
# No caching of search results or Crawl4AI content
```

**Solution**:
```python
# In research_pipeline.py - add Redis caching
cache_key = f"research:{hashlib.md5(','.join(queries)).hexdigest()}"
cached = await redis_client.get(cache_key)
if cached:
    return json.loads(cached), []  # Return cached + empty raw_data

# After scraping
await redis_client.setex(cache_key, 86400, json.dumps(context_string))  # 24hr TTL
```

#### **2. Parallelize Batch Crawling**
**Issue**: Crawl4AI processes URLs in batches of 2, causing slowdown
```python
batch_size = 2  # Only 2 concurrent crawls
```

**Solution**:
```python
# Increase batch size based on available memory
batch_size = 4  # Or make configurable
# Monitor memory usage
import psutil
mem_percent = psutil.virtual_memory().percent
batch_size = 6 if mem_percent < 70 else 3
```

#### **3. Add Query Result Deduplication**
**Issue**: Multiple agents may scrape same URL multiple times
```python
# No tracking of scraped URLs across agent execution
```

**Solution**:
```python
# In state.py - add scraped_urls set
class AgentState(TypedDict):
    # ... existing fields
    scraped_urls: set[str] = {}  # Track all URLs scraped so far

# In research_pipeline.py
def _clean_urls(urls, already_scraped):
    """Deduplicate against previously scraped URLs"""
    cleaned = [u for u in urls if u not in already_scraped]
    return cleaned[:MAX_URLS_PER_AGENT]
```

---

### 🔒 Security & Validation

#### **1. JWT Token Rotation Missing**
**Issue**: Tokens don't rotate, stale tokens never expire from client
```python
# Refresh token logic exists but old tokens remain valid
```

**Solution**:
```python
# In auth.py - revoke old tokens on refresh
# Add token_blacklist table
class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"
    id = Column(UUID, primary_key=True)
    jti = Column(String, unique=True)  # JWT ID
    blacklisted_at = Column(DateTime, default=datetime.utcnow)

# On refresh, add old token to blacklist
@router.post("/refresh")
async def refresh(req, db):
    # ... decode old token
    jti = payload.get("jti", str(uuid4()))
    # Add to blacklist
    blacklist = TokenBlacklist(jti=jti)
    db.add(blacklist)
    # ... issue new token
```

#### **2. Rate Limit Bypass via Multiple Accounts**
**Issue**: Rate limit is per-user (10/day), but easy to create new accounts
```python
# No CAPTCHA, email verification, or IP-based rate limiting
```

**Solution**:
```python
# In dependencies.py - add IP-based rate limiting
async def rate_limit(request: Request, current_user: User):
    # Existing per-user limit
    user_limit_key = f"rate_limit:{current_user.id}:{date}"
    
    # NEW: IP-based limit (50/day per IP)
    ip = request.client.host
    ip_limit_key = f"rate_limit_ip:{ip}:{date}"
    ip_requests = await redis_client.incr(ip_limit_key)
    if ip_requests > 50:
        raise HTTPException(status_code=429, detail="Too many requests from this IP")
```

#### **3. No Input Sanitization for Business Idea**
**Issue**: User input passed directly to LLM, potential for prompt injection
```python
business_idea = state.get("business_idea", "")
# Directly used in prompt - no sanitization
```

**Solution**:
```python
def sanitize_input(text: str) -> str:
    """Remove potential prompt injection patterns"""
    dangerous_patterns = [
        r"ignore.*instruction",
        r"forget.*about",
        r"system prompt",
        r"you are",
        r"act as",
    ]
    for pattern in dangerous_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text.strip()

# In routes/analysis.py
req.business_idea = sanitize_input(req.business_idea)
```

---

### 📊 Monitoring & Observability

#### **1. No Job Execution Metrics**
**Issue**: No visibility into job success rates, average duration, failure reasons
```python
# No logging of execution times or failure breakdown
```

**Solution**:
```python
# Add Prometheus metrics
from prometheus_client import Counter, Histogram

job_duration = Histogram('analysis_job_duration_seconds', 'Job execution time')
job_status = Counter('analysis_job_status_total', 'Job status', ['status'])
scraper_errors = Counter('scraper_errors_total', 'Scraper errors', ['agent', 'error_type'])

# In celery_app.py
import time
start_time = time.time()
try:
    # ... job execution
    job_status.labels(status='completed').inc()
    job_duration.observe(time.time() - start_time)
except Exception as e:
    job_status.labels(status='failed').inc()
    error_type = type(e).__name__
    scraper_errors.labels(agent='pipeline', error_type=error_type).inc()
```

#### **2. No Logging for LLM API Calls**
**Issue**: No tracking of token usage, cost, or model performance
```python
# Gemini API calls not logged for cost tracking
```

**Solution**:
```python
# In base_agent.py
result = chain.invoke(safe_input_vars)
# Log usage if available
if hasattr(result, 'usage_metadata'):
    logger.info(f"Tokens used: {result.usage_metadata.input_tokens} input, "
                f"{result.usage_metadata.output_tokens} output")
```

---

### 🏗️ Architecture Improvements

#### **1. Add Analysis Result Caching**
**Issue**: Identical business ideas + markets researched multiple times
```python
# No deduplication of analyses
```

**Solution**:
```python
# In routes/analysis.py
cache_key = f"analysis:{hash(req.business_idea + req.target_market)}"
cached_result = await redis_client.get(cache_key)
if cached_result:
    # Return cached result immediately
    job.result_json = json.loads(cached_result)
    job.status = JobStatus.COMPLETED
    return job

# After completion
await redis_client.setex(cache_key, 604800, job.result_json)  # 7 days
```

#### **2. Split Risk Modeller into Multiple Stages**
**Issue**: Risk Modeller tries to do too much (stress-test, scoring, strategy)
```python
# RiskModellerAgent combines 5 responsibilities
```

**Solution**: Break into specialized agents
```python
# New agent hierarchy:
# - BMC_Stress_Tester: Identifies failure points
# - Risk_Scorer: Calculates component scores
# - Mitigation_Planner: Generates strategies
# - Decision_Maker: Makes final recommendation

# Or at minimum, separate data gathering from recommendations
class RiskModellerAgent:
    def run(self, state):
        # Stage 1: Gather all data into structured risk factors
        risk_factors = self._analyze_risks(state)
        
        # Stage 2: Score each factor
        scores = self._calculate_scores(risk_factors)
        
        # Stage 3: Generate recommendations
        recommendation = self._make_recommendation(scores)
```

#### **3. Implement Analysis Depth Parameter**
**Issue**: All analyses use same depth regardless of user preference
```python
# depth parameter exists in schema but ignored in execution
depth = state.get("depth")  # Never used in agents
```

**Solution**:
```python
# In each agent
def run(self, state: dict) -> dict:
    depth = state.get("depth", "STANDARD")
    
    if depth == "QUICK":
        queries = queries[:2]  # Fewer queries
        self.model_name = "gemini-3.5-flash"  # Faster model
    elif depth == "DEEP":
        queries = queries + self._generate_followup_queries()
        self.model_name = "gemini-4-pro"  # Better model
    
    # Rest of execution adjusted for depth
```

#### **4. Add Intermediate Result Storage**
**Issue**: If job fails at Risk Modeller stage, all intermediate work lost
```python
# result_json only stored at end, not intermediate results
```

**Solution**:
```python
# In analysis_job.py - add intermediate storage
class AnalysisJob(Base):
    # ... existing fields
    market_result = Column(JSONB, nullable=True)
    sentiment_result = Column(JSONB, nullable=True)
    competitor_result = Column(JSONB, nullable=True)
    trend_result = Column(JSONB, nullable=True)
    risk_result = Column(JSONB, nullable=True)

# In orchestrator/graph.py - wrap each agent to save intermediate
def save_and_run(agent, node_name, state):
    result = agent.run(state)
    # Save intermediate result to DB
    save_intermediate(state["_job_id"], node_name, result)
    return result
```

---

### 💡 Feature Additions

#### **1. Analysis Export Formats**
**Issue**: Results only available in JSON, no PDF/CSV export
```python
# No export functionality
```

**Solution**:
```python
# Add export routes
@router.get("/{job_id}/export/{format}")
async def export_analysis(job_id: UUID, format: str):
    if format == "pdf":
        return generate_pdf_report(job)
    elif format == "csv":
        return generate_csv_export(job)
    elif format == "markdown":
        return generate_markdown_report(job)
```

#### **2. Comparative Analysis**
**Issue**: Can only analyze one business idea at a time
```python
# No bulk analysis or comparison
```

**Solution**:
```python
# Add batch endpoint
@router.post("/submit-batch")
async def submit_batch_analysis(requests: List[AnalysisSubmitRequest]):
    # Queue multiple jobs
    # Return comparison view
    return {"comparison_id": ..., "job_ids": [...]}
```

#### **3. Custom Prompts**
**Issue**: Agent prompts hardcoded, no user customization
```python
# Prompts in agents are static strings
```

**Solution**:
```python
# Make prompts user-customizable
class CustomPromptConfig(BaseModel):
    market_prompt: str = DEFAULT_MARKET_PROMPT
    sentiment_prompt: str = DEFAULT_SENTIMENT_PROMPT
    # ... others

@router.post("/submit-custom")
async def submit_analysis_custom(
    req: AnalysisSubmitRequest,
    prompts: Optional[CustomPromptConfig] = None
):
    # Use custom prompts if provided
```

---

### 📋 Summary of Improvements by Priority

| Priority | Issue | Impact | Effort |
|----------|-------|--------|--------|
| 🔴 CRITICAL | No scraper error handling | Job failures 10-20% of time | Low |
| 🔴 CRITICAL | Sequential execution (5-15 min) | Poor UX, lost users | High |
| 🟠 HIGH | No Gemini fallback | Complete failures on quota | Low |
| 🟠 HIGH | No timeout on Crawl4AI | Job hangs indefinitely | Low |
| 🟠 HIGH | Hardcoded URL/content limits | Poor analysis quality | Low |
| 🟡 MEDIUM | No research caching | Wasted API quota | Medium |
| 🟡 MEDIUM | No execution metrics | No cost tracking | Medium |
| 🟡 MEDIUM | Rate limit bypass | Account abuse | Medium |
| 🟢 LOW | No depth parameter use | Ignored feature | Low |
| 🟢 LOW | Monolithic Risk Modeller | Hard to extend | High |

---

## Recommendations for Next Steps

1. **Immediate (This Week)**:
   - Add try-catch to scraper with graceful degradation
   - Implement Gemini fallback to GPT-4o-mini
   - Add timeout to Crawl4AI

2. **Short-term (Next 2 Weeks)**:
   - Implement parallel agent execution (2-3 at a time)
   - Add research result caching
   - Implement Prometheus metrics

3. **Medium-term (Next Month)**:
   - Refactor depth parameter usage
   - Add intermediate result storage
   - Implement token rotation + revocation
   - IP-based rate limiting

4. **Long-term (Roadmap)**:
   - Split Risk Modeller into specialized agents
   - Add export formats (PDF, CSV, Markdown)
   - Implement comparative analysis
   - User-customizable prompts
   - Analysis result deduplication
