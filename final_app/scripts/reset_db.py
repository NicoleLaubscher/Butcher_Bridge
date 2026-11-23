"""Rebuild the schema and seed data from nothing. Development/test databases only."""
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.constants import CLIENT

load_dotenv()
if '--yes' not in sys.argv or os.getenv('APP_ENV') == 'production':
    sys.exit('Refusing to run: pass --yes and never use against production.')

conn = pymysql.connect(host=os.environ['DB_HOST'], port=int(os.getenv('DB_PORT', '3306')),
                       user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                       client_flag=CLIENT.MULTI_STATEMENTS, autocommit=True)
sql_dir = Path(__file__).resolve().parent.parent / 'sql'
with conn.cursor() as cur:
    cur.execute(f"DROP DATABASE IF EXISTS `{os.environ['DB_NAME']}`")
    for name in ('schema.sql', 'seed.sql'):
        cur.execute((sql_dir / name).read_text(encoding='utf-8'))
        while cur.nextset():
            pass
conn.close()
print('Database rebuilt.')