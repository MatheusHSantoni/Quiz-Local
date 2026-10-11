from flask import Blueprint, render_template, request
from database.conexao import conectar

participantes_bp = Blueprint("participantes", __name__)


@participantes_bp.route("/")
def index():
    return render_template("index.html")


@participantes_bp.route("/jogo", methods=["POST"])
def jogo():
    nome_dupla = request.form.get("dupla")

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "INSERT INTO duplas (nome_dupla) VALUES (?)",
        (nome_dupla,)
    )

    dupla_id = cursor.lastrowid

    cursor.execute(
        "SELECT * FROM perguntas LIMIT 1"
    )

    pergunta = cursor.fetchone()

    conexao.commit()
    conexao.close()

    return render_template(
        "jogo.html",
        nome_dupla=nome_dupla,
        dupla_id=dupla_id,
        pergunta=pergunta
    )

@participantes_bp.route("/responder", methods=["POST"])
def responder():
    dupla_id = request.form.get("dupla_id")
    pergunta_id = request.form.get("pergunta_id")
    alternativa = request.form.get("alternativa")

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        INSERT INTO respostas (
            dupla_id,
            pergunta_id,
            alternativa_escolhida
        )
        VALUES (?, ?, ?)
        """,
        (dupla_id, pergunta_id, alternativa))

    conexao.commit()
    conexao.close()

    return "Resposta salva com sucesso."