"""
Planos comerciais e trava de acesso por módulo contratado — camada ACIMA da
permissão por usuário que já existe (`Usuario.permissoes`/`exigir_modulo` em
fazenda/auth.py). Ali se controla o que um FUNCIONÁRIO de uma fazenda pode
ver; aqui se controla o que a FAZENDA (tenant) contratou e você (dono da
plataforma) aprovou — as duas travas precisam passar.

Módulos comerciais (distintos das chaves técnicas de permissão, embora
mapeiem para elas — ver fazenda/auth.py::MODULO_COMERCIAL_PARA_TECNICO):
rebanho, reprodutivo, produtivo, sanitario, financeiro, planejamento,
pedidos, estoque, alimentacao, agricultura, consultor (Diamond — habilita
convidar um consultor à fazenda; a mecânica de convite em si é uma fase
futura, aqui só existe como item do plano).

Todo contrato precisa de AO MENOS UM módulo base (rebanho ou financeiro) e os
módulos respeitam DEPENDENCIAS_MODULOS (ex.: estoque exige rebanho + financeiro,
pedidos exige financeiro) — ver validar_contrato_modulos. Rebanho NÃO é mais
obrigatório: o plano "financeiro" (financeiro + pedidos) não tem rebanho.
Contratos já existentes não são revalidados na leitura (grandfather).

Preço: o preço do plano de catálogo vive na tabela `preco_plano` (editável no
Painel CowData; a constante abaixo é o padrão/fallback) e é CONGELADO no
contrato (`ContratoFazenda.preco_mensal_fechado`) na aprovação — única fonte
de leitura é `preco_mensal_do_contrato`.

Fazenda nova nasce com ContratoFazenda.status="aguardando_aprovacao" e SEM
nenhuma linha em ContratoFazendaModulo — nada funciona (nem Rebanho) até você
aprovar/fechar o contrato (ver fazenda/api/routers/fazendas.py). A fazenda #1
(piloto real) é a exceção: migração de backfill já cria o contrato "ativo"
com os 8 módulos, para nunca travar quem já usa o sistema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, Session, SQLModel, UniqueConstraint, select

MODULO_REBANHO = "rebanho"

# Módulos comerciais vendáveis — vocabulário fechado (validado no router).
# "formulacao_dietas" fica de propósito FORA de todo plano do catálogo
# abaixo (nem Diamond) — é módulo avulso, contratado "sob medida" por
# fazenda (ContratoFazendaModulo direto), não incluso automaticamente em
# nenhum pacote existente. Ver fazenda/api/routers/formulacao_dietas.py.
MODULOS_COMERCIAIS = [
    MODULO_REBANHO, "reprodutivo", "produtivo", "sanitario", "financeiro",
    "planejamento", "pedidos", "estoque", "alimentacao", "agricultura", "consultor",
    "formulacao_dietas",
]

# Catálogo fechado de planos — nome de exibição, preço padrão e módulos
# inclusos. "custom" não é um plano de catálogo: contrato "sob medida" grava
# ContratoFazenda.plano = None e monta os módulos um a um.
PLANOS_CATALOGO: dict[str, dict] = {
    "standard": {
        "nome": "Standard",
        "preco": 250.00,
        "modulos": [MODULO_REBANHO, "reprodutivo"],
    },
    "silver": {
        "nome": "Silver",
        "preco": 350.00,
        "modulos": [MODULO_REBANHO, "reprodutivo", "produtivo", "sanitario", "financeiro"],
    },
    "gold": {
        "nome": "Gold",
        "preco": 420.00,
        "modulos": [
            MODULO_REBANHO, "reprodutivo", "produtivo", "sanitario", "financeiro",
            "planejamento", "pedidos", "estoque", "alimentacao", "agricultura",
        ],
    },
    "diamond": {
        "nome": "Diamond",
        "preco": 500.00,
        "modulos": [
            MODULO_REBANHO, "reprodutivo", "produtivo", "sanitario", "financeiro",
            "planejamento", "pedidos", "estoque", "alimentacao", "agricultura", "consultor",
        ],
    },
    # Fazenda cliente só-financeiro (sem rebanho): Controle Financeiro +
    # Cotações + Pedidos. Preço inicial R$ 200,00 — editável no Painel CowData
    # (tabela preco_plano), não é hard-coded além deste padrão.
    "financeiro": {
        "nome": "Financeiro",
        "preco": 200.00,
        "modulos": ["financeiro", "pedidos"],
    },
}

# Módulos "base": todo contrato precisa de pelo menos um deles.
MODULOS_BASE = [MODULO_REBANHO, "financeiro"]

# Dependências entre módulos comerciais: o módulo da chave só pode ser
# contratado junto com TODOS os da lista. (agricultura e consultor: sem
# dependência por enquanto.) Contrato existente não é revalidado na leitura.
DEPENDENCIAS_MODULOS: dict[str, list[str]] = {
    "estoque": [MODULO_REBANHO, "financeiro"],
    "pedidos": ["financeiro"],
    "planejamento": ["financeiro"],
    "reprodutivo": [MODULO_REBANHO],
    "produtivo": [MODULO_REBANHO],
    "sanitario": [MODULO_REBANHO],
    "alimentacao": [MODULO_REBANHO],
}

NOME_MODULO_EXIBICAO: dict[str, str] = {
    "rebanho": "Rebanho", "reprodutivo": "Reprodutivo", "produtivo": "Produtivo", "sanitario": "Sanitário",
    "financeiro": "Financeiro", "planejamento": "Planejamento", "pedidos": "Pedidos", "estoque": "Estoque",
    "alimentacao": "Alimentação", "agricultura": "Agricultura", "consultor": "Consultor",
    "formulacao_dietas": "Formulação de dietas",
}


def _nomes_pt(chaves: list[str]) -> str:
    nomes = [NOME_MODULO_EXIBICAO.get(c, c) for c in chaves]
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def validar_dependencias(modulos: list[str]) -> list[str]:
    """Mensagens (PT-BR) de dependência faltando para o conjunto de módulos —
    lista vazia = tudo certo. Ex.: ["estoque"] -> ["Estoque exige Rebanho e Financeiro"]."""
    escolhidos = set(modulos)
    erros: list[str] = []
    for modulo in modulos:
        exigidos = DEPENDENCIAS_MODULOS.get(modulo)
        if exigidos and not all(d in escolhidos for d in exigidos):
            erros.append(f"{NOME_MODULO_EXIBICAO.get(modulo, modulo)} exige {_nomes_pt(exigidos)}")
    return erros


def validar_contrato_modulos(modulos: list[str]) -> list[str]:
    """Regra de contrato novo/editado: ao menos um módulo base + dependências."""
    if not any(m in MODULOS_BASE for m in modulos):
        return [f"O contrato precisa de ao menos um módulo base ({' ou '.join(NOME_MODULO_EXIBICAO[m] for m in MODULOS_BASE)})"]
    return validar_dependencias(modulos)

# Desconto por periodicidade de pagamento adiantado (ver ContratoFazenda.ciclo_pagamento)
# — aplicado sobre preco_mensal do plano/módulos. Trimestral e semestral
# saíram do catálogo (revisão ago/2026, pedido explícito do usuário) —
# assinatura é só mensal agora, sem desconto por adiantamento. Os dicts
# continuam existindo (não viraram uma constante única) porque
# _publico_contrato usa .get(ciclo, default) — um contrato antigo já gravado
# com "trimestral"/"semestral" no banco continua sendo lido sem erro, só cai
# no desconto 0%/1 mês até ser resalvo (nesse ponto passa a "mensal").
DESCONTO_CICLO_PAGAMENTO: dict[str, float] = {
    "mensal": 0.0,
}
MESES_POR_CICLO: dict[str, int] = {"mensal": 1}

STATUS_CONTRATO = ["aguardando_aprovacao", "ativo", "suspenso"]


class PrecoModulo(SQLModel, table=True):
    """Catálogo de preço-padrão por módulo — só você edita (tela de admin).
    Um contrato "sob medida" parte destes valores; um contrato de plano
    fechado (Standard/Silver/Gold/Diamond) usa o preço do PLANOS_CATALOGO,
    não este catálogo por módulo (o plano já embute o preço do pacote)."""

    __tablename__ = "preco_modulo"

    id: Optional[int] = Field(default=None, primary_key=True)
    modulo: str = Field(unique=True, index=True)
    preco: float = 0.0
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class PrecoPlano(SQLModel, table=True):
    """Preço de catálogo de cada plano fechado (PLANOS_CATALOGO) — editável
    pelo dono no Painel CowData. Tabela GLOBAL (sem fazenda_id), semeada pela
    migração com os preços padrão. Mudar aqui NÃO muda contratos já fechados
    (eles carregam `ContratoFazenda.preco_mensal_fechado`). Não confundir com
    PrecoModulo (preço por módulo, só para contrato "sob medida")."""

    __tablename__ = "preco_plano"

    plano: str = Field(primary_key=True)
    preco: float = 0.0
    # None = ainda no padrão semeado (ninguém editou).
    atualizado_em: Optional[datetime] = None
    atualizado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class ContratoFazenda(SQLModel, table=True):
    """Um contrato por fazenda (não versionado — editar módulos/plano atualiza
    esta mesma linha). `plano` é a chave de PLANOS_CATALOGO quando é um dos
    pacotes fechados, ou None quando é "sob medida" (módulos avulsos em
    ContratoFazendaModulo, sem seguir nenhum pacote). `preco_mensal_fechado`
    é o preço do pacote CONGELADO (na aprovação / quando o plano muda em
    contrato ativo); None = ainda lê o catálogo ao vivo (rascunho)."""

    __tablename__ = "contrato_fazenda"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True, unique=True)
    plano: Optional[str] = None
    status: str = "aguardando_aprovacao"
    # "mensal" (padrão, sem desconto), "trimestral" (-5%) ou "semestral" (-20%,
    # via Pix Automático/QR dinâmico) — ver DESCONTO_CICLO_PAGAMENTO. Só o
    # valor à vista do pagamento adiantado muda; os módulos/preço-base do
    # plano são os mesmos.
    ciclo_pagamento: str = "mensal"
    preco_mensal_fechado: Optional[float] = None
    aprovado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    data_fechamento: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class ContratoFazendaModulo(SQLModel, table=True):
    """Um módulo contratado por uma fazenda, com o preço CONGELADO no momento
    da aprovação — editar o catálogo (PrecoModulo) ou o preço do pacote
    depois não muda contratos já fechados (segurança jurídica: o que foi
    assinado não muda sozinho)."""

    __tablename__ = "contrato_fazenda_modulo"
    __table_args__ = (UniqueConstraint("fazenda_id", "modulo", name="uq_contrato_fazenda_modulo"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    modulo: str = Field(index=True)
    preco: float = 0.0
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class ContratoAnexo(SQLModel, table=True):
    """Contrato assinado (PDF/imagem) anexado a uma fazenda — para consulta e
    segurança jurídica. Conteúdo em bytes no próprio banco (mesmo padrão de
    LancamentoAnexo, ver fazenda/models/financeiro.py) — sobrevive a
    redeploy, ao contrário de disco efêmero. Mais de um anexo por fazenda
    (contrato original, aditivos, distrato)."""

    __tablename__ = "contrato_anexo"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    nome_arquivo: str
    mime_type: str
    tamanho_bytes: int
    conteudo: bytes
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)


STATUS_ASSINATURA_ZAPSIGN = ["pending", "signed", "refused"]


class ContratoAssinaturaZapSign(SQLModel, table=True):
    """Uma tentativa de assinatura eletrônica do contrato-modelo via ZapSign
    (ver fazenda/rules/zapsign.py e fazenda/templates/contrato_cowdata.md) —
    histórico completo (mais de uma linha por fazenda: reenvio, correção).
    `status` começa "pending" e é atualizado pelo webhook
    (fazenda/api/routers/zapsign.py::zapsign_webhook) quando o signatário
    assina — nunca por polling do frontend."""

    __tablename__ = "contrato_assinatura_zapsign"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    document_token: str = Field(index=True, unique=True)
    signer_token: Optional[str] = None
    sign_url: Optional[str] = None
    status: str = "pending"
    solicitado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    assinado_em: Optional[datetime] = None


def preco_catalogo_plano(session: Session, plano: str) -> float:
    """Preço de catálogo HOJE do plano: linha em `preco_plano` se houver,
    senão o padrão em PLANOS_CATALOGO."""
    linha = session.get(PrecoPlano, plano)
    if linha is not None:
        return linha.preco
    return PLANOS_CATALOGO[plano]["preco"]


def preco_mensal_do_contrato(
    session: Session, contrato: ContratoFazenda, modulos: Optional[list[ContratoFazendaModulo]] = None,
) -> float:
    """ÚNICO lugar que calcula o valor mensal de um contrato (MRR, boleto,
    Asaas, GET contrato). Plano de catálogo: `preco_mensal_fechado` se já
    congelado, senão o preço de catálogo de hoje. Sob medida: soma dos módulos
    ativos. `modulos=None` carrega do banco (só os ativos)."""
    if contrato.plano and contrato.plano in PLANOS_CATALOGO:
        if contrato.preco_mensal_fechado is not None:
            return contrato.preco_mensal_fechado
        return preco_catalogo_plano(session, contrato.plano)
    if modulos is None:
        modulos = session.exec(
            select(ContratoFazendaModulo).where(
                ContratoFazendaModulo.fazenda_id == contrato.fazenda_id,
                ContratoFazendaModulo.ativo == True,  # noqa: E712
            )
        ).all()
    return sum(m.preco for m in modulos if m.ativo)
