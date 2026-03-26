# ZTA-AI — Data Integration & Connector Architecture (SLM-Strict)

**// universal connector layer — on-prem · cloud · saas · files**

---

## 01 — Three Ways to Connect Any Data Source

### No-Code UI Connector
*   **Method**: Admin opens ZTA-AI dashboard → clicks "Add Data Source" → fills in credentials → done.
*   **Ideal for**: IT admins and non-technical teams. Zero engineering required.
*   **Tags**: DASHBOARD, GUIDED WIZARD, 5-MIN SETUP

### SDK / API Integration
*   **Method**: Developer installs ZTA-AI SDK, registers data source via code.
*   **Control**: Full control over sync schedules, field mappings, and custom transformations.
*   **Supported**: REST + Python/Node/Java SDKs.
*   **Tags**: REST API, PYTHON SDK, NODE SDK, JAVA SDK

### On-Prem Agent
*   **Method**: Lightweight agent installed inside the client's private network.
*   **Security**: Reads data locally, encrypts it, and pushes only what's needed via outbound-only tunnel. No inbound firewall rules needed.
*   **Tags**: OUTBOUND ONLY, ENCRYPTED TUNNEL, ON-PREM SAFE

---

## 02 — Connector Catalog

### Databases
*   **PostgreSQL**: Native driver. Read-only service account enforced. SSL required. (JDBC, SSL, READ-ONLY)
*   **MySQL / MariaDB**: Connection pooling via PgBouncer-style proxy. Row-level filters applied. (POOLED, RLS)
*   **Microsoft SQL Server**: Windows Auth or SQL Auth. Supports Azure SQL & on-prem MSSQL. (WINDOWS AUTH, AZURE SQL)
*   **Oracle DB**: TNS / JDBC connection. Enterprise wallet support. (TNS, WALLET)
*   **MongoDB**: Document store. Schema inferred automatically. Read replica preferred. (ATLAS, SELF-HOSTED)
*   **Redis**: Cache / session data. Used as ephemeral context layer, not primary source. (CACHE, CONTEXT)
*   **Snowflake**: Data warehouse. OAuth2 + private key auth. Query cost guardrails enforced. (WAREHOUSE, OAUTH2)
*   **AWS RDS / Aurora**: IAM-based auth. VPC-peering or private link required for security. (IAM AUTH, VPC)

### Cloud Storage
*   **AWS S3**: IAM role-based access. Bucket policy enforcement. Object-level encryption. (IAM ROLE, SSE-KMS)
*   **Google Cloud Storage**: Service account JSON key or Workload Identity Federation. CMEK support. (SERVICE ACCT, CMEK)
*   **Azure Blob Storage**: Managed identity or SAS token auth. Supports ADLS Gen2 hierarchical NS. (MANAGED ID, SAS)
*   **AWS Glue / Athena**: Query S3 data lake via Athena. Schema catalog auto-discovered via Glue. (DATA LAKE, CATALOG)
*   **Azure Data Lake**: ADLS Gen2. Hierarchical namespace. Delta Lake format supported. (DELTA LAKE)
*   **BigQuery**: Serverless data warehouse. Column-level security via BigQuery policies. (SERVERLESS, COL SECURITY)

### SaaS Tools
*   **Slack**: OAuth2 bot token. Reads channels, threads, DMs per permission scope. RBAC applied per channel. (OAUTH2, BOT TOKEN)
*   **Jira / Confluence**: Atlassian OAuth2. Issues, sprints, wiki pages. Project-level RBAC enforced. (ATLASSIAN, PROJECT SCOPE)
*   **Salesforce**: Connected App OAuth. Reads CRM objects. Field-level security from Salesforce profiles respected. (CONNECTED APP, FLS)
*   **SAP**: RFC / OData API. BAPI calls. Supports S/4HANA and ECC. SSO via SAML. (ODATA, RFC, SAML)
*   **ServiceNow**: REST Table API. ITSM tickets, CMDB, incidents. OAuth or basic auth. (TABLE API, ITSM)
*   **Microsoft 365**: Graph API. SharePoint, OneDrive, Teams, Outlook. Azure AD app registration. (GRAPH API, AZURE AD)
*   **Google Workspace**: OAuth2. Drive, Docs, Sheets, Gmail. Domain-wide delegation supported. (DOMAIN DELEG, DRIVE API)
*   **HubSpot / Zendesk**: CRM and support tickets. Private app tokens. Customer data RBAC enforced. (CRM, SUPPORT)

### File Uploads
*   **PDF Documents**: OCR + text extraction. Multi-page chunking with overlap. Metadata preserved. (OCR, CHUNKING)
*   **Excel / CSV**: Sheet-level parsing. Headers auto-detected. Data types inferred. Large files streamed. (XLSX, STREAM)
*   **Word / Docs**: DOCX parsed. Tables, headings, footnotes extracted. Revision history ignored. (DOCX, STRUCTURED)
*   **PowerPoint / Slides**: Slide text, speaker notes extracted. Images skipped unless OCR enabled. (PPTX, NOTES)
*   **JSON / XML / YAML**: Structured data files parsed directly. Schema auto-inferred. Nested objects flattened. (JSON, XML, YAML)
*   **Email Exports (.eml / .mbox)**: Thread parsing, sender/recipient extraction. PII flagged and masked automatically. (EML, PII MASK)

---

## 03 — Universal Ingest Pipeline (Claim-Based Architecture)

**Every source goes through these steps to produce immutable, versioned claims:**

1.  **STEP 01: Source Connect**: Credential validated, connection tested, read-only access confirmed. (AUTH CHECK)
2.  **STEP 02: Schema Discovery**: Tables, fields, types auto-discovered. Admin reviews & approves exposed fields. (FIELD MAP)
3.  **STEP 03: PII Scanner**: Detects names, emails, SSNs, phone numbers, card numbers. Auto-flags for masking. (PII DETECT)
4.  **STEP 04: RBAC Mapping**: Admin assigns which departments and roles can see each table/collection/field via Policy Engine. (ROLE ASSIGN)
5.  **STEP 05: Alias Layer**: Real table & column names replaced with abstract aliases. SLM never sees real names. (ALIASING)
6.  **STEP 06: Claim Generation**: Data converted to immutable, versioned claims with provenance, sensitivity, and compliance tags. (CLAIM ENGINE)
7.  **STEP 07: Index & Embed**: Vector embeddings created for semantic search (RAG path). Stored in isolated per-tenant index. (VECTOR DB)
8.  **STEP 08: Live & Ready**: Source registered. Sync schedule set. ZTA-AI can now serve queries against this data. (ACTIVE)

**Note**: SLM receives only pre-approved, sanitized claims via the Context Governance Layer — never raw data.

---

## 04 — SDK Quickstart (Developer Path)

### Install & Connect Database (Python)
```python
# Install the ZTA-AI SDK
pip install ztaai-sdk

from ztaai import ZTAConnector

# Initialize with your org API key
connector = ZTAConnector(
    api_key="zta_org_xxxxxxxxxxxx",
    org_id="acme-corp"
)

# Register a PostgreSQL source
connector.register_source(
    name="hr_database",
    type="postgresql",
    host="10.0.1.50",
    port=5432,
    database="hr_prod",
    user="zta_readonly",
    password="env:DB_PASS",   # reads from env var
    ssl=True,
    department_scope="HR",       # RBAC silo
    sync_schedule="*/15 * * * *" # every 15 min
)
```

### Connect SaaS + File Upload (Python)
```python
# Connect a SaaS source (Salesforce)
connector.register_source(
    name="salesforce_crm",
    type="salesforce",
    auth_type="oauth2",
    client_id="env:SF_CLIENT_ID",
    client_secret="env:SF_SECRET",
    department_scope="SALES",
    objects=["Account", "Opportunity"]
)

# Upload a file source
connector.upload_file(
    file_path="./q3_report.pdf",
    label="Q3 Finance Report",
    department_scope="FINANCE",
    expires_in_days=90           # auto-purge
)

# Check all registered sources
connector.list_sources()
# → [hr_database , salesforce_crm , q3_report.pdf ]
```

---

## 05 — On-Prem Agent (Air-Gapped / Private Network)

**Status**: For companies that cannot expose their DB to the internet — the ZTA-AI Agent runs inside their network and syncs outbound only. No inbound ports needed. No firewall changes.

### Install Agent
*   **Method**: Single Docker container or binary. Runs inside company's private network. Registers with ZTA-AI cloud via unique org token.
```bash
docker run -d \
  -e ORG_TOKEN=zta_agent_xxx \
  ztaai/agent:latest
```

### How It Syncs
*   **Process**: Agent reads from local DB → encrypts with org's private key → sends only the approved abstract alias payload outbound to ZTA-AI endpoint. Raw data never leaves the network.
*   **Tags**: OUTBOUND ONLY, AES-256, RAW DATA STAYS LOCAL

### Query Flow (On-Prem)
*   **Process**: When ZTA-AI needs to answer a query, it sends the compiled abstract query to the agent. Agent executes locally, returns encrypted results. LLM never sees raw data.
*   **Tags**: LOCAL EXECUTION, ENCRYPTED RETURN

---

## 06 — No-Code Setup Wizard (Admin Dashboard Flow)

1.  **01: Open Dashboard**: Admin logs into ZTA-AI portal → goes to "Data Sources" → clicks "+ Add Source".
2.  **02: Pick Source Type**: Selects from catalog (PostgreSQL, S3, Salesforce, file upload, etc.) from a visual tile grid.
3.  **03: Enter Credentials**: Fills in host, port, credentials. ZTA-AI immediately tests connection and shows live status.
4.  **04: Review Schema**: Auto-discovered tables/fields shown. Admin toggles which fields to expose, which to always mask.
5.  **05: Assign to Roles**: Drag-assign tables to department silos (HR, Finance, etc.) using the RBAC mapping UI.
6.  **06: Set Sync Schedule**: Choose real-time CDC, hourly, daily, or manual. ZTA-AI handles incremental sync automatically.
7.  **07: Go Live**: Source active. Employees can now ask the chatbot questions backed by this data immediately.

> **Security Note**: ZTA-AI stores **zero raw data** from the client's systems. It stores only the alias map, immutable claims with provenance/compliance tags, vector embeddings of approved content, and the RBAC policy config. All actual query execution happens against the client's live source (or via the on-prem agent). The SLM receives only pre-approved, sanitized claim payloads — never raw data. If a client disconnects, all their config is wiped from ZTA-AI systems within 24 hours.

---

## 07 — Sync & Freshness Modes

*   **Real-Time CDC**: Change Data Capture via database WAL / binlog. Millisecond freshness. Best for operational DBs. (WAL / BINLOG, <100MS)
*   **Scheduled Sync**: Incremental pull on a cron. Every 5 min to daily. Best for file sources and SaaS APIs. (CRON, INCREMENTAL)
*   **Event-Driven Push**: Client pushes updates via ZTA-AI webhook endpoint. Zero polling overhead. Ideal for SaaS. (WEBHOOK, PUSH)
*   **Manual / On-Demand**: Admin triggers re-index manually. Best for large static datasets like annual reports or contracts. (ON-DEMAND, STATIC DOCS)
