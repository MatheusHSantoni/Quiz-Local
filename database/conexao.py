import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "database.db"

def conectar():
    return sqlite3.connect(CAMINHO_BANCO)