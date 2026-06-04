CREATE TYPE job_status AS ENUM ('pending', 'processing', 'done', 'failed');

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status job_status DEFAULT 'pending',
    input_file_url TEXT,
    output_file_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    retry_count INT DEFAULT 0,
    user_id UUID
);