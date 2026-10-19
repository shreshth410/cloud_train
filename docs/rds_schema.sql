-- ============================================================================
-- CloudTrain Relational Database Schema (PostgreSQL 16)
-- Synopsis reference architecture for optional RDS / Aurora deployment (S5)
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'UPLOADING',
    profile_json JSONB,
    error_code VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_datasets_user_status ON datasets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_datasets_created ON datasets(created_at DESC);

CREATE TABLE IF NOT EXISTS jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    dataset_id VARCHAR(64) NOT NULL REFERENCES datasets(dataset_id),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    stage VARCHAR(64) NOT NULL DEFAULT 'QUEUED',
    progress INT NOT NULL DEFAULT 0,
    compute_size VARCHAR(16) NOT NULL DEFAULT 'small',
    instance_id VARCHAR(64),
    config_json JSONB NOT NULL,
    metrics_summary JSONB,
    error_code VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INT
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_dataset ON jobs(dataset_id);

CREATE TABLE IF NOT EXISTS job_events (
    event_id BIGSERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    seq INT NOT NULL,
    stage VARCHAR(64) NOT NULL,
    progress INT NOT NULL,
    message TEXT,
    metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_job_seq UNIQUE (job_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_seq ON job_events(job_id, seq ASC);
