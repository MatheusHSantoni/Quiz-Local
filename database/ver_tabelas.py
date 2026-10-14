from conexao import conectar


conexao = conectar()
cursor = conexao.cursor()

cursor.execute("""
    PRAGMA table_info(duplas)
    """)

colunas = cursor.fetchall()

for coluna in colunas:
    print(dict(coluna))

conexao.close()