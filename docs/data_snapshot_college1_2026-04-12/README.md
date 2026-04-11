# College One Data Snapshot (2026-04-12)

Tenant:
- name: College One
- tenant_id: 7dcc2d9d-6586-4370-a8ae-24e00a92e1c0

## What is connected right now

Data sources:
1. Campus Claim Store (`ipeds_claims`) - `connected`
2. Campus MySQL Mirror (`mysql`) - `connected`
3. Campus PostgreSQL Mirror (`postgresql`) - `connected`
4. ERP Adapter (`erpnext`) - `paused`
5. Research Sheet Connector (`google_sheets`) - `disconnected`

Connector config summary (secrets redacted):
- Campus Claim Store: connector=mock_claims, claims_table=claims
- Campus MySQL Mirror: connection_url=mysql+pymysql://readonly:readonly@db.example.edu:3306/campus, claims_table=claims
- Campus PostgreSQL Mirror: connection_url=postgresql://readonly:readonly@db.example.edu:5432/campus, claims_table=claims
- ERP Adapter: base_url=https://erp.example.edu, api_key=***REDACTED***, api_secret=***REDACTED***
- Research Sheet Connector: service_account_json.project_id=seeded-research-project, spreadsheet_id=seeded-sheet-id

## Runtime data shape

- users: 22
- claims: 86
- role_policies: 6
- data_sources: 5
- domain_keywords: 9
- intent_definitions: 18
- intent_detection_keywords: 0
- domain_source_bindings: 0
- schema_fields: 0
- control_graph_nodes: 133
- control_graph_edges: 311
- policy_proofs: 21

Claims by domain:
- academic: 34 rows
- finance: 16 rows
- admissions: 6 rows
- hr: 6 rows
- exam: 6 rows
- department: 6 rows
- campus: 4 rows
- notices: 4 rows
- admin: 4 rows

Claim keys in every domain:
- record_count
- record_name
- record_value
- status_summary

## Access model (role policies)

- student: domains=[academic, notices, campus], row_scope_mode=owner_id
- faculty: domains=[academic, department, notices], row_scope_mode=course_ids
- dept_head: domains=[academic, department, notices], row_scope_mode=department_id
- admin_staff: domains=[admissions, finance, hr, exam, campus, notices], row_scope_mode=admin_function
- executive: domains=[academic, finance, hr, admissions, exam, department, campus, notices], aggregate_only=true
- it_head: domains=[academic, finance, hr, admissions, exam, department, campus, admin, notices], chat_enabled=false

## Files in this snapshot

- tenants.csv
- users.csv
- role_policies.csv
- data_sources.csv
- domain_source_bindings.csv
- domain_keywords.csv
- intent_definitions.csv
- intent_detection_keywords.csv
- claims.csv
- schema_fields.csv
- control_graph_nodes.csv
- control_graph_edges.csv
- policy_proofs.csv
