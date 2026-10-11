from conexao import conectar

conexao = conectar()
cursor = conexao.cursor()

cursor.execute("SELECT * FROM duplas")
duplas = cursor.fetchall()

for dupla in duplas:
  print(dupla)

conexao.close()
