import os
from functools import wraps

from flask import (Blueprint,render_template,request,redirect,url_for,session,flash)
from database.conexao import conectar


admin_bp = Blueprint("admin",__name__,url_prefix="/admin")

# FUNÇÕES AUXILIARES

def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):

        if not session.get("admin_logado"):
            return redirect(
                url_for("admin.login"))

        return funcao(*args, **kwargs)

    return verificar_login


def alternativas_sao_unicas(alternativas):

    alternativas_normalizadas = [
        " ".join(alternativa.split()).casefold()
        for alternativa in alternativas]

    return (
        len(alternativas_normalizadas)
        == len(set(alternativas_normalizadas))    )


# LOGIN
@admin_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = (request.form.get("usuario") or "").strip()
        senha = (request.form.get("senha") or "")
        usuario_admin = os.environ.get("ADMIN_USUARIO","admin")
        senha_admin = os.environ.get("ADMIN_SENHA","admin123")

        if (usuario == usuario_admin and senha == senha_admin):
            session.clear()
            session["admin_logado"] = True

            return redirect(url_for("admin.dashboard"))

        flash("Usuário ou senha inválidos.")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():

    session.pop("admin_logado",None)

    return redirect(url_for("admin.login"))


# DASHBOARD


@admin_bp.route("/")
@admin_obrigatorio
def dashboard():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM perguntas
        """)

    total_perguntas = (cursor.fetchone()["total"])

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM duplas
        """)

    total_duplas = (cursor.fetchone()["total"])

    cursor.execute(
        """
        SELECT ranking_liberado
        FROM configuracoes
        WHERE id = 1
        """)

    configuracao = cursor.fetchone()
    conexao.close()
    ranking_liberado = (configuracao is not None and configuracao["ranking_liberado"] == 1)
    return render_template("admin/dashboard.html",total_perguntas=total_perguntas,total_duplas=total_duplas,ranking_liberado=ranking_liberado)

# PERGUNTAS

@admin_bp.route("/perguntas")
@admin_obrigatorio
def perguntas():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT
            id,
            enunciado,
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e,
            alternativa_correta
        FROM perguntas
        ORDER BY id DESC
        """)

    lista_perguntas = cursor.fetchall()
    conexao.close()
    return render_template("admin/perguntas.html",perguntas=lista_perguntas)


@admin_bp.route("/perguntas/nova",methods=["GET", "POST"])
@admin_obrigatorio
def nova_pergunta():

    if request.method == "POST":
        enunciado = (request.form.get("enunciado") or "").strip()
        alternativa_a = (request.form.get("alternativa_a") or "").strip()
        alternativa_b = (request.form.get("alternativa_b") or "").strip()
        alternativa_c = (request.form.get("alternativa_c") or "").strip()
        alternativa_d = (request.form.get("alternativa_d") or "").strip()
        alternativa_e = (request.form.get("alternativa_e") or "").strip()
        alternativa_correta = (request.form.get("alternativa_correta") or "").strip().upper()


        if not all([
            enunciado,
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e,
            alternativa_correta]):

            flash("Preencha todos os campos.")
            return render_template("admin/nova_pergunta.html")

        alternativas = [
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e]

        if not alternativas_sao_unicas(alternativas):
            flash("As alternativas precisam ser diferentes entre si.")
            return render_template("admin/nova_pergunta.html")

        if alternativa_correta not in [
            "A",
            "B",
            "C",
            "D",
            "E"
        ]:
            flash("Alternativa correta inválida.")
            return render_template("admin/nova_pergunta.html")


        conexao = conectar()
        cursor = conexao.cursor()
        cursor.execute(
            """
            INSERT INTO perguntas (
                enunciado,
                alternativa_a,
                alternativa_b,
                alternativa_c,
                alternativa_d,
                alternativa_e,
                alternativa_correta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                enunciado,
                alternativa_a,
                alternativa_b,
                alternativa_c,
                alternativa_d,
                alternativa_e,
                alternativa_correta))

        conexao.commit()
        conexao.close()
        flash("Pergunta cadastrada com sucesso.")
        return redirect(url_for("admin.perguntas"))


    return render_template("admin/nova_pergunta.html")


@admin_bp.route("/perguntas/<int:pergunta_id>/editar",methods=["GET", "POST"])
@admin_obrigatorio
def editar_pergunta(pergunta_id):

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT
            id,
            enunciado,
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e,
            alternativa_correta
        FROM perguntas
        WHERE id = ?
        """,
        (pergunta_id,))

    pergunta = cursor.fetchone()


    if pergunta is None:
        conexao.close()
        return ("Pergunta não encontrada.",404)


    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM respostas
        WHERE pergunta_id = ?
        """,
        (pergunta_id,))

    total_respostas = (cursor.fetchone()["total"])

    if total_respostas > 0:
        conexao.close()
        flash("Não é possível editar uma pergunta que já foi respondida.")
        return redirect(url_for("admin.perguntas"))


    if request.method == "POST":
        enunciado = (request.form.get("enunciado") or "").strip()
        alternativa_a = (request.form.get("alternativa_a") or "").strip()
        alternativa_b = (request.form.get("alternativa_b") or "").strip()
        alternativa_c = (request.form.get("alternativa_c") or "").strip()
        alternativa_d = (request.form.get("alternativa_d") or "").strip()
        alternativa_e = (request.form.get("alternativa_e") or "").strip()
        alternativa_correta = (request.form.get("alternativa_correta") or "").strip().upper()

        if not all([
            enunciado,
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e,
            alternativa_correta
        ]):
            conexao.close()
            flash("Preencha todos os campos.")
            return render_template("admin/editar_pergunta.html",pergunta=pergunta)

        alternativas = [
            alternativa_a,
            alternativa_b,
            alternativa_c,
            alternativa_d,
            alternativa_e
        ]


        if not alternativas_sao_unicas(alternativas):
            conexao.close()
            flash("As alternativas precisam ser diferentes entre si.")            
            return render_template("admin/editar_pergunta.html",pergunta=pergunta)

        if alternativa_correta not in [
            "A",
            "B",
            "C",
            "D",
            "E"
        ]:
            conexao.close()
            flash("Alternativa correta inválida.")
            return render_template("admin/editar_pergunta.html",pergunta=pergunta)


        cursor.execute(
            """
            UPDATE perguntas
            SET
                enunciado = ?,
                alternativa_a = ?,
                alternativa_b = ?,
                alternativa_c = ?,
                alternativa_d = ?,
                alternativa_e = ?,
                alternativa_correta = ?
            WHERE id = ?
            """,
            (
                enunciado,
                alternativa_a,
                alternativa_b,
                alternativa_c,
                alternativa_d,
                alternativa_e,
                alternativa_correta,
                pergunta_id
            ))

        conexao.commit()
        conexao.close()
        flash("Pergunta atualizada com sucesso.")
        return redirect(url_for("admin.perguntas"))

    conexao.close()

    return render_template("admin/editar_pergunta.html",pergunta=pergunta)


@admin_bp.route("/perguntas/<int:pergunta_id>/excluir",methods=["POST"])
@admin_obrigatorio
def excluir_pergunta(pergunta_id):

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM respostas
        WHERE pergunta_id = ?
        """,
        (pergunta_id,))

    total_respostas = (cursor.fetchone()["total"])


    if total_respostas > 0:
        conexao.close()

        flash("Não é possível excluir uma pergunta que já foi respondida.")
        return redirect(url_for("admin.perguntas"))


    cursor.execute(
        """
        DELETE FROM perguntas
        WHERE id = ?
        """,
        (pergunta_id,))
    
    conexao.commit()
    conexao.close()
    flash("Pergunta excluída com sucesso.")

    return redirect(url_for("admin.perguntas"))


# RANKING

@admin_bp.route("/ranking/liberar",methods=["POST"])
@admin_obrigatorio
def liberar_ranking():

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        UPDATE configuracoes
        SET ranking_liberado = 1
        WHERE id = 1
        """)

    conexao.commit()
    conexao.close()

    flash("Ranking liberado com sucesso.")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/ranking/bloquear",methods=["POST"])
@admin_obrigatorio
def bloquear_ranking():

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute(
        """
        UPDATE configuracoes
        SET ranking_liberado = 0
        WHERE id = 1
        """)

    conexao.commit()
    conexao.close()

    flash("Ranking bloqueado com sucesso.")

    return redirect(url_for("admin.dashboard"))