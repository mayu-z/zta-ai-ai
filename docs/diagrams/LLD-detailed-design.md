# ZTA-AI Low Level Design (LLD)

**Plan Alignment:** This LLD is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). If implementation details here diverge from plan requirements, use the plan. See `docs/PLAN_ALIGNMENT.md`.

## 1. Database Schema (ERD)

```mermaid
erDiagram
    TENANTS ||--o{ USERS : has
    TENANTS ||--o{ DATA_SOURCES : has
    TENANTS ||--o{ CLAIMS : has
    TENANTS ||--o{ AUDIT_LOG : has
    TENANTS ||--o{ INTENT_CACHE : has
    DATA_SOURCES ||--o{ SCHEMA_FIELDS : defines
    USERS ||--o{ AUDIT_LOG : generates

    TENANTS {
        uuid id PK
        string name
        string domain UK
        string subdomain
        enum plan_tier
        enum status
        string google_workspace_domain
        timestamp created_at
    }

    USERS {
        uuid id PK
        uuid tenant_id FK
        string email UK
        string name
        enum persona_type
        string department
        string external_id
        string admin_function
        json course_ids
        json masked_fields
        enum status
        timestamp last_login_at
        timestamp created_at
    }

    CLAIMS {
        uuid id PK
        uuid tenant_id FK
        string domain
        string entity_type
        string entity_id
        string owner_id
        string department_id
        string course_id
        string admin_function
        string claim_key
        string value_text
        float value_number
        int version
        string provenance
        enum sensitivity
        json compliance_tags
        timestamp created_at
    }

    DATA_SOURCES {
        uuid id PK
        uuid tenant_id FK
        string name
        enum source_type
        string config_encrypted
        json department_scope
        enum status
        timestamp last_sync_at
        string sync_error_msg
        timestamp created_at
    }

    SCHEMA_FIELDS {
        uuid id PK
        uuid tenant_id FK
        uuid data_source_id FK
        string real_table
        string real_column
        string aliased_name
        enum visibility
        json persona_access
        timestamp created_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string session_id
        string query_text
        string intent_hash
        json domains_accessed
        boolean was_blocked
        string block_reason
        text response_summary
        int latency_ms
        timestamp created_at
    }

    INTENT_CACHE {
        uuid id PK
        uuid tenant_id FK
        string intent_hash UK
        json normalized_intent
        text response_template
        json compiled_query
        timestamp created_at
        timestamp expires_at
    }
```

## 2. API Routes Structure

```mermaid
flowchart LR
    subgraph Routes["API Routes"]
        subgraph Auth["/auth"]
            A1["POST /google"]
            A2["POST /refresh"]
            A3["POST /logout"]
        end

        subgraph Chat["/chat"]
            C1["GET /suggestions"]
            C2["GET /history"]
            C3["WS /stream"]
        end

        subgraph Admin["/admin"]
            D1["GET /users"]
            D2["PUT /users/{id}"]
            D3["POST /users/import"]
            D4["GET /data-sources"]
            D5["POST /data-sources"]
            D6["GET /data-sources/{id}/schema"]
            D7["GET /audit-log"]
            D8["POST /security/kill"]
        end
    end
```

## 3. Authentication Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as /auth/google
    participant G as Google OAuth
    participant I as IdentityService
    participant DB as Database
    participant J as JWTService

    C->>A: POST {google_token: "mock:email@domain"}
    A->>G: Verify token (or mock parse)
    G-->>A: {email, name}
    A->>I: authenticate(email)
    I->>DB: SELECT tenant WHERE domain = email_domain
    alt Tenant not found
        I-->>A: UNKNOWN_TENANT error
    end
    I->>DB: SELECT user WHERE email = email
    alt User not found
        I->>DB: INSERT new user (auto-provision)
    end
    I->>I: Build ScopeContext from user + tenant
    I->>J: sign_token(scope_context)
    J-->>I: JWT string
    I-->>A: AuthResponse{jwt, user}
    A-->>C: 200 OK {jwt, user}
```

## 4. Pipeline Service - Query Processing

```mermaid
flowchart TB
    subgraph Input
        Q[Query Text]
        S[ScopeContext]
    end

    subgraph Pipeline["PipelineService.process_query()"]
        direction TB
        
        H1[Append to history]
        
        subgraph Interpreter["InterpreterService"]
            I1[Parse query to intent]
            I2[Alias schema identifiers]
            I3[Hash intent]
            I4[Check cache]
        end
        
        subgraph SLM["SLM Layer"]
            S1[Render template]
            S2[Output guard validation]
        end
        
        subgraph Compiler["CompilerService"]
            C1[Compile intent to query plan]
            C2[Add scope constraints]
        end
        
        subgraph Policy["PolicyEngine"]
            P1[Check RBAC rules]
            P2[Check domain access]
            P3[Authorize or block]
        end
        
        subgraph Tool["ToolLayerService"]
            T1[Execute compiled query]
            T2[Fetch from data source]
        end
        
        subgraph Mask["Field Masking"]
            M1[Apply masked_fields policy]
        end
        
        subgraph Final["Finalization"]
            F1[Detokenize - inject values]
            F2[Cache intent if new]
            F3[Log to audit]
        end
    end

    Q --> H1
    S --> H1
    H1 --> I1
    I1 --> I2
    I2 --> I3
    I3 --> I4
    I4 -->|cache miss| S1
    I4 -->|cache hit| C1
    S1 --> S2
    S2 --> C1
    C1 --> C2
    C2 --> P1
    P1 --> P2
    P2 --> P3
    P3 -->|authorized| T1
    P3 -->|blocked| Error[ZTAError]
    T1 --> T2
    T2 --> M1
    M1 --> F1
    F1 --> F2
    F2 --> F3
    F3 --> Response[PipelineResult]
```

## 5. SLM Simulator - Template Mapping

```mermaid
flowchart LR
    subgraph Input
        Intent[InterpretedIntent]
        Scope[ScopeContext]
    end

    subgraph Simulator["SLMSimulator.render_template()"]
        Map{intent.name lookup}
        
        T1["student_attendance → 'Your attendance is [SLOT_1]% across [SLOT_2] subjects.'"]
        T2["student_grades → 'Your current GPA is [SLOT_1] with [SLOT_2] passed.'"]
        T3["student_fee → 'Outstanding fee: [SLOT_1], due [SLOT_2].'"]
        T4["faculty_course_attendance → '[SLOT_1] courses, avg [SLOT_2]%'"]
        T5["department_metrics → 'Performance index [SLOT_1], [SLOT_2] students'"]
        T6["executive_kpi → 'KPI [SLOT_1], trend delta [SLOT_2]'"]
        Default["domain_summary → 'Value [SLOT_1], secondary [SLOT_2]'"]
    end

    subgraph Guard["OutputGuard.validate()"]
        Check1[No raw numbers?]
        Check2[No real identifiers?]
        Check3[No SQL keywords?]
        Check4[Has SLOT placeholders?]
    end

    Intent --> Map
    Scope --> Map
    Map --> T1
    Map --> T2
    Map --> T3
    Map --> T4
    Map --> T5
    Map --> T6
    Map --> Default
    T1 --> Check1
    Check1 --> Check2
    Check2 --> Check3
    Check3 --> Check4
    Check4 -->|pass| Template[Safe Template]
    Check4 -->|fail| Error[UnsafeOutputError]
```

## 6. Policy Engine - Authorization Matrix

```mermaid
flowchart TB
    subgraph PersonaRules["Persona → Domain Access"]
        Student["student → academic, finance_self, notices"]
        Faculty["faculty → academic (course-scoped), notices"]
        DeptHead["dept_head → department, academic, finance_dept"]
        AdminStaff["admin_staff → function-specific domain"]
        Executive["executive → campus aggregates"]
        ITHead["it_head → admin only, NO chat"]
    end

    subgraph Checks["Authorization Checks"]
        C1{Domain allowed?}
        C2{Scope valid?}
        C3{Field masking needed?}
    end

    subgraph Actions
        Allow[Return authorized]
        Block[Raise AuthorizationError]
        Mask[Apply field masks]
    end

    PersonaRules --> C1
    C1 -->|yes| C2
    C1 -->|no| Block
    C2 -->|yes| C3
    C2 -->|no| Block
    C3 -->|yes| Mask
    C3 -->|no| Allow
    Mask --> Allow
```

## 7. WebSocket Chat Stream Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant WS as WebSocket /chat/stream
    participant Auth as get_scope_from_token
    participant RL as RateLimiter
    participant P as PipelineService
    participant H as HistoryService

    C->>WS: Connect with ?token=JWT
    WS->>WS: websocket.accept()
    
    loop Message Loop
        C->>WS: {query: "question"}
        WS->>Auth: Validate JWT
        alt Invalid token
            WS-->>C: {type: "error", message: "..."}
            WS->>WS: close(1008)
        end
        Auth-->>WS: ScopeContext
        
        WS->>RL: check_limit(scope)
        alt Rate limited
            WS-->>C: {type: "error", message: "Rate limit"}
        end
        
        WS->>P: process_query(scope, query)
        
        loop Token Streaming
            P-->>WS: token
            WS-->>C: {type: "token", content: "word "}
        end
        
        P-->>WS: PipelineResult
        WS-->>C: {type: "done", intent_hash, domains, latency_ms}
    end

    C->>WS: Close connection
    WS->>WS: Cleanup
```

## 8. Celery Task Flow - Audit Logging

```mermaid
flowchart LR
    subgraph Sync["Synchronous Path"]
        API[API Request]
        Service[AuditService.enqueue]
        Queue[Celery Task Queue]
    end

    subgraph Async["Celery Worker"]
        Task[write_audit_event_task]
        Repo[AuditRepository]
        DB[(PostgreSQL audit_log)]
    end

    API --> Service
    Service -->|delay()| Queue
    Queue --> Task
    Task --> Repo
    Repo --> DB
```

## 9. Data Source Connector Architecture

```mermaid
classDiagram
    class BaseConnector {
        <<abstract>>
        +tenant_id: str
        +source_id: str
        +config: dict
        +fetch_claims() list~Claim~
        +test_connection() bool
    }

    class MockClaimsConnector {
        +fetch_claims() list~Claim~
        +test_connection() bool
    }

    class PostgreSQLConnector {
        +connection_string: str
        +fetch_claims() list~Claim~
        +test_connection() bool
    }

    class GoogleSheetsConnector {
        +spreadsheet_id: str
        +credentials: dict
        +fetch_claims() list~Claim~
        +test_connection() bool
    }

    class ConnectorRegistry {
        -_connectors: dict
        +register(type, cls)
        +get(type) BaseConnector
        +create(source) BaseConnector
    }

    BaseConnector <|-- MockClaimsConnector
    BaseConnector <|-- PostgreSQLConnector
    BaseConnector <|-- GoogleSheetsConnector
    ConnectorRegistry --> BaseConnector
```

## 10. Class Diagram - Core Services

```mermaid
classDiagram
    class PipelineService {
        +process_query(db, scope, query) PipelineResult
    }

    class InterpreterService {
        +run(db, scope, query) InterpreterOutput
    }

    class CompilerService {
        +compile_intent(scope, intent) CompiledQuery
        +detokenize(template, plan, values) str
    }

    class PolicyEngine {
        +authorize(scope, intent, query) void
        +apply_field_masking(values, fields) tuple
    }

    class ToolLayerService {
        +execute(db, query) list~dict~
    }

    class SLMSimulator {
        +render_template(intent, scope) str
    }

    class OutputGuard {
        +validate(template, identifiers) void
    }

    class IdentityService {
        +authenticate(email) tuple
        +build_scope_context(user, tenant) ScopeContext
    }

    PipelineService --> InterpreterService
    PipelineService --> CompilerService
    PipelineService --> PolicyEngine
    PipelineService --> ToolLayerService
    PipelineService --> SLMSimulator
    CompilerService --> OutputGuard
```

## 11. Error Handling Hierarchy

```mermaid
classDiagram
    class ZTAError {
        +message: str
        +code: str
        +http_status: int
    }

    class AuthenticationError {
        +http_status = 401
    }

    class AuthorizationError {
        +http_status = 403
    }

    class RateLimitError {
        +http_status = 429
    }

    class UnsafeOutputError {
        +http_status = 500
    }

    class QueryValidationError {
        +http_status = 400
    }

    ZTAError <|-- AuthenticationError
    ZTAError <|-- AuthorizationError
    ZTAError <|-- RateLimitError
    ZTAError <|-- UnsafeOutputError
    ZTAError <|-- QueryValidationError
```

## 12. Request/Response Schemas

```mermaid
classDiagram
    class ScopeContext {
        +tenant_id: str
        +user_id: str
        +session_id: str
        +email: str
        +name: str
        +persona_type: str
        +department: str
        +external_id: str
        +admin_function: str
        +course_ids: list
        +allowed_domains: list
        +denied_domains: list
        +masked_fields: list
        +aggregate_only: bool
        +chat_enabled: bool
    }

    class InterpretedIntent {
        +name: str
        +domain: str
        +params: dict
        +normalized() str
    }

    class CompiledQuery {
        +source_type: str
        +query_plan: dict
        +scope_filters: dict
        +requested_fields: list
    }

    class PipelineResult {
        +response_text: str
        +source: str
        +latency_ms: int
        +intent_hash: str
        +domains_accessed: list
        +was_blocked: bool
    }

    class AuditEvent {
        +tenant_id: str
        +user_id: str
        +session_id: str
        +query_text: str
        +intent_hash: str
        +domains_accessed: list
        +was_blocked: bool
        +block_reason: str
        +response_summary: str
        +latency_ms: int
        +created_at: datetime
    }
```
