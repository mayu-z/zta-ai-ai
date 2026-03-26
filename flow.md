[ WEB-APP & MOBILE APPLICATION ]
        ↓
[ API LAYER (GATEWAY) ]
  - TLS / Auth headers
  - Rate limiting
        ↓
[ AUTH - RBAC/ABAC ]
  - Verify identity (JWT / SSO)
  - Check role + attributes
  - Generate access token
        ↓
[ INTERPRETER (INTENT ROUTER) ]
  - Parse query
  - Map to structured intent
  - Validate scope
  Example:
    "Show Q1 revenue"
    → { intent: "fetch", entity: "revenue", period: "Q1" }
        ↓
        ├───────────────────────┐
        │                       │
        ↓                       ↓

[ STRUCTURED PATH (SQL) ]  [ RAG PATH (VECTOR SEARCH) ]
  - Compiler                - Embedding Search
  - Query Builder           - Top-K retrieval
  - Safe SQL                - Metadata filter
        ↓                       ↓
[ DATABASE ]               [ VECTOR DB ]
        ↓                       ↓
[ TOKENIZER ]          [ CHUNK TOKENIZER ]
        ↓                       ↓
        └───────────┬───────────┘
                    ↓

[ RESPONSE COMPOSER (LLM) ]
  - Convert tokens → natural language
  - Apply tone and formatting
  Example:
    { "revenue_Q1": "₹5Cr" }
    → "Revenue for Q1 is ₹5 Crore."
        ↓
[ DE-TOKENIZER + MASKING ]
  - Re-apply real values (if authorized)
  - Apply field-level masking
  - Remove unauthorized fields
        ↓
[ OUTPUT ]
  - Return to user with audit trail