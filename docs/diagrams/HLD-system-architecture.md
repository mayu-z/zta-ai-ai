# ZTA-AI High Level Design (HLD)

**Plan Alignment:** This HLD is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). In case of conflict, use the plan. See `docs/PLAN_ALIGNMENT.md`.

## 1. System Context Diagram

```mermaid
C4Context
    title ZTA-AI System Context

    Person(user, "Campus User", "Student, Faculty, Admin, Executive, IT Head")
    
    System(ztaai, "ZTA-AI Platform", "Secure AI-powered campus assistant with Zero Trust architecture")
    
    System_Ext(idp, "Enterprise Identity Provider", "OIDC/SAML identity provider for SSO")
    System_Ext(datasources, "Campus Data Sources", "ERPNext, Google Sheets, MySQL databases")
    
    Rel(user, ztaai, "Asks questions via", "HTTPS/WSS")
    Rel(ztaai, idp, "Authenticates via", "OIDC/SAML + MFA")
    Rel(ztaai, datasources, "Fetches claims from", "API/DB connections")
```

## 2. High-Level Architecture

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        PWA[PWA Frontend]
        Admin[Admin Dashboard]
    end

    subgraph Gateway["Zero Trust Gate"]
        Auth[Authentication]
        RBAC[RBAC/ABAC Engine]
        JWT[JWT Issuer]
    end

    subgraph Core["Core Processing Pipeline"]
        Interpreter[Interpreter Layer]
        Compiler[Compiler - Control Plane]
        Policy[Policy Engine]
        Tool[Tool/Function Layer]
    end

    subgraph Data["Data Layer"]
        Claims[Claim Engine]
        Cache[(Redis Cache)]
        DB[(PostgreSQL)]
    end

    subgraph SLM["SLM Runtime - SANDBOXED"]
        Simulator[Template Renderer]
        Guard[Output Guard]
    end

    subgraph Async["Background Services"]
        Celery[Celery Worker]
        Audit[Audit Logger]
    end

    PWA --> Auth
    Admin --> Auth
    Auth --> RBAC
    RBAC --> JWT
    JWT --> Interpreter
    Interpreter --> Compiler
    Compiler --> Policy
    Policy --> Tool
    Tool --> Claims
    Claims --> DB
    Compiler --> Simulator
    Simulator --> Guard
    Guard --> Compiler
    Compiler --> PWA
    Tool --> Celery
    Celery --> Audit
    Audit --> DB
    Interpreter --> Cache
```

## 3. Component Overview

```mermaid
graph LR
    subgraph Frontend
        F1[index.html]
        F2[script.js]
        F3[style.css]
    end

    subgraph Backend["Backend - FastAPI"]
        B1[app/main.py]
        B2[app/api/routes/]
        B3[app/services/]
        B4[app/db/]
    end

    subgraph Infrastructure
        I1[(PostgreSQL)]
        I2[(Redis)]
        I3[Celery Worker]
    end

    Frontend -->|HTTP/WS| Backend
    Backend --> Infrastructure
```

## 4. Data Flow - Query Processing

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant F as Frontend
    participant A as Auth Layer
    participant I as Interpreter
    participant C as Compiler
    participant P as Policy Engine
    participant T as Tool Layer
    participant S as SLM Simulator
    participant G as Output Guard
    participant D as Database

    U->>F: Natural language query
    F->>A: WebSocket + JWT
    A->>A: Validate token, extract scope
    A->>I: Query + ScopeContext
    I->>I: Parse intent, alias schema
    I->>C: InterpretedIntent
    C->>P: Authorize request
    P->>P: Check RBAC/ABAC rules
    P-->>C: Authorized
    C->>T: Execute compiled query
    T->>D: Parameterized SQL
    D-->>T: Raw data
    T-->>C: Values
    C->>S: Abstract intent only
    S-->>G: Template with [SLOT_N]
    G->>G: Validate no leaks
    G-->>C: Safe template
    C->>C: Inject values into slots
    C-->>F: Final response
    F-->>U: Display answer
```

## 5. Security Zones

```mermaid
flowchart TB
    subgraph TRUSTED["TRUSTED ZONE"]
        direction TB
        Auth[Authentication]
        Compiler[Compiler]
        Policy[Policy Engine]
        Tool[Tool Layer]
        DB[(Database)]
    end

    subgraph SEMI["SEMI-TRUSTED ZONE"]
        Interpreter[Interpreter]
        Cache[(Intent Cache)]
    end

    subgraph UNTRUSTED["UNTRUSTED ZONE - SANDBOXED"]
        SLM[SLM Simulator]
        style SLM fill:#ff6b6b,stroke:#c92a2a
    end

    subgraph PUBLIC["PUBLIC ZONE"]
        Client[Client/Browser]
    end

    Client -->|"JWT Auth"| Auth
    Auth --> Interpreter
    Interpreter --> Compiler
    Compiler --> Policy
    Policy --> Tool
    Tool --> DB
    Compiler -.->|"Abstract intent only"| SLM
    SLM -.->|"Slot template only"| Compiler
```

## 6. Deployment Architecture

```mermaid
flowchart TB
    subgraph Docker["Docker Compose Environment"]
        subgraph API["api container :8000"]
            FastAPI[FastAPI + Uvicorn]
        end
        
        subgraph Worker["worker container"]
            CeleryW[Celery Worker]
        end
        
        subgraph Postgres["postgres container :5432"]
            PG[(PostgreSQL 15)]
        end
        
        subgraph RedisC["redis container :6379"]
            RD[(Redis 7)]
        end
    end

    Client[Browser] -->|"HTTP/WS :8000"| API
    API --> Postgres
    API --> RedisC
    Worker --> Postgres
    Worker --> RedisC
```

## 7. User Personas & Access Hierarchy

```mermaid
flowchart TD
    subgraph Personas["User Personas"]
        IT[IT Head]
        Exec[Executive/Dean]
        Dept[Dept Head]
        Admin[Admin Staff]
        Faculty[Faculty]
        Student[Student]
    end

    subgraph Access["Data Access Levels"]
        A1[Admin Dashboard Only]
        A2[Campus-wide Aggregates]
        A3[Department Data]
        A4[Function-specific Data]
        A5[Course-level Data]
        A6[Self Data Only]
    end

    IT --> A1
    Exec --> A2
    Dept --> A3
    Admin --> A4
    Faculty --> A5
    Student --> A6
```
