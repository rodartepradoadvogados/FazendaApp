"""
Bloco das BAIXAS da auditoria (docs/security-audit/achados.json).

Dos 8 achados de severidade baixa, 6 já estavam fechados por PRs anteriores.
Sobraram dois, e os dois são sobre a mesma pergunta: **de quem é este dado?**

  35 POST /cadastro/principios-ativos/restaurar-catalogo
     Rota do TENANT que reescrevia o catálogo GLOBAL de princípios ativos
     (`PrincipioAtivo` com `fazenda_id=None`, visível a todas as fazendas por
     `rules.visibilidade.visivel`). Sem dependência de fazenda e sem gate de
     papel nenhum — qualquer usuário de qualquer fazenda com o módulo
     sanitário liberado disparava a reescrita.

     A correção não foi pendurar um `exigir_admin` lá: o catálogo global é
     dado da CowData, não da fazenda, então a rota MUDOU DE LUGAR, para
     `painel_cowdata_farmacia.py`, com o gate que as outras escritas do
     catálogo global já usam (área "farmacia" + `pode_editar_farmacia`). É a
     mesma correção estrutural que o catálogo de touros NAAB recebeu no #702.

  17 POST /financeiro/cartoes (parte de cartao_credito.py)
     Criava CartaoCredito pela dependência tolerante. Um cartão órfão leva
     junto fatura, lançamento e conta bancária vinculada — e, com
     `fazenda_id` None, a própria checagem de posse da ContaCorrente logo
     abaixo perde o efeito, porque ela está dentro de um
     `if fazenda_id is not None`.

Token real (`criar_token`), nunca `dependency_overrides` de
`get_fazenda_atual_id` — mesmo espírito dos demais
test_seguranca_*_multitenant.py.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import EMAIL_DONO, criar_token, hash_senha
from fazenda.models import (
    CartaoCredito, ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Fazenda, PrincipioAtivo,
    Usuario, UsuarioFazenda,
)
from fazenda.models.equipe_cowdata_acesso import PermissaoEquipeCowData
from fazenda.models.planos import MODULOS_COMERCIAIS

ROTA_NOVA = "/painel-cowdata/farmacia/principios/restaurar-catalogo"
ROTA_ANTIGA = "/cadastro/principios-ativos/restaurar-catalogo"


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes com um admin cada, o dono da CowData, e dois
    membros da Equipe CowData com a área "farmacia" — um COM e outro SEM a
    permissão de edição, para separar os dois eixos do gate."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Atacante"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))

        # Dono da CowData — passa por `eh_email_dono_equivalente` sem precisar
        # de PermissaoEquipeCowData (é o bypass explícito de
        # `exigir_permissao_painel_cowdata`).
        s.add(Usuario(
            id=5, username="dono", senha_hash=hash_senha("x"), papel="admin",
            email=EMAIL_DONO, ativo=True,
        ))

        # Equipe CowData COM a área "farmacia" e a permissão de edição.
        s.add(Usuario(id=6, username="equipe_edita", senha_hash=hash_senha("x"), papel="operador", ativo=True))
        s.add(PermissaoEquipeCowData(usuario_id=6, areas="farmacia", pode_editar_farmacia=True))

        # Equipe CowData com a MESMA área, mas SEM a permissão de edição — é a
        # assimetria pedida pelo dono: consulta livre, escrita não.
        s.add(Usuario(id=7, username="equipe_so_consulta", senha_hash=hash_senha("x"), papel="operador", ativo=True))
        s.add(PermissaoEquipeCowData(usuario_id=7, areas="farmacia", pode_editar_farmacia=False))

        # --- Achado 17: conta bancária da fazenda 1 -----------------------
        conta_v = ContaCorrente(banco="001", agencia="1234", numero_conta="56789-0", fazenda_id=1)
        s.add(conta_v)
        s.commit()
        s.refresh(conta_v)
        ids["conta_vitima"] = conta_v.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(username: str, fazenda_id: int | None = None):
    """Token REAL. `fazenda_id=None` é o token de quem opera o Painel CowData,
    que não trabalha dentro de nenhuma fazenda-cliente."""
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


# ---------------------------------------------------------------------------
# Achado 35 — reescrita do catálogo GLOBAL de princípios ativos
# ---------------------------------------------------------------------------
def test_rota_antiga_do_tenant_nao_existe_mais(ambiente):
    """A rota saiu do router do tenant. Enquanto ela existisse lá, o gate
    dela seria `exigir_modulo("parametros")` — que todo admin de fazenda tem
    —, e nenhuma permissão de painel seria consultada."""
    c, _engine, _ids = ambiente
    for fazenda in (1, 2):
        r = c.post(ROTA_ANTIGA, headers=_cab(f"admin{fazenda}", fazenda))
        # 405 e não 404 porque o caminho ainda casa com o `PUT
        # /principios-ativos/{item_id}` que continua existindo (e é do
        # tenant, editando a linha DELE) — o que sumiu foi o verbo POST.
        assert r.status_code in (404, 405), (
            "a rota de escrita do catálogo global continua acessível pelo lado da fazenda. "
            f"Resposta: {r.status_code} {r.text[:200]}"
        )


def test_admin_de_fazenda_nao_reescreve_o_catalogo_global(ambiente):
    """O cenário do achado, na rota nova: o admin de uma fazenda-cliente é
    admin DELA, não da CowData. O catálogo é compartilhado por todos os
    tenants — quem escreve nele tem que ser da equipe."""
    c, engine, _ids = ambiente
    for fazenda in (1, 2):
        r = c.post(ROTA_NOVA, headers=_cab(f"admin{fazenda}", fazenda))
        assert r.status_code == 403, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert not s.exec(select(PrincipioAtivo)).all(), (
            "o catálogo global foi semeado por um admin de fazenda-cliente"
        )


def test_equipe_com_a_area_mas_sem_permissao_de_edicao_e_recusada(ambiente):
    """Os dois eixos do gate são checados: ter a área "farmacia" (consulta)
    não é o mesmo que poder escrever no catálogo."""
    c, engine, _ids = ambiente
    r = c.post(ROTA_NOVA, headers=_cab("equipe_so_consulta"))
    assert r.status_code == 403, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert not s.exec(select(PrincipioAtivo)).all()


def test_equipe_com_permissao_de_edicao_restaura_o_catalogo(ambiente):
    """Controle positivo — sem ele, a correção poderia ter só quebrado a
    função em vez de protegê-la. É este caminho que o botão do Painel
    CowData usa."""
    c, engine, _ids = ambiente
    r = c.post(ROTA_NOVA, headers=_cab("equipe_edita"))
    assert r.status_code == 200, r.text
    assert r.json()["criados"] > 0, "a restauração não semeou nada — o controle positivo não vale"
    with Session(engine) as s:
        principios = s.exec(select(PrincipioAtivo)).all()
        assert principios
        assert all(p.fazenda_id is None for p in principios), (
            "o catálogo restaurado tem que ser GLOBAL (fazenda_id nulo) — se nascer carimbado "
            "numa fazenda, as outras deixam de enxergá-lo"
        )


def test_dono_da_cowdata_restaura_o_catalogo(ambiente):
    """Segundo controle positivo: o dono-equivalente passa sem ter linha de
    PermissaoEquipeCowData (bypass explícito de
    `exigir_permissao_painel_cowdata`)."""
    c, _engine, _ids = ambiente
    r = c.post(ROTA_NOVA, headers=_cab("dono"))
    assert r.status_code == 200, r.text


def test_restaurar_catalogo_e_idempotente(ambiente):
    """A rota é add-missing por contrato — rodar duas vezes não pode duplicar
    nem sobrescrever. Vale como segurança porque uma reescrita destrutiva
    disparável por engano seria um estrago irreversível no catálogo de todos
    os clientes."""
    c, engine, _ids = ambiente
    primeira = c.post(ROTA_NOVA, headers=_cab("equipe_edita")).json()
    segunda = c.post(ROTA_NOVA, headers=_cab("equipe_edita")).json()
    assert segunda["criados"] == 0, f"a segunda passada criou {segunda['criados']} linhas"
    assert segunda["total"] == primeira["total"]
    with Session(engine) as s:
        nomes = [p.nome for p in s.exec(select(PrincipioAtivo)).all()]
        assert len(nomes) == len(set(nomes)), "o catálogo ficou com princípio ativo duplicado"


# ---------------------------------------------------------------------------
# Achado 17 — POST /financeiro/cartoes
# ---------------------------------------------------------------------------
def _corpo_cartao(conta_bancaria_id: int | None = None) -> dict:
    corpo = {
        "apelido": "Cartão da fazenda", "bandeira": "visa", "limite": 10000.0,
        "dia_fechamento": 5, "dia_vencimento": 15,
    }
    if conta_bancaria_id is not None:
        corpo["conta_bancaria_id"] = conta_bancaria_id
    return corpo


def test_cartao_com_token_sem_fazenda_e_recusado(ambiente):
    """Com a trava de porta desligada (ela é uma linha por router em main.py e
    some se alguém remontar o router), a criação ainda tem que recusar em vez
    de gravar um cartão sem dono. O token é de um usuário com DOIS vínculos —
    `resolver_fazenda_id_escrita` resolve sozinha quem tem vínculo único, e
    está certo assim; é com dois que não há o que adivinhar."""
    import main

    c, engine, _ids = ambiente
    with Session(engine) as s:
        s.add(Usuario(id=9, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=2))
        s.commit()

    # Camada 1: a trava de porta recusa na entrada.
    assert c.post("/financeiro/cartoes", json=_corpo_cartao(), headers=_cab("admin_duplo")).status_code == 409

    # Camada 2: sem ela, a dependência de escrita da própria rota.
    main.app.dependency_overrides[main._fazenda_selecionada[0].dependency] = lambda: None
    r = c.post("/financeiro/cartoes", json=_corpo_cartao(), headers=_cab("admin_duplo"))
    assert r.status_code == 409, (
        "nasceu cartão de crédito sem fazenda. Fatura, lançamento e conta bancária vinculada "
        f"ficam pendurados nele. Resposta: {r.status_code} {r.text[:200]}"
    )
    with Session(engine) as s:
        assert not s.exec(select(CartaoCredito).where(CartaoCredito.fazenda_id.is_(None))).all()


def test_cartao_nao_aceita_conta_bancaria_de_outra_fazenda(ambiente):
    """A checagem de posse da ContaCorrente já existia, mas vivia dentro de um
    `if fazenda_id is not None` — com o `fazenda_id` tolerante resolvendo
    None ela não valia nada. Aqui a fazenda 2 tenta vincular a conta da 1."""
    c, engine, ids = ambiente
    r = c.post("/financeiro/cartoes", json=_corpo_cartao(ids["conta_vitima"]), headers=_cab("admin2", 2))
    assert r.status_code == 404, (
        "404, nunca 403 — um 403 já confirma que a conta existe. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )
    with Session(engine) as s:
        assert not s.exec(select(CartaoCredito)).all()


def test_cartao_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, _ids = ambiente
    r = c.post("/financeiro/cartoes", json=_corpo_cartao(), headers=_cab("admin2", 2))
    assert r.status_code == 201, r.text
    with Session(engine) as s:
        cartoes = s.exec(select(CartaoCredito)).all()
        assert [k.fazenda_id for k in cartoes] == [2]


def test_cartao_com_a_propria_conta_bancaria_continua_funcionando(ambiente):
    """Controle positivo do vínculo: a conta da própria fazenda tem que ser
    aceita. Se este quebrar junto com o de bloqueio, a checagem virou um
    "recusa tudo"."""
    c, engine, _ids = ambiente
    with Session(engine) as s:
        conta = ContaCorrente(banco="756", agencia="9999", numero_conta="1111-1", fazenda_id=2)
        s.add(conta)
        s.commit()
        s.refresh(conta)
        conta_id = conta.id
    r = c.post("/financeiro/cartoes", json=_corpo_cartao(conta_id), headers=_cab("admin2", 2))
    assert r.status_code == 201, r.text
    assert r.json()["conta_bancaria_id"] == conta_id
