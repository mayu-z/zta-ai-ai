# External Mock University Postgres

This stack runs a separate PostgreSQL instance for manual connector testing.
It is intentionally outside the main ZTA compose project.

## Start

```bash
cd external-mock-university-db
docker compose up -d
```

## Connection Details

- Host: `localhost`
- Port: `55432`
- Database: `university_mock`
- User: `university`
- Password: `university`

Connection URL example for ZTA data source:

`postgresql+psycopg2://university:university@host.docker.internal:55432/university_mock`

Use `localhost` instead of `host.docker.internal` when testing from host tools.

## Important Tenant ID Binding Step

The `claims` rows are seeded with `REPLACE_WITH_ZTA_TENANT_ID`.
After creating a tenant in ZTA via `/system-admin/tenants`, run:

```sql
SELECT rebind_claims_tenant('<tenant_id_from_system_admin_api>');
```

You can run this from psql:

```bash
docker compose exec -T university-postgres psql -U university -d university_mock -c "SELECT rebind_claims_tenant('<tenant_id>');"
```

## Seeded Personas

- 1 tenant admin (`tenant.admin@college1.com`)
- 1 dean (`dean@college1.com`)
- 1 HOD (`hod.cse@college1.com`)
- 4 admin office users (`admissions`, `finance`, `hr`, `exam`)
- 5 faculty (`faculty1`..`faculty5`)
- 10 students (`student1`..`student10`)

## Stop

```bash
docker compose down
```
