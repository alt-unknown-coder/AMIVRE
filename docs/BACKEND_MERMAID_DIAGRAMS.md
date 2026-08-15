# AMIVRE Backend - Mermaid Architecture & Workflow Diagrams

## 1. Complete User Journey & Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant FastAPI as FastAPI Backend
    participant Database as PostgreSQL
    participant Redis
    participant Celery as Celery Worker
    participant LLM as Gemini API
    participant Tavily as Tavily Search
    participant Crawl4AI

    User->>Frontend: 1. Register/Login
    Frontend->>FastAPI: POST /auth/register or /login
    FastAPI->>Database: Check user, hash password
    Database-->>FastAPI: User stored/retrieved
    FastAPI-->>Frontend: JWT tokens

    User->>Frontend: 2. Submit Analysis
    Frontend->>FastAPI: POST /analysis/submit + JWT
    FastAPI->>FastAPI: Validate input (50+ words, rate limit)
    FastAPI->>Database: Create AnalysisJob (PENDING status)
    Database-->>FastAPI: Job ID
    FastAPI->>Redis: Queue Celery task
    FastAPI-->>Frontend: Return job_id, status=PENDING

    Frontend->>FastAPI: 3. Connect WebSocket (optional)
    FastAPI->>Redis: Subscribe to progress:{job_id}
    
    Celery->>Database: 4. Fetch AnalysisJob
    Database-->>Celery: Job details
    Celery->>Database: Update status = RUNNING
    Celery->>Redis: Publish "Initializing agents..."
    Redis-->>FastAPI: (WebSocket forwards to Frontend)

    Celery->>Celery: 5. Execute LangGraph Orchestrator
    
    Celery->>LLM: Master_Query_Node: Generate queries
    LLM-->>Celery: 4 query lists
    
    Celery->>Tavily: Market_Scout: Search queries
    Tavily-->>Celery: URLs
    Celery->>Crawl4AI: Extract content
    Crawl4AI-->>Celery: Markdown content
    Celery->>LLM: Analyze with context
    LLM-->>Celery: MarketScoutOutput
    Celery->>Redis: Publish AGENT_COMPLETE
    
    Celery->>Tavily: Sentiment_Analyst: Search queries
    Tavily-->>Celery: URLs
    Celery->>Crawl4AI: Extract reviews/forums
    Crawl4AI-->>Celery: Content
    Celery->>LLM: Analyze sentiment
    LLM-->>Celery: SentimentOutput
    Celery->>Redis: Publish AGENT_COMPLETE

    Celery->>Tavily: Competitor_Tracker: Search queries
    Tavily-->>Celery: URLs
    Celery->>Crawl4AI: Extract competitor data
    Crawl4AI-->>Celery: Content
    Celery->>LLM: Analyze competitors
    LLM-->>Celery: CompetitorOutput
    Celery->>Redis: Publish AGENT_COMPLETE

    Celery->>Tavily: Trend_Forecaster: Search queries
    Tavily-->>Celery: URLs
    Celery->>Crawl4AI: Extract trends
    Crawl4AI-->>Celery: Content
    Celery->>LLM: Analyze trends
    LLM-->>Celery: TrendOutput
    Celery->>Redis: Publish AGENT_COMPLETE

    Celery->>LLM: Risk_Modeller: Analyze all data
    LLM-->>Celery: RiskModelOutput
    
    Celery->>Database: Store result_json, status=COMPLETED
    Database-->>Celery: Confirmed
    Celery->>Redis: Publish "Analysis complete"
    Redis-->>FastAPI: (WebSocket forwards to Frontend)

    Frontend->>FastAPI: 6. GET /analysis/{job_id}
    FastAPI->>Database: Fetch AnalysisJob with results
    Database-->>FastAPI: Full job + result_json
    FastAPI-->>Frontend: AnalysisJobResponse
    Frontend->>User: Display results

    Frontend->>FastAPI: 7. GET /analysis/ (List jobs)
    FastAPI->>Database: Query jobs paginated
    Database-->>FastAPI: List of jobs
    FastAPI-->>Frontend: PaginatedAnalysisJobs
```

---

## 2. LangGraph Orchestrator Workflow

```mermaid
graph TD
    START([START]) --> MQN["🎯 Master_Query_Node<br/>Generate Search Queries"]
    
    MQN --> |market_queries| MS["🔍 Market_Scout<br/>TAM/SAM/SOM Analysis"]
    MS --> |market_data| SA["😊 Sentiment_Analyst<br/>Pain Points & Desires"]
    SA --> |sentiment_data| CT["🏢 Competitor_Tracker<br/>Competitive Analysis"]
    CT --> |competitor_data| TF["📈 Trend_Forecaster<br/>Market Trends"]
    TF --> |trend_data| RM["⚠️ Risk_Modeller<br/>Final Risk Assessment"]
    RM --> END([END])
    
    MQN -.->|sentiment_queries| SA
    MQN -.->|competitor_queries| CT
    MQN -.->|trend_queries| TF
    
    style START fill:#90EE90
    style END fill:#FFB6C6
    style MQN fill:#87CEEB
    style MS fill:#DDA0DD
    style SA fill:#F0E68C
    style CT fill:#FF6347
    style TF fill:#20B2AA
    style RM fill:#8B0000,color:#fff
```

---

## 3. Data Flow Between Components

```mermaid
graph LR
    subgraph Client["🖥️ CLIENT (Frontend)"]
        WEB["Web Browser<br/>Next.js"]
        WS["WebSocket<br/>Listener"]
    end
    
    subgraph API["🔌 API LAYER"]
        AUTH["Auth Routes<br/>register, login, refresh"]
        ANALYSIS["Analysis Routes<br/>submit, get, list, delete"]
        HEALTH["Health Check"]
        WSR["WebSocket Route<br/>/{job_id}"]
    end
    
    subgraph AUTH_LAYER["🔐 AUTH & VALIDATION"]
        JWT["JWT Token<br/>Validation"]
        RATE["Rate Limiter<br/>10/day per user"]
    end
    
    subgraph DATA["💾 DATA LAYER"]
        PSQL["PostgreSQL<br/>Users, Jobs, Results"]
        REDIS["Redis<br/>Cache, Pub/Sub, Queue"]
    end
    
    subgraph WORK["⚙️ WORKER LAYER"]
        CELERY["Celery Task<br/>Worker"]
        LANGGRAPH["LangGraph<br/>Orchestrator"]
    end
    
    subgraph AGENTS["🤖 AGENT LAYER"]
        BASE["Base Agent<br/>LLM Interface"]
        MQN_A["Master Query Node"]
        MS_A["Market Scout"]
        SA_A["Sentiment Analyst"]
        CT_A["Competitor Tracker"]
        TF_A["Trend Forecaster"]
        RM_A["Risk Modeller"]
    end
    
    subgraph SCRAPER["🌐 SCRAPER LAYER"]
        TAVILY["Tavily API<br/>Search"]
        CRAWL4AI["Crawl4AI<br/>Extract"]
    end
    
    subgraph LLM_LAYER["🧠 LLM LAYER"]
        GEMINI["Gemini API<br/>3.5 Flash"]
        FALLBACK["OpenAI Fallback<br/>GPT-4o-mini<br/>🚨 NOT IMPLEMENTED"]
    end
    
    WEB -->|JWT Token| API
    WEB -->|WebSocket| WSR
    
    API -->|Authenticate| AUTH_LAYER
    API -->|Check Rate Limit| RATE
    ANALYSIS -->|Store Job| PSQL
    ANALYSIS -->|Queue Task| REDIS
    ANALYSIS -->|Validate Token| JWT
    
    REDIS -->|Publish Progress| WSR
    WSR -->|Send Updates| WS
    WS -->|Display| WEB
    
    CELERY -->|Execute| LANGGRAPH
    LANGGRAPH -->|Invoke| BASE
    BASE -->|Cache Results| REDIS
    
    LANGGRAPH -->|Coordinate| MQN_A
    LANGGRAPH -->|Sequential| MS_A
    LANGGRAPH -->|Sequential| SA_A
    LANGGRAPH -->|Sequential| CT_A
    LANGGRAPH -->|Sequential| TF_A
    LANGGRAPH -->|Sequential| RM_A
    
    MS_A -->|Use Context| SCRAPER
    SA_A -->|Use Context| SCRAPER
    CT_A -->|Use Context| SCRAPER
    TF_A -->|Use Context| SCRAPER
    
    SCRAPER -->|Search| TAVILY
    SCRAPER -->|Extract| CRAWL4AI
    
    BASE -->|Query LLM| GEMINI
    GEMINI -->|Structured Output| BASE
    
    CELERY -->|Save Results| PSQL
    LANGGRAPH -->|Publish Status| REDIS
    
    style WEB fill:#87CEEB
    style AUTH fill:#90EE90
    style ANALYSIS fill:#90EE90
    style JWT fill:#FFD700
    style RATE fill:#FFD700
    style PSQL fill:#FF6347
    style REDIS fill:#FF6347
    style CELERY fill:#DDA0DD
    style LANGGRAPH fill:#DDA0DD
    style BASE fill:#F0E68C
    style TAVILY fill:#20B2AA
    style CRAWL4AI fill:#20B2AA
    style GEMINI fill:#8B0000,color:#fff
    style FALLBACK fill:#FF4500,color:#fff
```

---

## 4. Agent Execution Pipeline (Detailed)

```mermaid
sequenceDiagram
    participant State as AgentState
    participant Agent as Agent.run()
    participant Scraper as scraper_runner
    participant Pipeline as research_pipeline
    participant Tavily as Tavily API
    participant Crawl as Crawl4AI
    participant LLM as Gemini LLM
    participant Redis as Redis Pub/Sub

    Agent->>Agent: Publish AGENT_RUNNING
    Agent->>Redis: progress:{job_id}
    
    Agent->>Scraper: build_context(queries)
    Scraper->>Pipeline: run_pipeline(queries)
    
    Pipeline->>Tavily: Search each query
    Tavily-->>Pipeline: URLs list
    Pipeline->>Pipeline: Deduplicate, limit to 5
    
    Pipeline->>Crawl: Batch 1: URLs[0:2]
    Crawl-->>Pipeline: Markdown for each URL
    Pipeline->>Pipeline: Truncate to 3000 chars/URL
    Pipeline->>Pipeline: Prepend "### Source URL: {url}"
    
    Pipeline->>Crawl: Batch 2: URLs[2:4]
    Crawl-->>Pipeline: More Markdown
    
    Pipeline->>Pipeline: Join all with "---"
    Pipeline->>Pipeline: Truncate total to 15000 chars
    Pipeline-->>Scraper: (context_string, raw_data)
    
    Scraper-->>Agent: Grounded context
    Agent->>Agent: Construct prompt with context
    Agent->>LLM: Execute with structured_output
    
    LLM->>LLM: Parse prompt template
    LLM->>LLM: Enforce Pydantic schema
    LLM-->>Agent: Parsed model instance
    
    Agent->>Agent: Serialize to dict
    Agent->>Agent: Publish AGENT_COMPLETE
    Agent->>Redis: progress:{job_id}
    Agent-->>State: {result_key: output, scraped_data: {...}}
    
    State->>State: Merge into state dict
    State-->>State: Pass to next agent
```

---

## 5. Database Schema

```mermaid
erDiagram
    USERS ||--o{ ANALYSIS_JOBS : creates
    USERS {
        uuid id PK
        string email UK "unique, indexed"
        string hashed_password
        boolean is_active
        datetime created_at
        datetime updated_at
    }
    
    ANALYSIS_JOBS {
        uuid id PK
        uuid user_id FK "indexed"
        text business_idea
        string target_market
        string geography
        enum status "PENDING, RUNNING, COMPLETED, FAILED, PARTIAL"
        enum depth "QUICK, STANDARD, DEEP"
        jsonb result_json "Final analysis output"
        text error_message "Error details if failed"
        datetime created_at
        datetime updated_at
        datetime completed_at
    }
```

---

## 6. API Endpoint Map

```mermaid
graph TD
    API["📡 /api/v1"]
    
    AUTH["🔐 /auth"]
    ANALYSIS["📊 /analysis"]
    HEALTH["💚 /health"]
    WS["🔌 /ws"]
    
    API --> AUTH
    API --> ANALYSIS
    API --> HEALTH
    API --> WS
    
    AUTH --> AR["POST /register<br/>Input: UserCreate<br/>Output: user_id"]
    AUTH --> AL["POST /login<br/>Input: OAuth2 Form<br/>Output: Token"]
    AUTH --> AREF["POST /refresh<br/>Input: refresh_token<br/>Output: Token"]
    AUTH --> AME["GET /me<br/>Input: JWT<br/>Output: UserResponse"]
    
    ANALYSIS --> ASUB["POST /submit<br/>Input: AnalysisSubmitRequest<br/>Output: job_id, status<br/>Rate Limit: 10/day"]
    ANALYSIS --> AGET["GET /{job_id}<br/>Input: JWT, job_id<br/>Output: AnalysisJobResponse"]
    ANALYSIS --> ALIST["GET /<br/>Input: JWT, page, limit, status<br/>Output: PaginatedAnalysisJobs"]
    ANALYSIS --> ADEL["DELETE /{job_id}<br/>Input: JWT, job_id<br/>Output: 204 No Content"]
    
    HEALTH --> HC["GET<br/>Output: {status, version}"]
    
    WS --> WSPROG["WS /{job_id}<br/>Input: JWT, job_id<br/>Output: Progress events"]
    
    style API fill:#87CEEB,color:#000
    style AUTH fill:#90EE90
    style ANALYSIS fill:#90EE90
    style HEALTH fill:#90EE90
    style WS fill:#90EE90
    
    style AR fill:#FFD700
    style AL fill:#FFD700
    style AREF fill:#FFD700
    style AME fill:#FFD700
    
    style ASUB fill:#FFA07A
    style AGET fill:#FFA07A
    style ALIST fill:#FFA07A
    style ADEL fill:#FFA07A
    
    style HC fill:#98FB98
    style WSPROG fill:#87CEEB
```

---

## 7. Dependency Injection Flow

```mermaid
graph TD
    Request["📨 Incoming Request"]
    
    Request --> OAuth["OAuth2PasswordBearer<br/>Extract token from header"]
    OAuth --> JWT["get_current_user<br/>Decode JWT"]
    JWT --> DB["DB Session<br/>Query User"]
    DB --> User["✅ Authenticated User"]
    
    Request --> Rate["rate_limit<br/>Check Redis counter"]
    Rate --> RateCheck{Rate<br/>Limit?}
    RateCheck -->|Exceeded| Error429["❌ 429 Too Many Requests"]
    RateCheck -->|OK| Continue["✅ Allow Request"]
    
    User --> Route["🔀 Route Handler"]
    Continue --> Route
    Route --> Response["📤 Response"]
    
    style Request fill:#87CEEB
    style OAuth fill:#FFD700
    style JWT fill:#FFD700
    style DB fill:#FF6347
    style User fill:#90EE90
    style Rate fill:#FFD700
    style Error429 fill:#FF4500,color:#fff
    style Continue fill:#90EE90
    style Route fill:#DDA0DD
    style Response fill:#87CEEB
```

---

## 8. Error Handling & Recovery Paths

```mermaid
graph TD
    Job["🎯 Analysis Job Starts"]
    
    Job -->|Celery Task| CelTask["Execute run_analysis_pipeline"]
    CelTask -->|Fetch Job| FetchOK{Job Found?}
    FetchOK -->|No| Err1["❌ Job Not Found<br/>Status: FAILED"]
    FetchOK -->|Yes| SetRunning["Update status: RUNNING<br/>Publish message"]
    
    SetRunning --> Scrape["Execute Scraper Pipeline<br/>Tavily → Crawl4AI"]
    Scrape --> ScrapeOK{Scrape<br/>Success?}
    ScrapeOK -->|No| Err2["⚠️ Scraper Failed<br/>🚨 NO FALLBACK<br/>Job terminates"]
    ScrapeOK -->|Yes| LLMExec["Execute LLM Agents<br/>Master → Market → ... → Risk"]
    
    LLMExec --> LLMErr{LLM<br/>Error?}
    LLMErr -->|Timeout| Err3["❌ LLM Timeout<br/>Job: FAILED"]
    LLMErr -->|API Error| Err4["❌ LLM API Error<br/>🚨 NO RETRY LOGIC<br/>Job: FAILED"]
    LLMErr -->|Parse Error| Err5["❌ Schema Mismatch<br/>Status: FAILED"]
    LLMErr -->|Success| Serialize["Serialize Results<br/>Pydantic → JSON"]
    
    Serialize --> Store["Store in DB<br/>result_json, status=COMPLETED"]
    Store --> Publish["Publish COMPLETED<br/>to Redis"]
    Publish --> Success["✅ Job Complete"]
    
    Err1 --> ErrPublish["Publish error to Redis"]
    Err2 --> ErrPublish
    Err3 --> ErrPublish
    Err4 --> ErrPublish
    Err5 --> ErrPublish
    ErrPublish --> DBError["Store error_message<br/>status=FAILED"]
    DBError --> EndErr["❌ Analysis Failed"]
    
    style Job fill:#87CEEB
    style CelTask fill:#DDA0DD
    style FetchOK fill:#FFD700
    style Err1 fill:#FF4500,color:#fff
    style SetRunning fill:#90EE90
    style Scrape fill:#87CEEB
    style ScrapeOK fill:#FFD700
    style Err2 fill:#FF4500,color:#fff
    style LLMExec fill:#87CEEB
    style LLMErr fill:#FFD700
    style Err3 fill:#FF4500,color:#fff
    style Err4 fill:#FF4500,color:#fff
    style Err5 fill:#FF4500,color:#fff
    style Serialize fill:#90EE90
    style Store fill:#FF6347
    style Publish fill:#87CEEB
    style Success fill:#90EE90
    style EndErr fill:#FF4500,color:#fff
```

---

## 9. Sequential Agent Execution Timeline

```mermaid
timeline
    title Analysis Job Timeline (Sequential Agents)
    
    section Startup
        00:00 : Job Submitted
        00:05 : Celery Worker Picked Up
        00:15 : Master Query Node Generates Queries
    
    section Agent Execution
        01:00 : Market_Scout Starts (Tavily, Crawl4AI, Gemini)
        04:00 : Market_Scout Complete → Sentiment_Analyst Starts
        07:00 : Sentiment_Analyst Complete → Competitor_Tracker Starts
        10:00 : Competitor_Tracker Complete → Trend_Forecaster Starts
        13:00 : Trend_Forecaster Complete → Risk_Modeller Starts
        15:00 : Risk_Modeller Complete
    
    section Completion
        15:30 : Results Stored in DB
        15:45 : Status = COMPLETED, Redis Published
        16:00 : User Receives Results
        
        section Potential Bottlenecks
        01:00-04:00 : Market Scout (3 min) - Scraper
        04:00-07:00 : Sentiment Analyst (3 min) - Scraper
        10:00-13:00 : Competitor Tracker (3 min) - Scraper
        13:00-15:00 : Risk Modeller (2 min) - LLM only
```

---

## 10. Request Validation Pipeline

```mermaid
graph TD
    ReqReceived["📨 Request Received<br/>POST /analysis/submit"]
    
    ReqReceived --> Schema["Validate Schema<br/>AnalysisSubmitRequest"]
    Schema --> SchemaOK{Valid<br/>Schema?}
    SchemaOK -->|No| SchemaErr["❌ 422 Validation Error<br/>Return: error details"]
    SchemaOK -->|Yes| Len["Check business_idea length<br/>Minimum 200 chars (50 words)"]
    
    Len --> LenOK{Length<br/>OK?}
    LenOK -->|No| LenErr["❌ 422 Validation Error<br/>Must be 50+ words"]
    LenOK -->|Yes| Auth["Validate JWT Token"]
    
    Auth --> AuthOK{Valid<br/>JWT?}
    AuthOK -->|No| AuthErr["❌ 401 Unauthorized"]
    AuthOK -->|Yes| User["Fetch User from DB"]
    
    User --> UserOK{User<br/>Found?}
    UserOK -->|No| UserErr["❌ 404 User Not Found"]
    UserOK -->|Yes| Rate["Check Rate Limit<br/>10 analyses per day"]
    
    Rate --> RateOK{Under<br/>Limit?}
    RateOK -->|No| RateErr["❌ 429 Rate Limit Exceeded"]
    RateOK -->|Yes| Create["Create AnalysisJob<br/>status=PENDING"]
    
    Create --> Queue["Queue Celery Task"]
    Queue --> Respond["✅ 202 Accepted<br/>Return: {job_id, status, message}"]
    
    SchemaErr --> Error["Return Error Response"]
    LenErr --> Error
    AuthErr --> Error
    UserErr --> Error
    RateErr --> Error
    Error --> EndErr["❌ Request Failed"]
    
    Respond --> EndOK["✅ Request Queued"]
    
    style ReqReceived fill:#87CEEB
    style Schema fill:#FFD700
    style Len fill:#FFD700
    style Auth fill:#FFD700
    style User fill:#FF6347
    style Rate fill:#FFD700
    style Create fill:#90EE90
    style Queue fill:#DDA0DD
    style Respond fill:#90EE90
    style EndOK fill:#90EE90
    
    style SchemaErr fill:#FF4500,color:#fff
    style LenErr fill:#FF4500,color:#fff
    style AuthErr fill:#FF4500,color:#fff
    style UserErr fill:#FF4500,color:#fff
    style RateErr fill:#FF4500,color:#fff
    style EndErr fill:#FF4500,color:#fff
```

---

## 11. WebSocket Progress Broadcasting

```mermaid
sequenceDiagram
    participant Client as Client A
    participant ClientB as Client B
    participant WebSocket as WebSocket Handler
    participant Redis as Redis Pub/Sub
    participant Celery as Celery Worker
    participant Agent as Agent

    Client->>WebSocket: Connect<br/>WS /ws/{job_id}?token={jwt}
    WebSocket->>WebSocket: Validate JWT
    WebSocket->>Redis: Subscribe<br/>channel: progress:{job_id}

    ClientB->>WebSocket: Connect<br/>WS /ws/{job_id}?token={jwt}
    WebSocket->>Redis: Subscribe<br/>channel: progress:{job_id}

    Note over Celery,Agent: Parallel: Other work

    Agent->>Redis: Publish<br/>{status: AGENT_RUNNING, agent: Market_Scout}
    Redis->>WebSocket: Deliver message
    WebSocket->>Client: Send JSON
    WebSocket->>ClientB: Send JSON
    Client->>Client: Update UI
    ClientB->>ClientB: Update UI

    Note over Celery,Agent: More agent work...

    Agent->>Redis: Publish<br/>{status: AGENT_COMPLETE, agent: Market_Scout}
    Redis->>WebSocket: Deliver message
    WebSocket->>Client: Send JSON
    WebSocket->>ClientB: Send JSON

    Agent->>Redis: Publish<br/>{status: COMPLETED, message: Analysis complete}
    Redis->>WebSocket: Deliver message
    WebSocket->>Client: Send JSON + Close
    WebSocket->>ClientB: Send JSON + Close
    Client->>Client: Fetch final results
    ClientB->>ClientB: Fetch final results
```

---

## 12. Security & Authentication Flow

```mermaid
graph TD
    A["🔐 User Registration"]
    A --> B["Email + Password"]
    B --> C["Validate Email Format"]
    C --> D["Hash Password<br/>Bcrypt"]
    D --> E["Check Email Unique"]
    E --> EX{Exists?}
    EX -->|Yes| ER["❌ 409 Conflict<br/>Email exists"]
    EX -->|No| F["Store in DB<br/>users table"]
    F --> FR["✅ 201 Created<br/>user_id returned"]
    
    G["🔑 User Login"]
    G --> H["Email + Password"]
    H --> I["Query DB<br/>Find user by email"]
    I --> IX{Found?}
    IX -->|No| IE["❌ 401 Invalid Credentials"]
    IX -->|Yes| J["Verify Password<br/>Bcrypt compare"]
    J --> JX{Match?}
    JX -->|No| IE
    JX -->|Yes| K["Create JWT Tokens"]
    K --> L["Access Token<br/>TTL: 60 min<br/>Payload: {sub, exp}"]
    K --> M["Refresh Token<br/>TTL: 7 days<br/>Payload: {sub, exp}"]
    L --> N["✅ 200 OK<br/>Return tokens"]
    M --> N
    
    O["🔄 Token Refresh"]
    O --> P["Client sends<br/>refresh_token"]
    P --> Q["Decode JWT<br/>Verify signature"]
    Q --> QX{Valid?}
    QX -->|No| QE["❌ 401 Invalid Token"]
    QX -->|Yes| R["Issue new<br/>access_token"]
    R --> S["✅ 200 OK"]
    
    T["🛡️ Protected Request"]
    T --> U["Request header<br/>Authorization: Bearer {token}"]
    U --> V["Extract token"]
    V --> W["Decode JWT<br/>Verify HMAC-SHA256"]
    W --> WX{Valid?}
    WX -->|No| WE["❌ 401 Unauthorized"]
    WX -->|Yes| X["Extract user_id<br/>from payload"]
    X --> Y["Query DB<br/>Get User"]
    Y --> YX{Found & Active?}
    YX -->|No| YE["❌ 401/404 User error"]
    YX -->|Yes| Z["✅ Allow request<br/>Inject user into handler"]
    
    ER --> ERR["Register Failed"]
    IE --> LOGINERR["Login Failed"]
    QE --> REFRESHERR["Refresh Failed"]
    WE --> PREVERR["Request Denied"]
    YE --> PREVERR
    
    FR --> REGOK["✅ Registered"]
    N --> LOGINOK["✅ Logged In"]
    S --> REFRESHOK["✅ Tokens Refreshed"]
    Z --> PRESUCCESS["✅ Access Granted"]
    
    style A fill:#87CEEB
    style G fill:#87CEEB
    style O fill:#87CEEB
    style T fill:#87CEEB
    
    style K fill:#FFD700
    style L fill:#FFD700
    style M fill:#FFD700
    
    style FR fill:#90EE90
    style N fill:#90EE90
    style S fill:#90EE90
    style Z fill:#90EE90
    
    style ER fill:#FF4500,color:#fff
    style IE fill:#FF4500,color:#fff
    style QE fill:#FF4500,color:#fff
    style WE fill:#FF4500,color:#fff
    style YE fill:#FF4500,color:#fff
```

---

## Key Observations from These Diagrams:

1. **Sequential bottleneck**: Agents run one-at-a-time, each taking 3+ minutes (diagram 9)
2. **No error recovery**: Scraper failures terminate job immediately (diagram 8)
3. **Multiple clients can listen**: WebSocket broadcasts to all connected clients (diagram 11)
4. **Rate limiting applies per-user, not per-IP**: Account creation bypass possible (diagram 12)
5. **LLM entirely depends on Gemini**: No fallback implementation (diagram 3)

