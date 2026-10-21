import os
from functools import wraps
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from pwdlib import PasswordHash
from werkzeug.utils import secure_filename

from database.conexao import conectar
from services.ranking import buscar_ranking, resumo_ranking, ranking_pode_ser_liberado


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
password_hash = PasswordHash.recommended()

AREAS = ("LC", "CH", "CN", "MT")
TIPOS = ("PRINCIPAL", "RESERVA")
ALTERNATIVAS = {"A", "B", "C", "D", "E"}
EXTENSOES = {"png", "jpg", "jpeg", "webp"}


def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):
        if not session.get("admin_logado"):
            return redirect(url_for("admin.login"))

        return funcao(*args, **kwargs)

    return verificar_login


def alternativas_sao_unicas(alternativas):
    norm = [" ".join(a.split()).casefold() for a in alternativas]
    return len(norm) == len(set(norm))


def salvar_imagem(arquivo):
    if not arquivo or not arquivo.filename:
        return None

    nome = secure_filename(arquivo.filename)
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""

    if ext not in EXTENSOES:
        raise ValueError("Imagem inválida. Use PNG, JPG, JPEG ou WEBP.")

    pasta = Path(current_app.root_path) / "static" / "uploads"
    pasta.mkdir(parents=True, exist_ok=True)

    nome_final = f"{uuid4().hex}.{ext}"
    arquivo.save(pasta / nome_final)

    return f"uploads/{nome_final}"


def dados_pergunta_form():
    dados = {
        "area": (request.form.get("area") or "").upper(),
        "tipo": (request.form.get("tipo") or "").upper(),
        "ordem": request.form.get("ordem") or "",
        "ativa": 1 if request.form.get("ativa") == "1" else 0,
        "enunciado": (request.form.get("enunciado") or "").strip(),
        "alternativa_a": (request.form.get("alternativa_a") or "").strip(),
        "alternativa_b": (request.form.get("alternativa_b") or "").strip(),
        "alternativa_c": (request.form.get("alternativa_c") or "").strip(),
        "alternativa_d": (request.form.get("alternativa_d") or "").strip(),
        "alternativa_e": (request.form.get("alternativa_e") or "").strip(),
        "alternativa_correta": (request.form.get("alternativa_correta") or "").upper(),
    }

    try:
        dados["ordem"] = int(dados["ordem"])
    except (TypeError, ValueError):
        dados["ordem"] = 0

    return dados


def validar_pergunta(d, validar_ordem=True):
    obrigatorios = [
        d["enunciado"],
        d["alternativa_a"],
        d["alternativa_b"],
        d["alternativa_c"],
        d["alternativa_d"],
        d["alternativa_e"],
    ]

    if not all(obrigatorios):
        return "Preencha todos os campos obrigatórios."

    if d["area"] not in AREAS:
        return "Área inválida."

    if d["tipo"] not in TIPOS:
        return "Tipo inválido."

    if validar_ordem and d["ordem"] < 1:
        return "A ordem deve ser maior ou igual a 1."

    if d["alternativa_correta"] not in ALTERNATIVAS:
        return "Alternativa correta inválida."

    alternativas = [d[f"alternativa_{x}"] for x in "abcde"]

    if not alternativas_sao_unicas(alternativas):
        return "As alternativas precisam ser diferentes entre si."

    return None


def proxima_ordem(cursor, area, tipo, ignorar_id=None):
    sql = """
        SELECT COALESCE(MAX(ordem), 0) + 1 AS proxima
        FROM perguntas
        WHERE area=%s AND tipo=%s
    """

    params = [area, tipo]

    if ignorar_id is not None:
        sql += " AND id<>%s"
        params.append(ignorar_id)

    return cursor.execute(sql, params).fetchone()["proxima"]


def ordem_disponivel(cursor, area, tipo, ordem, ignorar_id=None):
    sql = """
        SELECT COUNT(*) AS total
        FROM perguntas
        WHERE area=%s
          AND tipo=%s
          AND ordem=%s
    """

    params = [area, tipo, ordem]

    if ignorar_id is not None:
        sql += " AND id<>%s"
        params.append(ignorar_id)

    return cursor.execute(sql, params).fetchone()["total"] == 0


def pergunta_usada_em_desempate(con, pergunta_id):
    return con.execute(
        """
        SELECT 1
        FROM desempate_rodadas
        WHERE pergunta_id=%s
        LIMIT 1
        """,
        (pergunta_id,),
    ).fetchone() is not None


def dupla_participou_desempate(con, dupla_id):
    return con.execute(
        """
        SELECT 1
        FROM desempate_membros
        WHERE dupla_id=%s
        LIMIT 1
        """,
        (dupla_id,),
    ).fetchone() is not None


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""

        admin_usuario = os.environ.get("ADMIN_USUARIO", "admin")
        admin_senha = os.environ.get("ADMIN_SENHA", "admin123")

        if usuario == admin_usuario and senha == admin_senha:
            session.clear()
            session["admin_logado"] = True

            return redirect(url_for("admin.dashboard"))

        flash("Usuário ou senha inválidos.")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.clear()

    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@admin_obrigatorio
def dashboard():
    con = conectar()
    c = con.cursor()

    total_perguntas = c.execute(
        "SELECT COUNT(*) AS total FROM perguntas"
    ).fetchone()["total"]

    total_duplas = c.execute(
        "SELECT COUNT(*) AS total FROM duplas"
    ).fetchone()["total"]

    config = c.execute("""
    SELECT ranking_liberado,
           etapa_ativa,
           fim_etapa,
           CURRENT_TIMESTAMP AS agora
    FROM configuracoes
    WHERE id=1
    """).fetchone()

    prontidao = {}

    for area in AREAS:
        prontidao[area] = c.execute(
            """
            SELECT COUNT(*) AS total
            FROM perguntas
            WHERE area=%s
              AND tipo='PRINCIPAL'
              AND ativa=1
            """,
            (area,),
        ).fetchone()["total"]

    con.close()

    resumo = resumo_ranking()

    return render_template(
        "admin/dashboard.html",
        total_perguntas=total_perguntas,
        total_duplas=total_duplas,
        ranking_liberado=bool(config["ranking_liberado"]),
        fim_etapa=config["fim_etapa"],
        agora=config["agora"],
        etapa_ativa=config["etapa_ativa"],
        prontidao=prontidao,
        resumo_ranking=resumo,
    )


@admin_bp.route("/etapa/<int:etapa>", methods=["POST"])
@admin_obrigatorio
def definir_etapa(etapa):
    if etapa not in (0, 1, 2):
        return ("Etapa inválida.", 400)

    if etapa in (1, 2):
        areas = ("LC", "CH") if etapa == 1 else ("CN", "MT")

        con = conectar()
        c = con.cursor()

        faltas = []

        for area in areas:
            n = c.execute(
                """
                SELECT COUNT(*) AS total
                FROM perguntas
                WHERE area=%s
                  AND tipo='PRINCIPAL'
                  AND ativa=1
                """,
                (area,),
            ).fetchone()["total"]

            if n < 2:
                faltas.append(f"{area}: {n}/2")

        if faltas:
            con.close()

            flash(
                "Etapa não liberada. Faltam questões principais ativas: "
                + ", ".join(faltas)
            )

            return redirect(url_for("admin.dashboard"))

        c.execute(
            """
            UPDATE configuracoes
            SET etapa_ativa=%s,
                fim_etapa=NULL,
                ranking_liberado=0
            WHERE id=1
            """,
            (etapa,),
        )

        con.commit()
        con.close()

    else:
        con = conectar()

        con.execute("""
            UPDATE configuracoes
            SET etapa_ativa=0,
                fim_etapa=NULL
            WHERE id=1
        """)

        con.commit()
        con.close()

    flash("Etapa atualizada com sucesso.")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/perguntas")
@admin_obrigatorio
def perguntas():
    con = conectar()

    lista = con.execute("""
        SELECT p.*, COUNT(r.id) AS total_respostas
        FROM perguntas p
        LEFT JOIN respostas r ON r.pergunta_id=p.id
        GROUP BY p.id
        ORDER BY
            CASE p.area
                WHEN 'LC' THEN 1
                WHEN 'CH' THEN 2
                WHEN 'CN' THEN 3
                ELSE 4
            END,
            CASE p.tipo
                WHEN 'PRINCIPAL' THEN 1
                ELSE 2
            END,
            p.ordem,
            p.id
    """).fetchall()

    con.close()

    return render_template(
        "admin/perguntas.html",
        perguntas=lista,
    )


@admin_bp.route("/perguntas/nova", methods=["GET", "POST"])
@admin_obrigatorio
def nova_pergunta():
    if request.method == "POST":
        d = dados_pergunta_form()
        erro = validar_pergunta(d, validar_ordem=False)

        if erro:
            flash(erro)

            return render_template(
                "admin/nova_pergunta.html",
                dados=d,
            )

        try:
            imagem = salvar_imagem(request.files.get("imagem"))

        except ValueError as e:
            flash(str(e))

            return render_template(
                "admin/nova_pergunta.html",
                dados=d,
            )

        con = conectar()
        c = con.cursor()

        # A ordem é automática dentro de cada área/tipo para evitar duplicidades.
        d["ordem"] = proxima_ordem(
            c,
            d["area"],
            d["tipo"],
        )

        # Questões de reserva ficam fora do quiz normal até serem liberadas.
        d["ativa"] = 1 if d["tipo"] == "PRINCIPAL" else 0

        c.execute(
            """
            INSERT INTO perguntas (
                area,
                tipo,
                ordem,
                ativa,
                enunciado,
                alternativa_a,
                alternativa_b,
                alternativa_c,
                alternativa_d,
                alternativa_e,
                alternativa_correta,
                imagem
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                d["area"],
                d["tipo"],
                d["ordem"],
                d["ativa"],
                d["enunciado"],
                d["alternativa_a"],
                d["alternativa_b"],
                d["alternativa_c"],
                d["alternativa_d"],
                d["alternativa_e"],
                d["alternativa_correta"],
                imagem,
            ),
        )

        con.commit()
        con.close()

        flash("Pergunta cadastrada com sucesso.")

        return redirect(url_for("admin.perguntas"))

    return render_template(
        "admin/nova_pergunta.html",
        dados=None,
    )


@admin_bp.route("/perguntas/<int:pergunta_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar_pergunta(pergunta_id):
    con = conectar()

    pergunta = con.execute(
        """
        SELECT *
        FROM perguntas
        WHERE id=%s
        """,
        (pergunta_id,),
    ).fetchone()

    if not pergunta:
        con.close()

        return ("Pergunta não encontrada.", 404)

    if request.method == "POST":
        d = dados_pergunta_form()
        erro = validar_pergunta(d)

        if erro:
            con.close()
            flash(erro)

            return render_template(
                "admin/editar_pergunta.html",
                pergunta={**dict(pergunta), **d},
            )

        imagem = pergunta["imagem"]

        try:
            nova = salvar_imagem(request.files.get("imagem"))

            if nova:
                imagem = nova

        except ValueError as e:
            con.close()
            flash(str(e))

            return render_template(
                "admin/editar_pergunta.html",
                pergunta=pergunta,
            )

        if not ordem_disponivel(
            con.cursor(),
            d["area"],
            d["tipo"],
            d["ordem"],
            pergunta_id,
        ):
            con.close()

            flash(
                "Já existe uma questão dessa área e tipo com essa ordem."
            )

            return render_template(
                "admin/editar_pergunta.html",
                pergunta={**dict(pergunta), **d},
            )

        con.execute(
            """
            UPDATE perguntas
            SET area=%s,
                tipo=%s,
                ordem=%s,
                ativa=%s,
                enunciado=%s,
                alternativa_a=%s,
                alternativa_b=%s,
                alternativa_c=%s,
                alternativa_d=%s,
                alternativa_e=%s,
                alternativa_correta=%s,
                imagem=%s
            WHERE id=%s
            """,
            (
                d["area"],
                d["tipo"],
                d["ordem"],
                d["ativa"],
                d["enunciado"],
                d["alternativa_a"],
                d["alternativa_b"],
                d["alternativa_c"],
                d["alternativa_d"],
                d["alternativa_e"],
                d["alternativa_correta"],
                imagem,
                pergunta_id,
            ),
        )

        con.commit()
        con.close()

        flash("Pergunta atualizada com sucesso.")

        return redirect(url_for("admin.perguntas"))

    con.close()

    return render_template(
        "admin/editar_pergunta.html",
        pergunta=pergunta,
    )


@admin_bp.route("/perguntas/<int:pergunta_id>")
@admin_obrigatorio
def visualizar_pergunta(pergunta_id):
    con = conectar()

    pergunta = con.execute(
        """
        SELECT p.*, COUNT(r.id) AS total_respostas
        FROM perguntas p
        LEFT JOIN respostas r ON r.pergunta_id=p.id
        WHERE p.id=%s
        GROUP BY p.id
        """,
        (pergunta_id,),
    ).fetchone()

    con.close()

    if not pergunta:
        return ("Pergunta não encontrada.", 404)

    return render_template(
        "admin/pergunta_detalhe.html",
        pergunta=pergunta,
    )


@admin_bp.route("/perguntas/<int:pergunta_id>/alternar-status", methods=["POST"])
@admin_obrigatorio
def alternar_status_pergunta(pergunta_id):
    con = conectar()
    c = con.cursor()

    pergunta = c.execute(
        """
        SELECT id, area, tipo, ordem, ativa
        FROM perguntas
        WHERE id=%s
        """,
        (pergunta_id,),
    ).fetchone()

    if not pergunta:
        con.close()

        return ("Pergunta não encontrada.", 404)

    # Na interface operacional, ATIVA = principal do quiz; RESERVA = fora do quiz normal.
    if pergunta["tipo"] == "PRINCIPAL" and pergunta["ativa"]:
        novo_tipo, nova_ativa = "RESERVA", 0
    else:
        novo_tipo, nova_ativa = "PRINCIPAL", 1

    nova_ordem = pergunta["ordem"]

    if not ordem_disponivel(
        c,
        pergunta["area"],
        novo_tipo,
        nova_ordem,
        pergunta_id,
    ):
        nova_ordem = proxima_ordem(
            c,
            pergunta["area"],
            novo_tipo,
            pergunta_id,
        )

    c.execute(
        """
        UPDATE perguntas
        SET tipo=%s,
            ativa=%s,
            ordem=%s
        WHERE id=%s
        """,
        (
            novo_tipo,
            nova_ativa,
            nova_ordem,
            pergunta_id,
        ),
    )

    con.commit()
    con.close()

    flash(
        "Questão ativada."
        if nova_ativa
        else "Questão movida para a reserva."
    )

    return redirect(url_for("admin.perguntas"))


@admin_bp.route("/perguntas/<int:pergunta_id>/excluir", methods=["POST"])
@admin_obrigatorio
def excluir_pergunta(pergunta_id):
    con = conectar()

    try:
        con.execute(
            """
            DELETE FROM respostas
            WHERE pergunta_id=%s
            """,
            (pergunta_id,),
        )

        con.execute(
            """
            DELETE FROM questoes_iniciadas
            WHERE pergunta_id=%s
            """,
            (pergunta_id,),
        )

        con.execute(
            """
            DELETE FROM desempate_rodadas
            WHERE pergunta_id=%s
            """,
            (pergunta_id,),
        )

        con.execute(
            """
            DELETE FROM perguntas
            WHERE id=%s
            """,
            (pergunta_id,),
        )

        con.commit()

    except Exception:
        con.rollback()
        con.close()

        raise

    con.close()

    flash("Pergunta excluída com sucesso.")

    return redirect(url_for("admin.perguntas"))


@admin_bp.route("/duplas")
@admin_obrigatorio
def duplas():
    con = conectar()

    lista = con.execute("""
        SELECT d.*,
               COUNT(r.id) AS respostas,
               COALESCE(SUM(r.pontos),0) AS pontos,

               COALESCE(
                   SUM(
                       CASE
                           WHEN p.area IN ('LC','CH')
                           THEN r.pontos
                           ELSE 0
                       END
                   ),
                   0
               ) AS pontos_e1,

               COALESCE(
                   SUM(
                       CASE
                           WHEN p.area IN ('CN','MT')
                           THEN r.pontos
                           ELSE 0
                       END
                   ),
                   0
               ) AS pontos_e2,

               SUM(
                   CASE
                       WHEN p.area IN ('LC','CH')
                       THEN 1
                       ELSE 0
                   END
               ) AS respostas_e1,

               SUM(
                   CASE
                       WHEN p.area IN ('CN','MT')
                       THEN 1
                       ELSE 0
                   END
               ) AS respostas_e2

        FROM duplas d
        LEFT JOIN respostas r ON r.dupla_id=d.id
        LEFT JOIN perguntas p ON p.id=r.pergunta_id

        GROUP BY d.id
        ORDER BY d.id
    """).fetchall()

    con.close()

    return render_template(
        "admin/duplas.html",
        duplas=lista,
    )


@admin_bp.route("/duplas/nova", methods=["GET", "POST"])
@admin_obrigatorio
def nova_dupla():
    if request.method == "POST":
        p1 = (request.form.get("participante_1") or "").strip()
        p2 = (request.form.get("participante_2") or "").strip()
        senha = request.form.get("senha") or ""

        if not p1 or not p2 or len(senha) < 6:
            flash(
                "Informe os dois participantes e uma senha com pelo menos 6 caracteres."
            )

        else:
            con = conectar()

            con.execute(
                """
                INSERT INTO duplas (
                    participante_1,
                    participante_2,
                    senha_hash
                )
                VALUES (%s,%s,%s)
                """,
                (
                    p1,
                    p2,
                    password_hash.hash(senha),
                ),
            )

            con.commit()
            con.close()

            flash("Dupla cadastrada.")

            return redirect(url_for("admin.duplas"))

    return render_template(
        "admin/dupla_form.html",
        dupla=None,
    )


@admin_bp.route("/duplas/<int:dupla_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def editar_dupla(dupla_id):
    con = conectar()

    dupla = con.execute(
        """
        SELECT *
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    if not dupla:
        con.close()

        return ("Dupla não encontrada.", 404)

    if request.method == "POST":
        p1 = (request.form.get("participante_1") or "").strip()
        p2 = (request.form.get("participante_2") or "").strip()

        if not p1 or not p2:
            con.close()

            flash("Informe os dois participantes.")

            return render_template(
                "admin/dupla_form.html",
                dupla=dupla,
            )

        con.execute(
            """
            UPDATE duplas
            SET participante_1=%s,
                participante_2=%s
            WHERE id=%s
            """,
            (
                p1,
                p2,
                dupla_id,
            ),
        )

        con.commit()
        con.close()

        flash("Dupla atualizada.")

        return redirect(url_for("admin.duplas"))

    con.close()

    return render_template(
        "admin/dupla_form.html",
        dupla=dupla,
    )


@admin_bp.route("/duplas/<int:dupla_id>/senha", methods=["GET", "POST"])
@admin_obrigatorio
def redefinir_senha_dupla(dupla_id):
    con = conectar()

    dupla = con.execute(
        """
        SELECT id, participante_1, participante_2
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    if not dupla:
        con.close()

        return ("Dupla não encontrada.", 404)

    if request.method == "POST":
        senha = request.form.get("senha") or ""
        confirmar = request.form.get("confirmar_senha") or ""

        if len(senha) < 6:
            flash(
                "A nova senha deve ter pelo menos 6 caracteres."
            )

        elif senha != confirmar:
            flash("As senhas não coincidem.")

        else:
            con.execute(
                """
                UPDATE duplas
                SET senha_hash=%s
                WHERE id=%s
                """,
                (
                    password_hash.hash(senha),
                    dupla_id,
                ),
            )

            con.commit()
            con.close()

            flash("Senha redefinida com sucesso.")

            return redirect(url_for("admin.duplas"))

    con.close()

    return render_template(
        "admin/redefinir_senha.html",
        dupla=dupla,
    )


@admin_bp.route("/duplas/<int:dupla_id>/respostas")
@admin_obrigatorio
def respostas_dupla(dupla_id):
    con = conectar()

    dupla = con.execute(
        """
        SELECT id, participante_1, participante_2
        FROM duplas
        WHERE id=%s
        """,
        (dupla_id,),
    ).fetchone()

    if not dupla:
        con.close()

        return ("Dupla não encontrada.", 404)

    respostas = con.execute(
        """
        SELECT r.*,
               p.area,
               p.ordem,
               p.enunciado,
               p.alternativa_correta,

               CASE r.alternativa_escolhida
                   WHEN 'A' THEN p.alternativa_a
                   WHEN 'B' THEN p.alternativa_b
                   WHEN 'C' THEN p.alternativa_c
                   WHEN 'D' THEN p.alternativa_d
                   WHEN 'E' THEN p.alternativa_e
               END AS texto_escolhido,

               CASE p.alternativa_correta
                   WHEN 'A' THEN p.alternativa_a
                   WHEN 'B' THEN p.alternativa_b
                   WHEN 'C' THEN p.alternativa_c
                   WHEN 'D' THEN p.alternativa_d
                   WHEN 'E' THEN p.alternativa_e
               END AS texto_correto

        FROM respostas r
        JOIN perguntas p ON p.id=r.pergunta_id

        WHERE r.dupla_id=%s

        ORDER BY
            CASE p.area
                WHEN 'LC' THEN 1
                WHEN 'CH' THEN 2
                WHEN 'CN' THEN 3
                ELSE 4
            END,
            p.ordem,
            r.id
        """,
        (dupla_id,),
    ).fetchall()

    con.close()

    return render_template(
        "admin/respostas_dupla.html",
        dupla=dupla,
        respostas=respostas,
    )


@admin_bp.route("/duplas/<int:dupla_id>/excluir", methods=["POST"])
@admin_obrigatorio
def excluir_dupla(dupla_id):
    con = conectar()

    try:
        con.execute(
            """
            DELETE FROM respostas
            WHERE dupla_id=%s
            """,
            (dupla_id,),
        )

        con.execute(
            """
            DELETE FROM questoes_iniciadas
            WHERE dupla_id=%s
            """,
            (dupla_id,),
        )

        con.execute(
            """
            DELETE FROM desempate_membros
            WHERE dupla_id=%s
            """,
            (dupla_id,),
        )

        con.execute(
            """
            UPDATE desempates
            SET vencedor_dupla_id=NULL
            WHERE vencedor_dupla_id=%s
            """,
            (dupla_id,),
        )

        con.execute(
            """
            DELETE FROM duplas
            WHERE id=%s
            """,
            (dupla_id,),
        )

        con.commit()

    except Exception:
        con.rollback()
        con.close()

        raise

    con.close()

    flash("Dupla excluída.")

    return redirect(url_for("admin.duplas"))


@admin_bp.route("/ranking")
@admin_obrigatorio
def ranking_preview():
    classificacao = buscar_ranking()
    resumo = resumo_ranking()

    return render_template(
        "admin/ranking_preview.html",
        ranking=classificacao,
        resumo=resumo,
    )


@admin_bp.route("/ranking/<acao>", methods=["POST"])
@admin_obrigatorio
def ranking_acao(acao):
    if acao not in ("liberar", "bloquear"):
        return ("Ação inválida.", 400)

    if acao == "liberar":
        pode, motivo = ranking_pode_ser_liberado()

        if not pode:
            flash(motivo)

            return redirect(url_for("admin.dashboard"))

    valor = 1 if acao == "liberar" else 0

    con = conectar()

    con.execute(
        """
        UPDATE configuracoes
        SET ranking_liberado=%s
        WHERE id=1
        """,
        (valor,),
    )

    con.commit()
    con.close()

    flash(
        "Ranking liberado."
        if valor
        else "Ranking bloqueado."
    )

    return redirect(url_for("admin.dashboard"))


# BLOCO 5 — TIMER

@admin_bp.route("/timer/iniciar", methods=["POST"])
@admin_obrigatorio
def iniciar_timer():
    con = conectar()

    configuracao = con.execute("""
        SELECT etapa_ativa
        FROM configuracoes
        WHERE id=1
    """).fetchone()

    if configuracao is None:
        con.close()

        flash("Configuração do quiz não encontrada.")

        return redirect(url_for("admin.dashboard"))

    if configuracao["etapa_ativa"] not in (1, 2):
        con.close()

        flash("Libere uma etapa antes de iniciar o cronômetro.")

        return redirect(url_for("admin.dashboard"))

    con.execute("""
        UPDATE configuracoes
        SET fim_etapa = CURRENT_TIMESTAMP + INTERVAL '10 minutes'
        WHERE id=1
    """)

    con.commit()
    con.close()

    flash("Cronômetro de 10 minutos iniciado.")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/timer/encerrar", methods=["POST"])
@admin_obrigatorio
def encerrar_timer():
    con = conectar()

    con.execute("""
        UPDATE configuracoes
        SET fim_etapa = NULL
        WHERE id=1
    """)

    con.commit()
    con.close()

    flash("Cronômetro encerrado.")

    return redirect(url_for("admin.dashboard"))


# BLOCO 6 — MORTE SÚBITA

@admin_bp.route("/desempates")
@admin_obrigatorio
def desempates():
    from services.desempate import sessoes_pendentes

    return render_template(
        "admin/desempates.html",
        sessoes=sessoes_pendentes(),
    )


@admin_bp.route("/desempates/<int:desempate_id>/sortear", methods=["POST"])
@admin_obrigatorio
def sortear_desempate(desempate_id):
    from services.desempate import sortear_rodada

    ok, info = sortear_rodada(desempate_id)

    flash(
        f"Área sorteada: {info['area']}. Rodada {info['numero']} liberada."
        if ok
        else info
    )

    return redirect(
        url_for("admin.desempates")
    )


@admin_bp.route("/desempates/<int:desempate_id>/telao")
@admin_obrigatorio
def telao_desempate_admin(desempate_id):
    return redirect(
        url_for("participantes.telao_desempate",
            desempate_id=desempate_id,))