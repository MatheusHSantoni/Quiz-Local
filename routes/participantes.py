from flask import Blueprint, render_template, request, redirect, url_for

from database.conexao import conectar
from services.ranking import buscar_ranking


participantes_bp = Blueprint("participantes", __name__)


@participantes_bp.route("/")
def index():
    return render_template("index.html")


@participantes_bp.route("/entrar", methods=["POST"])
def entrar():
    participante_1 = (request.form.get("participante_1") or "").strip()
    participante_2 = (request.form.get("participante_2") or "").strip()

    if not participante_1 or not participante_2:
        return "Informe o nome dos dois participantes.", 400

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
        (participante_1, participante_2))

    dupla_id = cursor.lastrowid

    conexao.commit()
    conexao.close()

    return redirect(
        url_for(
            "participantes.quiz",
            dupla_id=dupla_id))


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
        return "Dupla não encontrada.", 404

    cursor.execute(
        """
        SELECT *
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

    return render_template(
        "quiz.html",
        dupla=dupla,
        dupla_id=dupla_id,
        pergunta=pergunta
    )


@participantes_bp.route("/responder", methods=["POST"])
def responder():
    dupla_id = request.form.get("dupla_id")
    pergunta_id = request.form.get("pergunta_id")
    alternativa = request.form.get("alternativa")

    if not dupla_id or not pergunta_id or not alternativa:
        return "Dados da resposta incompletos.", 400

    if alternativa not in ["A", "B", "C", "D", "E"]:
        return "Alternativa inválida.", 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT alternativa_correta
        FROM perguntas
        WHERE id = ?
        """,
        (pergunta_id,))

    resultado = cursor.fetchone()

    if resultado is None:
        conexao.close()
        return "Pergunta não encontrada.", 404

    alternativa_correta = resultado["alternativa_correta"]

    if alternativa == alternativa_correta:
        correta = 1
        pontos = 100
    else:
        correta = 0
        pontos = 0

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
            pontos))

    conexao.commit()
    conexao.close()

    return redirect(
        url_for(
            "participantes.quiz",
            dupla_id=dupla_id))


@participantes_bp.route("/aguardando/<int:dupla_id>")
def aguardando(dupla_id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT id, participante_1, participante_2
        FROM duplas
        WHERE id = ?
        """,
        (dupla_id,))

    dupla = cursor.fetchone()

    if dupla is None:
        conexao.close()
        return "Dupla não encontrada.", 404

    cursor.execute("""
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """)

    configuracao = cursor.fetchone()
    conexao.close()

    if (configuracao is not None and configuracao["ranking_liberado"] == 1):
        return redirect(url_for("participantes.ranking"))

    return render_template("aguardando.html", dupla=dupla)

@participantes_bp.route("/ranking")
def ranking():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """
    )

    configuracao = cursor.fetchone()

    conexao.close()

    if configuracao is None:
        return "Configuração do ranking não encontrada.", 500

    if configuracao["ranking_liberado"] == 0:
        return "O ranking ainda não foi liberado.", 403

    classificacao = buscar_ranking()

    return render_template(
        "ranking.html",
        ranking=classificacao
    )