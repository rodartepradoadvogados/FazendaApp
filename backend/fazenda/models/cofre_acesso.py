"""
Cofre de acesso — trilha de pedido/aprovação/sessão/auditoria toda vez que a
CowData acessa os dados de uma fazenda-cliente para suporte (ver
fazenda/api/routers/cofre_acesso.py). Hoje o único ator possível é o dono
(EMAIL_DONO já enxerga tudo sem essa camada) — este mecanismo formaliza e
registra esse acesso desde já, e vira o controle real assim que a Equipe
CowData (ver painel_cowdata.py) ganhar contas de login próprias.

Não confundir com UsuarioFazenda/ContratoConsultor: aqueles são vínculos de
QUEM TRABALHA na fazenda (funcionário, consultor). Este é o registro de
QUANDO A PRÓPRIA COWDATA entrou nos dados de um cliente e por quê.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# Vocabulário fechado do motivo do pedido — nunca texto livre (mesmo padrão
# de MOTIVOS_BAIXA/MOTIVOS_VENDA: lista cadastrada, não input aberto).
MOTIVOS_ACESSO_SUPORTE = [
    "Configurar integração",
    "Diagnosticar erro relatado",
    "Suporte técnico solicitado pelo cliente",
    "Manutenção preventiva agendada",
    "Auditoria de rotina",
]

STATUS_PEDIDO_ACESSO = ["aguardando_aprovacao", "aprovado", "negado"]

# Duração de uma sessão de suporte a partir da aprovação — curta de propósito
# (ver Fazenda.exige_aprovacao_suporte); pode ser encerrada manualmente antes.
DURACAO_SESSAO_MINUTOS = 30


class PedidoAcessoSuporte(SQLModel, table=True):
    """Um pedido de acesso de suporte a uma fazenda. Nasce
    aguardando_aprovacao se a fazenda exigir aprovação prévia
    (Fazenda.exige_aprovacao_suporte), senão já nasce aprovado e abre a
    sessão na hora."""

    __tablename__ = "pedido_acesso_suporte"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    motivo: str
    status: str = "aguardando_aprovacao"
    aprovado_por_usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")
    pedido_em: datetime = Field(default_factory=datetime.utcnow)
    decidido_em: Optional[datetime] = None


class SessaoAcessoSuporte(SQLModel, table=True):
    """Uma sessão de acesso aberta a partir de um pedido aprovado. `ativa` é
    calculada na leitura (encerrada_em is None e expira_em no futuro), não
    guardada — evita ficar desatualizada sem um job de expiração."""

    __tablename__ = "sessao_acesso_suporte"

    id: Optional[int] = Field(default=None, primary_key=True)
    pedido_id: int = Field(foreign_key="pedido_acesso_suporte.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    motivo: str
    iniciada_em: datetime = Field(default_factory=datetime.utcnow)
    expira_em: datetime
    encerrada_em: Optional[datetime] = None


class AuditoriaAcessoSuporte(SQLModel, table=True):
    """Log append-only de entrada/saída — nunca editado nem apagado por
    nenhuma rota; é o que a tela "Auditoria recente" do Cofre de acesso lê."""

    __tablename__ = "auditoria_acesso_suporte"

    id: Optional[int] = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    acao: str  # "entrada" | "saida"
    quando: datetime = Field(default_factory=datetime.utcnow)
