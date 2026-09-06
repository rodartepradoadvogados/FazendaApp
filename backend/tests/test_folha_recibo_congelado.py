"""
C7 — o recibo de uma folha JÁ PAGA tem de ser o recibo do que foi pago.

O QUE ESTAVA ERRADO. `_detalhe_folha` remontava a discriminação do holerite A
CADA LEITURA, consultando `ValeParcela` ao vivo — inclusive para folha
`status == "pago"`. Só que o `valor_liquido` do pagamento ficou GRAVADO em
`FolhaPagamento`, e os self-heals do módulo pulam folha paga de propósito (não
se reescreve dinheiro que já saiu). Os dois números chegavam à tela por
caminhos diferentes: bastava um vale nascer, mudar de valor ou mudar de
competência DEPOIS do pagamento para o holerite impresso hoje deixar de ser o
recibo do que foi efetivamente pago. Num documento trabalhista isso é grave —
o holerite é prova.

Os dois caminhos que produzem a divergência sem nenhum truque (os dois são
usados aqui, porque são os que existem de verdade na tela):
 1. `POST /cadastro/vales` numa competência cuja folha já está paga — não há
    guarda nenhuma nesse caminho (as guardas de `_vale_competencia_paga` só
    cobrem editar/excluir vale e parcela);
 2. `PUT /cadastro/vales/{id}` movendo `competencia_inicio` para dentro de uma
    competência paga — a guarda olha as competências ATUAIS do vale, não as
    novas.

A CORREÇÃO: ao ser paga, a folha congela a discriminação que gerou aquele
líquido (`FolhaPagamento.discriminacao_congelada`), e o recibo passa a ser lido
dali. Folha não paga continua 100% ao vivo. Descongelar é um ato explícito —
`POST /cadastro/folha-pagamento/{id}/estornar` —, no molde de
`encerrar_diaria`/`reabrir_diaria`.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento,
    Pessoa,
)


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


def _pessoa(engine, nome: str = "Leomir Bonfim", fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3200.0, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _conta_corrente(engine, fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(
            banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6", fazenda_id=fazenda_id,
        )
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _folha(c, pessoa_id: int, competencia: str) -> dict:
    """A folha da competência, como a tela recebe — já com `detalhe`/`totais`."""
    resposta = c.get("/cadastro/folha-pagamento")
    assert resposta.status_code == 200, resposta.text
    return next(
        r for r in resposta.json()
        if r["pessoa_id"] == pessoa_id and r["competencia"] == competencia
    )


def _linhas_de_vale(folha: dict) -> list[dict]:
    return [d for d in folha["detalhe"] if d["tipo"] == "vale"]


def _lancar_vale(c, pessoa_id: int, competencia: str, valor: float, conta_id: int, **extra) -> dict:
    corpo = {
        "pessoa_id": pessoa_id, "valor_total": valor, "forma_pagamento": "pix",
        "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": competencia,
        "conta_corrente_id": conta_id, "observacao": "mercado",
    }
    corpo.update(extra)
    resposta = c.post("/cadastro/vales", json=corpo)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _pagar_folha(c, pessoa_id: int, competencia: str, valor_bruto: float = 3200.0) -> dict:
    resposta = c.post("/cadastro/folha-pagamento", json={
        "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": valor_bruto,
        "status": "pago", "data_pagamento": "2026-07-05",
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# ---------------------------------------------------------------------------
# O recibo da folha paga não se mexe mais
# ---------------------------------------------------------------------------
class TestReciboDaFolhaPagaNaoSeMexe:
    def test_vale_lancado_depois_do_pagamento_nao_entra_no_recibo_pago(self, client):
        """ESTE É O TESTE DO DEFEITO. Antes do congelamento, o vale lançado
        depois aparecia como uma linha de desconto num holerite já pago —
        recibo com um desconto que nunca foi descontado."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        _lancar_vale(c, pessoa_id, "2026-07", 400.0, conta_id)
        paga = _pagar_folha(c, pessoa_id, "2026-07")
        assert paga["valor_vale"] == 400.0
        assert paga["valor_liquido"] == 2800.0

        antes = _folha(c, pessoa_id, "2026-07")
        assert len(_linhas_de_vale(antes)) == 1

        # O fato novo: mais um vale na MESMA competência, depois do pagamento.
        _lancar_vale(c, pessoa_id, "2026-07", 500.0, conta_id, observacao="farmácia")

        depois = _folha(c, pessoa_id, "2026-07")
        assert len(_linhas_de_vale(depois)) == 1, "o vale novo não pode entrar num recibo já pago"
        assert depois["detalhe"] == antes["detalhe"]
        assert depois["totais"] == antes["totais"]

    def test_o_liquido_da_discriminacao_continua_somando_o_liquido_gravado(self, client):
        """A divergência que a tela denuncia com "Recibo não soma o líquido
        pago" (|Σ líquido gravado − Σ líquido da discriminação| > 0,01) deixa
        de existir: os dois números passam a vir do mesmo lugar."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        _lancar_vale(c, pessoa_id, "2026-07", 400.0, conta_id)
        _pagar_folha(c, pessoa_id, "2026-07")
        _lancar_vale(c, pessoa_id, "2026-07", 500.0, conta_id, observacao="farmácia")

        folha = _folha(c, pessoa_id, "2026-07")
        assert abs(folha["totais"]["liquido"] - folha["valor_liquido"]) <= 0.01
        assert folha["detalhe"][-1]["valor"] == folha["valor_liquido"]

    def test_parcela_remanejada_para_a_competencia_paga_nao_altera_o_recibo(self, client):
        """O outro caminho real: o vale existia em 2026-08 (aberta) e foi
        movido para 2026-07 (paga). A guarda de `_vale_competencia_paga` olha
        as competências ATUAIS do vale, então o PUT passa."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        vale = _lancar_vale(c, pessoa_id, "2026-08", 300.0, conta_id)
        _pagar_folha(c, pessoa_id, "2026-07")
        antes = _folha(c, pessoa_id, "2026-07")
        assert _linhas_de_vale(antes) == []

        resposta = c.put(f"/cadastro/vales/{vale['id']}", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
            "conta_corrente_id": conta_id, "observacao": "mercado",
        })
        assert resposta.status_code == 200, resposta.text

        depois = _folha(c, pessoa_id, "2026-07")
        assert _linhas_de_vale(depois) == []
        assert depois["detalhe"] == antes["detalhe"]

    def test_a_folha_paga_nao_muda_de_valor_por_causa_do_congelamento(self, client):
        """A trava explícita: o congelamento é só sobre a LEITURA do recibo —
        nenhum valor gravado (líquido, vale, conta a pagar) pode se mover."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        _lancar_vale(c, pessoa_id, "2026-07", 400.0, conta_id)
        paga = _pagar_folha(c, pessoa_id, "2026-07")
        numero = paga["numero_lancamento_gerado"]

        _lancar_vale(c, pessoa_id, "2026-07", 500.0, conta_id, observacao="farmácia")
        _folha(c, pessoa_id, "2026-07")  # a listagem é onde os self-heals rodam

        with Session(engine) as s:
            registro = s.get(FolhaPagamento, paga["id"])
            assert registro.valor_liquido == 2800.0
            assert registro.valor_vale == 400.0
            assert registro.status == "pago"
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first()
            assert conta.valor_total == 2800.0
            assert conta.valor_pago == 2800.0

    def test_marcar_como_pago_congela_o_recibo_daquele_instante(self, client):
        """A folha nasce pendente e vira paga pelo PUT (o botão "Marcar como
        pago"). É essa transição que tira a fotografia."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        criada = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        }).json()
        _lancar_vale(c, pessoa_id, "2026-07", 200.0, conta_id)
        _folha(c, pessoa_id, "2026-07")  # self-heal absorve o vale na folha pendente

        resposta = c.put(f"/cadastro/folha-pagamento/{criada['id']}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
            "status": "pago", "data_pagamento": "2026-07-05",
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["valor_liquido"] == 3000.0

        antes = _folha(c, pessoa_id, "2026-07")
        _lancar_vale(c, pessoa_id, "2026-07", 700.0, conta_id, observacao="farmácia")
        depois = _folha(c, pessoa_id, "2026-07")
        assert depois["detalhe"] == antes["detalhe"]
        assert depois["totais"]["liquido"] == 3000.0


class TestPayloadDaTela:
    def test_a_listagem_nao_devolve_o_json_da_fotografia_so_a_marca(self, client):
        """A tela já recebe as mesmas linhas em `detalhe` — mandar o blob
        junto dobraria a listagem inteira. Vai só o fato que ela precisa para
        rotular o documento."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        _pagar_folha(c, pessoa_id, "2026-07")
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 3200.0,
        })

        paga = _folha(c, pessoa_id, "2026-07")
        pendente = _folha(c, pessoa_id, "2026-08")
        assert "discriminacao_congelada" not in paga
        assert paga["recibo_congelado"] is True
        assert paga["recibo_congelado_em"]
        assert pendente["recibo_congelado"] is False
        assert pendente["recibo_congelado_em"] is None


# ---------------------------------------------------------------------------
# Folha NÃO paga continua ao vivo, com todos os self-heals
# ---------------------------------------------------------------------------
class TestFolhaNaoPagaContinuaAoVivo:
    def test_vale_lancado_depois_ainda_corrige_a_folha_pendente(self, client):
        """O self-heal de `listar_folha_pagamento` (vale lançado DEPOIS da
        folha ainda não paga) não pode ter sido desligado pelo congelamento."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        })
        assert _folha(c, pessoa_id, "2026-07")["valor_liquido"] == 3200.0

        _lancar_vale(c, pessoa_id, "2026-07", 450.0, conta_id)

        folha = _folha(c, pessoa_id, "2026-07")
        assert folha["valor_vale"] == 450.0
        assert folha["valor_liquido"] == 2750.0
        assert len(_linhas_de_vale(folha)) == 1
        assert folha["totais"]["liquido"] == 2750.0

    def test_folha_pendente_nao_guarda_fotografia_nenhuma(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        criada = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        }).json()
        _folha(c, pessoa_id, "2026-07")

        with Session(engine) as s:
            registro = s.get(FolhaPagamento, criada["id"])
            assert registro.discriminacao_congelada is None
            assert registro.discriminacao_congelada_em is None


# ---------------------------------------------------------------------------
# Descongelar existe, é explícito, e nunca acontece em silêncio
# ---------------------------------------------------------------------------
class TestEstornoDescongela:
    def test_estorno_devolve_a_folha_ao_calculo_ao_vivo(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        _lancar_vale(c, pessoa_id, "2026-07", 400.0, conta_id)
        paga = _pagar_folha(c, pessoa_id, "2026-07")
        _lancar_vale(c, pessoa_id, "2026-07", 500.0, conta_id, observacao="farmácia")
        assert len(_linhas_de_vale(_folha(c, pessoa_id, "2026-07"))) == 1

        resposta = c.post(f"/cadastro/folha-pagamento/{paga['id']}/estornar")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "pendente"
        assert resposta.json()["data_pagamento"] is None

        with Session(engine) as s:
            registro = s.get(FolhaPagamento, paga["id"])
            assert registro.discriminacao_congelada is None
            assert registro.discriminacao_congelada_em is None

        # Ao vivo de novo: os DOIS vales voltam a aparecer e o líquido se
        # recompõe pelo self-heal da listagem.
        folha = _folha(c, pessoa_id, "2026-07")
        assert len(_linhas_de_vale(folha)) == 2
        assert folha["valor_vale"] == 900.0
        assert folha["valor_liquido"] == 2300.0
        assert folha["totais"]["liquido"] == 2300.0

    def test_estorno_desfaz_a_baixa_da_conta_a_pagar(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        paga = _pagar_folha(c, pessoa_id, "2026-07")

        c.post(f"/cadastro/folha-pagamento/{paga['id']}/estornar")

        with Session(engine) as s:
            conta = s.exec(
                select(ContaGerencial).where(
                    ContaGerencial.numero_lancamento == paga["numero_lancamento_gerado"]
                )
            ).first()
            assert conta.valor_pago is None
            assert conta.data_pagamento is None

    def test_estorno_de_folha_nao_paga_e_recusado(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        criada = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
        }).json()

        resposta = c.post(f"/cadastro/folha-pagamento/{criada['id']}/estornar")
        assert resposta.status_code == 400
        assert "não está paga" in resposta.json()["detail"]

    def test_pagar_de_novo_congela_uma_fotografia_nova(self, client):
        """Depois do estorno a folha volta a ser editável e um novo pagamento
        congela o mundo DAQUELE momento — não o do pagamento anterior."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        _lancar_vale(c, pessoa_id, "2026-07", 400.0, conta_id)
        paga = _pagar_folha(c, pessoa_id, "2026-07")
        _lancar_vale(c, pessoa_id, "2026-07", 500.0, conta_id, observacao="farmácia")
        c.post(f"/cadastro/folha-pagamento/{paga['id']}/estornar")
        _folha(c, pessoa_id, "2026-07")

        resposta = c.put(f"/cadastro/folha-pagamento/{paga['id']}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3200.0,
            "status": "pago", "data_pagamento": "2026-08-05",
        })
        assert resposta.status_code == 200, resposta.text

        folha = _folha(c, pessoa_id, "2026-07")
        assert len(_linhas_de_vale(folha)) == 2
        assert folha["valor_liquido"] == 2300.0
        assert folha["totais"]["liquido"] == 2300.0

        # E a nova fotografia também não se mexe mais.
        _lancar_vale(c, pessoa_id, "2026-07", 100.0, conta_id, observacao="posto")
        assert _folha(c, pessoa_id, "2026-07")["detalhe"] == folha["detalhe"]


# ---------------------------------------------------------------------------
# Multi-tenant — o estorno é a única rota nova que escreve
# ---------------------------------------------------------------------------
@pytest.fixture
def duas_fazendas():
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
    def test_estorno_nao_alcanca_folha_paga_de_outra_fazenda(self, duas_fazendas):
        c, engine = duas_fazendas
        pessoa_vizinha = _pessoa(engine, nome="Vizinho", fazenda_id=2)
        with Session(engine) as s:
            folha_vizinha = FolhaPagamento(
                pessoa_id=pessoa_vizinha, competencia="2026-07", valor_bruto=3200.0,
                valor_liquido=3200.0, status="pago", data_pagamento=date(2026, 7, 5),
                discriminacao_congelada="[]", fazenda_id=2,
            )
            s.add(folha_vizinha)
            s.commit()
            s.refresh(folha_vizinha)
            folha_vizinha_id = folha_vizinha.id

        resposta = c.post(f"/cadastro/folha-pagamento/{folha_vizinha_id}/estornar")
        assert resposta.status_code == 404

        with Session(engine) as s:
            intacta = s.get(FolhaPagamento, folha_vizinha_id)
            assert intacta.status == "pago"
            assert intacta.discriminacao_congelada == "[]"

    def test_conta_a_pagar_homonima_de_outra_fazenda_nao_e_estornada(self, duas_fazendas):
        """`_conta_da_folha` filtra por `fazenda_id` NA PRÓPRIA consulta. Duas
        fazendas numeram lançamentos por conta própria, então o mesmo
        `numero_lancamento` existe nas duas — sem o filtro, o estorno da minha
        folha desbaixava a conta da vizinha."""
        c, engine = duas_fazendas
        pessoa_id = _pessoa(engine, fazenda_id=1)
        paga = _pagar_folha(c, pessoa_id, "2026-07")
        numero = paga["numero_lancamento_gerado"]

        with Session(engine) as s:
            s.add(ContaGerencial(
                numero_lancamento=numero, descricao="Folha da vizinha",
                data_vencimento=date(2026, 8, 5), fornecedor_cliente="Vizinho",
                tipo_documento="Folha de pagamento", valor_total=1000.0,
                parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
                data_pagamento=date(2026, 8, 5), valor_pago=1000.0, fazenda_id=2,
            ))
            s.commit()

        assert c.post(f"/cadastro/folha-pagamento/{paga['id']}/estornar").status_code == 200

        with Session(engine) as s:
            contas = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).all()
            por_fazenda = {conta.fazenda_id: conta for conta in contas}
            assert por_fazenda[1].valor_pago is None
            assert por_fazenda[2].valor_pago == 1000.0
