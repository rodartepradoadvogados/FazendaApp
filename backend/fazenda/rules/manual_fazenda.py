"""
Manual da Fazenda — monta, a partir dos parâmetros e indicadores já
calculados em outros módulos, um relatório com 4 seções:

  - rotina: projeção das próximas datas de BST, visita reprodutiva,
    calendário sanitário e reposição de estoque — mesma lógica de
    ancoragem já usada na Agenda, sem duplicar a Agenda inteira.
  - resultado: KPIs atuais (reaproveita calcular_indicadores).
  - insights: compara a média dos últimos meses com o período anterior nas
    métricas mensais já existentes (reaproveita agregar_mensal, a mesma
    série que alimenta Análise reprodutiva) e narra as variações relevantes.
  - sugestoes: as sugestões cadastradas pelo usuário (SugestaoManualFazenda)
    somadas a sugestões automáticas derivadas da rotina/insights.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from fazenda.models import (
    Animal, ControleLeiteiro, Estoque, Parto, ParametroManualFazenda,
    ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento, ProtocoloSanitario,
    Sanidade, Secagem, Servico, SugestaoManualFazenda, Usuario, UsuarioFazenda,
)
from fazenda.rules.email import enviar_email
from fazenda.rules.indicadores import calcular_indicadores
from fazenda.rules.parametros import (
    bst_ajuste_ancora_data, dias_resultado_conhecido, intervalo_bst, intervalo_visita_reprodutiva,
)
from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

MARCADORES_BST = re.compile(r"\b(lactotropi[nm]|boostin|bst|somatotropina)\b", re.IGNORECASE)

# Métricas mensais elegíveis para virar "insight" — subconjunto de
# agregar_mensal().series, com rótulo humano e categoria de exibição.
METRICAS_INSIGHT = [
    ("taxa_concepcao", "Reprodução", "Taxa de concepção", "%"),
    ("producao_leite", "Produção", "Produção de leite (média)", "kg"),
    ("perdas_prenhez", "Reprodução", "Perdas de prenhez", ""),
    ("num_secagens", "Produção", "Secagens", ""),
    ("del_medio", "Produção", "DEL médio", "d"),
]

# Subconjunto de METRICAS_INSIGHT cujo valor mensal depende de diagnóstico
# (regra R7 — ver `agregar_mensal.janela_dg_completa`). Só "taxa_concepcao" se
# encaixa: é positivos/serviços-com-resultado-conhecido, então o mês corrente
# — cujos serviços recentes majoritariamente ainda não têm 28 dias nem DG —
# fica com uma amostra pequena e enviesada. As demais (produção, perdas já
# registradas, secagens, DEL) não esperam diagnóstico nenhum e não devem
# perder o mês corrente da comparação.
METRICAS_DEPENDEM_DE_DG = frozenset({"taxa_concepcao"})


def parametro_manual(session: Session, fazenda_id: int | None) -> ParametroManualFazenda:
    query = select(ParametroManualFazenda)
    query = query.where(ParametroManualFazenda.fazenda_id == fazenda_id) if fazenda_id is not None else query.where(
        ParametroManualFazenda.fazenda_id.is_(None)
    )
    p = session.exec(query).first()
    if not p:
        p = ParametroManualFazenda(fazenda_id=fazenda_id)
        session.add(p)
        session.commit()
        session.refresh(p)
    return p


def _proximas_datas(ancora: date, intervalo: int, hoje: date, n: int = 3) -> list[str]:
    proxima = ancora + timedelta(days=intervalo)
    while proxima < hoje:
        proxima += timedelta(days=intervalo)
    return [(proxima + timedelta(days=i * intervalo)).isoformat() for i in range(n)]


def _rotina_bst(session: Session, fazenda_id: int | None, hoje: date) -> dict | None:
    query = select(Sanidade)
    if fazenda_id is not None:
        query = query.where(Sanidade.fazenda_id == fazenda_id)
    datas = [
        s.data_aplicacao for s in session.exec(query).all()
        if s.data_aplicacao and (s.atividade == "BST" or MARCADORES_BST.search(s.produto or ""))
    ]
    intervalo = intervalo_bst()
    ancora = max(datas) if datas else None
    ancora_manual = bst_ajuste_ancora_data()
    if ancora_manual is not None and (ancora is None or ancora_manual > ancora):
        ancora = ancora_manual
    if ancora is None or intervalo <= 0:
        return None
    return {
        "titulo": f"Aplicação de BST — a cada {intervalo} dias",
        "descricao": "Projeção com base na última aplicação real lançada.",
        "proximas_datas": _proximas_datas(ancora, intervalo, hoje),
    }


def _rotina_visita_reprodutiva(session: Session, fazenda_id: int | None, hoje: date, parametro: ParametroManualFazenda) -> dict | None:
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    datas = [s.data_servico for s in session.exec(query).all() if s.data_servico]
    intervalo = intervalo_visita_reprodutiva()
    if not datas or intervalo <= 0:
        return None
    responsavel = parametro.responsavel_manejo_nome or "responsável não cadastrado"
    if parametro.responsavel_manejo_empresa:
        responsavel = f"{responsavel} ({parametro.responsavel_manejo_empresa})"
    return {
        "titulo": f"Manejo reprodutivo — a cada {intervalo} dias, com {responsavel}",
        "descricao": "Ancorada no último serviço lançado.",
        "proximas_datas": _proximas_datas(max(datas), intervalo, hoje),
    }


def _rotina_sanitaria(session: Session, fazenda_id: int | None, hoje: date) -> dict:
    query = (
        select(ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento, ProtocoloSanitario)
        .join(ProtocoloSanitarioLancamento, ProtocoloSanitarioAplicacao.lancamento_id == ProtocoloSanitarioLancamento.id)
        .join(ProtocoloSanitario, ProtocoloSanitarioLancamento.protocolo_id == ProtocoloSanitario.id)
        .where(ProtocoloSanitarioAplicacao.realizada == False)  # noqa: E712
        .order_by(ProtocoloSanitarioAplicacao.data_prevista)
    )
    if fazenda_id is not None:
        query = query.where(ProtocoloSanitarioAplicacao.fazenda_id == fazenda_id)
    pendentes = session.exec(query).all()
    vencidas = [row for row in pendentes if row[0].data_prevista < hoje]
    proxima = pendentes[0] if pendentes else None
    return {
        "titulo": "Calendário sanitário preventivo",
        "vencidas": len(vencidas),
        "proxima": (
            {"protocolo": proxima[2].nome, "data": proxima[0].data_prevista.isoformat(), "animal": proxima[1].numero_matriz}
            if proxima else None
        ),
    }


def _rotina_compras(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(Estoque).where(Estoque.estocavel != False)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Estoque.fazenda_id == fazenda_id)
    itens = session.exec(query).all()
    criticos = [
        i for i in itens
        if i.quantidade is not None and i.estoque_minimo is not None and i.quantidade < i.estoque_minimo
    ]
    return [{"nome": i.nome, "quantidade": i.quantidade, "estoque_minimo": i.estoque_minimo} for i in criticos[:5]]


def _insights(session: Session, fazenda_id: int | None) -> list[dict]:
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query).all()]
    registros = analisar_servicos(servicos)
    secagens = [s.model_dump() for s in session.exec(select(Secagem)).all()]
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    agregado = agregar_mensal(registros, secagens, controles, dias_resultado=dias_resultado_conhecido())
    meses = agregado["meses"]
    if len(meses) < 2:
        return []
    janela_dg_completa = agregado["janela_dg_completa"]
    janela = min(3, len(meses) // 2) or 1
    insights = []
    for chave, categoria, label, unidade in METRICAS_INSIGHT:
        serie = agregado["series"].get(chave, [])
        # Métrica que depende de diagnóstico descarta o mês com janela de DG
        # aberta das duas janelas de comparação — senão o mês corrente (quase
        # sem diagnóstico, por definição) inventa uma "queda" que é só falta
        # de tempo. As demais métricas comparam todos os meses normalmente.
        completos = janela_dg_completa if chave in METRICAS_DEPENDEM_DE_DG else [True] * len(meses)
        recentes = [v for v, completo in zip(serie[-janela:], completos[-janela:]) if v is not None and completo]
        anteriores = [
            v for v, completo in zip(serie[-2 * janela:-janela], completos[-2 * janela:-janela])
            if v is not None and completo
        ]
        if not recentes or not anteriores:
            continue
        media_recente = sum(recentes) / len(recentes)
        media_anterior = sum(anteriores) / len(anteriores)
        if media_anterior == 0:
            continue
        variacao_pct = round(100 * (media_recente - media_anterior) / abs(media_anterior), 1)
        if abs(variacao_pct) < 3:
            continue  # variação pequena demais pra virar insight — evita ruído
        tendencia = "alta" if variacao_pct > 0 else "queda"
        insights.append({
            "categoria": categoria,
            "metrica": label,
            "tendencia": tendencia,
            "variacao_pct": variacao_pct,
            "valor_recente": round(media_recente, 1),
            "valor_anterior": round(media_anterior, 1),
            "unidade": unidade,
            "texto": f"{label} {'subiu' if variacao_pct > 0 else 'caiu'} {abs(variacao_pct)}% "
                     f"nos últimos {janela} mês(es), comparado ao período anterior.",
        })
    return sorted(insights, key=lambda i: -abs(i["variacao_pct"]))


def _sugestoes_automaticas(rotina: dict, insights: list[dict]) -> list[dict]:
    sugestoes = []
    sanit = rotina.get("sanitario") or {}
    if sanit.get("vencidas"):
        sugestoes.append({
            "texto": f"{sanit['vencidas']} aplicação(ões) sanitária(s) vencida(s) — regularize antes da próxima visita.",
            "categoria": "sanidade", "origem": "automatica",
        })
    if rotina.get("compras"):
        nomes = ", ".join(c["nome"] for c in rotina["compras"][:3])
        sugestoes.append({
            "texto": f"Estoque abaixo do mínimo: {nomes}. Programe a compra.",
            "categoria": "geral", "origem": "automatica",
        })
    for ins in insights:
        if ins["tendencia"] != "queda":
            continue
        if ins["categoria"] == "Reprodução":
            sugestoes.append({
                "texto": f"{ins['metrica']} em queda — vale revisar o manejo reprodutivo com {rotina.get('visita_reprodutiva', {}).get('titulo', 'o responsável técnico')}.",
                "categoria": "reprodutivo", "origem": "automatica",
            })
        elif ins["categoria"] == "Produção":
            sugestoes.append({
                "texto": f"{ins['metrica']} em queda — vale revisar dieta e conforto térmico do lote em lactação.",
                "categoria": "producao", "origem": "automatica",
            })
    return sugestoes


def montar_manual(session: Session, fazenda_id: int | None) -> dict:
    hoje = date.today()
    parametro = parametro_manual(session, fazenda_id)

    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    query_servicos = select(Servico)
    query_partos = select(Parto)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    animais = [a.model_dump() for a in session.exec(query_animais).all() if not a.eh_semen and a.sexo != "M"]
    servicos = [s.model_dump() for s in session.exec(query_servicos).all()]
    partos = [p.model_dump() for p in session.exec(query_partos).all()]
    indicadores = calcular_indicadores(animais, servicos, partos, data_ref=hoje)

    rotina = {
        "bst": _rotina_bst(session, fazenda_id, hoje),
        "visita_reprodutiva": _rotina_visita_reprodutiva(session, fazenda_id, hoje, parametro),
        "sanitario": _rotina_sanitaria(session, fazenda_id, hoje),
        "compras": _rotina_compras(session, fazenda_id),
    }
    insights = _insights(session, fazenda_id)

    query_sugestoes = select(SugestaoManualFazenda).where(SugestaoManualFazenda.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_sugestoes = query_sugestoes.where(SugestaoManualFazenda.fazenda_id == fazenda_id)
    sugestoes_custom = [
        {"texto": s.texto, "categoria": s.categoria, "origem": "usuario"}
        for s in session.exec(query_sugestoes.order_by(SugestaoManualFazenda.ordem)).all()
    ]

    return {
        "gerado_em": datetime.utcnow().isoformat(),
        "responsavel_manejo": {
            "nome": parametro.responsavel_manejo_nome,
            "empresa": parametro.responsavel_manejo_empresa,
            "tem_contrato": parametro.tem_contrato_manejo,
            "contrato_arquivo_nome": parametro.contrato_manejo_arquivo_nome,
        },
        "rotina": rotina,
        "resultado": {
            "total_animais": indicadores["rebanho"]["total"],
            "vacas_lactacao": indicadores["rebanho"]["vacas_lactacao"],
            "taxa_prenhez_pct": indicadores["reproducao"]["taxa_prenhez_pct"],
            "taxa_concepcao_pct": indicadores["reproducao"]["taxa_concepcao_pct"],
            "taxa_servico_pct": indicadores["reproducao"]["taxa_servico_pct"],
            "producao_media_kg": indicadores["producao"]["producao_media_kg"],
            "producao_total_dia_kg": indicadores["producao"]["producao_total_dia_kg"],
            "del_medio": indicadores["producao"]["del_medio"],
        },
        "insights": insights,
        "sugestoes": sugestoes_custom + _sugestoes_automaticas(rotina, insights),
    }


def emails_administradores_fazenda(session: Session, fazenda_id: int | None) -> list[str]:
    """E-mails dos administradores da fazenda (papel="admin", ativo, com
    e-mail cadastrado) — destinatários do envio semanal. Com fazenda_id
    definido, restringe aos vinculados via UsuarioFazenda; sem ele (piloto
    conservador de multi-fazenda, mesma regra do resto do sistema), pega
    todos os admins ativos com e-mail."""
    query = select(Usuario).where(Usuario.papel == "admin", Usuario.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.join(UsuarioFazenda, UsuarioFazenda.usuario_id == Usuario.id).where(
            UsuarioFazenda.fazenda_id == fazenda_id
        )
    usuarios = session.exec(query).all()
    emails = {u.email.strip() for u in usuarios if u.email and u.email.strip()}
    return sorted(emails)


def deve_enviar_manual_semanal(parametro: ParametroManualFazenda, agora: datetime) -> bool:
    """Segunda-feira, a partir das 7h, uma vez por semana (ISO) — não
    dispara de novo na mesma semana mesmo que o loop rode várias vezes
    depois das 7h de segunda."""
    if not parametro.email_semanal_ativo:
        return False
    if agora.weekday() != 0 or agora.hour < 7:
        return False
    if parametro.ultimo_envio_semanal_em is None:
        return True
    return parametro.ultimo_envio_semanal_em.isocalendar()[:2] != agora.isocalendar()[:2]


def enviar_manual_semanal_se_necessario(session: Session, fazenda_id: int | None = None, agora: datetime | None = None) -> bool:
    """Chamado periodicamente (ver loop em main.py) — verifica se é hora de
    mandar o Manual da Fazenda semanal e, se for, gera o PDF e envia para
    todos os administradores. Nunca propaga exceção (mesmo padrão de
    executar_backup_se_necessario) — um erro de envio não deve derrubar o
    processo, só fica pendente para a próxima checagem. `agora` é injetável
    só para teste; em produção sempre usa o instante real."""
    from fazenda.rules.manual_fazenda_pdf import gerar_pdf_manual

    agora = agora or datetime.utcnow()
    parametro = parametro_manual(session, fazenda_id)
    if not deve_enviar_manual_semanal(parametro, agora):
        return False
    emails = emails_administradores_fazenda(session, fazenda_id)
    if not emails:
        return False
    try:
        manual = montar_manual(session, fazenda_id)
        pdf_bytes = gerar_pdf_manual(manual)
        assunto = f"Manual da Fazenda — resumo semanal ({agora:%d/%m/%Y})"
        corpo = (
            "<p>Segue em anexo o Manual da Fazenda desta semana — rotina, resultado, "
            "insights e sugestões, calculados a partir dos parâmetros e indicadores atuais.</p>"
        )
        for email in emails:
            enviar_email(email, assunto, corpo, "manual_da_fazenda.pdf", pdf_bytes)
        parametro.ultimo_envio_semanal_em = agora
        session.add(parametro)
        session.commit()
        return True
    except Exception:  # noqa: BLE001 — nunca deixa o loop de fundo cair por causa do envio
        return False
