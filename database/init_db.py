import sqlite3 
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "database.db"

def criar_banco():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_dupla TEXT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS perguntas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enunciado TEXT NOT NULL,
            alternativa_a TEXT NOT NULL,
            alternativa_b TEXT NOT NULL,
            alternativa_c TEXT NOT NULL,
            alternativa_d TEXT NOT NULL,
            alternativa_correta TEXT NOT NULL
        )""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dupla_id INTEGER NOT NULL,
            pergunta_id INTEGER NOT NULL,
            alternativa_escolhida TEXT NOT NULL,
            respondida_em DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (dupla_id) REFERENCES duplas(id),
            FOREIGN KEY (pergunta_id) REFERENCES perguntas(id),

            UNIQUE (dupla_id, pergunta_id)
        )""")
    
    conexao.commit()
    conexao.close()

if __name__ == "__main__":
    criar_banco()
    print("Banco criado com sucesso.")