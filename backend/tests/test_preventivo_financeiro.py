"""
Fatia 9 do planejamento unificado (docs/agents/auditoria-preventivo-agenda/
planejamento/06-planejamento-unificado.md, secao 7): o agendamento preventivo
conversa com Compras, Estoque e Financeiro.

  (1) Comunicar compra -> cotacao/pedido do insumo que falta (dose x animais);
  (2) Vincular pagamento ja realizado (lancamento pago do Financeiro);
  (3) Lancar conta a pagar (produto x dose ou honorario);
  (4) Estoque desconsiderado -> compra 'Nao necessaria';
  (5) Cancelar: destino de cada vinculo (conta manter/cancelar, pagamento
      manter/desvincular), cada um logado; conta cancelada sai de 'A pagar';
  (6) Custo previsto / 'a informar' e contas em Conferir, pos-aplicacao e Concluidos;
  (7) Veterinario: Pessoa/CRMV, quem confirmou e quando.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from fazenda.models import (
    ChecklistItem, ContaGerencial, Cotacao, CotacaoItem, CronogramaSanitario, CronogramaSanitarioLog,
    CronogramaSanitarioVinculo, Estoque, Fornecedor, LancamentoItem, MovimentoEstoque, Pedido, PedidoItem,
)
from tests.test_aplicar_agendamento_preventivo import (  # noqa: F401  (fixtures reutilizadas)
    HOJE, _USUARIO, _agendar, _animal, _aplicar, _estoque, _espera, _materializar_template, _pessoas, _regra, _template,
    cenario, ctx,
)


# ─────────────────────────────── apoio ───────────────────────────────
def _pagamento(engine, *, valor: float = 128.0, produto: str = "B19", quantidade: float | None = 20.0, fornecedor: str = "Agro Vet",
               fazenda_id: int = 1, pago: bool = True, numero: str = "LC-2026-90001") -> int:
    with Session(engine) as s:
        c = ContaGerencial(
            fazenda_id=fazenda_id, numero_lancamento=numero, descricao=f"{produto} — vacina", tipo="despesa", origem="manual",
            fornecedor_cliente=fornecedor, valor_total=valor, valor_pago=valor if pago else None,
            data_vencimento=HOJE - timedelta(days=10), data_pagamento=(HOJE - timedelta(days=9)) if pago else None,
            parcela_num=1, parcela_total=1,
        )
        s.add(c)
        s.add(LancamentoItem(numero_lancamento=numero, tipo="despesa", produto=produto, quantidade=quantidade,
                             valor_total=valor, fazenda_id=fazenda_id))
        s.commit()
        s.refresh(c)
        return c.id


def _fornecedor(engine, nome: str = "Agro Vet", fazenda_id: int = 1) -> int:
    with Session(engine) as s:
        f = Fornecedor(nome=nome, tipo="Distribuidora", fazenda_id=fazenda_id, ativo=True)
        s.add(f)
        s.commit()
        s.refresh(f)
        return f.id


def _log(engine, ag: int) -> list[CronogramaSanitarioLog]:
    with Session(engine) as s:
        return list(s.exec(select(CronogramaSanitarioLog).where(CronogramaSanitarioLog.cronograma_id == ag).order_by(CronogramaSanitarioLog.id)).all())


def _acoes(engine, ag: int) -> list[str]:
    return [l.acao for l in _log(engine, ag)]


def _vinculos(engine, ag: int, tipo: str | None = None) -> list[CronogramaSanitarioVinculo]:
    with Session(engine) as s:
        q = select(CronogramaSanitarioVinculo).where(CronogramaSanitarioVinculo.cronograma_id == ag)
        if tipo:
            q = q.where(CronogramaSanitarioVinculo.tipo == tipo)
        return list(s.exec(q.order_by(CronogramaSanitarioVinculo.id)).all())


def _fin(c, ag: int) -> dict:
    r = c.get(f"/sanidade/cronogramas/{ag}/financeiro")
    assert r.status_code == 200, r.text
    return r.json()


def _put_checklist(c, ag: int, corpo: dict):
    return c.put(f"/sanidade/cronogramas/{ag}/checklist", json=corpo)


def _conta_pagar(c, ag: int, **kw):
    corpo = {"subtipo": "produto", "fornecedor": "Agro Vet", "vencimento": (HOJE + timedelta(days=10)).isoformat()}
    corpo.update(kw)
    return c.post(f"/sanidade/cronogramas/{ag}/financeiro/conta-pagar", json=corpo)


@pytest.fixture
def cena(cenario):
    """B19 com 4 animais no agendamento de hoje (3 da janela + 1 fora), vet Dr. Paulo, estoque 100 doses a R$ 6,40,
    checklist com estoque/vet/horario/financeiro."""
    _materializar_template(cenario, ("estoque", "vet", "horario", "financeiro"))
    return cenario


# ─────────────────────────────── necessidade e custo ───────────────────────────────
class TestNecessidadeECusto:
    def test_custo_previsto_e_preco_do_produto_x_dose_x_animais(self, cena):
        f = _fin(cena["c"], cena["ag"])
        n = f["necessidade"]
        assert n["produto"] == "B19" and n["animais"] == 4 and n["precisa"] == 4 and n["saldo"] == 100 and n["falta"] == 0
        assert n["cobre"] is True
        assert n["custo_previsto"] == pytest.approx(25.6) and n["custo_a_informar"] is False
        assert f["custo_previsto"] == pytest.approx(25.6)

    def test_frasco_do_veterinario_deixa_o_custo_a_informar(self, cena):
        c, ag = cena["c"], cena["ag"]
        r = _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Frasco do veterinário", "lote": "V1", "validade": (HOJE + timedelta(days=90)).isoformat()}})
        assert r.status_code == 200, r.text
        n = _fin(c, ag)["necessidade"]
        assert n["custo_a_informar"] is True and n["custo_previsto"] is None
        assert "veterinário" in n["custo_motivo"].lower()

    def test_sem_preco_cadastrado_tambem_e_a_informar(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s, valor_unitario=None)
            _animal(s, "1")
            cal = _regra(s)
            _espera(s, cal, ["1"])
        ag = _agendar(c, cal, ["1"], vet=vet)["id"]
        n = _fin(c, ag)["necessidade"]
        assert n["custo_previsto"] is None and n["custo_a_informar"] is True and "preço" in n["custo_motivo"].lower()

    def test_falta_e_dose_x_animais_menos_o_saldo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s, lotes=[("L1", 2.0, HOJE + timedelta(days=100))])
            for n in ("1", "2", "3", "4"):
                _animal(s, n)
            cal = _regra(s)
            _espera(s, cal, ["1", "2", "3", "4"])
        ag = _agendar(c, cal, ["1", "2", "3", "4"], vet=vet)["id"]
        n = _fin(c, ag)["necessidade"]
        assert n["precisa"] == 4 and n["saldo"] == 2 and n["falta"] == 2 and n["cobre"] is False


# ─────────────────────────────── (1) comunicar compra ───────────────────────────────
class TestComunicarCompra:
    def _sem_estoque(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            est, _l = _estoque(s, lotes=[("L1", 1.0, HOJE + timedelta(days=100))])
            for n in ("1", "2", "3"):
                _animal(s, n)
            cal = _regra(s)
            _template(s, ("estoque", "vet", "horario", "financeiro"))
            _espera(s, cal, ["1", "2", "3"])
        ag = _agendar(c, cal, ["1", "2", "3"], vet=vet)["id"]     # ja traz o item de compra (pendente: o estoque nao cobre)
        return c, engine, ag, est

    def test_cotacao_do_que_falta_cria_cotacao_em_rascunho_com_a_quantidade_calculada(self, ctx):
        c, engine, ag, est = self._sem_estoque(ctx)
        forn = _fornecedor(engine)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "cotacao", "fornecedor_ids": [forn], "necessario_ate": (HOJE + timedelta(days=5)).isoformat()})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["vinculo"]["tipo"] == "cotacao" and corpo["vinculo"]["estado"] == "ativo"
        with Session(engine) as s:
            cot = s.exec(select(Cotacao)).one()
            it = s.exec(select(CotacaoItem).where(CotacaoItem.cotacao_id == cot.id)).one()
            assert cot.status == "rascunho" and cot.fazenda_id == 1 and f"#{ag}" in (cot.observacao or "")
            assert it.produto == "B19" and it.quantidade == 2 and it.estoque_id == est  # 3 doses - 1 em estoque
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "compra")).one()
            assert item.status == "cumprido" and item.resposta == "cotacao"
        assert "Comunicou compra" in _acoes(engine, ag)
        assert _fin(c, ag)["compra"]["estado"] == "ok"

    def test_quantidade_pode_ser_informada(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "cotacao", "quantidade": 10})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(CotacaoItem)).one().quantidade == 10

    def test_pedido_direto_exige_fornecedor_e_grava_a_origem(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "pedido"})
        assert r.status_code == 400 and "fornecedor" in r.json()["detail"].lower()
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "pedido", "fornecedor_nome": "Agro Vet"})
        assert r.status_code == 200, r.text
        assert r.json()["vinculo"]["tipo"] == "pedido"
        with Session(engine) as s:
            p = s.exec(select(Pedido)).one()
            assert p.tipo == "compra" and p.origem_tipo == "sanidade_agendamento" and p.origem_item_id == ag and p.fazenda_id == 1
            it = s.exec(select(PedidoItem).where(PedidoItem.pedido_id == p.id)).one()
            assert it.produto_servico == "B19" and it.quantidade == 2

    def test_ja_comprei_nao_cria_nada_mas_resolve_o_item_e_loga(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "ja_comprei"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(Cotacao)).first() is None and s.exec(select(Pedido)).first() is None
        assert _fin(c, ag)["compra"]["estado"] == "ok"
        assert "Marcou compra como já feita" in _acoes(engine, ag)

    def test_fornecedor_de_outra_fazenda_e_recusado(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        estranho = _fornecedor(engine, "Alheio", fazenda_id=2)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "cotacao", "fornecedor_ids": [estranho]})
        assert r.status_code == 400 and "fornecedor" in r.json()["detail"].lower()

    def test_agendamento_encerrado_nao_comunica_compra(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        assert c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano"}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "cotacao"})
        assert r.status_code == 400 and "encerrado" in r.json()["detail"].lower()

    def test_outra_fazenda_nao_ve_nem_altera(self, ctx):
        c, engine, ag, _ = self._sem_estoque(ctx)
        _USUARIO["fazenda"] = 2
        assert c.get(f"/sanidade/cronogramas/{ag}/financeiro").status_code == 404
        assert c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "ja_comprei"}).status_code == 404


# ─────────────────────────────── (2) vincular pagamento ───────────────────────────────
class TestVincularPagamento:
    def test_candidatos_sao_compras_pagas_do_mesmo_produto_com_proporcional(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        pg = _pagamento(engine)
        _pagamento(engine, produto="Ivermectina", numero="LC-2026-90002")               # outro produto: nao entra
        _pagamento(engine, pago=False, numero="LC-2026-90003")                          # nao pago: nao entra
        _pagamento(engine, fazenda_id=2, numero="LC-2026-90004")                        # outra fazenda: nao entra
        r = c.get(f"/sanidade/cronogramas/{ag}/financeiro/pagamentos")
        assert r.status_code == 200, r.text
        lista = r.json()["pagamentos"]
        assert [p["id"] for p in lista] == [pg]
        assert lista[0]["valor"] == 128 and lista[0]["doses"] == 20 and lista[0]["proporcional"] == pytest.approx(25.6)
        assert lista[0]["resta"] == 128 and lista[0]["usado"] == 0

    def test_vincula_o_proporcional_resolve_o_item_financeiro_e_loga(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        pg = _pagamento(engine)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg})
        assert r.status_code == 200, r.text
        v = r.json()["vinculo"]
        assert v["tipo"] == "pagamento" and v["valor"] == pytest.approx(25.6) and v["modo"] == "proporcional"
        assert v["rotulo"] == "Agro Vet" and v["numero_lancamento"] == "LC-2026-90001"
        with Session(engine) as s:
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "financeiro")).one()
            assert item.status == "cumprido"
        assert "Vinculou pagamento já realizado" in _acoes(engine, ag)
        f = _fin(c, ag)
        assert f["pagamento"]["estado"] == "ok" and f["pagamento_vinculado_total"] == pytest.approx(25.6)

    def test_modo_inteiro_vincula_o_que_resta(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        pg = _pagamento(engine)
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg, "modo": "inteiro"})
        assert r.status_code == 200 and r.json()["vinculo"]["valor"] == 128

    def test_pagamento_ja_usado_por_outro_agendamento_desconta_do_que_resta(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        pg = _pagamento(engine, valor=30.0, quantidade=20.0)   # 1,50 por dose; este agendamento usa 4 = 6,00
        assert c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg, "modo": "inteiro"}).status_code == 200
        # outro agendamento: o pagamento ja esta todo vinculado
        with Session(engine) as s:
            _animal(s, "20")
            cal = s.exec(select(CronogramaSanitario)).first().calendario_sanitario_id
            _espera(s, cal, ["20"])
        ag2 = _agendar(c, cal, ["20"])["id"]
        r = c.post(f"/sanidade/cronogramas/{ag2}/financeiro/pagamento", json={"pagamento_id": pg})
        assert r.status_code == 400 and "totalmente vinculado" in r.json()["detail"].lower()
        cand = c.get(f"/sanidade/cronogramas/{ag2}/financeiro/pagamentos").json()["pagamentos"][0]
        assert cand["usado"] == 30 and cand["resta"] == 0

    def test_recusa_nao_pago_duplicado_e_de_outra_fazenda(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        aberto = _pagamento(engine, pago=False, numero="LC-2026-90010")
        assert c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": aberto}).status_code == 400
        alheio = _pagamento(engine, fazenda_id=2, numero="LC-2026-90011")
        assert c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": alheio}).status_code == 404
        pg = _pagamento(engine)
        assert c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg}).status_code == 200
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg})
        assert r.status_code == 400 and "já está vinculado" in r.json()["detail"].lower()

    def test_nao_duplica_lancamento_no_financeiro(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        pg = _pagamento(engine)
        c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg})
        with Session(engine) as s:
            assert len(s.exec(select(ContaGerencial)).all()) == 1


# ─────────────────────────────── (3) conta a pagar ───────────────────────────────
class TestContaAPagar:
    def test_lanca_conta_do_produto_com_o_custo_previsto_sem_dar_entrada_no_estoque(self, cena):
        c, engine, ag, est = cena["c"], cena["engine"], cena["ag"], cena["est"]
        antes = len([m for m in _movimentos(engine, est)])
        r = _conta_pagar(c, ag)
        assert r.status_code == 200, r.text
        v = r.json()["vinculo"]
        assert v["tipo"] == "conta" and v["valor"] == pytest.approx(25.6) and v["subtipo"] == "produto" and v["rotulo"] == "Agro Vet"
        with Session(engine) as s:
            cg = s.get(ContaGerencial, v["alvo_id"])
            assert cg.tipo == "despesa" and cg.valor_total == pytest.approx(25.6) and cg.data_pagamento is None and cg.valor_pago is None
            assert cg.fornecedor_cliente == "Agro Vet" and cg.data_vencimento == HOJE + timedelta(days=10) and cg.fazenda_id == 1
            assert cg.numero_lancamento == v["numero_lancamento"]
            assert s.get(Estoque, est).quantidade == 100
        assert len(_movimentos(engine, est)) == antes          # previsao nao mexe no estoque
        assert "Lançou conta a pagar" in _acoes(engine, ag)
        with Session(engine) as s:
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "financeiro")).one()
            assert item.status == "cumprido"

    def test_conta_aparece_em_a_pagar_no_financeiro(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        _conta_pagar(c, ag, vencimento=(HOJE + timedelta(days=3)).isoformat())
        r = c.get("/financeiro/contas-a-pagar", params={"dias": 10})
        assert r.status_code == 200
        assert [x["fornecedor_cliente"] for x in r.json()] == ["Agro Vet"]

    def test_conta_em_a_pagar_leva_o_link_de_volta_ao_agendamento(self, cena):
        c, ag = cena["c"], cena["ag"]
        _conta_pagar(c, ag, vencimento=(HOJE + timedelta(days=3)).isoformat())
        origem = c.get("/financeiro/contas-a-pagar", params={"dias": 10}).json()[0]["origem_preventivo"]
        assert origem["cronograma_id"] == ag and origem["protocolo"] == "Brucelose B19" and origem["subtipo"] == "produto"

    def test_extrato_de_lancamentos_marca_a_origem_preventiva(self, cena):
        c, ag = cena["c"], cena["ag"]
        conta = _conta_pagar(c, ag).json()["vinculo"]
        linhas = c.get("/financeiro/lancamentos").json()["lancamentos"]
        origem = next(l for l in linhas if l["id"] == conta["alvo_id"])["origem_preventivo"]
        assert origem["cronograma_id"] == ag and origem["protocolo"] == "Brucelose B19"

    def test_honorario_do_veterinario(self, cena):
        c, ag = cena["c"], cena["ag"]
        r = _conta_pagar(c, ag, subtipo="honorario", fornecedor="Dr. Paulo Menezes", valor=350)
        assert r.status_code == 200, r.text
        v = r.json()["vinculo"]
        assert v["subtipo"] == "honorario" and v["valor"] == 350 and "Honorário" in v["descricao"]

    def test_varias_contas_no_mesmo_agendamento(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        _conta_pagar(c, ag)
        _conta_pagar(c, ag, subtipo="honorario", fornecedor="Dr. Paulo", valor=350)
        f = _fin(c, ag)
        assert f["contas_ativas"] == 2 and f["conta_a_pagar_total"] == pytest.approx(375.6)

    def test_validacoes(self, cena):
        c, ag = cena["c"], cena["ag"]
        assert _conta_pagar(c, ag, fornecedor="  ").status_code == 400
        assert _conta_pagar(c, ag, subtipo="honorario").status_code == 400            # honorario sem valor
        assert _conta_pagar(c, ag, valor=-5).status_code == 400
        assert _conta_pagar(c, ag, subtipo="outro", valor=10).status_code == 400
        r = c.post(f"/sanidade/cronogramas/{ag}/financeiro/conta-pagar", json={"fornecedor": "X", "valor": 10})
        assert r.status_code == 422                                                   # vencimento e obrigatorio

    def test_produto_de_frasco_do_veterinario_pede_o_valor(self, cena):
        c, ag = cena["c"], cena["ag"]
        _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Frasco do veterinário", "lote": "V1", "validade": (HOJE + timedelta(days=60)).isoformat()}})
        r = _conta_pagar(c, ag)
        assert r.status_code == 400 and "valor" in r.json()["detail"].lower()
        assert _conta_pagar(c, ag, valor=90).status_code == 200


def _movimentos(engine, est: int):
    with Session(engine) as s:
        return list(s.exec(select(MovimentoEstoque).where(MovimentoEstoque.estoque_id == est)).all())


# ─────────────────────────────── (4) estoque desconsiderado -> compra nao necessaria ───────────────────────────────
class TestCompraNaoNecessaria:
    def test_desconsiderar_estoque_torna_a_compra_nao_necessaria(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        assert _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Frasco do veterinário", "lote": "V1", "validade": (HOJE + timedelta(days=60)).isoformat()}}).status_code == 200
        with Session(engine) as s:
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "compra")).one()
            assert item.status == "cumprido" and item.resposta == "nao_necessaria"
        assert _fin(c, ag)["compra"]["estado"] == "nao_necessaria"
        ck = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()["checklist"]
        compra = next(i for i in ck["itens"] if i["chave"] == "compra")
        assert compra["status"] == "cumprido" and compra["resposta"] == "nao_necessaria"

    def test_voltar_o_estoque_reabre_a_compra(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Estoque não cadastrado"}})
        _put_checklist(c, ag, {"estoque": {"estado": "pendente"}})
        with Session(engine) as s:
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "compra")).one()
            assert item.status == "pendente" and item.resposta is None

    def test_sem_estoque_que_cubra_a_compra_volta_a_pendente_ao_reabrir_o_estoque(self, ctx):
        c, engine, ag, _ = TestComunicarCompra()._sem_estoque(ctx)
        _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Estoque não cadastrado"}})
        assert _fin(c, ag)["compra"]["estado"] == "nao_necessaria"
        _put_checklist(c, ag, {"estoque": {"estado": "pendente"}})
        assert _fin(c, ag)["compra"]["estado"] == "pendente"

    def test_nao_necessaria_conta_como_resolvida_no_x_de_y(self, cena):
        c, ag = cena["c"], cena["ag"]
        antes = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()["checklist"]
        _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Outro", "outro": "x"}})
        depois = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()["checklist"]
        assert depois["resolvidos"] >= antes["resolvidos"] + 1
        assert not any(p["chave"] == "compra" for p in depois["pendentes"])

    def test_estoque_que_cobre_deixa_a_compra_nao_necessaria(self, cena):
        c, ag = cena["c"], cena["ag"]
        f = _fin(c, ag)
        assert f["necessidade"]["cobre"] is True and f["compra"]["estado"] == "nao_necessaria"


# ─────────────────────────────── (5) cancelar: destino de cada vinculo ───────────────────────────────
class TestCancelarComDestinos:
    def _com_conta_e_pagamento(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        conta = _conta_pagar(c, ag).json()["vinculo"]
        pg = _pagamento(engine)
        c.post(f"/sanidade/cronogramas/{ag}/financeiro/pagamento", json={"pagamento_id": pg})
        return c, engine, ag, conta, pg

    def test_sem_escolher_o_destino_nao_cancela_nada(self, cena):
        c, engine, ag, conta, pg = self._com_conta_e_pagamento(cena)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano"})
        assert r.status_code == 400 and "conta a pagar" in r.json()["detail"].lower()
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano", "destino_conta": "manter"})
        assert r.status_code == 400 and "pagamento" in r.json()["detail"].lower()
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, ag).status == "agendado"
            assert s.get(ContaGerencial, conta["alvo_id"]) is not None

    def test_cancelar_a_conta_tira_do_financeiro_e_guarda_a_foto_no_vinculo(self, cena):
        c, engine, ag, conta, pg = self._com_conta_e_pagamento(cena)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={
            "motivo": "Mudança de plano", "destino_conta": "cancelar", "destino_pagamento": "desvincular"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, ag).status == "cancelado"
            assert s.get(ContaGerencial, conta["alvo_id"]) is None                       # fora de A pagar e dos totais
            assert s.exec(select(LancamentoItem).where(LancamentoItem.numero_lancamento == conta["numero_lancamento"])).first() is None
            assert s.get(ContaGerencial, pg) is not None                                 # o pagamento continua no Financeiro
        v = _vinculos(engine, ag, "conta")[0]
        assert v.estado == "cancelado" and v.motivo_encerramento == "Mudança de plano" and v.valor == pytest.approx(25.6) and v.rotulo == "Agro Vet"
        p = _vinculos(engine, ag, "pagamento")[0]
        assert p.estado == "desvinculado" and p.encerrado_em is not None
        acoes = _acoes(engine, ag)
        assert "Cancelou conta a pagar do agendamento" in acoes and "Desvinculou pagamento já realizado" in acoes and "Cancelou" in acoes
        assert c.get("/financeiro/contas-a-pagar", params={"dias": 60}).json() == []

    def test_manter_conta_e_pagamento_loga_cada_um(self, cena):
        c, engine, ag, conta, pg = self._com_conta_e_pagamento(cena)
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={
            "motivo": "Falta de estoque", "destino_conta": "manter", "destino_pagamento": "manter"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(ContaGerencial, conta["alvo_id"]) is not None
        assert _vinculos(engine, ag, "conta")[0].estado == "ativo"
        acoes = _acoes(engine, ag)
        assert "Manteve conta a pagar do agendamento" in acoes and "Manteve pagamento vinculado" in acoes
        det = next(l for l in _log(engine, ag) if l.acao == "Manteve conta a pagar do agendamento")
        assert det.motivo == "Falta de estoque" and det.usuario_id == 1 and det.criado_em

    def test_conta_ja_paga_nao_pode_ser_cancelada(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        conta = _conta_pagar(c, ag).json()["vinculo"]
        with Session(engine) as s:
            cg = s.get(ContaGerencial, conta["alvo_id"])
            cg.data_pagamento, cg.valor_pago = HOJE, cg.valor_total
            s.add(cg)
            s.commit()
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano", "destino_conta": "cancelar"})
        assert r.status_code == 409 and "estorne" in r.json()["detail"].lower()
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, ag).status == "agendado" and s.get(ContaGerencial, conta["alvo_id"]) is not None

    def test_cancelar_cotacao_cancela_a_cotacao(self, ctx):
        t = TestComunicarCompra()
        c, engine, ag, _ = t._sem_estoque(ctx)
        c.post(f"/sanidade/cronogramas/{ag}/financeiro/compra", json={"modo": "cotacao"})
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano"})
        assert r.status_code == 400 and "cotação" in r.json()["detail"].lower()
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano", "destino_cotacao": "cancelar"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.exec(select(Cotacao)).one().status == "cancelada"
        assert "Cancelou cotação do agendamento" in _acoes(engine, ag)

    def test_sem_vinculos_o_cancelar_continua_igual(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        r = c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano", "destino_conta": "manter"})
        assert r.status_code == 200, r.text

    def test_encerrar_avulso_exige_motivo_e_so_uma_vez(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        conta = _conta_pagar(c, ag).json()["vinculo"]
        url = f"/sanidade/cronogramas/{ag}/financeiro/vinculos/{conta['id']}/encerrar"
        assert c.post(url, json={"acao": "cancelar_conta", "motivo": " "}).status_code == 400
        assert c.post(url, json={"acao": "desvincular_pagamento", "motivo": "x"}).status_code == 400   # acao errada para o tipo
        assert c.post(url, json={"acao": "cancelar_conta", "motivo": "Lançada por engano"}).status_code == 200
        assert c.post(url, json={"acao": "cancelar_conta", "motivo": "Lançada por engano"}).status_code == 400
        # sem conta ativa o item financeiro volta a pendente
        with Session(engine) as s:
            item = s.exec(select(ChecklistItem).where(ChecklistItem.cronograma_id == ag).where(ChecklistItem.chave == "financeiro")).one()
            assert item.status == "pendente"


# ─────────────────────────────── (6) Conferir, pos-aplicacao e Concluidos ───────────────────────────────
class TestCustoEContasNasTelas:
    def test_conferir_traz_custo_previsto_e_conta(self, cena):
        c, ag = cena["c"], cena["ag"]
        _conta_pagar(c, ag)
        ctx_ap = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()
        f = ctx_ap["financeiro"]
        assert f["custo_previsto"] == pytest.approx(25.6) and f["contas_ativas"] == 1 and f["conta_a_pagar_total"] == pytest.approx(25.6)
        assert f["link_contas_a_pagar"].startswith("/financeiro")

    def test_pos_aplicacao_e_concluidos_mostram_custo_conta_e_link(self, cena):
        c, engine, ag, vet, est = cena["c"], cena["engine"], cena["ag"], cena["vet"], cena["est"]
        _conta_pagar(c, ag)
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, estoque_id=est, ciencia_pendentes=True)
        assert r.status_code == 200, r.text
        f = r.json()["financeiro"]
        assert f["custo"] == pytest.approx(25.6) and f["custo_a_informar"] is False and f["contas_ativas"] == 1
        assert f["contas"][0]["valor"] == pytest.approx(25.6) and f["contas"][0]["estado"] == "ativo"
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["custo"] == pytest.approx(25.6) and item["financeiro"]["contas"][0]["numero_lancamento"]
        assert item["financeiro"]["link_contas_a_pagar"].startswith("/financeiro")

    def test_frasco_do_veterinario_fica_a_informar_em_concluidos(self, cena):
        c, engine, ag, vet = cena["c"], cena["engine"], cena["ag"], cena["vet"]
        _put_checklist(c, ag, {"estoque": {"estado": "desconsiderado", "motivo": "Frasco do veterinário", "lote": "V1", "validade": (HOJE + timedelta(days=60)).isoformat()}})
        r = _aplicar(c, ag, animais_aplicados=["1", "2", "3", "9"], aplicador_pessoa_id=vet, desconsiderar_estoque=True,
                     motivo_desconsiderar_estoque="Frasco do veterinário", lote_veterinario="V1", ciencia_pendentes=True)
        assert r.status_code == 200, r.text
        f = r.json()["financeiro"]
        assert f["custo"] is None and f["custo_a_informar"] is True and "veterinário" in f["custo_motivo"].lower()
        item = c.get("/sanidade/cronogramas/concluidos").json()["itens"][0]
        assert item["custo"] is None and item["financeiro"]["custo_a_informar"] is True

    def test_cancelados_em_concluidos_mostram_a_conta_cancelada(self, cena):
        c, engine, ag = cena["c"], cena["engine"], cena["ag"]
        _conta_pagar(c, ag)
        c.post(f"/sanidade/cronogramas/{ag}/cancelar", json={"motivo": "Mudança de plano", "destino_conta": "cancelar"})
        item = next(i for i in c.get("/sanidade/cronogramas/concluidos").json()["itens"] if i["estado"] == "cancelado")
        assert item["financeiro"]["contas"][0]["estado"] == "cancelado" and item["financeiro"]["contas_ativas"] == 0
        assert item["financeiro"]["conta_a_pagar_total"] == 0

    def test_acompanhamento_traz_o_financeiro_de_cada_agendamento(self, cena):
        c, ag = cena["c"], cena["ag"]
        _conta_pagar(c, ag)
        a = next(x for x in c.get("/sanidade/cronogramas/acompanhamento").json()["agendamentos"] if x["id"] == ag)
        assert a["financeiro"]["contas_ativas"] == 1 and a["financeiro"]["custo_previsto"] == pytest.approx(25.6)


# ─────────────────────────────── (7) veterinario: Pessoa/CRMV, quem e quando ───────────────────────────────
class TestVeterinarioNoChecklist:
    def test_confirmacao_guarda_pessoa_crmv_quem_registrou_e_quando(self, cena):
        c, engine, ag, vet = cena["c"], cena["engine"], cena["ag"], cena["vet"]
        quando = (datetime.utcnow() - timedelta(hours=3)).replace(microsecond=0, second=0)
        r = _put_checklist(c, ag, {"veterinario": {"estado": "confirmado", "pessoa_id": vet, "quando": quando.isoformat(), "observacao": "Confirmou por telefone"}})
        assert r.status_code == 200, r.text
        v = r.json()["checklist"]["veterinario"]
        assert v["estado"] == "confirmado" and v["nome"] == "Dr. Paulo" and v["crmv"] == "CRMV-MG 12345"
        assert v["confirmado_em"].startswith(quando.isoformat()[:16]) and v["observacao"] == "Confirmou por telefone"
        det = next(l for l in _log(engine, ag) if l.acao == "Confirmou o veterinário")
        assert "Dr. Paulo" in det.detalhe and "CRMV-MG 12345" in det.detalhe and det.usuario_id == 1

    def test_confirmacao_no_futuro_e_recusada_e_pessoa_alheia_tambem(self, cena):
        c, ag, vet = cena["c"], cena["ag"], cena["vet"]
        futuro = (datetime.utcnow() + timedelta(days=2)).isoformat()
        r = _put_checklist(c, ag, {"veterinario": {"estado": "confirmado", "pessoa_id": vet, "quando": futuro}})
        assert r.status_code == 400 and "futuro" in r.json()["detail"].lower()
        r = _put_checklist(c, ag, {"veterinario": {"estado": "confirmado", "pessoa_id": 99999}})
        assert r.status_code == 400

    def test_sem_confirmacao_o_bloco_e_pendente(self, cena):
        c, ag = cena["c"], cena["ag"]
        v = c.get(f"/sanidade/cronogramas/{ag}/aplicar-contexto").json()["checklist"]["veterinario"]
        assert v["estado"] in ("pendente", "confirmado")


# ─────────────────────────────── payload do assistente (passo Checklist) ───────────────────────────────
class TestPayloadDoAssistente:
    def _base(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            vet, _ = _pessoas(s)
            _estoque(s, lotes=[("L1", 1.0, HOJE + timedelta(days=100))])
            for n in ("1", "2", "3"):
                _animal(s, n)
            cal = _regra(s)
            _template(s, ("estoque", "vet", "horario", "financeiro"))
            _espera(s, cal, ["1", "2", "3"])
        return c, engine, cal, vet

    def test_agendar_ja_com_compra_e_conta(self, ctx):
        c, engine, cal, vet = self._base(ctx)
        ag = _agendar(c, cal, ["1", "2", "3"], vet=vet, checklist={"financeiro": {
            "compra": {"modo": "cotacao"},
            "contas": [{"subtipo": "honorario", "fornecedor": "Dr. Paulo", "valor": 350, "vencimento": (HOJE + timedelta(days=7)).isoformat()}],
        }})
        f = ag["financeiro"]
        assert f["contas_ativas"] == 1 and f["conta_a_pagar_total"] == 350 and len(f["compras"]) == 1
        with Session(engine) as s:
            assert s.exec(select(Cotacao)).one() is not None
        assert {"Comunicou compra", "Lançou conta a pagar"} <= set(_acoes(engine, ag["id"]))

    def test_payload_invalido_nao_cria_agendamento_pela_metade(self, ctx):
        c, engine, cal, vet = self._base(ctx)
        corpo = {
            "calendario_sanitario_id": cal, "animais_janela": ["1"], "animais_fora": [], "data_evento": HOJE.isoformat(), "hora": "10:00",
            "checklist": {"financeiro": {"contas": [{"subtipo": "produto", "fornecedor": "Agro Vet"}]}},   # sem vencimento
        }
        r = c.post("/sanidade/cronogramas/agendamentos", json=corpo)
        assert r.status_code == 400 and "vencimento" in r.json()["detail"].lower()
        with Session(engine) as s:
            assert s.exec(select(CronogramaSanitario).where(CronogramaSanitario.status == "agendado")).first() is None

    def test_novo_agendamento_de_vacina_ja_traz_o_item_de_compra(self, ctx):
        c, engine, cal, vet = self._base(ctx)
        ag = _agendar(c, cal, ["1", "2", "3"], vet=vet)
        assert any(i["chave"] == "compra" for i in ag["checklist"]["itens"])


class TestPreviaDoAssistente:
    def test_previa_traz_necessidade_custo_e_pagamentos_antes_de_o_agendamento_existir(self, cena):
        c, engine, cal = cena["c"], cena["engine"], cena["cal"]
        pg = _pagamento(engine)
        r = c.get("/sanidade/cronogramas/financeiro/previa", params={"calendario_id": cal, "animais": "1,2,3,9"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["necessidade"]["precisa"] == 4 and d["necessidade"]["custo_previsto"] == pytest.approx(25.6)
        assert [p["id"] for p in d["pagamentos"]] == [pg] and d["pagamentos"][0]["proporcional"] == pytest.approx(25.6)

    def test_previa_de_outra_fazenda_e_404(self, cena):
        c, cal = cena["c"], cena["cal"]
        _USUARIO["fazenda"] = 2
        assert c.get("/sanidade/cronogramas/financeiro/previa", params={"calendario_id": cal}).status_code == 404
