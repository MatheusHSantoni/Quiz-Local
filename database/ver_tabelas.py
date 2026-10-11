from conexao import conectar

conexao = conectar()
cursor = conexao.cursor()

cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)

tabelas = cursor.fetchall()

for tabela in tabelas:
    print(tabela)

conexao.close()