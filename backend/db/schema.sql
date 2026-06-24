CREATE TYPE job_status AS ENUM ('pending', 'processing', 'done', 'failed');

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status job_status DEFAULT 'pending',
    processing_key TEXT,
    input_file_url TEXT,
    job_type TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    retry_count INT DEFAULT 0,
    progress INT DEFAULT 0,
    user_id UUID
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);