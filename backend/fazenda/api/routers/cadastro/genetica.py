"""
Cadastro > Central de Sêmen e Touros — estoque de sêmen por touro (doses) e o
catálogo genético de touros (NAAB/provas). `router_touros_leitura` é montado
separadamente em main.py (aceita tanto o módulo "parametros" quanto
"rebanho"), por isso continua sendo um APIRouter à parte, reexportado por
`fazenda.api.routers.cadastro`.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.api.routers.estoque import sincronizar_item_estoque_semen
from fazenda.models import EstoqueSemen, SeedFlag, Servico, Touro
from fazenda.parsers.utils import parse_date
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.parametros import minimos_semen_por_tipo
from fazenda.rules.reproducao_analise import analisar_servicos
from fazenda.rules.touros import calcular_prova_ao_vivo, calcular_prova_media, casar_touro

router = APIRouter()

# Leitura do banco de touros: usada tanto em Configurações > Cadastro (módulo
# "parametros") quanto em Rebanho > Touros (módulo "rebanho") — roteador à
# parte porque `router` acima é montado em main.py exigindo só "parametros",
# e essa consulta específica precisa aceitar qualquer um dos dois módulos.
router_touros_leitura = APIRouter(prefix="/cadastro", tags=["cadastro"])

# ---------------------------------------------------------------------------
# Estoque de sêmen — doses por touro (usado no relatório de manejo).
# ---------------------------------------------------------------------------
TIPOS_SEMEN = ["convencional", "sexado", "fazenda"]
# Estoque mínimo de sêmen POR CATEGORIA (não por touro) — editável em
# Configurações > Cadastro > Central de Sêmen > Estoque mínimo, ver
# `fazenda.rules.parametros.minimos_semen_por_tipo`. Abaixo disso, gera
# alerta nas notificações e um evento diário na agenda até a NF suprir.
# Touros da fazenda (monta natural) — sempre disponíveis na inseminação.
TOUROS_FAZENDA = ["Sevaverde", "Frederico"]


def seed_semen_categorias(session: Session, fazenda_id: int | None = None) -> None:
    """Garante os touros da fazenda (Sevaverde, Frederico) como categoria
    'fazenda' e classifica o Hagen como sexado. Idempotente (SeedFlag) —
    dados históricos reais da fazenda #1, não vocabulário para replicar em
    fazenda nova (ver provisionar_fazenda_nova)."""
    chave = "semen_categorias_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for nome in TOUROS_FAZENDA:
        atual = existentes.get(nome.lower())
        if atual:
            atual.tipo = "fazenda"
            session.add(atual)
        else:
            session.add(EstoqueSemen(touro_nome=nome, tipo="fazenda", doses=0, fazenda_id=fazenda_id))
    hagen = existentes.get("hagen")
    if hagen:
        hagen.tipo = "sexado"
        session.add(hagen)
    session.add(SeedFlag(chave=chave))
    session.commit()


# Carga inicial do estoque de sêmen (planilha "estoque_de_semen.csv"): touro,
# categoria, doses, valor unitário e local. Roda UMA vez (SeedFlag); depois o
# usuário edita pela tela sem ser sobrescrito.
SEED_ESTOQUE_SEMEN = [
    # (touro, tipo, doses, valor_unitario, local)
    ("COORS", "convencional", 2, 4.19, "Caneca 1"),
    ("GUINESS", "convencional", 1, 22.67, "Caneca 1"),
    ("HAGEN", "sexado", 2, 125.00, "Caneca 1"),
    ("JAG", "convencional", 1, 0.0, "Caneca 1"),
    ("MOSAIC", "convencional", 1, 0.0, "Caneca 1"),
    ("PRAFESS", "convencional", 1, 0.0, "Caneca 1"),
    ("STORMY", "convencional", 1, 0.0, "Caneca 1"),
]


def seed_estoque_semen_inicial(session: Session, fazenda_id: int | None = None) -> None:
    """Lança o estoque de sêmen da planilha (upsert por touro). Idempotente
    (SeedFlag) — não sobrescreve edições posteriores do usuário. Dados
    históricos reais da fazenda #1, não vocabulário para fazenda nova."""
    chave = "estoque_semen_inicial_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for touro, tipo, doses, valor, local in SEED_ESTOQUE_SEMEN:
        atual = existentes.get(touro.lower())
        if atual:
            atual.tipo = tipo
            atual.doses = doses
            atual.valor_unitario = valor
            atual.local_armazenamento = local
            atual.atualizado_em = datetime.utcnow()
            session.add(atual)
        else:
            session.add(EstoqueSemen(
                touro_nome=touro, codigo=touro, tipo=tipo, doses=doses,
                valor_unitario=valor, local_armazenamento=local, fazenda_id=fazenda_id,
            ))
    session.add(SeedFlag(chave=chave))
    session.commit()


# Atualização do estoque de sêmen a partir do print enviado (contagem mais
# recente, por touro). Roda UMA vez (SeedFlag próprio, distinto do inicial —
# esse já foi consumido em produção): casa pelo nome curto já cadastrado
# (upsert, renomeando para o nome completo do pedigree) e cria os touros
# ainda não lançados. A linha "TOURO" (sem pedigree, código genérico) foi
# excluída a pedido — nunca cadastrada. Frederico, Sevaverde e ABS Newman-ET
# entram com a quantidade do print DESCONSIDERADA (mantém/zera), conforme
# instrução — os dois primeiros já são touros de monta natural sempre
# disponíveis (tipo "fazenda", doses irrelevantes).
SEED_ESTOQUE_SEMEN_202607 = [
    # (nome curto já cadastrado OU None se for novo, nome completo, código/naab, central, tipo, doses, local)
    ("hagen", "DENOVO 22094 HAGEN-ET", "29HO21643", "ABS", "sexado", 6, "Caneca 1"),
    ("stormy", "STORMY", "029HO19829", "ABS", "convencional", 1, "Caneca 1"),
    ("prafess", "SIEMERS OUT PRAFESS-ET", "3272850936", "ABS", "convencional", 1, "Caneca 1"),
    ("mosaic", "MOSAIC", "029HO18803", "ABS", "convencional", 1, "Caneca 1"),
    ("jag", "T-SPRUCE DENOVO JAG-ET", "29HO21688", "ABS", "convencional", 0, "Caneca 1"),
    ("guiness", "A.R.KK. MYTYME GUINESS 763", "29HO22747", "ABS", "convencional", 6, "Caneca 1"),
    ("coors", "A.R.K. ESQUIRE COORS 758", "29HO22744", "ABS", "convencional", 0, "Caneca 1"),
    (None, "A.R.K. MYTYME HILLUX 70", "29HO21898", "ABS", "convencional", 0, "Caneca 1"),
    (None, "A.R.K. STARGAZER MESSI", "29HO21627", "ABS", "convencional", 0, "Caneca 1"),
    (None, "DELEGADO HOMESTEAD FIV GRF", "1800D", "ABS", "convencional", 1, "Caneca 2"),
    (None, "WV-OAKWOOD SHOTTLE ALDO-ET", "001HO09218", "ABS", "convencional", 0, "Caneca 1"),
    (None, "ABS NEWMAN-ET", "029HO18586", "ABS", "convencional", 0, "Caneca 1"),  # quantidade do print (2) desconsiderada
    (None, "SUCESSOR", "6000BD", "ABS", "sexado", 0, "Caneca 1"),
    (None, "ROBO", "9300AN", "ABS", "convencional", 0, "Caneca 1"),
    (None, "METEORO", "5890BJ", "ABS", "sexado", 0, "Caneca 1"),
    (None, "NABIL", "1956AO", "ABS", "sexado", 0, "Caneca 1"),
    (None, "CAMPEAO FIV RIO DO LEITE", "6555AK", "ABS", "convencional", 0, "Caneca 1"),
]


def atualizar_estoque_semen_202607(session: Session, fazenda_id: int | None = None) -> None:
    """Aplica a contagem de estoque de sêmen do print enviado em jul/2026
    (upsert por touro). Roda uma vez (SeedFlag). Dados históricos reais da
    fazenda #1, não vocabulário para fazenda nova."""
    chave = "estoque_semen_202607_v1"
    if session.get(SeedFlag, chave):
        return
    existentes = {i.touro_nome.strip().lower(): i for i in session.exec(select(EstoqueSemen)).all()}
    for nome_curto, nome_completo, codigo, central, tipo, doses, local in SEED_ESTOQUE_SEMEN_202607:
        atual = existentes.get(nome_curto) if nome_curto else None
        if atual:
            atual.touro_nome = nome_completo
            atual.codigo = codigo
            atual.naab = codigo
            atual.central = central
            atual.tipo = tipo
            atual.doses = doses
            atual.local_armazenamento = local
            atual.atualizado_em = datetime.utcnow()
            session.add(atual)
        elif nome_completo.strip().lower() not in existentes:
            session.add(EstoqueSemen(
                touro_nome=nome_completo, codigo=codigo, naab=codigo, central=central,
                tipo=tipo, doses=doses, local_armazenamento=local, fazenda_id=fazenda_id,
            ))
    session.add(SeedFlag(chave=chave))
    session.commit()


def _buscar_semen_da_fazenda(session: Session, item_id: int, fazenda_id: int | None) -> EstoqueSemen | None:
    """Carrega UM item de estoque de sêmen por id JÁ FILTRANDO por fazenda na
    própria consulta (mesmo helper e mesmo motivo de
    agenda.py::_buscar_da_fazenda).

    Antes era `session.get()` seguido de
    `if fazenda_id is not None and item.fazenda_id != fazenda_id` — o padrão
    tolerante que a auditoria aponta como causa raiz: o recorte por fazenda
    dependia de o token trazer "fid", e um token sem ele DESLIGAVA o
    isolamento em vez de restringi-lo. Aqui isso valia edição e EXCLUSÃO do
    inventário de sêmen alheio (doses, valor unitário, canecas — informação
    comercial de genética de concorrente, a mesma que o achado 52 já tratou
    do lado da leitura). Filtrando na consulta, "de outra fazenda" e "sem
    fazenda" (órfão do backfill 029227481e9e) caem no mesmo não encontrado.

    `fazenda_id is None` só acontece onde o multi-fazenda não está
    provisionado (tabela `fazenda` vazia — suíte de testes e instalação
    anterior à f1a2b3c4d5e6); em qualquer ambiente com fazenda cadastrada a
    trava de porta (exigir_fazenda_selecionada, montada no router de cadastro
    em main.py) já recusou a requisição antes. Tratado explicitamente, não
    por omissão."""
    query = select(EstoqueSemen).where(EstoqueSemen.id == item_id)
    if fazenda_id is not None:
        query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
    return session.exec(query).first()


class EstoqueSemenIn(BaseModel):
    touro_nome: str
    codigo: str | None = None
    naab: str | None = None
    central: str | None = None
    tipo: str = "convencional"
    doses: int = 0
    valor_unitario: float | None = None
    local_armazenamento: str | None = None
    observacao: str | None = None
    ativo: bool = True


@router.get("/estoque-semen")
def listar_estoque_semen(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)
    if fazenda_id is not None:
        query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
    itens = session.exec(query).all()
    return [i.model_dump() for i in itens]


@router.get("/estoque-semen/disponivel")
def semen_disponivel(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Para a inseminação: touros por categoria (convencional/sexado/fazenda) e o
    status do estoque mínimo POR CATEGORIA. Convencional/sexado só entram na
    lista se tiverem dose em estoque; touros da fazenda (monta natural) sempre.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(EstoqueSemen).order_by(EstoqueSemen.touro_nome)
    if fazenda_id is not None:
        query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
    itens = [i for i in session.exec(query).all() if i.ativo]
    totais = {"convencional": 0, "sexado": 0}
    for i in itens:
        if i.tipo in totais:
            totais[i.tipo] += i.doses or 0
    touros = []
    for i in itens:
        # Fazenda sempre aparece; sêmen (conv/sexado) só com dose.
        if i.tipo == "fazenda" or (i.doses or 0) > 0:
            touros.append({"nome": i.touro_nome, "tipo": i.tipo, "doses": i.doses or 0})
    minimos = minimos_semen_por_tipo()
    abaixo = {cat: totais[cat] < minimo for cat, minimo in minimos.items()}
    return {"touros": touros, "totais": totais, "minimos": minimos, "abaixo_minimo": abaixo}


@router.post("/estoque-semen")
def criar_estoque_semen(
    dados: EstoqueSemenIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.touro_nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    if dados.tipo not in TIPOS_SEMEN:
        raise HTTPException(status_code=400, detail=f"Tipo inválido (aceitos: {', '.join(TIPOS_SEMEN)})")
    if dados.doses < 0:
        raise HTTPException(status_code=400, detail="Doses não pode ser negativo")
    item = EstoqueSemen(**dados.model_dump(), fazenda_id=fazenda_id)
    session.add(item)
    session.commit()
    session.refresh(item)
    # Espelha em Estoque (categoria "Sêmen e genética") — mesmo que a compra
    # via /compras-semen já faz, senão um touro cadastrado por aqui aparece
    # no Inventário de Sêmen mas fica invisível no módulo Estoque genérico.
    sincronizar_item_estoque_semen(item, session)
    session.commit()
    # 2º commit expira os atributos de `item` de novo — sem este refresh,
    # `model_dump()` devolvia {} (nenhum campo, nem "id") em vez do item.
    session.refresh(item)
    return item.model_dump()


@router.put("/estoque-semen/{item_id}")
def atualizar_estoque_semen(
    item_id: int, dados: EstoqueSemenIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = _buscar_semen_da_fazenda(session, item_id, fazenda_id)
    if not item:
        raise HTTPException(status_code=404, detail="Registro de sêmen não encontrado")
    if dados.tipo not in TIPOS_SEMEN:
        raise HTTPException(status_code=400, detail=f"Tipo inválido (aceitos: {', '.join(TIPOS_SEMEN)})")
    if dados.doses < 0:
        raise HTTPException(status_code=400, detail="Doses não pode ser negativo")
    for campo, valor in dados.model_dump().items():
        setattr(item, campo, valor)
    item.atualizado_em = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    sincronizar_item_estoque_semen(item, session)
    session.commit()
    session.refresh(item)
    return item.model_dump()


@router.delete("/estoque-semen/{item_id}")
def excluir_estoque_semen(
    item_id: int, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    item = _buscar_semen_da_fazenda(session, item_id, fazenda_id)
    if not item:
        raise HTTPException(status_code=404, detail="Registro de sêmen não encontrado")
    session.delete(item)
    session.commit()
    return {"excluido": True}


@router.get("/estoque-semen/prova-media")
def prova_media_semen(
    incluir_fazenda: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Prova média GENÉTICA (índices/PTA do catálogo, não a performance
    realizada no rebanho — para isso ver GET /estoque-semen/prova-ao-vivo)
    dos touros com sêmen em estoque hoje (doses > 0). Por padrão, sêmen
    "fazenda"/monta natural fica de fora (não tem prova de central de
    genética) — `incluir_fazenda=true` inclui mesmo assim (só entra se esse
    touro também estiver cadastrado no catálogo NAAB). Dois recortes:
    - "simples": média simples entre os touros com pelo menos 1 dose em
      estoque — cada touro pesa 1, tenha 1 dose ou 20.
    - "ponderada": média ponderada pela quantidade de doses de cada touro —
      soma(indicador × doses) / soma(doses). Mesma lógica de índice
      ponderado usada por provas genéticas oficiais (ex.: o TPI combina
      produção e tipo numa razão fixa) — aqui quem pondera é a quantidade
      de sêmen, não uma razão fixa entre índices.
    Em ambos, um touro sem determinado indicador não entra no cálculo
    DAQUELE indicador — não zera a média do grupo (ver calcular_prova_media).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    touros = session.exec(select(Touro)).all()
    touro_por_naab = {(t.naab or "").strip().upper(): t for t in touros}
    touro_por_nome = {(t.nome or "").strip().lower(): t for t in touros if t.nome}

    q_estoque = select(EstoqueSemen)
    if fazenda_id is not None:
        q_estoque = q_estoque.where(EstoqueSemen.fazenda_id == fazenda_id)
    estoque = [e for e in session.exec(q_estoque).all() if e.ativo and (incluir_fazenda or e.tipo != "fazenda")]
    pares: list[tuple[Touro, int]] = []
    for e in estoque:
        if (e.doses or 0) <= 0:
            continue
        touro = casar_touro(e, touro_por_naab, touro_por_nome)
        if touro:
            pares.append((touro, e.doses))
    total_doses = sum(p for _, p in pares)

    return {
        "simples": {
            "prova": calcular_prova_media([(t, 1) for t, _ in pares]),
            "touros_considerados": len(pares),
        },
        "ponderada": {
            "prova": calcular_prova_media(pares),
            "total_doses": total_doses,
            "touros_considerados": len(pares),
        },
    }


@router.get("/estoque-semen/prova-ao-vivo")
def prova_ao_vivo_semen(
    categoria: Optional[str] = None, ano_nascimento: Optional[int] = None,
    de: Optional[str] = None, ate: Optional[str] = None, incluir_fazenda: bool = False,
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    "Prova ao vivo" — os MESMOS indicadores genéticos do catálogo usados na
    prova média (GET /estoque-semen/prova-media: leite, gordura, proteína,
    TPI, NM$, tipo/úbere/pernas composto, CCS, fertilidade das filhas,
    facilidade de parto), só que ponderados pelo USO REAL do touro na
    fazenda (nº de serviços em que ele foi de fato usado) em vez das doses
    hoje em estoque — daí "ao vivo". NÃO é taxa de concepção/resultado
    reprodutivo (isso é do cruzamento touro+matriz+manejo, não prova do
    touro; ver fazenda.rules.reproducao_analise para essa métrica, usada em
    Análise reprodutiva). Filtros opcionais, só limitam quais serviços
    contam como uso: categoria (vaca/novilha/todas), ano de nascimento da
    matriz, e período da inseminação (de/ate, sobre a data do serviço). Por
    padrão exclui touros da própria fazenda (`incluir_fazenda=true` inclui).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    touros = session.exec(select(Touro)).all()
    touro_por_naab = {(t.naab or "").strip().upper(): t for t in touros}
    touro_por_nome = {(t.nome or "").strip().lower(): t for t in touros if t.nome}

    q_estoque = select(EstoqueSemen)
    if fazenda_id is not None:
        q_estoque = q_estoque.where(EstoqueSemen.fazenda_id == fazenda_id)
    estoque_por_nome = {(e.touro_nome or "").strip().lower(): e for e in session.exec(q_estoque).all()}

    q_servicos = select(Servico)
    if fazenda_id is not None:
        q_servicos = q_servicos.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(q_servicos).all()]
    registros = analisar_servicos(servicos)
    de_d = parse_date(de) if de else None
    ate_d = parse_date(ate) if ate else None
    resultado = calcular_prova_ao_vivo(
        registros, touro_por_naab, touro_por_nome, estoque_por_nome,
        categoria=categoria, ano_nascimento=ano_nascimento,
        periodo_de=de_d, periodo_ate=ate_d, incluir_fazenda=incluir_fazenda,
    )
    return {**resultado, "categoria": categoria or "todas", "ano_nascimento": ano_nascimento, "de": de, "ate": ate}


# ── Catálogo genético de touros (NAAB/provas) ───────────────────────────────
@router_touros_leitura.get("/touros")
def listar_touros(session: Session = Depends(get_session)) -> list[dict]:
    """Banco de touros importado do catálogo do fornecedor, ordenado por TPI
    (maior primeiro) e depois por nome."""
    touros = session.exec(select(Touro)).all()
    touros.sort(key=lambda t: (-(t.tpi if t.tpi is not None else -1e9), (t.nome or t.naab)))
    return [t.model_dump() for t in touros]

# ── MANUTENÇÃO DO CATÁLOGO: SAIU DAQUI (furo de segurança, set/2026) ────────
# `POST/PUT/DELETE /cadastro/touros`, `POST /cadastro/touros/recarregar-
# catalogo` e `GET /cadastro/touros/campos-planilha` moraram aqui até
# set/2026 e agora vivem em fazenda/api/routers/painel_cowdata_touros.py,
# sob a permissão "editar touros NAAB" do cadastro de equipe do Painel
# CowData.
#
# O QUE ESTAVA ERRADO. `Touro` é catálogo GLOBAL — não tem `fazenda_id`, é
# uma tabela só, lida por todas as fazendas-cliente. As rotas de escrita,
# porém, estavam montadas no router da fazenda e protegidas por
# `exigir_admin`, que é a proteção certa para o dado de UMA fazenda: o
# administrador de qualquer fazenda-cliente podia reescrever ou apagar o
# catálogo que todas as outras usavam. Elas foram REMOVIDAS em vez de
# passarem a recusar — uma rota que só recusa continua montada e volta a
# abrir sozinha se alguém trocar a dependência dela por engano.
#
# A LEITURA NÃO MUDOU: `GET /cadastro/touros` (router_touros_leitura, acima)
# continua igual, e com ela tudo que a fazenda faz com touro — listagem e
# busca, prova média (`/estoque-semen/prova-media`), prova ao vivo/estudo de
# touros (`/estoque-semen/prova-ao-vivo`), seleção na inseminação inclusive
# de touro fora do estoque, sugestão de acasalamento
# (relatorio_acasalamento.py), grau de sangue/genética (rules/genetica.py),
# ficha do animal (animais.py) e compra de sêmen (compra_semen.py).
