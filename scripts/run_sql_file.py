"""Run a .sql script against the database configured in config.py, via
psycopg. Used by CI to set up a fresh schema — not needed for local dev
against the shared Neon project, where the schema already exists.

Usage: python scripts/run_sql_file.py setup_db.sql [setup_users_table.sql ...]
"""
import sys
import psycopg
from config import Config


def run_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    dsn = Config.DATABASE_URL
    if dsn.startswith('postgres://'):
        dsn = dsn.replace('postgres://', 'postgresql://', 1)
    conn = psycopg.connect(dsn, options=f"-c search_path={Config.DB_SCHEMA}", autocommit=True)
    cursor = conn.cursor()
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{Config.DB_SCHEMA}"')
    try:
        cursor.execute(content)
    except psycopg.Error as e:
        print(f'--- {path} failed ---\n{content}\n--- error: {e}')
        raise
    cursor.close()
    conn.close()
    print(f'Ran {path}.')


if __name__ == '__main__':
    for sql_path in sys.argv[1:]:
        run_file(sql_path)
