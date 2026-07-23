"""
Fase 2C — produto independente do consultor: assinatura própria (fora do
contrato de qualquer fazenda), fazendas "gerenciadas" que ele acompanha por
importação de planilha (o produtor NÃO precisa ser cliente do sistema), e o
modo Simulação (projeto fictício, session-only — ver
fazenda/api/routers/consultores.py, POST /consultor/simulacao/calcular não
grava nada no banco).

Não confundir com UsuarioFazenda.consultor (Fase 2B, fazenda/models/
multitenant.py): aquele é o vínculo de um consultor DENTRO de uma fazenda
Diamond que já é cliente do sistema — mesmo acesso de um funcionário comum,
vendo os dados reais dela. Este aqui é o produto para o consultor atender
produtores que NÃO usam o sistema: os dados de "fazenda gerenciada" e das
planilhas importadas pertencem só ao consultor (`consultor_usuario_id`),
nunca a um tenant Fazenda real — nunca se misturam com nenhuma fazenda_id.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# Catálogo fechado — plano do CONSULTOR (assinatura própria), não da fazenda
# (ver fazenda/models/planos.py::PLANOS_CATALOGO, que é por fazenda-tenant).
PLANOS_CONSULTOR_CATALOGO: dict[str, dict] = {
    "consultor_basico": {"nome": "Até 3 fazendas", "preco": 300.00, "limite_fazendas": 3},
    "consultor_intermediario": {"nome": "Até 8 fazendas", "preco": 500.00, "limite_fazendas": 8},
    "consultor_avancado": {"nome": "Até 15 fazendas", "preco": 650.00, "limite_fazendas": 15},
}

STATUS_CONTRATO_CONSULTOR = ["aguardando_aprovacao", "ativo", "suspenso"]

# Vocabulário de categoria de dado importado — mesma nomenclatura dos módulos
# comerciais (ver planos.py::MODULOS_COMERCIAIS), exceto "consultor" (não se
# aplica aqui) e "planejamento"/"pedidos" (não fazem sentido fora do sistema).
CATEGORIAS_IMPORTACAO = [
    "rebanho", "reprodutivo", "produtivo", "sanitario", "financeiro", "estoque", "alimentacao", "agricultura",
]


class ContratoConsultor(SQLModel, table=True):
    """Um contrato por usuário-consultor (não por fazenda) — mesmo ciclo de
    vida do ContratoFazenda: nasce aguardando_aprovacao ao solicitar um
    plano, só libera (fazendas gerenciadas, importação) depois que você
    (dono) aprovar."""

    __tablename__ = "contrato_consultor"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True, unique=True)
    plano: str  # chave de PLANOS_CONSULTOR_CATALOGO
    limite_fazendas: int
    status: str = "aguardando_aprovacao"
    aprovado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    data_fechamento: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class FazendaGerenciada(SQLModel, table=True):
    """Fazenda cliente do CONSULTOR — não é uma Fazenda tenant do sistema,
    só um cadastro simples para organizar as planilhas importadas dela.
    Excluir esta linha (DELETE) apaga em cascata seus RegistroImportado."""

    __tablename__ = "fazenda_gerenciada"

    id: Optional[int] = Field(default=None, primary_key=True)
    consultor_usuario_id: int = Field(foreign_key="usuario.id", index=True)
    nome: str
    produtor: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    observacoes: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class RegistroImportado(SQLModel, table=True):
    """Uma linha de planilha importada — genérico de propósito (o consultor
    atende produtores com planilhas/sistemas variados; não vale a pena
    modelar cada indicador possível de cada categoria). `dados_json` guarda
    o dict coluna→valor da linha original (serializado com json.dumps);
    `categoria` classifica o tipo de dado para filtro na tela."""

    __tablename__ = "registro_importado"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_gerenciada_id: int = Field(foreign_key="fazenda_gerenciada.id", index=True)
    categoria: str = Field(index=True)
    data_referencia: Optional[date] = None
    dados_json: str = "{}"
    arquivo_origem: str
    criado_em: datetime = Field(default_factory=datetime.utcnow)
