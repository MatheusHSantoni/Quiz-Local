from database.conexao import conectar

def limpar_dados_teste():
    resposta = input(
        "Isso vai apagar todas as duplas, respostas e desempates. "
        "Deseja continuar? [s/N]: "
    ).strip().lower()

    if resposta != "s":
        print("Operação cancelada.")
        return

    conexao = conectar()
    cursor = conexao.cursor()

    try:
        cursor.execute("""
            TRUNCATE TABLE
                questoes_iniciadas,
                respostas,
                desempate_membros,
                desempate_rodadas,
                desempates,
                duplas
            RESTART IDENTITY CASCADE
        """)

        cursor.execute("""
            UPDATE configuracoes
            SET ranking_liberado = 0,
                etapa_ativa = 0,
                fim_etapa = NULL
            WHERE id = 1""")

        conexao.commit()

        print("Dados de teste limpos com sucesso.")

    except Exception:
        conexao.rollback()
        raise

    finally:
        cursor.close()
        conexao.close()


if __name__ == "__main__":
    limpar_dados_teste()