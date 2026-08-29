-- Care-LifeLine M2 初始化建表（Postgres）
-- 由 `make compose-up` 起 Postgres 后执行；CI/本地测试用 SQLite 走 db.engine.init_db 自动建表。
-- schema v3（2026-08-29）：纵向记忆三表加双时间轴（valid_from/valid_to）与溯源
-- （provenance/source_session_id，ADR-0018）；已有旧库需重建（dev 为种子数据可重生成）。

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role          VARCHAR(32) NOT NULL DEFAULT 'patient',
    display_name  VARCHAR(64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patients (
    id            SERIAL PRIMARY KEY,
    external_id   VARCHAR(64),
    name          VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS sessions (
    id            SERIAL PRIMARY KEY,
    thread_id     VARCHAR(64) NOT NULL UNIQUE,
    user_id       INTEGER REFERENCES users(id),
    title         VARCHAR(255),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_sessions_thread_id ON sessions(thread_id);

CREATE TABLE IF NOT EXISTS messages (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    role          VARCHAR(32) NOT NULL,
    content       TEXT NOT NULL,
    citations     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS qc_rules (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(64) NOT NULL UNIQUE,
    description   VARCHAR(255) NOT NULL,
    severity      VARCHAR(32) NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS qc_hits (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER REFERENCES sessions(id),
    message_id    INTEGER REFERENCES messages(id),
    rule_code     VARCHAR(64) NOT NULL,
    severity      VARCHAR(32) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER REFERENCES sessions(id),
    event         VARCHAR(64) NOT NULL,
    detail        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patient_metrics (
    id            SERIAL PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    name          VARCHAR(64) NOT NULL,
    value         DOUBLE PRECISION NOT NULL,
    unit          VARCHAR(32),
    measured_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_patient_metrics_patient ON patient_metrics(patient_id);

CREATE TABLE IF NOT EXISTS patient_medications (
    id                 SERIAL PRIMARY KEY,
    patient_id         INTEGER NOT NULL REFERENCES patients(id),
    name               VARCHAR(64) NOT NULL,
    dosage             VARCHAR(64),
    frequency          VARCHAR(64),
    provenance         VARCHAR(16) NOT NULL DEFAULT 'user',
    source_session_id  INTEGER REFERENCES sessions(id),
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to           TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_patient_medications_patient ON patient_medications(patient_id);

CREATE TABLE IF NOT EXISTS patient_allergies (
    id                 SERIAL PRIMARY KEY,
    patient_id         INTEGER NOT NULL REFERENCES patients(id),
    allergen           VARCHAR(64) NOT NULL,
    reaction           VARCHAR(128),
    severity           VARCHAR(16) NOT NULL DEFAULT 'moderate',
    provenance         VARCHAR(16) NOT NULL DEFAULT 'user',
    source_session_id  INTEGER REFERENCES sessions(id),
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to           TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_patient_allergies_patient ON patient_allergies(patient_id);

CREATE TABLE IF NOT EXISTS patient_followups (
    id                 SERIAL PRIMARY KEY,
    patient_id         INTEGER NOT NULL REFERENCES patients(id),
    plan               VARCHAR(255) NOT NULL,
    due_date           TIMESTAMPTZ,
    status             VARCHAR(16) NOT NULL DEFAULT 'pending',
    provenance         VARCHAR(16) NOT NULL DEFAULT 'user',
    source_session_id  INTEGER REFERENCES sessions(id),
    valid_from         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to           TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_patient_followups_patient ON patient_followups(patient_id);

CREATE TABLE IF NOT EXISTS memory_proposals (
    id            SERIAL PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    thread_id     VARCHAR(64),
    kind          VARCHAR(16) NOT NULL,
    action        VARCHAR(16) NOT NULL DEFAULT 'add',
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    excerpt       TEXT,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    decided_by    VARCHAR(64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_memory_proposals_patient ON memory_proposals(patient_id);
CREATE INDEX IF NOT EXISTS ix_memory_proposals_status ON memory_proposals(status);

CREATE TABLE IF NOT EXISTS hitl_reviews (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    thread_id       VARCHAR(64) NOT NULL,
    input_text      TEXT NOT NULL,
    draft           TEXT NOT NULL,
    qc_json         TEXT NOT NULL DEFAULT '{}',
    violations_json TEXT NOT NULL DEFAULT '[]',
    patient_context TEXT,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    reviewer        VARCHAR(64),
    decision        VARCHAR(16),
    corrected_text  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_hitl_reviews_status ON hitl_reviews(status);

CREATE TABLE IF NOT EXISTS proactive_reminders (
    id            SERIAL PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    metric        VARCHAR(64) NOT NULL,
    message       TEXT NOT NULL,
    severity      VARCHAR(16) NOT NULL DEFAULT 'info',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proactive_reminders_patient ON proactive_reminders(patient_id);
