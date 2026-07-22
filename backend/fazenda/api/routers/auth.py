"""
Router de autenticação — login, dados do usuário logado e cadastro de usuários
(somente admin).
Endpoints: POST /auth/login · GET /auth/me · GET/POST /auth/usuarios
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from datetime import datetime, timedelta

from fazenda.auth import EMAIL_DONO, MODULOS, criar_token, exigir_dono, get_current_user, hash_senha, verificar_senha
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import LoginAcesso, Pessoa, Usuario
from fazenda.rules.email import enviar_email

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_SENHA_VALIDADE = timedelta(hours=1)


def _mascarar_email(email: str) -> str:
    """'jairodarte@gmail.com' -> 'j***te@gmail.com' — só a 1ª letra e as 2
    últimas do usuário do e-mail ficam visíveis, o resto vira ***."""
    if "@" not in email:
        return "***"
    local, dominio = email.split("@", 1)
    if len(local) <= 3:
        return f"{local[:1]}***@{dominio}"
    return f"{local[0]}***{local[-2:]}@{dominio}"


class LoginIn(BaseModel):
    username: str
    senha: str


class NovoUsuario(BaseModel):
    username: str
    senha: str
    pessoa_id: int
    papel: str = "operador"
    permissoes: list[str] = []
    email: str | None = None
    pode_publicar_materias_blog: bool = False


class EditarUsuario(BaseModel):
    username: str | None = None
    pessoa_id: int | None = None
    papel: str | None = None
    permissoes: list[str] | None = None
    ativo: bool | None = None
    senha: str | None = None
    email: str | None = None
    pode_publicar_materias_blog: bool | None = None


class PreferenciasIn(BaseModel):
    paleta: str | None = None
    email: str | None = None
    reivindicar_proprietario: bool = False


def _publico(u: Usuario, session: Session | None = None) -> dict:
    perms = MODULOS if u.papel == "admin" else [m for m in (u.permissoes or "").split(",") if m]
    pessoa_nome = None
    if u.pessoa_id and session is not None:
        pessoa = session.get(Pessoa, u.pessoa_id)
        pessoa_nome = pessoa.nome if pessoa else None
    return {"id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel,
            "permissoes": perms, "ativo": u.ativo, "paleta": u.paleta or "vinho",
            "email": u.email, "eh_dono": (u.email or "").strip().lower() == EMAIL_DONO,
            "pode_publicar_materias_blog": u.pode_publicar_materias_blog,
            "pessoa_id": u.pessoa_id, "pessoa_nome": pessoa_nome}


def _validar_pessoa_do_usuario(session: Session, pessoa_id: int, ignorar_usuario_id: int | None = None) -> Pessoa:
    """Toda conta de login exige uma Pessoa já cadastrada (Configurações >
    Cadastro > Pessoas) — nunca um nome livre — e cada pessoa só pode estar
    vinculada a um único usuário por vez."""
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada. Cadastre a pessoa antes de criar o login.")
    ja_vinculado = session.exec(select(Usuario).where(Usuario.pessoa_id == pessoa_id)).first()
    if ja_vinculado and ja_vinculado.id != ignorar_usuario_id:
        raise HTTPException(status_code=400, detail=f"Esta pessoa já está vinculada ao usuário \"{ja_vinculado.username}\".")
    return pessoa


@router.post("/login")
def login(dados: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.username == dados.username)).first()
    if not user or not user.ativo or not verificar_senha(dados.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    user.ultimo_login = datetime.utcnow()
    session.add(user)
    session.add(LoginAcesso(usuario_id=user.id, criado_em=user.ultimo_login))
    session.commit()
    return {"token": criar_token(user.username), "usuario": _publico(user, session)}


class EsqueciSenhaVerificarIn(BaseModel):
    username: str


class EsqueciSenhaEnviarIn(BaseModel):
    username: str


class RedefinirSenhaIn(BaseModel):
    token: str
    nova_senha: str


@router.post("/esqueci-senha/verificar")
def esqueci_senha_verificar(dados: EsqueciSenhaVerificarIn, session: Session = Depends(get_session)) -> dict:
    """Passo 1 do fluxo 'Esqueci minha senha': só confirma se o login existe e,
    se existir, devolve o e-mail cadastrado mascarado — para a janela suspensa
    perguntar 'deseja redefinir por e-mail?' sem expor o e-mail completo."""
    user = session.exec(select(Usuario).where(Usuario.username == dados.username.strip())).first()
    if not user or not user.ativo:
        return {"existe": False}
    if not user.email:
        return {"existe": True, "tem_email": False}
    return {"existe": True, "tem_email": True, "email_mascarado": _mascarar_email(user.email)}


@router.post("/esqueci-senha/enviar")
def esqueci_senha_enviar(dados: EsqueciSenhaEnviarIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.username == dados.username.strip())).first()
    if not user or not user.ativo or not user.email:
        raise HTTPException(status_code=404, detail="Não foi possível enviar o e-mail de redefinição.")
    user.reset_senha_token = secrets.token_urlsafe(32)
    user.reset_senha_expira = datetime.utcnow() + RESET_SENHA_VALIDADE
    session.add(user)
    session.commit()
    link = f"{settings.frontend_base_url}/redefinir-senha?token={user.reset_senha_token}"
    corpo_html = f"""
        <p>Olá, {user.nome or user.username}!</p>
        <p>Recebemos um pedido para redefinir a senha do seu login <strong>{user.username}</strong> no sistema da fazenda.</p>
        <p><a href="{link}">Clique aqui para definir uma nova senha</a></p>
        <p>Esse link vale por 1 hora. Se você não pediu essa redefinição, pode ignorar este e-mail.</p>
    """
    try:
        enviar_email(user.email, "Redefinição de senha", corpo_html)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"enviado": True}


@router.post("/redefinir-senha")
def redefinir_senha(dados: RedefinirSenhaIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.reset_senha_token == dados.token)).first()
    if not user or not user.reset_senha_expira or user.reset_senha_expira < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Link inválido ou expirado. Peça uma nova redefinição de senha.")
    if len(dados.nova_senha) < 4:
        raise HTTPException(status_code=400, detail="A senha deve ter ao menos 4 caracteres.")
    user.senha_hash = hash_senha(dados.nova_senha)
    user.reset_senha_token = None
    user.reset_senha_expira = None
    session.add(user)
    session.commit()
    return {"redefinido": True}


@router.get("/me")
def me(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return _publico(user, session)


@router.get("/usuarios")
def listar_usuarios(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    return [_publico(u, session) for u in session.exec(select(Usuario)).all()]


@router.get("/usuarios/acessos")
def listar_acessos(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> list[dict]:
    """Relatório de últimos acessos — restrito ao proprietário (ver exigir_dono).
    Traz os 3 logins mais recentes de cada usuário (histórico completo em
    LoginAcesso; Usuario.ultimo_login guarda só o mais recente, mantido por
    compatibilidade com o resto do sistema)."""
    usuarios = session.exec(select(Usuario)).all()
    resultado = []
    for u in sorted(usuarios, key=lambda u: (u.ultimo_login is None, u.ultimo_login or datetime.min), reverse=True):
        ultimos = session.exec(
            select(LoginAcesso).where(LoginAcesso.usuario_id == u.id).order_by(LoginAcesso.criado_em.desc()).limit(3)
        ).all()
        resultado.append({
            "id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel, "ativo": u.ativo,
            # Ambos os campos são gravados via datetime.utcnow() (naive, mas em
            # UTC) — sem o "Z", o navegador interpretaria a string como já
            # sendo horário local e exibiria um horário adiantado (bug: acesso
            # "no futuro"). Acrescentar o "Z" deixa o navegador converter para
            # o fuso local corretamente.
            "ultimo_login": (u.ultimo_login.isoformat() + "Z") if u.ultimo_login else None,
            "ultimos_acessos": [a.criado_em.isoformat() + "Z" for a in ultimos],
        })
    return resultado


@router.get("/modulos")
def listar_modulos(_: Usuario = Depends(get_current_user)) -> list[str]:
    return MODULOS


@router.post("/usuarios")
def criar_usuario(dados: NovoUsuario, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    pessoa = _validar_pessoa_do_usuario(session, dados.pessoa_id)
    perms = "" if dados.papel == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    novo = Usuario(username=dados.username, nome=pessoa.nome, pessoa_id=pessoa.id, senha_hash=hash_senha(dados.senha),
                   papel=dados.papel, permissoes=perms, email=(dados.email or "").strip() or None,
                   pode_publicar_materias_blog=dados.pode_publicar_materias_blog)
    session.add(novo)
    session.commit()
    session.refresh(novo)
    return _publico(novo, session)


@router.put("/usuarios/{user_id}")
def editar_usuario(user_id: int, dados: EditarUsuario, admin: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    u = session.get(Usuario, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if dados.username is not None and dados.username != u.username:
        if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
            raise HTTPException(status_code=400, detail="Já existe um usuário com esse login")
        u.username = dados.username
    if dados.pessoa_id is not None:
        pessoa = _validar_pessoa_do_usuario(session, dados.pessoa_id, ignorar_usuario_id=u.id)
        u.pessoa_id = pessoa.id
        u.nome = pessoa.nome
    if dados.papel is not None:
        u.papel = dados.papel
    if dados.permissoes is not None:
        u.permissoes = "" if (dados.papel or u.papel) == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    if dados.ativo is not None:
        # não deixa o admin desativar a si mesmo
        if u.id == admin.id and not dados.ativo:
            raise HTTPException(status_code=400, detail="Não é possível desativar você mesmo")
        u.ativo = dados.ativo
    if dados.senha:
        u.senha_hash = hash_senha(dados.senha)
    if dados.email is not None:
        u.email = dados.email.strip() or None
    if dados.pode_publicar_materias_blog is not None:
        u.pode_publicar_materias_blog = dados.pode_publicar_materias_blog
    session.add(u)
    session.commit()
    session.refresh(u)
    return _publico(u, session)


@router.put("/preferencias")
def salvar_preferencias(dados: PreferenciasIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    """Preferências pessoais (paleta, e-mail) — cada usuário edita as suas, sem precisar ser admin.

    O e-mail é um jeito self-service de virar "dono" (eh_dono compara com
    EMAIL_DONO) — por isso, quando o valor enviado é EXATAMENTE o e-mail do
    proprietário, isso só é aceito como uma recuperação de acesso (nenhum
    usuário admin ainda é o dono) e só para quem já é admin. Sem essa dupla
    trava, qualquer usuário comum poderia se autopromover a dono digitando o
    e-mail certo. Qualquer outro e-mail (contato pessoal) é sempre livre.

    `reivindicar_proprietario=True` é a via preferida para isso: o frontend
    não precisa saber/enviar o valor de EMAIL_DONO (evita o erro comum de um
    admin digitar o PRÓPRIO e-mail pessoal ali, achando que é isso que o
    torna dono — aquilo só salva um contato comum e nunca promove ninguém).
    Mesmas duas travas de sempre (admin + ninguém mais é dono) se aplicam.
    """
    if dados.paleta is not None:
        if dados.paleta not in ("vinho", "verde"):
            raise HTTPException(status_code=400, detail="Paleta inválida")
        user.paleta = dados.paleta
    novo_email = EMAIL_DONO if dados.reivindicar_proprietario else dados.email
    if novo_email is not None:
        novo_email = novo_email.strip() or None
        if novo_email and novo_email.lower() == EMAIL_DONO:
            if user.papel != "admin":
                raise HTTPException(status_code=403, detail="Somente um administrador pode assumir o e-mail do proprietário")
            dono_atual = session.exec(select(Usuario).where(Usuario.email == EMAIL_DONO)).first()
            if dono_atual and dono_atual.id != user.id:
                raise HTTPException(status_code=403, detail="Já existe um proprietário definido — peça para ele transferir o acesso")
        user.email = novo_email
    session.add(user)
    session.commit()
    session.refresh(user)
    return _publico(user)
