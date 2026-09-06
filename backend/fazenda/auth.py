"""
Autenticação — sem dependências externas (stdlib apenas).

- Senhas: PBKDF2-HMAC-SHA256 com salt aleatório (formato pbkdf2$iter$salt$hash).
- Token: payload base64url assinado com HMAC-SHA256 (parecido com JWT), com
  validade (exp). O segredo vem de AUTH_SECRET (env) — defina em produção.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, SeedFlag, Usuario, UsuarioFazenda,
)
from fazenda.models.equipe_cowdata_acesso import (
    CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA, NIVEL_SIGILO_PADRAO, PermissaoEquipeCowData,
)

# Segredo que assina TODO token de sessão. O valor abaixo é público (está no
# repositório) e serve só para desenvolvimento/teste — quem o conhece consegue
# forjar um token de qualquer usuário de qualquer fazenda, inclusive do dono.
# Por isso `_exigir_segredo_de_producao()` (chamado no startup, ver main.py)
# recusa subir com ele fora de dev.
SECRET_DEV = "fazenda-estreito-ponte-de-pedra-troque-em-producao"
SECRET = os.environ.get("AUTH_SECRET", SECRET_DEV)


def _rodando_em_producao() -> bool:
    """Produção = ambiente Railway chamado "production". RAILWAY_ENVIRONMENT_NAME
    é injetada automaticamente pelo Railway em todo serviço — é a fonte direta,
    em vez de deduzir pelo tipo de banco configurado. Só cai no heurístico antigo
    (Postgres configurado) se essa variável não existir (deploy fora do Railway),
    pra nunca afrouxar a proteção que já existia."""
    if os.environ.get("FAZENDA_TESTING"):
        return False
    ambiente_railway = os.environ.get("RAILWAY_ENVIRONMENT_NAME")
    if ambiente_railway is not None:
        return ambiente_railway == "production"
    return os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))


def exigir_segredo_de_producao() -> None:
    """Falha alto e cedo se o app subir em produção com o segredo de
    desenvolvimento. Antes o fallback era silencioso: bastava a variável
    AUTH_SECRET sumir do ambiente para todos os tokens passarem a ser
    assinados com uma string pública, sem nenhum sinal de que isso aconteceu."""
    if _rodando_em_producao() and SECRET == SECRET_DEV:
        raise RuntimeError(
            "AUTH_SECRET não está definida em produção — o app se recusa a subir assinando "
            "sessões com o segredo público de desenvolvimento. Defina AUTH_SECRET no ambiente."
        )
PBKDF2_ITER = 120_000
TOKEN_VALIDADE_S = 60 * 60 * 12  # 12 horas
# "Manter conectado" (checkbox no login, marcada por padrão dentro do app
# Capacitor — ver app/login/page.tsx): token de validade bem mais longa, para
# o funcionário não precisar logar de novo a cada 12h no celular pessoal dele.
# Só volta a pedir login se ele sair (logout), desinstalar o app (limpa o
# localStorage da WebView) ou desmarcar essa opção.
TOKEN_VALIDADE_LONGA_S = 60 * 60 * 24 * 90  # 90 dias
# Cadeado do Painel do Contador — reautenticação por senha que destrava,
# por um tempo curto, a escrita normalmente bloqueada em bloquear_escrita_contador
# (lançamentos extraordinários de guia/imposto/multa, recálculo de juros,
# abrir chamado). Ver /auth/desbloquear em fazenda/api/routers/auth.py.
DESBLOQUEIO_VALIDADE_S = 15 * 60  # 15 minutos

# E-mail do proprietário — único com acesso ao relatório de últimos acessos
# (ver /auth/usuarios/acessos). Fixo por enquanto, sem UI de gestão. E-mail de
# acesso principal do proprietário; rodartepradoadvogados@gmail.com continua
# funcionando como login/contato alternativo da mesma pessoa, só não é mais o
# valor que `eh_dono` compara.
#
# Usado sozinho (não via EMAILS_DONO_EQUIVALENTE) em contextos que precisam de
# UM único e-mail "de contato do proprietário" — VAPID_SUBJECT (push.py),
# destinatário do backup semanal (rules/backup.py) e as seed_* que provisionam
# a conta inicial — nunca em checagem de permissão.
EMAIL_DONO = "jairodarte@gmail.com"

# E-mails com o MESMO nível de acesso do proprietário (`eh_dono`) — hoje o
# próprio dono e o Alexandre Scarpa, sócio, a pedido explícito do proprietário
# ("ele precisa exatamente do mesmo acesso que eu dentro do site"). Lista
# pequena e nomeada de propósito: Painel CowData administra TODAS as fazendas
# clientes da SaaS, não só esta, então ampliar quem passa por `exigir_dono`
# além de contas específicas e conhecidas seria abrir uma brecha de segurança
# entre clientes (ver painel_cowdata.py, 100% gated por exigir_dono).
EMAILS_DONO_EQUIVALENTE = {EMAIL_DONO, "alexandrescarpazoo@yahoo.com.br"}


def eh_email_dono_equivalente(email: str | None) -> bool:
    return (email or "").strip().lower() in EMAILS_DONO_EQUIVALENTE


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------
def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), PBKDF2_ITER)
    return f"pbkdf2${PBKDF2_ITER}${salt}${dk.hex()}"


def verificar_senha(senha: str, guardado: str) -> bool:
    try:
        _, iters, salt, h = guardado.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def criar_token(
    username: str, fazenda_id: int | None = None, manter_conectado: bool = False,
    suporte: bool = False, sessao_suporte_id: int | None = None, nivel_sigilo: str | None = None,
) -> str:
    """`fazenda_id` (piloto conservador de multi-fazenda, ver
    fazenda/models/multitenant.py) só é gravado quando já foi selecionado —
    login com um usuário vinculado a uma única fazenda auto-seleciona; um
    usuário sem nenhuma fazenda vinculada (todo mundo antes desta mudança,
    até rodar o backfill) gera token sem "fid", e o resto do sistema continua
    se comportando exatamente como antes (ver get_fazenda_atual_id).

    `manter_conectado` estende a validade para TOKEN_VALIDADE_LONGA_S e grava
    "lembrar" no payload — assim /auth/selecionar-fazenda (que reemite o
    token já com a fazenda escolhida) consegue preservar a mesma validade
    longa em vez de voltar para as 12h padrão (ver token_manter_conectado).

    `suporte`/`sessao_suporte_id`: token emitido ao entrar numa fazenda a
    partir do Painel CowData (ver fazenda/api/routers/cofre_acesso.py) — o
    request bloqueando_em_modo_suporte usa a claim "suporte" pra recusar
    ações destrutivas, e a validade AQUI é sempre a da própria sessão de
    suporte (DURACAO_SESSAO_MINUTOS, ver models/cofre_acesso.py), nunca a
    longa de "manter conectado" — sessão de suporte é sempre curta, mesmo
    que o dono tenha "manter conectado" marcado no login.

    `nivel_sigilo`: carimbado JUNTO com "suporte" (#132) — quanto da fazenda
    esta sessão enxerga (ver NIVEIS_SIGILO_EQUIPE_COWDATA em
    models/equipe_cowdata_acesso.py). Vem no próprio token, não só no banco,
    para _bloquear_modo_suporte (main.py) não precisar de uma consulta extra
    a cada request só para saber o nível. Ignorado quando suporte=False —
    só sessão de suporte tem nível de sigilo."""
    from fazenda.models.cofre_acesso import DURACAO_SESSAO_MINUTOS

    if suporte:
        validade_s = DURACAO_SESSAO_MINUTOS * 60
    elif manter_conectado:
        validade_s = TOKEN_VALIDADE_LONGA_S
    else:
        validade_s = TOKEN_VALIDADE_S
    payload_dict = {"sub": username, "exp": int(time.time()) + validade_s}
    if fazenda_id is not None:
        payload_dict["fid"] = fazenda_id
    if manter_conectado and not suporte:
        payload_dict["lembrar"] = True
    if suporte:
        payload_dict["suporte"] = True
        if sessao_suporte_id is not None:
            payload_dict["ssid"] = sessao_suporte_id
        # Nunca omitido: sem isto, um token de suporte sem a claim cairia no
        # default mais restritivo em _bloquear_modo_suporte de qualquer
        # jeito (nsig ausente == "basico"), mas gravar explícito evita
        # qualquer ambiguidade de "esqueceram de setar" vs "é básico mesmo".
        payload_dict["nsig"] = nivel_sigilo or NIVEL_SIGILO_PADRAO
    payload = _b64(json.dumps(payload_dict).encode())
    sig = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def _validar_token_payload(token: str) -> dict | None:
    try:
        payload, sig = token.split(".")
        esperado = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, esperado):
            return None
        dados = json.loads(_unb64(payload))
        if dados.get("exp", 0) < time.time():
            return None
        return dados
    except Exception:
        return None


def validar_token(token: str) -> str | None:
    dados = _validar_token_payload(token)
    return dados.get("sub") if dados else None


def criar_token_desbloqueio(username: str) -> str:
    """Token curto emitido por /auth/desbloquear após reautenticação por
    senha — ver bloquear_escrita_contador abaixo, que é quem de fato o
    valida e concede a escrita temporária."""
    payload_dict = {
        "sub": username, "exp": int(time.time()) + DESBLOQUEIO_VALIDADE_S, "finalidade": "desbloqueio_contador",
    }
    payload = _b64(json.dumps(payload_dict).encode())
    sig = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def validar_token_desbloqueio(token: str, username: str) -> bool:
    dados = _validar_token_payload(token)
    return bool(dados) and dados.get("finalidade") == "desbloqueio_contador" and dados.get("sub") == username


# ---------------------------------------------------------------------------
# Dependências FastAPI
# ---------------------------------------------------------------------------
def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Usuario:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    username = validar_token(authorization.split(" ", 1)[1])
    if not username:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
    user = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if not user or not user.ativo:
        raise HTTPException(status_code=401, detail="Usuário inativo")
    return user


def get_fazenda_atual_id(
    authorization: str | None = Header(default=None),
) -> int | None:
    """Fazenda selecionada no login/troca de fazenda (piloto conservador de
    multi-fazenda), lida do próprio token — None para qualquer token emitido
    antes desta mudança, ou de usuário ainda sem nenhuma fazenda vinculada
    (SEM RETROATIVIDADE: essas rotas continuam vendo tudo, como sempre viram,
    até serem migradas explicitamente para considerar fazenda_id)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    dados = _validar_token_payload(authorization.split(" ", 1)[1])
    return dados.get("fid") if dados else None


def resolver_fazenda_id_escrita(session: Session, user: Usuario, fazenda_id_do_token: int | None) -> int | None:
    """Resolve a fazenda de um lançamento novo — em qualquer ambiente onde o
    multi-fazenda está de fato provisionado (tabela `fazenda` com pelo menos
    uma linha — todo ambiente de produção, desde a migração
    f1a2b3c4d5e6), NUNCA devolve None em silêncio (ao contrário de
    `get_fazenda_atual_id`/`fazenda_id_seguro`, tolerantes de propósito para
    leitura de dado legado). É a causa raiz do bug do D6 sumindo da Agenda
    (ver PR claude/fazenda-id-raiz): toda rota de escrita gravava
    `fazenda_id=fazenda_id` direto, e as 3 situações abaixo devolviam None
    ali — o registro nascia órfão. Decisão do dono do produto: não pode
    existir registro sem fazenda_id, então aqui não sobra caminho
    silencioso, só resolve certo ou recusa.

    1. Token já veio com "fid" (login normal, fazenda já escolhida) — usa.
    2. Token legado (sem "fid" — emitido antes do multi-fazenda existir, ou
       de uma sessão "manter conectado" de até 90 dias que nunca deslogou,
       ver TOKEN_VALIDADE_LONGA_S) + usuário vinculado a EXATAMENTE uma
       fazenda — resolve por ela, sem forçar reautenticação (é a imensa
       maioria: hoje a instalação tem uma fazenda real de verdade).
    3. Sem "fid" e usuário sem nenhuma fazenda vinculada, ou vinculado a mais
       de uma (não dá pra saber qual sem o token dizer): se a tabela
       `fazenda` está VAZIA, o multi-fazenda simplesmente não está em uso
       neste ambiente — devolve None, exatamente o comportamento de sempre
       (é o caso de toda a suíte de testes que não monta cenário de
       multi-fazenda, e seria o de qualquer instalação anterior à migração
       f1a2b3c4d5e6). Havendo QUALQUER fazenda cadastrada, recusa com 409 em
       vez de adivinhar — o usuário precisa sair e entrar de novo para que o
       login emita um token já com a fazenda escolhida.
    """
    if fazenda_id_do_token is not None:
        return fazenda_id_do_token
    fazendas = sorted({
        fid for fid in session.exec(
            select(UsuarioFazenda.fazenda_id).where(UsuarioFazenda.usuario_id == user.id)
        ).all()
    })
    if len(fazendas) == 1:
        return fazendas[0]
    if session.exec(select(Fazenda.id).limit(1)).first() is None:
        return None
    if not fazendas:
        raise HTTPException(
            status_code=409,
            detail="Seu usuário não está vinculado a nenhuma fazenda. Peça a um administrador para "
                   "vincular seu acesso a uma fazenda antes de lançar dados.",
        )
    raise HTTPException(
        status_code=409,
        detail="Sua sessão não tem uma fazenda selecionada e seu usuário tem acesso a mais de uma. "
               "Saia e entre novamente para escolher a fazenda antes de lançar dados.",
    )


def get_fazenda_id_escrita(
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    user: Usuario = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> int | None:
    """Dependência FastAPI para rotas de ESCRITA — troca o `fazenda_id: int |
    None = Depends(get_fazenda_atual_id)` tolerante por uma resolução que só
    devolve None quando o multi-fazenda não está provisionado neste ambiente
    (tabela `fazenda` vazia — nunca o caso em produção, ver
    `resolver_fazenda_id_escrita`); em qualquer ambiente com fazenda
    cadastrada, o valor aqui nunca chega None ao
    `session.add(Modelo(fazenda_id=fazenda_id))` do endpoint. Composta EM
    CIMA de `get_fazenda_atual_id` (não reimplementa a leitura do token) de
    propósito: assim um `dependency_overrides[get_fazenda_atual_id]` de
    teste continua valendo aqui também, sem precisar sobrescrever as duas."""
    return resolver_fazenda_id_escrita(session, user, fazenda_id)


def get_suporte_do_token(
    authorization: str | None = Header(default=None),
) -> dict:
    """Lê as claims "suporte"/"ssid"/"nsig" do token atual (ver criar_token)
    — usado pelo middleware de bloqueio_modo_suporte (main.py) e por
    /auth/me, pra o frontend saber se deve mostrar o aviso "modo suporte
    CowData" e com que nível de sigilo (#132)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"ativo": False, "sessao_id": None, "nivel_sigilo": None}
    dados = _validar_token_payload(authorization.split(" ", 1)[1])
    if not dados or not dados.get("suporte"):
        return {"ativo": False, "sessao_id": None, "nivel_sigilo": None}
    return {"ativo": True, "sessao_id": dados.get("ssid"), "nivel_sigilo": dados.get("nsig") or NIVEL_SIGILO_PADRAO}


def exigir_sessao_suporte(authorization: str | None = Header(default=None)) -> dict:
    """Dependência que EXIGE modo suporte CowData ativo (o oposto de todo o
    resto do sistema) — usada só por `POST /estoque/{id}/restaurar-padrao`
    (pedido explícito do usuário: "restaurar padrão CowData... apenas por
    meio de acesso do suporte CowData", pra fechar a mão-dupla — um tenant
    não pode desfazer sozinho uma personalização que ele mesmo escolheu)."""
    info = get_suporte_do_token(authorization)
    if not info["ativo"]:
        raise HTTPException(status_code=403, detail="Esta ação só pode ser feita durante uma sessão de suporte CowData")
    return info


def token_manter_conectado(
    authorization: str | None = Header(default=None),
) -> bool:
    """Lê "lembrar" do token atual — usado por /auth/selecionar-fazenda para
    reemitir o token (já com a fazenda escolhida) preservando a validade
    longa quando o login original marcou "Manter conectado"."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    dados = _validar_token_payload(authorization.split(" ", 1)[1])
    return bool(dados and dados.get("lembrar"))


def get_current_user_opcional(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Usuario | None:
    """Igual a get_current_user, mas retorna None em vez de 401 sem token —
    para rotas públicas (ex.: leitura do blog News) que também aceitam login."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    username = validar_token(authorization.split(" ", 1)[1])
    if not username:
        return None
    user = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if not user or not user.ativo:
        return None
    return user


def exigir_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.papel != "admin":
        raise HTTPException(status_code=403, detail="Requer administrador")
    return user


def exigir_admin_ou_dono(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Igual a `exigir_admin`, mas também deixa passar o dono-equivalente
    (ver `eh_email_dono_equivalente`) mesmo que o `papel` gravado não seja
    literalmente "admin" — usado por ferramentas administrativas pontuais
    (ex.: reconstrução de ordem de parto) onde bloquear o próprio dono da
    fazenda por causa de um `papel` divergente seria o bug, não a proteção."""
    if user.papel != "admin" and not eh_email_dono_equivalente(user.email):
        raise HTTPException(status_code=403, detail="Requer administrador")
    return user


def exigir_dono(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Restringe a quem tem acesso equivalente ao do proprietário (ver
    EMAILS_DONO_EQUIVALENTE), por e-mail cadastrado. Independente de
    papel/admin: mesmo outro admin não passa por aqui."""
    if not eh_email_dono_equivalente(user.email):
        raise HTTPException(status_code=403, detail="Acesso restrito ao proprietário")
    return user


def eh_membro_equipe_cowdata(session: Session, user: Usuario) -> bool:
    """True quando este Usuario pertence a um membro da Equipe CowData
    (Pessoa cadastrada na fazenda interna eh_empresa_cowdata=True — ver
    painel_cowdata.py). Não confundir com dono-equivalente: um membro comum
    da equipe (Financeiro, Comercial, Consultor...) não é dono, só ganha
    acesso ao que a PermissaoEquipeCowData dele liberar."""
    if not user.pessoa_id:
        return False
    pessoa = session.get(Pessoa, user.pessoa_id)
    if not pessoa or not pessoa.fazenda_id:
        return False
    fazenda = session.get(Fazenda, pessoa.fazenda_id)
    return bool(fazenda and fazenda.eh_empresa_cowdata)


def _permissao_equipe_cowdata(session: Session, usuario_id: int) -> PermissaoEquipeCowData | None:
    return session.exec(select(PermissaoEquipeCowData).where(PermissaoEquipeCowData.usuario_id == usuario_id)).first()


def nivel_sigilo_equipe_cowdata(session: Session, user: Usuario) -> str:
    """Nível de sigilo (#132) que este usuário carrega para dentro de uma
    fazenda-cliente ao abrir uma sessão de suporte — chamado UMA VEZ, na
    abertura da sessão (ver cofre_acesso.py::_abrir_sessao), pra ser
    carimbado no token (criar_token) e em SessaoAcessoSuporte.

    Dono-equivalente sempre "total" (mesmo bypass de exigir_area_painel_
    cowdata: o dono nunca teve PermissaoEquipeCowData nem precisa). Membro
    da equipe sem nenhum PermissaoEquipeCowData gravado — não deveria
    acontecer, já que abrir uma sessão exige a área "cofre" (que por sua vez
    exige essa linha existir), mas por segurança cai no nível mais
    restritivo em vez de estourar erro no meio do fluxo de suporte."""
    if eh_email_dono_equivalente(user.email):
        return "total"
    perm = _permissao_equipe_cowdata(session, user.id)
    return perm.nivel_sigilo if perm else NIVEL_SIGILO_PADRAO


def exigir_area_painel_cowdata(area: str):
    """Fábrica de dependência: dono-equivalente sempre passa (acesso total,
    como sempre); senão exige ser membro da Equipe CowData com esta área
    liberada em PermissaoEquipeCowData.areas. Usado nas rotas PRÓPRIAS do
    Painel CowData (Equipe, Financeiro CowData, Suporte/Cofre) — ainda não
    nas rotas de fazendas.py compartilhadas com o resto do sistema (ver
    docstring de fazenda/models/equipe_cowdata_acesso.py)."""

    def _dep(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> Usuario:
        if eh_email_dono_equivalente(user.email):
            return user
        perm = _permissao_equipe_cowdata(session, user.id)
        if perm and area in (perm.areas or "").split(","):
            return user
        raise HTTPException(status_code=403, detail="Sem permissão para esta área do Painel CowData")

    return _dep


def tem_permissao_painel_cowdata(session: Session, user: Usuario, permissao: str) -> bool:
    """Este usuário tem UMA das sete permissões de EDIÇÃO do Painel CowData
    (ver PERMISSOES_EDICAO_PAINEL_COWDATA em
    fazenda/models/equipe_cowdata_acesso.py)?

    Dono-equivalente sempre sim — mesmo bypass de
    `exigir_area_painel_cowdata`: o dono nunca teve linha em
    PermissaoEquipeCowData nem precisa ter. Qualquer outro sem linha gravada
    (ou com a permissão desligada) é NÃO — nunca abrir acesso por omissão,
    que é a decisão explícita da migração ("ninguém ganha nada").

    Usado como função (e não só como dependência) porque uma das rotas
    precisa checar a permissão no MEIO do handler, dependendo dos campos que
    o corpo do pedido tenta mexer — ver painel_cowdata_usuarios.py."""
    if permissao not in CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA:
        raise ValueError(f"Permissão desconhecida do Painel CowData: {permissao}")
    if eh_email_dono_equivalente(user.email):
        return True
    perm = _permissao_equipe_cowdata(session, user.id)
    return bool(perm and getattr(perm, permissao, False))


def exigir_permissao_painel_cowdata(area: str, permissao: str):
    """Fábrica de dependência para as rotas de ESCRITA do Painel CowData:
    exige a ÁREA (eixo "areas", que responde "ele VÊ esta parte do painel?")
    E a permissão booleana de edição (eixo "o que ele pode FAZER").

    As duas, sempre — nunca uma OU outra. A permissão nova é uma camada A
    MAIS por cima da checagem de área que já existia, e não um caminho
    alternativo que a contorne: sem a área, nem chega a olhar a permissão.

    É isso que dá a assimetria pedida pelo dono (set/2026): a rota de
    LEITURA continua só com `exigir_area_painel_cowdata(area)` — consulta é
    livre para quem tem a área —, e só a de escrita passa por aqui."""

    def _dep(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> Usuario:
        if eh_email_dono_equivalente(user.email):
            return user
        perm = _permissao_equipe_cowdata(session, user.id)
        if not perm or area not in (perm.areas or "").split(","):
            raise HTTPException(status_code=403, detail="Sem permissão para esta área do Painel CowData")
        if not getattr(perm, permissao, False):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para editar aqui — a consulta continua liberada. "
                       "Peça ao proprietário para marcar esta permissão no cadastro de equipe.",
            )
        return user

    return _dep


def exigir_contratante_ou_dono(
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> Usuario:
    """Contratante = usuário mestre de UMA fazenda (UsuarioFazenda.contratante,
    ver fazenda/models/multitenant.py) — gerencia a própria fazenda (ex.:
    vincular/desvincular usuários), mas não as ações reservadas só ao dono da
    plataforma (exigir_dono), como criar fazenda nova ou administrar News/Blog.
    O dono sempre passa, independente de fazenda selecionada."""
    if eh_email_dono_equivalente(user.email):
        return user
    if fazenda_id is None:
        raise HTTPException(status_code=403, detail="Requer ser contratante desta fazenda")
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if not vinculo or not vinculo.contratante:
        raise HTTPException(status_code=403, detail="Requer ser contratante desta fazenda")
    return user


def exigir_pode_publicar(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
) -> Usuario:
    """Permissão específica para publicar/gerenciar matérias do blog (News) e
    confirmar a revisão de publicação definitiva. Independente de papel/admin
    — igual exigir_dono, um admin comum não passa por aqui sem a flag.

    "Edição de News" (set/2026) entra aqui como camada A MAIS, nunca como
    caminho alternativo: para um MEMBRO DA EQUIPE COWDATA a flag antiga
    (`Usuario.pode_publicar_materias_blog`) continua sendo exigida e, além
    dela, agora também `pode_editar_news` do cadastro de equipe. Quem não é
    da Equipe CowData (usuário de fazenda-cliente com a flag) não muda em
    nada — o gate dele continua sendo só a flag.

    Quem cadastra o login da equipe marca uma coisa só na tela (Painel
    CowData > Equipe > "Editar News"): a rota que grava a permissão espelha
    a marcação na flag do Usuario (ver painel_cowdata.py::
    _aplicar_permissao_news), justamente para que o "E" acima não vire uma
    armadilha em que a caixa está marcada e mesmo assim não funciona."""
    if not user.pode_publicar_materias_blog:
        raise HTTPException(status_code=403, detail="Sem permissão para publicar matérias no blog")
    if eh_membro_equipe_cowdata(session, user) and not tem_permissao_painel_cowdata(session, user, "pode_editar_news"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar News no Painel CowData")
    return user


# Módulos do sistema (chaves usadas nas permissões dos operadores).
MODULOS = [
    "capa", "indicadores", "agenda", "lancamentos", "reproducao", "analise", "vet",
    "rebanho", "producao", "alimentacao", "sanidade", "recria", "financeiro", "estoque",
    "pedidos", "parametros", "upload",
]


def tem_modulo(user: Usuario, modulo: str) -> bool:
    if user.papel == "admin":
        return True
    liberados = {m.strip() for m in (user.permissoes or "").split(",") if m.strip()}
    return modulo in liberados


def exigir_modulo(modulo: str):
    """Dependência: exige que o usuário logado tenha acesso ao módulo."""
    def _dep(user: Usuario = Depends(get_current_user)) -> Usuario:
        if not tem_modulo(user, modulo):
            raise HTTPException(status_code=403, detail=f"Sem acesso ao módulo '{modulo}'")
        return user
    return _dep


def exigir_modulo_qualquer(*modulos: str):
    """Dependência: exige acesso a QUALQUER UM dos módulos — para dados lidos
    por mais de uma área do site (ex.: banco de touros, usado tanto em
    Configurações > Cadastro quanto em Rebanho > Touros)."""
    def _dep(user: Usuario = Depends(get_current_user)) -> Usuario:
        if not any(tem_modulo(user, m) for m in modulos):
            raise HTTPException(status_code=403, detail=f"Sem acesso a nenhum dos módulos: {', '.join(modulos)}")
        return user
    return _dep


def bloquear_escrita_contador():
    """Dependência de router (aplicada no include_router de main.py, junto
    com exigir_modulo("financeiro")) — o vínculo `contador` (Painel do
    Contador, ver fazenda/models/multitenant.py::UsuarioFazenda) é só
    leitura/exportação: qualquer método que não seja GET/HEAD/OPTIONS é
    bloqueado para quem tiver esse vínculo na fazenda selecionada. GET passa
    direto — é o que sustenta os relatórios do painel.

    Cadeado: com o header X-Desbloqueio contendo um token válido de
    /auth/desbloquear (reautenticação por senha, validade de 15 minutos —
    ver criar_token_desbloqueio acima), a escrita é liberada temporariamente
    — usado para lançamentos extraordinários de guia/imposto/multa,
    recálculo de juros e abertura de chamado."""
    def _dep(
        request: Request,
        user: Usuario = Depends(get_current_user),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
        session: Session = Depends(get_session),
        x_desbloqueio: str | None = Header(default=None),
    ) -> None:
        if request.method in ("GET", "HEAD", "OPTIONS") or fazenda_id is None:
            return
        vinculo = session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == fazenda_id)
        ).first()
        if vinculo and vinculo.contador:
            if x_desbloqueio and validar_token_desbloqueio(x_desbloqueio, user.username):
                return
            raise HTTPException(
                status_code=403,
                detail="Contador tem acesso somente leitura/exportação — destranque o cadeado com sua senha para lançamentos extraordinários",
            )
    return _dep


def exigir_nao_consultor():
    """Dependência de endpoint (não de router inteiro) — bloqueia quem tem o
    vínculo `consultor` (veterinário/agrônomo convidado, ver
    fazenda/models/multitenant.py::UsuarioFazenda) mesmo já tendo acesso ao
    módulo financeiro. Usada só em pontos sensíveis específicos (ex.: link
    para o banco de dados externo em Relatórios financeiros) — o consultor
    continua com o mesmo acesso de um funcionário comum no resto do sistema."""
    def _dep(
        user: Usuario = Depends(get_current_user),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
        session: Session = Depends(get_session),
    ) -> None:
        if fazenda_id is None:
            return
        vinculo = session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == fazenda_id)
        ).first()
        if vinculo and vinculo.consultor:
            raise HTTPException(status_code=403, detail="Consultores não têm acesso a esta funcionalidade")
    return _dep


def eh_consultor_cowdata(session: Session, usuario: Usuario) -> bool:
    """True quando este login pertence a um membro da Equipe CowData com
    cargo "Consultor" (ver painel_cowdata.py: cada membro é uma `Pessoa` da
    fazenda lógica `eh_empresa_cowdata`, e o cargo mora em `Pessoa.tipo`).

    É o que distingue o CONSULTOR COWDATA do consultor externo convidado
    pelo próprio cliente — os dois usam `UsuarioFazenda.consultor` para o
    vínculo com a fazenda, então o vínculo sozinho não diferencia."""
    if not usuario.pessoa_id:
        return False
    pessoa = session.get(Pessoa, usuario.pessoa_id)
    if not pessoa or (pessoa.tipo or "") != "Consultor":
        return False
    fazenda = session.get(Fazenda, pessoa.fazenda_id) if pessoa.fazenda_id else None
    return bool(fazenda and fazenda.eh_empresa_cowdata)


def exigir_admin_ou_consultor_fazenda():
    """Formulação de Dietas: restrita ao dono-equivalente (Alexandre Rodarte
    e Alexandre Scarpa, ver EMAILS_DONO_EQUIVALENTE) e aos CONSULTORES
    COWDATA vinculados a ESTA fazenda — pedido explícito do usuário
    (backlog #127).

    Mudou em ago/2026: antes qualquer `papel == "admin"` e o `contratante`
    da própria fazenda-cliente também entravam. Não entram mais — a
    Formulação de Dietas é serviço prestado pela CowData, não ferramenta de
    autoatendimento do cliente. Consultor EXTERNO convidado pelo cliente
    (UsuarioFazenda.consultor sem ser da Equipe CowData) também não entra;
    quem diferencia os dois é `eh_consultor_cowdata` (o vínculo sozinho não
    diferencia — ver docstring dela).

    O contador é bloqueado explicitamente (o Painel do Contador não inclui
    Formulação de Dietas). Operador comum, mesmo com o módulo `alimentacao`
    liberado, não passa — é um eixo de acesso à parte, não empilhado sobre a
    permissão de módulo comum (ver tem_modulo/exigir_modulo).

    Token sem fazenda selecionada (sem "fid") é sempre 403 aqui — ao
    contrário do resto do sistema, este módulo não tem nenhum dado legado
    para acomodar (nasceu depois do piloto de multi-fazenda), então não há
    caso legítimo de operar sem fazenda selecionada.

    Sessão de suporte CowData (token com claim "suporte") também passa
    direto, igual ao dono-equivalente — sem vínculo NESTA fazenda-cliente, o
    membro de suporte cairia sempre no 403 final apesar de precisar ver a
    tela para ajudar o cliente (mesmo raciocínio de
    exigir_modulo_contratado, logo abaixo)."""
    def _dep(
        user: Usuario = Depends(get_current_user),
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
        suporte: dict = Depends(get_suporte_do_token),
        session: Session = Depends(get_session),
    ) -> Usuario:
        if eh_email_dono_equivalente(user.email) or suporte.get("ativo"):
            return user
        if fazenda_id is None:
            raise HTTPException(status_code=403, detail="Selecione a fazenda antes de usar a Formulação de Dietas")
        vinculo = session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == fazenda_id)
        ).first()
        if vinculo and vinculo.contador:
            raise HTTPException(status_code=403, detail="O Painel do Contador não inclui Formulação de Dietas")
        if vinculo and vinculo.consultor and eh_consultor_cowdata(session, user):
            return user
        raise HTTPException(
            status_code=403,
            detail="Formulação de Dietas é restrita à CowData e ao Consultor CowData vinculado a esta fazenda.",
        )
    return _dep


# ---------------------------------------------------------------------------
# Trava por PLANO CONTRATADO (fazenda/tenant) — camada ACIMA da permissão por
# usuário acima (exigir_modulo/tem_modulo). Aquela decide o que um FUNCIONÁRIO
# vê dentro da própria fazenda; esta decide o que a FAZENDA contratou e o
# dono da plataforma aprovou (ver fazenda/models/planos.py e
# fazenda/api/routers/fazendas.py). As duas precisam passar.
#
# Token sem "fid" (emitido antes deste piloto, ou usuário ainda sem fazenda
# vinculada) pula esta checagem — mesmo comportamento "sem retroatividade"
# de get_fazenda_atual_id e de todo o resto do piloto de multi-fazenda.
# ---------------------------------------------------------------------------
def _contrato_ativo(session: Session, fazenda_id: int) -> ContratoFazenda | None:
    contrato = session.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == fazenda_id)).first()
    if not contrato or contrato.status != "ativo":
        return None
    return contrato


def exigir_contrato_ativo():
    """Dependência: só exige que a fazenda tenha um contrato ATIVO (qualquer
    módulo) — para áreas transversais que não pertencem a um módulo comercial
    específico (Agenda, Indicadores, Parâmetros, Upload/Importar). Como
    Rebanho está em todo plano, contrato ativo já garante pelo menos isso."""
    def _dep(fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session)) -> None:
        if fazenda_id is None:
            return
        if not _contrato_ativo(session, fazenda_id):
            raise HTTPException(status_code=403, detail="Fazenda sem contrato ativo — aguardando aprovação")
    return _dep


def multifazenda_provisionado(session: Session) -> bool:
    """Este ambiente tem multi-fazenda de fato em uso? (= a tabela `fazenda`
    tem pelo menos uma linha). É a linha divisória usada por
    `resolver_fazenda_id_escrita`, por `exigir_fazenda_selecionada` e pelas
    rotas que precisam recusar um token sem fazenda por conta própria: com
    zero fazendas não há tenant a isolar (instalação anterior à migração
    f1a2b3c4d5e6, e a maior parte da suíte de testes); com qualquer fazenda
    cadastrada — todo ambiente de produção — a falta de fazenda no token
    deixa de ser "legado tolerado" e passa a ser recusa."""
    return session.exec(select(Fazenda.id).limit(1)).first() is not None


def exigir_fazenda_selecionada():
    """Dependência de router: RECUSA qualquer requisição cujo token não diga
    em que fazenda ela acontece.

    É a trava que faltava para a causa raiz da auditoria (F-A-01, F-B-01,
    F-B-02, F-A-03). O sistema inteiro isola tenant pelo padrão tolerante
    `if fazenda_id is not None: query = query.where(Modelo.fazenda_id == ...)`
    — herdado do piloto de multi-fazenda, quando havia uma fazenda só e
    "sem fid" queria dizer "antes da migração". Com mais de uma fazenda-
    cliente no banco, esse `if` inverte de sentido: um token SEM "fid" não
    restringe nada, ele DESLIGA o isolamento em toda rota que segue o padrão
    — leitura e escrita, em todos os módulos ao mesmo tempo.

    Corrigir rota por rota seria interminável e frágil (são centenas de
    consultas, e cada rota nova nasceria com o mesmo risco). A trava certa é
    na porta: se a requisição vai mexer em dado de fazenda, o token tem que
    dizer QUAL fazenda. Não dizendo, ela não entra — e aí não importa quantas
    consultas lá dentro seguem o padrão tolerante.

    Três formas de um token chegar sem "fid", todas reais (ver
    routers/auth.py::login):
      1. usuário com 2+ fazendas que não chamou /auth/selecionar-fazenda;
      2. membro da Equipe CowData (o login sempre oferece a escolha a ele);
      3. token legado/"manter conectado" emitido antes do multi-fazenda.
    Nenhuma delas tem por que operar dentro de uma fazenda: (1) e (3) só
    precisam escolher a fazenda, (2) tem que entrar pelo Cofre de acesso —
    que é justamente o controle de suporte (motivo, protocolo, expiração,
    auditoria, nível de sigilo) que o login normal contornava, porque o token
    saía sem "fid" E sem "suporte" e o bloqueio de modo suporte (main.py) só
    olha a claim "suporte". A sessão de suporte legítima continua passando
    aqui: o token do Cofre carimba o `fid` da fazenda visitada
    (routers/cofre_acesso.py).

    A escape hatch é a mesma — e pela mesma razão — de
    `resolver_fazenda_id_escrita`: se a tabela `fazenda` está VAZIA, o
    multi-fazenda não está provisionado neste ambiente e não há tenant a
    isolar (é o caso da suíte de testes que não monta cenário multi-fazenda,
    e o de qualquer instalação anterior à migração f1a2b3c4d5e6). Havendo
    QUALQUER fazenda cadastrada — todo ambiente de produção —, recusa.

    Deliberadamente NÃO resolve sozinha a fazenda do usuário de vínculo único
    (como `resolver_fazenda_id_escrita` faz na escrita). Resolver aqui não
    consertaria nada: o endpoint continuaria lendo `None` do token via
    `get_fazenda_atual_id` e as consultas continuariam sem filtro. Ou o token
    diz a fazenda, ou a requisição não entra."""
    def _dep(
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
        session: Session = Depends(get_session),
    ) -> None:
        if fazenda_id is not None:
            return
        if not multifazenda_provisionado(session):
            return
        raise HTTPException(
            status_code=409,
            detail="Sua sessão não tem uma fazenda selecionada. Saia e entre novamente para "
                   "escolher em qual fazenda deseja trabalhar.",
            # 409 já é usado como status de negócio em várias rotas (conflito
            # de sincronização, lançamento duplicado...), então o frontend não
            # pode reagir ao status sozinho. Este cabeçalho é a marca que
            # distingue ESTA recusa das outras: authFetch (lib/api.ts) a
            # reconhece e manda o usuário para /escolher-conta em vez de
            # mostrar um erro cru. Precisa estar em expose_headers do CORS
            # (main.py) para o JS conseguir lê-lo.
            headers={"X-Fazenda-Nao-Selecionada": "1"},
        )
    return _dep


def fazenda_tem_modulo_contratado(session: Session, fazenda_id: int | None, modulo: str) -> bool:
    """A FAZENDA (não o usuário) tem este módulo comercial contratado e
    ativo? Mesma regra usada por `exigir_modulo_contratado` (dependência de
    rota), exposta aqui como função simples para quem precisa da mesma
    checagem DENTRO do corpo de uma função já autenticada — ex.: a Agenda
    decidindo se mostra ou não um card financeiro/de estoque sem recusar a
    rota inteira (ver fazenda/api/routers/agenda.py). Sem fazenda selecionada,
    não restringe — mesmo "sem retroatividade" de get_fazenda_atual_id."""
    if fazenda_id is None:
        return True
    tem = session.exec(
        select(ContratoFazendaModulo).where(
            ContratoFazendaModulo.fazenda_id == fazenda_id,
            ContratoFazendaModulo.modulo == modulo,
            ContratoFazendaModulo.ativo == True,  # noqa: E712
        )
    ).first()
    return tem is not None


def exigir_modulo_contratado(modulo: str):
    """Dependência: exige que A FAZENDA (não o usuário) tenha este módulo
    comercial contratado e ativo, dentro de um contrato aprovado. Some junto
    com exigir_modulo/exigir_modulo_qualquer nos include_router (main.py) —
    não substitui a permissão do funcionário, só adiciona a trava do tenant.

    Sessão de suporte CowData (token com claim "suporte", ver
    get_suporte_do_token/entrarComoSuporte) pula esta trava: o time de
    suporte precisa poder ABRIR qualquer módulo — inclusive um à-la-carte
    como Formulação de Dietas, que não vem em nenhum pacote do catálogo
    (ver fazenda/models/planos.py) — para ajudar/configurar em nome do
    cliente mesmo antes de uma contratação formal, sem depender de a
    fazenda-teste já ter o módulo cadastrado. Isto só libera LEITURA/uso;
    escrita nas áreas sensíveis continua bloqueada pelo middleware
    _bloquear_modo_suporte (main.py), e a permissão do FUNCIONÁRIO
    (exigir_modulo, checada em paralelo) não é afetada por isto."""
    def _dep(
        fazenda_id: int | None = Depends(get_fazenda_atual_id),
        suporte: dict = Depends(get_suporte_do_token),
        session: Session = Depends(get_session),
    ) -> None:
        if fazenda_id is None or suporte.get("ativo"):
            return
        if not _contrato_ativo(session, fazenda_id):
            raise HTTPException(status_code=403, detail="Fazenda sem contrato ativo — aguardando aprovação")
        if not fazenda_tem_modulo_contratado(session, fazenda_id, modulo):
            raise HTTPException(status_code=403, detail=f"Módulo '{modulo}' não contratado por esta fazenda")
    return _dep


# ---------------------------------------------------------------------------
# Seed do administrador inicial
# ---------------------------------------------------------------------------
def seed_admin(session: Session) -> None:
    """Cria o admin inicial se ainda não houver nenhum usuário. Já nasce com
    e-mail = EMAIL_DONO — é o próprio proprietário — para que `exigir_dono`/
    `eh_dono` (relatório de Acessos e Auditoria) funcionem desde o primeiro
    login, sem precisar de um passo manual de cadastro depois.

    A senha vem de ADMIN_PASS. Sem essa variável, sorteia uma senha aleatória e
    a imprime UMA vez no log — nunca cai numa senha fixa. Até aqui havia um
    valor padrão escrito no código, que é público no repositório: qualquer
    instalação que subisse sem ADMIN_PASS ficava com a senha do dono conhecida
    por quem lesse o fonte.
    """
    existe = session.exec(select(Usuario)).first()
    if existe:
        return
    username = os.environ.get("ADMIN_USER", "AlexandreRodarte")
    senha = os.environ.get("ADMIN_PASS")
    if not senha:
        senha = secrets.token_urlsafe(12)
        print(
            f"[seed_admin] ADMIN_PASS nao definida. Admin inicial '{username}' criado com senha "
            f"aleatoria: {senha}\n"
            f"[seed_admin] Anote agora e troque no primeiro acesso — ela nao sera exibida de novo.",
            flush=True,
        )
    session.add(Usuario(
        username=username, nome="Alexandre Rodarte", senha_hash=hash_senha(senha),
        papel="admin", email=EMAIL_DONO,
    ))
    session.commit()


def seed_email_dono_backfill(session: Session) -> None:
    """Uma única vez (SeedFlag): bancos já existentes (deploy anterior a esta
    mudança) têm o admin inicial sem e-mail — seed_admin() rodou antes de
    passar a gravar `email=EMAIL_DONO`, então `exigir_dono`/`eh_dono`
    (Controle de Acesso, Acessos e Auditoria — site e app) nunca fecham.
    Identifica o dono pelo `username` do admin inicial (ADMIN_USER, mesmo
    valor usado por seed_admin() — default "AlexandreRodarte"), não pela
    contagem de usuários: um sistema em produção já tem vários usuários
    cadastrados (operadores, veterinário, funcionários), então a condição
    antiga ("só quando há exatamente 1 usuário") nunca disparava e o e-mail
    do dono ficava para sempre em branco. Nunca sobrescreve um e-mail já
    definido."""
    chave = "email_dono_backfill_por_username_202607b"
    if session.get(SeedFlag, chave):
        return
    username = os.environ.get("ADMIN_USER", "AlexandreRodarte")
    dono = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if dono and not (dono.email or "").strip():
        dono.email = EMAIL_DONO
        session.add(dono)
    session.add(SeedFlag(chave=chave))
    session.commit()


def seed_email_dono_correcao_202607c(session: Session) -> None:
    """Uma única vez (SeedFlag): corrige à força o e-mail do admin inicial
    (ADMIN_USER, default "AlexandreRodarte") para o EMAIL_DONO atual —
    diferente de seed_email_dono_backfill (que só preenche se estivesse em
    branco), esta SOBRESCREVE mesmo que o campo já tenha outro valor. Motivo:
    o próprio proprietário usou o fluxo self-service "Sou o proprietário" e
    cadastrou seu e-mail pessoal (jairodarte@gmail.com) — que na época não
    batia com o EMAIL_DONO então vigente (rodartepradoadvogados@gmail.com),
    então salvou como e-mail comum e NÃO virou dono. EMAIL_DONO passou a ser
    jairodarte@gmail.com nesta mesma mudança; esta migração garante que o
    dono fique correto sem precisar de mais nenhum passo manual dele."""
    chave = "email_dono_correcao_202607c"
    if session.get(SeedFlag, chave):
        return
    username = os.environ.get("ADMIN_USER", "AlexandreRodarte")
    dono = session.exec(select(Usuario).where(Usuario.username == username)).first()
    if dono:
        dono.email = EMAIL_DONO
        session.add(dono)
    session.add(SeedFlag(chave=chave))
    session.commit()


def seed_permissao_publicar_dono(session: Session) -> None:
    """Uma única vez (SeedFlag): o proprietário (EMAIL_DONO) já nasce com a
    permissão de publicar matérias no blog, já que ele já usa essa função hoje
    (Configurações > News > Adicionar matéria ao blog). Todos os demais
    usuários — inclusive outros admins — começam sem essa permissão, como
    pedido; essa migração nunca roda de novo DEPOIS de aplicada, então o
    proprietário pode revogar a própria depois se quiser.

    Só marca a SeedFlag quando o usuário do dono já existe — o admin inicial
    (seed_admin) nasce sem e-mail, então se o e-mail só for cadastrado depois
    (Configurações > Usuários), esta migração tenta de novo no próximo
    startup em vez de desistir silenciosamente e deixar o botão "Confirmar
    revisão definitiva" sempre desabilitado."""
    chave = "pode_publicar_materias_blog_dono_202607"
    if session.get(SeedFlag, chave):
        return
    dono = session.exec(select(Usuario).where(Usuario.email == EMAIL_DONO)).first()
    if not dono:
        return
    dono.pode_publicar_materias_blog = True
    session.add(dono)
    session.add(SeedFlag(chave=chave))
    session.commit()
