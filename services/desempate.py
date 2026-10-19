import random
from database.conexao import conectar

AREAS = ("LC", "CH", "CN", "MT")


def _eligible_rows(con):
    return con.execute("""
        SELECT d.id, d.participante_1, d.participante_2,
               SUM(CASE WHEN r.fase='REGULAR' THEN r.pontos ELSE 0 END) pontos,
               SUM(CASE WHEN r.fase='REGULAR' THEN 1 ELSE 0 END) respostas
        FROM duplas d LEFT JOIN respostas r ON r.dupla_id=d.id
        GROUP BY d.id HAVING respostas >= 8
        ORDER BY pontos DESC, d.id
    """).fetchall()


def sincronizar_empates():
    """Cria sessões para grupos empatados do quiz regular, sem duplicá-las."""
    con = conectar(); c = con.cursor()
    rows = _eligible_rows(con)
    grupos = {}
    for r in rows:
        grupos.setdefault(r["pontos"], []).append(r)
    for pontos, membros in grupos.items():
        if len(membros) < 2:
            continue
        existente = c.execute("SELECT id FROM desempates WHERE pontos_regulares=? ORDER BY id DESC LIMIT 1", (pontos,)).fetchone()
        if existente:
            ids_existentes = {x["dupla_id"] for x in c.execute("SELECT dupla_id FROM desempate_membros WHERE desempate_id=?", (existente["id"],)).fetchall()}
            if ids_existentes == {m["id"] for m in membros}:
                continue
        c.execute("INSERT INTO desempates (pontos_regulares,status) VALUES (?, 'PENDENTE')", (pontos,))
        did = c.lastrowid
        for m in membros:
            c.execute("INSERT INTO desempate_membros (desempate_id,dupla_id,status) VALUES (?,?,'ATIVA')", (did,m["id"]))
    con.commit(); con.close()


def sessoes_pendentes():
    sincronizar_empates()
    con=conectar(); c=con.cursor()
    sessoes=c.execute("SELECT * FROM desempates WHERE status!='RESOLVIDO' ORDER BY pontos_regulares DESC,id").fetchall()
    out=[]
    for s in sessoes:
        membros=c.execute("""SELECT dm.*, d.participante_1,d.participante_2 FROM desempate_membros dm JOIN duplas d ON d.id=dm.dupla_id WHERE dm.desempate_id=? ORDER BY dm.status DESC,d.id""",(s["id"],)).fetchall()
        rodada=c.execute("""SELECT dr.*,p.area,p.enunciado FROM desempate_rodadas dr JOIN perguntas p ON p.id=dr.pergunta_id WHERE dr.desempate_id=? ORDER BY dr.numero DESC LIMIT 1""",(s["id"],)).fetchone()
        out.append({"sessao":dict(s),"membros":[dict(x) for x in membros],"rodada":dict(rodada) if rodada else None})
    con.close(); return out


def sessao_da_dupla(dupla_id):
    sincronizar_empates()
    con=conectar(); row=con.execute("""
      SELECT de.*,dm.status membro_status FROM desempates de JOIN desempate_membros dm ON dm.desempate_id=de.id
      WHERE dm.dupla_id=? AND de.status!='RESOLVIDO' ORDER BY de.id DESC LIMIT 1
    """,(dupla_id,)).fetchone(); con.close()
    return dict(row) if row else None


def rodada_atual(desempate_id):
    con=conectar(); r=con.execute("""SELECT dr.*,p.area,p.enunciado,p.alternativa_a,p.alternativa_b,p.alternativa_c,p.alternativa_d,p.alternativa_e,p.alternativa_correta,p.imagem
    FROM desempate_rodadas dr JOIN perguntas p ON p.id=dr.pergunta_id WHERE dr.desempate_id=? AND dr.status='ABERTA' ORDER BY dr.numero DESC LIMIT 1""",(desempate_id,)).fetchone(); con.close()
    return dict(r) if r else None


def sortear_rodada(desempate_id):
    con=conectar(); c=con.cursor()
    de=c.execute("SELECT * FROM desempates WHERE id=? AND status!='RESOLVIDO'",(desempate_id,)).fetchone()
    if not de: con.close(); return False,"Desempate não encontrado ou já resolvido."
    aberta=c.execute("SELECT id FROM desempate_rodadas WHERE desempate_id=? AND status='ABERTA'",(desempate_id,)).fetchone()
    if aberta: con.close(); return False,"A rodada atual ainda está em andamento."
    disponiveis=[]
    for area in AREAS:
        q=c.execute("""SELECT p.id FROM perguntas p WHERE p.area=? AND p.tipo='RESERVA'
          AND NOT EXISTS (SELECT 1 FROM desempate_rodadas dr WHERE dr.pergunta_id=p.id)
          ORDER BY p.ordem,p.id LIMIT 1""",(area,)).fetchone()
        if q: disponiveis.append((area,q["id"]))
    if not disponiveis: con.close(); return False,"Não há questões de reserva disponíveis para o desempate."
    area, pergunta_id=random.choice(disponiveis)
    numero=c.execute("SELECT COALESCE(MAX(numero),0)+1 n FROM desempate_rodadas WHERE desempate_id=?",(desempate_id,)).fetchone()["n"]
    c.execute("INSERT INTO desempate_rodadas (desempate_id,numero,area,pergunta_id,status) VALUES (?,?,?,?, 'ABERTA')",(desempate_id,numero,area,pergunta_id))
    c.execute("UPDATE desempates SET status='EM_ANDAMENTO' WHERE id=?",(desempate_id,))
    c.execute("UPDATE perguntas SET ativa=1 WHERE id=?",(pergunta_id,))
    con.commit(); con.close(); return True,{"area":area,"numero":numero}


def registrar_resposta(dupla_id, pergunta_id, alternativa):
    con=conectar(); c=con.cursor()
    rodada=c.execute("""SELECT dr.* FROM desempate_rodadas dr JOIN desempate_membros dm ON dm.desempate_id=dr.desempate_id
      WHERE dm.dupla_id=? AND dm.status='ATIVA' AND dr.pergunta_id=? AND dr.status='ABERTA' ORDER BY dr.id DESC LIMIT 1""",(dupla_id,pergunta_id)).fetchone()
    if not rodada: con.close(); return False,"Esta questão de desempate não está disponível para a dupla."
    p=c.execute("SELECT alternativa_correta FROM perguntas WHERE id=?",(pergunta_id,)).fetchone()
    correta=int(alternativa==p["alternativa_correta"])
    try:
        c.execute("INSERT INTO respostas (dupla_id,pergunta_id,alternativa_escolhida,correta,pontos,fase,rodada_desempate) VALUES (?,?,?,?,?,'DESEMPATE',?)",
                  (dupla_id,pergunta_id,alternativa,correta,100 if correta else 0,rodada["numero"]))
        con.commit()
    except Exception:
        con.rollback(); con.close(); return False,"Resposta já registrada ou inválida."
    _resolver_se_completa(con, rodada["id"])
    con.close(); return True,None


def _resolver_se_completa(con, rodada_id):
    c=con.cursor(); rd=c.execute("SELECT * FROM desempate_rodadas WHERE id=?",(rodada_id,)).fetchone()
    ativos=c.execute("SELECT dupla_id FROM desempate_membros WHERE desempate_id=? AND status='ATIVA'",(rd["desempate_id"],)).fetchall()
    respostas=c.execute("SELECT dupla_id,correta FROM respostas WHERE pergunta_id=? AND fase='DESEMPATE' AND rodada_desempate=?",(rd["pergunta_id"],rd["numero"])).fetchall()
    if len(respostas) < len(ativos): return
    corretas=[r["dupla_id"] for r in respostas if r["correta"]]
    erradas=[r["dupla_id"] for r in respostas if not r["correta"]]
    c.execute("UPDATE desempate_rodadas SET status='CONCLUIDA' WHERE id=?",(rodada_id,))
    c.execute("UPDATE perguntas SET ativa=0 WHERE id=?",(rd["pergunta_id"],))
    # Só há eliminação quando a rodada separa desempenhos.
    if corretas and erradas:
        for did in erradas:
            c.execute("UPDATE desempate_membros SET status='ELIMINADA', eliminada_rodada=? WHERE desempate_id=? AND dupla_id=?",(rd["numero"],rd["desempate_id"],did))
    restantes=c.execute("SELECT dupla_id FROM desempate_membros WHERE desempate_id=? AND status='ATIVA'",(rd["desempate_id"],)).fetchall()
    if len(restantes)==1:
        vencedor=restantes[0]["dupla_id"]
        c.execute("UPDATE desempate_membros SET status='VENCEDORA' WHERE desempate_id=? AND dupla_id=?",(rd["desempate_id"],vencedor))
        c.execute("UPDATE desempates SET status='RESOLVIDO', vencedor_dupla_id=? WHERE id=?",(vencedor,rd["desempate_id"]))
    con.commit()


def status_telao(desempate_id):
    con=conectar(); c=con.cursor()
    de=c.execute("SELECT * FROM desempates WHERE id=?",(desempate_id,)).fetchone()
    if not de: con.close(); return None
    rd=c.execute("SELECT dr.*,p.enunciado FROM desempate_rodadas dr JOIN perguntas p ON p.id=dr.pergunta_id WHERE dr.desempate_id=? ORDER BY dr.numero DESC LIMIT 1",(desempate_id,)).fetchone()
    membros=c.execute("SELECT dm.status,d.id,d.participante_1,d.participante_2 FROM desempate_membros dm JOIN duplas d ON d.id=dm.dupla_id WHERE dm.desempate_id=? ORDER BY d.id",(desempate_id,)).fetchall()
    respondidas=0; esperadas=sum(1 for m in membros if m["status"] in ("ATIVA","VENCEDORA"))
    if rd:
        respondidas=c.execute("SELECT COUNT(*) n FROM respostas WHERE pergunta_id=? AND fase='DESEMPATE' AND rodada_desempate=?",(rd["pergunta_id"],rd["numero"])).fetchone()["n"]
    out={"sessao":dict(de),"rodada":dict(rd) if rd else None,"membros":[dict(x) for x in membros],"respondidas":respondidas,"esperadas":esperadas}
    con.close(); return out
