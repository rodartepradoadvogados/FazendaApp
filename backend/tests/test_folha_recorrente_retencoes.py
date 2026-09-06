"""
Bugs de dinheiro na Folha de Pagamento (correções autorizadas pelo dono):

BUG 1 — `_gerar_folha_recorrente` copiava do lançamento-modelo apenas
        `valor_bruto`, `descontos`, `observacao` e `centro_custo`. INSS, IR,
        FGTS/DCTF, `conta_corrente_id` e `dia_vencimento` ficavam de fora, e o
        líquido era calculado SEM as retenções — toda competência gerada
        automaticamente nascia com retenção zero e líquido inflado, no banco
        e na conta a pagar (não só na tela).

BUG 2 — `_detalhe_folha` decidia mostrar a linha de INSS/IR pelo PERCENTUAL.
        Quem digita o valor direto no formulário (`inssManual`) grava
        `valor_inss=300, percentual_inss=0`: o líquido caía, mas o recibo não
        mostrava desconto nenhum e não fechava.

Cobre também a regra de segurança do reprocessamento das folhas pendentes já
geradas erradas: folha `status="pago"` é histórico financeiro e NUNCA é
tocada (mesmo padrão de `listar_folha_pagamento`/`_remover_folha_duplicada`).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import ContaCorrente, ContaGerencial, FolhaPagamento, Pessoa


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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


def _pessoa(c) -> int:
    return c.post("/cadastro/pessoas", json={"nome": "Funcionário Retenção", "tipos": ["Funcionário"]}).json()["id"]


def _conta_corrente(engine) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _competencia_anterior(competencia: str, meses: int) -> str:
    ano, mes = (int(x) for x in competencia.split("-"))
    for _ in range(meses):
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return f"{ano:04d}-{mes:02d}"


def _conta_de(engine, numero: str) -> ContaGerencial:
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()


# ---------------------------------------------------------------------------
# BUG 1 — geração por recorrência
# ---------------------------------------------------------------------------
class TestRecorrenciaCopiaRetencoes:
    """Bruto 3000, descontos 200, INSS 240 (8%), IR 150 (5%) → líquido 2410.
    Com o bug, o líquido nascia 2800 (3000 − 200) e as retenções, zeradas."""

    def _modelo(self, c, engine, competencia: str, conta_id: int) -> dict:
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": _pessoa(c), "competencia": competencia, "valor_bruto": 3000.0,
            "descontos": 200.0,
            "percentual_inss": 8.0, "valor_inss": 240.0,
            "percentual_ir": 5.0, "valor_ir": 150.0,
            "percentual_fgts": 8.0, "percentual_dctf": 2.0,
            "recorrente": True, "dia_vencimento": 15,
            "conta_corrente_id": conta_id,
            "observacao": "Salário mensal",
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_gerada_copia_inss_ir_e_desconta_no_liquido(self, client):
        c, engine = client
        atual = date.today().strftime("%Y-%m")
        conta_id = _conta_corrente(engine)
        modelo = self._modelo(c, engine, _competencia_anterior(atual, 3), conta_id)
        assert modelo["valor_liquido"] == 2410.0  # sanidade: o modelo já estava certo

        gerados = [r for r in c.get("/cadastro/folha-pagamento").json() if r["origem_recorrencia_id"]]
        assert len(gerados) == 3
        for g in gerados:
            assert g["percentual_inss"] == 8.0
            assert g["valor_inss"] == 240.0
            assert g["percentual_ir"] == 5.0
            assert g["valor_ir"] == 150.0
            # O bug entregava 2800.0 aqui.
            assert g["valor_liquido"] == 2410.0

    def test_gerada_copia_fgts_dctf_conta_e_dia_vencimento(self, client):
        c, engine = client
        atual = date.today().strftime("%Y-%m")
        conta_id = _conta_corrente(engine)
        self._modelo(c, engine, _competencia_anterior(atual, 2), conta_id)

        gerados = [r for r in c.get("/cadastro/folha-pagamento").json() if r["origem_recorrencia_id"]]
        assert gerados
        for g in gerados:
            assert g["percentual_fgts"] == 8.0
            assert g["valor_fgts"] == 240.0  # 8% de 3000 (via _calcular_encargo_projetado)
            assert g["percentual_dctf"] == 2.0
            assert g["valor_dctf"] == 60.0
            assert g["conta_corrente_id"] == conta_id
            assert g["dia_vencimento"] == 15

    def test_conta_a_pagar_gerada_usa_o_liquido_com_retencoes(self, client):
        c, engine = client
        atual = date.today().strftime("%Y-%m")
        conta_id = _conta_corrente(engine)
        self._modelo(c, engine, _competencia_anterior(atual, 2), conta_id)

        gerados = [r for r in c.get("/cadastro/folha-pagamento").json() if r["origem_recorrencia_id"]]
        assert gerados
        for g in gerados:
            conta = _conta_de(engine, g["numero_lancamento_gerado"])
            assert conta is not None
            assert conta.valor_total == 2410.0  # com o bug: 2800.0
            assert conta.data_vencimento.day == 15  # dia_vencimento do modelo
            # conta_bancaria é o campo que os relatórios gerenciais filtram.
            assert conta.conta_bancaria == "Banco do Brasil · Agência 0001-2 · Conta corrente 12345-6"

    def test_observacao_e_centro_custo_continuam_sendo_copiados(self, client):
        """Guarda-corpo: o que a geração já copiava certo não pode regredir."""
        c, engine = client
        atual = date.today().strftime("%Y-%m")
        conta_id = _conta_corrente(engine)
        self._modelo(c, engine, _competencia_anterior(atual, 1), conta_id)
        gerados = [r for r in c.get("/cadastro/folha-pagamento").json() if r["origem_recorrencia_id"]]
        assert gerados
        for g in gerados:
            assert g["observacao"] == "Salário mensal"
            assert g["centro_custo"] == "Pecuária Leiteira"
            assert g["status"] == "pendente"
            assert g["recorrente"] is False  # a gerada nunca vira um novo modelo


# ---------------------------------------------------------------------------
# BUG 1 — reprocessamento das folhas PENDENTES já geradas erradas
# ---------------------------------------------------------------------------
class TestReprocessamentoDasJaGeradas:
    def _cenario_bug(self, c, engine, status: str) -> tuple[int, str]:
        """Reproduz no banco o estado que a geração buggada deixava: folha da
        competência seguinte com retenções zeradas e líquido = bruto − descontos
        (sem INSS/IR), com a conta a pagar no mesmo valor inflado."""
        atual = date.today().strftime("%Y-%m")
        anterior = _competencia_anterior(atual, 1)
        pessoa_id = _pessoa(c)
        modelo = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": anterior, "valor_bruto": 3000.0, "descontos": 200.0,
            "percentual_inss": 8.0, "valor_inss": 240.0, "percentual_ir": 5.0, "valor_ir": 150.0,
            "recorrente": True, "dia_vencimento": 15,
        }).json()

        ano, mes = (int(x) for x in atual.split("-"))
        with Session(engine) as s:
            pessoa = s.get(Pessoa, pessoa_id)
            errada = FolhaPagamento(
                pessoa_id=pessoa_id, competencia=atual, valor_bruto=3000.0, descontos=200.0,
                valor_vale=0.0, valor_liquido=2800.0, status=status,
                observacao=modelo["observacao"], origem_recorrencia_id=modelo["id"],
                numero_lancamento_gerado="LC-BUG-1",
            )
            s.add(errada)
            s.add(ContaGerencial(
                numero_lancamento="LC-BUG-1",
                descricao=f"Folha de pagamento — {pessoa.nome} ({atual})",
                data_vencimento=date(ano, mes, 15), data_competencia=date(ano, mes, 1),
                fornecedor_cliente=pessoa.nome, tipo_documento="Folha de pagamento",
                centro_custo="Pecuária Leiteira", valor_total=2800.0,
                parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
                data_pagamento=date(ano, mes, 15) if status == "pago" else None,
                valor_pago=2800.0 if status == "pago" else None,
            ))
            s.commit()
            s.refresh(errada)
            return errada.id, atual

    def test_pendente_gerada_errada_e_corrigida_na_listagem(self, client):
        c, engine = client
        registro_id, competencia = self._cenario_bug(c, engine, status="pendente")

        listagem = c.get("/cadastro/folha-pagamento").json()
        corrigida = next(r for r in listagem if r["id"] == registro_id)
        assert corrigida["valor_inss"] == 240.0
        assert corrigida["percentual_inss"] == 8.0
        assert corrigida["valor_ir"] == 150.0
        assert corrigida["percentual_ir"] == 5.0
        assert corrigida["valor_liquido"] == 2410.0
        assert corrigida["competencia"] == competencia

        # A conta a pagar vinculada também precisa cair — é ela que o dono paga.
        assert _conta_de(engine, "LC-BUG-1").valor_total == 2410.0

    def test_folha_ja_paga_nunca_e_alterada(self, client):
        """Corrigir o líquido de uma folha PAGA mudaria histórico financeiro —
        o reprocessamento é restrito a status != "pago"."""
        c, engine = client
        registro_id, _ = self._cenario_bug(c, engine, status="pago")

        listagem = c.get("/cadastro/folha-pagamento").json()
        paga = next(r for r in listagem if r["id"] == registro_id)
        assert paga["valor_liquido"] == 2800.0
        assert paga["valor_inss"] == 0.0
        assert paga["valor_ir"] == 0.0
        assert _conta_de(engine, "LC-BUG-1").valor_total == 2800.0

    def test_reprocessamento_e_idempotente(self, client):
        c, engine = client
        registro_id, _ = self._cenario_bug(c, engine, status="pendente")
        c.get("/cadastro/folha-pagamento")
        primeira = next(r for r in c.get("/cadastro/folha-pagamento").json() if r["id"] == registro_id)
        segunda = next(r for r in c.get("/cadastro/folha-pagamento").json() if r["id"] == registro_id)
        assert primeira["valor_liquido"] == segunda["valor_liquido"] == 2410.0
        assert _conta_de(engine, "LC-BUG-1").valor_total == 2410.0

    def test_nao_sobrescreve_folha_pendente_editada_a_mao(self, client):
        """O reprocessamento só age sobre a assinatura EXATA do bug (líquido ==
        bruto − descontos − vale e retenções zeradas, com bruto/descontos ainda
        iguais aos do modelo). Uma folha que o usuário editou fica como está."""
        c, engine = client
        registro_id, _ = self._cenario_bug(c, engine, status="pendente")
        with Session(engine) as s:
            registro = s.get(FolhaPagamento, registro_id)
            registro.valor_bruto = 2500.0  # bruto editado à mão (mês com falta)
            registro.valor_liquido = 2300.0
            s.add(registro)
            s.commit()

        editada = next(r for r in c.get("/cadastro/folha-pagamento").json() if r["id"] == registro_id)
        assert editada["valor_bruto"] == 2500.0
        assert editada["valor_liquido"] == 2300.0
        assert editada["valor_inss"] == 0.0


# ---------------------------------------------------------------------------
# BUG 2 — discriminação (recibo) com INSS/IR digitados como valor
# ---------------------------------------------------------------------------
class TestDetalheInssIrPorValor:
    def _detalhe(self, c, **retencoes) -> list[dict]:
        pessoa_id = _pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0, **retencoes,
        })
        assert r.status_code == 200, r.text
        registro = next(x for x in c.get("/cadastro/folha-pagamento").json() if x["id"] == r.json()["id"])
        return registro["detalhe"]

    def test_valor_manual_sem_percentual_ainda_aparece_no_recibo(self, client):
        c, _ = client
        # É exatamente o que o campo `inssManual` do formulário grava.
        detalhe = self._detalhe(c, valor_inss=300.0, percentual_inss=0.0, valor_ir=120.0, percentual_ir=0.0)
        por_label = {d["label"]: d["valor"] for d in detalhe}
        assert por_label["INSS"] == -300.0
        assert por_label["IR"] == -120.0

    def test_recibo_fecha_com_valor_manual(self, client):
        """A soma das linhas discriminadas tem que dar o líquido — era o que
        não fechava: o líquido descontava 420, a discriminação, nada."""
        c, _ = client
        detalhe = self._detalhe(c, valor_inss=300.0, percentual_inss=0.0, valor_ir=120.0, percentual_ir=0.0)
        assert detalhe[-1]["label"] == "Valor líquido"
        liquido = detalhe[-1]["valor"]
        assert liquido == 2580.0
        assert round(sum(d["valor"] for d in detalhe[:-1]), 2) == liquido

    def test_percentual_informado_continua_na_referencia_da_linha(self, client):
        c, _ = client
        detalhe = self._detalhe(c, valor_inss=240.0, percentual_inss=8.0, valor_ir=150.0, percentual_ir=5.0)
        labels = [d["label"] for d in detalhe]
        assert "INSS (8%)" in labels
        assert "IR (5%)" in labels

    def test_sem_retencao_nenhuma_linha_e_emitida(self, client):
        c, _ = client
        detalhe = self._detalhe(c)
        labels = [d["label"] for d in detalhe]
        assert not any(l.startswith("INSS") for l in labels)
        assert not any(l.startswith("IR") for l in labels)

    def test_nao_inventa_percentual_a_partir_do_valor(self, client):
        c, _ = client
        detalhe = self._detalhe(c, valor_inss=300.0, percentual_inss=0.0)
        assert "INSS" in [d["label"] for d in detalhe]
        assert not any("%" in d["label"] for d in detalhe)


# ---------------------------------------------------------------------------
# BUG 1 — a GERAÇÃO em si, sem o self-heal por trás
# ---------------------------------------------------------------------------
class TestGeracaoIsoladaDoSelfHeal:
    """
    `_corrigir_folha_gerada_sem_retencao` conserta na listagem o que a geração
    escreveu errado — e por isso mascara uma regressão da própria geração nos
    testes de ponta a ponta. Aqui a geração é chamada DIRETO e o que ela grava
    é conferido no banco, antes de qualquer self-heal: se `_gerar_folha_
    recorrente` voltar a esquecer as retenções, é aqui que estoura.
    """

    def test_gerar_folha_recorrente_grava_retencoes_e_liquido_certos(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro.rh_folha import _gerar_folha_recorrente

        atual = date.today().strftime("%Y-%m")
        anterior = _competencia_anterior(atual, 1)
        conta_id = _conta_corrente(engine)
        modelo = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": _pessoa(c), "competencia": anterior, "valor_bruto": 3000.0, "descontos": 200.0,
            "percentual_inss": 8.0, "valor_inss": 240.0, "percentual_ir": 5.0, "valor_ir": 150.0,
            "percentual_fgts": 8.0, "percentual_dctf": 2.0,
            "recorrente": True, "dia_vencimento": 15, "conta_corrente_id": conta_id,
        }).json()

        with Session(engine) as s:
            # Apaga o que a própria criação já tiver gerado, para a chamada
            # abaixo ser a única responsável pela competência atual.
            for folha in s.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == atual)).all():
                s.delete(folha)
            s.commit()
            _gerar_folha_recorrente(s, modelo["fazenda_id"])

        with Session(engine) as s:
            gerada = s.exec(select(FolhaPagamento).where(FolhaPagamento.competencia == atual)).first()
            assert gerada is not None
            assert gerada.origem_recorrencia_id == modelo["id"]
            assert (gerada.percentual_inss, gerada.valor_inss) == (8.0, 240.0)
            assert (gerada.percentual_ir, gerada.valor_ir) == (5.0, 150.0)
            assert gerada.valor_liquido == 2410.0  # com o bug: 2800.0
            assert gerada.valor_fgts == 240.0
            assert gerada.valor_dctf == 60.0
            assert gerada.conta_corrente_id == conta_id
            assert gerada.dia_vencimento == 15
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == gerada.numero_lancamento_gerado
            )).first()
            assert conta.valor_total == 2410.0
            assert conta.conta_bancaria == "Banco do Brasil · Agência 0001-2 · Conta corrente 12345-6"
