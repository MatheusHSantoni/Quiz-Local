import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "database.db"


def _colunas(cursor, tabela):
    return {linha[1] for linha in cursor.execute(f"PRAGMA table_info({tabela})").fetchall()}


def _adicionar_coluna(cursor, tabela, definicao):
    nome = definicao.split()[0]
    if nome not in _colunas(cursor, tabela):
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {definicao}")


def criar_banco():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participante_1 TEXT NOT NULL,
            participante_2 TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
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
            alternativa_e TEXT NOT NULL,
            alternativa_correta TEXT NOT NULL
        )""")
    _adicionar_coluna(cursor, "perguntas", "area TEXT NOT NULL DEFAULT 'LC'")
    _adicionar_coluna(cursor, "perguntas", "tipo TEXT NOT NULL DEFAULT 'PRINCIPAL'")
    _adicionar_coluna(cursor, "perguntas", "ordem INTEGER NOT NULL DEFAULT 1")
    _adicionar_coluna(cursor, "perguntas", "ativa INTEGER NOT NULL DEFAULT 1")
    _adicionar_coluna(cursor, "perguntas", "imagem TEXT")

    # Normaliza ordens legadas: cada combinação área/tipo passa a ter
    # ordem única e sequencial. Isso corrige bases antigas com duas
    # questões na mesma posição sem apagar respostas históricas.
    for area in ("LC", "CH", "CN", "MT"):
        for tipo in ("PRINCIPAL", "RESERVA"):
            ids = cursor.execute(
                "SELECT id FROM perguntas WHERE area=? AND tipo=? ORDER BY ordem, id",
                (area, tipo),
            ).fetchall()
            for ordem, (pergunta_id,) in enumerate(ids, start=1):
                cursor.execute("UPDATE perguntas SET ordem=? WHERE id=?", (ordem, pergunta_id))

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_perguntas_area_tipo_ordem ON perguntas(area, tipo, ordem)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respostas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dupla_id INTEGER NOT NULL,
            pergunta_id INTEGER NOT NULL,
            alternativa_escolhida TEXT NOT NULL,
            correta INTEGER NOT NULL,
            pontos INTEGER NOT NULL DEFAULT 0,
            respondida_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dupla_id) REFERENCES duplas(id),
            FOREIGN KEY (pergunta_id) REFERENCES perguntas(id),
            UNIQUE (dupla_id, pergunta_id)
        )""")

    # Bloco 4: separa respostas do quiz principal das respostas de morte súbita.
    # As respostas existentes são, por definição, do quiz regular.
    _adicionar_coluna(cursor, "respostas", "fase TEXT NOT NULL DEFAULT 'REGULAR'")
    _adicionar_coluna(cursor, "respostas", "rodada_desempate INTEGER")
    cursor.execute("UPDATE respostas SET fase='REGULAR' WHERE fase IS NULL OR fase='' ")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY,
            ranking_liberado INTEGER NOT NULL DEFAULT 0
        )""")
    _adicionar_coluna(cursor, "configuracoes", "etapa_ativa INTEGER NOT NULL DEFAULT 0")
    cursor.execute("INSERT OR IGNORE INTO configuracoes (id, ranking_liberado, etapa_ativa) VALUES (1, 0, 0)")

    # Bloco 5: sessões e rodadas da morte súbita.
    cursor.execute("""CREATE TABLE IF NOT EXISTS desempates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pontos_regulares INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDENTE',
        vencedor_dupla_id INTEGER,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vencedor_dupla_id) REFERENCES duplas(id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS desempate_membros (
        desempate_id INTEGER NOT NULL, dupla_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'ATIVA', eliminada_rodada INTEGER,
        PRIMARY KEY (desempate_id, dupla_id),
        FOREIGN KEY (desempate_id) REFERENCES desempates(id), FOREIGN KEY (dupla_id) REFERENCES duplas(id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS desempate_rodadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, desempate_id INTEGER NOT NULL, numero INTEGER NOT NULL,
        area TEXT NOT NULL, pergunta_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ABERTA',
        criada_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(desempate_id, numero), UNIQUE(pergunta_id),
        FOREIGN KEY (desempate_id) REFERENCES desempates(id), FOREIGN KEY (pergunta_id) REFERENCES perguntas(id)
    )""")

    conexao.commit()
    conexao.close()


if __name__ == "__main__":
    criar_banco()
    print("Banco atualizado com sucesso.")
