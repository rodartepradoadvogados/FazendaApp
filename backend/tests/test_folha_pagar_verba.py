"""
Folha: pagar lançando valor DISTINTO numa verba, e decidir o destino da
diferença no ato do pagamento (`POST /cadastro/folha-pagamento/{id}/pagar`).

O que cada bloco prova, e por que:

 A) Pagar MENOS vale do que a parcela previa, com cada uma das três decisões
    do dono — abater (deixa de ser cobrado, e com conta informada volta ao
    caixa como "Devolução de vale"), desconsiderar (a fazenda assume, e o
    Financeiro é comunicado) e reparcelar (a diferença volta ao saldo, nas
    competências seguintes). Em todos, o que se mede é o par: a parcela do mês
    fica valendo o que foi realmente descontado E o líquido pago é o líquido
    recalculado com esse desconto.

 B) Pagar MAIS do que a parcela previa: o excedente é antecipação do saldo, e
    só cabe reparcelar — não há valor deixado de cobrar para abater nem para
    a fazenda assumir. Descontar mais do que o vale inteiro é recusado.

 C) A recusa que o dono pediu: confirmar com diferença e SEM decisão escolhida
    não pode passar — e não pode deixar nada gravado pelo caminho.

 D) O congelamento continua valendo: a fotografia do recibo é tirada DEPOIS da
    decisão (o holerite mostra o desconto que houve, não o previsto), e a
    competência paga fecha a porta para as ações de vale do #708.

 E) Isolamento entre fazendas nas rotas novas: folha de outra fazenda, parcela
    que não é verba desta folha e conta bancária de outra fazenda caem todas
    em 404 — nunca 403, que confirmaria a existência do id.

TOKEN DE VERDADE em tudo (`criar_token`), nunca `dependency_overrides` do
`get_fazenda_atual_id`: falsificar a claim tiraria do teste exatamente o que o
bloco (E) precisa provar.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento,
    Pessoa, Usuario, UsuarioFazenda, ValeFuncionario, ValeParcela,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


# ---------------------------------------------------------------------------
# Ambiente: duas fazendas-clientes, cada uma com seu admin e seu funcionário
# ---------------------------------------------------------------------------
@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        for fid, nome in ((1, "Fazenda Um"), (2, "Fazenda Dois")):
            s.add(Fazenda(id=fid, nome=nome, ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Salário alto de propósito: o teto de 40% do salário para vale
        # (R$ 2.000) não pode ser o que faz um teste de pagamento falhar.
        s.add(Pessoa(id=1, nome="Leomir Bonfim", tipo="Funcionário", salario_base=5000.0, fazenda_id=1))
        s.add(Pessoa(id=2, nome="Vizinho Silva", tipo="Funcionário", salario_base=5000.0, fazenda_id=2))
        s.add(Usuario(id=1, username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=1))
        s.add(Usuario(id=2, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=2))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        s.add(ContaCorrente(id=1, banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6", fazenda_id=1))
        s.add(ContaCorrente(id=2, banco="Sicoob", agencia="3000", numero_conta="777-1", fazenda_id=2))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cab(username: str = "admin1", fazenda_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


# ── helpers ────────────────────────────────────────────────────────────────
def _criar_vale(c, *, pessoa_id: int = 1, valor: float = 900.0, parcelas: int = 3,
                competencia: str = "2026-07", conta_id: int | None = 1,
                headers: dict | None = None) -> dict:
    resposta = c.post("/cadastro/vales", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "valor_total": valor, "forma_pagamento": "pix",
        "data_pagamento": "2026-06-10", "parcelas": parcelas, "competencia_inicio": competencia,
        "conta_corrente_id": conta_id, "observacao": "mercado",
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _criar_folha(c, *, pessoa_id: int = 1, competencia: str, bruto: float = 3000.0,
                 headers: dict | None = None) -> dict:
    resposta = c.post("/cadastro/folha-pagamento", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": bruto,
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _folha(c, competencia: str, pessoa_id: int = 1, headers: dict | None = None) -> dict:
    resposta = c.get("/cadastro/folha-pagamento", headers=headers or _cab())
    assert resposta.status_code == 200, resposta.text
    return next(
        r for r in resposta.json() if r["pessoa_id"] == pessoa_id and r["competencia"] == competencia
    )


def _parcela_id_da_verba(c, competencia: str, pessoa_id: int = 1, headers: dict | None = None) -> int:
    """O id da parcela de vale como a TELA o vê: pela origem da linha do
    holerite, que é de onde o pop-up de pagamento tira a verba clicável."""
    folha = _folha(c, competencia, pessoa_id, headers)
    linha = next(d for d in folha["detalhe"] if d["tipo"] == "vale")
    return linha["origem"]["parcela_id"]


def _pagar(c, folha_id: int, corpo: dict, headers: dict | None = None):
    return c.post(f"/cadastro/folha-pagamento/{folha_id}/pagar", headers=headers or _cab(), json=corpo)


def _parcelas(engine, vale_id: int) -> list[ValeParcela]:
    with Session(engine) as s:
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
        return sorted(parcelas, key=lambda p: (p.competencia, p.id or 0))


def _vale(engine, vale_id: int) -> ValeFuncionario:
    with Session(engine) as s:
        return s.get(ValeFuncionario, vale_id)


def _folha_db(engine, folha_id: int) -> FolhaPagamento:
    with Session(engine) as s:
        return s.get(FolhaPagamento, folha_id)


# ===========================================================================
# A) Pagar MENOS do que a parcela previa — as três decisões
# ===========================================================================
class TestPagarMenosQueOPrevisto:
    def test_abater_deixa_de_cobrar_a_diferenca_e_lanca_a_devolucao(self, ambiente):
        """R$ 300 previstos de vale, R$ 100 descontados: os R$ 200 deixam de
        ser cobrados e, como o funcionário devolveu em dinheiro, entram no
        caixa como receita — senão a fazenda desembolsou o vale inteiro,
        deixou de recuperar parte na folha e o dinheiro que voltou não
        apareceria em lugar nenhum."""
        c, engine = ambiente
        vale = _criar_vale(c)  # 900 em 3x: 07, 08, 09
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater", "conta_corrente_id": 1},
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "pago"

        parcelas = _parcelas(engine, vale["id"])
        assert [(p.competencia, p.valor) for p in parcelas] == [
            ("2026-07", 100.0), ("2026-08", 300.0), ("2026-09", 300.0),
        ]
        assert _vale(engine, vale["id"]).valor_abatido == 200.0

        # O líquido pago é o recalculado com o desconto que realmente houve.
        registro = _folha_db(engine, folha["id"])
        assert registro.valor_vale == 100.0
        assert registro.valor_liquido == 2900.0

        with Session(engine) as s:
            devolucao = s.exec(
                select(ContaGerencial).where(ContaGerencial.descricao.like("Devolução de vale%"))
            ).first()
            assert devolucao is not None
            assert (devolucao.tipo, devolucao.valor_total, devolucao.valor_pago) == ("receita", 200.0, 200.0)
            assert devolucao.fazenda_id == 1

    def test_abater_sem_conta_nao_inventa_entrada_no_caixa(self, ambiente):
        """Abatimento que é perdão/concessão não tem devolução a lançar."""
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater"},
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["decisoes"][0]["numero_lancamento_devolucao"] is None
        with Session(engine) as s:
            assert not s.exec(
                select(ContaGerencial).where(ContaGerencial.descricao.like("Devolução de vale%"))
            ).all()

    def test_desconsiderar_parte_a_parcela_e_a_fazenda_assume_a_diferenca(self, ambiente):
        """A parcela do mês se parte em duas: a cobrada e a assumida pela
        fazenda — que continua no banco, com o motivo, porque é o registro de
        por que aquele pedaço do desconto sumiu."""
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "desconsiderar", "motivo": "quebrou o trator"},
        })
        assert resposta.status_code == 200, resposta.text
        # A fazenda assumindo o valor é decisão que se comunica ao Financeiro:
        # o vale saiu por pix e tem lançamento próprio no extrato.
        assert resposta.json()["decisoes"][0]["financeiro"]["natureza"] == "lancamento_proprio"

        parcelas_julho = [p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07"]
        cobrada = [p for p in parcelas_julho if not p.assumida_pela_fazenda]
        assumida = [p for p in parcelas_julho if p.assumida_pela_fazenda]
        assert [p.valor for p in cobrada] == [100.0]
        assert [p.valor for p in assumida] == [200.0]
        assert assumida[0].motivo_assuncao == "quebrou o trator"
        assert _vale(engine, vale["id"]).valor_assumido_fazenda == 200.0

        registro = _folha_db(engine, folha["id"])
        assert registro.valor_vale == 100.0  # a assumida não é descontada de ninguém
        assert registro.valor_liquido == 2900.0

    def test_desconsiderar_tudo_marca_a_parcela_inteira_sem_criar_gemea(self, ambiente):
        """Descontar zero é o caso em que não há o que partir: a própria
        parcela é o que a fazenda assume."""
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 0.0}],
            "decisao": {"tipo": "desconsiderar"},
        })
        assert resposta.status_code == 200, resposta.text

        parcelas_julho = [p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07"]
        assert len(parcelas_julho) == 1
        assert parcelas_julho[0].assumida_pela_fazenda is True
        assert parcelas_julho[0].valor == 300.0
        assert _folha_db(engine, folha["id"]).valor_liquido == 3000.0

    def test_reparcelar_devolve_a_diferenca_ao_saldo_das_competencias_seguintes(self, ambiente):
        """A diferença continua sendo dívida: R$ 200 não descontados voltam
        para o saldo (200 + 600 restantes) e são redistribuídos em 2x."""
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 2},
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["decisoes"][0]["competencias"] == ["2026-08", "2026-09"]

        assert [(p.competencia, p.valor) for p in _parcelas(engine, vale["id"])] == [
            ("2026-07", 100.0), ("2026-08", 400.0), ("2026-09", 400.0),
        ]
        # O vale inteiro continua devido: nada foi abatido nem assumido.
        v = _vale(engine, vale["id"])
        assert (v.valor_abatido, v.valor_assumido_fazenda) == (0.0, 0.0)

    def test_reparcelar_recusa_competencia_de_destino_ja_paga(self, ambiente):
        """A porta que o #708 fechou continua fechada: a diferença não pode
        cair num mês cujo holerite já é recibo."""
        c, engine = ambiente
        _criar_vale(c, parcelas=1, valor=300.0)  # só 2026-07
        folha_agosto = _criar_folha(c, competencia="2026-08")
        assert _pagar(c, folha_agosto["id"], {"data_pagamento": "2026-09-05"}).status_code == 200

        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")
        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 1, "competencia_inicio": "2026-08"},
        })
        assert resposta.status_code == 400
        assert "2026-08" in resposta.json()["detail"]
        assert _folha_db(engine, folha["id"]).status == "pendente"


# ===========================================================================
# B) Pagar MAIS do que a parcela previa
# ===========================================================================
class TestPagarMaisQueOPrevisto:
    def test_o_excedente_antecipa_o_saldo_e_o_resto_e_reparcelado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)  # 900 em 3x
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 500.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 2},
        })
        assert resposta.status_code == 200, resposta.text

        assert [(p.competencia, p.valor) for p in _parcelas(engine, vale["id"])] == [
            ("2026-07", 500.0), ("2026-08", 200.0), ("2026-09", 200.0),
        ]
        registro = _folha_db(engine, folha["id"])
        assert (registro.valor_vale, registro.valor_liquido) == (500.0, 2500.0)

    def test_descontar_o_vale_inteiro_de_uma_vez_nao_deixa_parcela_sobrando(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 900.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 1},
        })
        assert resposta.status_code == 200, resposta.text
        assert [(p.competencia, p.valor) for p in _parcelas(engine, vale["id"])] == [("2026-07", 900.0)]

    def test_recusa_descontar_mais_do_que_o_vale_inteiro(self, ambiente):
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 1000.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 1},
        })
        assert resposta.status_code == 400
        assert "saldo restante" in resposta.json()["detail"]
        assert _folha_db(engine, folha["id"]).status == "pendente"

    def test_abater_nao_serve_para_quem_descontou_a_mais(self, ambiente):
        """Não há valor deixado de cobrar para abater — o dinheiro foi
        descontado de verdade."""
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 500.0}],
            "decisao": {"tipo": "abater"},
        })
        assert resposta.status_code == 400
        assert "a mais" in resposta.json()["detail"]


# ===========================================================================
# C) Diferença sem decisão: recusa, e sem deixar rastro
# ===========================================================================
class TestDiferencaExigeDecisao:
    def test_confirmar_com_diferenca_e_sem_decisao_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
        })
        assert resposta.status_code == 400
        assert "Escolha o que fazer com ela" in resposta.json()["detail"]

        # Nada gravado: nem a folha paga, nem a parcela mexida.
        assert _folha_db(engine, folha["id"]).status == "pendente"
        assert [p.valor for p in _parcelas(engine, vale["id"])] == [300.0, 300.0, 300.0]

    def test_decisao_desconhecida_tambem_e_recusada(self, ambiente):
        c, _ = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "perdoar_tudo"},
        })
        assert resposta.status_code == 400

    def test_sem_diferenca_e_o_marcar_como_pago_de_sempre(self, ambiente):
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 300.0}],
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["decisoes"] == []
        registro = _folha_db(engine, folha["id"])
        assert (registro.status, registro.valor_liquido) == ("pago", 2700.0)

    def test_folha_ja_paga_nao_e_paga_de_novo(self, ambiente):
        c, _ = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        assert _pagar(c, folha["id"], {"data_pagamento": "2026-08-05"}).status_code == 200
        resposta = _pagar(c, folha["id"], {"data_pagamento": "2026-08-06"})
        assert resposta.status_code == 400
        assert "já está pago" in resposta.json()["detail"]


# ===========================================================================
# D) O congelamento, e a porta que ele fecha
# ===========================================================================
class TestReciboCongelado:
    def test_a_fotografia_e_tirada_depois_da_decisao(self, ambiente):
        """O holerite tem de mostrar o desconto que HOUVE. Se a fotografia
        fosse tirada antes da decisão, o recibo cobraria os R$ 300 previstos
        de um pagamento em que só R$ 100 foram descontados."""
        c, _ = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")
        assert _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater"},
        }).status_code == 200

        paga = _folha(c, "2026-07")
        assert paga["recibo_congelado"] is True
        linha_vale = next(d for d in paga["detalhe"] if d["tipo"] == "vale")
        assert linha_vale["desconto"] == 100.0
        assert paga["totais"]["liquido"] == 2900.0

    def test_competencia_paga_fecha_a_porta_para_as_acoes_do_vale(self, ambiente):
        c, _ = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")
        assert _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 2},
        }).status_code == 200

        resposta = c.post(f"/cadastro/vales/{vale['id']}/acoes", headers=_cab(), json={
            "acao": "reparcelar", "parcelas": 2, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 400
        assert "2026-07" in resposta.json()["detail"]


# ===========================================================================
# E) Isolamento entre fazendas
# ===========================================================================
class TestIsolamentoEntreFazendas:
    def test_folha_de_outra_fazenda_da_404(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        resposta = _pagar(
            c, folha["id"], {"data_pagamento": "2026-08-05"}, headers=_cab("admin2", 2),
        )
        assert resposta.status_code == 404
        assert _folha_db(engine, folha["id"]).status == "pendente"

    def test_parcela_de_outra_fazenda_nao_vira_verba_desta_folha(self, ambiente):
        """A parcela existe — só não é verba DESTA folha. Cai em 404 pelo
        mesmo motivo de sempre: 403 confirmaria a existência do id."""
        c, engine = ambiente
        vale_vizinho = _criar_vale(c, pessoa_id=2, competencia="2026-07", conta_id=2,
                                   headers=_cab("admin2", 2))
        parcela_vizinha = _parcelas(engine, vale_vizinho["id"])[0]

        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_vizinha.id, "valor_pago": 10.0}],
            "decisao": {"tipo": "abater"},
        })
        assert resposta.status_code == 404
        assert _folha_db(engine, folha["id"]).status == "pendente"
        with Session(engine) as s:
            assert s.get(ValeParcela, parcela_vizinha.id).valor == parcela_vizinha.valor

    def test_devolucao_nao_pode_cair_em_conta_de_outra_fazenda(self, ambiente):
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela_id = _parcela_id_da_verba(c, "2026-07")

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater", "conta_corrente_id": 2},
        })
        assert resposta.status_code == 404
        assert _folha_db(engine, folha["id"]).status == "pendente"

    def test_uma_fazenda_paga_a_propria_folha_normalmente(self, ambiente):
        """O contraprova do bloco: o mesmo fluxo, dentro da fazenda certa,
        passa — o que separa os casos é a fazenda, não a rota."""
        c, engine = ambiente
        vale = _criar_vale(c, pessoa_id=2, competencia="2026-07", conta_id=2, headers=_cab("admin2", 2))
        folha = _criar_folha(c, pessoa_id=2, competencia="2026-07", headers=_cab("admin2", 2))
        parcela_id = _parcela_id_da_verba(c, "2026-07", pessoa_id=2, headers=_cab("admin2", 2))

        resposta = _pagar(c, folha["id"], {
            "data_pagamento": "2026-08-05",
            "verbas": [{"parcela_id": parcela_id, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater", "conta_corrente_id": 2},
        }, headers=_cab("admin2", 2))
        assert resposta.status_code == 200, resposta.text
        assert _vale(engine, vale["id"]).valor_abatido == 200.0
