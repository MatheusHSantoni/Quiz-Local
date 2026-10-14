import os

from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash)

from database.conexao import conectar


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin")


def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):

        if not session.get("admin_logado"):
            return redirect(url_for("admin.login"))

        return funcao(*args, **kwargs)

    return verificar_login


@admin_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""

        usuario_admin = os.environ.get(
            "ADMIN_USUARIO",
            "admin")

        senha_admin = os.environ.get(
            "ADMIN_SENHA",
            "admin123")

        if usuario == usuario_admin and senha == senha_admin:

            session["admin_logado"] = True

            return redirect(url_for("admin.dashboard"))

        flash("Usuário ou senha inválidos.")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():

    session.pop(
        "admin_logado",
        None)

    return redirect(
        url_for("admin.login"))


@admin_bp.route("/")
@admin_obrigatorio
def dashboard():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM perguntas
        """)

    total_perguntas = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM duplas
        """)

    total_duplas = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """)

    configuracao = cursor.fetchone()
    conexao.close()

    ranking_liberado = (
        configuracao is not None
        and configuracao["ranking_liberado"] == 1
    )

    return render_template(
        "admin/dashboard.html",
        total_perguntas=total_perguntas,
        total_duplas=total_duplas,
        ranking_liberado=ranking_liberado
    )