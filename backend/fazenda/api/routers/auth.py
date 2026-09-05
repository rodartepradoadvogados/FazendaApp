"""
Router de autenticação — login, dados do usuário logado e cadastro de usuários
(somente admin).
Endpoints: POST /auth/login · GET /auth/me · GET/POST /auth/usuarios
"""
from __future__ import annotations

import html
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from datetime import datetime, timedelta

from fazenda.auth import (
    DESBLOQUEIO_VALIDADE_S, EMAIL_DONO, MODULOS, criar_token, criar_token_desbloqueio, eh_consultor_cowdata,
    eh_email_dono_equivalente, eh_membro_equipe_cowdata, exigir_admin_ou_dono, exigir_dono, get_current_user,
    get_fazenda_atual_id, get_suporte_do_token, hash_senha, token_manter_conectado, verificar_senha,
)
from fazenda.models.equipe_cowdata_acesso import PermissaoEquipeCowData
from fazenda.config import settings
from fazenda.database import get_session
from fazenda.models import ContratoFazendaModulo, Fazenda, LoginAcesso, Pessoa, Usuario, UsuarioFazenda
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
    # Checkbox "Manter conectado neste aparelho" — marcada por padrão no app
    # Capacitor, desmarcada por padrão no site (ver app/login/page.tsx).
    manter_conectado: bool = False


class NovoUsuario(BaseModel):
    username: str
    senha: str
    # Uma das duas: pessoa_id (funcionário/consultor da fazenda, já cadastrado
    # em Configurações > Cadastro > Pessoas) ou nome (conta sem vínculo com
    # nenhuma fazenda — ex.: equipe da própria CowData, criada em Painel
    # CowData > Equipe — ver _validar_pessoa_ou_nome).
    pessoa_id: int | None = None
    nome: str | None = None
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
    pessoa_tipo = None
    if u.pessoa_id and session is not None:
        pessoa = session.get(Pessoa, u.pessoa_id)
        pessoa_nome = pessoa.nome if pessoa else None
        # CSV de TipoPessoa.nome (ex.: "Empreiteiro" ou "Funcionário,Diarista")
        # — usado no app de campo (frontend/lib/api.ts::ehOperadorRestrito)
        # pra restringir o Menu de operadores vinculados a certos tipos de
        # Pessoa (empreiteiro/prestador/diarista/funcionário).
        pessoa_tipo = pessoa.tipo if pessoa else None
    eh_equipe_cowdata = False
    areas_cowdata: list[str] = []
    if session is not None and not eh_email_dono_equivalente(u.email) and eh_membro_equipe_cowdata(session, u):
        eh_equipe_cowdata = True
        perm = session.exec(select(PermissaoEquipeCowData).where(PermissaoEquipeCowData.usuario_id == u.id)).first()
        areas_cowdata = [a for a in (perm.areas or "").split(",") if a] if perm else []
    return {"id": u.id, "username": u.username, "nome": u.nome, "papel": u.papel,
            # None quando o usuário nunca escolheu paleta — o frontend só deve
            # sobrescrever o que já está no navegador quando houver preferência
            # de fato salva (ver login() em frontend/lib/api.ts). Um fallback
            # fixo aqui reescreveria a paleta atual de todo mundo a cada login.
            "permissoes": perms, "ativo": u.ativo, "paleta": u.paleta,
            "email": u.email, "eh_dono": eh_email_dono_equivalente(u.email),
            "pode_publicar_materias_blog": u.pode_publicar_materias_blog,
            "pessoa_id": u.pessoa_id, "pessoa_nome": pessoa_nome, "pessoa_tipo": pessoa_tipo,
            # Membro da Equipe CowData (não dono) com login próprio — ver
            # fazenda/models/equipe_cowdata_acesso.py. `areas_painel_cowdata`
            # alimenta o filtro do menu do Painel CowData no frontend.
            "eh_equipe_cowdata": eh_equipe_cowdata, "areas_painel_cowdata": areas_cowdata,
            # Membro da Equipe CowData com cargo Consultor — junto com o
            # vínculo `consultor` NA FAZENDA SELECIONADA é o que libera a
            # Formulação de Dietas (ver auth.py::exigir_admin_ou_consultor_fazenda
            # e lib/api.ts::podeFormularDietas). Sozinho não libera nada.
            "eh_consultor_cowdata": eh_consultor_cowdata(session, u) if session is not None else False}


def _validar_pessoa_do_usuario(session: Session, pessoa_id: int, ignorar_usuario_id: int | None = None) -> Pessoa:
    """Login vinculado a uma Pessoa já cadastrada (Configurações > Cadastro >
    Pessoas) — cada pessoa só pode estar vinculada a um único usuário por vez.
    Ver _validar_pessoa_ou_nome: essa trava só vale para quem escolhe vincular
    a uma pessoa da fazenda; uma conta sem fazenda (equipe CowData) usa nome
    livre e não passa por aqui."""
    pessoa = session.get(Pessoa, pessoa_id)
    if not pessoa:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada. Cadastre a pessoa antes de criar o login.")
    ja_vinculado = session.exec(select(Usuario).where(Usuario.pessoa_id == pessoa_id)).first()
    if ja_vinculado and ja_vinculado.id != ignorar_usuario_id:
        raise HTTPException(status_code=400, detail=f"Esta pessoa já está vinculada ao usuário \"{ja_vinculado.username}\".")
    return pessoa


def _validar_pessoa_ou_nome(session: Session, pessoa_id: int | None, nome: str | None, ignorar_usuario_id: int | None = None) -> tuple[int | None, str]:
    """Resolve o par (pessoa_id, nome) de um NovoUsuario/EditarUsuario: com
    pessoa_id, valida e usa o nome da Pessoa (trava antiga, inalterada); sem
    pessoa_id, exige `nome` direto — caminho para contas sem vínculo com
    nenhuma fazenda (ex.: equipe da CowData, ver fazenda/api/routers/auth.py
    e app/painel-cowdata/equipe)."""
    if pessoa_id is not None:
        pessoa = _validar_pessoa_do_usuario(session, pessoa_id, ignorar_usuario_id)
        return pessoa.id, pessoa.nome
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        raise HTTPException(status_code=400, detail="Informe pessoa_id (funcionário da fazenda) ou nome (conta sem fazenda).")
    return None, nome_limpo


def _fazendas_vinculadas(session: Session, usuario_id: int) -> list[Fazenda]:
    vinculos = session.exec(select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id)).all()
    fazendas = [session.get(Fazenda, v.fazenda_id) for v in vinculos]
    return [f for f in fazendas if f and f.ativa]


def _fazenda_publica(f: Fazenda, vinculo: UsuarioFazenda | None = None, session: Session | None = None) -> dict:
    # `vinculo_contador` diz ao frontend se deve mandar direto pro Painel do
    # Contador (/contador, casca própria) em vez da navegação normal da
    # fazenda — ver components/AuthShell.tsx e fazenda/models/multitenant.py.
    # `vinculo_consultor` diz ao frontend que este usuário é um vínculo
    # externo (veterinário/agrônomo convidado) — usado para ESCONDER
    # funcionalidades sensíveis (ex.: botão de acesso ao banco de dados
    # externo em Relatórios financeiros) mesmo quando ele tem o módulo
    # "financeiro" liberado, ver frontend/lib/api.ts::ehConsultor().
    # `vinculo_contratante` diz ao frontend que este usuário é o usuário
    # mestre DESTA fazenda — usado por podeFormularDietas() (Formulação de
    # Dietas), espelhando fazenda.auth.exigir_admin_ou_consultor_fazenda.
    # `modulos_contratados`: os módulos comerciais que a FAZENDA (não o
    # usuário) contratou e estão ativos — mesma trava do backend
    # (fazenda.auth.exigir_modulo_contratado), espelhada aqui para a Sidebar
    # poder ESCONDER de cara o que a fazenda não comprou, em vez de mostrar o
    # item e só 403ar ao clicar ("acesso integral" mesmo em plano restrito —
    # bug real encontrado em produção). `session=None` (ex.: contexto sem
    # banco à mão) devolve lista vazia — o frontend trata ausência do campo
    # como "sem restrição conhecida", nunca escondendo por engano.
    modulos: list[str] = []
    if session is not None:
        modulos = sorted(
            m.modulo for m in session.exec(
                select(ContratoFazendaModulo).where(
                    ContratoFazendaModulo.fazenda_id == f.id, ContratoFazendaModulo.ativo == True,  # noqa: E712
                )
            ).all()
        )
    return {
        "id": f.id, "nome": f.nome, "cidade": f.cidade, "uf": f.uf,
        # Fazenda de demonstração/sandbox (ver Fazenda.eh_teste) — o
        # frontend usa isto pra desenhar a tarja de teste, nunca escondida
        # por trás de um campo ausente (default False, igual ao model).
        "eh_teste": f.eh_teste,
        "vinculo_contador": bool(vinculo and vinculo.contador),
        "vinculo_consultor": bool(vinculo and vinculo.consultor),
        "vinculo_contratante": bool(vinculo and vinculo.contratante),
        "modulos_contratados": modulos,
    }


def _vinculo(session: Session, usuario_id: int, fazenda_id: int) -> UsuarioFazenda | None:
    return session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == usuario_id, UsuarioFazenda.fazenda_id == fazenda_id)
    ).first()


def _opcoes_de_conta(session: Session, user: Usuario) -> tuple[list[Fazenda], bool, list[dict]]:
    """Único lugar que decide QUAIS contas um usuário pode escolher — usado
    tanto por POST /auth/login (no instante da autenticação) quanto por
    GET /auth/contas-disponiveis (a qualquer momento depois, ver "Trocar de
    conta" no menu e a pergunta a cada abertura do app). Extraído para cá
    porque as duas rotas têm que enxergar EXATAMENTE a mesma lista sempre —
    duas cópias do mesmo critério (dono-equivalente/Equipe CowData +
    fazendas vinculadas) são duas chances de um dia divergirem uma da outra.

    Devolve (fazendas, mostrar_opcao_cowdata, opcoes) — login() ainda
    precisa de `fazendas`/`mostrar_opcao_cowdata` à parte para decidir a
    auto-seleção (só ele faz isso; contas-disponiveis não auto-seleciona
    nada, só lista)."""
    fazendas = _fazendas_vinculadas(session, user.id)
    eh_admin_cowdata = eh_email_dono_equivalente(user.email) and len(fazendas) >= 1
    eh_membro_cowdata = not eh_email_dono_equivalente(user.email) and eh_membro_equipe_cowdata(session, user)
    mostrar_opcao_cowdata = eh_admin_cowdata or eh_membro_cowdata
    opcoes = [_fazenda_publica(f, session=session) for f in fazendas]
    if mostrar_opcao_cowdata:
        # Sentinela id=0 (fazendas de verdade começam em 1) — ver comentário
        # equivalente em login(), abaixo.
        opcoes.append({"id": 0, "nome": "Painel CowData", "cowdata": True})
    return fazendas, mostrar_opcao_cowdata, opcoes


@router.post("/login")
def login(dados: LoginIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(Usuario).where(Usuario.username == dados.username)).first()
    if not user or not user.ativo or not verificar_senha(dados.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    user.ultimo_login = datetime.utcnow()
    session.add(user)
    session.add(LoginAcesso(usuario_id=user.id, criado_em=user.ultimo_login))
    session.commit()

    # Piloto conservador de multi-fazenda (ver fazenda/models/multitenant.py):
    # 0 ou 1 fazenda vinculada → auto-seleciona (ou nenhuma) e segue como
    # sempre seguiu, sem tela nova. Só aparece a seleção quando há de fato
    # mais de uma fazenda vinculada ao mesmo usuário — EXCETO para os
    # administradores CowData (ver EMAILS_DONO_EQUIVALENTE), que sempre
    # escolhem entre a fazenda direto (administrador) e o Painel CowData
    # (suporte auditado, ver cofre_acesso.py), mesmo tendo só 1 fazenda —
    # pedido explícito do usuário: nunca cair direto numa fazenda-cliente
    # sem escolher conscientemente "como quem". Só força essa tela quando
    # existe pelo menos 1 fazenda de verdade pra oferecer ao lado do Painel
    # CowData — sem isso (dono-equivalente sem nenhum UsuarioFazenda gravado,
    # só o bypass por e-mail) mantém o comportamento de sempre, pra nunca
    # arriscar travar quem só tinha esse acesso indireto.
    # Membro da Equipe CowData com login próprio (ago/2026): mesma tela de
    # escolha do dono, mas sem exigir nenhuma fazenda vinculada — ver
    # docstring de _opcoes_de_conta.
    fazendas, mostrar_opcao_cowdata, opcoes = _opcoes_de_conta(session, user)
    fazenda_auto = fazendas[0] if (len(fazendas) == 1 and not mostrar_opcao_cowdata) else None
    resposta = {
        "token": criar_token(user.username, fazenda_id=fazenda_auto.id if fazenda_auto else None, manter_conectado=dados.manter_conectado),
        "usuario": _publico(user, session),
    }
    if fazenda_auto:
        resposta["fazenda_atual"] = _fazenda_publica(fazenda_auto, _vinculo(session, user.id, fazenda_auto.id), session)
    if len(fazendas) > 1 or mostrar_opcao_cowdata:
        # O frontend reconhece a entrada sintética "Painel CowData" (id=0)
        # pelo campo "cowdata" e, ao escolher, só navega pro Painel usando o
        # token já emitido acima (fid=None), sem chamar /auth/selecionar-
        # fazenda (essa "fazenda" não existe) — ver POST /auth/entrar-
        # painel-cowdata para o caso de reentrar nela DEPOIS de já ter
        # escolhido uma fazenda (token com fid), que este bypass aqui não
        # cobre.
        resposta["selecao_fazenda_necessaria"] = True
        resposta["fazendas_disponiveis"] = opcoes
    return resposta


class DesbloqueioIn(BaseModel):
    senha: str


@router.post("/desbloquear")
def desbloquear(dados: DesbloqueioIn, user: Usuario = Depends(get_current_user)) -> dict:
    """Reautenticação por senha — destranca por 15 min o cadeado do Painel do
    Contador (lançamentos extraordinários, recálculo de juros, chamado). Ver
    fazenda/auth.py::bloquear_escrita_contador, que valida o token retornado
    aqui via o header X-Desbloqueio."""
    if not verificar_senha(dados.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Senha incorreta")
    return {"token_desbloqueio": criar_token_desbloqueio(user.username), "validade_segundos": DESBLOQUEIO_VALIDADE_S}


class SelecionarFazendaIn(BaseModel):
    fazenda_id: int


@router.post("/selecionar-fazenda")
def selecionar_fazenda(
    dados: SelecionarFazendaIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    manter_conectado: bool = Depends(token_manter_conectado),
) -> dict:
    """Completa o login quando o usuário está vinculado a mais de uma
    fazenda — emite um novo token já com a fazenda escolhida (ver
    get_fazenda_atual_id, usado pelos endpoints que já filtram por fazenda).
    Preserva a validade longa do "Manter conectado" do login original —
    senão quem marcou a opção era jogado de volta para as 12h padrão assim
    que escolhia a fazenda."""
    vinculo = session.exec(
        select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == user.id, UsuarioFazenda.fazenda_id == dados.fazenda_id)
    ).first()
    if not vinculo:
        raise HTTPException(status_code=403, detail="Você não está vinculado a esta fazenda")
    fazenda = session.get(Fazenda, dados.fazenda_id)
    if not fazenda or not fazenda.ativa:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return {
        "token": criar_token(user.username, fazenda_id=fazenda.id, manter_conectado=manter_conectado),
        "fazenda_atual": _fazenda_publica(fazenda, vinculo, session),
    }


@router.get("/contas-disponiveis")
def contas_disponiveis(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    """Mesma lista (e o MESMO critério, ver _opcoes_de_conta) que POST
    /auth/login devolve em "fazendas_disponiveis" — só que chamável a
    qualquer momento depois do login, não só no instante dele. Alimenta a
    tela-eixo "Trocar de conta" (frontend: /escolher-conta), tanto quando o
    app pergunta sozinho a cada abertura (só faz sentido perguntar se há
    mais de 1 opção — decisão do FRONTEND, ver comentário abaixo) quanto
    quando a pessoa pede pra trocar pelo menu.

    Devolve a lista mesmo com 0 ou 1 opção — de propósito: esta rota só
    LISTA, nunca decide "vale a pena perguntar" (isso é regra de produto,
    não de dado, e já mora no frontend em dois lugares com critérios
    ligeiramente diferentes — abrir o app exige >1 opção; o menu "Trocar de
    conta" está sempre disponível, mesmo para quem só tem uma conta).
    Replicar aqui a regra "só quando > 1" duplicaria a decisão — e uma
    cópia a mais é só mais uma chance de divergir da outra."""
    _, _, opcoes = _opcoes_de_conta(session, user)
    return {"opcoes": opcoes}


@router.post("/entrar-painel-cowdata")
def entrar_painel_cowdata(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    manter_conectado: bool = Depends(token_manter_conectado),
) -> dict:
    """Reemite o token do usuário SEM a claim "fid" — o formato de token que
    o Painel CowData espera (ver get_fazenda_atual_id/criar_token).

    Por que este endpoint precisa existir: ao ESCOLHER "Painel CowData" no
    instante do login, o frontend não chama nada — só navega usando o
    token que POST /auth/login já emitiu (que nunca tem "fid" quando a
    opção Painel CowData aparece, ver login() acima). Mas quem já ENTROU
    numa fazenda antes (token COM "fid" gravado) e depois pede para trocar
    para o Painel CowData pelo meio da sessão (ver "Trocar de conta") tem
    um token que não serve — precisa de um novo, sem "fid", e é isso que
    esta rota emite.

    RESTRIÇÃO DE SEGURANÇA — NÃO RELAXAR: um token sem "fid" desliga o
    filtro por fazenda em várias rotas ainda não migradas para
    get_fazenda_id_escrita (achado de uma auditoria de segurança em
    andamento, ver docs/security-audit/achados.json — token sem fazenda
    selecionada tolera leitura/escrita cross-tenant em várias rotas). Por
    isso esta rota só emite esse tipo de token para quem já tinha o
    critério que hoje decide se a opção "Painel CowData" aparece no login
    (dono-equivalente OU membro da Equipe CowData) — nunca para um usuário
    comum, mesmo autenticado: alargar esse caminho para qualquer um seria
    abrir, por uma porta nova, exatamente o buraco que a auditoria
    encontrou. Ver test_entrar_painel_cowdata.py::
    test_usuario_comum_recebe_403.

    Preserva a validade longa do "Manter conectado", igual a
    selecionar_fazenda acima — trocar de conta no meio de uma sessão longa
    não pode jogar quem marcou a opção de volta pras 12h padrão."""
    pode_entrar = eh_email_dono_equivalente(user.email) or eh_membro_equipe_cowdata(session, user)
    if not pode_entrar:
        raise HTTPException(status_code=403, detail="Acesso restrito à administração da CowData")
    return {"token": criar_token(user.username, fazenda_id=None, manter_conectado=manter_conectado)}


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
    # BUG DE SEGURANÇA CORRIGIDO: nome/username são texto livre no cadastro
    # (ver _validar_pessoa_ou_nome) — sem escape, um valor tipo
    # "<img src=x onerror=...>" executava no cliente de e-mail.
    nome_seguro = html.escape(user.nome or user.username)
    username_seguro = html.escape(user.username)
    corpo_html = f"""
        <p>Olá, {nome_seguro}!</p>
        <p>Recebemos um pedido para redefinir a senha do seu login <strong>{username_seguro}</strong> no sistema da fazenda.</p>
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
def me(
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    suporte: dict = Depends(get_suporte_do_token),
    session: Session = Depends(get_session),
) -> dict:
    dados = _publico(user, session)
    if fazenda_id:
        fazenda = session.get(Fazenda, fazenda_id)
        if fazenda:
            dados["fazenda_atual"] = _fazenda_publica(fazenda, _vinculo(session, user.id, fazenda_id), session)
    # Sessão aberta a partir do Painel CowData (ver cofre_acesso.py) — o
    # frontend usa isso pra mostrar o aviso "modo suporte" com o botão de
    # encerrar (POST /painel-cowdata/cofre/sessoes/{id}/encerrar).
    dados["suporte_ativo"] = suporte["ativo"]
    dados["sessao_suporte_id"] = suporte["sessao_id"]
    dados["nivel_sigilo_suporte"] = suporte["nivel_sigilo"]
    return dados


@router.get("/usuarios")
def listar_usuarios(
    _: Usuario = Depends(exigir_dono),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Controle de Acesso (Insights e Administração > Controle de Acesso):
    lista os usuários da fazenda ATUAL (a mesma que o resto da tela mostra,
    inclusive em sessão de suporte — ver get_fazenda_atual_id), não de todo o
    banco. Sem o filtro, essa tela — que já pede "cadastre a pessoa NESTA
    fazenda primeiro" para criar um login novo — misturava usuários de
    QUALQUER cliente da plataforma na lista da direita (bug real encontrado
    em produção). Token sem fazenda selecionada (legado) mantém o
    comportamento antigo, sem filtro — mesmo "sem retroatividade" do resto
    do piloto de multi-fazenda."""
    query = select(Usuario)
    if fazenda_id is not None:
        query = query.join(Pessoa, Pessoa.id == Usuario.pessoa_id).where(Pessoa.fazenda_id == fazenda_id)
    return [_publico(u, session) for u in session.exec(query).all()]


@router.get("/usuarios/acessos")
def listar_acessos(
    _: Usuario = Depends(exigir_admin_ou_dono),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Relatório de últimos acessos — dono-equivalente OU administrador da
    fazenda atual (ver exigir_admin_ou_dono; pedido explícito do usuário
    ago/2026, ampliando o que antes era só `exigir_dono`).

    Escopado à fazenda ATUAL, mesmo padrão e mesmo motivo de `listar_usuarios`
    acima: sem o filtro, um administrador de UMA fazenda-cliente veria o
    histórico de login de TODAS as outras (bug de vazamento entre clientes,
    não só de UX) — `exigir_dono` sozinho nunca precisou disso porque só o
    proprietário da plataforma passava por aqui; `exigir_admin_ou_dono` abre
    a um público bem maior (qualquer administrador de qualquer fazenda-cliente),
    então o filtro deixa de ser opcional."""
    query = select(Usuario)
    if fazenda_id is not None:
        query = query.join(Pessoa, Pessoa.id == Usuario.pessoa_id).where(Pessoa.fazenda_id == fazenda_id)
    usuarios = session.exec(query).all()
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
    pessoa_id, nome = _validar_pessoa_ou_nome(session, dados.pessoa_id, dados.nome)
    perms = "" if dados.papel == "admin" else ",".join(m for m in dados.permissoes if m in MODULOS)
    novo = Usuario(username=dados.username, nome=nome, pessoa_id=pessoa_id, senha_hash=hash_senha(dados.senha),
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
        if dados.paleta not in ("vinho", "verde", "azul"):
            raise HTTPException(status_code=400, detail="Paleta inválida")
        user.paleta = dados.paleta
    novo_email = EMAIL_DONO if dados.reivindicar_proprietario else dados.email
    if novo_email is not None:
        novo_email = novo_email.strip() or None
        if novo_email and eh_email_dono_equivalente(novo_email):
            # BUG DE SEGURANÇA CORRIGIDO: a checagem antiga comparava só com
            # EMAIL_DONO (`== EMAIL_DONO`), não com o conjunto completo
            # EMAILS_DONO_EQUIVALENTE — qualquer usuário autenticado, de
            # qualquer papel, conseguia virar dono-equivalente só enviando o
            # OUTRO e-mail da lista (nunca o literal EMAIL_DONO), pulando as
            # duas travas abaixo por inteiro. Auto-atendimento continua
            # existindo só para EMAIL_DONO (via reivindicar_proprietario ou
            # digitando o valor certo) — o(s) outro(s) e-mail(is)
            # equivalente(s) nunca são atribuíveis por aqui.
            if novo_email.lower() != EMAIL_DONO:
                raise HTTPException(status_code=403, detail="Este e-mail não pode ser definido por aqui.")
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
