import psycopg

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from pwdlib import PasswordHash
from database.conexao import conectar
from services.ranking import buscar_ranking


participantes_bp = Blueprint("participantes", __name__)
password_hash = PasswordHash.recommended()

AREAS_ETAPA = {
    1: ("LC", "CH"),
    2: ("CN", "MT"),
}

ALTERNATIVAS = {"A", "B", "C", "D", "E"}


def _perguntas_oficiais_etapa(cursor, etapa):
    """Retorna exatamente as duas primeiras questões principais ativas de cada área da etapa."""
    ids = []

    for area in AREAS_ETAPA[etapa]:
        linhas = cursor.execute(
            """
            SELECT id
            FROM perguntas
            WHERE area=%s
              AND tipo='PRINCIPAL'
              AND ativa=1
            ORDER BY ordem, id
            """,
            (area,),
        ).fetchall()

        ids.extend(
            linha["id"]
            for linha in linhas)

    return ids


def _proxima_pergunta(cursor, dupla_id, etapa):
    areas = AREAS_ETAPA[etapa]
    ids = _perguntas_oficiais_etapa(cursor, etapa)

    if len(ids) < 1:
        return None

    marcadores = ",".join(
        "%s"
        for _ in ids
    )

    return cursor.execute(
        f"""
        SELECT id,
               area,
               enunciado,
               alternativa_a,
               alternativa_b,
               alternativa_c,
               alternativa_d,
               alternativa_e,
               alternativa_correta,
               imagem,
               ordem
        FROM perguntas
        WHERE id IN ({marcadores})
          AND id NOT IN (
              SELECT pergunta_id
              FROM respostas
              WHERE dupla_id=%s
                AND fase='REGULAR'
          )
        ORDER BY
            CASE area
                WHEN %s THEN 1
                WHEN %s THEN 2
                ELSE 3
            END,
            ordem,
            id
        LIMIT 1
        """,
        (
            *ids,
            dupla_id,
            areas[0],
            areas[1],
        ),
    ).fetchone()


def _etapa_concluida(cursor, dupla_id, etapa):
    ids = _perguntas_oficiais_etapa(
        cursor,
        etapa,)

    if len(ids) < 1:
        return False

    marcadores = ",".join(
        "%s"
        for _ in ids)

    total = cursor.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM respostas
        WHERE dupla_id=%s
          AND fase='REGULAR'
          AND pergunta_id IN ({marcadores})
        """,
        (
            dupla_id,
            *ids,
        ),
    ).fetchone()["total"]

    return total == len(ids)


def _buscar_configuracao(cursor):
    return cursor.execute("""
        SELECT etapa_ativa,
               ranking_liberado,
               fim_etapa,
               CURRENT_TIMESTAMP AS agora
        FROM configuracoes
        WHERE id=1
    """).fetchone()


@participantes_bp.route("/")
def index():
    return render_template("index.html")


@participantes_bp.route("/cadastro")
def cadastro():
    return render_template("cadastro.html")


@participantes_bp.route("/entrar", methods=["POST"])
def entrar():
    participante_1 = (request.form.get("participante_1") or "").strip()

    participante_2 = (request.form.get("participante_2") or "").strip()

    senha = request.form.get("senha") or ""

    if not participante_1 or not participante_2 or not senha:
        return ("Informe os dois participantes e uma senha.",400,)

    if len(senha) < 6:
        return ("A senha deve ter pelo menos 6 caracteres.",400,)

    senha_hash = password_hash.hash(senha)

    conexao = conectar()
    cursor = conexao.cursor()

    dupla = cursor.execute(
        """
        INSERT INTO duplas (
            participante_1,
            participante_2,
            senha_hash
        )
        VALUES (%s,%s,%s)
        RETURNING id
        """,
        (
            participante_1,
            participante_2,
            senha_hash,
        ),
    ).fetchone()

    dupla_id = dupla["id"]

    conexao.commit()
    conexao.close()

    session["dupla_id"] = dupla_id

    return redirect(
        url_for("participantes.dupla_criada", dupla_id=dupla_id,))


@participantes_bp.route("/dupla-criada/<int:dupla_id>")
def dupla_criada(dupla_id):
    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.",403,)

    conexao = conectar()
    cursor = conexao.cursor()

    dupla = cursor.execute(
        """
        SELECT id,
               participante_1,
               participante_2
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    conexao.close()

    if dupla is None:
        return ("Time não encontrado.",404,)

    return render_template("dupla_criada.html",dupla=dupla,)


@participantes_bp.route("/login-time")
def login_time():
    return render_template("login_time.html")


@participantes_bp.route("/entrar-dupla", methods=["POST"])
def entrar_dupla():
    dupla_id = request.form.get("dupla_id")
    senha = request.form.get("senha") or ""

    if not dupla_id or not senha:
        return ("Informe o número do time e a senha.",400,)

    try:
        dupla_id = int(dupla_id)

    except (TypeError, ValueError):
        return ("Número do time inválido.",400,)

    if dupla_id <= 0:
        return ("Número do time inválido.",400,)

    conexao = conectar()
    cursor = conexao.cursor()

    dupla = cursor.execute(
        """
        SELECT id,
               senha_hash
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    conexao.close()

    if (dupla is None or not password_hash.verify(senha,dupla["senha_hash"],)):
        return ("Time ou senha inválidos.",401,)

    session["dupla_id"] = dupla["id"]

    return redirect(url_for("participantes.quiz",dupla_id=dupla["id"],))


@participantes_bp.route("/sair-time")
def sair_time():
    session.pop(
        "dupla_id",
        None,)

    return redirect(url_for("participantes.index"))


@participantes_bp.route("/quiz/<int:dupla_id>")
def quiz(dupla_id):
    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.",403,)

    conexao = conectar()
    cursor = conexao.cursor()

    dupla = cursor.execute(
        """
        SELECT id,
               participante_1,
               participante_2
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    if dupla is None:
        conexao.close()

        return ("Time não encontrado.",404,)

    # A morte súbita tem prioridade para uma dupla
    # que está participando de uma rodada aberta.
    from services.desempate import sessao_da_dupla, rodada_atual

    sessao_desempate = sessao_da_dupla(dupla_id)

    if (
        sessao_desempate
        and sessao_desempate.get("membro_status") == "ATIVA"):
        rodada = rodada_atual(
            sessao_desempate["id"])

        if rodada:
            ja_respondeu = cursor.execute(
                """
                SELECT 1
                FROM respostas
                WHERE dupla_id=%s
                  AND pergunta_id=%s
                  AND fase='DESEMPATE'
                """,
                (
                    dupla_id,
                    rodada["pergunta_id"],
                ),
            ).fetchone()

            if not ja_respondeu:
                conexao.close()

                return render_template(
                    "quiz.html",
                    dupla=dupla,
                    dupla_id=dupla_id,
                    pergunta=rodada,
                    etapa="DESEMPATE",
                    desempate=True,
                    fim_etapa=None,)

    configuracao = _buscar_configuracao(
        cursor)

    if configuracao is None:
        conexao.close()

        return ("Configuração do quiz não encontrada.",500,)

    if configuracao["ranking_liberado"]:
        conexao.close()

        return redirect(url_for("participantes.ranking"))
    
    etapa = configuracao["etapa_ativa"]

    if etapa not in (1, 2):
        conexao.close()

        return redirect(url_for("participantes.aguardando",dupla_id=dupla_id,))

    if (configuracao["fim_etapa"] is None
        or configuracao["agora"] >= configuracao["fim_etapa"]):
        conexao.close()

        return redirect(url_for("participantes.aguardando",dupla_id=dupla_id,))

    pergunta = _proxima_pergunta(
        cursor,
        dupla_id,
        etapa,)

    if pergunta is None:
        conexao.close()

        return redirect(url_for("participantes.aguardando",dupla_id=dupla_id,))

    cursor.execute(
        """
        INSERT INTO questoes_iniciadas (
            dupla_id,
            pergunta_id
        )
        VALUES (%s,%s)
        ON CONFLICT (dupla_id, pergunta_id) DO NOTHING
        """,
        (
            dupla_id,
            pergunta["id"],
        ),
    )

    conexao.commit()
    conexao.close()

    return render_template("quiz.html", dupla=dupla, dupla_id=dupla_id, pergunta=pergunta,etapa=etapa, desempate=False,fim_etapa=configuracao["fim_etapa"],)


@participantes_bp.route("/responder", methods=["POST"])
def responder():
    try:
        dupla_id = int(
            request.form.get("dupla_id","",))
        
        pergunta_id = int(
            request.form.get("pergunta_id","",))

    except (TypeError, ValueError):
        return ("Dados da resposta inválidos.",400,)

    alternativa = (
        request.form.get("alternativa") or ""
    ).strip().upper()

    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.",403,)

    if alternativa not in ALTERNATIVAS:
        return ("Alternativa inválida.",400,)

    conexao = conectar()
    cursor = conexao.cursor()

    # MORTE SÚBITA
    #
    # Primeiro verificamos se a pergunta enviada
    # pertence a uma rodada aberta de desempate
    # da qual esta dupla participa.
    rodada_desempate = cursor.execute(
        """
        SELECT dr.id
        FROM desempate_rodadas dr
        JOIN desempate_membros dm
          ON dm.desempate_id=dr.desempate_id
        WHERE dr.pergunta_id=%s
          AND dr.status='ABERTA'
          AND dm.dupla_id=%s
          AND dm.status='ATIVA'
        ORDER BY dr.id DESC
        LIMIT 1
        """,
        (
            pergunta_id,
            dupla_id,
        ),
    ).fetchone()

    if rodada_desempate:
        conexao.close()

        from services.desempate import registrar_resposta

        ok, erro = registrar_resposta(
            dupla_id,
            pergunta_id,
            alternativa,)

        if not ok:
            return (erro,409,)

        # Depois que a resposta do desempate foi
        # registrada, verificamos o estado atual
        # do ranking.
        conexao = conectar()
        cursor = conexao.cursor()

        configuracao = _buscar_configuracao(
            cursor)

        conexao.close()

        if configuracao is None:
            return ("Configuração do quiz não encontrada.",500,)

        if configuracao["ranking_liberado"]:
            return redirect(url_for("participantes.ranking"))

        return redirect(url_for("participantes.aguardando",dupla_id=dupla_id,))

    configuracao = _buscar_configuracao(
        cursor)

    if configuracao is None:
        conexao.close()

        return ("Configuração do quiz não encontrada.",500,)

    # Se o ranking estiver aberto, não permitimos
    # registrar uma nova resposta regular.
    if configuracao["ranking_liberado"]:
        conexao.close()

        return redirect(url_for("participantes.ranking"))

    etapa = configuracao["etapa_ativa"]

    if etapa not in (1, 2):
        conexao.close()

        return redirect(
            url_for("participantes.aguardando",dupla_id=dupla_id,))

    if (configuracao["fim_etapa"] is None
        or configuracao["agora"] >= configuracao["fim_etapa"]):
        conexao.close()

        return redirect(
            url_for("participantes.aguardando",dupla_id=dupla_id,))

    pergunta_atual = _proxima_pergunta(
        cursor,
        dupla_id,
        etapa,)

    if (not pergunta_atual
        or pergunta_id != pergunta_atual["id"]):
        conexao.close()

        return ("Esta não é a pergunta atual do time.",400,)

    registro_tempo = cursor.execute(
        """
        SELECT GREATEST(
            0,
            FLOOR(
                EXTRACT(
                    EPOCH FROM (
                        clock_timestamp() - iniciada_em
                    )
                ) * 1000
            )
        )::BIGINT AS tempo_resposta_ms
        FROM questoes_iniciadas
        WHERE dupla_id=%s
          AND pergunta_id=%s
        """,
        (
            dupla_id,
            pergunta_id,
        ),
    ).fetchone()

    if registro_tempo is None:
        conexao.close()

        return ("Não foi possível determinar o início desta questão.",409,)

    tempo_resposta_ms = registro_tempo["tempo_resposta_ms"]

    correta = int(alternativa == pergunta_atual["alternativa_correta"])

    try:
        cursor.execute(
            """
            INSERT INTO respostas (
                dupla_id,
                pergunta_id,
                alternativa_escolhida,
                correta,
                pontos,
                fase,
                tempo_resposta_ms
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                dupla_id,
                pergunta_id,
                alternativa,
                correta,
                100 if correta else 0,
                "REGULAR",
                tempo_resposta_ms,
            ),)

        conexao.commit()

    except psycopg.IntegrityError:
        conexao.rollback()
        conexao.close()

        return ("Não foi possível registrar a resposta. Tente novamente.",409,)

    except Exception:
        conexao.rollback()
        conexao.close()

        raise

    conexao.close()

    return redirect(
        url_for("participantes.quiz",dupla_id=dupla_id,))


@participantes_bp.route("/aguardando/<int:dupla_id>")
def aguardando(dupla_id):
    if session.get("dupla_id") != dupla_id:
        # A sessão do navegador pode ter sido substituída
        # por outro login.
        return redirect(
            url_for("participantes.login_time",sessao="substituida",))

    conexao = conectar()
    cursor = conexao.cursor()

    dupla = cursor.execute(
        """
        SELECT id,
               participante_1,
               participante_2
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    if dupla is None:
        conexao.close()

        return (
            "Time não encontrado.",
            404,)

    configuracao = _buscar_configuracao(
        cursor)

    if configuracao is None:
        conexao.close()

        return ("Configuração do quiz não encontrada.",500,)

    # Ranking liberado sempre pode ser visualizado.
    if configuracao["ranking_liberado"]:
        conexao.close()

        return redirect(url_for("participantes.ranking"))

    from services.desempate import sessao_da_dupla, rodada_atual

    sessao_desempate = sessao_da_dupla(
        dupla_id)

    if sessao_desempate:
        membro_status = sessao_desempate.get(
            "membro_status")

        rodada = rodada_atual(sessao_desempate["id"])

        # Enquanto a dupla participa de um desempate,
        # esse fluxo tem prioridade sobre as etapas.
        if membro_status == "ATIVA":
            if rodada:
                ja_respondeu = cursor.execute(
                    """
                    SELECT 1
                    FROM respostas
                    WHERE dupla_id=%s
                      AND pergunta_id=%s
                      AND fase='DESEMPATE'
                    """,
                    (
                        dupla_id,
                        rodada["pergunta_id"],
                    ),
                ).fetchone()

                if not ja_respondeu:
                    conexao.close()

                    return redirect(
                        url_for("participantes.quiz",dupla_id=dupla_id,))

                estado = "desempate_respondido"

            else:
                estado = "desempate_aguardando"

            conexao.close()

            return render_template("aguardando.html",dupla=dupla,etapa_ativa=configuracao["etapa_ativa"],estado=estado,)

        if membro_status == "ELIMINADA":
            conexao.close()

            return render_template("aguardando.html",dupla=dupla,etapa_ativa=0,estado="desempate_eliminada",)

    etapa_ativa = configuracao["etapa_ativa"]

    # Se uma nova etapa foi aberta enquanto a dupla
    # estava esperando, ela volta automaticamente
    # para o quiz.
    if (etapa_ativa in (1, 2)
        and configuracao["fim_etapa"] is not None
        and configuracao["agora"] < configuracao["fim_etapa"]
        and _proxima_pergunta(
            cursor,
            dupla_id,
            etapa_ativa,
        ) is not None
    ):
        conexao.close()

        return redirect(
            url_for("participantes.quiz",dupla_id=dupla_id,))

    concluiu_e1 = _etapa_concluida(
        cursor,
        dupla_id,
        1,
    )

    concluiu_e2 = _etapa_concluida(
        cursor,
        dupla_id,
        2,
    )

    conexao.close()

    if concluiu_e2:
        estado = "etapa2_concluida"

    elif concluiu_e1:
        estado = "etapa1_concluida"

    elif etapa_ativa == 0:
        estado = "pausada"

    else:
        estado = "aguardando"

    return render_template("aguardando.html",dupla=dupla,etapa_ativa=etapa_ativa,estado=estado,)


@participantes_bp.route("/ranking")
def ranking():
    conexao = conectar()
    cursor = conexao.cursor()

    configuracao = cursor.execute("""
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id=1
    """).fetchone()

    conexao.close()

    if configuracao is None:
        return ("Configuração do ranking não encontrada.",500,)

    if not configuracao["ranking_liberado"]:
        dupla_id = session.get("dupla_id")

        if dupla_id:
            return redirect(
                url_for("participantes.aguardando",dupla_id=dupla_id,))

        return ("O ranking ainda não foi liberado.",403,)

    classificacao = buscar_ranking()

    return render_template("ranking.html",ranking=classificacao,)


@participantes_bp.route("/desempate/<int:desempate_id>")
def telao_desempate(desempate_id):
    from services.desempate import status_telao

    estado = status_telao(desempate_id)

    if not estado:
        return ("Desempate não encontrado.", 404,)

    return render_template("desempate_telao.html", estado=estado,)


@participantes_bp.route("/desempate/<int:desempate_id>/status")
def status_desempate(desempate_id):
    from services.desempate import status_telao

    estado = status_telao(
        desempate_id
    )

    if not estado:
        return jsonify({
            "erro": "não encontrado"
        }), 404

    return jsonify({
        "status": estado["sessao"]["status"],
        "rodada": estado["rodada"],
        "respondidas": estado["respondidas"],
        "esperadas": estado["esperadas"],
        "membros": estado["membros"],
    })