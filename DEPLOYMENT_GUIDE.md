# Production Deployment Guide: Intent Detection Keywords Refactor

**Plan Alignment:** This deployment guide is aligned to `ZTA_AI_FINAL_PRODUCT_PRODUCTION_PLAN.md` (v3.0, April 11, 2026). The plan is authoritative for phase gates and production acceptance criteria. See `docs/PLAN_ALIGNMENT.md`.

## Overview

This document provides step-by-step instructions for deploying the architectural refactor that moves intent detection keywords (and eventually other hardcoded business logic) from Python code to database configuration.

**Goal:** Enable zero-downtime deployment of changes that remove hardcoded business decisions and make ZTA a pure policy mediation layer.

---

## Phase 2 Security Artifacts

The following production hardening artifacts are now available and should be applied as part of security phase execution:

- Kubernetes baseline network policies: `deploy/k8s/security/network-policies.yaml`
- Kubernetes approved external egress template: `deploy/k8s/security/external-egress-policy.example.yaml`
- Incident response runbook: `docs/incident-response-playbook.md`

Recommended order:

1. Align label selectors and namespace values with your environment.
2. Apply baseline network policies and verify pod-to-pod traffic.
3. Configure approved external egress CIDRs and verify outbound dependencies (OIDC/SLM).
4. Issue mTLS certificates using `backend/scripts/generate_mtls_artifacts.sh` and configure `SERVICE_MTLS_*` values.
5. Validate incident response on-call flow with a tabletop drill.

---

## Pre-Deployment Checklist

- [ ] All tests passing: `pytest backend/tests/test_intent_detection_keywords.py backend/tests/test_intent_extractor_with_keywords.py backend/tests/test_admin_intent_keywords_api.py backend/tests/test_migrations.py`
- [ ] Code review approved by 2+ reviewers
- [ ] Staging environment validated with full test suite
- [ ] Production database backup created and verified
- [ ] Rollback procedure tested in staging environment
- [ ] Team notified of scheduled deployment window
- [ ] Monitoring dashboards and alerts configured
- [ ] Post-deployment verification plan documented

---

## Phase 1: Code Deployment (No Service Impact)

This phase deploys new code without enabling the feature.

### 1.1 Deploy New Application Code

```bash
# Build new container image with code changes
docker build -t zta-ai:v2.1.0 backend/

# Tag image for registry
docker tag zta-ai:v2.1.0 registry.example.com/zta-ai:v2.1.0
docker push registry.example.com/zta-ai:v2.1.0

# Update Kubernetes deployment (or docker-compose, depending on environment)
# kubectl set image deployment/zta-api zta-api=registry.example.com/zta-ai:v2.1.0
# This does NOT restart services yet - we'll do that in Phase 2
```

**Why this works:** New code contains:
- New database models (IntentDetectionKeyword)
- Updated registry loader function
- Updated intent extraction logic with detection_keywords parameter
- New admin endpoints for managing keywords
- Updated seed script

But since detection_keywords defaults to empty dict, existing code paths work unchanged.

### 1.2 Verify Code Deployment

```bash
# Check that pods are updated with new image
docker ps | grep zta-ai:v2.1.0

# Verify logs show no errors
docker logs <container_id> | grep -i error | head -20
```

---

## Phase 2: Database Migration

This phase applies database schema changes.

### 2.1 Create Database Backup

```bash
# PostgreSQL backup (production environment)
pg_dump -h db.prod.internal -U postgres -d zta_production \
  --no-password > /backups/zta_pre_migration_$(date +%Y%m%d_%H%M%S).sql

# Verify backup
ls -lh /backups/zta_pre_migration_*.sql

# Test restore in staging
pg_restore -h db.staging.internal -U postgres -d zta_staging < /backups/zta_pre_migration_*.sql
```

### 2.2 Run Alembic Migrations

```bash
# Connect to production database
cd backend

# Check pending migrations
export DATABASE_URL="postgresql://user:password@db.prod.internal/zta_production"
alembic current
alembic heads

# Apply migrations
alembic upgrade head

# Verify migration succeeded
alembic current
# Output should show: "001_add_intent_detection_keywords"
```

**Migration Details:**
- Creates new table: `intent_detection_keywords`
- Adds indexes for efficient querying
- Sets up foreign key to tenants table
- Adds cascading delete for data integrity

### 2.3 Verify Migration

```sql
-- Connect to production database
psql -h db.prod.internal -U postgres -d zta_production

-- Verify table exists
\dt intent_detection_keywords

-- Verify columns
\d intent_detection_keywords

-- Verify indexes
\di ix_intent_detection_keywords_*

-- Verify foreign key relationship
SELECT constraint_name, table_name 
FROM information_schema.table_constraints 
WHERE table_name = 'intent_detection_keywords';

-- Verify migration history
SELECT version, description, installed_on FROM alembic_version;

-- Exit
\q
```

---

## Phase 3: Seed Data Population

This phase populates the new table with initial detection keywords.

### 3.1 Run Bootstrap Seed (First-Time Initialization)

```bash
# For existing tenant databases, run bootstrap seed
# This will populate intent_detection_keywords table with defaults
docker-compose exec api python -m scripts.bootstrap_seed

# Expected output:
# "Bootstrap already initialized for existing tenant; skipping re-seed"
# OR (if first time after migration)
# "Seed complete: runtime config bootstrapped for existing tenant"
# {"intent_detection_keywords_seeded": 15, ...}
```

### 3.2 Verify Seed Data

```sql
-- Query seed data
SELECT COUNT(*) as total_keywords
FROM intent_detection_keywords
WHERE is_active = true;

-- Expected: 15+ keywords (grade markers, attendance, fees)

-- List all keywords by intent
SELECT DISTINCT intent_name, keyword_type
FROM intent_detection_keywords
WHERE is_active = true
ORDER BY intent_name, keyword_type;

-- Expected intents: student_attendance, student_fee, student_grades
```

---

## Phase 4: Enable Feature & Restart Services

This phase makes the feature live.

### 4.1 Rolling Restart of API Containers

```bash
# Option 1: Kubernetes rolling update
kubectl rollout restart deployment/zta-api
kubectl rollout status deployment/zta-api --timeout=5m

# Option 2: Docker Compose
# Scale up new containers with new code
docker-compose up -d --scale api=2

# Wait for health checks
sleep 30
curl http://localhost:8000/health

# Once healthy, scale down old containers
docker-compose scale api=1
```

### 4.2 Verify Services Health

```bash
# Check API is responding
curl -s http://api.prod.internal/health | jq .

# Expected: {"status": "healthy", "database": "connected"}

# Check logs for errors
docker logs <api_container> | tail -50 | grep -i "error\|warning"

# Expected: No new errors related to intent detection
```

### 4.3 Monitor First Requests

```bash
# Submit test query to verify intent extraction works
POST /chat
Body: {
  "user_id": "test-user-123",
  "query": "show me my gpa"
}

# Expected response includes:
# - interpreted_intent.name = "student_grades"
# - no errors in pipeline stages
```

---

## Phase 5: Post-Deployment Validation

This phase confirms the feature works end-to-end.

### 5.1 Admin API Endpoint Testing

```bash
# Test creating a new detection keyword
POST /admin/intent-detection-keywords
Headers: {Authorization: "Bearer <admin_token>"}
Body: {
  "intent_name": "student_grades",
  "keyword_type": "grade_marker",
  "keyword": "test_keyword",
  "priority": 100,
  "is_active": true
}

# Expected: 200 OK with keyword details

# Test modifying detection keywords already triggers new behavior
# (no container restart needed)

# Submit query with new keyword
# Expected: query routes to correct intent using new keyword
```

### 5.2 Intent Routing Verification

```bash
# Test grade marker routing
Query: "what's my gpa?"
Expected Intent: "student_grades" (confidence high)

# Test fee routing
Query: "what's my balance?"
Expected Intent: "student_fee" (confidence high)

# Test attendance routing
Query: "what's my attendance?"
Expected Intent: "student_attendance" (confidence high)

# Test backward compatibility (old behavior still works)
Query: "show me my grades"
Expected Intent: "student_grades" (routes via keyword matching, not grade marker)
```

### 5.3 Monitor for 24 Hours

**Metrics to Watch:**
- Error rate: should be < 0.1% (no change from baseline)
- Intent extraction latency: should be << 100ms (no degradation)
- Database query performance: monitor pool exhaustion
- Cache hit rate: should be stable
- Admin API usage: track keyword CRUD operations

**Logging to Check:**
```bash
# Tail API logs for errors
docker logs -f api_container | grep -i error

# Check database slow queries
SELECT query, mean_time
FROM pg_stat_statements
WHERE query LIKE '%intent_detection%'
ORDER BY mean_time DESC
LIMIT 10;
```

---

## Rollback Procedure

This section covers emergency rollback if issues are detected.

### Immediate Actions (Within First Hour)

**If critical issue detected:**

1. **Disable feature flag** (if implemented)
   ```bash
   # Set environment variable to disable new code paths
   export ENABLE_INTENT_DETECTION_KEYWORDS=false
   docker-compose restart api
   ```

2. **Revert code** (if flag not available)
   ```bash
   docker-compose down
   rm /usr/local/bin/docker-compose.yml  # or your compose file
   
   # Pull previous working image
   docker pull registry.example.com/zta-ai:v2.0.9
   
   # Update compose file to use old image
   docker-compose up -d
   ```

3. **Restore database** (if data corruption)
   ```bash
   # Stop application
   docker-compose down
   
   # Restore from backup
   psql -h db.prod.internal -U postgres -d zta_production < \
     /backups/zta_pre_migration_20250101_120000.sql
   
   # Restart
   docker-compose up -d
   ```

### Full Rollback Steps

If emergency rollback needed:

```bash
# 1. Stop services
docker-compose down

# 2. Revert database (if necessary)
# Skip if feature only adds new tables without modifying existing ones
alembic downgrade -1
# or restore from backup (see above)

# 3. Switch to previous image
cd backend/
git checkout v2.0.9  # or previous working version
docker build -t zta-ai:v2.0.9-rollback .

# 4. Restart services
docker-compose up -d

# 5. Verify health
sleep 10
curl http://localhost:8000/health
```

### Verification After Rollback

```bash
# Check version
docker exec api python -c "import app; print(app.__version__)"

# Test basic query
POST /chat
Body: {"user_id": "test", "query": "show grades"}
# Should work without calling new detection keywords

# Check database state
alembic current
# Should show previous migration, NOT "001_add_intent_detection_keywords"
```

---

## Post-Rollback Recovery

If rollback occurred, follow this to re-deploy safely:

1. **Investigate root cause**
   - Check logs from rolled-back version
   - Analyze metrics at time of incident
   - Run local reproduction tests

2. **Fix issues**
   - Update code if bug found
   - Add/update tests to prevent regression
   - Code review with extended stakeholders

3. **Re-test in staging**
   - Full test suite
   - Load testing (if performance issue)
   - Migration script testing
   - Full end-to-end workflow

4. **Re-deploy with lessons learned**
   - Brief team on what went wrong
   - Execute deployment with additional monitoring
   - Extend validation period if necessary

---

## Deployment Timing & Notifications

### Recommended Deployment Window

- **Day:** Tuesday-Thursday (avoid Friday deployments)
- **Time:** 10 AM - 2 PM (business hours for quick response to issues)
- **Expected Duration:** 15-30 minutes for full deployment
- **Maintenance Window:** Notify users 24 hours in advance

### Communication Template

```
🚀 DEPLOYMENT NOTICE

We are deploying an architectural improvement to ZTA-AI that enables 
faster feature iterations and reduces code changes needed for business 
logic updates.

⏱️ Scheduled: [DATE] [TIME] - [TIME+30MIN] [TZ]
📊 Expected Impact: < 1 minute service interruption during rolling restart
🔄 Rollback Plan: Yes, tested and ready

No user action required. Your queries will continue working normally.

Questions? Contact the DevOps team.
```

---

## Success Criteria

Deployment is considered successful if:

1. ✅ All tests pass (unit + integration + migration tests)
2. ✅ Zero database integrity issues (constraints, foreign keys working)
3. ✅ Intent extraction latency unchanged (< 50ms baseline)
4. ✅ Grade marker routing works (gpa → student_grades)
5. ✅ Admin endpoints functioning (can create/list/delete keywords)
6. ✅ No errors in logs related to new feature
7. ✅ Error rate stable (<0.1% on all endpoints)
8. ✅ Backward compatibility maintained (old queries still work)
9. ✅ 24-hour monitoring shows no degradation
10. ✅ Team trained on new admin endpoints

---

## Reverting to Previous Version

If needed long-term:

```bash
# Option 1: Keep new code, disable detection keywords
# Set env var: ENABLE_INTENT_DETECTION_KEYWORDS=false
# New code paths skip DB loading, use hardcoded defaults

# Option 2: Full version revert
git revert <commit_hash>
docker build -t zta-ai:v2.0.9-fixed .

# Option 3: Feature branch recovery
git checkout <old_branch>
git pull
docker build ...
```

---

##  Monitoring Queries

### Database Health

```sql
-- Check table sizes
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename IN ('intent_definition', 'intent_detection_keywords')
ORDER BY pg_total_relation_size DESC;

-- Check index usage
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename LIKE 'intent_detection%'
ORDER BY idx_scan DESC;

-- Monitor table growth
SELECT
  COUNT(*) as total_keywords,
  COUNT(DISTINCT intent_name) as unique_intents,
  COUNT(DISTINCT keyword_type) as unique_types
FROM intent_detection_keywords
WHERE is_active = true;
```

### Application Performance

```sql
-- Intent extraction performance
SELECT
  intent_name,
  COUNT(*) as extraction_count,
  AVG(extraction_time_ms) as avg_time,
  MAX(extraction_time_ms) as max_time
FROM pipeline_telemetry
WHERE stage = 'intent_extraction'
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY intent_name
ORDER BY avg_time DESC;

-- Cache hit rate
SELECT
  intent_name,
  status,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY intent_name), 2) as pct
FROM pipeline_telemetry
WHERE stage = 'intent_cache'
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY intent_name, status
ORDER BY intent_name, status;
```

---

## Support & Escalation

### If Deployment Fails

1. **Immediate Action**: Initiate rollback (see Rollback Procedure)
2. **Notify**: Escalate to architecture team
3. **Document**: Log incident details for post-mortem
4. **Communicate**: Notify users of status within 5 minutes

### Emergency Contacts

- On-Call DevOps: [PHONE/SLACK]
- Platform Architect: [CONTACT]
- Database Team: [CONTACT]
- Product Manager: [CONTACT]

---

## Appendix: Testing Checklist

```bash
# Before deployment, run:

# 1. Unit tests
pytest backend/tests/test_intent_detection_keywords.py -v
pytest backend/tests/test_intent_extractor_with_keywords.py -v
pytest backend/tests/test_migrations.py -v

# 2. Integration tests
pytest backend/tests/test_admin_intent_keywords_api.py -v

# 3. Existing tests (regression)
pytest backend/tests/ -k "not test_intent_detection" -x

# 4. Migration testing
alembic upgrade head  # should complete without errors
alembic downgrade -1  # should complete without errors
alembic upgrade head  # should complete without errors

# 5. Manual smoke tests (see Post-Deployment Validation)
```
