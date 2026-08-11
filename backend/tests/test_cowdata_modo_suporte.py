"""
Painel CowData como instância à parte: administradores CowData
(EMAILS_DONO_EQUIVALENTE) escolhem, ao logar, entre entrar DIRETO numa
fazenda vinculada (administrador — acesso de sempre, sem restrição) ou
entrar pelo Painel CowData (e, de lá, abrir uma fazenda como SUPORTE —
via Cofre de Acesso, token com validade curta e ações destrutivas
bloqueadas). Ver fazenda/api/routers/auth.py::login, cofre_acesso.py e
main.py::_bloquear_modo_suporte.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.api.routers.painel_cowdata import seed_cowdata_empresa
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, Usuario
from fazenda.models.multitenant import UsuarioFazenda


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fazenda = Fazenda(nome="Fazenda Jairo Nasser", ativa=True)
        s.add(fazenda)
        s.commit()
        s.refresh(fazenda)

        dono = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO)
        sem_vinculo = Usuario(username="dono-sem-vinculo", nome="Dono sem vínculo", senha_hash=hash_senha("123"), papel="admin", email="alexandrescarpazoo@yahoo.com.br")
        comum = Usuario(username="admin-comum", nome="Admin comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com")
        s.add_all([dono, sem_vinculo, comum])
        s.commit()
        s.refresh(dono)
        s.refresh(comum)

        s.add(UsuarioFazenda(usuario_id=dono.id, fazenda_id=fazenda.id, contratante=True))
        s.add(UsuarioFazenda(usuario_id=comum.id, fazenda_id=fazenda.id))
        s.commit()

        # Fazenda "CowData (empresa)" + cargos — necessário pros testes de
        # nível de sigilo, que criam um membro de verdade da Equipe CowData
        # (não dono-equivalente) com PermissaoEquipeCowData.nivel_sigilo.
        seed_cowdata_empresa(s)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def _fazenda_id(client) -> int:
    r = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"})
    return r.json()["fazenda_atual"]["id"]


def test_dono_com_vinculo_sempre_ve_o_escolhedor(client):
    """Mesmo com só 1 fazenda vinculada — diferente do piloto multi-fazenda
    comum (que só mostra a tela com >1) — o dono-equivalente sempre escolhe
    conscientemente entre a fazenda e o Painel CowData."""
    r = client.post("/auth/login", json={"username": "dono", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert data["selecao_fazenda_necessaria"] is True
    nomes = {f["nome"] for f in data["fazendas_disponiveis"]}
    assert "Fazenda Jairo Nasser" in nomes
    assert "Painel CowData" in nomes
    cowdata = next(f for f in data["fazendas_disponiveis"] if f["nome"] == "Painel CowData")
    assert cowdata["cowdata"] is True
    assert cowdata["id"] == 0
    # Sem fazenda_atual — token emitido já vem sem "fid" até escolher.
    assert "fazenda_atual" not in data


def test_admin_comum_com_1_fazenda_continua_auto_selecionando(client):
    """Regressão: usuário comum (não dono-equivalente) com 1 fazenda vinculada
    continua exatamente como antes — sem tela de escolha nenhuma."""
    r = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert "selecao_fazenda_necessaria" not in data
    assert data["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"


def test_dono_sem_nenhum_vinculo_nao_forca_escolhedor(client):
    """Rede de segurança: dono-equivalente sem UsuarioFazenda gravado (só o
    bypass por e-mail) mantém o comportamento de sempre — nunca arrisca
    travar quem só tinha esse acesso indireto."""
    r = client.post("/auth/login", json={"username": "dono-sem-vinculo", "senha": "123"})
    assert r.status_code == 200
    data = r.json()
    assert "selecao_fazenda_necessaria" not in data
    r2 = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {data['token']}"})
    assert r2.status_code == 200


def test_escolher_fazenda_direto_da_acesso_de_administrador_sem_restricao(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post("/auth/selecionar-fazenda", json={"fazenda_id": fid}, headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    token = r.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["suporte_ativo"] is False
    assert me["sessao_suporte_id"] is None
    assert me["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"

    # DELETE em qualquer rota some/existente não é bloqueado pelo middleware
    # (o 404 de rota inexistente prova que passou direto, sem a mensagem
    # 403 do modo suporte).
    r = client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_entrar_pelo_painel_cowdata_e_abrir_fazenda_gera_token_de_suporte(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    # "Escolher Painel CowData" no frontend = simplesmente não chamar
    # /auth/selecionar-fazenda — o token do login (sem fid) já serve.
    token_cowdata = login["token"]
    r = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token_cowdata}"})
    assert r.status_code == 200

    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Auxílio/treinamento de usuário", "assunto_chamado": "Dúvida do cliente sobre relatório"},
        headers={"Authorization": f"Bearer {token_cowdata}"},
    )
    assert r.status_code == 200
    pedido = r.json()
    assert pedido["status"] == "aprovado"
    assert "token" in pedido and pedido["token"]
    assert pedido["sessao_id"] is not None
    assert pedido["sessao_expira_em"]

    token_suporte = pedido["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token_suporte}"}).json()
    assert me["suporte_ativo"] is True
    assert me["sessao_suporte_id"] is not None
    assert me["fazenda_atual"]["nome"] == "Fazenda Jairo Nasser"


def _token_suporte(client) -> str:
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Configurar parâmetros da fazenda", "assunto_chamado": "Ajuste de parâmetro de teste"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    return r.json()["token"]


def test_modo_suporte_bloqueia_delete(client):
    token = _token_suporte(client)
    r = client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_bloqueia_escrita_em_financeiro(client):
    token = _token_suporte(client)
    r = client.post("/financeiro/qualquer-coisa", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_nao_bloqueia_leitura(client):
    token = _token_suporte(client)
    r = client.get("/painel-cowdata/cofre/motivos", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_modo_suporte_consegue_encerrar_a_propria_sessao(client):
    """A própria rota de encerrar sessão do Cofre não pode ficar bloqueada
    pelo middleware — senão quem entra em modo suporte fica preso até expirar."""
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    pedido = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Diagnosticar erro relatado", "assunto_chamado": "Erro relatado pelo cliente"},
        headers={"Authorization": f"Bearer {login['token']}"},
    ).json()
    token_suporte = pedido["token"]
    sessoes = client.get("/painel-cowdata/cofre/sessoes-ativas", headers={"Authorization": f"Bearer {login['token']}"}).json()
    sessao_id = next(s["id"] for s in sessoes if s["fazenda_id"] == fid)

    r = client.post(f"/painel-cowdata/cofre/sessoes/{sessao_id}/encerrar", headers={"Authorization": f"Bearer {token_suporte}"})
    assert r.status_code == 200
    assert r.json()["encerrada_em"] is not None


def test_pedido_exige_assunto_chamado(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Diagnosticar erro relatado", "assunto_chamado": "   "},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert r.status_code == 400
    assert "assunto" in r.json()["detail"].lower()


def test_pedido_rejeita_motivo_fora_da_lista(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Motivo qualquer inventado", "assunto_chamado": "Teste"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert r.status_code == 400


def test_pedido_e_sessao_trazem_protocolo_e_assunto(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    fid = _fazenda_id(client)
    pedido = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Incidente de segurança", "assunto_chamado": "Verificar login suspeito", "observacao": "Relatado por e-mail"},
        headers={"Authorization": f"Bearer {login['token']}"},
    ).json()
    assert pedido["protocolo"] == f"SUP-{pedido['id']:06d}"
    assert pedido["assunto_chamado"] == "Verificar login suspeito"
    assert pedido["observacao"] == "Relatado por e-mail"

    sessoes = client.get("/painel-cowdata/cofre/sessoes-ativas", headers={"Authorization": f"Bearer {login['token']}"}).json()
    sessao = next(s for s in sessoes if s["fazenda_id"] == fid)
    assert sessao["protocolo"] == pedido["protocolo"]
    assert sessao["assunto_chamado"] == "Verificar login suspeito"


def test_fazendas_cofre_traz_plano_e_modulos(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    r = client.get("/painel-cowdata/cofre/fazendas", headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    fazenda = r.json()[0]
    assert "plano_nome" in fazenda
    assert "modulos" in fazenda
    assert isinstance(fazenda["modulos"], list)


def test_acoes_de_suporte_registram_escrita_bloqueada_e_permitida(client):
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    token_suporte = _token_suporte(client)

    # DELETE é sempre bloqueado — vira uma linha "bloqueada" na auditoria.
    client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token_suporte}"})
    # POST fora de prefixo sensível passa (o 404 é da rota inexistente, não
    # do middleware) — vira uma linha "permitida", com o status real (404).
    client.post("/rota-inofensiva-qualquer", json={}, headers={"Authorization": f"Bearer {token_suporte}"})

    r = client.get("/painel-cowdata/cofre/acoes", headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    acoes = r.json()
    bloqueadas = [a for a in acoes if a["metodo"] == "DELETE" and a["caminho"] == "/rota-que-nao-existe"]
    permitidas = [a for a in acoes if a["metodo"] == "POST" and a["caminho"] == "/rota-inofensiva-qualquer"]
    assert len(bloqueadas) == 1 and bloqueadas[0]["bloqueado"] is True
    assert len(permitidas) == 1 and permitidas[0]["bloqueado"] is False and permitidas[0]["status_code"] == 404
    assert bloqueadas[0]["protocolo"] is not None


def test_acesso_a_minha_fazenda_acoes_exige_contratante_ou_dono(client):
    fid = _fazenda_id(client)
    token_suporte = _token_suporte(client)
    client.delete("/rota-que-nao-existe", headers={"Authorization": f"Bearer {token_suporte}"})

    # O dono, com a fazenda selecionada, enxerga a auditoria da fazenda.
    login = client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()
    sel = client.post("/auth/selecionar-fazenda", json={"fazenda_id": fid}, headers={"Authorization": f"Bearer {login['token']}"}).json()
    r = client.get("/painel-cowdata/cofre/minha-fazenda/acoes", headers={"Authorization": f"Bearer {sel['token']}"})
    assert r.status_code == 200
    assert len(r.json()) >= 1

    # Admin comum (vinculado, mas sem ser contratante) NÃO enxerga.
    login_comum = client.post("/auth/login", json={"username": "admin-comum", "senha": "123"}).json()
    r2 = client.get("/painel-cowdata/cofre/minha-fazenda/acoes", headers={"Authorization": f"Bearer {login_comum['token']}"})
    assert r2.status_code == 403


# ---------------------------------------------------------------------------
# FALHA DE SEGURANÇA (#132) — folha de pagamento/RH mora sob "/cadastro"
# (rh_folha.py, rh_contratos.py, rh_vale_item.py — ver fazenda/api/routers/
# cadastro/__init__.py), não sob "/financeiro". Antes da correção,
# _PREFIXOS_SENSIVEIS_MODO_SUPORTE só continha "/financeiro" e mais 4
# prefixos, então uma sessão de suporte CowData conseguia ESCREVER folha,
# rescisão, férias, 13º, diária e vale de uma fazenda-cliente. Estes testes
# falhavam antes da correção em main.py (a rota devolvia 404 — "passou
# direto pelo middleware" — em vez de 403 "bloqueada").
# ---------------------------------------------------------------------------
_ROTAS_RH_SOB_CADASTRO = [
    "/cadastro/folha-pagamento",
    "/cadastro/folha-pagamento-unificada",
    "/cadastro/ferias",
    "/cadastro/decimo-terceiro",
    "/cadastro/rescisao",
    "/cadastro/rescisoes",
    "/cadastro/vales",
    "/cadastro/vale-item",
    "/cadastro/vale-avulso",
    "/cadastro/empreitadas",
    "/cadastro/contratos",
    "/cadastro/diarias",
]


@pytest.mark.parametrize("prefixo", _ROTAS_RH_SOB_CADASTRO)
def test_modo_suporte_bloqueia_escrita_em_rh_sob_cadastro(client, prefixo):
    """POST em cada prefixo de RH sob /cadastro tem que dar 403 (bloqueado
    pelo middleware) — não 404 (rota real respondendo, ou pior, aceitando o
    lançamento). Sub-caminho arbitrário porque o middleware bloqueia por
    PREFIXO, antes de qualquer roteamento real (mesmo padrão já usado por
    test_modo_suporte_bloqueia_escrita_em_financeiro, acima)."""
    token = _token_suporte(client)
    r = client.post(f"{prefixo}/qualquer-coisa", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, f"{prefixo}: esperava 403 (bloqueado), veio {r.status_code} — {r.text}"
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_bloqueia_put_em_rh_sob_cadastro(client):
    """PUT (edição) também precisa ficar bloqueado — não só POST/DELETE."""
    token = _token_suporte(client)
    r = client.put("/cadastro/rescisoes/1", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "modo suporte" in r.json()["detail"].lower()


def test_modo_suporte_continua_escrevendo_em_cadastro_operacional_comum(client):
    """A correção da falha de segurança tem que ser CIRÚRGICA: só os
    prefixos de RH — o resto de /cadastro (raças, motivos, unidades de
    estoque etc.) continua liberado para escrita em modo suporte. Caminho
    arbitrário/inexistente sob /cadastro (mesma técnica das demais rotas
    deste arquivo): o 404 aqui só prova algo se vier da rota faltando, não
    do middleware — por isso comparamos com a mensagem, não só o status."""
    token = _token_suporte(client)
    r = client.post("/cadastro/rota-operacional-generica-inexistente", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404, f"cadastro operacional comum não deveria ser bloqueado pelo modo suporte — {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Nível de sigilo por conta (#132) — carimbado no token quando a sessão de
# suporte abre (ver PermissaoEquipeCowData.nivel_sigilo, criar_token e
# _bloquear_modo_suporte), controla tanto ESCRITA (já sempre bloqueada nos
# prefixos sensíveis, independente do nível) quanto LEITURA (GET) das áreas
# acima do nível da sessão.
# ---------------------------------------------------------------------------
def _token_dono(client) -> str:
    return client.post("/auth/login", json={"username": "dono", "senha": "123"}).json()["token"]


def _criar_membro_suporte(client, nivel_sigilo: str, username: str = "membro.suporte") -> dict:
    """Membro de verdade da Equipe CowData (não dono-equivalente), com área
    "cofre" liberada (pré-requisito pra pedir acesso) e o nível de sigilo
    dado."""
    token_dono = _token_dono(client)
    pessoa = client.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Membro Suporte", "cargo": "Suporte"},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    usuario = client.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={"username": username, "email": f"{username}@x.com", "senha": "senha123", "areas": ["cofre"], "nivel_sigilo": nivel_sigilo},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    return usuario


def _abrir_suporte_como(client, username: str, fid: int, senha: str = "senha123") -> dict:
    login = client.post("/auth/login", json={"username": username, "senha": senha}).json()
    r = client.post(
        "/painel-cowdata/cofre/pedidos",
        json={"fazenda_id": fid, "motivo": "Diagnosticar erro relatado", "assunto_chamado": "Teste de nível de sigilo"},
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_membro_criado_sem_nivel_explicito_recebe_o_mais_restritivo(client):
    """Regra de ouro da migração/cadastro: nunca abrir acesso por omissão."""
    token_dono = _token_dono(client)
    pessoa = client.post(
        "/painel-cowdata/equipe/pessoas", json={"nome": "Sem Nível", "cargo": "Suporte"},
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    usuario = client.post(
        f"/painel-cowdata/equipe/pessoas/{pessoa['id']}/usuario",
        json={"username": "sem.nivel", "email": "sn@x.com", "senha": "senha123", "areas": ["cofre"]},  # nivel_sigilo omitido
        headers={"Authorization": f"Bearer {token_dono}"},
    ).json()
    assert usuario["nivel_sigilo"] == "basico"


def test_pedido_traz_nivel_de_sigilo_carimbado_no_token(client):
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "tecnico")
    pedido = _abrir_suporte_como(client, "membro.suporte", fid)
    assert pedido["nivel_sigilo"] == "tecnico"


def test_nivel_basico_bloqueia_leitura_de_financeiro_e_rh(client):
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "basico")
    token = _abrir_suporte_como(client, "membro.suporte", fid)["token"]

    r_fin = client.get("/financeiro/qualquer-coisa", headers={"Authorization": f"Bearer {token}"})
    assert r_fin.status_code == 403
    assert "nível de sigilo" in r_fin.json()["detail"].lower()
    assert "financeiro" in r_fin.json()["detail"].lower()

    r_rh = client.get("/cadastro/folha-pagamento-zzz-inexistente", headers={"Authorization": f"Bearer {token}"})
    assert r_rh.status_code == 403
    assert "folha de pagamento" in r_rh.json()["detail"].lower()

    # Operacional (fora de qualquer grupo) continua livre — 404 é da rota
    # inexistente, prova que não foi o middleware quem bloqueou.
    r_op = client.get("/rebanho-rota-generica-qualquer", headers={"Authorization": f"Bearer {token}"})
    assert r_op.status_code == 404


def test_nivel_tecnico_permite_financeiro_mas_nao_rh(client):
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "tecnico")
    token = _abrir_suporte_como(client, "membro.suporte", fid)["token"]

    r_fin = client.get("/financeiro/qualquer-coisa", headers={"Authorization": f"Bearer {token}"})
    assert r_fin.status_code == 404  # não bloqueado — passou pro roteamento normal

    r_rh = client.get("/cadastro/rescisoes-zzz-inexistente", headers={"Authorization": f"Bearer {token}"})
    assert r_rh.status_code == 403
    assert "folha de pagamento" in r_rh.json()["detail"].lower()


def test_nivel_total_permite_leitura_de_tudo(client):
    """Caminhos inexistentes sob os grupos antes bloqueados — o objetivo é
    provar que o middleware NÃO intercepta mais (404 "rota não existe", não
    403 "bloqueado"), sem depender de contrato/módulo contratado pela
    fazenda-teste (que aqui não existe — ver GET real x caminho arbitrário
    nos outros testes deste arquivo)."""
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "total")
    token = _abrir_suporte_como(client, "membro.suporte", fid)["token"]

    assert client.get("/financeiro/qualquer-coisa", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.get("/cadastro/folha-pagamento-zzz-inexistente", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    # Escrita continua bloqueada mesmo em "total" — nível de sigilo é sobre
    # LEITURA; ESCRITA em RH/financeiro fica sempre proibida em modo suporte.
    r = client.post("/cadastro/rescisoes", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_dono_equivalente_em_suporte_sempre_nivel_total(client):
    """Dono nunca tem PermissaoEquipeCowData (bypassa por e-mail) — precisa
    cair em "total" mesmo assim, senão o próprio dono ficaria mais restrito
    que um membro comum configurado com nível alto."""
    fid = _fazenda_id(client)
    pedido = _abrir_suporte_como(client, "dono", fid, senha="123")
    assert pedido["nivel_sigilo"] == "total"
    token = pedido["token"]
    assert client.get("/cadastro/folha-pagamento-zzz-inexistente", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_sessao_e_auditoria_registram_nivel_de_sigilo(client):
    """#132(e): o dono da fazenda precisa conseguir conferir depois com que
    alcance cada suporte entrou — nível de sigilo tem que aparecer tanto na
    sessão ativa quanto no log grosso de entrada/saída e na ação bloqueada."""
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "basico")
    pedido = _abrir_suporte_como(client, "membro.suporte", fid)
    token = pedido["token"]

    # Tenta uma leitura que o nível "basico" não alcança — vira uma linha de
    # auditoria bloqueada (só GET bloqueado é auditado, não todo GET).
    client.get("/financeiro/qualquer-coisa", headers={"Authorization": f"Bearer {token}"})

    token_dono = _token_dono(client)
    sessoes = client.get("/painel-cowdata/cofre/sessoes-ativas", headers={"Authorization": f"Bearer {token_dono}"}).json()
    sessao = next(s for s in sessoes if s["id"] == pedido["sessao_id"])
    assert sessao["nivel_sigilo"] == "basico"

    entradas = client.get("/painel-cowdata/cofre/auditoria", headers={"Authorization": f"Bearer {token_dono}"}).json()
    entrada = next(e for e in entradas if e["fazenda_id"] == fid and e["acao"] == "entrada")
    assert entrada["nivel_sigilo"] == "basico"

    acoes = client.get("/painel-cowdata/cofre/acoes", headers={"Authorization": f"Bearer {token_dono}"}).json()
    bloqueada_get = next(a for a in acoes if a["metodo"] == "GET" and a["caminho"] == "/financeiro/qualquer-coisa")
    assert bloqueada_get["bloqueado"] is True
    assert bloqueada_get["nivel_sigilo"] == "basico"


def test_get_permitido_nao_gera_linha_de_auditoria(client):
    """Só GET bloqueado é auditado — senão a auditoria vira um log de toda
    leitura feita durante a sessão, inútil de tão grande."""
    fid = _fazenda_id(client)
    _criar_membro_suporte(client, "total")
    token = _abrir_suporte_como(client, "membro.suporte", fid)["token"]

    client.get("/rebanho-rota-generica-qualquer", headers={"Authorization": f"Bearer {token}"})

    token_dono = _token_dono(client)
    acoes = client.get("/painel-cowdata/cofre/acoes", headers={"Authorization": f"Bearer {token_dono}"}).json()
    assert not any(a["metodo"] == "GET" and a["caminho"] == "/rebanho-rota-generica-qualquer" for a in acoes)
