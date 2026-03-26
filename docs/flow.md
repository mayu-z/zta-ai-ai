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

[ RESPONSE COMPOSER (SLM - SANDBOXED & UNTRUSTED) ]
  ⚠️  SLM Constraints:
    - Receives ONLY pre-approved, structured claims
    - NO access to databases or raw data
    - NO decision-making authority
    - NO tool or function calling
    - NO memory or state across requests
    - Runs in isolated, sandboxed environment
    - Stateless per request
  
  Responsibilities:
    - Convert structured claims → natural language
    - Apply tone and formatting
    - Generate explanations & summaries
    - Output: Structured JSON (not free-form)
  
  Example:
    Input:  { "revenue_Q1": "₹5Cr" }
    Output: {
              "summary": "Revenue for Q1 is ₹5 Crore.",
              "explanation": "...",
              "confidence": 0.95
            }
        ↓
[ DE-TOKENIZER + MASKING ]
  - Re-apply real values (if authorized)
  - Apply field-level masking
  - Remove unauthorized fields
        ↓
[ OUTPUT ]
  - Return to user with audit trail