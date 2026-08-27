-- ============================================================
-- NexaConsult Global â€” Synthetic Enterprise Database
-- Modelled after a large professional services firm (Accenture-like)
-- Schema: enterprise_demo
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- 1. DEPARTMENTS / SERVICE LINES
-- ============================================================
CREATE TABLE departments (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    service_line    TEXT NOT NULL,
    practice        TEXT,
    region          TEXT NOT NULL,
    head_employee_id TEXT,
    cost_center     TEXT,
    created_at      TEXT NOT NULL
);

INSERT INTO departments VALUES
('DEPT-001','Technology Consulting','Technology','Cloud & Infrastructure','North America','EMP-001','CC-1001','2018-01-01'),
('DEPT-002','Strategy & Consulting','Strategy','Digital Strategy','North America','EMP-010','CC-1002','2018-01-01'),
('DEPT-003','Interactive / UX','Interactive','Experience Design','Europe','EMP-020','CC-1003','2019-03-01'),
('DEPT-004','Operations','Operations','Supply Chain','APAC','EMP-030','CC-1004','2018-01-01'),
('DEPT-005','Security Services','Technology','Cybersecurity','North America','EMP-040','CC-1005','2020-06-01'),
('DEPT-006','Data & AI','Technology','Applied Intelligence','North America','EMP-050','CC-1006','2021-01-01'),
('DEPT-007','Finance Consulting','Strategy','CFO & Enterprise Value','Europe','EMP-060','CC-1007','2018-01-01'),
('DEPT-008','HR & Talent','Operations','Talent & Organization','LATAM','EMP-070','CC-1008','2019-01-01');

-- ============================================================
-- 2. EMPLOYEES
-- ============================================================
CREATE TABLE employees (
    id                  TEXT PRIMARY KEY,
    employee_code       TEXT UNIQUE NOT NULL,
    first_name          TEXT NOT NULL,
    last_name           TEXT NOT NULL,
    email               TEXT UNIQUE NOT NULL,
    phone               TEXT,
    grade               TEXT NOT NULL,
    title               TEXT NOT NULL,
    department_id       TEXT REFERENCES departments(id),
    manager_id          TEXT,
    hire_date           TEXT NOT NULL,
    location_city       TEXT NOT NULL,
    location_country    TEXT NOT NULL,
    employment_type     TEXT NOT NULL,
    base_salary         REAL,
    currency            TEXT DEFAULT 'USD',
    utilization_target  REAL DEFAULT 0.80,
    status              TEXT DEFAULT 'ACTIVE',
    created_at          TEXT NOT NULL
);

INSERT INTO employees VALUES
('EMP-001','NC10001','Priya','Sharma','p.sharma@nexaconsult.com','+1-212-555-0101','MD','Managing Director','DEPT-001',NULL,'2015-03-15','New York','USA','FULL_TIME',320000,'USD',0.70,'ACTIVE','2015-03-15'),
('EMP-002','NC10002','James','Holloway','j.holloway@nexaconsult.com','+1-212-555-0102','SM','Senior Manager','DEPT-001','EMP-001','2017-07-10','New York','USA','FULL_TIME',195000,'USD',0.80,'ACTIVE','2017-07-10'),
('EMP-003','NC10003','Chen','Liu','c.liu@nexaconsult.com','+1-415-555-0103','C','Consultant','DEPT-001','EMP-002','2020-09-01','San Francisco','USA','FULL_TIME',110000,'USD',0.85,'ACTIVE','2020-09-01'),
('EMP-004','NC10004','Aisha','Patel','a.patel@nexaconsult.com','+1-415-555-0104','AC','Analyst Consultant','DEPT-001','EMP-002','2022-07-15','San Francisco','USA','FULL_TIME',85000,'USD',0.85,'ACTIVE','2022-07-15'),
('EMP-005','NC10005','Luca','Romano','l.romano@nexaconsult.com','+1-312-555-0105','C','Consultant','DEPT-001','EMP-002','2021-01-10','Chicago','USA','FULL_TIME',108000,'USD',0.85,'ACTIVE','2021-01-10'),
('EMP-010','NC10010','Sofia','Andersen','s.andersen@nexaconsult.com','+1-646-555-0110','MD','Managing Director','DEPT-002',NULL,'2014-06-01','New York','USA','FULL_TIME',330000,'USD',0.70,'ACTIVE','2014-06-01'),
('EMP-011','NC10011','Marcus','Webb','m.webb@nexaconsult.com','+1-646-555-0111','SM','Senior Manager','DEPT-002','EMP-010','2016-11-20','New York','USA','FULL_TIME',200000,'USD',0.80,'ACTIVE','2016-11-20'),
('EMP-012','NC10012','Yuki','Tanaka','y.tanaka@nexaconsult.com','+81-3-555-0112','M','Manager','DEPT-002','EMP-011','2019-04-01','Tokyo','Japan','FULL_TIME',14500000,'JPY',0.82,'ACTIVE','2019-04-01'),
('EMP-013','NC10013','Fatima','Al-Hassan','f.alhassan@nexaconsult.com','+44-20-555-0113','C','Consultant','DEPT-002','EMP-011','2021-09-06','London','UK','FULL_TIME',72000,'GBP',0.85,'ACTIVE','2021-09-06'),
('EMP-020','NC10020','Elise','Fontaine','e.fontaine@nexaconsult.com','+33-1-555-0120','M','Manager','DEPT-003',NULL,'2019-02-11','Paris','France','FULL_TIME',88000,'EUR',0.80,'ACTIVE','2019-02-11'),
('EMP-021','NC10021','Daniel','Osei','d.osei@nexaconsult.com','+44-20-555-0121','C','Consultant','DEPT-003','EMP-020','2022-03-07','London','UK','FULL_TIME',65000,'GBP',0.85,'ACTIVE','2022-03-07'),
('EMP-030','NC10030','Rajesh','Iyer','r.iyer@nexaconsult.com','+91-22-555-0130','SM','Senior Manager','DEPT-004',NULL,'2018-08-20','Mumbai','India','FULL_TIME',4200000,'INR',0.82,'ACTIVE','2018-08-20'),
('EMP-031','NC10031','Wei','Zhang','w.zhang@nexaconsult.com','+86-21-555-0131','C','Consultant','DEPT-004','EMP-030','2021-06-14','Shanghai','China','FULL_TIME',520000,'CNY',0.85,'ACTIVE','2021-06-14'),
('EMP-040','NC10040','Michael','Torres','m.torres@nexaconsult.com','+1-703-555-0140','SM','Senior Manager','DEPT-005',NULL,'2017-04-03','Washington DC','USA','FULL_TIME',210000,'USD',0.80,'ACTIVE','2017-04-03'),
('EMP-041','NC10041','Nora','Eriksson','n.eriksson@nexaconsult.com','+46-8-555-0141','C','Consultant','DEPT-005','EMP-040','2023-02-01','Stockholm','Sweden','FULL_TIME',720000,'SEK',0.85,'ACTIVE','2023-02-01'),
('EMP-050','NC10050','Amara','Diallo','a.diallo@nexaconsult.com','+1-617-555-0150','M','Manager','DEPT-006',NULL,'2020-11-09','Boston','USA','FULL_TIME',165000,'USD',0.82,'ACTIVE','2020-11-09'),
('EMP-051','NC10051','Kevin','Park','k.park@nexaconsult.com','+1-617-555-0151','AC','Analyst Consultant','DEPT-006','EMP-050','2023-07-17','Boston','USA','FULL_TIME',90000,'USD',0.85,'ACTIVE','2023-07-17'),
('EMP-060','NC10060','Helena','Brandt','h.brandt@nexaconsult.com','+49-30-555-0160','MD','Managing Director','DEPT-007',NULL,'2013-05-22','Berlin','Germany','FULL_TIME',280000,'EUR',0.70,'ACTIVE','2013-05-22'),
('EMP-061','NC10061','Pablo','Reyes','p.reyes@nexaconsult.com','+34-91-555-0161','M','Manager','DEPT-007','EMP-060','2018-10-15','Madrid','Spain','FULL_TIME',90000,'EUR',0.82,'ACTIVE','2018-10-15'),
('EMP-070','NC10070','Carmen','Silva','c.silva@nexaconsult.com','+55-11-555-0170','M','Manager','DEPT-008',NULL,'2019-05-30','Sao Paulo','Brazil','FULL_TIME',380000,'BRL',0.80,'ACTIVE','2019-05-30');

-- ============================================================
-- 3. SKILLS MATRIX
-- ============================================================
CREATE TABLE employee_skills (
    id              TEXT PRIMARY KEY,
    employee_id     TEXT REFERENCES employees(id),
    skill           TEXT NOT NULL,
    category        TEXT NOT NULL,
    proficiency     TEXT NOT NULL,  -- BEGINNER | INTERMEDIATE | ADVANCED | EXPERT
    certified       INTEGER DEFAULT 0,
    last_used_date  TEXT
);

INSERT INTO employee_skills VALUES
('SKL-001','EMP-001','Cloud Architecture','Technical','EXPERT',1,'2024-08-01'),
('SKL-002','EMP-001','AWS','Technical','EXPERT',1,'2024-08-01'),
('SKL-003','EMP-001','Client Management','Business','EXPERT',0,'2024-08-01'),
('SKL-004','EMP-002','Kubernetes','Technical','ADVANCED',1,'2024-07-15'),
('SKL-005','EMP-002','DevOps','Technical','ADVANCED',1,'2024-07-15'),
('SKL-006','EMP-003','Python','Technical','ADVANCED',0,'2024-08-10'),
('SKL-007','EMP-003','Terraform','Technical','INTERMEDIATE',1,'2024-06-01'),
('SKL-008','EMP-004','Java','Technical','INTERMEDIATE',0,'2024-07-20'),
('SKL-009','EMP-005','Azure','Technical','ADVANCED',1,'2024-08-05'),
('SKL-010','EMP-010','Digital Strategy','Business','EXPERT',0,'2024-08-01'),
('SKL-011','EMP-011','Change Management','Business','ADVANCED',0,'2024-07-01'),
('SKL-012','EMP-012','Agile','Technical','ADVANCED',1,'2024-07-01'),
('SKL-013','EMP-013','Data Analysis','Technical','INTERMEDIATE',0,'2024-06-15'),
('SKL-014','EMP-020','UX Research','Design','ADVANCED',0,'2024-08-01'),
('SKL-015','EMP-020','Figma','Design','EXPERT',0,'2024-08-01'),
('SKL-016','EMP-021','UI Development','Technical','ADVANCED',0,'2024-07-25'),
('SKL-017','EMP-030','Supply Chain','Operations','EXPERT',0,'2024-08-01'),
('SKL-018','EMP-040','Penetration Testing','Security','EXPERT',1,'2024-08-01'),
('SKL-019','EMP-040','SIEM','Security','EXPERT',1,'2024-08-01'),
('SKL-020','EMP-050','Machine Learning','Technical','ADVANCED',1,'2024-08-01'),
('SKL-021','EMP-050','Python','Technical','EXPERT',0,'2024-08-01'),
('SKL-022','EMP-051','Data Engineering','Technical','INTERMEDIATE',0,'2024-07-01');

-- ============================================================
-- 4. CLIENTS (ACCOUNTS)
-- ============================================================
CREATE TABLE clients (
    id              TEXT PRIMARY KEY,
    client_code     TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    industry        TEXT NOT NULL,
    segment         TEXT NOT NULL,   -- ENTERPRISE | MID_MARKET | SMB | PUBLIC_SECTOR
    region          TEXT NOT NULL,
    country         TEXT NOT NULL,
    account_owner_id TEXT REFERENCES employees(id),
    annual_revenue_usd REAL,
    relationship_start TEXT,
    status          TEXT DEFAULT 'ACTIVE',
    created_at      TEXT NOT NULL
);

INSERT INTO clients VALUES
('CLI-001','NC-ACC-001','Apex Financial Group','Financial Services','ENTERPRISE','North America','USA','EMP-010',48000000000,'2016-03-01','ACTIVE','2016-03-01'),
('CLI-002','NC-ACC-002','Meridian Health Systems','Healthcare','ENTERPRISE','North America','USA','EMP-001',12000000000,'2018-07-15','ACTIVE','2018-07-15'),
('CLI-003','NC-ACC-003','GlobalLogix','Manufacturing','ENTERPRISE','Europe','Germany','EMP-060',8500000000,'2017-09-01','ACTIVE','2017-09-01'),
('CLI-004','NC-ACC-004','TerraEnergy Corp','Energy','ENTERPRISE','North America','Canada','EMP-011',22000000000,'2019-01-10','ACTIVE','2019-01-10'),
('CLI-005','NC-ACC-005','AsiaPacific Retail','Retail','MID_MARKET','APAC','Singapore','EMP-030',1200000000,'2020-04-01','ACTIVE','2020-04-01'),
('CLI-006','NC-ACC-006','Ministry of Digital Affairs','Government','PUBLIC_SECTOR','Europe','UK','EMP-040',NULL,'2021-06-15','ACTIVE','2021-06-15'),
('CLI-007','NC-ACC-007','VeloTech Mobility','Technology','MID_MARKET','Europe','France','EMP-020',450000000,'2022-02-01','ACTIVE','2022-02-01'),
('CLI-008','NC-ACC-008','BancSur','Financial Services','ENTERPRISE','LATAM','Brazil','EMP-061',5800000000,'2020-11-01','ACTIVE','2020-11-01'),
('CLI-009','NC-ACC-009','NovaBio Pharma','Life Sciences','ENTERPRISE','North America','USA','EMP-050',3100000000,'2023-03-01','ACTIVE','2023-03-01'),
('CLI-010','NC-ACC-010','StarPort Logistics','Transportation','MID_MARKET','APAC','Japan','EMP-012',780000000,'2021-08-20','ACTIVE','2021-08-20');

-- ============================================================
-- 5. PROJECTS / ENGAGEMENTS
-- ============================================================
CREATE TABLE projects (
    id                  TEXT PRIMARY KEY,
    project_code        TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    client_id           TEXT REFERENCES clients(id),
    department_id       TEXT REFERENCES departments(id),
    project_type        TEXT NOT NULL,  -- IMPLEMENTATION | ADVISORY | MANAGED_SERVICE | ASSESSMENT
    status              TEXT NOT NULL,  -- ACTIVE | COMPLETED | ON_HOLD | CANCELLED
    lead_employee_id    TEXT REFERENCES employees(id),
    start_date          TEXT NOT NULL,
    end_date            TEXT,
    planned_end_date    TEXT,
    contract_value_usd  REAL,
    budget_usd          REAL,
    actual_spend_usd    REAL DEFAULT 0,
    delivery_model      TEXT,           -- ON_SITE | REMOTE | HYBRID
    region              TEXT,
    sow_reference       TEXT,
    created_at          TEXT NOT NULL
);

INSERT INTO projects VALUES
('PROJ-001','NC-P-2022-001','Apex Cloud Transformation','CLI-001','DEPT-001','IMPLEMENTATION','COMPLETED','EMP-002','2022-01-15','2023-06-30','2023-06-30',4800000,5000000,4650000,'HYBRID','North America','SOW-2022-001','2022-01-15'),
('PROJ-002','NC-P-2022-002','Meridian EHR Modernization','CLI-002','DEPT-001','IMPLEMENTATION','ACTIVE','EMP-002','2022-09-01',NULL,'2024-12-31',7200000,7500000,3100000,'ON_SITE','North America','SOW-2022-002','2022-09-01'),
('PROJ-003','NC-P-2023-001','GlobalLogix Digital Strategy','CLI-003','DEPT-002','ADVISORY','COMPLETED','EMP-011','2023-02-01','2023-10-31','2023-10-31',1200000,1200000,1180000,'REMOTE','Europe','SOW-2023-001','2023-02-01'),
('PROJ-004','NC-P-2023-002','TerraEnergy AI Analytics Platform','CLI-004','DEPT-006','IMPLEMENTATION','ACTIVE','EMP-050','2023-07-01',NULL,'2025-06-30',5500000,6000000,2200000,'HYBRID','North America','SOW-2023-002','2023-07-01'),
('PROJ-005','NC-P-2023-003','AsiaPacific Retail Omnichannel','CLI-005','DEPT-003','IMPLEMENTATION','ACTIVE','EMP-020','2023-05-15',NULL,'2024-11-30',980000,1000000,520000,'REMOTE','APAC','SOW-2023-003','2023-05-15'),
('PROJ-006','NC-P-2023-004','UK MOD Digital Passport','CLI-006','DEPT-005','IMPLEMENTATION','ACTIVE','EMP-040','2023-10-01',NULL,'2025-03-31',8900000,9000000,1800000,'ON_SITE','Europe','SOW-2023-004','2023-10-01'),
('PROJ-007','NC-P-2024-001','VeloTech UX Redesign','CLI-007','DEPT-003','ADVISORY','ACTIVE','EMP-020','2024-01-10',NULL,'2024-09-30',420000,450000,280000,'REMOTE','Europe','SOW-2024-001','2024-01-10'),
('PROJ-008','NC-P-2024-002','BancSur Core Banking Upgrade','CLI-008','DEPT-007','IMPLEMENTATION','ACTIVE','EMP-061','2024-03-01',NULL,'2025-12-31',11000000,12000000,1900000,'HYBRID','LATAM','SOW-2024-002','2024-03-01'),
('PROJ-009','NC-P-2024-003','NovaBio AI Drug Discovery Platform','CLI-009','DEPT-006','IMPLEMENTATION','ACTIVE','EMP-050','2024-04-15',NULL,'2026-04-14',9800000,10000000,2100000,'HYBRID','North America','SOW-2024-003','2024-04-15'),
('PROJ-010','NC-P-2024-004','StarPort Logistics Automation','CLI-010','DEPT-004','IMPLEMENTATION','ACTIVE','EMP-030','2024-02-20',NULL,'2025-08-31',2300000,2500000,680000,'REMOTE','APAC','SOW-2024-004','2024-02-20'),
('PROJ-011','NC-P-2021-001','Apex Cybersecurity Assessment','CLI-001','DEPT-005','ASSESSMENT','COMPLETED','EMP-040','2021-03-01','2021-09-30','2021-09-30',650000,650000,620000,'ON_SITE','North America','SOW-2021-001','2021-03-01'),
('PROJ-012','NC-P-2022-003','GlobalLogix Supply Chain Resilience','CLI-003','DEPT-004','ADVISORY','COMPLETED','EMP-030','2022-06-01','2023-01-31','2023-01-31',820000,900000,810000,'HYBRID','Europe','SOW-2022-003','2022-06-01');

-- ============================================================
-- 6. PROJECT ALLOCATIONS
-- ============================================================
CREATE TABLE project_allocations (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id),
    employee_id     TEXT REFERENCES employees(id),
    role            TEXT NOT NULL,
    allocation_pct  REAL NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT,
    billing_rate    REAL,
    currency        TEXT DEFAULT 'USD',
    status          TEXT DEFAULT 'ACTIVE'
);

INSERT INTO project_allocations VALUES
('ALLOC-001','PROJ-001','EMP-002','Delivery Lead',100,'2022-01-15','2023-06-30',250,'USD','COMPLETED'),
('ALLOC-002','PROJ-001','EMP-003','Cloud Architect',100,'2022-01-15','2023-06-30',195,'USD','COMPLETED'),
('ALLOC-003','PROJ-001','EMP-004','Junior Consultant',80,'2022-03-01','2023-06-30',150,'USD','COMPLETED'),
('ALLOC-004','PROJ-002','EMP-002','Delivery Lead',50,'2022-09-01',NULL,250,'USD','ACTIVE'),
('ALLOC-005','PROJ-002','EMP-005','Integration Architect',100,'2022-09-01',NULL,185,'USD','ACTIVE'),
('ALLOC-006','PROJ-002','EMP-004','Consultant',20,'2023-01-01',NULL,150,'USD','ACTIVE'),
('ALLOC-007','PROJ-003','EMP-011','Strategy Lead',80,'2023-02-01','2023-10-31',280,'USD','COMPLETED'),
('ALLOC-008','PROJ-003','EMP-013','Consultant',100,'2023-02-01','2023-10-31',160,'USD','COMPLETED'),
('ALLOC-009','PROJ-004','EMP-050','AI Lead',100,'2023-07-01',NULL,295,'USD','ACTIVE'),
('ALLOC-010','PROJ-004','EMP-051','Data Engineer',100,'2023-07-01',NULL,165,'USD','ACTIVE'),
('ALLOC-011','PROJ-005','EMP-020','Design Lead',80,'2023-05-15',NULL,220,'USD','ACTIVE'),
('ALLOC-012','PROJ-005','EMP-021','UI Consultant',100,'2023-05-15',NULL,170,'USD','ACTIVE'),
('ALLOC-013','PROJ-006','EMP-040','Security Lead',100,'2023-10-01',NULL,310,'USD','ACTIVE'),
('ALLOC-014','PROJ-006','EMP-041','Security Consultant',100,'2023-10-01',NULL,175,'USD','ACTIVE'),
('ALLOC-015','PROJ-009','EMP-050','AI Architect',50,'2024-04-15',NULL,295,'USD','ACTIVE'),
('ALLOC-016','PROJ-009','EMP-051','ML Engineer',100,'2024-04-15',NULL,175,'USD','ACTIVE');

-- ============================================================
-- 7. REVENUE
-- ============================================================
CREATE TABLE revenue (
    id              TEXT PRIMARY KEY,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    project_id      TEXT REFERENCES projects(id),
    department_id   TEXT REFERENCES departments(id),
    client_id       TEXT REFERENCES clients(id),
    revenue_usd     REAL NOT NULL,
    revenue_type    TEXT NOT NULL,    -- RECOGNIZED | BILLED | BACKLOG
    currency        TEXT DEFAULT 'USD',
    fx_rate         REAL DEFAULT 1.0,
    created_at      TEXT NOT NULL
);

INSERT INTO revenue VALUES
('REV-001','2022-01-01','2022-03-31','PROJ-001','DEPT-001','CLI-001',480000,'RECOGNIZED','USD',1.0,'2022-04-05'),
('REV-002','2022-04-01','2022-06-30','PROJ-001','DEPT-001','CLI-001',560000,'RECOGNIZED','USD',1.0,'2022-07-05'),
('REV-003','2022-07-01','2022-09-30','PROJ-001','DEPT-001','CLI-001',620000,'RECOGNIZED','USD',1.0,'2022-10-05'),
('REV-004','2022-10-01','2022-12-31','PROJ-001','DEPT-001','CLI-001',710000,'RECOGNIZED','USD',1.0,'2023-01-05'),
('REV-005','2023-01-01','2023-03-31','PROJ-001','DEPT-001','CLI-001',800000,'RECOGNIZED','USD',1.0,'2023-04-05'),
('REV-006','2023-04-01','2023-06-30','PROJ-001','DEPT-001','CLI-001',680000,'RECOGNIZED','USD',1.0,'2023-07-05'),
('REV-007','2022-10-01','2022-12-31','PROJ-002','DEPT-001','CLI-002',400000,'RECOGNIZED','USD',1.0,'2023-01-05'),
('REV-008','2023-01-01','2023-03-31','PROJ-002','DEPT-001','CLI-002',520000,'RECOGNIZED','USD',1.0,'2023-04-05'),
('REV-009','2023-04-01','2023-06-30','PROJ-002','DEPT-001','CLI-002',610000,'RECOGNIZED','USD',1.0,'2023-07-05'),
('REV-010','2023-07-01','2023-09-30','PROJ-002','DEPT-001','CLI-002',590000,'RECOGNIZED','USD',1.0,'2023-10-05'),
('REV-011','2023-10-01','2023-12-31','PROJ-002','DEPT-001','CLI-002',630000,'RECOGNIZED','USD',1.0,'2024-01-05'),
('REV-012','2024-01-01','2024-03-31','PROJ-002','DEPT-001','CLI-002',700000,'RECOGNIZED','USD',1.0,'2024-04-05'),
('REV-013','2023-02-01','2023-06-30','PROJ-003','DEPT-002','CLI-003',620000,'RECOGNIZED','USD',1.0,'2023-07-05'),
('REV-014','2023-07-01','2023-10-31','PROJ-003','DEPT-002','CLI-003',560000,'RECOGNIZED','USD',1.0,'2023-11-05'),
('REV-015','2023-07-01','2023-09-30','PROJ-004','DEPT-006','CLI-004',420000,'RECOGNIZED','USD',1.0,'2023-10-05'),
('REV-016','2023-10-01','2023-12-31','PROJ-004','DEPT-006','CLI-004',580000,'RECOGNIZED','USD',1.0,'2024-01-05'),
('REV-017','2024-01-01','2024-03-31','PROJ-004','DEPT-006','CLI-004',650000,'RECOGNIZED','USD',1.0,'2024-04-05'),
('REV-018','2024-04-01','2024-06-30','PROJ-004','DEPT-006','CLI-004',550000,'RECOGNIZED','USD',1.0,'2024-07-05'),
('REV-019','2023-06-01','2023-09-30','PROJ-005','DEPT-003','CLI-005',280000,'RECOGNIZED','USD',1.0,'2023-10-05'),
('REV-020','2023-10-01','2023-12-31','PROJ-005','DEPT-003','CLI-005',240000,'RECOGNIZED','USD',1.0,'2024-01-05'),
('REV-021','2024-01-01','2024-06-30','PROJ-005','DEPT-003','CLI-005',310000,'RECOGNIZED','USD',1.0,'2024-07-05'),
('REV-022','2024-01-01','2024-03-31','PROJ-006','DEPT-005','CLI-006',900000,'RECOGNIZED','USD',1.0,'2024-04-05'),
('REV-023','2024-04-01','2024-06-30','PROJ-006','DEPT-005','CLI-006',900000,'RECOGNIZED','USD',1.0,'2024-07-05'),
('REV-024','2024-01-01','2024-03-31','PROJ-007','DEPT-003','CLI-007',140000,'RECOGNIZED','USD',1.0,'2024-04-05'),
('REV-025','2024-04-01','2024-06-30','PROJ-007','DEPT-003','CLI-007',140000,'RECOGNIZED','USD',1.0,'2024-07-05'),
('REV-026','2024-03-01','2024-06-30','PROJ-008','DEPT-007','CLI-008',950000,'RECOGNIZED','USD',1.0,'2024-07-05'),
('REV-027','2024-04-01','2024-06-30','PROJ-009','DEPT-006','CLI-009',700000,'RECOGNIZED','USD',1.0,'2024-07-05');

-- ============================================================
-- 8. TIMESHEETS
-- ============================================================
CREATE TABLE timesheets (
    id              TEXT PRIMARY KEY,
    employee_id     TEXT REFERENCES employees(id),
    project_id      TEXT REFERENCES projects(id),
    week_start      TEXT NOT NULL,
    billable_hours  REAL DEFAULT 0,
    non_billable_hours REAL DEFAULT 0,
    overtime_hours  REAL DEFAULT 0,
    status          TEXT DEFAULT 'SUBMITTED',  -- DRAFT | SUBMITTED | APPROVED | REJECTED
    approved_by     TEXT REFERENCES employees(id),
    submitted_at    TEXT,
    approved_at     TEXT
);

INSERT INTO timesheets VALUES
('TS-001','EMP-003','PROJ-001','2023-06-05',40,0,0,'APPROVED','EMP-002','2023-06-08','2023-06-09'),
('TS-002','EMP-003','PROJ-001','2023-06-12',40,0,0,'APPROVED','EMP-002','2023-06-15','2023-06-16'),
('TS-003','EMP-004','PROJ-002','2024-07-29',32,0,5,'APPROVED','EMP-002','2024-08-01','2024-08-02'),
('TS-004','EMP-004','PROJ-002','2024-08-05',32,0,0,'SUBMITTED','EMP-002','2024-08-08',NULL),
('TS-005','EMP-050','PROJ-004','2024-08-05',40,0,8,'SUBMITTED','EMP-001','2024-08-08',NULL),
('TS-006','EMP-051','PROJ-004','2024-08-05',40,0,0,'SUBMITTED','EMP-050','2024-08-08',NULL),
('TS-007','EMP-020','PROJ-005','2024-08-05',32,0,0,'SUBMITTED','EMP-010','2024-08-08',NULL),
('TS-008','EMP-040','PROJ-006','2024-08-05',40,0,10,'SUBMITTED','EMP-001','2024-08-08',NULL),
('TS-009','EMP-005','PROJ-002','2024-08-05',40,0,2,'SUBMITTED','EMP-002','2024-08-08',NULL),
('TS-010','EMP-050','PROJ-009','2024-08-05',20,5,0,'SUBMITTED','EMP-001','2024-08-08',NULL);

-- ============================================================
-- 9. EXPENSES
-- ============================================================
CREATE TABLE expenses (
    id              TEXT PRIMARY KEY,
    employee_id     TEXT REFERENCES employees(id),
    project_id      TEXT REFERENCES projects(id),
    expense_date    TEXT NOT NULL,
    category        TEXT NOT NULL,   -- TRAVEL | ACCOMMODATION | MEALS | SOFTWARE | HARDWARE | OTHER
    amount          REAL NOT NULL,
    currency        TEXT DEFAULT 'USD',
    description     TEXT,
    status          TEXT DEFAULT 'PENDING',  -- PENDING | APPROVED | REJECTED | REIMBURSED
    approved_by     TEXT REFERENCES employees(id),
    reimbursed_at   TEXT
);

INSERT INTO expenses VALUES
('EXP-001','EMP-003','PROJ-001','2023-05-10','TRAVEL',1850,'USD','Flight NYC to client site LA','REIMBURSED','EMP-002','2023-05-25'),
('EXP-002','EMP-003','PROJ-001','2023-05-11','ACCOMMODATION',320,'USD','Hotel - 2 nights LA','REIMBURSED','EMP-002','2023-05-25'),
('EXP-003','EMP-040','PROJ-006','2024-08-01','TRAVEL',920,'GBP','Train London to Birmingham client site','PENDING',NULL,NULL),
('EXP-004','EMP-040','PROJ-006','2024-08-01','ACCOMMODATION',280,'GBP','Hotel Birmingham - 2 nights','PENDING',NULL,NULL),
('EXP-005','EMP-050','PROJ-004','2024-07-15','SOFTWARE',3500,'USD','Azure ML compute subscription - July','APPROVED','EMP-001',NULL),
('EXP-006','EMP-020','PROJ-005','2024-06-20','TRAVEL',2200,'USD','Flight Paris to Singapore','APPROVED','EMP-010',NULL),
('EXP-007','EMP-030','PROJ-010','2024-07-01','MEALS',85,'USD','Client lunch - StarPort team','APPROVED','EMP-001',NULL),
('EXP-008','EMP-002','PROJ-002','2024-07-25','TRAVEL',620,'USD','Flight NYC to client HQ Boston','APPROVED','EMP-001',NULL);

-- ============================================================
-- 10. INVOICES & TRANSACTIONS
-- ============================================================
CREATE TABLE invoices (
    id              TEXT PRIMARY KEY,
    invoice_number  TEXT UNIQUE NOT NULL,
    client_id       TEXT REFERENCES clients(id),
    project_id      TEXT REFERENCES projects(id),
    issue_date      TEXT NOT NULL,
    due_date        TEXT NOT NULL,
    amount_usd      REAL NOT NULL,
    status          TEXT DEFAULT 'SENT',  -- DRAFT | SENT | PAID | OVERDUE | CANCELLED
    paid_date       TEXT,
    created_at      TEXT NOT NULL
);

INSERT INTO invoices VALUES
('INV-001','NC-INV-2022-0001','CLI-001','PROJ-001','2022-04-01','2022-05-01',480000,'PAID','2022-04-28','2022-04-01'),
('INV-002','NC-INV-2022-0002','CLI-001','PROJ-001','2022-07-01','2022-08-01',560000,'PAID','2022-07-29','2022-07-01'),
('INV-003','NC-INV-2022-0003','CLI-001','PROJ-001','2022-10-01','2022-11-01',620000,'PAID','2022-10-30','2022-10-01'),
('INV-004','NC-INV-2023-0001','CLI-001','PROJ-001','2023-01-01','2023-02-01',710000,'PAID','2023-01-27','2023-01-01'),
('INV-005','NC-INV-2023-0002','CLI-002','PROJ-002','2023-01-15','2023-02-15',400000,'PAID','2023-02-14','2023-01-15'),
('INV-006','NC-INV-2023-0003','CLI-002','PROJ-002','2023-04-15','2023-05-15',520000,'PAID','2023-05-10','2023-04-15'),
('INV-007','NC-INV-2024-0001','CLI-002','PROJ-002','2024-04-15','2024-05-15',700000,'PAID','2024-05-13','2024-04-15'),
('INV-008','NC-INV-2024-0002','CLI-004','PROJ-004','2024-04-01','2024-05-01',650000,'PAID','2024-04-30','2024-04-01'),
('INV-009','NC-INV-2024-0003','CLI-004','PROJ-004','2024-07-01','2024-08-01',550000,'SENT',NULL,'2024-07-01'),
('INV-010','NC-INV-2024-0004','CLI-006','PROJ-006','2024-07-01','2024-08-01',900000,'OVERDUE',NULL,'2024-07-01'),
('INV-011','NC-INV-2024-0005','CLI-009','PROJ-009','2024-07-15','2024-08-15',700000,'SENT',NULL,'2024-07-15'),
('INV-012','NC-INV-2024-0006','CLI-008','PROJ-008','2024-07-01','2024-08-01',950000,'SENT',NULL,'2024-07-01');

-- ============================================================
-- 11. SUPPORT TICKETS (Internal Helpdesk)
-- ============================================================
CREATE TABLE support_tickets (
    id              TEXT PRIMARY KEY,
    ticket_number   TEXT UNIQUE NOT NULL,
    raised_by_id    TEXT REFERENCES employees(id),
    assigned_to_id  TEXT REFERENCES employees(id),
    department_id   TEXT REFERENCES departments(id),
    project_id      TEXT REFERENCES projects(id),
    category        TEXT NOT NULL,    -- IT | HR | FINANCE | LEGAL | FACILITIES | DATA
    priority        TEXT NOT NULL,    -- LOW | MEDIUM | HIGH | CRITICAL
    subject         TEXT NOT NULL,
    description     TEXT,
    status          TEXT DEFAULT 'OPEN',  -- OPEN | IN_PROGRESS | RESOLVED | CLOSED
    created_at      TEXT NOT NULL,
    resolved_at     TEXT,
    sla_hours       INTEGER
);

INSERT INTO support_tickets VALUES
('TKT-001','NC-TKT-2024-001','EMP-004','EMP-040','DEPT-005',NULL,'IT','HIGH','VPN access failing on client site','Cannot connect to VPN from Meridian HQ. Need urgent fix.','RESOLVED','2024-07-15','2024-07-15',4),
('TKT-002','NC-TKT-2024-002','EMP-051','EMP-050','DEPT-006','PROJ-004','DATA','MEDIUM','Azure ML quota exceeded','Hitting compute quota on Azure ML workspace for TerraEnergy project.','IN_PROGRESS','2024-08-01',NULL,24),
('TKT-003','NC-TKT-2024-003','EMP-041','EMP-040','DEPT-005','PROJ-006','IT','CRITICAL','Security incident - suspicious login detected','Unauthorized login attempt detected on MOD project environment.','RESOLVED','2024-08-05','2024-08-05',1),
('TKT-004','NC-TKT-2024-004','EMP-013','EMP-070','DEPT-008',NULL,'HR','LOW','Update to leave balance','Requesting correction to annual leave balance after maternity leave return.','OPEN','2024-08-10',NULL,72),
('TKT-005','NC-TKT-2024-005','EMP-003','EMP-060','DEPT-007',NULL,'FINANCE','MEDIUM','Expense reimbursement delayed','EXP-001 and EXP-002 from May not yet reimbursed.','CLOSED','2024-05-30','2024-06-02',48),
('TKT-006','NC-TKT-2024-006','EMP-020','EMP-070','DEPT-008','PROJ-005','HR','MEDIUM','Travel policy clarification for APAC trip','Need guidance on per diem allowances for Singapore travel.','RESOLVED','2024-06-15','2024-06-16',24);

-- ============================================================
-- 12. OKRs / KPIs
-- ============================================================
CREATE TABLE okrs (
    id              TEXT PRIMARY KEY,
    period          TEXT NOT NULL,     -- e.g. 'Q3-2024'
    department_id   TEXT REFERENCES departments(id),
    objective       TEXT NOT NULL,
    key_result      TEXT NOT NULL,
    target_value    REAL,
    actual_value    REAL,
    unit            TEXT,
    status          TEXT DEFAULT 'ON_TRACK',  -- ON_TRACK | AT_RISK | OFF_TRACK | ACHIEVED | MISSED
    owner_id        TEXT REFERENCES employees(id),
    created_at      TEXT NOT NULL
);

INSERT INTO okrs VALUES
('OKR-001','Q3-2024','DEPT-001','Grow Cloud Practice Revenue','Recognized Revenue from Cloud projects','3500000',2800000,'USD','AT_RISK','EMP-002','2024-07-01'),
('OKR-002','Q3-2024','DEPT-001','Improve Team Utilization','Average billable utilization across practice','0.83',0.81,'ratio','ON_TRACK','EMP-001','2024-07-01'),
('OKR-003','Q3-2024','DEPT-006','Launch AI Accelerator Framework','Complete internal framework and pilot on 2 projects','2',1,'count','ON_TRACK','EMP-050','2024-07-01'),
('OKR-004','Q3-2024','DEPT-006','Grow Data & AI Revenue','Recognized Revenue from D&AI projects','2000000',1250000,'USD','ON_TRACK','EMP-050','2024-07-01'),
('OKR-005','Q3-2024','DEPT-005','Zero Critical Security Incidents','Critical incidents unresolved beyond SLA','0',0,'count','ACHIEVED','EMP-040','2024-07-01'),
('OKR-006','Q2-2024','DEPT-002','Strategy Practice Win Rate','New project win rate from proposals','0.40',0.38,'ratio','AT_RISK','EMP-011','2024-04-01'),
('OKR-007','Q3-2024','DEPT-007','BancSur Milestone Delivery','Complete Phase 1 of BancSur core banking on time','1',0,'count','ON_TRACK','EMP-061','2024-07-01'),
('OKR-008','Q3-2024','DEPT-003','Client CSAT Score','Average CSAT score from Q3 project surveys','4.5',4.3,'score_out_of_5','ON_TRACK','EMP-020','2024-07-01');

-- ============================================================
-- 13. PERFORMANCE REVIEWS
-- ============================================================
CREATE TABLE performance_reviews (
    id              TEXT PRIMARY KEY,
    employee_id     TEXT REFERENCES employees(id),
    reviewer_id     TEXT REFERENCES employees(id),
    review_period   TEXT NOT NULL,
    overall_rating  TEXT NOT NULL,   -- EXCEEDS | MEETS | BELOW | UNSATISFACTORY
    technical_score INTEGER,
    delivery_score  INTEGER,
    leadership_score INTEGER,
    comments        TEXT,
    promotion_eligible INTEGER DEFAULT 0,
    completed_at    TEXT NOT NULL
);

INSERT INTO performance_reviews VALUES
('PRV-001','EMP-003','EMP-002','2023-H2','EXCEEDS',5,5,4,'Outstanding delivery on Apex Cloud project. Ready for Senior Consultant promotion.',1,'2024-01-15'),
('PRV-002','EMP-004','EMP-002','2023-H2','MEETS',4,4,3,'Good work on Meridian project. Needs to improve client communication skills.',0,'2024-01-15'),
('PRV-003','EMP-051','EMP-050','2023-H2','MEETS',4,3,3,'Strong ML engineering skills. Needs to improve documentation practices.',0,'2024-01-20'),
('PRV-004','EMP-013','EMP-011','2023-H2','EXCEEDS',4,5,4,'Excellent client relationship management on GlobalLogix engagement.',1,'2024-01-18'),
('PRV-005','EMP-041','EMP-040','2023-H2','MEETS',4,4,3,'Solid security consulting work. Should pursue OSCP certification.',0,'2024-01-20'),
('PRV-006','EMP-021','EMP-020','2023-H2','EXCEEDS',5,4,4,'Exceptional UX design output. Led successful AsiaPacific retail design sprint.',1,'2024-01-22'),
('PRV-007','EMP-031','EMP-030','2023-H2','MEETS',3,4,3,'Good delivery on supply chain work. Technical skills need upskilling in automation tools.',0,'2024-01-25');

-- ============================================================
-- 14. CONVERSATIONS (for Chat DB / RAG demos)
-- ============================================================
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    client_id       TEXT REFERENCES clients(id),
    project_id      TEXT REFERENCES projects(id),
    employee_id     TEXT REFERENCES employees(id),
    channel         TEXT NOT NULL,   -- EMAIL | TEAMS | SLACK | PHONE | IN_PERSON
    subject         TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    access_level    TEXT DEFAULT 'INTERNAL'  -- INTERNAL | CLIENT_FACING | CONFIDENTIAL
);

CREATE TABLE conversation_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    sender_type     TEXT NOT NULL,   -- EMPLOYEE | CLIENT | SYSTEM
    sender_id       TEXT,
    message_text    TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    sensitivity     TEXT DEFAULT 'NONE'  -- NONE | POTENTIAL_PII | SENSITIVE
);

INSERT INTO conversations VALUES
('CONV-001','CLI-001','PROJ-001','EMP-002','TEAMS','Apex Cloud Transformation - Weekly Status','2023-06-05 10:00:00','2023-06-05 11:00:00','CLIENT_FACING'),
('CONV-002','CLI-002','PROJ-002','EMP-002','EMAIL','Meridian EHR - Phase 2 Scope Discussion','2024-07-20 09:00:00','2024-07-20 09:30:00','CLIENT_FACING'),
('CONV-003',NULL,NULL,'EMP-050','SLACK','Data & AI Practice - Standup','2024-08-05 09:00:00','2024-08-05 09:15:00','INTERNAL'),
('CONV-004','CLI-006','PROJ-006','EMP-040','IN_PERSON','MOD Security Review - Incident Debrief','2024-08-05 14:00:00','2024-08-05 16:00:00','CONFIDENTIAL');

INSERT INTO conversation_messages VALUES
('MSG-001','CONV-001','EMPLOYEE','EMP-002','Good morning team. Status update: Migration of Apex core services to AWS us-east-1 is 85% complete. Remaining items: IAM policy review and final smoke tests. On track for June 30 cutover.','2023-06-05 10:02:00','NONE'),
('MSG-002','CONV-001','CLIENT','CLI-001-CONTACT','Thanks James. Are there any risks to the June 30 date we should be aware of?','2023-06-05 10:05:00','NONE'),
('MSG-003','CONV-001','EMPLOYEE','EMP-002','One minor risk: the legacy Oracle adapter needs a patch from the vendor. We have a workaround ready if the patch does not arrive by June 25.','2023-06-05 10:08:00','NONE'),
('MSG-004','CONV-002','EMPLOYEE','EMP-002','Following our call, I want to confirm scope for Phase 2: integration with Epic EHR, patient portal redesign, and HIPAA compliance certification. Budget estimate is .8M additional.','2024-07-20 09:05:00','SENSITIVE'),
('MSG-005','CONV-002','CLIENT','CLI-002-CONTACT','Confirmed. We will need the HIPAA certification complete before go-live. Please include that in the SOW amendment.','2024-07-20 09:12:00','SENSITIVE'),
('MSG-006','CONV-003','EMPLOYEE','EMP-050','AI Accelerator Framework update: pilot on TerraEnergy is showing 34% reduction in model inference time after optimization. Starting NovaBio pilot next week.','2024-08-05 09:03:00','NONE'),
('MSG-007','CONV-003','EMPLOYEE','EMP-051','Confirmed. NovaBio data pipeline is ready. First model training run scheduled for Aug 12.','2024-08-05 09:06:00','NONE'),
('MSG-008','CONV-004','EMPLOYEE','EMP-040','Security incident TKT-003 confirmed as a credential stuffing attack against one non-privileged account. Account isolated, password reset, 2FA enforced. No data exfiltration detected.','2024-08-05 14:15:00','SENSITIVE');

-- ============================================================
-- 15. SERVICES / PRODUCTS CATALOG
-- ============================================================
CREATE TABLE service_catalog (
    id              TEXT PRIMARY KEY,
    service_code    TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    department_id   TEXT REFERENCES departments(id),
    day_rate_usd    REAL,
    description     TEXT,
    active          INTEGER DEFAULT 1
);

INSERT INTO service_catalog VALUES
('SVC-001','NC-SVC-001','Cloud Migration & Modernization','Technology','DEPT-001',2200,'End-to-end cloud migration advisory and implementation services.',1),
('SVC-002','NC-SVC-002','Enterprise AI & ML Platform','Technology','DEPT-006',2800,'Design and build of enterprise-grade AI and machine learning platforms.',1),
('SVC-003','NC-SVC-003','Digital Strategy Advisory','Strategy','DEPT-002',2600,'Senior-led digital transformation strategy and roadmap development.',1),
('SVC-004','NC-SVC-004','UX & Experience Design','Interactive','DEPT-003',1800,'User research, UX design, and digital product design services.',1),
('SVC-005','NC-SVC-005','Cybersecurity Assessment & MSSP','Technology','DEPT-005',2500,'Penetration testing, security architecture review, and managed security.',1),
('SVC-006','NC-SVC-006','Supply Chain Optimization','Operations','DEPT-004',2000,'Supply chain analysis, resilience planning, and automation.',1),
('SVC-007','NC-SVC-007','Finance Transformation','Strategy','DEPT-007',2400,'CFO advisory, finance modernization, and ERP implementation.',1),
('SVC-008','NC-SVC-008','Talent & Organization','Operations','DEPT-008',1900,'Change management, org design, and talent strategy.',1);

-- ============================================================
-- 16. USEFUL VIEWS for SQL query demos
-- ============================================================

CREATE VIEW v_project_financials AS
SELECT
    p.project_code,
    p.name AS project_name,
    c.name AS client_name,
    p.status,
    p.contract_value_usd,
    p.budget_usd,
    p.actual_spend_usd,
    ROUND((p.actual_spend_usd / NULLIF(p.budget_usd, 0)) * 100, 1) AS budget_consumed_pct,
    COALESCE(SUM(r.revenue_usd), 0) AS total_recognized_revenue,
    p.start_date,
    p.planned_end_date
FROM projects p
JOIN clients c ON c.id = p.client_id
LEFT JOIN revenue r ON r.project_id = p.id AND r.revenue_type = 'RECOGNIZED'
GROUP BY p.id, p.project_code, p.name, c.name, p.status,
         p.contract_value_usd, p.budget_usd, p.actual_spend_usd,
         p.start_date, p.planned_end_date;

CREATE VIEW v_employee_utilization AS
SELECT
    e.employee_code,
    e.first_name || ' ' || e.last_name AS full_name,
    e.grade,
    e.title,
    d.name AS department,
    COALESCE(SUM(t.billable_hours), 0) AS total_billable_hours,
    COALESCE(SUM(t.non_billable_hours), 0) AS total_non_billable_hours,
    COALESCE(SUM(t.overtime_hours), 0) AS total_overtime_hours,
    e.utilization_target
FROM employees e
JOIN departments d ON d.id = e.department_id
LEFT JOIN timesheets t ON t.employee_id = e.id
WHERE e.status = 'ACTIVE'
GROUP BY e.id, e.employee_code, e.first_name, e.last_name,
         e.grade, e.title, d.name, e.utilization_target;

CREATE VIEW v_department_revenue_summary AS
SELECT
    d.name AS department,
    d.service_line,
    r.period_start,
    r.period_end,
    SUM(r.revenue_usd) AS total_revenue_usd,
    COUNT(DISTINCT r.project_id) AS project_count
FROM revenue r
JOIN departments d ON d.id = r.department_id
GROUP BY d.id, d.name, d.service_line, r.period_start, r.period_end;

CREATE VIEW v_overdue_invoices AS
SELECT
    i.invoice_number,
    c.name AS client_name,
    p.name AS project_name,
    i.issue_date,
    i.due_date,
    i.amount_usd,
    i.status,
    julianday('now') - julianday(i.due_date) AS days_overdue
FROM invoices i
JOIN clients c ON c.id = i.client_id
JOIN projects p ON p.id = i.project_id
WHERE i.status IN ('OVERDUE', 'SENT')
  AND i.due_date < date('now');

CREATE VIEW v_active_project_team AS
SELECT
    p.project_code,
    p.name AS project_name,
    c.name AS client_name,
    e.first_name || ' ' || e.last_name AS employee_name,
    e.grade,
    a.role,
    a.allocation_pct,
    a.billing_rate,
    a.billing_rate * a.allocation_pct / 100 AS effective_daily_rate
FROM project_allocations a
JOIN projects p ON p.id = a.project_id
JOIN employees e ON e.id = a.employee_id
JOIN clients c ON c.id = p.client_id
WHERE a.status = 'ACTIVE' AND p.status = 'ACTIVE';
