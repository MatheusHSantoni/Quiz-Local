import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "database.db"


def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA busy_timeout = 10000")
    conexao.execute("PRAGMA journal_mode = WAL")
    return conexao
