"""
IDOR de confirmação: "id sequencial adivinhável + rota que carrega o registro
por id sem perguntar de quem ele é".

É o padrão comum aos achados críticos 22, 23, 24, 37 e 7 da auditoria
(docs/security-audit/achados.json). Todas as rotas aqui recebem o alvo do
CORPO ou da URL — `evento_id` é texto livre em POST /agenda/realizados,
`dieta_id`/`alimento_id` são inteiros pequenos e sequenciais, e as datas
D0/D7/D9/D11 do protocolo IATF são fixas, então colisão entre tenants é o caso
normal, não o excepcional. Sem filtrar por fazenda NA CONSULTA que carrega o
registro, a fazenda B confirma, encerra ou sequestra dado da fazenda A só
chutando o id.

O CowData não tem RLS no banco: o isolamento existe só no código da aplicação.
A trava de porta (fazenda/auth.py::exigir_fazenda_selecionada) garante que a
requisição diga EM QUAL fazenda acontece; estes testes são a trava de dentro —
dizer a fazenda certa não pode dar acesso ao registro da outra.

TOKEN DE VERDADE, nunca `dependency_overrides[get_fazenda_atual_id]`: é o
caminho token -> get_fazenda_atual_id -> get_fazenda_id_escrita -> consulta que
está em julgamento, e falsificar o meio dele já deixou furo passar antes (ver
tests/test_seguranca_p1_multitenant.py, que só usa override). Mesmo espírito de
tests/test_trava_fazenda_selecionada.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    Alimento, Animal, AplicacaoAgendada, ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda,
    Lida, LidaAplicacao, LidaLancamento, ParametroFazenda, ProtocoloCustomizadoAplicacao,
    ProtocoloCustomizadoLancamento, ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, Sanidade,
    TabelaNutricionalProduto, Usuario, UsuarioFazenda,
)
from fazenda.models.alimentacao import Dieta, DietaLancamento
from fazenda.models.planos import MODULOS_COMERCIAIS

# Data em que os dois tenants têm etapa prevista — a colisão de (data, dia)
# entre fazendas é o cenário real do achado 22, não uma coincidência forçada.
D0 = date(2026, 6, 1)


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes, um admin em cada, e um registro atacável da
    fazenda 1 para cada rota sob teste. A fazenda 2 recebe um espelho só onde
    o teste precisa provar que a rota continua funcionando para o dono."""
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

        # --- Achado 22: protocolo IATF (grupo por data_prevista + dia) ------
        lanc_iatf = ProtocoloIatfLancamento(nome_protocolo="Ovsynch", data_d0=D0, fazenda_id=1)
        s.add(lanc_iatf)
        s.commit()
        s.refresh(lanc_iatf)
        ap_iatf = ProtocoloIatfAplicacao(
            lancamento_id=lanc_iatf.id, numero_matriz="A100", dia=0, descricao="D0",
            data_prevista=D0, realizada=False, fazenda_id=1,
        )
        s.add(ap_iatf)

        # --- Achado 23a: protocolo customizado (grupo por lançamento + dia) -
        lanc_custom = ProtocoloCustomizadoLancamento(
            protocolo_id=1, nome_protocolo="Casqueamento", categoria="sanidade", dia_inicial=0,
            data_inicio=D0, ativo=True, fazenda_id=1,
        )
        s.add(lanc_custom)
        s.commit()
        s.refresh(lanc_custom)
        s.add(ProtocoloCustomizadoAplicacao(
            lancamento_id=lanc_custom.id, numero_matriz="A100", dia=0, descricao="Etapa 1",
            data_prevista=D0, realizada=False, fazenda_id=1,
        ))

        # --- Achado 23b: lida (confirma E consome estoque) ------------------
        lida = Lida(
            nome="Limpeza do bebedouro", modo="unico", dia_inicial=0, descricao_evento="Limpar",
            dar_baixa_estoque=True, insumo_padrao="Cloro", insumo_dose=2.0, insumo_unidade="l",
            ativo=True, fazenda_id=1,
        )
        s.add(lida)
        s.commit()
        s.refresh(lida)
        lanc_lida = LidaLancamento(
            lida_id=lida.id, nome_protocolo="Limpeza do bebedouro", modo="unico", dia_inicial=0,
            data_inicio=D0, ativo=True, fazenda_id=1,
        )
        s.add(lanc_lida)
        s.commit()
        s.refresh(lanc_lida)
        s.add(LidaAplicacao(
            lancamento_id=lanc_lida.id, dia=0, descricao="Limpar", insumo="Cloro", insumo_dose=2.0,
            insumo_unidade="l", data_prevista=D0, realizada=False, fazenda_id=1,
        ))
        # O estoque de cloro é da fazenda ATACANTE: se ela conseguisse
        # confirmar a lida alheia, gastaria o próprio insumo numa tarefa que
        # não é dela (o efeito colateral descrito no achado 23).
        estoque_cloro = Estoque(
            nome="Cloro", quantidade=100.0, unidade="l", fazenda_id=2, estocavel=True,
            estoque_inicializado=True,
        )
        s.add(estoque_cloro)

        # --- Achado 24: protocolo sanitário e aplicação agendada -----------
        lanc_san = ProtocoloSanitarioLancamento(
            protocolo_id=1, numero_matriz="A100", data_inicio=D0, fazenda_id=1,
        )
        etapa_san = ProtocoloSanitarioEtapa(
            protocolo_id=1, dia=0, produto="Vacina Alvo", dosagem=1.0, unidade="ml", via="IM",
            fazenda_id=1,
        )
        s.add(lanc_san)
        s.add(etapa_san)
        s.commit()
        s.refresh(lanc_san)
        s.refresh(etapa_san)
        ap_san = ProtocoloSanitarioAplicacao(
            lancamento_id=lanc_san.id, etapa_id=etapa_san.id, dia=0, numero_matriz="A100",
            data_prevista=D0, produto="Vacina Alvo", realizada=False, fazenda_id=1,
        )
        # Aplicação ÓRFÃ (fazenda_id NULL). A migração de backfill
        # (029227481e9e) documenta que linhas assim sobrevivem em instalação
        # com 2+ fazendas — e a checagem antiga (`not in (None, fazenda_id)`)
        # deixava qualquer tenant confirmá-las.
        ap_san_orfa = ProtocoloSanitarioAplicacao(
            lancamento_id=lanc_san.id, etapa_id=etapa_san.id, dia=1, numero_matriz="A101",
            data_prevista=D0, produto="Vacina Órfã", realizada=False, fazenda_id=None,
        )
        s.add(ap_san)
        s.add(ap_san_orfa)

        ag = AplicacaoAgendada(
            numero_matriz="A100", data=D0, produto="Vermífugo Alvo", dose=1.0, unidade="ml",
            aplicado=False, fazenda_id=1,
        )
        # Vacina pré-parto: a busca é por (numero_matriz, data, observação) —
        # texto livre, sem FK. As duas fazendas têm um animal "500", que é
        # exatamente como a colisão acontece na vida real.
        vacina_a = AplicacaoAgendada(
            numero_matriz="500", data=D0, produto="Vacina pré-parto A", observacao="Vacina pré-parto",
            aplicado=False, fazenda_id=1,
        )
        s.add(ag)
        s.add(vacina_a)

        # --- Achado 37: dieta ativa da fazenda 1 ---------------------------
        dieta = DietaLancamento(
            fazenda_id=1, lote=1, data_abertura=D0, leite_bezerros_kg_dia=120.0,
        )
        s.add(dieta)

        # --- Achado 7: parâmetro global de intervalo de BST ----------------
        s.add(ParametroFazenda(
            chave="intervalo_bst", fazenda_id=None, valor="12", tipo="int", grupo="bst",
            label="Intervalo BST",
        ))
        s.add(Sanidade(
            numero_matriz="A100", data_aplicacao=date(2026, 5, 1), produto="Lactotropin",
            atividade="BST", fazenda_id=1,
        ))

        # --- Ocorrências novas do mesmo padrão -----------------------------
        # Item de estoque da fazenda 1 já vinculado ao alimento dela: é o
        # vínculo que POST /alimentacao/alimentos "rouba" quando não confere
        # a posse dos `estoque_ids` recebidos.
        alimento_a = Alimento(nome="Silagem da Fazenda 1", fazenda_id=1)
        s.add(alimento_a)
        s.commit()
        s.refresh(alimento_a)
        estoque_a = Estoque(
            nome="Silagem", quantidade=1000.0, unidade="kg", fazenda_id=1,
            alimento_id=alimento_a.id, estocavel=True,
        )
        s.add(estoque_a)

        # Produto de tabela nutricional órfão (fazenda_id NULL) — é o que o
        # seed padrão da tabela cria; a checagem antiga de gerar-composicao
        # tolerava justamente o NULL.
        produto_orfao = TabelaNutricionalProduto(nome="Milho grão", ordem=0, fazenda_id=None)
        s.add(produto_orfao)

        # Dieta CSV + rebanho da fazenda 1, para o relatório de balanço.
        s.add(Animal(numero="A100", ativo=True, fazenda_id=1))
        s.add(Dieta(lote=1, ingrediente="Leite", quantidade=10.0, unidade="kg", fazenda_id=1))
        s.commit()

        ids.update(
            iatf_aplicacao=ap_iatf.id,
            custom_lancamento=lanc_custom.id,
            lida_lancamento=lanc_lida.id,
            estoque_cloro=estoque_cloro.id,
            sanitario_aplicacao=ap_san.id,
            sanitario_aplicacao_orfa=ap_san_orfa.id,
            aplicacao_agendada=ag.id,
            dieta=dieta.id,
            alimento_a=alimento_a.id,
            estoque_a=estoque_a.id,
            produto_orfao=produto_orfao.id,
        )

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int):
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


# ---------------------------------------------------------------------------
# Achado 22 — confirmar/desconfirmar protocolo IATF de outra fazenda
# ---------------------------------------------------------------------------
def test_iatf_de_outra_fazenda_nao_e_confirmado(ambiente):
    c, engine, ids = ambiente
    r = c.post("/agenda/realizados", json={"evento_id": f"protocolo_iatf_{D0.isoformat()}_0"}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        ap = s.get(ProtocoloIatfAplicacao, ids["iatf_aplicacao"])
        assert ap.realizada is False, (
            "a fazenda 2 confirmou o D0 do protocolo IATF da fazenda 1 — D0/D7/D9/D11 são datas "
            "fixas, então basta acertar a data para gravar Sanidade falsa no animal da vítima"
        )
    with Session(engine) as s:
        assert s.exec(select(Sanidade).where(Sanidade.fazenda_id == 2)).first() is None, (
            "a confirmação cruzada gravou Sanidade na fazenda atacante referenciando o animal alheio"
        )


def test_iatf_de_outra_fazenda_nao_e_desconfirmado(ambiente):
    """DELETE é o espelho do POST: reverter um tratamento CONFIRMADO da vítima
    apaga o registro de conformidade dela (achado 25, mesma família)."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        ap = s.get(ProtocoloIatfAplicacao, ids["iatf_aplicacao"])
        ap.realizada, ap.data_realizacao = True, D0
        s.add(ap)
        s.commit()
    r = c.delete(f"/agenda/realizados/protocolo_iatf_{D0.isoformat()}_0", headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloIatfAplicacao, ids["iatf_aplicacao"]).realizada is True, (
            "a fazenda 2 desfez a confirmação da fazenda 1"
        )


def test_iatf_da_propria_fazenda_continua_confirmando(ambiente):
    c, engine, ids = ambiente
    r = c.post("/agenda/realizados", json={"evento_id": f"protocolo_iatf_{D0.isoformat()}_0"}, headers=_cab(1))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloIatfAplicacao, ids["iatf_aplicacao"]).realizada is True


# ---------------------------------------------------------------------------
# Achado 23 — protocolo customizado e lida
# ---------------------------------------------------------------------------
def test_protocolo_customizado_de_outra_fazenda_nao_e_confirmado(ambiente):
    c, engine, ids = ambiente
    evento = f"protocolo_customizado_{ids['custom_lancamento']}_0"
    r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        ap = s.exec(select(ProtocoloCustomizadoAplicacao)).first()
        assert ap.realizada is False, (
            "a fazenda 2 confirmou o protocolo customizado da fazenda 1 só usando o lancamento_id "
            "(inteiro pequeno e sequencial) no corpo da requisição"
        )


def test_protocolo_customizado_da_propria_fazenda_continua_confirmando(ambiente):
    c, engine, ids = ambiente
    evento = f"protocolo_customizado_{ids['custom_lancamento']}_0"
    assert c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(1)).status_code == 200
    with Session(engine) as s:
        assert s.exec(select(ProtocoloCustomizadoAplicacao)).first().realizada is True


def test_lida_de_outra_fazenda_nao_e_confirmada_nem_gasta_estoque_do_atacante(ambiente):
    c, engine, ids = ambiente
    evento = f"lida_{ids['lida_lancamento']}_0"
    r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.exec(select(LidaAplicacao)).first().realizada is False, (
            "a fazenda 2 confirmou a lida da fazenda 1"
        )
        assert s.get(Estoque, ids["estoque_cloro"]).quantidade == 100.0, (
            "confirmar lida alheia consumiu o estoque da própria fazenda atacante — o efeito "
            "colateral descrito no achado 23"
        )


def test_lida_da_propria_fazenda_continua_confirmando(ambiente):
    c, engine, ids = ambiente
    evento = f"lida_{ids['lida_lancamento']}_0"
    assert c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(1)).status_code == 200
    with Session(engine) as s:
        assert s.exec(select(LidaAplicacao)).first().realizada is True


# ---------------------------------------------------------------------------
# Achado 24 — protocolo sanitário, aplicação agendada e vacina pré-parto
# ---------------------------------------------------------------------------
def test_protocolo_sanitario_de_outra_fazenda_nao_e_confirmado(ambiente):
    c, engine, ids = ambiente
    evento = f"protocolo_sanitario_{ids['sanitario_aplicacao']}"
    r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloSanitarioAplicacao, ids["sanitario_aplicacao"]).realizada is False, (
            "a fazenda 2 confirmou a aplicação sanitária da fazenda 1 só incrementando o id"
        )
        assert s.exec(select(Sanidade).where(Sanidade.fazenda_id == 2)).first() is None


def test_protocolo_sanitario_orfao_nao_e_confirmavel_por_ninguem(ambiente):
    """`fazenda_id=NULL` não é "de todo mundo". A checagem antiga era
    `aplicacao.fazenda_id not in (None, fazenda_id)`: o NULL passava por
    qualquer tenant."""
    c, engine, ids = ambiente
    evento = f"protocolo_sanitario_{ids['sanitario_aplicacao_orfa']}"
    for fazenda in (1, 2):
        r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(fazenda))
        assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloSanitarioAplicacao, ids["sanitario_aplicacao_orfa"]).realizada is False, (
            "uma aplicação órfã (fazenda_id NULL, resíduo real do backfill) foi confirmada — "
            "registro sem dono não pode virar registro de qualquer um"
        )


def test_protocolo_sanitario_da_propria_fazenda_continua_confirmando(ambiente):
    c, engine, ids = ambiente
    evento = f"protocolo_sanitario_{ids['sanitario_aplicacao']}"
    assert c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(1)).status_code == 200
    with Session(engine) as s:
        assert s.get(ProtocoloSanitarioAplicacao, ids["sanitario_aplicacao"]).realizada is True


def test_aplicacao_agendada_de_outra_fazenda_nao_e_confirmada(ambiente):
    c, engine, ids = ambiente
    evento = f"aplic_agendada_{ids['aplicacao_agendada']}"
    r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(AplicacaoAgendada, ids["aplicacao_agendada"]).aplicado is False, (
            "a fazenda 2 deu por aplicada a aplicação programada de um animal da fazenda 1"
        )


def test_aplicacao_agendada_da_propria_fazenda_continua_confirmando(ambiente):
    c, engine, ids = ambiente
    evento = f"aplic_agendada_{ids['aplicacao_agendada']}"
    assert c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(1)).status_code == 200
    with Session(engine) as s:
        assert s.get(AplicacaoAgendada, ids["aplicacao_agendada"]).aplicado is True


def test_vacina_pre_parto_nao_atravessa_por_colisao_de_numero_de_animal(ambiente):
    """O evento_id da vacina pré-parto é `numero_matriz` + data — texto livre,
    sem FK. Duas fazendas com uma vaca "500" é o normal."""
    c, engine, ids = ambiente
    evento = f"vacina_pre_parto_500_{D0.isoformat()}"
    r = c.post("/agenda/realizados", json={"evento_id": evento}, headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        vacina = s.exec(
            select(AplicacaoAgendada).where(AplicacaoAgendada.observacao == "Vacina pré-parto")
        ).first()
        assert vacina.aplicado is False, (
            "a fazenda 2 confirmou a vacina pré-parto da vaca 500 da fazenda 1 — o número do "
            "animal coincidir entre tenants não pode dar acesso ao registro"
        )


# ---------------------------------------------------------------------------
# Achado 37 — encerrar dieta de outra fazenda
# ---------------------------------------------------------------------------
def test_dieta_de_outra_fazenda_nao_e_encerrada(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/alimentacao/dietas/{ids['dieta']}/encerrar",
        json={"data_efetivo_encerramento": "2026-06-10"}, headers=_cab(2),
    )
    assert r.status_code == 404, (
        "404, nunca 403: responder 403 já confirma que aquele id existe. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )
    with Session(engine) as s:
        assert s.get(DietaLancamento, ids["dieta"]).data_efetivo_encerramento is None, (
            "a fazenda 2 encerrou a dieta ativa da fazenda 1, interrompendo a baixa automática "
            "de estoque e a apuração da vítima"
        )


def test_dieta_da_propria_fazenda_continua_encerrando(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/alimentacao/dietas/{ids['dieta']}/encerrar",
        json={"data_efetivo_encerramento": "2026-06-10"}, headers=_cab(1),
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Achado 7 — ajuste do intervalo de BST
# ---------------------------------------------------------------------------
def test_ajuste_de_bst_nao_enxerga_aplicacoes_da_outra_fazenda(ambiente):
    c, engine, ids = ambiente
    r = c.post(
        "/producao/bst/ajustar-proxima-aplicacao",
        json={"nova_data": "2026-07-01", "modo": "intervalo"}, headers=_cab(2),
    )
    assert r.status_code == 400, (
        "a fazenda 2 não tem NENHUMA aplicação de BST — se o cálculo passou, ele agregou a "
        f"aplicação da fazenda 1. Resposta: {r.status_code} {r.text[:200]}"
    )


def test_ajuste_de_bst_nao_sobrescreve_o_parametro_global(ambiente):
    """A escrita cai numa linha CLONADA para a fazenda; o padrão global
    (fazenda_id NULL, visto por toda fazenda sem override próprio) não muda."""
    c, engine, ids = ambiente
    r = c.post(
        "/producao/bst/ajustar-proxima-aplicacao",
        json={"nova_data": "2026-07-01", "modo": "intervalo"}, headers=_cab(1),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        linhas = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "intervalo_bst")).all()
        global_ = [l for l in linhas if l.fazenda_id is None]
        da_fazenda_1 = [l for l in linhas if l.fazenda_id == 1]
        assert len(da_fazenda_1) == 1, "deveria clonar a linha para a fazenda 1, não editar a global"
        assert global_[0].valor == "12", (
            "o intervalo de BST global mudou — toda fazenda-cliente sem override próprio passou a "
            "receber o parâmetro escolhido por outro tenant"
        )


# ---------------------------------------------------------------------------
# Ocorrências NOVAS do mesmo padrão, encontradas ao revisar os arquivos
# ---------------------------------------------------------------------------
def test_criar_alimento_nao_sequestra_item_de_estoque_de_outra_fazenda(ambiente):
    """`estoque_ids` vinha cru do corpo e era carregado com
    `session.get(Estoque, eid)`, sem posse: cadastrar um alimento informando
    os ids da vítima roubava o vínculo `Estoque.alimento_id` dela."""
    c, engine, ids = ambiente
    r = c.post(
        "/alimentacao/alimentos",
        json={"nome": "Silagem da Fazenda 2", "estoque_ids": [ids["estoque_a"]]},
        headers=_cab(2),
    )
    assert r.status_code == 201, r.text
    with Session(engine) as s:
        item = s.get(Estoque, ids["estoque_a"])
        assert item.fazenda_id == 1
        assert item.alimento_id == ids["alimento_a"], (
            "o item de estoque da fazenda 1 passou a apontar para o alimento da fazenda 2 — "
            "o vínculo foi roubado e a baixa automática de dieta da vítima quebra em silêncio"
        )


def test_gerar_composicao_de_produto_orfao_e_recusada(ambiente):
    """A checagem era invertida (`produto.fazenda_id is not None and ...`):
    todo produto de tabela nutricional sem fazenda ficava aberto a qualquer
    tenant."""
    c, engine, ids = ambiente
    r = c.post(
        f"/alimentacao/tabela-nutricional/produtos/{ids['produto_orfao']}/gerar-composicao",
        headers=_cab(2),
    )
    assert r.status_code == 404, (
        f"produto com fazenda_id NULL aceito como se fosse da fazenda 2. Resposta: {r.status_code}"
    )


def test_balanco_controle_x_entrega_nao_soma_dieta_de_outra_fazenda(ambiente):
    """As três consultas de "leite dos bezerros" eram as únicas do handler sem
    filtro de fazenda — somavam a dieta ativa de todas as fazendas-clientes."""
    c, engine, ids = ambiente
    r = c.get(
        "/producao/relatorio-controle-entrega?data_inicio=2026-06-01&data_fim=2026-06-30",
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["leite_bezerros_kg_dia"] == 0.0, (
        "os 120 kg/dia de leite de bezerro da dieta da fazenda 1 entraram no balanço da fazenda 2"
    )
