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
from fazenda.auth import (
    eh_email_dono_equivalente, exigir_permissao_painel_cowdata, hash_senha, tem_permissao_painel_cowdata,
)
from fazenda.database import get_session
from fazenda.models import Fazenda, Pessoa, Usuario, UsuarioFazenda

router = APIRouter(prefix="/painel-cowdata/usuarios", tags=["painel-cowdata-usuarios"])

# TRÊS PERMISSÕES SEPARADAS (set/2026), pedido explícito do dono: "consulta de
# usuários", "edição de usuários" e "controle de acesso de usuários CowData".
# Até aqui as quatro rotas deste arquivo compartilhavam a MESMA dependência
# (`exigir_area_painel_cowdata("cadastros")`) — ver ou mexer era a mesma
# coisa, e mexer aqui inclui trocar senha, papel, permissões e ativo de um
# login de fazenda-cliente, que é o material de escalada de privilégio.
#
#   _dep_consulta  — listar pessoas e usuários da fazenda (GET).
#   _dep_edicao    — criar/editar o login (POST/PUT).
#   pode_controlar_acesso_usuarios — exigida A MAIS, dentro do handler, para
#                    os campos que DÃO ACESSO: senha, papel, permissões e
#                    ativo. Criar um login é sempre dar acesso, então o POST
#                    exige as duas.
#
# Todas somam à área "cadastros", que continua sendo checada primeiro dentro
# de `exigir_permissao_painel_cowdata` — nenhuma delas é caminho alternativo
# em volta de nada. Em particular, a trava contra escalada de privilégio no
# PUT (login dono-equivalente, ver comentário lá embaixo) roda ANTES de
# qualquer permissão nova e não foi tocada.
_dep_consulta = Depends(exigir_permissao_painel_cowdata("cadastros", "pode_consultar_usuarios"))
_dep_edicao = Depends(exigir_permissao_painel_cowdata("cadastros", "pode_editar_usuarios"))

# Campos do PUT que decidem SE e COMO alguém entra — mexer neles exige, além
# de "editar usuários", a permissão de controle de acesso.
_CAMPOS_DE_ACESSO = ("senha", "papel", "permissoes", "ativo")


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
    fazenda_id: int, _: Usuario = _dep_consulta, session: Session = Depends(get_session),
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
    fazenda_id: int, _: Usuario = _dep_consulta, session: Session = Depends(get_session),
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
    ator: Usuario = _dep_edicao, session: Session = Depends(get_session),
) -> dict:
    # Criar um login É dar acesso (nasce com senha, papel e permissões), então
    # o POST exige as duas permissões — não dá para "só cadastrar" alguém sem
    # decidir com que acesso ele entra.
    if not tem_permissao_painel_cowdata(session, ator, "pode_controlar_acesso_usuarios"):
        raise HTTPException(
            status_code=403,
            detail="Criar um login define senha, papel e permissões — requer a permissão "
                   "'controle de acesso de usuários CowData'.",
        )
    _fazenda_cliente(session, fazenda_id)
    pessoa = session.get(Pessoa, dados.pessoa_id)
    if not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada nesta fazenda")
    if session.exec(select(Usuario).where(Usuario.pessoa_id == dados.pessoa_id)).first():
        raise HTTPException(status_code=400, detail="Esta pessoa já tem um usuário")
    if session.exec(select(Usuario).where(Usuario.username == dados.username)).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")
    perms = "" if dados.papel == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    email = (dados.email or "").strip() or None
    if email and eh_email_dono_equivalente(email):
        # BUG DE SEGURANÇA CORRIGIDO: esta rota é gated só por
        # exigir_area_painel_cowdata("cadastros") (área de baixo
        # privilégio, não exigir_dono) — sem esta trava, qualquer operador
        # do CowData com acesso a "cadastros" conseguia criar um usuário de
        # uma fazenda-cliente com o e-mail dono-equivalente e escalar
        # privilégio via PUT /auth/preferencias.
        raise HTTPException(status_code=403, detail="Este e-mail não pode ser atribuído por aqui.")
    novo = Usuario(
        username=dados.username, nome=pessoa.nome, pessoa_id=pessoa.id, senha_hash=hash_senha(dados.senha),
        papel=dados.papel, permissoes=perms, email=email,
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
    ator: Usuario = _dep_edicao, session: Session = Depends(get_session),
) -> dict:
    _fazenda_cliente(session, fazenda_id)
    u = session.get(Usuario, usuario_id)
    pessoa = session.get(Pessoa, u.pessoa_id) if u and u.pessoa_id else None
    if not u or not pessoa or pessoa.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado nesta fazenda")
    # BUG DE SEGURANÇA CORRIGIDO (escalada de privilégio): a trava de e-mail
    # logo abaixo só impedia ATRIBUIR um e-mail dono-equivalente a um login
    # comum — nada impedia de EDITAR um login que JÁ é dono-equivalente. E
    # essa conta existe dentro de fazenda-cliente: o sócio (ver
    # EMAILS_DONO_EQUIVALENTE em fazenda/auth.py) é uma Pessoa da fazenda,
    # com login próprio, e portanto aparece nesta rota como qualquer outro
    # usuário dela.
    #
    # Cenário concreto: um funcionário do CowData com SÓ a área "cadastros"
    # (área de baixo privilégio — não passa por exigir_dono) chamava
    # PUT /painel-cowdata/usuarios/{fazenda}/{id_do_socio} com
    # {"senha": "escolhida por ele"} e passava a poder entrar como
    # dono-equivalente: Painel CowData inteiro, todas as fazendas-clientes,
    # cofre de acesso, financeiro. O mesmo valia para trocar o `username`
    # (sequestrar o login) ou desativar a conta do dono (`ativo: false`).
    #
    # A rota equivalente que pode mexer numa conta dessas é
    # PUT /auth/usuarios, gated por exigir_dono — quem é dono-equivalente
    # continua passando aqui também, para não perder a própria tela.
    if eh_email_dono_equivalente(u.email) and not eh_email_dono_equivalente(ator.email):
        raise HTTPException(
            status_code=403,
            detail="Este login tem acesso equivalente ao do proprietário e não pode ser alterado por aqui.",
        )
    # "Controle de acesso de usuários CowData" (set/2026) — camada A MAIS,
    # DEPOIS da trava de dono-equivalente acima, nunca no lugar dela: um
    # membro sem esta permissão continua batendo primeiro naquele 403 quando
    # o alvo é a conta do dono, e este bloco não tem como afrouxá-lo. O que
    # ele acrescenta é que MEXER em senha/papel/permissões/ativo de QUALQUER
    # login — não só o do dono — passa a exigir a permissão específica; quem
    # tem só "editar usuários" fica com o que não decide acesso (username e
    # e-mail).
    campos_de_acesso = [c for c in _CAMPOS_DE_ACESSO if getattr(dados, c) is not None]
    if campos_de_acesso and not tem_permissao_painel_cowdata(session, ator, "pode_controlar_acesso_usuarios"):
        raise HTTPException(
            status_code=403,
            detail="Alterar senha, papel, permissões ou situação (ativo/inativo) requer a permissão "
                   "'controle de acesso de usuários CowData'.",
        )
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
        email = dados.email.strip() or None
        if email and eh_email_dono_equivalente(email):
            raise HTTPException(status_code=403, detail="Este e-mail não pode ser atribuído por aqui.")
        u.email = email
    session.add(u)
    session.commit()
    session.refresh(u)
    _garantir_vinculo(session, u.id, fazenda_id, u.papel)
    session.commit()
    return _publico(u, session)
