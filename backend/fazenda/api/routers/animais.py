"""
Router de animais — listagem e consulta de animais.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    Animal, AgendaManual, BaixaAnimal, ColostragemBezerra, CompraAnimal, ControleLeiteiro, EstoqueSemen, MovimentoLote, Parto,
    PesagemCorporal, ProtocoloIatfAplicacao, ProtocoloSanitario, ProtocoloSanitarioLancamento, QualidadeLeite,
    Sanidade, Secagem, Servico, Touro,
)
from fazenda.ordenacao import chave_numero

router = APIRouter(prefix="/animais", tags=["animais"])


@router.get("/")
def listar_animais(
    grupo: str | None = Query(None, description="Filtrar por grupo primário"),
    sit_rep: str | None = Query(None, description="Filtrar por situação reprodutiva"),
    ativo: bool = Query(True),
    incluir_machos: bool = Query(False, description="Incluir machos e sêmen (padrão: só fêmeas)"),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(Animal).where(Animal.ativo == ativo)
    if grupo:
        query = query.where(Animal.grupo_primario.contains(grupo))
    if sit_rep:
        query = query.where(Animal.sit_rep == sit_rep)

    animais = session.exec(query).all()
    if not incluir_machos:
        # Rebanho = só fêmeas. Exclui sêmen/reprodutores e machos. Registros
        # antigos (sem o campo) permanecem até o próximo upload do GERAL.
        animais = [a for a in animais if not a.eh_semen and a.sexo != "M"]

    # Datas reprodutivas por matriz: último serviço POSITIVO (concepção) e último
    # parto. Usadas no front para dias de gestação, dias para o parto e PEV.
    ult_pos: dict[str, object] = {}
    for s in session.exec(select(Servico)).all():
        d = s.data_servico
        if d and (s.diagnostico or "").strip().upper() == "POSITIVO":
            if s.numero_matriz not in ult_pos or d > ult_pos[s.numero_matriz]:
                ult_pos[s.numero_matriz] = d
    ult_parto: dict[str, object] = {}
    for p in session.exec(select(Parto)).all():
        d = p.data_parto
        if d and (p.numero_matriz not in ult_parto or d > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = d

    saida = []
    for a in animais:
        d = a.model_dump()
        sp = ult_pos.get(a.numero)
        pp = ult_parto.get(a.numero)
        d["data_ult_servico_pos"] = sp.isoformat() if sp else None
        d["data_ult_parto"] = pp.isoformat() if pp else None
        saida.append(d)
    saida.sort(key=lambda d: chave_numero(d["numero"]))
    return saida


# Lotes de lactação (convenção do sistema, mesma da Produção).
LOTES_LACTACAO = ("01", "02", "03")


def _codigo_lote(g: str | None) -> str | None:
    return g[:2] if g and len(g) >= 2 and g[:2].isdigit() else None


@router.get("/estratificacao")
def estratificacao_rebanho(session: Session = Depends(get_session)) -> dict:
    """Composição do rebanho (fêmeas ativas) por faixa etária e, nas adultas,
    por situação (lactação / secas / pré-parto). Alimenta o gráfico do Rebanho."""
    hoje = date.today()
    ult_parto: dict[str, date] = {}
    for p in session.exec(select(Parto)).all():
        if p.data_parto and (p.numero_matriz not in ult_parto or p.data_parto > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = p.data_parto
    ult_pos: dict[str, date] = {}
    for s in session.exec(select(Servico)).all():
        if s.data_servico and (s.diagnostico or "").strip().upper() == "POSITIVO":
            if s.numero_matriz not in ult_pos or s.data_servico > ult_pos[s.numero_matriz]:
                ult_pos[s.numero_matriz] = s.data_servico

    estratos = {
        "aleitamento_0_3m": 0, "recria_4_11m": 0, "recria_12_24m": 0,
        "novilhas_acima_24m": 0, "vacas_lactacao": 0, "vacas_secas": 0, "vacas_pre_parto": 0,
        "sem_data_nasc": 0,
    }
    total = 0
    for a in session.exec(select(Animal).where(Animal.ativo == True)).all():  # noqa: E712
        if a.eh_semen or a.sexo == "M":
            continue
        total += 1
        pariu = a.numero in ult_parto
        if pariu:
            # Vaca adulta: lactação (lote 01–03), pré-parto (prenhe e gestação
            # avançada ≥ 240 dias) ou seca.
            gest = (hoje - ult_pos[a.numero]).days if a.numero in ult_pos else None
            if _codigo_lote(a.grupo_primario) in LOTES_LACTACAO:
                estratos["vacas_lactacao"] += 1
            elif gest is not None and gest >= 240:
                estratos["vacas_pre_parto"] += 1
            else:
                estratos["vacas_secas"] += 1
            continue
        # Fêmea que ainda não pariu → classifica por idade.
        if not a.data_nasc:
            estratos["sem_data_nasc"] += 1
            continue
        d = (hoje - a.data_nasc).days
        if d <= 90:
            estratos["aleitamento_0_3m"] += 1
        elif d <= 364:
            estratos["recria_4_11m"] += 1
        elif d <= 730:
            estratos["recria_12_24m"] += 1
        else:
            estratos["novilhas_acima_24m"] += 1

    def pct(n: int) -> float:
        return round(100 * n / total, 1) if total else 0.0

    vacas = estratos["vacas_lactacao"] + estratos["vacas_secas"] + estratos["vacas_pre_parto"]
    return {
        "total": total,
        "estratos": estratos,
        "percentuais": {k: pct(v) for k, v in estratos.items()},
        "vacas_total": vacas,
        "pct_lactacao_sobre_total": pct(estratos["vacas_lactacao"]),
        "pct_lactacao_sobre_vacas": round(100 * estratos["vacas_lactacao"] / vacas, 1) if vacas else 0.0,
    }


@router.get("/{numero}")
def buscar_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")
    return animal.model_dump()


@router.get("/{numero}/ficha")
def ficha_animal(numero: str, session: Session = Depends(get_session)) -> dict:
    """
    Ficha única do animal: absolutamente todos os lançamentos já registrados
    para ele, reunidos em uma resposta — reprodução, parto, colostragem/IgG,
    produção, sanidade, movimentação de lote, compra/baixa e agenda. Serve
    tanto a tela de consulta quanto a exportação em PDF (por maior que fique).
    """
    animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")

    def _dump(rows) -> list[dict]:
        return [r.model_dump() for r in rows]

    partos = session.exec(select(Parto).where(Parto.numero_matriz == numero).order_by(Parto.data_parto)).all()
    # Ordem de parto = posição cronológica (1º, 2º, 3º…). Quando a fonte não
    # traz o número (ex.: animal com um único parto), deriva pela ordem da data
    # — o primeiro parto é sempre "1", não fica em branco/zero.
    partos_dump = []
    for idx, p in enumerate(partos):
        d = p.model_dump()
        if not d.get("ordem_parto"):
            d["ordem_parto"] = idx + 1
        partos_dump.append(d)
    servicos = session.exec(select(Servico).where(Servico.numero_matriz == numero).order_by(Servico.data_servico)).all()
    # Código NAAB do pai (touro/sêmen usado no serviço), buscado no catálogo de
    # sêmen pelo nome do reprodutor — anexado a cada serviço para exibir na ficha.
    naab_por_touro = {
        s.touro_nome.strip().lower(): s.naab
        for s in session.exec(select(EstoqueSemen)).all() if s.naab
    }
    # Banco de touros (provas NAAB/CDCB) — para mostrar nome + provas do pai.
    touros = session.exec(select(Touro)).all()
    touro_por_naab = {(t.naab or "").strip().upper(): t for t in touros}
    touro_por_nome = {(t.nome or "").strip().lower(): t for t in touros if t.nome}
    servicos_dump = []
    for s in servicos:
        d = s.model_dump()
        naab = naab_por_touro.get((s.reprodutor or "").strip().lower())
        d["reprodutor_naab"] = naab
        # Casa o touro pelo NAAB (ou, na falta, pelo nome do reprodutor).
        touro = (touro_por_naab.get((naab or "").strip().upper())
                 or touro_por_nome.get((s.reprodutor or "").strip().lower()))
        d["touro"] = touro.model_dump() if touro else None
        # Chaves planas para a tabela genérica da ficha (provas do pai).
        d["touro_central"] = touro.central if touro else None
        d["touro_tpi"] = touro.tpi if touro else None
        d["touro_nm"] = touro.nm_dolar if touro else None
        servicos_dump.append(d)

    # Pai deste animal (nome de guerra + NAAB): não existe FK direta — o
    # animal é a cria de um Parto da mãe, e o pai é o reprodutor do serviço
    # da mãe que mais provavelmente gerou essa gestação (o mais próximo antes
    # do parto, dentro da janela de gestação bovina — ~260 a 295 dias).
    pai = None
    parto_como_cria = session.exec(
        select(Parto).where((Parto.numero_cria_1 == numero) | (Parto.numero_cria_2 == numero))
    ).first()
    if parto_como_cria and parto_como_cria.data_parto:
        servicos_mae = session.exec(
            select(Servico).where(Servico.numero_matriz == parto_como_cria.numero_matriz).order_by(Servico.data_servico)
        ).all()
        candidatos = [
            s for s in servicos_mae
            if s.data_servico and s.reprodutor and 260 <= (parto_como_cria.data_parto - s.data_servico).days <= 295
        ]
        servico_concepcao = candidatos[-1] if candidatos else None
        if servico_concepcao:
            naab = naab_por_touro.get((servico_concepcao.reprodutor or "").strip().lower())
            touro_pai = (touro_por_naab.get((naab or "").strip().upper())
                         or touro_por_nome.get((servico_concepcao.reprodutor or "").strip().lower()))
            pai = {
                "nome": servico_concepcao.reprodutor,
                "naab": naab or (touro_pai.naab if touro_pai else None),
                "central": touro_pai.central if touro_pai else None,
                "tpi": touro_pai.tpi if touro_pai else None,
                "nm_dolar": touro_pai.nm_dolar if touro_pai else None,
            }

    protocolos_iatf = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == numero).order_by(ProtocoloIatfAplicacao.data_prevista)
    ).all()

    movimentos_lote = session.exec(
        select(MovimentoLote).where(MovimentoLote.numero_matriz == numero).order_by(MovimentoLote.data_movimento)
    ).all()

    colostragem = session.exec(select(ColostragemBezerra).where(ColostragemBezerra.numero_animal == numero)).first()

    controles_leiteiros = session.exec(
        select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == numero).order_by(ControleLeiteiro.data_controle)
    ).all()

    pesagens_corporais = session.exec(
        select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero).order_by(PesagemCorporal.data_pesagem)
    ).all()

    qualidade_leite = session.exec(
        select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero).order_by(QualidadeLeite.data_coleta)
    ).all()

    aplicacoes_sanitarias = session.exec(
        select(Sanidade).where(Sanidade.numero_matriz == numero).order_by(Sanidade.data_aplicacao)
    ).all()

    protocolos_nomes = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}
    protocolos_sanitarios_rows = session.exec(
        select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.numero_matriz == numero).order_by(ProtocoloSanitarioLancamento.data_inicio)
    ).all()
    protocolos_sanitarios = [
        {**p.model_dump(), "protocolo_nome": protocolos_nomes.get(p.protocolo_id, "—")} for p in protocolos_sanitarios_rows
    ]

    secagens = session.exec(select(Secagem).where(Secagem.numero_matriz == numero).order_by(Secagem.data_secagem)).all()

    eventos_agenda = [
        e for e in session.exec(select(AgendaManual).order_by(AgendaManual.data_evento)).all()
        if e.numero_animal and numero in [n.strip() for n in e.numero_animal.split(",")]
    ]

    baixa = session.exec(select(BaixaAnimal).where(BaixaAnimal.numero_animal == numero)).first()
    compra = session.exec(select(CompraAnimal).where(CompraAnimal.numero_animal == numero)).first()

    return {
        "animal": animal.model_dump(),
        "pai": pai,
        "partos": partos_dump,
        "servicos": servicos_dump,
        "protocolos_iatf": _dump(protocolos_iatf),
        "movimentos_lote": _dump(movimentos_lote),
        "colostragem": colostragem.model_dump() if colostragem else None,
        "controles_leiteiros": _dump(controles_leiteiros),
        "pesagens_corporais": _dump(pesagens_corporais),
        "qualidade_leite": _dump(qualidade_leite),
        "aplicacoes_sanitarias": _dump(aplicacoes_sanitarias),
        "protocolos_sanitarios": protocolos_sanitarios,
        "secagens": _dump(secagens),
        "eventos_agenda": _dump(eventos_agenda),
        "baixa": baixa.model_dump() if baixa else None,
        "compra": compra.model_dump() if compra else None,
    }
