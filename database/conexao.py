import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "database.db"

def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao