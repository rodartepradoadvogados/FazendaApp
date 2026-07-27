"""
Sistema — usuários/login, parâmetros, agenda, Telegram, News, notificações push e portal de comunicação.

Submódulo de fazenda.models — parte da camada de dados SQLModel (tabelas
SQLite/PostgreSQL + validação Pydantic). Ver fazenda/models/__init__.py para
o re-export consolidado usado pelo resto do código.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel
from sqlalchemy import BigInteger

class SeedFlag(SQLModel, table=True):
    """Marcador de migração/seed de dados executado uma única vez.

    Usado por normalizações que devem rodar só na primeira inicialização
    (ex.: ativar todas as contas gerenciais) e nunca sobrescrever ajustes
    manuais feitos depois pelo usuário.
    """

    __tablename__ = "seed_flag"

    chave: str = Field(primary_key=True)
    aplicado_em: datetime = Field(default_factory=datetime.utcnow)


class ParametroFazenda(SQLModel, table=True):
    """Parâmetro editável de manejo/metas/financeiro — substitui o antigo dict
    fixo em `rules/parametros.py` por um valor persistido e de fato editável
    pela UI de Configurações > Parâmetros. `valor` fica como texto para caber
    qualquer `tipo` (int/float/bool/date) num único campo; `get_param()` (ver
    `rules/parametros.py`) faz a conversão na leitura."""

    __tablename__ = "parametro_fazenda"

    id: Optional[int] = Field(default=None, primary_key=True)
    chave: str = Field(index=True, unique=True)
    grupo: str
    label: str
    valor: str
    tipo: str = "int"  # "int" | "float" | "bool" | "date"
    unidade: Optional[str] = None
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class TelegramPendente(SQLModel, table=True):
    """Documento recebido pelo robô do Telegram, aguardando o usuário responder
    se é receita ou despesa antes de virar um lançamento financeiro. Depois de
    lido (`tipo`/`dados_lidos` preenchidos), continua vivo até o usuário
    confirmar/corrigir/cancelar — só aí vira (ou não) um LancamentoPendente."""

    __tablename__ = "telegram_pendente"

    id: Optional[int] = Field(default=None, primary_key=True)
    # BigInteger: ids de chat do Telegram passam de 2,1 bi (não cabem em INTEGER).
    chat_id: int = Field(sa_type=BigInteger, index=True)  # de quem recebeu (para responder)
    file_id: str                         # id do arquivo no Telegram (para baixar)
    file_name: Optional[str] = None
    mime: Optional[str] = None
    kind: str                            # "xml" | "documento"
    tipo: Optional[str] = None           # "receita" | "despesa" — preenchido após a escolha
    dados_lidos: Optional[str] = None    # JSON já extraído do documento, aguardando confirmação
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class TelegramSessao(SQLModel, table=True):
    """Estado da conversa de um chat no robô: qual lançamento está sendo
    preenchido, em que etapa e os dados já coletados (JSON)."""

    __tablename__ = "telegram_sessao"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(sa_type=BigInteger, index=True, unique=True)
    fluxo: Optional[str] = None          # tipo de lançamento em andamento
    etapa: int = 0                       # índice da pergunta atual
    dados: str = "{}"                    # JSON acumulado dos campos respondidos
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class LancamentoPendente(SQLModel, table=True):
    """Lançamento operacional (pesagem, parto, secagem, troca de lote…) enviado
    pelo Telegram e aguardando aprovação da conta principal antes de virar um
    registro real no sistema."""

    __tablename__ = "lancamento_pendente"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str = Field(index=True)        # controle_leiteiro | parto | secagem | ...
    payload: str = "{}"                  # JSON dos campos coletados
    resumo: str = ""                     # texto legível para a tela de aprovação
    solicitante_chat_id: Optional[int] = Field(default=None, sa_type=BigInteger)
    solicitante_nome: Optional[str] = None
    status: str = Field(default="pendente", index=True)  # pendente | aprovado | rejeitado
    erro: Optional[str] = None           # mensagem se a materialização falhar
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    decidido_em: Optional[datetime] = None
    decidido_por: Optional[str] = None   # username de quem aprovou/rejeitou


# ---------------------------------------------------------------------------
# Agenda Manual
# ---------------------------------------------------------------------------
class AgendaManual(SQLModel, table=True):
    """Eventos adicionados manualmente — equivalente à aba AGENDA_MANUAL do Excel."""

    __tablename__ = "agenda_manual"

    id: Optional[int] = Field(default=None, primary_key=True)
    data_evento: date
    descricao: str
    categoria: str = "Gestão/Financeiro"
    numero_animal: Optional[str] = None  # CSV de números, quando vinculado a um ou mais animais
    lotes: Optional[str] = None  # CSV de códigos de lote, quando vinculado a um ou mais lotes
    tipo_evento: Optional[str] = None  # Compra, Venda, Serviço, Outro
    observacao: Optional[str] = None
    recorrente: bool = False  # linha-modelo que gera as próximas ocorrências automaticamente
    intervalo_dias: Optional[int] = None
    intervalo_meses: Optional[int] = None
    origem_recorrencia_id: Optional[int] = None  # id da linha-modelo que gerou esta ocorrência
    apenas_admin: bool = False  # evento visível somente para o administrador
    link: Optional[str] = None  # rota interna de instruções/ação (ex.: "/configuracoes?aba=importar")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


# ---------------------------------------------------------------------------
# Evento realizado (workflow da agenda)
# ---------------------------------------------------------------------------
class EventoRealizado(SQLModel, table=True):
    """Marca um evento da agenda (identificado por hash estável) como concluído."""

    __tablename__ = "evento_realizado"

    id: Optional[int] = Field(default=None, primary_key=True)
    evento_id: str = Field(index=True, unique=True)
    marcado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Solicitação de exclusão (fluxo de aprovação p/ não-administradores)
# ---------------------------------------------------------------------------
class SolicitacaoExclusao(SQLModel, table=True):
    """
    Pedido de exclusão feito por um operador (não-admin) — fica pendente até
    um administrador aprovar (executa a exclusão de fato) ou rejeitar.
    """

    __tablename__ = "solicitacao_exclusao"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str
    id_alvo: str
    titulo: Optional[str] = None  # descrição do alvo no momento do pedido (snapshot p/ exibição)
    status: str = "pendente"       # pendente | aprovada | rejeitada
    solicitado_por: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    decidido_por: Optional[str] = None
    decidido_em: Optional[datetime] = None
    motivo_rejeicao: Optional[str] = None


# ---------------------------------------------------------------------------
# Usuário (login / controle de acesso)
# ---------------------------------------------------------------------------
class Usuario(SQLModel, table=True):
    """Usuário do sistema. Senha guardada apenas como hash (pbkdf2)."""

    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    nome: Optional[str] = None
    senha_hash: str
    papel: str = "admin"          # admin (tudo + gerencia usuários) | operador
    # Módulos liberados p/ operador, separados por vírgula. Admin ignora (tem tudo).
    permissoes: Optional[str] = None
    ativo: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    # Preferência pessoal de paleta de cores — "vinho" (padrão) ou "verde".
    paleta: Optional[str] = None
    # E-mail pessoal (opcional) — usado hoje só para identificar o dono da
    # fazenda e liberar o relatório de acessos (ver fazenda.auth.exigir_dono).
    email: Optional[str] = None
    ultimo_login: Optional[datetime] = None
    # Permissão específica para publicar matérias no blog (News) — independente
    # de papel/admin (ver fazenda.auth.exigir_pode_publicar). Todo usuário
    # nasce sem essa permissão; o proprietário recebe uma única vez via seed
    # (ver fazenda.auth.seed_permissao_publicar_dono).
    pode_publicar_materias_blog: bool = False
    # Vínculo com o cadastro de Pessoas — todo usuário novo exige uma pessoa já
    # cadastrada (ver criar_usuario em fazenda.api.routers.auth); contas
    # antigas podem não ter esse vínculo até serem editadas retroativamente.
    pessoa_id: Optional[int] = Field(default=None, foreign_key="pessoa.id")
    # Fluxo "Esqueci minha senha" — token de uso único enviado por e-mail
    # (ver fazenda.api.routers.auth). None fora de um pedido de redefinição
    # em andamento; limpo assim que a senha é redefinida ou o token expira.
    reset_senha_token: Optional[str] = Field(default=None, index=True)
    reset_senha_expira: Optional[datetime] = None
    # Próximo passo do Cofre de acesso (ver fazenda/models/cofre_acesso.py):
    # nível de sigilo máximo que esta conta poderia alcançar em fazendas de
    # terceiros. Aditivo e ainda dormente — nenhuma rota lê este campo hoje;
    # existe só para já ter o dado quando esse controle mais fino entrar em
    # vigor (ninguém, nem o dono, ganha mais visibilidade por causa dele).
    nivel_sigilo_maximo: Optional[str] = None


class LoginAcesso(SQLModel, table=True):
    """Um login bem-sucedido — histórico completo (Usuario.ultimo_login guarda
    só o mais recente). Alimenta o relatório de últimos acessos, restrito ao
    proprietário (ver fazenda.auth.exigir_dono)."""

    __tablename__ = "login_acesso"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class BackupAutomatico(SQLModel, table=True):
    """Registro de cada rodada do backup automático semanal (ver
    fazenda.rules.backup) — guarda quando rodou e se deu certo, para decidir
    se já é hora da próxima rodada e para o erro não se perder caso o envio
    do e-mail falhe (ex.: RESEND_API_KEY não configurada)."""

    __tablename__ = "backup_automatico"

    id: Optional[int] = Field(default=None, primary_key=True)
    executado_em: datetime = Field(default_factory=datetime.utcnow)
    sucesso: bool = True
    erro: Optional[str] = None


# ---------------------------------------------------------------------------
# News — blog de importação de notícias de pecuária leiteira (botão "News").
# ---------------------------------------------------------------------------
class FonteNews(SQLModel, table=True):
    """Um site cadastrado para o agregador de notícias (Configurações > News,
    só administrador). Guarda o último erro de busca — quando um site muda de
    layout ou sai do ar, aparece aqui para o admin substituir/corrigir a URL,
    em vez de quebrar a página de notícias para todo mundo."""

    __tablename__ = "fonte_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    url: str  # home do site ou feed RSS/Atom direto
    ativo: bool = True
    ultimo_erro: Optional[str] = None
    ultima_busca_em: Optional[datetime] = None
    ultima_busca_ok_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    # Fonte alimentada via POST /news/manual (ex.: robô agendado) em vez de
    # RSS — nunca busca sozinha, então nunca aparece com erro de fetch.
    manual: bool = False


class NoticiaNews(SQLModel, table=True):
    """Uma matéria já importada de uma fonte (manchete + resumo + link) — cache
    local para não depender de buscar no site a cada carregamento da página."""

    __tablename__ = "noticia_news"

    id: Optional[int] = Field(default=None, primary_key=True)
    fonte_id: int = Field(foreign_key="fonte_news.id", index=True)
    manchete: str
    resumo: Optional[str] = None
    link: str = Field(unique=True)
    data_publicacao: Optional[datetime] = None  # data/hora informada pelo site (quando disponível)
    capturado_em: datetime = Field(default_factory=datetime.utcnow, index=True)
    # Matéria escrita por nós (admin ou robô) via Configurações > News > Adicionar
    # matéria ao blog — corpo completo do texto, distinto do `resumo` (que é o
    # recorte curto vindo de fontes RSS externas). Nula para matérias antigas
    # importadas de RSS.
    materia: Optional[str] = None
    # Fontes/URLs de referência informadas ao publicar a matéria (JSON: lista de
    # strings) — 0 a N links, diferente do `link` único usado no fluxo antigo de
    # importação RSS.
    fontes: Optional[str] = None
    # Revisão de publicação definitiva (aba própria em Configurações > News) —
    # etapa humana que o robô nunca faz, independente de quem/o que publicou a
    # matéria (robô /milknews, "Adicionar matéria ao blog" ou aprovação de
    # pendente). Toda matéria nasce não revisada.
    revisado_final: bool = False
    revisado_final_em: Optional[datetime] = None
    revisado_final_por: Optional[str] = None
    # Ilustração da matéria (#news-redesign) — caminho público dentro de
    # frontend/public/news-images/ (ex.: "/news-images/compost-barn-01.jpg"),
    # escolhido a partir do banco de fotos + manifesto de tags (ver
    # frontend/public/news-images/manifest.json). Nula para matérias antigas
    # ou sem foto correspondente no banco — a tela cai no fundo temático
    # rotativo já existente (newsVisual.ts) nesse caso.
    imagem: Optional[str] = None
    # Rótulo curto (pílula na tela, ex.: "Instalações", "Genética", "Qualidade
    # do Leite") — livre, sem lista fixa; nulo não mostra pílula.
    categoria: Optional[str] = None


class NotaCapa(SQLModel, table=True):
    """Nota informativa simples, exibida na Capa para o produtor — distinta de
    matéria de blog (NoticiaNews): não tem revisão nem fonte RSS, é só um
    aviso curto e atualizável (ex.: mudança regulatória/de mercado relevante),
    editável só pelo dono da plataforma (ver auth.py::exigir_dono). Só a mais
    recente com `ativa=True` aparece na Capa."""

    __tablename__ = "nota_capa"

    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    texto: str
    ativa: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Notificações push (Web Push API) — canal adicional de entrega para os
# MESMOS alertas do sininho (/notificacoes), funcionando com o app fechado.
# Ver fazenda/api/routers/push.py.
# ---------------------------------------------------------------------------
class PushSubscription(SQLModel, table=True):
    """Uma inscrição de push do navegador (PushSubscription da Web Push API)
    vinculada ao usuário logado que a criou. Um usuário pode ter mais de uma
    (um por navegador/dispositivo em que clicou "Ativar notificações")."""

    __tablename__ = "push_subscription"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    endpoint: str = Field(index=True)  # URL única do serviço de push do navegador
    p256dh: str
    auth: str
    user_agent: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


class PushNotificacaoEnviada(SQLModel, table=True):
    """Registro de deduplicação: evita reenviar o mesmo alerta (mesma
    `chave`) via push para o mesmo usuário mais de uma vez por dia — a
    lógica de "quando gerar o alerta" continua 100% em calcular_agenda()/
    notificacoes.py; isto só impede reenvio no canal de entrega novo, já
    que o sininho é reconsultado a cada poll do app aberto."""

    __tablename__ = "push_notificacao_enviada"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    chave: str = Field(index=True)
    data_referencia: date = Field(index=True)
    enviado_em: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Administração > Portal > Comunicação — mensagens internas e tarefas
# delegadas entre usuários, com sinalização na central de alertas (#513-515).
# ---------------------------------------------------------------------------
class PortalMensagem(SQLModel, table=True):
    """Uma mensagem, e-mail-log ou tarefa delegada do Portal de comunicação.

    Regras de permanência na central de alertas (ver /notificacoes):
      - tipo "tarefa": some ao ser lida (não tem fluxo de resposta).
      - tipo "mensagem" sem pede_retorno: some ao ser lida.
      - tipo "mensagem" com pede_retorno: só some quando resolvida (marcada
        "resolvido" OU respondida — responder já marca resolvida=True)."""

    __tablename__ = "portal_mensagem"

    id: Optional[int] = Field(default=None, primary_key=True)
    tipo: str = "mensagem"  # "mensagem" | "tarefa"
    remetente_usuario_id: int = Field(foreign_key="usuario.id")
    destinatario_usuario_id: int = Field(foreign_key="usuario.id", index=True)
    aba: Optional[str] = None  # sanidade|alimentacao|estoque|indicadores|financeiro|pedidos|listas|lancamentos|agenda
    corpo: str
    pede_retorno: bool = False
    lida: bool = False
    resolvida: bool = False
    # Quando esta linha é a resposta a outra, aponta para a mensagem original.
    resposta_de_id: Optional[int] = Field(default=None, foreign_key="portal_mensagem.id")
    # Quando tipo="tarefa", aponta para o evento correspondente na Agenda.
    agenda_manual_id: Optional[int] = Field(default=None, foreign_key="agenda_manual.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
