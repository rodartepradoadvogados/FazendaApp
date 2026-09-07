"""
DELETE de Férias / 13º salário quando a conta a pagar JÁ FOI BAIXADA no
Financeiro — o mesmo furo que o PR #725 fechou em `excluir_folha_pagamento`.

O risco é dinheiro sumindo do extrato: `FeriasFuncionario.status` /
`DecimoTerceiro.status` são o estado do RECIBO, e a baixa vive na
`ContaGerencial` gerada junto. Os dois divergem sempre que o recibo fica
"pendente" e alguém paga o lançamento direto em Financeiro > Contas a pagar
(fluxo normal). As duas exclusões só olhavam `registro.status` e apagavam a
conta sem ver `valor_pago` — levando embora do extrato um pagamento que
ACONTECEU.

Cobre, para cada rotina: a recusa (400 e o registro continua lá), a
contraprova (conta pendente → exclusão normal, conta some junto) e o
isolamento entre fazendas (conta homônima da vizinha nunca é lida nem
apagada), este último também para a guia de FGTS/DCTF, cuja busca da conta
passou a ter o recorte de fazenda dentro da consulta.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, DecimoTerceiro, Fazenda,
    FeriasFuncionario, GuiaFolhaEncargo, Pessoa,
)


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"


def _montar_app(engine, fazenda_id: int | None):
    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    if fazenda_id is not None:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
    return main.app


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    app = _montar_app(engine, None)
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


@pytest.fixture
def duas_fazendas():
    """Sessão logada na fazenda 1, com a fazenda 2 existindo ao lado."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um", ativa=True))
        s.add(Fazenda(id=2, nome="Fazenda Dois", ativa=True))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", ativo=True))
        s.commit()
    app = _montar_app(engine, 1)
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


def _pessoa(engine, nome: str = "Leomir Bonfim", fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3000.0, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _lancar_ferias(c, pessoa_id: int) -> dict:
    r = c.post("/cadastro/ferias", json={
        "pessoa_id": pessoa_id,
        "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2025-12-31",
        "dias_gozados": 30, "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _lancar_decimo(c, pessoa_id: int) -> dict:
    r = c.post("/cadastro/decimo-terceiro", json={
        "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _baixar_no_financeiro(engine, numero: str) -> int:
    """Alguém deu baixa no lançamento direto em Contas a pagar — o recibo do
    RH continua "pendente"."""
    with Session(engine) as s:
        conta = s.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
        ).first()
        assert conta is not None
        conta.data_pagamento = date(2026, 6, 29)
        conta.valor_pago = conta.valor_total
        s.add(conta)
        s.commit()
        return conta.id


class TestExcluirFeriasComContaJaPaga:
    def test_recusa_quando_a_conta_a_pagar_ja_foi_baixada_no_financeiro(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        ferias = _lancar_ferias(c, pessoa_id)
        assert ferias["status"] == "pendente"
        conta_id = _baixar_no_financeiro(engine, ferias["numero_lancamento_gerado"])

        r = c.delete(f"/cadastro/ferias/{ferias['id']}")
        assert r.status_code == 400, r.text
        assert "já foi baixada" in r.json()["detail"]

        # E o pagamento continua no extrato, junto com o registro de férias.
        with Session(engine) as s:
            assert s.get(ContaGerencial, conta_id) is not None
            assert s.get(FeriasFuncionario, ferias["id"]) is not None

    def test_contraprova_conta_nao_paga_continua_sendo_excluida_junto(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        ferias = _lancar_ferias(c, pessoa_id)
        numero = ferias["numero_lancamento_gerado"]

        assert c.delete(f"/cadastro/ferias/{ferias['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(FeriasFuncionario, ferias["id"]) is None
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first() is None


class TestExcluirDecimoTerceiroComContaJaPaga:
    def test_recusa_quando_a_conta_a_pagar_ja_foi_baixada_no_financeiro(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        decimo = _lancar_decimo(c, pessoa_id)
        assert decimo["status"] == "pendente"
        conta_id = _baixar_no_financeiro(engine, decimo["numero_lancamento_gerado"])

        r = c.delete(f"/cadastro/decimo-terceiro/{decimo['id']}")
        assert r.status_code == 400, r.text
        assert "já foi baixada" in r.json()["detail"]

        with Session(engine) as s:
            assert s.get(ContaGerencial, conta_id) is not None
            assert s.get(DecimoTerceiro, decimo["id"]) is not None

    def test_contraprova_conta_nao_paga_continua_sendo_excluida_junto(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        decimo = _lancar_decimo(c, pessoa_id)
        numero = decimo["numero_lancamento_gerado"]

        assert c.delete(f"/cadastro/decimo-terceiro/{decimo['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(DecimoTerceiro, decimo["id"]) is None
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first() is None


def _so_a_conta_paga_da_vizinha(engine, numero: str, descricao: str) -> int:
    """Deixa no banco UMA conta com esse `numero_lancamento`: a da fazenda 2,
    JÁ PAGA. A da fazenda 1 sai de cena (base migrada, número reaproveitado,
    lançamento próprio já excluído em Lançamentos) — é o arranjo em que a
    busca sem recorte de fazenda alcança e apaga o pagamento da VIZINHA."""
    with Session(engine) as s:
        minha = s.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == 1,
            )
        ).first()
        if minha is not None:
            s.delete(minha)
        conta = ContaGerencial(
            numero_lancamento=numero, descricao=descricao,
            data_vencimento=date(2026, 6, 29), fornecedor_cliente="Vizinho",
            tipo_documento="Férias", valor_total=900.0,
            parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
            data_pagamento=date(2026, 6, 29), valor_pago=900.0, fazenda_id=2,
        )
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


class TestIsolamentoEntreFazendas:
    def test_ferias_de_outra_fazenda_devolve_404(self, duas_fazendas):
        c, engine = duas_fazendas
        pessoa_vizinha = _pessoa(engine, nome="Vizinho", fazenda_id=2)
        with Session(engine) as s:
            registro = FeriasFuncionario(
                pessoa_id=pessoa_vizinha, salario_base=3000.0,
                periodo_aquisitivo_inicio=date(2025, 1, 1), periodo_aquisitivo_fim=date(2025, 12, 31),
                dias_direito=30, dias_gozados=30,
                data_inicio_gozo=date(2026, 7, 1), data_fim_gozo=date(2026, 7, 30),
                valor_ferias=3000.0, valor_terco_constitucional=1000.0, valor_abono=0.0,
                valor_total=4000.0, status="pendente", fazenda_id=2,
            )
            s.add(registro)
            s.commit()
            s.refresh(registro)
            registro_id = registro.id

        assert c.delete(f"/cadastro/ferias/{registro_id}").status_code == 404
        with Session(engine) as s:
            assert s.get(FeriasFuncionario, registro_id) is not None

    def test_conta_homonima_paga_da_vizinha_nao_bloqueia_nem_some(self, duas_fazendas):
        """Duas fazendas podem carregar o mesmo `numero_lancamento` (base
        migrada, importação). Sem o recorte de fazenda DENTRO da consulta, a
        exclusão das minhas férias alcançava a conta PAGA da vizinha e a
        apagava — dinheiro sumindo do extrato de outro tenant."""
        c, engine = duas_fazendas
        pessoa_id = _pessoa(engine, fazenda_id=1)
        ferias = _lancar_ferias(c, pessoa_id)
        numero = ferias["numero_lancamento_gerado"]
        conta_vizinha_id = _so_a_conta_paga_da_vizinha(engine, numero, "Férias da vizinha")

        assert c.delete(f"/cadastro/ferias/{ferias['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(FeriasFuncionario, ferias["id"]) is None
            # A conta paga da vizinha ficou onde estava.
            restantes = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).all()
            assert [conta.fazenda_id for conta in restantes] == [2]
            assert s.get(ContaGerencial, conta_vizinha_id).valor_pago == 900.0

    def test_guia_fgts_conta_homonima_paga_da_vizinha_nao_bloqueia_nem_some(self, duas_fazendas):
        """`_conta_da_guia` buscava só por `numero_lancamento`: excluir a guia
        da fazenda 1 recusava por um pagamento que não é dela — ou apagava a
        conta paga da fazenda 2, que era quem carregava aquele número."""
        c, engine = duas_fazendas
        r = c.post("/cadastro/folha-pagamento/guias", json={
            "tipo": "fgts", "competencia": "2026-07", "valor_principal": 1240.0,
            "data_vencimento": "2026-08-20",
        })
        assert r.status_code == 200, r.text
        guia = r.json()
        numero = guia["numero_lancamento"]
        conta_vizinha_id = _so_a_conta_paga_da_vizinha(engine, numero, "Guia da vizinha")

        assert c.delete(f"/cadastro/folha-pagamento/guias/{guia['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(GuiaFolhaEncargo, guia["id"]) is None
            restantes = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).all()
            assert [conta.fazenda_id for conta in restantes] == [2]
            assert s.get(ContaGerencial, conta_vizinha_id).valor_pago == 900.0
