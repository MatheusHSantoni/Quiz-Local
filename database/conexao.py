import os
import psycopg
from psycopg.rows import dict_row

def conectar():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("A variável DATABASE_URL não foi configurada.")

    return psycopg.connect(database_url, row_factory=dict_row)