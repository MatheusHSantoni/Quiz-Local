from conexao import conectar

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
        alternativa_correta
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
        "Quanto é 2 + 2?",
        "2",
        "3",
        "4",
        "5",
        "C"
    )
)
conexao.commit()
conexao.close()

print("Pergunta inserida com sucesso.")