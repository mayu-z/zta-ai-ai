# ZTA-AI Architecture Diagrams

**Plan Alignment:** Diagram intent is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). For canonical scope, phase gates, and security/compliance requirements, use the plan first. See `docs/PLAN_ALIGNMENT.md`.

This directory contains High Level Design (HLD) and Low Level Design (LLD) diagrams for the ZTA-AI platform.

## Files

| File | Description |
|------|-------------|
| [HLD-system-architecture.md](./HLD-system-architecture.md) | High-level system overview, data flows, security zones |
| [LLD-detailed-design.md](./LLD-detailed-design.md) | Database schema, API routes, class diagrams, detailed flows |

## Viewing the Diagrams

### VS Code
Install the **Markdown Preview Mermaid Support** extension:
```
ext install bierner.markdown-mermaid
```
Then use `Ctrl+Shift+V` to preview the markdown files.

### GitHub
GitHub natively renders Mermaid diagrams in markdown files.

### Online
Paste mermaid code blocks at [mermaid.live](https://mermaid.live) for interactive editing.

## Diagram Index

### HLD (High Level Design)
1. **System Context** - C4 context showing users and external systems
2. **High-Level Architecture** - All components and their relationships
3. **Component Overview** - Frontend/Backend/Infrastructure split
4. **Data Flow** - Query processing sequence diagram
5. **Security Zones** - Trust boundaries (Trusted/Semi-Trusted/Untrusted)
6. **Deployment Architecture** - Docker containers and ports
7. **User Personas** - Access hierarchy for each role

### LLD (Low Level Design)
1. **Database Schema (ERD)** - All tables and relationships
2. **API Routes** - REST endpoint structure
3. **Authentication Flow** - Login sequence diagram
4. **Pipeline Service** - Detailed query processing flowchart
5. **SLM Simulator** - Template mapping and output guard
6. **Policy Engine** - Authorization matrix
7. **WebSocket Chat** - Streaming message flow
8. **Celery Tasks** - Async audit logging
9. **Connector Architecture** - Data source plugin system
10. **Core Services** - Class diagram of main services
11. **Error Handling** - Exception hierarchy
12. **Request/Response Schemas** - Pydantic model structure
