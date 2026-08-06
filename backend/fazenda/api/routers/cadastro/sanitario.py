"""
Cadastro > Sanitário — Princípio ativo, Doença, calendário sanitário padrão,
Agendamento de pesagem, Evento sanitário e Exames. Protocolos sanitários
(curativos e indução de lactação) ficam em protocolos_sanitarios.py — módulo
maior e com sua própria importação de planilha.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    AgendamentoPesagem, CalendarioSanitario, Doenca, EventoSanitario, ExameDefinicao, Lote, PrincipioAtivo,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.calendario_sanitario import proxima_ocorrencia

from ._comum import _crud_nome_ativo

router = APIRouter()

# ---------------------------------------------------------------------------
# Princípio ativo / Doença / Evento sanitário — cadastros de apoio ao
# Calendário sanitário (Sanidade). Seed inicial com os nomes já usados no
# protocolo padrão da fazenda (manejo sazonal + vacinas por fase fisiológica).
# ---------------------------------------------------------------------------
SEED_EVENTOS_SANITARIOS = [
    "Vermífugo", "Reprodutiva (Primovacinação)", "Reprodutiva (Reforço)", "Clostridiose",
    "Diarreia Neonatal", "Botulismo", "Tifopasteurina", "Leptospirose",
    "Exames de Tuberculose e Brucelose", "Febre Aftosa", "Raiva", "Brucelose B19", "Brucelose RB51",
]
SEED_DOENCAS = [
    "Brucelose", "Clostridiose", "Diarreia Neonatal", "Botulismo", "Pasteurelose", "Verminose",
    "Leptospirose", "Tuberculose", "Febre Aftosa", "Raiva",
]


def seed_cadastro_sanitario(session: Session) -> None:
    """Cria os cadastros sanitários padrão se as tabelas ainda estiverem vazias (idempotente).
    Princípios ativos não entram aqui: o catálogo completo (documento base) é
    responsabilidade de bootstrap_farmacia, que roda em todo start."""
    if not session.exec(select(EventoSanitario)).first():
        for nome in SEED_EVENTOS_SANITARIOS:
            session.add(EventoSanitario(nome=nome))
    if not session.exec(select(Doenca)).first():
        for nome in SEED_DOENCAS:
            session.add(Doenca(nome=nome))
    session.commit()


# ---------------------------------------------------------------------------
# Calendário sanitário padrão da fazenda — carregado das planilhas enviadas
# (calendário fixo anual + protocolo por fase fisiológica). Roda em todo
# start, idempotente: só cria o que ainda não existe (não sobrescreve
# edição do usuário — dosagem/frequência/produto continuam 100% editáveis
# nas telas de Cadastro > Sanitário e Lançamentos > Sanitário > Calendário).
# Valores de dose/idade/gatilho vindos das planilhas em faixa (ex.: "2 mL a
# 5 mL", "4 a 8 meses") foram fixados num ponto do meio — ajuste à vontade.
# ---------------------------------------------------------------------------
SEED_PRINCIPIOS_CALENDARIO = [
    # (nome, categoria, doença vinculada)
    ("Botulismo (Toxoide)", "Biológicos (Vacinas e Diagnósticos)", "Botulismo"),
    ("Tifopasteurina", "Biológicos (Vacinas e Diagnósticos)", "Pasteurelose"),
    ("Febre Aftosa (Vacina)", "Biológicos (Vacinas e Diagnósticos)", "Febre Aftosa"),
    ("Raiva (Vacina)", "Biológicos (Vacinas e Diagnósticos)", "Raiva"),
]

# Eventos "por fase fisiológica" (protocolo por estágio) — configura o
# EventoSanitario para gerar a pendência sozinho, disparado pelo gatilho
# (nascimento, novilha apta, entrada no pré-parto), sem depender de uma
# regra do calendário. Só aplica se o evento ainda estiver no padrão
# "nenhum" (nunca configurado manualmente).
SEED_EVENTOS_POR_ESTAGIO = [
    # nome, doença, gatilho, idade/offset, dose, unidade, via
    {"nome": "Brucelose B19", "doenca": "Brucelose", "gatilho": "nascimento", "offset_dias": 150,
     "dose": 2, "unidade": "ml", "via": "Subcutânea", "sexo_alvo": "F"},
    {"nome": "Brucelose RB51", "doenca": "Brucelose", "gatilho": "novilha_apta", "idade_meses": 13,
     "dose": 2, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Reprodutiva (Primovacinação)", "doenca": None, "gatilho": "novilha_apta", "idade_meses": 13,
     "dose": 5, "unidade": "ml", "via": "Intramuscular"},
    {"nome": "Clostridiose", "doenca": "Clostridiose", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Diarreia Neonatal", "doenca": "Diarreia Neonatal", "gatilho": "entrada_lote",
     "dose": 2, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Botulismo", "doenca": "Botulismo", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
    {"nome": "Tifopasteurina", "doenca": "Pasteurelose", "gatilho": "entrada_lote",
     "dose": 3, "unidade": "ml", "via": "Subcutânea"},
]

# Eventos "por fase fisiológica" que devem entrar na lista de espera do
# cronograma sanitário (agendamento com veterinário) em vez de virar
# pendência de "aplicar agora" direto assim que o animal bate o gatilho —
# ver CalendarioSanitario.usa_cronograma. Idempotente: só cria a regra se
# NENHUMA com usa_cronograma=True já existir pra esse evento. Uma regra
# "comum" (usa_cronograma=False/None) órfã pra esse evento é promovida no
# lugar em vez de duplicada — nasce de uma tentativa de cadastro manual que
# não conseguiu marcar "usar cronograma sanitário" por um bug já corrigido
# no formulário (checkbox sumia ao selecionar um evento "por evento de
# vida", ver FormCalendarioSanitario.tsx), então preservar essa regra como
# está (usa_cronograma=False pra sempre) contraria o que o usuário queria.
SEED_CRONOGRAMA_POR_ESTAGIO = [
    {"nome": "Brucelose B19", "categoria_alvo": "Bezerras (3 a 8 meses)",
     "produto": "Brucelose Bovina (Cepa 19 ou RB51)", "dosagem": "2 mL", "unidade": "ml",
     "freq_valor": 30, "freq_unidade": "dias"},
]

# Regras do calendário fixo anual — época/rebanho (não por animal). Datas
# ancoradas em 2026 (ano corrente); a recorrência projeta as próximas
# ocorrências sozinha (não precisa estar no futuro).
SEED_CALENDARIO_FIXO = [
    {"evento": "Vermífugo", "categoria_alvo": "Bezerras até Novilhas", "freq_valor": 4, "freq_unidade": "meses",
     "data": date(2026, 1, 15), "dosagem": "Conforme o peso (ex.: 1 mL/50 kg)", "categoria_preventiva": "tratamento"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 1, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 6, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Reprodutiva (Reforço)", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 12, 15), "dosagem": "5 mL (depende do fabricante)", "categoria_preventiva": "vacina"},
    {"evento": "Leptospirose", "categoria_alvo": "Novilhas IA até Vacas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 3, 15), "dosagem": "2 mL a 5 mL (conforme bula)", "categoria_preventiva": "vacina"},
    {"evento": "Leptospirose", "categoria_alvo": "Bezerras até Novilhas", "freq_valor": 12, "freq_unidade": "meses",
     "data": date(2026, 9, 15), "dosagem": "Conforme o peso", "categoria_preventiva": "vacina"},
    {"evento": "Exames de Tuberculose e Brucelose", "categoria_alvo": "Rebanho Geral", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2027, 4, 15), "dosagem": "Coleta de sangue / Aplicação PPD", "categoria_preventiva": "exame",
     "observacao": "Retomado em 2027 — já foi feito recentemente."},
    {"evento": "Febre Aftosa", "categoria_alvo": "Vacas", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2026, 5, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Calendário do Governo."},
    {"evento": "Brucelose RB51", "categoria_alvo": "Vacas Adultas", "freq_valor": 4, "freq_unidade": "anos",
     "data": date(2026, 7, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Reforço a cada 4 anos — estratégia: fazer em anos de Copa do Mundo, para não esquecer."},
    {"evento": "Raiva", "categoria_alvo": "Vacas", "freq_valor": 1, "freq_unidade": "anos",
     "data": date(2026, 11, 15), "dosagem": "2 mL", "categoria_preventiva": "vacina",
     "observacao": "Calendário do Governo."},
]

# Princípio ativo a vincular por evento (quando existe correspondência clara
# no catálogo da farmácia) — só informativo/rastreio, dosagem real continua
# sendo escolhida no lançamento.
PRINCIPIO_POR_EVENTO_CALENDARIO = {
    "Reprodutiva (Reforço)": "Reprodutiva (IBR, BVD, Leptospirose)",
    "Leptospirose": "Reprodutiva (IBR, BVD, Leptospirose)",
    "Brucelose RB51": "Brucelose Bovina (Cepa 19 ou RB51)",
    "Vermífugo": "Albendazol",
    "Febre Aftosa": "Febre Aftosa (Vacina)",
    "Raiva": "Raiva (Vacina)",
}


def configurar_calendario_sanitario_padrao(session: Session) -> None:
    """Compatibiliza e cadastra o calendário sanitário padrão da fazenda
    (planilhas "calendário por mês" e "protocolo por estágio"). Roda em todo
    start, idempotente:
      - só cria princípio ativo/regra do calendário que ainda não existir;
      - só configura um EventoSanitario "por estágio" se ele ainda estiver
        no padrão "nenhum" (nunca foi configurado manualmente).
    Os 13 eventos e as 10 doenças usados aqui já vêm do seed_cadastro_sanitario
    — nenhum evento/doença novo precisou ser criado, só compatibilizado.
    """
    doencas = {d.nome: d for d in session.exec(select(Doenca)).all()}
    eventos = {e.nome: e for e in session.exec(select(EventoSanitario)).all()}
    principios = {p.nome: p for p in session.exec(select(PrincipioAtivo)).all()}

    # 1) Princípios ativos que faltam no catálogo (Botulismo, Tifopasteurina,
    # Febre Aftosa e Raiva não têm biológico próprio hoje — a farmácia só
    # tinha os combos de Clostridiose/Brucelose/Reprodutiva/Tuberculina).
    for nome, categoria, doenca_nome in SEED_PRINCIPIOS_CALENDARIO:
        if nome in principios:
            continue
        novo = PrincipioAtivo(nome=nome, categoria=categoria, categoria_software="Biológico (Vacina)")
        session.add(novo)
        principios[nome] = novo
    session.commit()
    for nome in principios:
        session.refresh(principios[nome])

    # 2) Eventos "por fase fisiológica" — configura gatilho automático.
    # Entrada em lote (pré-parto) exige um lote já marcado pre_parto=True;
    # sem isso, não dá pra saber qual lote dispara o evento — fica pendente
    # de configuração manual (Configurações > Cadastro > Sanitário > Eventos).
    lote_pre_parto = session.exec(select(Lote).where(Lote.pre_parto == True)).first()  # noqa: E712
    for cfg in SEED_EVENTOS_POR_ESTAGIO:
        ev = eventos.get(cfg["nome"])
        if not ev:
            continue
        # sexo_alvo é campo novo (bug corrigido depois do 1º seed) — aplica
        # mesmo em evento já configurado antes, só quando ainda está em
        # branco (nunca sobrescreve edição manual feita pela tela de cadastro).
        if cfg.get("sexo_alvo") and ev.sexo_alvo is None:
            ev.sexo_alvo = cfg["sexo_alvo"]
            session.add(ev)
        if ev.tipo_agendamento != "nenhum":
            continue  # já foi configurado manualmente — não mexe no resto
        if cfg["gatilho"] == "entrada_lote" and not lote_pre_parto:
            continue  # falta um lote pré-parto cadastrado — configurar depois
        ev.tipo_agendamento = "evento"
        ev.gatilho = cfg["gatilho"]
        if cfg["gatilho"] == "entrada_lote":
            ev.gatilho_lote = lote_pre_parto.codigo
            ev.categoria_alvo = ev.categoria_alvo or "Novilhas e vacas prenhes (pré-parto)"
        if cfg["gatilho"] == "novilha_apta":
            ev.gatilho_idade_meses = cfg.get("idade_meses")
        if cfg["gatilho"] == "nascimento":
            ev.offset_dias = cfg.get("offset_dias")
        if cfg.get("doenca") and doencas.get(cfg["doenca"]):
            ev.doenca_id = ev.doenca_id or doencas[cfg["doenca"]].id
        ev.categoria_preventiva = ev.categoria_preventiva or "vacina"
        ev.dose_padrao = ev.dose_padrao if ev.dose_padrao is not None else cfg["dose"]
        ev.unidade_padrao = ev.unidade_padrao or cfg["unidade"]
        ev.via_padrao = ev.via_padrao or cfg["via"]
        session.add(ev)
    session.commit()

    # 2.5) Regras "por fase fisiológica" que entram no cronograma (lista de
    # espera de agendamento) em vez de aplicar direto — ver
    # SEED_CRONOGRAMA_POR_ESTAGIO acima.
    regras_por_evento: dict[int, list[CalendarioSanitario]] = {}
    for c in session.exec(select(CalendarioSanitario)).all():
        regras_por_evento.setdefault(c.evento_sanitario_id, []).append(c)
    for cfg in SEED_CRONOGRAMA_POR_ESTAGIO:
        ev = eventos.get(cfg["nome"])
        if not ev:
            continue
        existentes = regras_por_evento.get(ev.id, [])
        if any(c.usa_cronograma for c in existentes):
            continue  # já tem regra de cronograma pra esse evento — não mexe
        orfa = existentes[0] if existentes else None
        if orfa:
            orfa.usa_cronograma = True
            session.add(orfa)
            continue
        principio = principios.get(cfg.get("produto"))
        nova = CalendarioSanitario(
            evento_sanitario_id=ev.id,
            categoria_alvo=cfg["categoria_alvo"],
            doenca_id=ev.doenca_id,
            produto=cfg.get("produto"),
            principio_ativo_id=principio.id if principio else None,
            dosagem=cfg["dosagem"],
            unidade=cfg["unidade"],
            frequencia_valor=cfg["freq_valor"],
            frequencia_unidade=cfg["freq_unidade"],
            data_evento=date.today(),
            usa_cronograma=True,
        )
        session.add(nova)
        regras_por_evento.setdefault(ev.id, []).append(nova)
    session.commit()

    # 3) Regras do calendário fixo anual — época/rebanho. Evita duplicar se já
    # existir uma regra igual (mesmo evento + mesma categoria-alvo + mesmo mês
    # de âncora — "Reprodutiva (Reforço)" tem 3 aplicações/ano na mesma
    # categoria, diferenciadas só pelo mês; sem o mês na chave, a 2ª e a 3ª
    # seriam descartadas como "duplicata" da 1ª).
    existentes = {
        (c.evento_sanitario_id, (c.categoria_alvo or "").strip().lower(), c.data_evento.month)
        for c in session.exec(select(CalendarioSanitario)).all()
    }
    for cfg in SEED_CALENDARIO_FIXO:
        ev = eventos.get(cfg["evento"])
        if not ev:
            continue
        chave = (ev.id, cfg["categoria_alvo"].strip().lower(), cfg["data"].month)
        if chave in existentes:
            continue
        # Mantém a categoria_preventiva do evento se já foi definida manualmente.
        if not ev.categoria_preventiva:
            ev.categoria_preventiva = cfg["categoria_preventiva"]
            session.add(ev)
        principio_nome = PRINCIPIO_POR_EVENTO_CALENDARIO.get(cfg["evento"])
        principio = principios.get(principio_nome) if principio_nome else None
        session.add(CalendarioSanitario(
            evento_sanitario_id=ev.id,
            categoria_alvo=cfg["categoria_alvo"],
            doenca_id=ev.doenca_id,
            principio_ativo_id=principio.id if principio else None,
            dosagem=cfg["dosagem"],
            frequencia_valor=cfg["freq_valor"],
            frequencia_unidade=cfg["freq_unidade"],
            data_evento=cfg["data"],
            observacao=cfg.get("observacao"),
        ))
        existentes.add(chave)
    session.commit()


_listar_principios, _criar_principio, _atualizar_principio, _ = _crud_nome_ativo(PrincipioAtivo, com_fazenda=True)
router.get("/principios-ativos")(_listar_principios)
router.post("/principios-ativos")(_criar_principio)
router.put("/principios-ativos/{item_id}")(_atualizar_principio)


@router.post("/principios-ativos/restaurar-catalogo")
def restaurar_catalogo_principios(session: Session = Depends(get_session)) -> dict:
    """(Re)semeia o catálogo base de princípios ativos (documento base da farmácia)
    — add-missing e idempotente: só cria os que faltam e não sobrescreve edições.
    Útil quando o banco foi criado antes do catálogo completo existir."""
    from fazenda.rules.farmacia import seed_farmacia
    antes = len(session.exec(select(PrincipioAtivo)).all())
    seed_farmacia(session)
    total = len(session.exec(select(PrincipioAtivo)).all())
    return {"criados": total - antes, "total": total}

_listar_doencas, _criar_doenca, _atualizar_doenca, _ = _crud_nome_ativo(Doenca, com_fazenda=True)
router.get("/doencas")(_listar_doencas)
router.post("/doencas")(_criar_doenca)
router.put("/doencas/{item_id}")(_atualizar_doenca)



# ---------------------------------------------------------------------------
# Agendamento de pesagem do rebanho (acompanhamento da evolução de peso) —
# periodicidade por fase + dia da semana, que alimenta a Agenda.
# ---------------------------------------------------------------------------
class AgendamentoPesagemIn(BaseModel):
    nome: str
    ativo: bool = True
    idade_min_dias: int | None = None
    idade_max_dias: int | None = None
    categoria_alvo: str | None = None
    frequencia_valor: int = 15
    frequencia_unidade: str = "dias"  # "dias" | "meses"
    dia_semana: int = 1  # 0=segunda … 6=domingo
    data_referencia: date


@router.get("/agendamentos-pesagem")
def listar_agendamentos_pesagem(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(AgendamentoPesagem).order_by(AgendamentoPesagem.nome)
    if fazenda_id is not None:
        query = query.where(AgendamentoPesagem.fazenda_id == fazenda_id)
    return [a.model_dump() for a in session.exec(query).all()]


def _valida_pesagem(dados: AgendamentoPesagemIn) -> None:
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome da fase (ex.: Bezerras até desmama)")
    if dados.frequencia_unidade not in ("dias", "meses"):
        raise HTTPException(status_code=400, detail="Frequência inválida (dias ou meses)")
    if dados.frequencia_valor <= 0:
        raise HTTPException(status_code=400, detail="A periodicidade deve ser maior que zero")
    if not (0 <= dados.dia_semana <= 6):
        raise HTTPException(status_code=400, detail="Dia da semana inválido")


@router.post("/agendamentos-pesagem", status_code=201)
def criar_agendamento_pesagem(
    dados: AgendamentoPesagemIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _valida_pesagem(dados)
    obj = AgendamentoPesagem(**{**dados.model_dump(), "nome": dados.nome.strip()}, fazenda_id=fazenda_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/agendamentos-pesagem/{item_id}")
def atualizar_agendamento_pesagem(
    item_id: int, dados: AgendamentoPesagemIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    _valida_pesagem(dados)
    for k, v in {**dados.model_dump(), "nome": dados.nome.strip()}.items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.delete("/agendamentos-pesagem/{item_id}")
def excluir_agendamento_pesagem(
    item_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    obj = session.get(AgendamentoPesagem, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    session.delete(obj)
    session.commit()
    return {"ok": True}

# Evento sanitário — cadastro RICO (nome + agendamento por época/evento +
# medicamento padrão). Alimenta o calendário sanitário e a Agenda.
FREQUENCIAS_EVENTO = ["dias", "meses", "anos"]
TIPOS_AGENDAMENTO = ["nenhum", "epoca", "evento"]
GATILHOS_EVENTO = [
    "nascimento", "entrada_lote", "novilha_apta", "secagem", "parto",
    # Eventos de vida adicionais — mudanças de categoria/fase reprodutiva que
    # o calendário sanitário também pode usar como gatilho, em vez de uma
    # frequência periódica (ver fazenda.rules.eventos_sanitarios).
    "desmama", "mudanca_recria", "inseminacao", "gestacao_confirmada", "mudanca_pre_parto",
]


class EventoSanitarioIn(BaseModel):
    nome: str
    ativo: bool = True
    tipo_agendamento: str = "nenhum"
    categoria_alvo: str | None = None
    sexo_alvo: str | None = None  # "F" | "M" | None (ambos)
    categoria_preventiva: str | None = None  # "vacina" | "exame" | "tratamento"
    doenca_id: int | None = None
    data_primeiro: date | None = None
    frequencia_valor: int | None = None
    frequencia_unidade: str | None = None
    gatilho: str | None = None
    gatilho_lote: str | None = None
    gatilho_idade_meses: int | None = None
    offset_dias: int | None = None
    produto_padrao: str | None = None
    dose_padrao: float | None = None
    unidade_padrao: str | None = None
    via_padrao: str | None = None
    # Só para exame: avisa na Agenda N dias antes, para confirmar com o veterinário.
    agenda_dias_antes: int | None = None
    # Condição de exclusão mútua — ex.: não agendar "Brucelose RB51" se o
    # animal já recebeu "Brucelose B19" (alternativas de vacina/estirpe).
    condicao_evento_id: int | None = None
    # Só para exame: qual ExameDefinicao decide o tipo de resultado
    # (diagnóstico/numérico) mostrado no lançamento (Sanitário > Preventivo).
    exame_definicao_id: int | None = None
    # Nome de um ServicoCadastro — liga este evento (vacina ou exame) ao
    # botão "Lançar financeiro" no calendário sanitário, sem depender de
    # adivinhar pelo nome do evento.
    servico_financeiro: str | None = None


def _dto_evento_sanitario(session: Session, ev: EventoSanitario) -> dict:
    d = ev.model_dump()
    d["doenca_nome"] = None
    if ev.doenca_id:
        doenca = session.get(Doenca, ev.doenca_id)
        d["doenca_nome"] = doenca.nome if doenca else None
    d["condicao_evento_nome"] = None
    if ev.condicao_evento_id:
        condicao = session.get(EventoSanitario, ev.condicao_evento_id)
        d["condicao_evento_nome"] = condicao.nome if condicao else None
    d["exame_definicao_nome"] = None
    if ev.exame_definicao_id:
        exame_def = session.get(ExameDefinicao, ev.exame_definicao_id)
        d["exame_definicao_nome"] = exame_def.nome if exame_def else None
    if ev.tipo_agendamento == "epoca" and ev.data_primeiro and ev.frequencia_valor and ev.frequencia_unidade:
        d["proxima_ocorrencia"] = proxima_ocorrencia(ev.data_primeiro, ev.frequencia_valor, ev.frequencia_unidade).isoformat()
    else:
        d["proxima_ocorrencia"] = None
    return d


def _validar_evento_sanitario(dados: EventoSanitarioIn, session: Session, *, item_id: int | None = None) -> None:
    if dados.tipo_agendamento not in TIPOS_AGENDAMENTO:
        raise HTTPException(status_code=400, detail=f"Tipo de agendamento inválido (use: {', '.join(TIPOS_AGENDAMENTO)})")
    if dados.sexo_alvo is not None and dados.sexo_alvo not in ("F", "M"):
        raise HTTPException(status_code=400, detail="Sexo-alvo inválido (use F, M ou deixe em branco)")
    if dados.doenca_id is not None and not session.get(Doenca, dados.doenca_id):
        raise HTTPException(status_code=400, detail="Doença não encontrada")
    if dados.condicao_evento_id is not None:
        if dados.condicao_evento_id == item_id:
            raise HTTPException(status_code=400, detail="Um evento não pode ser condição de si mesmo")
        if not session.get(EventoSanitario, dados.condicao_evento_id):
            raise HTTPException(status_code=400, detail="Evento sanitário da condição não encontrado")
    if dados.exame_definicao_id is not None and not session.get(ExameDefinicao, dados.exame_definicao_id):
        raise HTTPException(status_code=400, detail="Exame (cadastro) não encontrado")
    if dados.tipo_agendamento == "epoca":
        if not dados.data_primeiro:
            raise HTTPException(status_code=400, detail="Informe a data do primeiro evento (agendamento por época)")
        if not dados.frequencia_valor or dados.frequencia_valor <= 0:
            raise HTTPException(status_code=400, detail="Informe uma frequência maior que zero")
        if dados.frequencia_unidade not in FREQUENCIAS_EVENTO:
            raise HTTPException(status_code=400, detail=f"Frequência inválida (use: {', '.join(FREQUENCIAS_EVENTO)})")
    if dados.tipo_agendamento == "evento":
        if dados.gatilho not in GATILHOS_EVENTO:
            raise HTTPException(status_code=400, detail=f"Gatilho inválido (use: {', '.join(GATILHOS_EVENTO)})")
        if dados.gatilho == "entrada_lote" and not (dados.gatilho_lote or "").strip():
            raise HTTPException(status_code=400, detail="Informe o lote do gatilho (entrada no lote)")
        if dados.gatilho == "novilha_apta" and not dados.gatilho_idade_meses:
            raise HTTPException(status_code=400, detail="Informe a idade-alvo em meses (aptidão de novilha)")


@router.get("/eventos-sanitarios")
def listar_eventos_sanitarios(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(EventoSanitario).order_by(EventoSanitario.nome)
    if fazenda_id is not None:
        query = query.where(EventoSanitario.fazenda_id == fazenda_id)
    eventos = session.exec(query).all()
    return [_dto_evento_sanitario(session, ev) for ev in eventos]


@router.post("/eventos-sanitarios")
def criar_evento_sanitario(
    dados: EventoSanitarioIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(EventoSanitario).where(EventoSanitario.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(EventoSanitario.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um evento sanitário com o nome '{nome}'")
    _validar_evento_sanitario(dados, session)
    ev = EventoSanitario(**{**dados.model_dump(), "nome": nome}, fazenda_id=fazenda_id)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return _dto_evento_sanitario(session, ev)


@router.put("/eventos-sanitarios/{item_id}")
def atualizar_evento_sanitario(
    item_id: int, dados: EventoSanitarioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    ev = session.get(EventoSanitario, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not ev or (fazenda_id is not None and ev.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Evento sanitário não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_evento_sanitario(dados, session, item_id=item_id)
    for campo, valor in {**dados.model_dump(), "nome": nome}.items():
        setattr(ev, campo, valor)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return _dto_evento_sanitario(session, ev)

# ---------------------------------------------------------------------------
# Exames (Configurações > Cadastro > Sanitário > Exames) — nome do exame +
# tipo de resultado (diagnóstico ou numérico), vinculado ao princípio ativo.
# Consumido em Lançamentos > Sanitário > Preventivo (ver sanidade.py
# cadastrar_preventivo) — nunca gera aplicação de medicamento.
# ---------------------------------------------------------------------------
TIPOS_RESULTADO_EXAME = ["diagnostico", "numerico"]


class ExameDefinicaoIn(BaseModel):
    nome: str
    ativo: bool = True
    principio_ativo_id: int | None = None
    tipo_resultado: str = "diagnostico"
    faixa_min: float | None = None
    faixa_max: float | None = None
    acao_abaixo: str | None = None
    acao_dentro: str | None = None
    acao_acima: str | None = None
    observacao: str | None = None


def _dto_exame_definicao(session: Session, ex: ExameDefinicao) -> dict:
    d = ex.model_dump()
    d["principio_ativo_nome"] = None
    if ex.principio_ativo_id:
        principio = session.get(PrincipioAtivo, ex.principio_ativo_id)
        d["principio_ativo_nome"] = principio.nome if principio else None
    return d


def _validar_exame_definicao(dados: ExameDefinicaoIn, session: Session) -> None:
    if dados.tipo_resultado not in TIPOS_RESULTADO_EXAME:
        raise HTTPException(status_code=400, detail=f"Tipo de resultado inválido (use: {', '.join(TIPOS_RESULTADO_EXAME)})")
    if dados.principio_ativo_id is not None and not session.get(PrincipioAtivo, dados.principio_ativo_id):
        raise HTTPException(status_code=400, detail="Princípio ativo não encontrado")
    if dados.tipo_resultado == "numerico":
        if dados.faixa_min is None or dados.faixa_max is None:
            raise HTTPException(status_code=400, detail="Informe a faixa (de x até y) para exame numérico")
        if dados.faixa_min > dados.faixa_max:
            raise HTTPException(status_code=400, detail="A faixa mínima não pode ser maior que a máxima")


@router.get("/exames")
def listar_exames(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ExameDefinicao).order_by(ExameDefinicao.nome)
    if fazenda_id is not None:
        query = query.where(ExameDefinicao.fazenda_id == fazenda_id)
    exames = session.exec(query).all()
    return [_dto_exame_definicao(session, ex) for ex in exames]


@router.post("/exames")
def criar_exame(
    dados: ExameDefinicaoIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(ExameDefinicao).where(ExameDefinicao.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ExameDefinicao.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um exame com o nome '{nome}'")
    _validar_exame_definicao(dados, session)
    ex = ExameDefinicao(**{**dados.model_dump(), "nome": nome}, fazenda_id=fazenda_id)
    session.add(ex)
    session.commit()
    session.refresh(ex)
    return _dto_exame_definicao(session, ex)


@router.put("/exames/{item_id}")
def atualizar_exame(
    item_id: int, dados: ExameDefinicaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    ex = session.get(ExameDefinicao, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not ex or (fazenda_id is not None and ex.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Exame não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_exame_definicao(dados, session)
    for campo, valor in {**dados.model_dump(), "nome": nome}.items():
        setattr(ex, campo, valor)
    session.add(ex)
    session.commit()
    session.refresh(ex)
    return _dto_exame_definicao(session, ex)


@router.delete("/exames/{item_id}")
def excluir_exame(
    item_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    ex = session.get(ExameDefinicao, item_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not ex or (fazenda_id is not None and ex.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Exame não encontrado")
    session.delete(ex)
    session.commit()
    return {"excluido": True, "id": item_id}


