"""
Painel CowData > Usuários — cria/edita login de operadores de UMA fazenda-
cliente por vez (escolhida explicitamente por fazenda_id), sem precisar
entrar nela via modo suporte.

Diferente de Cadastros globais (painel_cowdata_cadastros.py): aqui não há
"aplicar em todas as fazendas" — usuário/login é sempre de UMA fazenda só,
por natureza (pedido explícito do usuário: "à exceção de Usuários, o resto
todo... altera o parâmetro de todas as fazendas").

Reaproveita os mesmos campos/regras de POST/PUT /auth/usuarios (mesmo
formulário da tela de Configurações > Cadastro > Pessoas > Controle de
Acesso de cada fazenda), só que com fazenda_id explícito no path em vez de
vir do token (Painel CowData não tem fazenda selecionada — ver
fazenda.auth.get_fazenda_atual_id).

Fecha também uma lacuna que já existia mesmo entrando por modo suporte:
POST/PUT /auth/usuarios nunca cria o vínculo UsuarioFazenda (ver
fazenda/models/multitenant.py) — sem ele, o login do novo usuário não
resolve `fid` nenhum (0 vínculos) e ele não haveria de cair nesta fazenda
de jeito nenhum. Aqui sempre garantimos o vínculo (contratante=True quando
papel="admin", os demais como vínculo simples) ao criar OU editar.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.auth import MODULOS, _publico
from fazenda.auth import exigir_area_painel_cowdata, hash_senha
from fazenda.database import get_session
from fazenda.models import Fazenda, Pessoa, Usuario, UsuarioFazenda

router = APIRouter(prefix="/painel-cowdata/usuarios", tags=["painel-cowdata-usuarios"])


def _fazenda_cliente(session: Session, fazenda_id: int) -> Fazenda:
    f = session.get(Fazenda, fazenda_id)
    if not f or f.eh_empresa_cowdata:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return f


def _garantir_vinculo(session: Session, usuario_id: int, fazenda_id: int, papel: str) -> None:
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()
    if vinculo is None:
        session.add(UsuarioFazenda(usuario_id=usuario_id, fazenda_id=fazenda_id, contratante=(papel == "admin")))
    elif papel == "admin" and not vinculo.contratante and not vinculo.consultor and not vinculo.contador:
        vinculo.contratante = True
        session.add(vinculo)


@router.get("/{fazenda_id}/pessoas")
def listar_pessoas_da_fazenda(
    fazenda_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> list[dict]:
    _fazenda_cliente(session, fazenda_id)
    pessoas = session.exec(
        select(Pessoa).where(Pessoa.fazenda_id == fazenda_id, Pessoa.ativo == True)  # noqa: E712
    ).all()
    usuarios_por_pessoa = {
        u.pessoa_id: u.id for u in session.exec(select(Usuario).where(Usuario.pessoa_id.is_not(None))).all()
    }
    return [
        {"id": p.id, "nome": p.nome, "tipo": p.tipo, "email": p.email, "tem_usuario": p.id in usuarios_por_pessoa}
        for p in sorted(pessoas, key=lambda p: p.nome)
    ]


@router.get("/{fazenda_id}")
def listar_usuarios_da_fazenda(
    fazenda_id: int, _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> list[dict]:
    _fazenda_cliente(session, fazenda_id)
    usuarios = session.exec(
        select(Usuario).join(Pessoa, Pessoa.id == Usuario.pessoa_id).where(Pessoa.fazenda_id == fazenda_id)
    ).all()
    saida = []
    for u in usuarios:
        d = _publico(u, session)
        vinculo = session.exec(
            select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == u.id, UsuarioFazenda.fazenda_id == fazenda_id)
        ).first()
        d["vinculo_contratante"] = bool(vinculo and vinculo.contratante)
        saida.append(d)
    return saida


class NovoUsuarioFazenda(BaseModel):
    pessoa_id: int
    username: str
    senha: str
    papel: str = "operador"
    permissoes: list[str] = []
    email: str | None = None


@router.post("/{fazenda_id}")
def criar_usuario_da_fazenda(
    fazenda_id: int, dados: NovoUsuarioFazenda,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    _fazenda_cliente(session, fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada nesta fazenda")
    if session.exec(select(Usuario).where(Usuario.pessoa_id == dados.pessoa_id)).first():
        raise HTTPException(status_code=400, detail="Esta pessoa já tem um usuário")
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    perms = "" if dados.papel == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    novo = Usuario(
        username=dados.username, nome=pessoa.nome, pessoa_id=pessoa.id, senha_hash=hash_senha(dados.senha),
        papel=dados.papel, permissoes=perms, email=(dados.email or "").strip() or None,
    )
    session.add(novo)
    session.commit()
    session.refresh(novo)
    _garantir_vinculo(session, novo.id, fazenda_id, dados.papel)
    session.commit()
    return _publico(novo, session)


class EditarUsuarioFazenda(BaseModel):
    username: str | None = None
    papel: str | None = None
    permissoes: list[str] | None = None
    ativo: bool | None = None
    senha: str | None = None
    email: str | None = None


@router.put("/{fazenda_id}/{usuario_id}")
def editar_usuario_da_fazenda(
    fazenda_id: int, usuario_id: int, dados: EditarUsuarioFazenda,
    _: Usuario = Depends(exigir_area_painel_cowdata("cadastros")), session: Session = Depends(get_session),
) -> dict:
    _fazenda_cliente(session, fazenda_id)
    u = session.get(Usuario, usuario_id)
    pessoa = session.get(Pessoa, u.pessoa_id) if u and u.pessoa_id else None
    if not u or not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado nesta fazenda")
    if dados.username is not None and dados.username != u.username:
        if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
            raise HTTPException(status_code=400, detail="Já existe um usuário com esse login")
        u.username = dados.username
    if dados.papel is not None:
        u.papel = dados.papel
    if dados.permissoes is not None:
        u.permissoes = "" if (dados.papel or u.papel) == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    if dados.ativo is not None:
        u.ativo = dados.ativo
    if dados.senha:
        u.senha_hash = hash_senha(dados.senha)
    if dados.email is not None:
        u.email = dados.email.strip() or None
    session.add(u)
    session.commit()
    session.refresh(u)
    _garantir_vinculo(session, u.id, fazenda_id, u.papel)
    session.commit()
    return _publico(u, session)
