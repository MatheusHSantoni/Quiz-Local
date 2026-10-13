from database.conexao import conectar


def buscar_ranking():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT
            duplas.id,
            duplas.participante_1,
            duplas.participante_2,
            COALESCE(SUM(respostas.pontos), 0) AS total_pontos
        FROM duplas
        LEFT JOIN respostas
            ON respostas.dupla_id = duplas.id
        GROUP BY duplas.id
        ORDER BY total_pontos DESC
        """)

    ranking = cursor.fetchall()

    conexao.close()

    return ranking