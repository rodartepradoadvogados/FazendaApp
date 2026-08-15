"""
Cofre de acesso — trilha de pedido/aprovação/sessão/auditoria toda vez que a
CowData acessa os dados de uma fazenda-cliente para suporte (ver
fazenda/api/routers/cofre_acesso.py). Hoje o único ator possível é o dono
(EMAIL_DONO já enxerga tudo sem essa camada) — este mecanismo formaliza e
registra esse acesso desde já, e vira o controle real assim que a Equipe
CowData (ver painel_cowdata.py) ganhar contas de login próprias.

Não confundir com UsuarioFazenda: aquele é o vínculo de QUEM TRABALHA na
fazenda (funcionário, consultor). Este é o registro de QUANDO A PRÓPRIA
COWDATA entrou nos dados de um cliente e por quê.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from fazenda.models.equipe_cowdata_acesso import NIVEL_SIGILO_PADRAO

# Vocabulário fechado do motivo do pedido — nunca texto livre (mesmo padrão
# de MOTIVOS_BAIXA/MOTIVOS_VENDA: lista cadastrada, não input aberto).
# Lista redefinida a pedido do usuário (ago/2026) — substitui a anterior
# ("Configurar integração"/"Suporte técnico solicitado pelo cliente"/
# "Manutenção preventiva agendada"/"Auditoria de rotina") por esta, mais
# específica ao motivo jurídico/operacional do acesso.
MOTIVOS_ACESSO_SUPORTE = [
    "Configurar parâmetros da fazenda",
    "Auxílio/treinamento de usuário",
    "Migração/importação de dados",
    "Diagnosticar erro relatado",
    "Incidente de segurança",
    "Ordem judicial",
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
    # Assunto do chamado (livre, obrigatório) e observação (livre, opcional)
    # — pedido explícito do usuário para o fluxo de 3 janelas do Painel
    # CowData > Suporte > Acesso CowData. `assunto_chamado` nullable só para
    # não quebrar pedidos já gravados antes desta coluna existir.
    assunto_chamado: Optional[str] = None
    observacao: Optional[str] = None
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
    # Nível de sigilo vigente NESTA sessão (copiado de PermissaoEquipeCowData
    # no momento em que ela abre — ver _abrir_sessao em cofre_acesso.py e
    # NIVEIS_SIGILO_EQUIPE_COWDATA). Gravado aqui, não só no token, para o
    # dono da fazenda conseguir conferir depois com que alcance cada suporte
    # entrou mesmo depois do token expirar (#132).
    nivel_sigilo: str = NIVEL_SIGILO_PADRAO
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
    # Nível de sigilo da sessão que entrou/saiu (ver SessaoAcessoSuporte
    # acima) — duplicado aqui, não só lá, porque esta tabela não tem
    # sessao_id (é o log grosso de entrada/saída, sem FK pra sessão) e é a
    # primeira coisa que o dono da fazenda vê em Configurações > Auditoria
    # CowData e no Painel CowData > Suporte > Auditoria (#132). Nullable só
    # para não quebrar linhas já gravadas antes desta coluna existir — nunca
    # escrito como None por código novo.
    nivel_sigilo: Optional[str] = None
    quando: datetime = Field(default_factory=datetime.utcnow)


class AcaoAuditoriaSuporte(SQLModel, table=True):
    """Log append-only de CADA escrita (POST/PUT/PATCH/DELETE) tentada
    durante uma sessão de suporte — granularidade abaixo de
    AuditoriaAcessoSuporte (que só marca entrada/saída da sessão como um
    todo). Escrito pelo próprio middleware que decide bloquear ou deixar
    passar (ver main.py::_bloquear_modo_suporte), então cobre tanto ações
    permitidas quanto tentativas bloqueadas — pedido explícito do usuário:
    "tudo o que ocorrer nesse acesso de suporte deve ficar disponível para
    ser auditado". Alimenta a sub-aba Painel CowData > Suporte > Auditoria
    de Acessos CowData e a aba da fazenda Configurações > Auditoria CowData
    (só para contratante-administrador).

    #132: passou a registrar também GET bloqueado por nível de sigilo (não
    todo GET — só o que o nível da sessão não alcança, senão isto viraria um
    log de toda leitura feita, gigantesco e inútil). `metodo` continua sendo
    quase sempre POST/PUT/PATCH/DELETE; um "GET" aqui significa sempre
    `bloqueado=True`. O nível de sigilo em si não é gravado por linha — ver
    SessaoAcessoSuporte.nivel_sigilo (join por sessao_id)."""

    __tablename__ = "acao_auditoria_suporte"

    id: Optional[int] = Field(default=None, primary_key=True)
    sessao_id: int = Field(foreign_key="sessao_acesso_suporte.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    metodo: str  # POST | PUT | PATCH | DELETE | GET (GET só aparece bloqueado)
    caminho: str  # request.url.path
    status_code: Optional[int] = None
    bloqueado: bool = False
    quando: datetime = Field(default_factory=datetime.utcnow)
