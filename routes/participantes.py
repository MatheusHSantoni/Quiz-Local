from flask import (Blueprint,render_template,request,redirect,url_for)
from database.conexao import conectar
from services.ranking import buscar_ranking

participantes_bp = Blueprint("participantes",__name__)

# ENTRADA

@participantes_bp.route("/")
def index():
    return render_template("index.html")

# CRIAR NOVO TIME
@participantes_bp.route("/entrar", methods=["POST"])
def entrar():

    participante_1 = (request.form.get("participante_1") or "").strip()
    participante_2 = (request.form.get("participante_2") or "").strip()

    if not participante_1 or not participante_2:
        return ("Informe o nome dos dois participantes.",400)

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        INSERT INTO duplas (
            participante_1,
            participante_2
        )
        VALUES (?, ?)
        """,
        (
            participante_1,
            participante_2
        ))

    dupla_id = cursor.lastrowid
    conexao.commit()
    conexao.close()

    return redirect(url_for("participantes.dupla_criada",dupla_id=dupla_id))

# CONFIRMAÇÃO DO TIME

@participantes_bp.route("/dupla-criada/<int:dupla_id>")
def dupla_criada(dupla_id):

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT
            id,
            participante_1,
            participante_2
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()
    conexao.close()

    if dupla is None:
        return ("Time não encontrado.",404)

    return render_template("dupla_criada.html",dupla=dupla)

# ENTRAR EM TIME EXISTENTE

@participantes_bp.route("/entrar-dupla",methods=["POST"])
def entrar_dupla():

    dupla_id = request.form.get("dupla_id")
    if not dupla_id:
        return ("Informe o número do time.",400)

    try:
        dupla_id = int(dupla_id)

    except ValueError:
        return ("Número do time inválido.",400)

    if dupla_id <= 0:
        return ("Número do time inválido.",400)

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT
            id,
            participante_1,
            participante_2
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()
    conexao.close()

    if dupla is None:
        return ("Time não encontrado.",404)

    return redirect(
        url_for("participantes.quiz",dupla_id=dupla["id"]))

# QUIZ

@participantes_bp.route("/quiz/<int:dupla_id>")
def quiz(dupla_id):

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT
            id,
            participante_1,
            participante_2
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()

    if dupla is None:
        conexao.close()

        return ("Time não encontrado.",404)

    cursor.execute(
        """
        SELECT
            id,
            enunciado,
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e
        FROM perguntas
        WHERE id NOT IN (
            SELECT pergunta_id
            FROM respostas
            WHERE dupla_id = ?
        )
        ORDER BY id
        LIMIT 1
        """,
        (dupla_id,))

    pergunta = cursor.fetchone()
    conexao.close()

    if pergunta is None:
        return redirect(
            url_for(
                "participantes.aguardando",
                dupla_id=dupla_id))

    return render_template("quiz.html",dupla=dupla,dupla_id=dupla_id,pergunta=pergunta)

# RESPOSTA

@participantes_bp.route("/responder",methods=["POST"])
def responder():

    dupla_id = request.form.get("dupla_id")
    pergunta_id = request.form.get("pergunta_id")
    alternativa = (request.form.get("alternativa") or "").strip().upper()

    if (not dupla_id or not pergunta_id or not alternativa ):
        return ("Dados da resposta incompletos.",400)

    try:
        dupla_id = int(dupla_id)
        pergunta_id = int(pergunta_id)

    except ValueError:
        return ("Dados da resposta inválidos.",400)

    if alternativa not in [
        "A",
        "B",
        "C",
        "D",
        "E"
    ]:
        return ("Alternativa inválida.",400)

    conexao = conectar()
    cursor = conexao.cursor()

    # Verifica se o time existe
    cursor.execute(
        """
        SELECT id
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()
    if dupla is None:
        conexao.close()

        return ("Time não encontrado.",404)

    # Busca a próxima pergunta não respondida
    cursor.execute(
        """
        SELECT
            id,
            alternativa_correta
        FROM perguntas
        WHERE id NOT IN (
            SELECT pergunta_id
            FROM respostas
            WHERE dupla_id = ?
        )
        ORDER BY id
        LIMIT 1
        """,
        (dupla_id,))

    pergunta_atual = cursor.fetchone()

    if pergunta_atual is None:
        conexao.close()

        return redirect(
            url_for(
                "participantes.aguardando",
                dupla_id=dupla_id))

    # Impede responder uma pergunta diferente da atual
    if pergunta_id != pergunta_atual["id"]:
        conexao.close()

        return ("Esta não é a pergunta atual do time.",400)

    alternativa_correta = (pergunta_atual["alternativa_correta"])
    correta = int(alternativa == alternativa_correta)

    pontos = (
        100
        if correta
        else 0)

    cursor.execute(
        """
        INSERT INTO respostas (
            dupla_id,
            pergunta_id,
            alternativa_escolhida,
            correta,
            pontos
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            dupla_id,
            pergunta_id,
            alternativa,
            correta,
            pontos
        ))

    conexao.commit()
    conexao.close()

    return redirect(url_for("participantes.quiz",dupla_id=dupla_id))

# AGUARDANDO RESULTADO

@participantes_bp.route("/aguardando/<int:dupla_id>")
def aguardando(dupla_id):

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT
            id,
            participante_1,
            participante_2
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()

    if dupla is None:
        conexao.close()

        return ("Time não encontrado.",404)

    cursor.execute(
        """
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """)

    configuracao = cursor.fetchone()
    conexao.close()

    if (configuracao is not None and configuracao["ranking_liberado"] == 1):
        return redirect( url_for("participantes.ranking"))

    return render_template("aguardando.html",dupla=dupla)

# RANKING

@participantes_bp.route("/ranking")
def ranking():

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """)

    configuracao = cursor.fetchone()

    conexao.close()

    if configuracao is None:
        return ("Configuração do ranking não encontrada.",500)

    if configuracao["ranking_liberado"] == 0:
        return ("O ranking ainda não foi liberado.",403)

    classificacao = buscar_ranking()

    return render_template("ranking.html",ranking=classificacao)