-- Care-LifeLine M2 初始化建表（Postgres）
-- 由 `make compose-up` 起 Postgres 后执行；CI/本地测试用 SQLite 走 db.engine.init_db 自动建表。

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

CREATE TABLE IF NOT EXISTS citations (
    id            SERIAL PRIMARY KEY,
    message_id    INTEGER REFERENCES messages(id),
    source        VARCHAR(255) NOT NULL,
    snippet       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qc_rules (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(64) NOT NULL UNIQUE,
    description   VARCHAR(255) NOT NULL,
    severity      VARCHAR(32) NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1
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
