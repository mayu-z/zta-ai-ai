# Sample Queries and Expected Behavior

## Student (student@campusa.edu)

Query: `What is my attendance percentage this semester?`
Expected: Allowed. Returns template-filled values for `STU-4821` only.

Query: `Show attendance for STU-9001`
Expected: Blocked at interpreter student self-scope guard.

## Faculty (faculty@campusa.edu)

Query: `Show attendance for my courses`
Expected: Allowed. Compiler injects `course_ids IN [CSE101, CSE102]`.

## Dept Head (head.cse@campusa.edu)

Query: `Summarize department attendance`
Expected: Allowed. Compiler injects `department_id = CSE`.

## Admin Staff Finance (finance.admin@campusa.edu)

Query: `Show finance records summary`
Expected: Allowed with `admin_function = finance` scope.

## Executive (dean@campusa.edu)

Query: `Give me campus KPI summary`
Expected: Allowed aggregate-only output.

## IT Head (it.head@campusa.edu)

Query: `Show student attendance`
Expected: Blocked. IT Head is admin-only and has no business data chat access.
