"""
Cadastro > Protocolos Sanitários — protocolo sanitário (etapas por dia,
importação via planilha) e protocolo de indução de lactação, incluindo os
seeds dos protocolos curativos padrão (mastite, pós-parto, pneumonia,
diarreia) e dos dois protocolos de indução de lactação do produtor.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    Doenca, PrincipioAtivo, ProtocoloIatf, ProtocoloIatfEtapa, ProtocoloIatfLancamento,
    ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa, ProtocoloInducaoLancamento, ProtocoloSanitario,
    ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, SeedFlag,
)
from fazenda.rules.auditoria import fazenda_id_seguro

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Protocolo sanitário — cadastro com múltiplas etapas (produto/dosagem/via por
# dia), a exemplo do tratamento de mastite. Dias podem começar em D0 ou D1
# conforme o dia_inicial do protocolo (mesmo padrão da indução de lactação).
# ---------------------------------------------------------------------------
# Igual à lista usada no restante do site (frontend/lib/constants.ts) — as
# duas listas divergiam (esta faltava Subcutânea/Intrauterina), o que rejeitava
# no backend vias que o formulário deixava escolher.
VIAS_APLICACAO = [
    "Intramuscular", "Subcutânea", "Intravenosa", "Intramamária", "Oral", "Tópica", "Subdérmica", "Intrauterina",
    "Intravaginal", "Intradérmica", "Pour-on",
]
CRITERIOS_MEDICAMENTO = ["medicamento", "principio_ativo", "classificacao", "doenca"]
CLASSIFICACOES_MEDICAMENTO = ["Antimicrobiano", "Anti-inflamatório", "Antibiótico", "Antiparasitário", "Vacina", "Hormônio", "Outro"]
# Finalidade do protocolo sanitário de etapas. None (protocolo cadastrado
# antes desta distinção) é lido como "curativo" — ver FINALIDADE_PADRAO.
FINALIDADES_PROTOCOLO_SANITARIO = ["curativo", "preventivo"]
FINALIDADE_PADRAO = "curativo"


class ProtocoloEtapaIn(BaseModel):
    dia: int
    criterio_tipo: str = "medicamento"  # medicamento | principio_ativo | classificacao
    produto: str  # medicamento OU o valor do critério (princípio ativo / classificação)
    dosagem: float
    unidade: str
    via: str | None = None
    observacao: str | None = None  # nota livre (ex.: "Se necessário", "10ml por orelha")


class ProtocoloSanitarioIn(BaseModel):
    nome: str
    doenca_id: int | None = None
    eh_mastite: bool = False
    dia_inicial: int = 0
    finalidade: str | None = None  # curativo | preventivo — None vira "curativo"
    ativo: bool = True
    etapas: list[ProtocoloEtapaIn]


def _validar_finalidade(finalidade: str | None) -> str:
    if finalidade is None:
        return FINALIDADE_PADRAO
    if finalidade not in FINALIDADES_PROTOCOLO_SANITARIO:
        raise HTTPException(
            status_code=400,
            detail=f"Finalidade inválida — use uma de: {', '.join(FINALIDADES_PROTOCOLO_SANITARIO)}",
        )
    return finalidade


def _validar_etapas(etapas: list[ProtocoloEtapaIn]) -> None:
    if not etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in etapas:
        if e.dia < 0:
            raise HTTPException(
                status_code=400,
                detail="O dia da etapa não pode ser negativo (o protocolo pode começar em D0)",
            )
        if e.dosagem <= 0:
            raise HTTPException(status_code=400, detail="A dosagem de cada etapa deve ser positiva")
        if e.via and e.via not in VIAS_APLICACAO:
            raise HTTPException(status_code=400, detail=f"Via inválida — use uma de: {', '.join(VIAS_APLICACAO)}")
        if e.criterio_tipo not in CRITERIOS_MEDICAMENTO:
            raise HTTPException(status_code=400, detail=f"Critério inválido — use um de: {', '.join(CRITERIOS_MEDICAMENTO)}")
        if not (e.produto or "").strip():
            raise HTTPException(status_code=400, detail="Informe o medicamento, princípio ativo ou classificação de cada etapa")


def _serializar_protocolo(session: Session, p: ProtocoloSanitario, doencas: dict[int, str]) -> dict:
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == p.id).order_by(ProtocoloSanitarioEtapa.dia)
    ).all()
    return {
        **p.model_dump(),
        # Protocolo cadastrado antes da distinção curativo/preventivo não tem
        # finalidade gravada — é curativo por definição, e a tela precisa ver
        # isso resolvido em vez de um campo vazio.
        "finalidade": p.finalidade or FINALIDADE_PADRAO,
        "doenca_nome": doencas.get(p.doenca_id) if p.doenca_id else None,
        "etapas": [e.model_dump() for e in etapas],
    }


@router.get("/protocolos-sanitarios")
def listar_protocolos_sanitarios(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    query = select(ProtocoloSanitario).order_by(ProtocoloSanitario.nome)
    if fazenda_id is not None:
        query = query.where(ProtocoloSanitario.fazenda_id == fazenda_id)
    protocolos = session.exec(query).all()
    return [_serializar_protocolo(session, p, doencas) for p in protocolos]


@router.post("/protocolos-sanitarios")
def criar_protocolo_sanitario(
    dados: ProtocoloSanitarioIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(ProtocoloSanitario).where(ProtocoloSanitario.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ProtocoloSanitario.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo com o nome '{nome}'")
    _validar_etapas(dados.etapas)

    protocolo = ProtocoloSanitario(
        nome=nome, doenca_id=dados.doenca_id, eh_mastite=dados.eh_mastite,
        dia_inicial=dados.dia_inicial, finalidade=_validar_finalidade(dados.finalidade),
        ativo=dados.ativo, fazenda_id=fazenda_id,
    )
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()

    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return _serializar_protocolo(session, protocolo, doencas)


@router.put("/protocolos-sanitarios/{protocolo_id}")
def atualizar_protocolo_sanitario(
    protocolo_id: int, dados: ProtocoloSanitarioIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloSanitario, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_etapas(dados.etapas)

    protocolo.nome = nome
    protocolo.doenca_id = dados.doenca_id
    protocolo.eh_mastite = dados.eh_mastite
    protocolo.dia_inicial = dados.dia_inicial
    protocolo.finalidade = _validar_finalidade(dados.finalidade)
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == protocolo_id)).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()

    doencas = {d.id: d.nome for d in session.exec(select(Doenca)).all()}
    return _serializar_protocolo(session, protocolo, doencas)


@router.delete("/protocolos-sanitarios/{protocolo_id}")
def excluir_protocolo_sanitario(
    protocolo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloSanitario, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    ja_lancado = session.exec(
        select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.protocolo_id == protocolo_id)
    ).first()
    if ja_lancado:
        raise HTTPException(
            status_code=409,
            detail="Este protocolo já foi lançado ao menos uma vez e não pode ser excluído — desative-o em vez disso.",
        )
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas:
        session.delete(e)
    session.delete(protocolo)
    session.commit()
    return {"excluido": True}


def _upsert_protocolo_sanitario(
    session: Session, nome: str, etapas: list[dict], *, doenca_id: int | None = None, eh_mastite: bool | None = None,
    fazenda_id: int | None = None,
) -> ProtocoloSanitario:
    """Cria o protocolo se ele ainda não existir, ou substitui as etapas se já
    existir (mesma regra do PUT manual) — usado tanto pela importação de
    planilha (fazenda_id da requisição) quanto pelo cadastro automático dos
    protocolos padrão no startup (sem fazenda_id — dado legado/compartilhado,
    mesmo padrão de seed_cadastro_sanitario)."""
    etapas_in = [ProtocoloEtapaIn(**e) for e in etapas]
    _validar_etapas(etapas_in)

    query_dup = select(ProtocoloSanitario).where(ProtocoloSanitario.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ProtocoloSanitario.fazenda_id == fazenda_id)
    protocolo = session.exec(query_dup).first()
    if protocolo is None:
        protocolo = ProtocoloSanitario(
            nome=nome, doenca_id=doenca_id,
            eh_mastite=eh_mastite if eh_mastite is not None else ("mastite" in nome.lower()),
            fazenda_id=fazenda_id,
        )
        session.add(protocolo)
        session.commit()
        session.refresh(protocolo)
    else:
        if doenca_id is not None:
            protocolo.doenca_id = doenca_id
        if eh_mastite is not None:
            protocolo.eh_mastite = eh_mastite
        session.add(protocolo)
        for antiga in session.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == protocolo.id)).all():
            session.delete(antiga)
        session.commit()

    for etapa in etapas_in:
        session.add(ProtocoloSanitarioEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()
    return protocolo


# ---------------------------------------------------------------------------
# Importação de protocolo sanitário via Excel/CSV — mesmas 7 colunas do
# cadastro manual (Nome do protocolo, Dia da aplicação, Definido por,
# Medicamento, Dosagem, Unidade, Via). Cada linha é uma etapa; várias linhas
# com o mesmo nome formam um único protocolo — como nas planilhas de
# mastite/pós-parto/pneumonia/diarreia do produtor, que trazem um protocolo
# por aba. Upsert por nome: nunca apaga um protocolo ausente da planilha.
# ---------------------------------------------------------------------------
_ALIASES_COLUNA_PROTOCOLO = {
    "nome": ["nome do protocolo", "protocolo", "nome"],
    "dia": ["dia da aplicacao", "dia", "dia aplicacao"],
    "definido_por": ["definido por", "criterio", "criterio tipo"],
    "produto": ["medicamento", "produto"],
    "dosagem": ["dosagem", "dose"],
    "unidade": ["unidade", "unidade de medida"],
    "via": ["via", "via de aplicacao"],
}
_CRITERIO_POR_TEXTO = {
    "medicamento": "medicamento",
    "principio ativo": "principio_ativo",
    "doenca": "doenca",
    "classificacao": "classificacao",
}


def _norm_cabecalho(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _mapear_colunas_protocolo(cabecalhos: list) -> dict[str, int]:
    disponiveis = {_norm_cabecalho(str(c)) if c is not None else "": i for i, c in enumerate(cabecalhos)}
    mapa: dict[str, int] = {}
    for campo, apelidos in _ALIASES_COLUNA_PROTOCOLO.items():
        for ap in apelidos:
            if ap in disponiveis:
                mapa[campo] = disponiveis[ap]
                break
    return mapa


def _extrair_observacao(texto: str) -> tuple[str, str | None]:
    """Separa uma nota entre parênteses (ex.: "Lutalyse (Se necessário)") do
    valor principal, para não quebrar o casamento por nome exato do produto/via."""
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", texto.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return texto.strip(), None


def _casar_via(texto: str) -> tuple[str | None, str | None]:
    """Acha a via cadastrada (VIAS_APLICACAO) mais próxima do texto da
    planilha, devolvendo o que sobrar (ex.: "10ml por orelha") como observação."""
    base, obs = _extrair_observacao(texto)
    base_norm = _norm_cabecalho(base)
    for via in VIAS_APLICACAO:
        if _norm_cabecalho(via) == base_norm:
            return via, obs
    for via in VIAS_APLICACAO:
        via_norm = _norm_cabecalho(via)
        if via_norm and via_norm in base_norm:
            resto = base_norm.replace(via_norm, "").strip()
            extra = f"{resto} {obs}".strip() if resto else obs
            return via, (extra or None)
    return (base or None), obs


def ler_planilha_protocolos_sanitarios(content: bytes, filename: str | None) -> dict[str, list[dict]]:
    """Lê um Excel (todas as abas) ou CSV com uma linha por etapa e agrupa as
    etapas por nome de protocolo, na ordem em que aparecem na planilha."""
    nome_arquivo = (filename or "").lower()
    linhas: list[tuple[dict[str, int], tuple]] = []
    if nome_arquivo.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for ws in wb.worksheets:
            it = ws.iter_rows(values_only=True)
            try:
                cabecalho = list(next(it))
            except StopIteration:
                continue
            mapa = _mapear_colunas_protocolo(cabecalho)
            if "nome" not in mapa or "produto" not in mapa:
                continue
            for row in it:
                if row is None or all(c is None or str(c).strip() == "" for c in row):
                    continue
                linhas.append((mapa, row))
    else:
        import csv as _csv
        texto = content.decode("utf-8-sig", errors="replace")
        primeira = texto.splitlines()[0] if texto.strip() else ""
        delim = ";" if primeira.count(";") >= primeira.count(",") else ","
        leitor = list(_csv.reader(io.StringIO(texto), delimiter=delim))
        if leitor:
            mapa = _mapear_colunas_protocolo(leitor[0])
            for row in leitor[1:]:
                if not row or all(not (c or "").strip() for c in row):
                    continue
                linhas.append((mapa, row))

    protocolos: dict[str, list[dict]] = {}
    for mapa, row in linhas:
        def _cell(campo: str):
            i = mapa.get(campo)
            return row[i] if i is not None and i < len(row) else None

        nome = str(_cell("nome") or "").strip()
        produto_bruto = str(_cell("produto") or "").strip()
        if not nome or not produto_bruto:
            continue
        try:
            dia = int(float(_cell("dia") or 0))
        except (TypeError, ValueError):
            continue
        try:
            dosagem = float(_cell("dosagem") or 0)
        except (TypeError, ValueError):
            dosagem = 0.0
        unidade = str(_cell("unidade") or "").strip()
        via_bruta = str(_cell("via") or "").strip()
        definido_por = _norm_cabecalho(str(_cell("definido_por") or "medicamento"))
        criterio_tipo = _CRITERIO_POR_TEXTO.get(definido_por, "medicamento")

        produto, obs_produto = _extrair_observacao(produto_bruto)
        via, obs_via = (_casar_via(via_bruta) if via_bruta else (None, None))
        observacao = " / ".join(x for x in [obs_produto, obs_via] if x) or None

        protocolos.setdefault(nome, []).append({
            "dia": dia, "criterio_tipo": criterio_tipo, "produto": produto,
            "dosagem": dosagem, "unidade": unidade, "via": via, "observacao": observacao,
        })
    return protocolos


@router.post("/protocolos-sanitarios/importar")
async def importar_protocolos_sanitarios(
    file: UploadFile = File(...), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    conteudo = await file.read()
    protocolos = ler_planilha_protocolos_sanitarios(conteudo, file.filename)
    if not protocolos:
        raise HTTPException(
            status_code=400,
            detail="Não encontrei nenhuma linha reconhecível na planilha — confira se o cabeçalho tem as colunas: "
                   "Nome do protocolo, Dia da aplicação, Definido por, Medicamento, Dosagem, Unidade, Via.",
        )
    criados, atualizados, erros = [], [], []
    for nome, etapas in protocolos.items():
        etapas.sort(key=lambda e: e["dia"])
        query_dup = select(ProtocoloSanitario).where(ProtocoloSanitario.nome == nome)
        if fazenda_id is not None:
            query_dup = query_dup.where(ProtocoloSanitario.fazenda_id == fazenda_id)
        existia = session.exec(query_dup).first() is not None
        try:
            _upsert_protocolo_sanitario(session, nome, etapas, fazenda_id=fazenda_id)
            (atualizados if existia else criados).append(nome)
        except HTTPException as e:
            erros.append(f"{nome}: {e.detail}")
    return {"criados": criados, "atualizados": atualizados, "erros": erros}


# ---------------------------------------------------------------------------
# Protocolo de indução de lactação — cadastro do cronograma-molde (dias,
# medicamentos por princípio ativo, implante de progesterona, manejo de
# adaptação à ordenha). O lançamento em animais vive em /producao (ver
# fazenda.api.routers.producao).
# ---------------------------------------------------------------------------
TIPOS_ETAPA_INDUCAO = ["medicamento", "dispositivo", "manejo"]
ACOES_DISPOSITIVO_INDUCAO = ["colocar", "retirar"]


class EtapaInducaoIn(BaseModel):
    dia: int
    tipo: str = "medicamento"  # medicamento | dispositivo | manejo
    principio_ativo_id: int | None = None
    produto: str
    acao_dispositivo: str | None = None  # colocar | retirar (só tipo=dispositivo)
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloInducaoIn(BaseModel):
    nome: str
    dia_inicial: int = 0
    observacao: str | None = None
    ativo: bool = True
    etapas: list[EtapaInducaoIn]


def _validar_etapas_inducao(etapas: list[EtapaInducaoIn]) -> None:
    if not etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in etapas:
        if e.tipo not in TIPOS_ETAPA_INDUCAO:
            raise HTTPException(status_code=400, detail=f"Tipo de etapa inválido — use um de: {', '.join(TIPOS_ETAPA_INDUCAO)}")
        if not (e.produto or "").strip():
            raise HTTPException(status_code=400, detail="Informe o produto/princípio ativo ou a ação de cada etapa")
        if e.tipo == "dispositivo" and e.acao_dispositivo not in ACOES_DISPOSITIVO_INDUCAO:
            raise HTTPException(status_code=400, detail="Etapa de dispositivo precisa de acao_dispositivo: colocar | retirar")
        if e.tipo == "medicamento" and (e.dose is not None and e.dose <= 0):
            raise HTTPException(status_code=400, detail="A dose de uma etapa de medicamento deve ser positiva")


def _serializar_protocolo_inducao(session: Session, p: ProtocoloInducaoLactacao) -> dict:
    etapas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa)
        .where(ProtocoloInducaoLactacaoEtapa.protocolo_id == p.id)
        .order_by(ProtocoloInducaoLactacaoEtapa.dia)
    ).all()
    return {**p.model_dump(), "etapas": [e.model_dump() for e in etapas]}


@router.get("/protocolos-inducao-lactacao")
def listar_protocolos_inducao(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ProtocoloInducaoLactacao).order_by(ProtocoloInducaoLactacao.nome)
    if fazenda_id is not None:
        query = query.where(ProtocoloInducaoLactacao.fazenda_id == fazenda_id)
    protocolos = session.exec(query).all()
    return [_serializar_protocolo_inducao(session, p) for p in protocolos]


@router.post("/protocolos-inducao-lactacao")
def criar_protocolo_inducao(
    dados: ProtocoloInducaoIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(ProtocoloInducaoLactacao).where(ProtocoloInducaoLactacao.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ProtocoloInducaoLactacao.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo com o nome '{nome}'")
    _validar_etapas_inducao(dados.etapas)

    protocolo = ProtocoloInducaoLactacao(
        nome=nome, dia_inicial=dados.dia_inicial, observacao=dados.observacao, ativo=dados.ativo,
        fazenda_id=fazenda_id,
    )
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_inducao(session, protocolo)


@router.put("/protocolos-inducao-lactacao/{protocolo_id}")
def atualizar_protocolo_inducao(
    protocolo_id: int, dados: ProtocoloInducaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloInducaoLactacao, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_etapas_inducao(dados.etapas)

    protocolo.nome = nome
    protocolo.dia_inicial = dados.dia_inicial
    protocolo.observacao = dados.observacao
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=protocolo.id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_inducao(session, protocolo)


@router.delete("/protocolos-inducao-lactacao/{protocolo_id}")
def excluir_protocolo_inducao(
    protocolo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Cópia estrutural de `excluir_protocolo_sanitario`/`excluir_protocolo_iatf_cadastrado`
    (G8) — mesmo padrão de bloqueio quando já houve lançamento: aqui o
    caminho recomendado é desativar (`ativo=False`), não apagar histórico."""
    protocolo = session.get(ProtocoloInducaoLactacao, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    ja_lancado = session.exec(
        select(ProtocoloInducaoLancamento).where(ProtocoloInducaoLancamento.protocolo_id == protocolo_id)
    ).first()
    if ja_lancado:
        raise HTTPException(
            status_code=409,
            detail="Este protocolo já foi lançado ao menos uma vez e não pode ser excluído — desative-o (campo Ativo) em vez disso.",
        )
    etapas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.protocolo_id == protocolo_id)
    ).all()
    for e in etapas:
        session.delete(e)
    session.delete(protocolo)
    session.commit()
    return {"excluido": True}


# ---------------------------------------------------------------------------
# Protocolo IATF — cadastro do molde de hormônios. O dia de cada etapa é
# LIVRE (qualquer inteiro ≥ 0) — antes ficava travado em D0/D7/D9, mas existe
# protocolo de verdade com outro espaçamento (ex.: D0, D8, D10, D12). A
# inseminação nunca faz parte do molde (não se cadastra hormônio nela): ela é
# sempre 2 dias depois da ÚLTIMA etapa cadastrada — D9 → D11 no protocolo
# clássico, D12 → D14 num protocolo D0/D8/D10/D12 (ver
# fazenda.rules.protocolo_iatf.dia_inseminacao). Padronizado no mesmo formato
# do protocolo sanitário/indução: mesmo seletor de insumo (medicamento/
# princípio ativo/classificação). O lançamento em animais continua em
# /reproducao (POST /reproducao/protocolo-iatf).
# ---------------------------------------------------------------------------


class EtapaIatfIn(BaseModel):
    dia: int
    criterio_tipo: str = "medicamento"  # medicamento | principio_ativo | classificacao
    principio_ativo_id: int | None = None
    produto: str
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloIatfIn(BaseModel):
    nome: str
    observacao: str | None = None
    ativo: bool = True
    etapas: list[EtapaIatfIn]


def _validar_etapas_iatf(etapas: list[EtapaIatfIn]) -> None:
    if not etapas:
        raise HTTPException(status_code=400, detail="Informe ao menos uma etapa do protocolo")
    for e in etapas:
        if e.dia < 0:
            raise HTTPException(status_code=400, detail="O dia da etapa não pode ser negativo — o protocolo começa em D0")
        if e.criterio_tipo not in CRITERIOS_MEDICAMENTO:
            raise HTTPException(status_code=400, detail=f"Critério inválido — use um de: {', '.join(CRITERIOS_MEDICAMENTO)}")
        if not (e.produto or "").strip():
            raise HTTPException(status_code=400, detail="Informe o medicamento, princípio ativo ou classificação de cada etapa")
        if e.dose is not None and e.dose <= 0:
            raise HTTPException(status_code=400, detail="A dose de uma etapa deve ser positiva")


def _serializar_protocolo_iatf(session: Session, p: ProtocoloIatf) -> dict:
    etapas = session.exec(
        select(ProtocoloIatfEtapa).where(ProtocoloIatfEtapa.protocolo_id == p.id).order_by(ProtocoloIatfEtapa.dia)
    ).all()
    return {**p.model_dump(), "etapas": [e.model_dump() for e in etapas]}


@router.get("/protocolos-iatf")
def listar_protocolos_iatf_cadastrados(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(ProtocoloIatf).order_by(ProtocoloIatf.nome)
    if fazenda_id is not None:
        query = query.where(ProtocoloIatf.fazenda_id == fazenda_id)
    protocolos = session.exec(query).all()
    return [_serializar_protocolo_iatf(session, p) for p in protocolos]


@router.post("/protocolos-iatf")
def criar_protocolo_iatf_cadastrado(
    dados: ProtocoloIatfIn, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(ProtocoloIatf).where(ProtocoloIatf.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(ProtocoloIatf.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um protocolo IATF com o nome '{nome}'")
    _validar_etapas_iatf(dados.etapas)

    protocolo = ProtocoloIatf(nome=nome, observacao=dados.observacao, ativo=dados.ativo, fazenda_id=fazenda_id)
    session.add(protocolo)
    session.commit()
    session.refresh(protocolo)
    for etapa in dados.etapas:
        session.add(ProtocoloIatfEtapa(protocolo_id=protocolo.id, fazenda_id=fazenda_id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_iatf(session, protocolo)


@router.put("/protocolos-iatf/{protocolo_id}")
def atualizar_protocolo_iatf_cadastrado(
    protocolo_id: int, dados: ProtocoloIatfIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloIatf, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    _validar_etapas_iatf(dados.etapas)

    protocolo.nome = nome
    protocolo.observacao = dados.observacao
    protocolo.ativo = dados.ativo
    session.add(protocolo)

    etapas_antigas = session.exec(select(ProtocoloIatfEtapa).where(ProtocoloIatfEtapa.protocolo_id == protocolo_id)).all()
    for e in etapas_antigas:
        session.delete(e)
    session.commit()
    for etapa in dados.etapas:
        session.add(ProtocoloIatfEtapa(protocolo_id=protocolo.id, fazenda_id=fazenda_id, **etapa.model_dump()))
    session.commit()
    return _serializar_protocolo_iatf(session, protocolo)


@router.delete("/protocolos-iatf/{protocolo_id}")
def excluir_protocolo_iatf_cadastrado(
    protocolo_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    protocolo = session.get(ProtocoloIatf, protocolo_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not protocolo or (fazenda_id is not None and protocolo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    ja_lancado = session.exec(
        select(ProtocoloIatfLancamento).where(ProtocoloIatfLancamento.protocolo_id == protocolo_id)
    ).first()
    if ja_lancado:
        raise HTTPException(
            status_code=409,
            detail="Este protocolo já foi lançado ao menos uma vez e não pode ser excluído — desative-o em vez disso.",
        )
    etapas = session.exec(select(ProtocoloIatfEtapa).where(ProtocoloIatfEtapa.protocolo_id == protocolo_id)).all()
    for e in etapas:
        session.delete(e)
    session.delete(protocolo)
    session.commit()
    return {"excluido": True}


# Cronograma das duas planilhas do produtor ("Protocolo Ativos 1" — 28 dias,
# D0 a D27, e manutenção da bST depois disso — e "Protocolo Ativos 2" — 18
# dias, D0 a D18). Doses/unidades e dias vêm literalmente das planilhas
# anexadas; "Somatotropina Bovina (bST)" não tinha princípio ativo cadastrado
# — foi criado aqui para compatibilizar com o restante do sistema (mesmo
# grupo/categoria dos demais hormônios reprodutivos).
# Os dias abaixo já são 0-based (dia_inicial=0) — antes desta padronização
# em D0 (jul/2026) este protocolo era D1-based (dia_inicial=1); quem já
# tinha rodado o seed antigo é corrigido por seed_inducao_lactacao_ativos1_d0
# (mesmo offset de datas: dia - dia_inicial é idêntico nos dois casos).
SEED_PRINCIPIOS_INDUCAO = ["Somatotropina Bovina (bST)"]

# (dia, tipo, produto/principio, acao_dispositivo, dose, unidade, via)
SEED_ETAPAS_INDUCAO_1 = [
    (0, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (0, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (0, "dispositivo", "Implante de Progesterona", "colocar", None, None, None),
    (1, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (2, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (3, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (4, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (5, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (6, "medicamento", "Benzoato de Estradiol", None, 30, "ml", None),
    (7, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (7, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (7, "dispositivo", "Implante de Progesterona", "retirar", None, None, None),
    (8, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (9, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (10, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (11, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (12, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (13, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (14, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (14, "medicamento", "Benzoato de Estradiol", None, 20, "ml", None),
    (15, "medicamento", "Cloprostenol Sódico / D-Cloprostenol", None, 3, "ml", None),
    (16, "manejo", "Adaptação na ordenha", None, None, None, None),
    (17, "manejo", "Adaptação na ordenha", None, None, None, None),
    (18, "medicamento", "Dexametasona", None, 20, "ml", None),
    (18, "manejo", "Adaptação na ordenha", None, None, None, None),
    (19, "medicamento", "Dexametasona", None, 20, "ml", None),
    (19, "manejo", "Adaptação na ordenha", None, None, None, None),
    (20, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (20, "medicamento", "Dexametasona", None, 20, "ml", None),
    (20, "manejo", "Adaptação na ordenha", None, None, None, None),
    (21, "manejo", "COMEÇAR A ORDENHA", None, None, None, None),
    (27, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
]

SEED_ETAPAS_INDUCAO_2 = [
    (0, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (0, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (0, "dispositivo", "Implante de Progesterona", "colocar", None, None, None),
    (2, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (4, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (6, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (8, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (8, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (10, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (12, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (14, "medicamento", "Somatotropina Bovina (bST)", None, None, "dose", None),
    (14, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (15, "medicamento", "Cloprostenol Sódico / D-Cloprostenol", None, None, "dose", None),
    (15, "medicamento", "Dexametasona", None, 10, "ml", None),
    (15, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (15, "dispositivo", "Implante de Progesterona", "retirar", None, None, None),
    (16, "medicamento", "Dexametasona", None, 10, "ml", None),
    (16, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (17, "medicamento", "Dexametasona", None, 10, "ml", None),
    (17, "medicamento", "Benzoato de Estradiol", None, 2, "ml", None),
    (18, "manejo", "INICIAR A ORDENHA", None, None, None, None),
]


def seed_protocolos_inducao_lactacao(session: Session) -> None:
    """
    Cadastra os dois protocolos de indução de lactação (18 e 28 dias) a partir
    das planilhas do produtor, por princípio ativo. Roda UMA vez (SeedFlag) —
    depois disso os dois protocolos ficam livres para o usuário editar/excluir
    em Configurações > Cadastro, sem que reinicializações apaguem as edições.
    """
    chave = "protocolos_inducao_lactacao_v1"
    if session.get(SeedFlag, chave):
        return

    for nome_pa in SEED_PRINCIPIOS_INDUCAO:
        if not session.exec(select(PrincipioAtivo).where(PrincipioAtivo.nome == nome_pa)).first():
            session.add(PrincipioAtivo(nome=nome_pa, categoria="Fármacos Reprodutivos e Hormônios"))
    session.commit()

    principios_por_nome = {p.nome: p.id for p in session.exec(select(PrincipioAtivo)).all()}

    def _criar(nome: str, dia_inicial: int, observacao: str, etapas: list[tuple]) -> None:
        if session.exec(select(ProtocoloInducaoLactacao).where(ProtocoloInducaoLactacao.nome == nome)).first():
            return
        protocolo = ProtocoloInducaoLactacao(nome=nome, dia_inicial=dia_inicial, observacao=observacao)
        session.add(protocolo)
        session.commit()
        session.refresh(protocolo)
        for dia, tipo, produto, acao, dose, unidade, via in etapas:
            session.add(ProtocoloInducaoLactacaoEtapa(
                protocolo_id=protocolo.id, dia=dia, tipo=tipo, produto=produto,
                principio_ativo_id=principios_por_nome.get(produto) if tipo == "medicamento" else None,
                acao_dispositivo=acao, dose=dose, unidade=unidade, via=via,
            ))
        session.commit()

    _criar(
        "Protocolo de Indução de Lactação — 28 dias (Ativos 1)", 0,
        "Manter a bST (Somatotropina Bovina) a cada 12 dias até o final da lactação — "
        "a partir do D27 a vaca entra no ciclo normal de aplicação de bST do rebanho (Sanidade > Preventiva > BST).",
        SEED_ETAPAS_INDUCAO_1,
    )
    _criar(
        "Protocolo de Indução de Lactação — 18 dias (Ativos 2)", 0,
        "Protocolo intensivo (63 animais) — aplicações em dias alternados; nos dias de INTERVALO não há nenhuma etapa.",
        SEED_ETAPAS_INDUCAO_2,
    )

    session.add(SeedFlag(chave=chave))
    session.commit()


def seed_inducao_lactacao_ativos1_d0(session: Session) -> None:
    """
    Uma única vez (SeedFlag): normaliza o protocolo "Ativos 1" (28 dias) para
    também começar em D0, como todos os demais protocolos do sistema
    (sanitários e o outro protocolo de indução, "Ativos 2") passaram a fazer
    nesta padronização (jul/2026). Quando `seed_protocolos_inducao_lactacao`
    já rodou num deploy anterior a esta mudança, o protocolo já existe no
    banco com `dia_inicial=1` e etapas em D1..D28 — aqui subtraímos 1 do dia
    de cada etapa e zeramos `dia_inicial`, preservando exatamente as mesmas
    datas de aplicação (a fórmula de cálculo é `dia - dia_inicial`, então
    D1/dia_inicial=1 e D0/dia_inicial=0 produzem o mesmo offset). Em bancos
    novos, o seed acima já cria o protocolo com SEED_ETAPAS_INDUCAO_1
    renumerado e dia_inicial=0 — esta função não encontra nada para corrigir
    e só marca a flag.
    """
    chave = "inducao_lactacao_ativos1_d0_202607"
    if session.get(SeedFlag, chave):
        return
    protocolo = session.exec(
        select(ProtocoloInducaoLactacao).where(
            ProtocoloInducaoLactacao.nome == "Protocolo de Indução de Lactação — 28 dias (Ativos 1)"
        )
    ).first()
    if protocolo and protocolo.dia_inicial == 1:
        etapas = session.exec(
            select(ProtocoloInducaoLactacaoEtapa).where(ProtocoloInducaoLactacaoEtapa.protocolo_id == protocolo.id)
        ).all()
        for etapa in etapas:
            etapa.dia -= 1
            session.add(etapa)
        protocolo.dia_inicial = 0
        session.add(protocolo)
    session.add(SeedFlag(chave=chave))
    session.commit()


# ---------------------------------------------------------------------------
# Protocolos sanitários curativos — mastite, pós-parto/retenção de placenta,
# pneumonia e diarreia, cadastrados a partir das planilhas do produtor (uma
# aba por protocolo, uma linha por etapa: dia, medicamento, dosagem, unidade,
# via). Mesmo formato aceito pela importação manual em
# POST /cadastro/protocolos-sanitarios/importar.
# ---------------------------------------------------------------------------
SEED_PROTOCOLOS_SANITARIOS_CURATIVOS = "protocolos_sanitarios_curativos_v1"


def _tuplas_para_etapas(tuplas: list[tuple]) -> list[dict]:
    return [
        {"dia": dia, "criterio_tipo": "medicamento", "produto": produto, "dosagem": float(dose),
         "unidade": unidade, "via": via, "observacao": obs}
        for dia, produto, dose, unidade, via, obs in tuplas
    ]


_PROTOCOLOS_SANITARIOS_CURATIVOS: list[dict] = [
    {
        "nome": "Mastite - Protocolo 1", "doenca": "Mastite", "eh_mastite": True,
        "etapas": _tuplas_para_etapas([
            (1, "Borgal", 40, "ml", "Intramuscular", None),
            (1, "Spectramast", 2, "unidade", "Intramamária", None),
            (2, "Spectramast", 2, "unidade", "Intramamária", None),
            (3, "Borgal", 40, "ml", "Intramuscular", None),
            (3, "Spectramast", 2, "unidade", "Intramamária", None),
            (4, "Spectramast", 2, "unidade", "Intramamária", None),
            (5, "Spectramast", 2, "unidade", "Intramamária", None),
        ]),
    },
    {
        "nome": "Mastite - Protocolo 2", "doenca": "Mastite", "eh_mastite": True,
        "etapas": _tuplas_para_etapas([
            (1, "Agemoxi", 50, "ml", "Intramuscular", None),
            (1, "Mastijet", 2, "unidade", "Intramamária", None),
            (2, "Mastijet", 2, "unidade", "Intramamária", None),
            (3, "Agemoxi", 50, "ml", "Intramuscular", None),
            (3, "Mastijet", 2, "unidade", "Intramamária", None),
            (4, "Mastijet", 2, "unidade", "Intramamária", None),
            (5, "Mastijet", 2, "unidade", "Intramamária", None),
        ]),
    },
    {
        "nome": "Mastite - Protocolo 3", "doenca": "Mastite", "eh_mastite": True,
        "etapas": _tuplas_para_etapas([
            (1, "Gentopen", 30, "ml", "Intramuscular", None),
            (1, "Mastite Clínica VL", 2, "unidade", "Intramamária", None),
            (2, "Gentopen", 30, "ml", "Intramuscular", None),
            (2, "Mastite Clínica VL", 2, "unidade", "Intramamária", None),
            (3, "Gentopen", 30, "ml", "Intramuscular", None),
            (3, "Mastite Clínica VL", 2, "unidade", "Intramamária", None),
            (4, "Gentopen", 30, "ml", "Intramuscular", None),
            (4, "Mastite Clínica VL", 2, "unidade", "Intramamária", None),
            (5, "Gentopen", 30, "ml", "Intramuscular", None),
            (5, "Mastite Clínica VL", 2, "unidade", "Intramamária", None),
        ]),
    },
    {
        "nome": "Pós-Parto - Vaca Grande", "doenca": None, "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Drench", 1, "ml", "Oral", None),
            (1, "Lutalyse", 5, "ml", "Intravenosa", None),
            (1, "TurboCA", 250, "ml", "Intravenosa", None),
            (1, "Mercepton", 100, "ml", "Intravenosa", None),
        ]),
    },
    {
        "nome": "Pós-Parto - Novilha Grande", "doenca": None, "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Propileno", 110, "ml", "Oral", None),
            (1, "Lutalyse", 5, "ml", "Intramuscular", None),
        ]),
    },
    {
        "nome": "Pós-Parto - Aborto", "doenca": None, "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Terramicina LA", 1, "frasco", "Intramuscular", None),
        ]),
    },
    {
        "nome": "Retenção de Placenta", "doenca": "Retenção de Placenta", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Terramicina LA", 1, "frasco", "Intramuscular", None),
            (5, "Excede", 20, "ml", "Subcutânea", "10ml por orelha"),
            (30, "Lutalyse", 5, "ml", "Intramuscular", "Se necessário"),
            (30, "Metricure", 1, "unidade", "Intrauterina", "Se necessário"),
        ]),
    },
    {
        "nome": "Pneumonia - Protocolo A", "doenca": "Pneumonia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Resflor", 2, "ml / 15kg PV", "Subcutânea", None),
            (1, "Aliv V", 10, "ml", "Intramuscular", None),
            (2, "Banamine", 2, "ml / 40kg PV", "Intramuscular", None),
            (2, "Aliv V", 10, "ml", "Intramuscular", None),
            (3, "Resflor", 2, "ml / 15kg PV", "Subcutânea", None),
            (3, "Aliv V", 10, "ml", "Intramuscular", None),
            (4, "Aliv V", 10, "ml", "Intramuscular", None),
            (5, "Aliv V", 10, "ml", "Intramuscular", None),
        ]),
    },
    {
        "nome": "Pneumonia - Protocolo B", "doenca": "Pneumonia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Advocin", 1, "ml / 30kg PV", "Intramuscular", None),
            (1, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (2, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (3, "Advocin", 1, "ml / 30kg PV", "Intramuscular", None),
            (3, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (4, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (5, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
        ]),
    },
    {
        "nome": "Pneumonia - Protocolo C", "doenca": "Pneumonia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Pencivet", 1, "ml / 25kg PV", "Intramuscular", None),
            (1, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (2, "Pencivet", 1, "ml / 25kg PV", "Intramuscular", None),
            (2, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (3, "Pencivet", 1, "ml / 25kg PV", "Intramuscular", None),
            (3, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (4, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (5, "Maxicam 2%", 2.5, "ml / 100kg PV", "Intramuscular", None),
        ]),
    },
    {
        "nome": "Diarreia - Protocolo 1", "doenca": "Diarreia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (1, "Borgal", 3, "ml / 50kg PV", "Intramuscular", None),
            (2, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (2, "Biobac", 4, "g", "Oral", None),
            (3, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (3, "Borgal", 3, "ml / 50kg PV", "Intramuscular", None),
            (3, "Biobac", 4, "g", "Oral", None),
            (4, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (4, "Biobac", 4, "g", "Oral", None),
            (5, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (5, "Biobac", 4, "g", "Oral", None),
        ]),
    },
    {
        "nome": "Diarreia - Protocolo 2", "doenca": "Diarreia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Advocin", 1, "ml / 30kg PV", "Intramuscular", None),
            (1, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (1, "Trigental", 4, "g", "Oral", None),
            (2, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (2, "Biobac", 4, "g", "Oral", None),
            (3, "Advocin", 1, "ml / 30kg PV", "Intramuscular", None),
            (3, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (3, "Biobac", 4, "g", "Oral", None),
            (4, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (4, "Biobac", 4, "g", "Oral", None),
            (5, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (5, "Biobac", 4, "g", "Oral", None),
        ]),
    },
    {
        "nome": "Diarreia - Protocolo 3", "doenca": "Diarreia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Resflor", 2, "ml / 15kg PV", "Subcutânea", None),
            (2, "Biobac", 4, "g", "Oral", None),
            (3, "Resflor", 2, "ml / 15kg PV", "Subcutânea", None),
            (3, "Biobac", 4, "g", "Oral", None),
            (4, "Biobac", 4, "g", "Oral", None),
            (5, "Biobac", 4, "g", "Oral", None),
        ]),
    },
    {
        "nome": "Diarreia - Protocolo 4", "doenca": "Diarreia", "eh_mastite": False,
        "etapas": _tuplas_para_etapas([
            (1, "Trigental", 4, "g", "Oral", None),
            (1, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (2, "Trigental", 4, "g", "Oral", None),
            (2, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (3, "Trigental", 4, "g", "Oral", None),
            (3, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (4, "Trigental", 4, "g", "Oral", None),
            (4, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
            (5, "Trigental", 4, "g", "Oral", None),
            (5, "Maxican", 2.5, "ml / 100kg PV", "Intramuscular", None),
        ]),
    },
]


def seed_protocolos_sanitarios_curativos(session: Session) -> None:
    """
    Cadastra os protocolos sanitários curativos das planilhas do produtor
    (mastite, pós-parto/retenção de placenta, pneumonia e diarreia) e remove o
    protocolo de mastite único que existia antes das 3 variantes acima — só
    quando ele nunca foi usado num lançamento (histórico nunca é apagado).
    Roda uma vez (SeedFlag); depois disso os protocolos ficam livres para o
    usuário editar/excluir em Configurações > Cadastro (mesma convenção de
    seed_protocolos_inducao_lactacao).
    """
    chave = SEED_PROTOCOLOS_SANITARIOS_CURATIVOS
    nomes_novos = {p["nome"] for p in _PROTOCOLOS_SANITARIOS_CURATIVOS}
    if session.get(SeedFlag, chave):
        # A flag só marca que já rodou uma vez — confere se os protocolos
        # ainda existem antes de confiar nela (mesma cautela do bootstrap de
        # touros: perda de dados independente da flag nunca se autocorrigiria).
        existentes = {
            p.nome for p in session.exec(
                select(ProtocoloSanitario).where(ProtocoloSanitario.nome.in_(nomes_novos))
            ).all()
        }
        if existentes == nomes_novos:
            return

    # Remove o(s) protocolo(s) de mastite antigo(s) — cadastrado(s) manualmente
    # antes desta importação, com um nome fora do conjunto novo — só se nunca
    # foi usado num lançamento; do contrário deixa como está (o histórico não
    # pode sumir) e ele continua disponível para exclusão manual em
    # Configurações > Cadastro > Excluir cadastros.
    antigos = session.exec(
        select(ProtocoloSanitario).where(
            ProtocoloSanitario.eh_mastite == True,  # noqa: E712
            ~ProtocoloSanitario.nome.in_(nomes_novos),
        )
    ).all()
    for antigo in antigos:
        tem_lancamento = session.exec(
            select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.protocolo_id == antigo.id)
        ).first()
        if tem_lancamento:
            logger.warning(
                "Protocolo de mastite antigo '%s' (id=%s) tem lançamentos e não foi removido automaticamente — "
                "exclua manualmente em Configurações > Cadastro > Excluir cadastros, se ainda fizer sentido.",
                antigo.nome, antigo.id,
            )
            continue
        # Savepoint isolado: qualquer falha ao apagar (ex.: alguma restrição do
        # banco que não previmos) só pula este protocolo — nunca derruba o
        # startup do app inteiro (já aconteceu: travou um deploy em produção).
        try:
            with session.begin_nested():
                for etapa in session.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == antigo.id)).all():
                    session.delete(etapa)
                session.delete(antigo)
                session.flush()
        except Exception:
            logger.exception(
                "Falha ao remover o protocolo de mastite antigo '%s' (id=%s) — seguindo sem apagá-lo. "
                "Exclua manualmente em Configurações > Cadastro > Excluir cadastros, se ainda fizer sentido.",
                antigo.nome, antigo.id,
            )
    session.commit()

    doencas_por_nome = {d.nome: d.id for d in session.exec(select(Doenca)).all()}

    def _doenca_id(nome: str | None) -> int | None:
        if not nome:
            return None
        if nome not in doencas_por_nome:
            doenca = Doenca(nome=nome)
            session.add(doenca)
            session.commit()
            session.refresh(doenca)
            doencas_por_nome[nome] = doenca.id
        return doencas_por_nome[nome]

    for spec in _PROTOCOLOS_SANITARIOS_CURATIVOS:
        _upsert_protocolo_sanitario(
            session, spec["nome"], spec["etapas"],
            doenca_id=_doenca_id(spec["doenca"]), eh_mastite=spec["eh_mastite"],
        )

    if not session.get(SeedFlag, chave):
        session.add(SeedFlag(chave=chave))
    session.commit()




