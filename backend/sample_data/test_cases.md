# ZTA Runtime Test Checks

## Executive (`executive@local.test`)

Query: `Give me campus aggregate KPI summary.`
Expected: Allowed. Aggregate campus response only.

Query: `Show average enrollment across sampled institutions.`
Expected: Allowed. Aggregate enrollment response only.

Query: `Show raw student records.`
Expected: Blocked or no matching data. Executive access is aggregate-only.

Query: `Show finance records summary.`
Expected: Blocked. Executive does not have finance domain access.

## Admissions Admin (`admissions@local.test`)

Query: `Show open admissions coverage across sampled campuses.`
Expected: Allowed. Admissions-scope aggregate response.

Query: `Give me admissions KPI summary for institutions in scope.`
Expected: Allowed. Admissions-only data should be returned.

Query: `Give me campus aggregate KPI summary.`
Expected: Blocked. Admissions admin is not an executive aggregate persona.

Query: `Show finance records summary.`
Expected: Blocked. Cross-domain finance access should be denied.

## IT Head (`ithead@local.test`)

Query: `Give me campus aggregate KPI summary.`
Expected: Blocked. IT Head is restricted to admin operations, not chat data access.

Admin action: `GET /admin/data-sources`
Expected: Allowed.

Admin action: `GET /admin/audit-log`
Expected: Allowed.
