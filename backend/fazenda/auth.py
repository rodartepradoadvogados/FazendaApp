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
    ContratoConsultor, ContratoFazenda, ContratoFazendaModulo, SeedFlag, Usuario, UsuarioFazenda,
)

SECRET = os.environ.get("AUTH_SECRET", "fazenda-estreito-ponte-de-pedra-troque-em-producao")
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
EMAIL_DONO = "jairodarte@gmail.com"


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


def criar_token(username: str, fazenda_id: int | None = None, manter_conectado: bool = False) -> str:
    """`fazenda_id` (piloto conservador de multi-fazenda, ver
    fazenda/models/multitenant.py) só é gravado quando já foi selecionado —
    login com um usuário vinculado a uma única fazenda auto-seleciona; um
    usuário sem nenhuma fazenda vinculada (todo mundo antes desta mudança,
    até rodar o backfill) gera token sem "fid", e o resto do sistema continua
    se comportando exatamente como antes (ver get_fazenda_atual_id).

    `manter_conectado` estende a validade para TOKEN_VALIDADE_LONGA_S e grava
    "lembrar" no payload — assim /auth/selecionar-fazenda (que reemite o
    token já com a fazenda escolhida) consegue preservar a mesma validade
    longa em vez de voltar para as 12h padrão (ver token_manter_conectado)."""
    payload_dict = {"sub": username, "exp": int(time.time()) + (TOKEN_VALIDADE_LONGA_S if manter_conectado else TOKEN_VALIDADE_S)}
    if fazenda_id is not None:
        payload_dict["fid"] = fazenda_id
    if manter_conectado:
        payload_dict["lembrar"] = True
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


def exigir_dono(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Restringe a UM único usuário — o proprietário — por e-mail cadastrado.
    Independente de papel/admin: mesmo outro admin não passa por aqui."""
    if (user.email or "").strip().lower() != EMAIL_DONO:
        raise HTTPException(status_code=403, detail="Acesso restrito ao proprietário")
    return user


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
    if (user.email or "").strip().lower() == EMAIL_DONO:
        return user
    if fazenda_id is None:
        raise HTTPException(status_code=403, detail="Requer ser contratante desta fazenda")
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if not vinculo or not vinculo.contratante:
        raise HTTPException(status_code=403, detail="Requer ser contratante desta fazenda")
    return user


def exigir_pode_publicar(user: Usuario = Depends(get_current_user)) -> Usuario:
    """Permissão específica para publicar/gerenciar matérias do blog (News) e
    confirmar a revisão de publicação definitiva. Independente de papel/admin
    — igual exigir_dono, um admin comum não passa por aqui sem a flag."""
    if not user.pode_publicar_materias_blog:
        raise HTTPException(status_code=403, detail="Sem permissão para publicar matérias no blog")
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


def exigir_modulo_contratado(modulo: str):
    """Dependência: exige que A FAZENDA (não o usuário) tenha este módulo
    comercial contratado e ativo, dentro de um contrato aprovado. Some junto
    com exigir_modulo/exigir_modulo_qualquer nos include_router (main.py) —
    não substitui a permissão do funcionário, só adiciona a trava do tenant."""
    def _dep(fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session)) -> None:
        if fazenda_id is None:
            return
        if not _contrato_ativo(session, fazenda_id):
            raise HTTPException(status_code=403, detail="Fazenda sem contrato ativo — aguardando aprovação")
        tem = session.exec(
            select(ContratoFazendaModulo).where(
                ContratoFazendaModulo.fazenda_id == fazenda_id,
                ContratoFazendaModulo.modulo == modulo,
                ContratoFazendaModulo.ativo == True,  # noqa: E712
            )
        ).first()
        if not tem:
            raise HTTPException(status_code=403, detail=f"Módulo '{modulo}' não contratado por esta fazenda")
    return _dep


# ---------------------------------------------------------------------------
# Trava por assinatura do CONSULTOR (Fase 2C) — produto independente do
# consultor (fazendas gerenciadas por importação de planilha, fora de
# qualquer fazenda-tenant). Não confundir com exigir_modulo_contratado
# ("consultor"), que é o módulo comercial de uma FAZENDA Diamond (Fase 2B).
# ---------------------------------------------------------------------------
def _contrato_consultor_ativo(session: Session, usuario_id: int) -> ContratoConsultor | None:
    contrato = session.exec(select(ContratoConsultor).where(ContratoConsultor.usuario_id == usuario_id)).first()
    if not contrato or contrato.status != "ativo":
        return None
    return contrato


def exigir_consultor_ativo():
    """Dependência: exige que o USUÁRIO LOGADO (não uma fazenda) tenha uma
    assinatura de consultor ativa — usada pelo router de fazendas gerenciadas/
    importação/indicadores (fazenda/api/routers/consultores.py)."""
    def _dep(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> Usuario:
        if not _contrato_consultor_ativo(session, user.id):
            raise HTTPException(status_code=403, detail="Assinatura de consultor sem contrato ativo — aguardando aprovação")
        return user
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
