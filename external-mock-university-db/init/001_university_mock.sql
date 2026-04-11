-- Mock University Dataset (external to ZTA runtime)
-- This database is intentionally separate so tenant admins can connect it from UI.

CREATE TABLE IF NOT EXISTS departments (
  department_id text PRIMARY KEY,
  department_name text NOT NULL
);

CREATE TABLE IF NOT EXISTS user_directory (
  user_id text PRIMARY KEY,
  email text NOT NULL UNIQUE,
  full_name text NOT NULL,
  persona text NOT NULL,
  department_id text REFERENCES departments(department_id),
  admin_function text,
  owner_external_id text,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
  course_id text PRIMARY KEY,
  course_name text NOT NULL,
  department_id text NOT NULL REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS enrollments (
  enrollment_id text PRIMARY KEY,
  student_user_id text NOT NULL REFERENCES user_directory(user_id),
  course_id text NOT NULL REFERENCES courses(course_id),
  term text NOT NULL,
  grade_point numeric(4,2),
  attendance_percent numeric(5,2),
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fee_ledger (
  fee_id text PRIMARY KEY,
  student_user_id text NOT NULL REFERENCES user_directory(user_id),
  term text NOT NULL,
  total_due numeric(12,2) NOT NULL,
  paid_amount numeric(12,2) NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

-- Connector-ready table for ZTA SQL source type.
CREATE TABLE IF NOT EXISTS claims (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  domain text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  owner_id text,
  department_id text,
  course_id text,
  admin_function text,
  claim_key text NOT NULL,
  value_text text,
  value_number double precision,
  value_json jsonb,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

INSERT INTO departments (department_id, department_name) VALUES
  ('cse', 'Computer Science and Engineering'),
  ('ece', 'Electronics and Communication Engineering'),
  ('admin', 'University Administration')
ON CONFLICT (department_id) DO NOTHING;

INSERT INTO user_directory (user_id, email, full_name, persona, department_id, admin_function, owner_external_id) VALUES
  ('usr-admin-001', 'tenant.admin@college1.com', 'Tenant Admin', 'it_head', 'admin', NULL, 'ADM-001'),
  ('usr-dean-001', 'dean@college1.com', 'Dean', 'executive', 'admin', NULL, 'EXE-001'),
  ('usr-hod-001', 'hod.cse@college1.com', 'CSE Department Head', 'dept_head', 'cse', NULL, 'HOD-001'),
  ('usr-adm-001', 'admissions@college1.com', 'Admissions Office', 'admin_staff', 'admin', 'admissions', 'ADM-101'),
  ('usr-fin-001', 'finance@college1.com', 'Finance Office', 'admin_staff', 'admin', 'finance', 'FIN-101'),
  ('usr-hr-001', 'hr@college1.com', 'HR Office', 'admin_staff', 'admin', 'hr', 'HR-101'),
  ('usr-exm-001', 'exam@college1.com', 'Exam Office', 'admin_staff', 'admin', 'exam', 'EXM-101')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_directory (user_id, email, full_name, persona, department_id, owner_external_id)
SELECT
  'usr-fac-' || lpad(gs::text, 3, '0'),
  'faculty' || gs::text || '@college1.com',
  'Faculty ' || gs::text,
  'faculty',
  CASE WHEN gs % 2 = 0 THEN 'ece' ELSE 'cse' END,
  'FAC-' || lpad(gs::text, 3, '0')
FROM generate_series(1, 5) gs
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_directory (user_id, email, full_name, persona, department_id, owner_external_id)
SELECT
  'usr-stu-' || lpad(gs::text, 3, '0'),
  'student' || gs::text || '@college1.com',
  'Student ' || gs::text,
  'student',
  CASE WHEN gs % 2 = 0 THEN 'ece' ELSE 'cse' END,
  'STU-' || lpad(gs::text, 3, '0')
FROM generate_series(1, 10) gs
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO courses (course_id, course_name, department_id) VALUES
  ('CSE101', 'Data Structures', 'cse'),
  ('CSE201', 'Database Systems', 'cse'),
  ('ECE101', 'Signals and Systems', 'ece'),
  ('ECE201', 'Digital Communication', 'ece')
ON CONFLICT (course_id) DO NOTHING;

INSERT INTO enrollments (enrollment_id, student_user_id, course_id, term, grade_point, attendance_percent)
SELECT
  'enr-' || lpad(gs::text, 4, '0'),
  'usr-stu-' || lpad(((gs - 1) % 10 + 1)::text, 3, '0'),
  CASE WHEN gs % 2 = 0 THEN 'CSE101' ELSE 'ECE101' END,
  '2026-S1',
  6.50 + ((gs % 20) * 0.12),
  82.00 + ((gs % 10) * 1.50)
FROM generate_series(1, 20) gs
ON CONFLICT (enrollment_id) DO NOTHING;

INSERT INTO fee_ledger (fee_id, student_user_id, term, total_due, paid_amount, status)
SELECT
  'fee-' || lpad(gs::text, 4, '0'),
  'usr-stu-' || lpad(gs::text, 3, '0'),
  '2026-S1',
  120000,
  CASE WHEN gs % 3 = 0 THEN 120000 ELSE 90000 END,
  CASE WHEN gs % 3 = 0 THEN 'paid' ELSE 'partial' END
FROM generate_series(1, 10) gs
ON CONFLICT (fee_id) DO NOTHING;

-- Replace this value with the tenant_id returned by /system-admin/tenants.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM claims LIMIT 1) THEN
    INSERT INTO claims (id, tenant_id, domain, entity_type, entity_id, claim_key, value_number, value_text)
    VALUES
      ('clm-academic-count', 'REPLACE_WITH_ZTA_TENANT_ID', 'academic', 'records', 'academic-overview', 'record_count', 120, NULL),
      ('clm-academic-status', 'REPLACE_WITH_ZTA_TENANT_ID', 'academic', 'records', 'academic-overview', 'status_summary', NULL, 'Academic outcomes are stable'),
      ('clm-finance-count', 'REPLACE_WITH_ZTA_TENANT_ID', 'finance', 'records', 'finance-overview', 'record_count', 40, NULL),
      ('clm-finance-status', 'REPLACE_WITH_ZTA_TENANT_ID', 'finance', 'records', 'finance-overview', 'status_summary', NULL, 'Fee collection at 91 percent'),
      ('clm-campus-count', 'REPLACE_WITH_ZTA_TENANT_ID', 'campus', 'records', 'campus-overview', 'record_count', 22, NULL),
      ('clm-campus-status', 'REPLACE_WITH_ZTA_TENANT_ID', 'campus', 'records', 'campus-overview', 'status_summary', NULL, 'Campus ops healthy'),
      ('clm-admin-count', 'REPLACE_WITH_ZTA_TENANT_ID', 'admin', 'records', 'admin-overview', 'record_count', 14, NULL),
      ('clm-admin-status', 'REPLACE_WITH_ZTA_TENANT_ID', 'admin', 'records', 'admin-overview', 'status_summary', NULL, 'Security controls green');
  END IF;
END$$;

CREATE OR REPLACE FUNCTION rebind_claims_tenant(new_tenant_id text)
RETURNS void
LANGUAGE sql
AS $$
  UPDATE claims SET tenant_id = new_tenant_id;
$$;
