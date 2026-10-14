import sqlite3
import secrets
from pathlib import Path


CAMINHO_BANCO = Path(__file__).parent / "database.db"


def coluna_existe(cursor, tabela, coluna):
    cursor.execute(f"PRAGMA table_info({tabela})")
    colunas = cursor.fetchall()

    return any(
        coluna_info[1] == coluna
        for coluna_info in colunas)


def gerar_codigo_acesso(cursor):
    while True:
        codigo = str(secrets.randbelow(9000) + 1000)

        cursor.execute(
            """
            SELECT id
            FROM duplas
            WHERE codigo_acesso = ?
            """,
            (codigo,))

        codigo_existente = cursor.fetchone()
        if codigo_existente is None:
            return codigo


def atualizar_duplas_existentes(cursor):
    cursor.execute(
        """
        SELECT
            id,
            nome_dupla,
            codigo_acesso
        FROM duplas
        """)

    duplas = cursor.fetchall()

    for dupla in duplas:
        dupla_id = dupla[0]
        nome_dupla = dupla[1]
        codigo_acesso = dupla[2]

        if not nome_dupla:
            nome_dupla = f"Dupla {dupla_id}"
        if not codigo_acesso:
            codigo_acesso = gerar_codigo_acesso(
                cursor)

        cursor.execute(
            """
            UPDATE duplas
            SET
                nome_dupla = ?,
                codigo_acesso = ?
            WHERE id = ?
            """,
            (
                nome_dupla,
                codigo_acesso,
                dupla_id
            ))


def criar_banco():
    conexao = sqlite3.connect(
        CAMINHO_BANCO)

    cursor = conexao.cursor()
    cursor.execute(
        """
        PRAGMA foreign_keys = ON
        """)


    # DUPLAS
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS duplas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_dupla TEXT NOT NULL,
            participante_1 TEXT NOT NULL,
            participante_2 TEXT NOT NULL,
            codigo_acesso TEXT NOT NULL UNIQUE,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)


    # Migração para bancos antigos
    if not coluna_existe(cursor,"duplas","nome_dupla"):
        cursor.execute(
            """
            ALTER TABLE duplas
            ADD COLUMN nome_dupla TEXT
            """)

    if not coluna_existe(
        cursor,
        "duplas",
        "codigo_acesso"):
        cursor.execute(
            """
            ALTER TABLE duplas
            ADD COLUMN codigo_acesso TEXT
            """)


    # Preenche as duplas que já existiam
    atualizar_duplas_existentes(cursor)
    # Garante que códigos não possam se repetir
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_duplas_codigo_acesso
        ON duplas(codigo_acesso)
        """)

    # PERGUNTAS

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS perguntas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enunciado TEXT NOT NULL,
            alternativa_a TEXT NOT NULL,
            alternativa_b TEXT NOT NULL,
            alternativa_c TEXT NOT NULL,
            alternativa_d TEXT NOT NULL,
            alternativa_e TEXT NOT NULL,
            alternativa_correta TEXT NOT NULL
        )""")

    # RESPOSTAS

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS respostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dupla_id INTEGER NOT NULL,
            pergunta_id INTEGER NOT NULL,
            alternativa_escolhida TEXT NOT NULL,
            correta INTEGER NOT NULL,
            pontos INTEGER NOT NULL DEFAULT 0,
            respondida_em DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (dupla_id)
                REFERENCES duplas(id),

            FOREIGN KEY (pergunta_id)
                REFERENCES perguntas(id),

            UNIQUE (
                dupla_id,
                pergunta_id
            ))""")

# CONFIGURAÇÕES

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            ranking_liberado INTEGER NOT NULL DEFAULT 0
        )""")
    cursor.execute(
        """
        INSERT OR IGNORE INTO configuracoes (
            id,
            ranking_liberado)
        VALUES (1, 0)
        """)


    conexao.commit()
    conexao.close()

if __name__ == "__main__":
    criar_banco()

    print("Banco atualizado com sucesso.")