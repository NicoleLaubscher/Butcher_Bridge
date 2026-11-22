"""Shared MySQL connection management. Never stores connection secrets in Git."""
import os
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor


def connection():
    required = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError('Missing database settings: ' + ', '.join(missing) + '. Copy .env.example to .env.')
    options = dict(host=os.environ['DB_HOST'], port=int(os.getenv('DB_PORT', '3306')),
                   user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                   database=os.environ['DB_NAME'], charset='utf8mb4', cursorclass=DictCursor,
                   autocommit=False, connect_timeout=10)
    if os.getenv('DB_SSL_CA'):
        options['ssl'] = {'ca': os.environ['DB_SSL_CA']}
        options['ssl_verify_cert'] = True
        options['ssl_verify_identity'] = True
    elif os.getenv('APP_ENV') == 'production':
        raise RuntimeError('Production DB connections require DB_SSL_CA for verified TLS.')
    return pymysql.connect(**options)

@contextmanager
def transaction():
    conn = connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql, params=()):
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


@contextmanager
def read_snapshot():
    """Materialise consistent InnoDB reads without opening a write transaction."""
    conn = connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")

            def read(sql):
                cur.execute(sql)
                return tuple(cur.fetchall())

            yield read
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
