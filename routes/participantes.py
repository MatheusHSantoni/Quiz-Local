from flask import (Blueprint,render_template,request,redirect,url_for,session)
from pwdlib import PasswordHash
from database.conexao import conectar
from services.ranking import buscar_ranking


participantes_bp = Blueprint("participantes",__name__)
password_hash = PasswordHash.recommended()

AREAS_ETAPA = {
    1: ("LC", "CH"),
    2: ("CN", "MT"),
}


def _perguntas_oficiais_etapa(cursor, etapa):
    """Retorna exatamente as duas primeiras questões principais ativas de cada área da etapa."""
    ids = []
    for area in AREAS_ETAPA[etapa]:
        linhas = cursor.execute(
            """
            SELECT id
            FROM perguntas
            WHERE area=? AND tipo='PRINCIPAL' AND ativa=1
            ORDER BY ordem, id
            LIMIT 2
            """,
            (area,),
        ).fetchall()
        ids.extend(linha["id"] for linha in linhas)
    return ids


def _proxima_pergunta(cursor, dupla_id, etapa):
    areas = AREAS_ETAPA[etapa]
    ids = _perguntas_oficiais_etapa(cursor, etapa)
    if len(ids) < 4:
        return None
    marcadores = ",".join("?" for _ in ids)
    return cursor.execute(
        f"""
        SELECT id, area, enunciado, alternativa_a, alternativa_b, alternativa_c,
               alternativa_d, alternativa_e, alternativa_correta, imagem, ordem
        FROM perguntas
        WHERE id IN ({marcadores})
          AND id NOT IN (SELECT pergunta_id FROM respostas WHERE dupla_id=?)
        ORDER BY CASE area WHEN ? THEN 1 WHEN ? THEN 2 ELSE 3 END, ordem, id
        LIMIT 1
        """,
        (*ids, dupla_id, areas[0], areas[1]),
    ).fetchone()


def _etapa_concluida(cursor, dupla_id, etapa):
    ids = _perguntas_oficiais_etapa(cursor, etapa)
    if len(ids) < 4:
        return False
    marcadores = ",".join("?" for _ in ids)
    total = cursor.execute(
        f"SELECT COUNT(*) total FROM respostas WHERE dupla_id=? AND pergunta_id IN ({marcadores})",
        (dupla_id, *ids),
    ).fetchone()["total"]
    return total == 4


@participantes_bp.route("/")
def index():
    return render_template("index.html")


@participantes_bp.route("/cadastro")
def cadastro():
    return render_template("cadastro.html")


@participantes_bp.route("/entrar",methods=["POST"])
def entrar():
    participante_1 = (request.form.get("participante_1") or "").strip()
    participante_2 = (request.form.get("participante_2") or "").strip()
    senha = request.form.get("senha") or ""
    if not participante_1 or not participante_2 or not senha:
        return ("Informe os dois participantes e uma senha.",400)
    if len(senha) < 6:
        return ("A senha deve ter pelo menos 6 caracteres.",400)
    senha_hash = password_hash.hash(senha)
    conexao = conectar(); cursor = conexao.cursor()
    cursor.execute("INSERT INTO duplas (participante_1,participante_2,senha_hash) VALUES (?,?,?)",
                   (participante_1,participante_2,senha_hash))
    dupla_id = cursor.lastrowid
    conexao.commit(); conexao.close()
    session["dupla_id"] = dupla_id
    return redirect(url_for("participantes.dupla_criada",dupla_id=dupla_id))


@participantes_bp.route("/dupla-criada/<int:dupla_id>")
def dupla_criada(dupla_id):
    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.",403)
    conexao = conectar(); cursor = conexao.cursor()
    dupla = cursor.execute("SELECT id,participante_1,participante_2 FROM duplas WHERE id=?",(dupla_id,)).fetchone()
    conexao.close()
    if dupla is None:
        return ("Time não encontrado.",404)
    return render_template("dupla_criada.html",dupla=dupla)


@participantes_bp.route("/login-time")
def login_time():
    return render_template("login_time.html")


@participantes_bp.route("/entrar-dupla",methods=["POST"])
def entrar_dupla():
    dupla_id = request.form.get("dupla_id")
    senha = request.form.get("senha") or ""
    if not dupla_id or not senha:
        return ("Informe o número do time e a senha.",400)
    try:
        dupla_id = int(dupla_id)
    except ValueError:
        return ("Número do time inválido.",400)
    if dupla_id <= 0:
        return ("Número do time inválido.",400)
    conexao = conectar(); cursor = conexao.cursor()
    dupla = cursor.execute("SELECT id,senha_hash FROM duplas WHERE id=?",(dupla_id,)).fetchone()
    conexao.close()
    if dupla is None or not password_hash.verify(senha, dupla["senha_hash"]):
        return ("Time ou senha inválidos.",401)
    session["dupla_id"] = dupla["id"]
    return redirect(url_for("participantes.quiz",dupla_id=dupla["id"]))


@participantes_bp.route("/sair-time")
def sair_time():
    session.pop("dupla_id",None)
    return redirect(url_for("participantes.index"))


@participantes_bp.route("/quiz/<int:dupla_id>")
def quiz(dupla_id):
    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.", 403)
    conexao = conectar(); cursor = conexao.cursor()
    dupla = cursor.execute("SELECT id,participante_1,participante_2 FROM duplas WHERE id=?", (dupla_id,)).fetchone()
    if dupla is None:
        conexao.close(); return ("Time não encontrado.", 404)
    # A morte súbita tem prioridade sobre as etapas regulares para as duplas envolvidas.
    from services.desempate import sessao_da_dupla, rodada_atual
    ds = sessao_da_dupla(dupla_id)
    if ds and ds.get("membro_status") == "ATIVA":
        rd = rodada_atual(ds["id"])
        if rd:
            ja = cursor.execute("SELECT 1 FROM respostas WHERE dupla_id=? AND pergunta_id=? AND fase='DESEMPATE'", (dupla_id, rd["pergunta_id"])).fetchone()
            if not ja:
                conexao.close()
                return render_template("quiz.html", dupla=dupla, dupla_id=dupla_id, pergunta=rd, etapa="DESEMPATE", desempate=True)
    config = cursor.execute("SELECT etapa_ativa,ranking_liberado FROM configuracoes WHERE id=1").fetchone()
    if config["ranking_liberado"]:
        conexao.close(); return redirect(url_for("participantes.ranking"))
    etapa = config["etapa_ativa"]
    if etapa not in (1, 2):
        conexao.close(); return redirect(url_for("participantes.aguardando", dupla_id=dupla_id))
    pergunta = _proxima_pergunta(cursor, dupla_id, etapa)
    conexao.close()
    if pergunta is None:
        return redirect(url_for("participantes.aguardando", dupla_id=dupla_id))
    return render_template("quiz.html", dupla=dupla, dupla_id=dupla_id, pergunta=pergunta, etapa=etapa)


@participantes_bp.route("/responder", methods=["POST"])
def responder():
    try:
        dupla_id = int(request.form.get("dupla_id", "")); pergunta_id = int(request.form.get("pergunta_id", ""))
    except ValueError:
        return ("Dados da resposta inválidos.", 400)
    alternativa = (request.form.get("alternativa") or "").strip().upper()
    if session.get("dupla_id") != dupla_id:
        return ("Acesso não autorizado.", 403)
    if alternativa not in "ABCDE":
        return ("Alternativa inválida.", 400)
    conexao=conectar(); cursor=conexao.cursor()


    # ---------------------------------------------------------
    # MORTE SÚBITA
    # ---------------------------------------------------------
    # Verifica se esta pergunta pertence a uma rodada aberta
    # de desempate da qual a dupla participa como membro ativo.
    rd = cursor.execute("""
        SELECT dr.id
        FROM desempate_rodadas dr
        JOIN desempate_membros dm
          ON dm.desempate_id = dr.desempate_id
        WHERE dr.pergunta_id = ?
          AND dr.status = 'ABERTA'
          AND dm.dupla_id = ?
          AND dm.status = 'ATIVA'
        ORDER BY dr.id DESC
        LIMIT 1
    """, (pergunta_id, dupla_id)).fetchone()

    if rd:
        conexao.close()

        from services.desempate import registrar_resposta

        ok, erro = registrar_resposta(
            dupla_id,
            pergunta_id,
            alternativa
        )

        if not ok:
            return (erro, 409)

        return redirect(
            url_for(
                "participantes.aguardando",
                dupla_id=dupla_id
            )
        )









    config=cursor.execute("SELECT etapa_ativa,ranking_liberado FROM configuracoes WHERE id=1").fetchone()
    if config["ranking_liberado"]:
        conexao.close(); return redirect(url_for("participantes.ranking"))
    etapa=config["etapa_ativa"]
    if etapa not in (1,2):
        conexao.close(); return redirect(url_for("participantes.aguardando",dupla_id=dupla_id))
    pergunta_atual = _proxima_pergunta(cursor, dupla_id, etapa)
    if not pergunta_atual or pergunta_id != pergunta_atual["id"]:
        conexao.close(); return ("Esta não é a pergunta atual do time.",400)
    correta=int(alternativa==pergunta_atual["alternativa_correta"])
    try:
        cursor.execute("INSERT INTO respostas (dupla_id,pergunta_id,alternativa_escolhida,correta,pontos,fase) VALUES (?,?,?,?,?,?)",
                       (dupla_id,pergunta_id,alternativa,correta,100 if correta else 0,"REGULAR"))
        conexao.commit()
    except Exception:
        conexao.rollback(); conexao.close(); return ("Não foi possível registrar a resposta. Tente novamente.",409)
    conexao.close()
    return redirect(url_for("participantes.quiz",dupla_id=dupla_id))


@participantes_bp.route("/aguardando/<int:dupla_id>")
def aguardando(dupla_id):
    if session.get("dupla_id") != dupla_id:
        # A sessão do navegador pode ter sido substituída por outro login.
        # Em vez de uma página 403 crua, volta ao login com uma explicação.
        return redirect(url_for("participantes.login_time", sessao="substituida"))
    conexao = conectar(); cursor = conexao.cursor()
    dupla = cursor.execute("SELECT id,participante_1,participante_2 FROM duplas WHERE id=?",(dupla_id,)).fetchone()
    if dupla is None:
        conexao.close(); return ("Time não encontrado.",404)
    configuracao = cursor.execute("SELECT ranking_liberado,etapa_ativa FROM configuracoes WHERE id=1").fetchone()
    if configuracao is not None and configuracao["ranking_liberado"] == 1:
        conexao.close(); return redirect(url_for("participantes.ranking"))

    from services.desempate import sessao_da_dupla, rodada_atual
    ds = sessao_da_dupla(dupla_id)
    if ds:
        membro_status = ds.get("membro_status")
        rd = rodada_atual(ds["id"])

        # Enquanto a dupla participa de um desempate, esse fluxo tem prioridade
        # sobre a mensagem de "Quiz finalizado" da etapa 2.
        if membro_status == "ATIVA":
            if rd:
                ja = cursor.execute(
                    "SELECT 1 FROM respostas WHERE dupla_id=? AND pergunta_id=? AND fase='DESEMPATE'",
                    (dupla_id, rd["pergunta_id"]),
                ).fetchone()
                if not ja:
                    conexao.close()
                    return redirect(url_for("participantes.quiz", dupla_id=dupla_id))
                estado = "desempate_respondido"
            else:
                estado = "desempate_aguardando"
            conexao.close()
            return render_template(
                "aguardando.html",
                dupla=dupla,
                etapa_ativa=configuracao["etapa_ativa"] if configuracao else 0,
                estado=estado,
            )

        if membro_status == "ELIMINADA":
            conexao.close()
            return render_template(
                "aguardando.html", dupla=dupla, etapa_ativa=0, estado="desempate_eliminada"
            )

    etapa_ativa = configuracao["etapa_ativa"] if configuracao else 0
    # Se uma nova etapa foi aberta enquanto a dupla estava na tela de espera,
    # o refresh automático a encaminha para a próxima questão disponível.
    if etapa_ativa in (1, 2) and _proxima_pergunta(cursor, dupla_id, etapa_ativa) is not None:
        conexao.close(); return redirect(url_for("participantes.quiz", dupla_id=dupla_id))

    concluiu_e1 = _etapa_concluida(cursor, dupla_id, 1)
    concluiu_e2 = _etapa_concluida(cursor, dupla_id, 2)
    conexao.close()

    if concluiu_e2:
        estado = "etapa2_concluida"
    elif concluiu_e1:
        estado = "etapa1_concluida"
    elif etapa_ativa == 0:
        estado = "pausada"
    else:
        estado = "aguardando"

    return render_template("aguardando.html", dupla=dupla, etapa_ativa=etapa_ativa, estado=estado)


@participantes_bp.route("/ranking")
def ranking():
    conexao = conectar(); cursor = conexao.cursor()
    configuracao = cursor.execute("SELECT ranking_liberado FROM configuracoes WHERE id=1").fetchone()
    conexao.close()
    if configuracao is None:
        return ("Configuração do ranking não encontrada.",500)
    if configuracao["ranking_liberado"] == 0:
        return ("O ranking ainda não foi liberado.",403)
    classificacao = buscar_ranking()
    return render_template("ranking.html",ranking=classificacao)


@participantes_bp.route("/desempate/<int:desempate_id>")
def telao_desempate(desempate_id):
    from services.desempate import status_telao
    estado=status_telao(desempate_id)
    if not estado: return ("Desempate não encontrado.",404)
    return render_template("desempate_telao.html", estado=estado)

@participantes_bp.route("/desempate/<int:desempate_id>/status")
def status_desempate(desempate_id):
    from flask import jsonify
    from services.desempate import status_telao
    e=status_telao(desempate_id)
    if not e: return jsonify({"erro":"não encontrado"}),404
    return jsonify({"status":e["sessao"]["status"],"rodada":e["rodada"],"respondidas":e["respondidas"],"esperadas":e["esperadas"],"membros":e["membros"]})
