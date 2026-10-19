from database.conexao import conectar

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
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    (
        "Qual é a capital do Brasil?",
        "São Paulo",
        "Rio de Janeiro",
        "Brasília",
        "Salvador",
        "Belo Horizonte",
        "C"
    ))


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
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    (
        "Quanto é 10 × 5?",
        "15",
        "25",
        "40",
        "50",
        "100",
        "D"
    ))

conexao.commit()
conexao.close()

print("Perguntas inseridas com sucesso.")