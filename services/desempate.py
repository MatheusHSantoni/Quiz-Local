import random
import psycopg

from database.conexao import conectar


AREAS = ("LC", "CH", "CN", "MT")
ALTERNATIVAS = {"A", "B", "C", "D", "E"}


def _eligible_rows(con):
    return con.execute("""
        SELECT d.id,
               d.participante_1,
               d.participante_2,
               SUM(
                   CASE
                       WHEN r.fase='REGULAR'
                       THEN r.pontos
                       ELSE 0
                   END
               ) AS pontos,
               SUM(
                   CASE
                       WHEN r.fase='REGULAR'
                       THEN 1
                       ELSE 0
                   END
               ) AS respostas
        FROM duplas d
        LEFT JOIN respostas r ON r.dupla_id=d.id
        GROUP BY d.id
        HAVING SUM(
            CASE
                WHEN r.fase='REGULAR'
                THEN 1
                ELSE 0
            END
        ) >= 8
        ORDER BY pontos DESC, d.id
    """).fetchall()


def sincronizar_empates():
    """Cria sessões para grupos empatados do quiz regular, sem duplicá-las."""
    con = conectar()
    c = con.cursor()

    rows = _eligible_rows(con)
    grupos = {}

    for r in rows:
        grupos.setdefault(r["pontos"], []).append(r)

    for pontos, membros in grupos.items():
        if len(membros) < 2:
            continue

        existente = c.execute(
            """
            SELECT id
            FROM desempates
            WHERE pontos_regulares=%s
            ORDER BY id DESC
            LIMIT 1
            """,
            (pontos,),
        ).fetchone()

        if existente:
            ids_existentes = {
                x["dupla_id"]
                for x in c.execute(
                    """
                    SELECT dupla_id
                    FROM desempate_membros
                    WHERE desempate_id=%s
                    """,
                    (existente["id"],),
                ).fetchall()
            }

            ids_membros = {
                m["id"]
                for m in membros
            }

            if ids_existentes == ids_membros:
                continue

        novo_desempate = c.execute(
            """
            INSERT INTO desempates (
                pontos_regulares,
                status
            )
            VALUES (%s,'PENDENTE')
            RETURNING id
            """,
            (pontos,),
        ).fetchone()

        desempate_id = novo_desempate["id"]

        for membro in membros:
            c.execute(
                """
                INSERT INTO desempate_membros (
                    desempate_id,
                    dupla_id,
                    status
                )
                VALUES (%s,%s,'ATIVA')
                """,
                (
                    desempate_id,
                    membro["id"],
                ),
            )

    con.commit()
    con.close()


def sessoes_pendentes():
    sincronizar_empates()

    con = conectar()
    c = con.cursor()

    sessoes = c.execute("""
        SELECT *
        FROM desempates
        WHERE status!='RESOLVIDO'
        ORDER BY pontos_regulares DESC,id
    """).fetchall()

    resultado = []

    for sessao in sessoes:
        membros = c.execute(
            """
            SELECT dm.*,
                   d.participante_1,
                   d.participante_2
            FROM desempate_membros dm
            JOIN duplas d ON d.id=dm.dupla_id
            WHERE dm.desempate_id=%s
            ORDER BY dm.status DESC,d.id
            """,
            (sessao["id"],),
        ).fetchall()

        rodada = c.execute(
            """
            SELECT dr.*,
                   p.area,
                   p.enunciado
            FROM desempate_rodadas dr
            JOIN perguntas p ON p.id=dr.pergunta_id
            WHERE dr.desempate_id=%s
            ORDER BY dr.numero DESC
            LIMIT 1
            """,
            (sessao["id"],),
        ).fetchone()

        resultado.append({
            "sessao": dict(sessao),
            "membros": [dict(x) for x in membros],
            "rodada": dict(rodada) if rodada else None,
        })

    con.close()

    return resultado


def sessao_da_dupla(dupla_id):
    sincronizar_empates()

    con = conectar()

    row = con.execute(
        """
        SELECT de.*,
               dm.status AS membro_status
        FROM desempates de
        JOIN desempate_membros dm
          ON dm.desempate_id=de.id
        WHERE dm.dupla_id=%s
          AND de.status!='RESOLVIDO'
        ORDER BY de.id DESC
        LIMIT 1
        """,
        (dupla_id,),
    ).fetchone()

    con.close()

    return dict(row) if row else None


def rodada_atual(desempate_id):
    con = conectar()

    rodada = con.execute(
        """
        SELECT p.id AS id,
               dr.id AS rodada_id,
               dr.desempate_id,
               dr.numero,
               dr.area,
               dr.pergunta_id,
               dr.status,
               dr.criada_em,
               p.enunciado,
               p.alternativa_a,
               p.alternativa_b,
               p.alternativa_c,
               p.alternativa_d,
               p.alternativa_e,
               p.alternativa_correta,
               p.imagem
        FROM desempate_rodadas dr
        JOIN perguntas p ON p.id=dr.pergunta_id
        WHERE dr.desempate_id=%s
          AND dr.status='ABERTA'
        ORDER BY dr.numero DESC
        LIMIT 1
        """,
        (desempate_id,),
    ).fetchone()

    con.close()

    return dict(rodada) if rodada else None


def sortear_rodada(desempate_id):
    con = conectar()
    c = con.cursor()

    desempate = c.execute(
        """
        SELECT *
        FROM desempates
        WHERE id=%s
          AND status!='RESOLVIDO'
        """,
        (desempate_id,),
    ).fetchone()

    if not desempate:
        con.close()

        return (
            False,
            "Desempate não encontrado ou já resolvido."
        )

    aberta = c.execute(
        """
        SELECT id
        FROM desempate_rodadas
        WHERE desempate_id=%s
          AND status='ABERTA'
        """,
        (desempate_id,),
    ).fetchone()

    if aberta:
        con.close()

        return (
            False,
            "A rodada atual ainda está em andamento."
        )

    disponiveis = []

    for area in AREAS:
        pergunta = c.execute(
            """
            SELECT p.id
            FROM perguntas p
            WHERE p.area=%s
              AND p.tipo='RESERVA'
              AND NOT EXISTS (
                  SELECT 1
                  FROM desempate_rodadas dr
                  WHERE dr.pergunta_id=p.id
              )
            ORDER BY p.ordem,p.id
            LIMIT 1
            """,
            (area,),
        ).fetchone()

        if pergunta:
            disponiveis.append(
                (
                    area,
                    pergunta["id"],
                )
            )

    if not disponiveis:
        con.close()

        return (
            False,
            "Não há questões de reserva disponíveis para o desempate."
        )

    area, pergunta_id = random.choice(disponiveis)

    numero = c.execute(
        """
        SELECT COALESCE(MAX(numero),0)+1 AS numero
        FROM desempate_rodadas
        WHERE desempate_id=%s
        """,
        (desempate_id,),
    ).fetchone()["numero"]

    c.execute(
        """
        INSERT INTO desempate_rodadas (
            desempate_id,
            numero,
            area,
            pergunta_id,
            status
        )
        VALUES (%s,%s,%s,%s,'ABERTA')
        """,
        (
            desempate_id,
            numero,
            area,
            pergunta_id,
        ),
    )

    c.execute(
        """
        UPDATE desempates
        SET status='EM_ANDAMENTO'
        WHERE id=%s
        """,
        (desempate_id,),
    )

    c.execute(
        """
        UPDATE perguntas
        SET ativa=1
        WHERE id=%s
        """,
        (pergunta_id,),
    )

    con.commit()
    con.close()

    return True,{
        "area": area,
        "numero": numero,
    }


def registrar_resposta(dupla_id, pergunta_id, alternativa):
    if alternativa not in ALTERNATIVAS:
        return False,"Alternativa inválida."

    con = conectar()
    c = con.cursor()

    rodada = c.execute(
        """
        SELECT dr.*
        FROM desempate_rodadas dr
        JOIN desempate_membros dm
          ON dm.desempate_id=dr.desempate_id
        WHERE dm.dupla_id=%s
          AND dm.status='ATIVA'
          AND dr.pergunta_id=%s
          AND dr.status='ABERTA'
        ORDER BY dr.id DESC
        LIMIT 1
        """,
        (
            dupla_id,
            pergunta_id,
        ),
    ).fetchone()

    if not rodada:
        con.close()

        return (
            False,
            "Esta questão de desempate não está disponível para a dupla."
        )

    pergunta = c.execute(
        """
        SELECT alternativa_correta
        FROM perguntas
        WHERE id=%s
        """,
        (pergunta_id,),
    ).fetchone()

    if not pergunta:
        con.close()

        return (
            False,
            "Pergunta de desempate não encontrada."
        )

    correta = int(
        alternativa == pergunta["alternativa_correta"]
    )

    try:
        c.execute(
            """
            INSERT INTO respostas (
                dupla_id,
                pergunta_id,
                alternativa_escolhida,
                correta,
                pontos,
                fase,
                rodada_desempate
            )
            VALUES (%s,%s,%s,%s,%s,'DESEMPATE',%s)
            """,
            (
                dupla_id,
                pergunta_id,
                alternativa,
                correta,
                100 if correta else 0,
                rodada["numero"],
            ),
        )

        _resolver_se_completa(
            con,
            rodada["id"],
        )

        con.commit()

    except psycopg.IntegrityError:
        con.rollback()
        con.close()

        return (
            False,
            "Esta resposta já foi registrada."
        )

    except Exception:
        con.rollback()
        con.close()

        raise

    con.close()

    return True,None


def _resolver_se_completa(con, rodada_id):
    c = con.cursor()

    rodada = c.execute(
        """
        SELECT *
        FROM desempate_rodadas
        WHERE id=%s
        """,
        (rodada_id,),
    ).fetchone()

    if not rodada:
        raise RuntimeError(
            "Rodada de desempate não encontrada."
        )

    ativos = c.execute(
        """
        SELECT dupla_id
        FROM desempate_membros
        WHERE desempate_id=%s
          AND status='ATIVA'
        """,
        (rodada["desempate_id"],),
    ).fetchall()

    respostas = c.execute(
        """
        SELECT dupla_id,correta
        FROM respostas
        WHERE pergunta_id=%s
          AND fase='DESEMPATE'
          AND rodada_desempate=%s
        """,
        (
            rodada["pergunta_id"],
            rodada["numero"],
        ),
    ).fetchall()

    if len(respostas) < len(ativos):
        return

    corretas = [
        resposta["dupla_id"]
        for resposta in respostas
        if resposta["correta"]
    ]

    erradas = [
        resposta["dupla_id"]
        for resposta in respostas
        if not resposta["correta"]
    ]

    c.execute(
        """
        UPDATE desempate_rodadas
        SET status='CONCLUIDA'
        WHERE id=%s
        """,
        (rodada_id,),
    )

    c.execute(
        """
        UPDATE perguntas
        SET ativa=0
        WHERE id=%s
        """,
        (rodada["pergunta_id"],),
    )

    # Só há eliminação quando a rodada separa os desempenhos.
    if corretas and erradas:
        for dupla_id in erradas:
            c.execute(
                """
                UPDATE desempate_membros
                SET status='ELIMINADA',
                    eliminada_rodada=%s
                WHERE desempate_id=%s
                  AND dupla_id=%s
                """,
                (
                    rodada["numero"],
                    rodada["desempate_id"],
                    dupla_id,
                ),
            )

    restantes = c.execute(
        """
        SELECT dupla_id
        FROM desempate_membros
        WHERE desempate_id=%s
          AND status='ATIVA'
        """,
        (rodada["desempate_id"],),
    ).fetchall()

    if len(restantes) == 1:
        vencedor = restantes[0]["dupla_id"]

        c.execute(
            """
            UPDATE desempate_membros
            SET status='VENCEDORA'
            WHERE desempate_id=%s
              AND dupla_id=%s
            """,
            (
                rodada["desempate_id"],
                vencedor,
            ),
        )

        c.execute(
            """
            UPDATE desempates
            SET status='RESOLVIDO',
                vencedor_dupla_id=%s
            WHERE id=%s
            """,
            (
                vencedor,
                rodada["desempate_id"],
            ),
        )


def status_telao(desempate_id):
    con = conectar()
    c = con.cursor()

    desempate = c.execute(
        """
        SELECT *
        FROM desempates
        WHERE id=%s
        """,
        (desempate_id,),
    ).fetchone()

    if not desempate:
        con.close()

        return None

    rodada = c.execute(
        """
        SELECT dr.*,
               p.enunciado
        FROM desempate_rodadas dr
        JOIN perguntas p ON p.id=dr.pergunta_id
        WHERE dr.desempate_id=%s
        ORDER BY dr.numero DESC
        LIMIT 1
        """,
        (desempate_id,),
    ).fetchone()

    membros = c.execute(
        """
        SELECT dm.status,
               d.id,
               d.participante_1,
               d.participante_2
        FROM desempate_membros dm
        JOIN duplas d ON d.id=dm.dupla_id
        WHERE dm.desempate_id=%s
        ORDER BY d.id
        """,
        (desempate_id,),
    ).fetchall()

    respondidas = 0

    esperadas = sum(
        1
        for membro in membros
        if membro["status"] in ("ATIVA","VENCEDORA")
    )

    if rodada:
        respondidas = c.execute(
            """
            SELECT COUNT(*) AS total
            FROM respostas
            WHERE pergunta_id=%s
              AND fase='DESEMPATE'
              AND rodada_desempate=%s
            """,
            (
                rodada["pergunta_id"],
                rodada["numero"],
            ),
        ).fetchone()["total"]

    resultado = {
        "sessao": dict(desempate),
        "rodada": dict(rodada) if rodada else None,
        "membros": [dict(x) for x in membros],
        "respondidas": respondidas,
        "esperadas": esperadas,
    }

    con.close()

    return resultado