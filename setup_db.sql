-- Smart Resume Analyser database schema for Postgres (Neon free tier).
-- Run this against the schema named by DB_SCHEMA (see config.py) — the
-- connection's search_path must already point there (models.py's
-- get_db_connection() does this via `options=-c search_path=<schema>`),
-- so table names below are deliberately unqualified.

CREATE TABLE IF NOT EXISTS resumes (
    id SERIAL PRIMARY KEY,
    user_id INT NULL,
    candidate_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    filename VARCHAR(255) NOT NULL,
    raw_text TEXT,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    resume_id INT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    skill_name VARCHAR(100) NOT NULL,
    category VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS education (
    id SERIAL PRIMARY KEY,
    resume_id INT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    degree VARCHAR(255),
    institution VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS experience (
    id SERIAL PRIMARY KEY,
    resume_id INT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    title VARCHAR(255),
    company VARCHAR(255),
    description TEXT
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id SERIAL PRIMARY KEY,
    resume_id INT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    overall_score INT DEFAULT 0,
    skills_score INT DEFAULT 0,
    education_score INT DEFAULT 0,
    experience_score INT DEFAULT 0,
    formatting_score INT DEFAULT 0,
    recommended_field VARCHAR(100),
    recommendations TEXT,
    analysed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP VIEW IF EXISTS resume_dashboard;

CREATE VIEW resume_dashboard AS
SELECT
    r.id,
    r.user_id,
    r.candidate_name,
    r.email,
    r.upload_date,
    ar.overall_score,
    ar.skills_score,
    ar.education_score,
    ar.experience_score,
    ar.formatting_score,
    ar.recommended_field,
    (SELECT COUNT(*) FROM skills s WHERE s.resume_id = r.id) AS total_skills
FROM resumes r
LEFT JOIN analysis_results ar ON ar.resume_id = r.id;
