"""
Holerite discriminado — as quatro colunas do recibo de papel (Descrição ·
Referência · Vencimentos · Descontos) e, principalmente, a IDENTIDADE do
desconto de vale.

O que estava errado e estes testes travam:

1. `_detalhe_folha` devolvia `list[{label, valor}]` e montava a linha do vale
   como texto (`f"Vale (parcela {k}/{n})"`) com o `ValeFuncionario` em mãos —
   data do vale, observação, forma de pagamento, nº do lançamento e a nota
   fiscal de origem eram descartados. Sete vales na mesma competência viravam
   sete linhas indistinguíveis, e a única forma de a tela adivinhar "o que é
   vale" era um regex no rótulo em português.
2. A tela de Contas (`folha-pagamento-unificada`) calculava o discriminado e o
   jogava fora ao montar o dict — por isso clicar num nome não abria nada.
3. Nenhum valor podia dizer de onde veio: não havia coluna de referência.

Cobre também o isolamento entre fazendas do carregamento em lote das parcelas
(`_contexto_discriminacao`), que é o ponto onde um vale de outra fazenda
poderia entrar num holerite.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import (
    ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento, Pessoa,
    ValeFuncionario, ValeParcela,
)
from fazenda.rules import holerite


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


def _pessoa(engine, nome: str = "Leomir Bonfim", admissao: date | None = None) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3200.0, data_admissao=admissao)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _conta_corrente(engine) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _linhas(c, pessoa_id: int, competencia: str) -> list[dict]:
    resposta = c.get("/cadastro/folha-pagamento")
    assert resposta.status_code == 200, resposta.text
    registros = resposta.json()
    registro = next(r for r in registros if r["pessoa_id"] == pessoa_id and r["competencia"] == competencia)
    return registro["detalhe"]


def _por_tipo(detalhe: list[dict], tipo: str) -> list[dict]:
    return [d for d in detalhe if d["tipo"] == tipo]


# ---------------------------------------------------------------------------
# A linha do vale deixa de ser texto e passa a ser um vale
# ---------------------------------------------------------------------------
class TestIdentidadeDoValeNaLinha:
    def test_cada_linha_de_vale_traz_o_proprio_vale_id(self, client):
        """Dois vales de MESMO VALOR na mesma competência — o caso em que a
        tela antiga terminava num palpite, porque as duas linhas eram a mesma
        string e o valor não desempatava."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        for dia, obs in ((10, "mercado"), (21, "farmácia")):
            r = c.post("/cadastro/vales", json={
                "pessoa_id": pessoa_id, "valor_total": 320.0, "forma_pagamento": "pix",
                "data_pagamento": f"2026-06-{dia:02d}", "parcelas": 1, "competencia_inicio": "2026-07",
                "observacao": obs, "conta_corrente_id": conta_id,
            })
            assert r.status_code == 200, r.text
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })

        vales = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "vale")
        assert len(vales) == 2
        ids = {v["origem"]["vale_id"] for v in vales}
        assert len(ids) == 2, "duas parcelas de mesmo valor precisam apontar para vales diferentes"
        # E o humano distingue as duas sem abrir nada: a observação virou a
        # descrição e a data do vale virou a referência.
        assert {v["descricao"] for v in vales} == {"Vale — mercado", "Vale — farmácia"}
        assert {v["referencia"] for v in vales} == {
            "Parcela única · vale de 10/06/2026", "Parcela única · vale de 21/06/2026",
        }

    def test_referencia_diz_qual_parcela_de_quantas(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 900.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-06-12", "parcelas": 3, "competencia_inicio": "2026-07",
            "observacao": "adiantamento", "conta_corrente_id": conta_id,
        })
        for competencia in ("2026-07", "2026-08", "2026-09"):
            c.post("/cadastro/folha-pagamento", json={
                "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": 3200.0,
            })

        referencias = [
            _por_tipo(_linhas(c, pessoa_id, comp), "vale")[0]["referencia"]
            for comp in ("2026-07", "2026-08", "2026-09")
        ]
        assert referencias == [
            "Parcela 1 de 3 · vale de 12/06/2026",
            "Parcela 2 de 3 · vale de 12/06/2026",
            "Parcela 3 de 3 · vale de 12/06/2026",
        ]

    def test_origem_traz_o_caminho_ate_o_extrato(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 400.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-05", "parcelas": 1, "competencia_inicio": "2026-07",
            "observacao": "combustível", "numero_documento_pagamento": "PIX-9931",
            "conta_corrente_id": conta_id,
        })
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })

        origem = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "vale")[0]["origem"]
        assert origem["data_pagamento"] == "2026-06-05"
        assert origem["forma_pagamento"] == "pix"
        assert origem["observacao"] == "combustível"
        assert origem["numero_documento_pagamento"] == "PIX-9931"
        assert origem["valor_total"] == 400.0
        # Houve saída de caixa: existe lançamento no extrato para onde ir.
        assert origem["sem_saida_de_caixa"] is False
        assert origem["numero_lancamento_gerado"]

    def test_desconto_integral_em_folha_explica_a_ausencia_do_extrato(self, client):
        """`numero_lancamento_gerado` é NULL POR DESENHO aqui (não houve saída
        de caixa) — a linha precisa dizer isso em vez de a tela mostrar um
        link quebrado ou sumir com a informação."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 250.0, "forma_pagamento": "desconto_integral_folha",
            "data_pagamento": "2026-06-20", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })

        origem = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "vale")[0]["origem"]
        assert origem["sem_saida_de_caixa"] is True
        assert origem["numero_lancamento_gerado"] is None


# ---------------------------------------------------------------------------
# Nenhum valor sem referência
# ---------------------------------------------------------------------------
class TestColunaReferencia:
    def test_toda_linha_de_provento_ou_desconto_tem_referencia(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 100.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-06-02", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
            "descontos": 40.0, "percentual_inss": 7.78, "valor_inss": 248.96,
        })

        detalhe = _linhas(c, pessoa_id, "2026-07")
        for d in detalhe:
            if d["tipo"] == "liquido":
                continue
            assert d["referencia"], f"linha sem referência: {d['descricao']}"
            assert d["descricao"]

    def test_retencao_confere_contra_o_bruto_da_competencia(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 7.78, "valor_inss": 155.6,
        })
        linha = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "inss")[0]
        assert linha["referencia"] == "7,78% sobre R$ 2.000,00"
        assert linha["origem"]["confere"] is True
        assert linha["origem"]["base"] == 2000.0

    def test_retencao_ajustada_a_mao_declara_a_divergencia(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 7.78, "valor_inss": 200.0,
        })
        linha = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "inss")[0]
        assert "ajustado à mão" in linha["referencia"]
        assert linha["origem"]["confere"] is False

    def test_retencao_sem_percentual_nao_inventa_percentual(self, client):
        """O formulário permite digitar o valor direto (`inssManual`). Sem base
        declarada, qualquer percentual aqui seria inventado."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 0.0, "valor_inss": 155.68,
        })
        linha = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "inss")[0]
        assert linha["referencia"] == "Valor informado, sem percentual"
        assert linha["origem"]["percentual"] is None
        assert "%" not in linha["label"]

    def test_referencia_do_bruto_e_mensal_fora_do_mes_de_admissao(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine, admissao=date(2024, 3, 12))
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })
        assert _por_tipo(_linhas(c, pessoa_id, "2026-07"), "bruto")[0]["referencia"] == "Mensal"

    def test_no_mes_de_admissao_a_referencia_diz_o_fato_gravado(self, client):
        """Nunca "30 Dias" (o divisor usado não está gravado em lugar nenhum) —
        só o fato que o cadastro sustenta: a data de admissão."""
        c, engine = client
        pessoa_id = _pessoa(engine, admissao=date(2026, 7, 12))
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2064.5,
        })
        referencia = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "bruto")[0]["referencia"]
        assert referencia == "Admissão em 12/07 · 20 de 31 dias do mês"

    def test_outros_descontos_declara_que_nao_tem_itemizacao(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0, "descontos": 340.0,
        })
        linha = _por_tipo(_linhas(c, pessoa_id, "2026-07"), "outros")[0]
        assert linha["referencia"] == "Valor único, sem detalhamento gravado"


# ---------------------------------------------------------------------------
# Totais das duas colunas e o rodapé honesto
# ---------------------------------------------------------------------------
class TestTotaisEBases:
    def test_as_duas_colunas_fecham_com_o_liquido_gravado(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        v = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-06-02", "parcelas": 1, "competencia_inicio": "2026-07",
            "conta_corrente_id": _conta_corrente(engine),
        })
        assert v.status_code == 200, v.text
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
            "descontos": 40.0, "percentual_inss": 7.78, "valor_inss": 248.96,
        })
        assert r.status_code == 200, r.text

        registro = next(
            x for x in c.get("/cadastro/folha-pagamento").json()
            if x["pessoa_id"] == pessoa_id and x["competencia"] == "2026-07"
        )
        totais = registro["totais"]
        assert totais["total_proventos"] == 3200.0
        assert totais["total_descontos"] == round(300.0 + 40.0 + 248.96, 2)
        assert totais["liquido"] == registro["valor_liquido"]
        assert totais["liquido_negativo"] is False

    def test_descontos_maiores_que_vencimentos_nao_produzem_um_liquido_valido(self, client):
        """A conta do print do dono: bruto 3.200,00, sete vales somando
        4.880,54. "Líquido −1.680,54" tem aparência de resultado válido; o que
        existe de fato é um excedente, e o recibo não pode ser emitido."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        with Session(engine) as s:
            vale = ValeFuncionario(
                pessoa_id=pessoa_id, valor_total=4880.54, forma_pagamento="dinheiro",
                data_pagamento=date(2026, 6, 29), parcelas=1, competencia_inicio="2026-07",
            )
            s.add(vale)
            s.commit()
            s.refresh(vale)
            s.add(ValeParcela(vale_id=vale.id, pessoa_id=pessoa_id, competencia="2026-07", valor=4880.54))
            folha = FolhaPagamento(
                pessoa_id=pessoa_id, competencia="2026-07", valor_bruto=3200.0,
                valor_vale=4880.54, valor_liquido=-1680.54,
            )
            s.add(folha)
            s.commit()

        registro = next(
            x for x in c.get("/cadastro/folha-pagamento").json()
            if x["pessoa_id"] == pessoa_id and x["competencia"] == "2026-07"
        )
        assert registro["totais"]["liquido_negativo"] is True
        assert registro["totais"]["excedente"] == 1680.54

    def test_rodape_so_mostra_a_base_que_o_banco_sustenta(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2100.0,
            "percentual_inss": 7.78, "valor_inss": 163.38, "percentual_fgts": 8.0,
        })
        registro = next(
            x for x in c.get("/cadastro/folha-pagamento").json()
            if x["pessoa_id"] == pessoa_id and x["competencia"] == "2026-07"
        )
        bases = registro["bases"]
        assert bases["salario_base"] == 2100.0  # do lançamento, nunca de Pessoa.salario_base
        assert bases["base_inss"] == 2100.0
        assert bases["base_ir"] is None  # sem IR lançado, não existe base a mostrar
        assert bases["fgts_projetado"] == 168.0

    def test_sem_percentual_a_base_da_retencao_fica_de_fora_do_rodape(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 0.0, "valor_inss": 155.68,
        })
        registro = next(
            x for x in c.get("/cadastro/folha-pagamento").json()
            if x["pessoa_id"] == pessoa_id and x["competencia"] == "2026-07"
        )
        assert registro["bases"]["base_inss"] is None


# ---------------------------------------------------------------------------
# A tela de Contas deixa de ser a mesma tabela sem o clique
# ---------------------------------------------------------------------------
class TestLedgerUnificadoLevaODiscriminado:
    def test_linha_de_funcionario_carrega_o_holerite_inteiro(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-08", "parcelas": 2, "competencia_inicio": "2026-07",
            "observacao": "mercado", "conta_corrente_id": _conta_corrente(engine),
        })
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })

        linha = next(
            l for l in c.get("/cadastro/folha-pagamento-unificada").json()
            if l["tipo"] == "funcionario" and l["pessoa_id"] == pessoa_id
        )
        assert linha["competencia"] == "2026-07"
        assert linha["totais"]["liquido"] == linha["valor"]
        vale = next(d for d in linha["detalhe"] if d["tipo"] == "vale")
        assert vale["descricao"] == "Vale — mercado"
        assert vale["referencia"] == "Parcela 1 de 2 · vale de 08/06/2026"
        assert vale["origem"]["vale_id"]

    def test_ferias_traz_dias_gozados_e_periodo_aquisitivo_na_referencia(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/ferias", json={
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2025-12-31",
            "dias_gozados": 20, "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-20",
        })
        assert r.status_code == 200, r.text

        linha = next(
            l for l in c.get("/cadastro/folha-pagamento-unificada").json()
            if l["origem_subtipo"] == "ferias" and l["pessoa_id"] == pessoa_id
        )
        principal = linha["detalhe"][0]
        assert principal["referencia"] == "20 de 30 dias · aquisitivo 01/01/2025 a 31/12/2025"
        assert linha["totais"]["liquido"] == pytest.approx(linha["valor"], abs=0.01)

    def test_decimo_terceiro_traz_avos_e_parcela_na_referencia(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "primeira", "meses_trabalhados": 8,
        })
        assert r.status_code == 200, r.text

        linha = next(
            l for l in c.get("/cadastro/folha-pagamento-unificada").json()
            if l["origem_subtipo"] == "decimo_terceiro" and l["pessoa_id"] == pessoa_id
        )
        # A 1ª parcela é adiantamento de até 50% do 13º (Lei 4.749/1965, art.
        # 2º), então o bruto da linha é R$ 1.066,67 e não o 13º cheio de
        # R$ 2.133,33 — a referência precisa dizer sobre qual integral o
        # adiantamento foi tirado, senão o recibo mostra uma metade sem
        # avisar que é metade.
        assert linha["detalhe"][0]["referencia"] == (
            "8/12 avos de 2026 · 1ª parcela · adiantamento sobre 13º integral de R$ 2.133,33"
        )
        # 2133,33 / 2 = 1066,665 -> 1066,66 no arredondamento; o centavo
        # sobra para a 2ª parcela, que é o SALDO (integral - adiantamento),
        # então a soma das duas fecha exatamente em 2133,33.
        assert linha["detalhe"][0]["provento"] == 1066.66


# ---------------------------------------------------------------------------
# Isolamento entre fazendas no carregamento em lote
# ---------------------------------------------------------------------------
@pytest.fixture
def duas_fazendas():
    """Duas fazendas ativas e a sessão já com a fazenda 1 selecionada — o
    cenário em que uma consulta mal escoposada vazaria dado da vizinha."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um", ativa=True))
        s.add(Fazenda(id=2, nome="Fazenda Dois", ativa=True))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", ativo=True))
        s.commit()

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: 1
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


class TestIsolamentoEntreFazendas:
    def test_parcela_de_vale_de_outra_fazenda_nunca_entra_no_holerite(self, duas_fazendas):
        """`_contexto_discriminacao` carrega parcelas de várias folhas de uma
        vez. O escopo é o conjunto de `pessoa_id` das folhas já filtradas por
        fazenda — uma pessoa homônima da fazenda vizinha, com um vale do mesmo
        mês, não pode contaminar a discriminação."""
        c, engine = duas_fazendas
        from fazenda.api.routers.cadastro.rh_folha import _contexto_discriminacao

        with Session(engine) as s:
            minha_pessoa = Pessoa(nome="Leomir Bonfim", tipo="Funcionário", fazenda_id=1)
            pessoa_vizinha = Pessoa(nome="Leomir Bonfim", tipo="Funcionário", fazenda_id=2)
            s.add(minha_pessoa)
            s.add(pessoa_vizinha)
            s.commit()
            s.refresh(minha_pessoa)
            s.refresh(pessoa_vizinha)
            minha_pessoa_id, pessoa_vizinha_id = minha_pessoa.id, pessoa_vizinha.id

            vale_vizinho = ValeFuncionario(
                pessoa_id=pessoa_vizinha_id, valor_total=999.0, forma_pagamento="pix",
                data_pagamento=date(2026, 6, 1), parcelas=1, competencia_inicio="2026-07",
                fazenda_id=2,
            )
            s.add(vale_vizinho)
            s.commit()
            s.refresh(vale_vizinho)
            vale_vizinho_id = vale_vizinho.id
            s.add(ValeParcela(
                vale_id=vale_vizinho_id, pessoa_id=pessoa_vizinha_id, competencia="2026-07",
                valor=999.0, fazenda_id=2,
            ))
            minha_folha = FolhaPagamento(
                pessoa_id=minha_pessoa_id, competencia="2026-07", valor_bruto=3200.0,
                valor_liquido=3200.0, fazenda_id=1,
            )
            s.add(minha_folha)
            s.commit()
            s.refresh(minha_folha)

            contexto = _contexto_discriminacao(s, [minha_folha])
            assert contexto["parcelas_por_pessoa_competencia"] == {}
            # O índice das parcelas ASSUMIDAS pela fazenda (a linha informativa
            # do mês desconsiderado) tem o mesmo escopo, e por isso a mesma
            # trava: ele nasce da mesma varredura, e uma parcela da vizinha não
            # pode entrar nele nem como explicação.
            assert contexto["assumidas_por_pessoa_competencia"] == {}
            assert vale_vizinho_id not in contexto["vales"]

        detalhe = _linhas(c, minha_pessoa_id, "2026-07")
        assert not [d for d in detalhe if d["tipo"] == "vale"]
        assert detalhe[-1]["valor"] == 3200.0


# ---------------------------------------------------------------------------
# Regras puras de formatação (sem I/O)
# ---------------------------------------------------------------------------
class TestRegrasPuras:
    def test_parcela_unica_nao_vira_parcela_1_de_1(self):
        assert holerite.referencia_vale(1, 1, date(2026, 8, 2)) == "Parcela única · vale de 02/08/2026"

    def test_descricao_do_vale_de_nota_traz_nota_e_produto(self):
        assert holerite.descricao_vale(None, {"numero_documento": "4471", "produto": "Kit embreagem"}) == (
            "Vale — nota 4471 (Kit embreagem)"
        )

    def test_vale_sem_observacao_e_sem_nota_fica_so_vale(self):
        """E aí a referência sozinha (parcela + data) já desempata — não se
        inventa descrição."""
        assert holerite.descricao_vale("   ", None) == "Vale"

    def test_percentual_sai_sem_zeros_decorativos(self):
        referencia, _ = holerite.referencia_retencao(160.0, 8.0, 2000.0)
        assert referencia == "8% sobre R$ 2.000,00"
