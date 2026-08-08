"""
Rescisão contratual (CLT) — camada de persistência/ciclo de vida
(`simulacao` → `fechada`) adicionada sobre `calcular_rescisao` (função pura,
já coberta em `test_folha_rh.py` — não re-testada aqui).

Cobre: criar/editar/excluir simulação (nenhum lançamento em Financeiro),
fechar único/detalhado (gera 1 ou N ContaGerencial), a cascata de dedução do
fechamento detalhado, inativação de pessoa, bloqueios de edição/exclusão/
fechamento duplo sobre registro já fechado, listagem (simulação + fechada +
legado) e isolamento multi-fazenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, RescisaoFuncionario
from fazenda.models.planos import MODULOS_COMERCIAIS


# ---------------------------------------------------------------------------
# Fixture — mesmo padrão de test_folha_rh.py (sqlite em memória + overrides).
# ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_pessoa(
    engine, fazenda_id: int | None = None, salario_base: float = 3000.0, data_admissao: date = date(2026, 1, 20),
    nome: str = "Fulano Rescisão",
) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=salario_base, data_admissao=data_admissao, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _payload_simulacao(pessoa_id: int, **overrides) -> dict:
    base = {
        "pessoa_id": pessoa_id,
        "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": "2026-07-20",
        "dias_ferias_vencidas": 0,
        "aviso_previo_trabalhado": False,
    }
    base.update(overrides)
    return base


# Cenário-base (mesmo de test_folha_rh.py: salário 3000, admitido 2026-01-20,
# desligado 2026-07-20, sem_justa_causa) — com o percentual seedado
# (0.3333, não exatamente 1/3), valor_total = 9755.27. Ver docstring de
# test_calcular_rescisao_sem_justa_causa em test_folha_rh.py para o detalhamento.
VALOR_TOTAL_BASE_SEM_JUSTA_CAUSA = 9755.27
VALOR_SALDO_SALARIO_BASE = 2000.0  # 3000/30*20, não depende do percentual seedado


# ---------------------------------------------------------------------------
# 1-2: criar simulação
# ---------------------------------------------------------------------------
def test_criar_simulacao_nao_gera_lancamento(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["status"] == "simulacao"
    assert dados["numero_lancamento_gerado"] is None

    with Session(engine) as s:
        assert s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Rescisão")).first() is None


def test_simulacao_sem_overrides_usa_valores_calculados(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_saldo_salario"] == VALOR_SALDO_SALARIO_BASE
    assert dados["valor_total"] == VALOR_TOTAL_BASE_SEM_JUSTA_CAUSA
    assert dados["valor_bruto"] == VALOR_TOTAL_BASE_SEM_JUSTA_CAUSA  # sem deduções, bruto == líquido


# ---------------------------------------------------------------------------
# 3: override + deduções
# ---------------------------------------------------------------------------
def test_simulacao_com_override_e_deducoes(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post(
        "/cadastro/rescisoes",
        json=_payload_simulacao(
            pessoa_id, valor_saldo_salario=2500.0, valor_inss=300.0, valor_ir=100.0, valor_vale_em_aberto=50.0,
        ),
    )
    assert r.status_code == 200, r.text
    dados = r.json()
    bruto_esperado = round(VALOR_TOTAL_BASE_SEM_JUSTA_CAUSA - VALOR_SALDO_SALARIO_BASE + 2500.0, 2)
    assert dados["valor_saldo_salario"] == 2500.0
    assert dados["valor_bruto"] == bruto_esperado
    assert dados["valor_total"] == round(bruto_esperado - 300.0 - 100.0 - 50.0, 2)


# ---------------------------------------------------------------------------
# 4: editar simulação (PUT)
# ---------------------------------------------------------------------------
def test_editar_simulacao_recalcula(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    # Muda o tipo de rescisão -> recalcula (pedido_demissao não tem aviso prévio nem multa de FGTS).
    r_put = c.put(f"/cadastro/rescisoes/{registro_id}", json=_payload_simulacao(pessoa_id, tipo_rescisao="pedido_demissao"))
    assert r_put.status_code == 200, r_put.text
    dados = r_put.json()
    assert dados["valor_aviso_previo"] == 0.0
    assert dados["valor_multa_fgts"] == 0.0
    assert dados["valor_total"] != VALOR_TOTAL_BASE_SEM_JUSTA_CAUSA


def test_editar_simulacao_com_override_vence_sugestao(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_put = c.put(
        f"/cadastro/rescisoes/{registro_id}", json=_payload_simulacao(pessoa_id, valor_saldo_salario=1234.56),
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["valor_saldo_salario"] == 1234.56


# ---------------------------------------------------------------------------
# 5-7: fechar (único / detalhado / pago)
# ---------------------------------------------------------------------------
def test_fechar_unico_gera_uma_conta(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r_fechar.status_code == 200, r_fechar.text
    dados = r_fechar.json()
    assert dados["status"] == "fechada"
    assert dados["forma_lancamento"] == "unico"
    assert dados["numero_lancamento_gerado"]

    with Session(engine) as s:
        contas = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).all()
        assert len(contas) == 1
        conta = contas[0]
        assert conta.parcela_total == 1
        assert conta.valor_total == dados["valor_total"]
        assert conta.tipo_documento == "Rescisão"
        assert conta.tipo == "despesa"


def test_fechar_detalhado_gera_n_contas_somando_o_liquido(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "detalhado"})
    assert r_fechar.status_code == 200, r_fechar.text
    dados = r_fechar.json()
    assert dados["forma_lancamento"] == "detalhado"

    with Session(engine) as s:
        contas = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).all()
        assert len(contas) > 1
        n = len(contas)
        assert all(c.parcela_total == n for c in contas)
        assert all(c.valor_total >= 0 for c in contas)
        assert round(sum(c.valor_total for c in contas), 2) == dados["valor_total"]


def test_fechar_pago_marca_valor_pago_e_data(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_fechar = c.post(
        f"/cadastro/rescisoes/{registro_id}/fechar",
        json={"forma_lancamento": "unico", "status_pagamento": "pago", "data_pagamento": "2026-07-25"},
    )
    assert r_fechar.status_code == 200, r_fechar.text
    dados = r_fechar.json()

    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == dados["numero_lancamento_gerado"])
        ).first()
        assert conta.valor_pago == dados["valor_total"]
        assert conta.data_pagamento == date(2026, 7, 25)


# ---------------------------------------------------------------------------
# 8: inativar_pessoa
# ---------------------------------------------------------------------------
def test_fechar_inativa_pessoa_quando_solicitado(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_fechar = c.post(
        f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico", "inativar_pessoa": True},
    )
    assert r_fechar.status_code == 200, r_fechar.text
    assert r_fechar.json()["inativou_pessoa"] is True

    with Session(engine) as s:
        assert s.get(Pessoa, pessoa_id).ativo is False


def test_fechar_sem_inativar_pessoa_mantem_ativa(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r_fechar.status_code == 200, r_fechar.text
    assert r_fechar.json()["inativou_pessoa"] is False

    with Session(engine) as s:
        assert s.get(Pessoa, pessoa_id).ativo is True


# ---------------------------------------------------------------------------
# 9-10: bloqueios sobre registro já fechado
# ---------------------------------------------------------------------------
def test_fechar_duas_vezes_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r1 = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r1.status_code == 200, r1.text

    r2 = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r2.status_code == 400, r2.text


def test_editar_ou_excluir_fechada_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]
    c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})

    r_put = c.put(f"/cadastro/rescisoes/{registro_id}", json=_payload_simulacao(pessoa_id, dias_ferias_vencidas=10))
    assert r_put.status_code == 400, r_put.text

    r_del = c.delete(f"/cadastro/rescisoes/{registro_id}")
    assert r_del.status_code == 400, r_del.text

    with Session(engine) as s:
        registro = s.get(RescisaoFuncionario, registro_id)
        assert registro is not None
        assert registro.status == "fechada"


# ---------------------------------------------------------------------------
# 11: excluir simulação
# ---------------------------------------------------------------------------
def test_excluir_simulacao_remove_registro_sem_conta(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    registro_id = r.json()["id"]

    r_del = c.delete(f"/cadastro/rescisoes/{registro_id}")
    assert r_del.status_code == 200, r_del.text

    with Session(engine) as s:
        assert s.get(RescisaoFuncionario, registro_id) is None
        assert s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Rescisão")).first() is None


# ---------------------------------------------------------------------------
# 12: valor líquido <= 0 bloqueia
# ---------------------------------------------------------------------------
def test_criar_com_total_negativo_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id, valor_vale_em_aberto=99999.0))
    assert r.status_code == 400, r.text


def test_fechar_com_total_zero_bloqueia(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    # Zera as 6 verbas via override e deduz exatamente o bruto -> líquido 0
    # (create permite total == 0; fechar não).
    payload = _payload_simulacao(
        pessoa_id,
        valor_saldo_salario=1000.0,
        valor_aviso_previo=0.0,
        valor_ferias_vencidas=0.0,
        valor_ferias_proporcionais=0.0,
        valor_decimo_terceiro_proporcional=0.0,
        valor_multa_fgts=0.0,
        valor_inss=1000.0,
    )
    r = c.post("/cadastro/rescisoes", json=payload)
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["valor_total"] == 0.0
    registro_id = dados["id"]

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r_fechar.status_code == 400, r_fechar.text


# ---------------------------------------------------------------------------
# 13: listagem — detalhe termina em "Valor líquido"; deduções negativas
# ---------------------------------------------------------------------------
def test_listagem_traz_simulacao_e_fechada_com_detalhe(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    r1 = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
    r2 = c.post(
        "/cadastro/rescisoes",
        json=_payload_simulacao(pessoa_id, data_desligamento="2026-08-05", valor_inss=100.0, valor_ir=50.0),
    )
    id_fechada = r2.json()["id"]
    c.post(f"/cadastro/rescisoes/{id_fechada}/fechar", json={"forma_lancamento": "unico"})

    r = c.get("/cadastro/rescisoes")
    assert r.status_code == 200, r.text
    itens = r.json()
    assert len(itens) >= 2

    por_id = {i["id"]: i for i in itens if not i.get("legado")}
    assert r1.json()["id"] in por_id
    assert id_fechada in por_id
    assert por_id[id_fechada]["status"] == "fechada"
    assert por_id[r1.json()["id"]]["status"] == "simulacao"

    for item in (por_id[r1.json()["id"]], por_id[id_fechada]):
        detalhe = item["detalhe"]
        assert detalhe[-1]["label"] == "Valor líquido"

    detalhe_fechada = por_id[id_fechada]["detalhe"]
    linhas_por_label = {d["label"]: d["valor"] for d in detalhe_fechada}
    assert linhas_por_label["INSS"] < 0
    assert linhas_por_label["IRRF"] < 0


# ---------------------------------------------------------------------------
# 14: rescisão legada (ContaGerencial sem RescisaoFuncionario)
# ---------------------------------------------------------------------------
def test_rescisao_legada_aparece_na_listagem_como_readonly(client):
    c, engine = client
    pessoa_id = _criar_pessoa(engine)

    with Session(engine) as s:
        conta = ContaGerencial(
            numero_lancamento="LC-2025-00001",
            descricao="Rescisão — Dispensa sem justa causa — Legado (2025-05-01)",
            data_vencimento=date(2025, 5, 1),
            data_competencia=date(2025, 5, 1),
            fornecedor_cliente="Legado",
            tipo_documento="Rescisão",
            valor_total=5000.0,
            parcela_num=1, parcela_total=1,
            tipo="despesa", origem="auto",
        )
        s.add(conta)
        s.commit()

    r = c.get("/cadastro/rescisoes")
    assert r.status_code == 200, r.text
    legados = [i for i in r.json() if i.get("legado")]
    assert len(legados) == 1
    item = legados[0]
    assert item["status"] == "fechada"
    assert item["forma_lancamento"] == "unico"
    assert item["detalhe"] == []
    assert item["numero_lancamento_gerado"] == "LC-2025-00001"


# ---------------------------------------------------------------------------
# 15: isolamento multi-fazenda
# ---------------------------------------------------------------------------
def test_isolamento_multi_fazenda(client):
    c, engine = client
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    _como_fazenda(1)
    pessoa_fazenda_1 = _criar_pessoa(engine, fazenda_id=1)

    r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_fazenda_1))
    assert r.status_code == 200, r.text
    registro_id = r.json()["id"]

    _como_fazenda(2)
    r_get = c.get("/cadastro/rescisoes")
    assert r_get.status_code == 200
    assert all(i.get("id") != registro_id for i in r_get.json() if not i.get("legado"))

    r_put = c.put(f"/cadastro/rescisoes/{registro_id}", json=_payload_simulacao(pessoa_fazenda_1))
    assert r_put.status_code == 404, r_put.text

    r_del = c.delete(f"/cadastro/rescisoes/{registro_id}")
    assert r_del.status_code == 404, r_del.text

    r_fechar = c.post(f"/cadastro/rescisoes/{registro_id}/fechar", json={"forma_lancamento": "unico"})
    assert r_fechar.status_code == 404, r_fechar.text

    # POST referenciando Pessoa da fazenda 1 enquanto age como fazenda 2 -> 404.
    r_post = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_fazenda_1))
    assert r_post.status_code == 404, r_post.text
