from database.conexao import conectar

conexao = conectar()
cursor = conexao.cursor()

cursor.execute(
    """
    SELECT
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = %s
    ORDER BY ordinal_position
    """,
    ("duplas",))

colunas = cursor.fetchall()

for coluna in colunas:
    print(dict(coluna))

conexao.close()