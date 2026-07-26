"""
Planos comerciais e trava de acesso por módulo contratado — camada ACIMA da
permissão por usuário que já existe (`Usuario.permissoes`/`exigir_modulo` em
fazenda/auth.py). Ali se controla o que um FUNCIONÁRIO de uma fazenda pode
ver; aqui se controla o que a FAZENDA (tenant) contratou e você (dono da
plataforma) aprovou — as duas travas precisam passar.

Módulos comerciais (distintos das chaves técnicas de permissão, embora
mapeiem para elas — ver fazenda/auth.py::MODULO_COMERCIAL_PARA_TECNICO):
rebanho (sempre incluso em todo plano), reprodutivo, produtivo, sanitario,
financeiro, planejamento, pedidos, estoque, alimentacao, agricultura,
consultor (Diamond — habilita convidar um consultor à fazenda; a mecânica de
convite em si é uma fase futura, aqui só existe como item do plano).

Fazenda nova nasce com ContratoFazenda.status="aguardando_aprovacao" e SEM
nenhuma linha em ContratoFazendaModulo — nada funciona (nem Rebanho) até você
aprovar/fechar o contrato (ver fazenda/api/routers/fazendas.py). A fazenda #1
(piloto real) é a exceção: migração de backfill já cria o contrato "ativo"
com os 8 módulos, para nunca travar quem já usa o sistema.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint

MODULO_REBANHO = "rebanho"

# Módulos comerciais vendáveis — vocabulário fechado (validado no router).
MODULOS_COMERCIAIS = [
    MODULO_REBANHO, "reprodutivo", "produtivo", "sanitario", "financeiro",
    "planejamento", "pedidos", "estoque", "alimentacao", "agricultura", "consultor",
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
}

# Desconto por periodicidade de pagamento adiantado (ver ContratoFazenda.ciclo_pagamento)
# — aplicado sobre preco_mensal do plano/módulos. Mesmos percentuais usados no
# contrato-modelo (fazenda/templates/contrato_cowdata.html) e no Painel CowData.
# Sem tier "anual" de propósito (revisão jul/2026: assinatura é mensal por
# padrão via Pix Automático; semestral virou o teto de desconto — 20%, mesmo
# valor que o "anual" tinha antes — manter os dois lado a lado não faria
# sentido, então o anual saiu).
DESCONTO_CICLO_PAGAMENTO: dict[str, float] = {
    "mensal": 0.0,
    "trimestral": 0.05,
    "semestral": 0.20,
}
MESES_POR_CICLO: dict[str, int] = {"mensal": 1, "trimestral": 3, "semestral": 6}

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


class ContratoFazenda(SQLModel, table=True):
    """Um contrato por fazenda (não versionado — editar módulos/plano atualiza
    esta mesma linha). `plano` é a chave de PLANOS_CATALOGO quando é um dos 4
    pacotes fechados, ou None quando é "sob medida" (módulos avulsos em
    ContratoFazendaModulo, sem seguir nenhum pacote)."""

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
