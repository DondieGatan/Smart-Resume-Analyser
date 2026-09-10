-- Run against the schema named by DB_SCHEMA (see config.py / setup_db.sql).
-- Kept in sync with models.py's init_users_table(), which is what actually
-- runs this at app startup — this file is a manual/reference copy.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    reset_token VARCHAR(255) NULL,
    reset_token_expiry TIMESTAMP NULL
);
