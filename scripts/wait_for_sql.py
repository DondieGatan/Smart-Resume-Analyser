"""Poll the configured Postgres database until it accepts connections, or
give up after ~3 minutes. Used by CI to wait for the postgres service
container to finish starting before the schema-setup steps try to connect."""
import sys
import time

import psycopg
from config import Config

MAX_ATTEMPTS = 60
DELAY_SECONDS = 3


def main():
    dsn = Config.DATABASE_URL
    if dsn.startswith('postgres://'):
        dsn = dsn.replace('postgres://', 'postgresql://', 1)
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            conn = psycopg.connect(dsn, connect_timeout=5)
            conn.close()
            print(f'Postgres is up after {attempt} attempt(s) (~{attempt * DELAY_SECONDS}s).')
            return 0
        except Exception as e:
            last_error = e
            if attempt == 1 or attempt % 5 == 0:
                print(f'attempt {attempt}/{MAX_ATTEMPTS}: not ready yet ({type(e).__name__}: {e})')
            time.sleep(DELAY_SECONDS)
    print(f'::error::Postgres did not become ready within {MAX_ATTEMPTS * DELAY_SECONDS}s. Last error: {last_error}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
