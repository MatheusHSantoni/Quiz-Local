from collections import Counter
from database.conexao import conectar

AREAS = ("LC", "CH", "CN", "MT")
RESPOSTAS_REGULARES_POR_AREA = 2
TOTAL_RESPOSTAS_REGULARES = 8


def _linhas_classificacao(conexao):
    return conexao.execute("""
        SELECT d.id,d.participante_1,d.participante_2,
        SUM(CASE WHEN r.fase='REGULAR' THEN 1 ELSE 0 END) respostas_regulares,
        SUM(CASE WHEN r.fase='REGULAR' THEN r.pontos ELSE 0 END) pontos_regulares,
        SUM(CASE WHEN r.fase='DESEMPATE' THEN r.pontos ELSE 0 END) pontos_desempate,
        SUM(CASE WHEN r.fase='DESEMPATE' THEN 1 ELSE 0 END) respostas_desempate,
        SUM(CASE WHEN r.fase='REGULAR' AND p.area='LC' THEN 1 ELSE 0 END) resp_lc,
        SUM(CASE WHEN r.fase='REGULAR' AND p.area='CH' THEN 1 ELSE 0 END) resp_ch,
        SUM(CASE WHEN r.fase='REGULAR' AND p.area='CN' THEN 1 ELSE 0 END) resp_cn,
        SUM(CASE WHEN r.fase='REGULAR' AND p.area='MT' THEN 1 ELSE 0 END) resp_mt
        FROM duplas d LEFT JOIN respostas r ON r.dupla_id=d.id LEFT JOIN perguntas p ON p.id=r.pergunta_id
        GROUP BY d.id
    """).fetchall()


def _completou_quiz(l):
    return all(l[f"resp_{a.lower()}"] >= 2 for a in AREAS)


def _ordem_desempate(con, dupla_id, pontos):
    m=con.execute("""SELECT dm.status,dm.eliminada_rodada,de.id FROM desempate_membros dm JOIN desempates de ON de.id=dm.desempate_id
      WHERE dm.dupla_id=? AND de.pontos_regulares=? ORDER BY de.id DESC LIMIT 1""",(dupla_id,pontos)).fetchone()
    if not m: return (1,0)
    if m["status"]=="VENCEDORA": return (3,999999)
    if m["status"]=="ATIVA": return (2,999999)
    return (0,m["eliminada_rodada"] or 0)


def buscar_ranking():
    con=conectar(); linhas=_linhas_classificacao(con)
    elegiveis=[dict(l) for l in linhas if _completou_quiz(l)]
    for x in elegiveis: x["_desempate_ordem"]=_ordem_desempate(con,x["id"],x["pontos_regulares"])
    con.close()
    elegiveis.sort(key=lambda x:(-x["pontos_regulares"],-x["_desempate_ordem"][0],-x["_desempate_ordem"][1],x["id"]))
    # Enquanto o desempate está pendente, mantém posição compartilhada; resolvido, usa a ordem da morte súbita.
    pos=0; chave_ant=None
    for i,x in enumerate(elegiveis,1):
        chave=(x["pontos_regulares"],x["_desempate_ordem"])
        if chave!=chave_ant: pos=i; chave_ant=chave
        x["posicao"]=pos; x["total_pontos"]=x["pontos_regulares"]
    return elegiveis


def resumo_ranking():
    from services.desempate import sincronizar_empates, sessoes_pendentes
    con=conectar(); linhas=_linhas_classificacao(con); con.close()
    eleg=[dict(l) for l in linhas if _completou_quiz(l)]; inc=[dict(l) for l in linhas if not _completou_quiz(l)]
    sincronizar_empates(); pend=sessoes_pendentes()
    return {"total":len(linhas),"elegiveis":len(eleg),"incompletas":len(inc),"grupos_empate":len(pend),
            "duplas_empatadas":sum(sum(1 for m in s["membros"] if m["status"]=='ATIVA') for s in pend),"empates":{}}


def ranking_pode_ser_liberado():
    r=resumo_ranking()
    if r["elegiveis"]==0: return False,"Ainda não há nenhuma dupla que tenha concluído as duas etapas."
    if r["grupos_empate"]>0: return False,f"Há {r['grupos_empate']} empate(s) pendente(s), envolvendo {r['duplas_empatadas']} dupla(s). Resolva o desempate antes de liberar o ranking."
    return True,None
