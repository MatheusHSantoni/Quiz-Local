from database.conexao import conectar


def _linhas_classificacao(conexao):
    return conexao.execute("""
        SELECT d.id,d.participante_1,d.participante_2,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                THEN 1
                ELSE 0
            END
        ) respostas_regulares,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                THEN r.pontos
                ELSE 0
            END
        ) pontos_regulares,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area IN ('LC','CH')
                THEN r.pontos
                ELSE 0
            END
        ) pontos_etapa1,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area IN ('CN','MT')
                THEN r.pontos
                ELSE 0
            END
        ) pontos_etapa2,

        SUM(
            CASE
                WHEN r.fase='DESEMPATE'
                THEN r.pontos
                ELSE 0
            END
        ) pontos_desempate,

        SUM(
            CASE
                WHEN r.fase='DESEMPATE'
                THEN 1
                ELSE 0
            END
        ) respostas_desempate,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area='LC'
                THEN 1
                ELSE 0
            END
        ) resp_lc,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area='CH'
                THEN 1
                ELSE 0
            END
        ) resp_ch,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area='CN'
                THEN 1
                ELSE 0
            END
        ) resp_cn,

        SUM(
            CASE
                WHEN r.fase='REGULAR'
                 AND p.area='MT'
                THEN 1
                ELSE 0
            END
        ) resp_mt

        FROM duplas d
        LEFT JOIN respostas r ON r.dupla_id=d.id
        LEFT JOIN perguntas p ON p.id=r.pergunta_id

        GROUP BY d.id
    """).fetchall()


def _ordem_desempate(con, dupla_id, pontos):
    m = con.execute(
        """
        SELECT dm.status,dm.eliminada_rodada,de.id
        FROM desempate_membros dm
        JOIN desempates de ON de.id=dm.desempate_id
        WHERE dm.dupla_id=%s
          AND de.pontos_regulares=%s
        ORDER BY de.id DESC
        LIMIT 1
        """,
        (dupla_id,pontos),
    ).fetchone()

    if not m:
        return (1,0)

    if m["status"] == "VENCEDORA":
        return (3,999999)

    if m["status"] == "ATIVA":
        return (2,999999)

    return (0,m["eliminada_rodada"] or 0)


def buscar_ranking():
    con = conectar()

    linhas = [
        dict(linha)
        for linha in _linhas_classificacao(con)
    ]

    for linha in linhas:
        linha["total_pontos"] = linha["pontos_regulares"]

        linha["_desempate_ordem"] = _ordem_desempate(
            con,
            linha["id"],
            linha["pontos_regulares"],
        )

    con.close()

    linhas.sort(
        key=lambda linha: (
            -linha["total_pontos"],
            -linha["_desempate_ordem"][0],
            -linha["_desempate_ordem"][1],
            linha["id"],
        )
    )

    posicao = 0
    chave_anterior = None

    for indice,linha in enumerate(linhas,1):
        chave = (
            linha["total_pontos"],
            linha["_desempate_ordem"],
        )

        if chave != chave_anterior:
            posicao = indice
            chave_anterior = chave

        linha["posicao"] = posicao

    return linhas


def resumo_ranking():
    from services.desempate import sincronizar_empates, sessoes_pendentes

    con = conectar()

    linhas = _linhas_classificacao(con)

    con.close()

    sincronizar_empates()

    pendentes = sessoes_pendentes()

    completas = [
        dict(linha)
        for linha in linhas
        if linha["respostas_regulares"] >= 8
    ]

    incompletas = [
        dict(linha)
        for linha in linhas
        if linha["respostas_regulares"] < 8
    ]

    return {
        "total": len(linhas),
        "elegiveis": len(completas),
        "incompletas": len(incompletas),
        "grupos_empate": len(pendentes),
        "duplas_empatadas": sum(
            sum(
                1
                for membro in sessao["membros"]
                if membro["status"] == "ATIVA"
            )
            for sessao in pendentes
        ),
        "empates": {},
    }


def ranking_pode_ser_liberado():
    con = conectar()

    total = con.execute(
        """
        SELECT COUNT(*) AS total
        FROM duplas
        """
    ).fetchone()["total"]

    con.close()

    if total == 0:
        return False,"Ainda não existem duplas cadastradas."

    return True,None