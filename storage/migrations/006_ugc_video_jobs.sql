-- UGC video generation job tracking with per-step status

CREATE TABLE IF NOT EXISTS ugc_video_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    topic TEXT NOT NULL,
    platform TEXT NOT NULL,
    duration TEXT DEFAULT '5',
    status TEXT DEFAULT 'pending',
    -- Step statuses: pending | running | complete | failed
    frame_status TEXT DEFAULT 'pending',
    frame_path TEXT,
    video_status TEXT DEFAULT 'pending',
    video_task_id TEXT,
    video_path TEXT,
    tts_status TEXT DEFAULT 'pending',
    tts_path TEXT,
    lipsync_status TEXT DEFAULT 'pending',
    lipsync_task_id TEXT,
    lipsync_path TEXT,
    assembly_status TEXT DEFAULT 'pending',
    final_path TEXT,
    -- Metadata
    influencer_key TEXT,
    motion_prompt TEXT,
    voiceover_script TEXT,
    angle_json TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    run_dir TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ugc_jobs_status ON ugc_video_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ugc_jobs_job_id ON ugc_video_jobs(job_id);
