"""
Vale de funcionário: as quatro ações do dono dentro da Folha, o vale PARCIAL
no lançamento financeiro, e as duas portas que deixavam um holerite já pago
passar a mentir.

O QUE ESTE ARQUIVO COBRE, e por que cada bloco existe:

 A) `POST /cadastro/vales/{id}/acoes` — reparcelar o saldo, abater um valor,
    desconsiderar o vale de UM mês e cancelar o vale inteiro. As duas últimas
    têm um efeito que não é da folha e sim do Financeiro (decisão textual do
    dono: "Desconsiderar o vale faz a conta passar a ser da fazenda... e
    comunicar com o financeiro completo"), então cada uma é checada NOS DOIS
    lados: a folha deixa de descontar E o valor vira despesa da fazenda.

 B) Vale PARCIAL no item da nota — "2/3 do preço da ração de cachorro é do
    funcionário, 1/3 eu que pago". O que se mede aqui não é só o valor do
    vale: é que a sobra virou um item NORMAL, com a mesma conta gerencial e o
    mesmo centro de custo da nota, e que ela voltou a contar nos relatórios
    gerenciais (é justamente o que `sem_itens_de_vale` tira quando o item é
    vale).

 C) As duas portas: lançar vale numa competência JÁ PAGA, e mover um vale
    existente PARA uma competência já paga. Nos dois casos a folha paga é
    imutável (a discriminação dela foi congelada no pagamento), então a
    parcela nova entrava no banco e o recibo daquele mês passava a cobrar um
    desconto que nunca foi descontado.

TOKEN DE VERDADE em tudo (`criar_token`), nunca `dependency_overrides` do
`get_fazenda_atual_id`: o isolamento entre fazendas depende da claim do token
e das próprias consultas, e falsificar a claim tiraria do teste exatamente o
que ele precisa provar (ver o bloco de isolamento no fim).
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
    ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, LancamentoItem,
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
        # salário alto de propósito: o teto de 40% (R$ 2.000) não pode ser o
        # que faz um teste de ação de vale falhar.
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


# ── helpers de escrita ─────────────────────────────────────────────────────
def _criar_vale(
    c, *, pessoa_id: int = 1, valor: float = 900.0, parcelas: int = 3,
    competencia: str = "2026-07", conta_id: int | None = 1, headers: dict | None = None,
    forma: str = "pix",
) -> dict:
    resposta = c.post("/cadastro/vales", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "valor_total": valor, "forma_pagamento": forma,
        "data_pagamento": "2026-06-10", "parcelas": parcelas, "competencia_inicio": competencia,
        "conta_corrente_id": conta_id, "observacao": "mercado",
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _criar_folha(c, *, pessoa_id: int = 1, competencia: str, bruto: float = 3000.0,
                 paga: bool = False, headers: dict | None = None) -> dict:
    corpo = {"pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": bruto}
    if paga:
        corpo.update({"status": "pago", "data_pagamento": f"{competencia}-28"})
    resposta = c.post("/cadastro/folha-pagamento", headers=headers or _cab(), json=corpo)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _folha(c, competencia: str, pessoa_id: int = 1, headers: dict | None = None) -> dict:
    resposta = c.get("/cadastro/folha-pagamento", headers=headers or _cab())
    assert resposta.status_code == 200, resposta.text
    return next(
        r for r in resposta.json() if r["pessoa_id"] == pessoa_id and r["competencia"] == competencia
    )


def _acao(c, vale_id: int, corpo: dict, headers: dict | None = None):
    return c.post(f"/cadastro/vales/{vale_id}/acoes", headers=headers or _cab(), json=corpo)


def _parcelas(engine, vale_id: int) -> list[ValeParcela]:
    with Session(engine) as s:
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
        return sorted(parcelas, key=lambda p: (p.competencia, p.id or 0))


def _itens(engine, numero_lancamento: str) -> list[LancamentoItem]:
    with Session(engine) as s:
        itens = s.exec(
            select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero_lancamento)
        ).all()
        return sorted(itens, key=lambda i: i.id or 0)


def _lancamento_com_vale(c, *, vale: dict, valor_item: float = 300.0, quantidade: float = 3.0,
                         headers: dict | None = None):
    """Uma nota de UM item (ração), com o item marcado como vale."""
    return c.post("/financeiro/lancamentos", headers=headers or _cab(), json={
        "tipo": "despesa",
        "data_emissao": "2026-06-10",
        "centro_custo": "Pecuária Leiteira",
        "itens": [{
            "produto": "Ração para cães 15kg",
            "tipo_item": "produto",
            "codigo_conta_gerencial": "3.01.05",
            "nome_conta_gerencial": "Diversos",
            "quantidade": quantidade,
            "valor_unitario": round(valor_item / quantidade, 2),
            "valor_total": valor_item,
            "vale": vale,
        }],
    })


# ===========================================================================
# A) As quatro ações do dono
# ===========================================================================
class TestReparcelarSaldo:
    def test_reparcela_o_saldo_pendente_nas_competencias_novas(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)  # 900 em 3x: 07, 08, 09

        resposta = _acao(c, vale["id"], {
            "acao": "reparcelar", "parcelas": 2, "competencia_inicio": "2026-10",
        })
        assert resposta.status_code == 200, resposta.text

        parcelas = _parcelas(engine, vale["id"])
        assert [p.competencia for p in parcelas] == ["2026-10", "2026-11"]
        assert [p.valor for p in parcelas] == [450.0, 450.0]

    def test_o_que_ja_caiu_em_folha_paga_nao_entra_no_saldo(self, ambiente):
        """Reparcelar mexe no SALDO, não no valor do vale: a parcela de julho
        já foi descontada de um pagamento que saiu e não volta atrás."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {
            "acao": "reparcelar", "parcelas": 2, "competencia_inicio": "2026-11",
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["saldo_reparcelado"] == 600.0

        parcelas = _parcelas(engine, vale["id"])
        assert [p.competencia for p in parcelas] == ["2026-07", "2026-11", "2026-12"]
        assert [p.valor for p in parcelas] == [300.0, 300.0, 300.0]

    def test_reparcelar_para_dentro_de_competencia_paga_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c, competencia="2026-08")
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {
            "acao": "reparcelar", "parcelas": 3, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"]

    def test_sem_saldo_pendente_nao_reparcela(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c, valor=300.0, parcelas=1)
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {"acao": "reparcelar", "parcelas": 2})
        assert resposta.status_code == 400
        assert "saldo pendente" in resposta.json()["detail"]


class TestAbaterDoVale:
    def test_abatimento_reduz_o_saldo_e_a_folha_desconta_menos(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)                      # 900 em 3x (300/mês)
        _criar_folha(c, competencia="2026-07")     # pendente
        assert _folha(c, "2026-07")["valor_vale"] == 300.0

        resposta = _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["saldo_apos"] == 600.0

        assert [p.valor for p in _parcelas(engine, vale["id"])] == [200.0, 200.0, 200.0]
        folha = _folha(c, "2026-07")
        assert folha["valor_vale"] == 200.0
        assert folha["valor_liquido"] == 2800.0

        with Session(engine) as s:
            registro = s.get(ValeFuncionario, vale["id"])
            assert registro.valor_abatido == 300.0
            # `valor_total` é o valor efetivamente adiantado — histórico, não
            # se reescreve (mesma regra de `editar_parcela_vale`).
            assert registro.valor_total == 900.0

    def test_devolucao_em_dinheiro_entra_no_caixa(self, ambiente):
        """Sem este lançamento o caixa fica furado: a fazenda desembolsou o
        vale inteiro, deixa de recuperar parte na folha, e o dinheiro que o
        funcionário devolveu não aparece em lugar nenhum."""
        c, engine = ambiente
        vale = _criar_vale(c)

        resposta = _acao(c, vale["id"], {"acao": "abater", "valor": 150.0, "conta_corrente_id": 1})
        assert resposta.status_code == 200, resposta.text
        numero = resposta.json()["numero_lancamento_devolucao"]
        assert numero

        with Session(engine) as s:
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first()
            assert conta.tipo == "receita"
            assert conta.valor_total == 150.0
            assert conta.valor_pago == 150.0
            assert conta.fazenda_id == 1

    def test_abatimento_sem_conta_bancaria_nao_lanca_nada(self, ambiente):
        """Abatimento que é perdão/concessão não teve dinheiro voltando —
        inventar uma entrada ali seria pior que não ter nenhuma."""
        c, engine = ambiente
        vale = _criar_vale(c)
        resposta = _acao(c, vale["id"], {"acao": "abater", "valor": 150.0})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["numero_lancamento_devolucao"] is None

    def test_abatimento_maior_que_o_saldo_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        resposta = _acao(c, vale["id"], {"acao": "abater", "valor": 1200.0})
        assert resposta.status_code == 400
        assert "maior que o saldo" in resposta.json()["detail"]

    def test_abater_o_saldo_inteiro_zera_as_parcelas_pendentes(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        resposta = _acao(c, vale["id"], {"acao": "abater", "valor": 900.0})
        assert resposta.status_code == 200, resposta.text
        # Parcela de R$ 0,00 vira ruído no holerite — some.
        assert _parcelas(engine, vale["id"]) == []


class TestDesconsiderarOMes:
    def test_o_mes_desconsiderado_sai_do_desconto_e_a_parcela_fica_marcada(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        assert _folha(c, "2026-07")["valor_vale"] == 300.0

        resposta = _acao(c, vale["id"], {
            "acao": "desconsiderar_mes", "competencia": "2026-07", "motivo": "quebrou o trator dele",
        })
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["valor_assumido"] == 300.0

        folha = _folha(c, "2026-07")
        assert folha["valor_vale"] == 0.0
        assert folha["valor_liquido"] == 3000.0, "o funcionário passa a receber o salário cheio"
        # A parcela NÃO é apagada: é ela que explica, no histórico do mês, por
        # que o desconto sumiu.
        parcela_julho = next(p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07")
        assert parcela_julho.assumida_pela_fazenda is True
        assert parcela_julho.motivo_assuncao == "quebrou o trator dele"
        assert parcela_julho.valor == 300.0

    def test_o_mes_desconsiderado_nao_vira_linha_de_desconto_no_holerite(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})

        folha = _folha(c, "2026-07")
        assert [d for d in folha["detalhe"] if d["tipo"] == "vale"] == []
        assert folha["totais"]["liquido"] == 3000.0

    def test_os_meses_seguintes_continuam_sendo_descontados(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _criar_folha(c, competencia="2026-08")
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})

        assert _folha(c, "2026-07")["valor_vale"] == 0.0
        assert _folha(c, "2026-08")["valor_vale"] == 300.0, "desconsiderar é do MÊS, não do vale"

    def test_desconsiderar_mes_com_folha_paga_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"]

    def test_vale_de_item_desconsiderado_por_inteiro_volta_a_ser_despesa_da_fazenda(self, ambiente):
        """O vale nasceu de um item de nota, que hoje está FORA dos relatórios
        gerenciais por ser vale. Desconsiderar tudo devolve o item aos
        relatórios — é literalmente "a conta passa a ser da fazenda"."""
        c, engine = ambiente
        resposta = _lancamento_com_vale(c, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 201, resposta.text
        numero = resposta.json()["numero_lancamento"]
        vale_id = resposta.json()["vales_criados"][0]["vale_id"]

        acao = _acao(c, vale_id, {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert acao.status_code == 200, acao.text
        assert acao.json()["financeiro"]["natureza"] == "item_de_nota"

        itens = _itens(engine, numero)
        assert len(itens) == 1, "não há o que dividir: a fazenda assumiu o item inteiro"
        assert itens[0].vale_funcionario_id is None
        assert itens[0].valor_total == 300.0

    def test_vale_de_item_desconsiderado_em_parte_divide_o_item(self, ambiente):
        """Vale de item em 2 parcelas com só um mês desconsiderado: metade
        continua sendo cobrada do funcionário e metade vira despesa da
        fazenda — o item se divide, com a mesma conta gerencial e o mesmo
        centro de custo, porque é a mesma compra."""
        c, engine = ambiente
        resposta = _lancamento_com_vale(c, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 2, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 201, resposta.text
        numero = resposta.json()["numero_lancamento"]
        vale_id = resposta.json()["vales_criados"][0]["vale_id"]

        acao = _acao(c, vale_id, {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert acao.status_code == 200, acao.text
        assert acao.json()["financeiro"]["itens"][0]["dividido"] is True

        itens = _itens(engine, numero)
        assert len(itens) == 2
        do_vale = next(i for i in itens if i.vale_funcionario_id is not None)
        da_fazenda = next(i for i in itens if i.vale_funcionario_id is None)
        assert do_vale.valor_total == 150.0
        assert da_fazenda.valor_total == 150.0
        assert da_fazenda.codigo_conta_gerencial == "3.01.05"
        assert da_fazenda.centro_custo == do_vale.centro_custo
        assert round(sum(i.valor_total for i in itens), 2) == 300.0, "a nota tem de continuar fechando"


class TestCancelarOVale:
    def test_cancelar_tira_o_saldo_inteiro_da_cobranca_do_funcionario(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _criar_folha(c, competencia="2026-08")

        resposta = _acao(c, vale["id"], {"acao": "cancelar", "motivo": "acordo na saída"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["valor_assumido"] == 900.0

        assert _folha(c, "2026-07")["valor_vale"] == 0.0
        assert _folha(c, "2026-08")["valor_vale"] == 0.0
        assert all(p.assumida_pela_fazenda for p in _parcelas(engine, vale["id"]))
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]).status == "cancelado"

    def test_o_que_ja_foi_descontado_em_folha_paga_continua_descontado(self, ambiente):
        """Cancelar não devolve dinheiro que já saiu: o holerite de julho é
        recibo. A resposta diz quais competências ficaram de fora para o dono
        não achar que o cancelamento reverteu tudo."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {"acao": "cancelar"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["valor_assumido"] == 600.0
        assert resposta.json()["competencias_ja_descontadas"] == ["2026-07"]

        parcela_julho = next(p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07")
        assert parcela_julho.assumida_pela_fazenda is False

    def test_o_lancamento_do_vale_deixa_de_ser_vale_e_vira_despesa_da_fazenda(self, ambiente):
        """O vale saiu do caixa por pix e tem lançamento próprio, marcado como
        "Vale de funcionário" (tipo de baixa espelhada que o Financeiro nem
        deixa estornar). Cancelado o vale, aquele desembolso passa a ser uma
        despesa comum da fazenda — e o rótulo tem de dizer isso."""
        c, engine = ambiente
        vale = _criar_vale(c)
        with Session(engine) as s:
            numero = s.get(ValeFuncionario, vale["id"]).numero_lancamento_gerado
        assert numero

        resposta = _acao(c, vale["id"], {"acao": "cancelar"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["financeiro"]["reclassificado"] is True

        with Session(engine) as s:
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first()
            assert conta.tipo_documento == "Recibo"
            assert "assumida pela fazenda" in conta.descricao
            assert conta.valor_total == 900.0, "a saída de caixa aconteceu e não pode sumir"

    def test_cancelar_duas_vezes_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        assert _acao(c, vale["id"], {"acao": "cancelar"}).status_code == 200
        segunda = _acao(c, vale["id"], {"acao": "cancelar"})
        assert segunda.status_code == 400
        assert "já foi cancelado" in segunda.json()["detail"]

    def test_vale_cancelado_nao_pode_mais_ser_editado_nem_excluido(self, ambiente):
        """Editar recriaria as parcelas (apagando a marca de assumido) e
        excluir apagaria o lançamento de caixa que agora sustenta uma despesa
        da fazenda — os dois deixariam os dois lados divergentes."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "cancelar"})

        edicao = c.put(f"/cadastro/vales/{vale['id']}", headers=_cab(), json={
            "pessoa_id": 1, "valor_total": 900.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-10", "parcelas": 3, "competencia_inicio": "2026-07",
            "conta_corrente_id": 1,
        })
        assert edicao.status_code == 400
        exclusao = c.delete(f"/cadastro/vales/{vale['id']}", headers=_cab())
        assert exclusao.status_code == 400


class TestAcaoInvalida:
    def test_acao_desconhecida_e_recusada(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        resposta = _acao(c, vale["id"], {"acao": "apagar_tudo"})
        assert resposta.status_code == 400
        assert "Ação inválida" in resposta.json()["detail"]


# ===========================================================================
# B) Vale integral × vale parcial no lançamento financeiro
# ===========================================================================
class TestValeParcial:
    def test_percentual_divide_o_item_e_a_sobra_vira_despesa_da_fazenda(self, ambiente):
        """O caso do dono: 2/3 da ração são do funcionário, 1/3 é dele."""
        c, engine = ambiente
        resposta = _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
            "abrangencia": "parcial", "percentual": 66.67,
        })
        assert resposta.status_code == 201, resposta.text
        numero = resposta.json()["numero_lancamento"]

        itens = _itens(engine, numero)
        assert len(itens) == 2
        do_vale = next(i for i in itens if i.vale_funcionario_id is not None)
        da_fazenda = next(i for i in itens if i.vale_funcionario_id is None)
        assert do_vale.valor_total == 200.01
        assert da_fazenda.valor_total == 99.99
        assert round(sum(i.valor_total for i in itens), 2) == 300.0
        # A sobra é a mesma compra: herda conta gerencial e centro de custo.
        assert da_fazenda.codigo_conta_gerencial == "3.01.05"
        assert da_fazenda.nome_conta_gerencial == "Diversos"
        assert da_fazenda.centro_custo == do_vale.centro_custo
        # E a quantidade acompanha o valor (2/3 dos quilos, 1/3 dos quilos).
        assert round(do_vale.quantidade + da_fazenda.quantidade, 4) == 3.0

        with Session(engine) as s:
            vale = s.get(ValeFuncionario, resposta.json()["vales_criados"][0]["vale_id"])
            assert vale.valor_total == 200.01, "o vale cobra só a parte do funcionário"

    def test_valor_em_reais_divide_o_item_do_mesmo_jeito(self, ambiente):
        c, engine = ambiente
        resposta = _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
            "abrangencia": "parcial", "valor": 120.0,
        })
        assert resposta.status_code == 201, resposta.text
        itens = _itens(engine, resposta.json()["numero_lancamento"])
        do_vale = next(i for i in itens if i.vale_funcionario_id is not None)
        da_fazenda = next(i for i in itens if i.vale_funcionario_id is None)
        assert do_vale.valor_total == 120.0
        assert da_fazenda.valor_total == 180.0

    def test_a_folha_desconta_so_a_parte_do_funcionario(self, ambiente):
        c, engine = ambiente
        _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
            "abrangencia": "parcial", "valor": 120.0,
        })
        _criar_folha(c, competencia="2026-07")
        folha = _folha(c, "2026-07")
        assert folha["valor_vale"] == 120.0
        assert folha["valor_liquido"] == 2880.0

    def test_a_sobra_volta_a_contar_nos_relatorios_gerenciais(self, ambiente):
        """`sem_itens_de_vale` tira do gerencial a LINHA inteira que é vale —
        é por isso que a divisão é em duas linhas e não numa coluna: assim a
        parte da fazenda continua sendo somada por todo relatório, sem que
        nenhum deles precise aprender a subtrair uma fração."""
        c, engine = ambiente
        from fazenda.rules.vale_item import sem_itens_de_vale

        resposta = _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
            "abrangencia": "parcial", "valor": 120.0,
        })
        numero = resposta.json()["numero_lancamento"]
        with Session(engine) as s:
            gerenciais = s.exec(
                sem_itens_de_vale(select(LancamentoItem)).where(
                    LancamentoItem.numero_lancamento == numero
                )
            ).all()
        assert round(sum(i.valor_total for i in gerenciais), 2) == 180.0

    def test_integral_continua_sendo_o_padrao_e_nao_divide_nada(self, ambiente):
        c, engine = ambiente
        resposta = _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 201, resposta.text
        itens = _itens(engine, resposta.json()["numero_lancamento"])
        assert len(itens) == 1
        assert itens[0].vale_funcionario_id is not None
        assert itens[0].valor_total == 300.0

    @pytest.mark.parametrize("vale_parcial, trecho_erro", [
        ({"abrangencia": "parcial"}, "percentual OU o valor"),
        ({"abrangencia": "parcial", "percentual": 50.0, "valor": 100.0}, "percentual OU o valor"),
        ({"abrangencia": "parcial", "percentual": 100.0}, "entre 0 e 100"),
        ({"abrangencia": "parcial", "percentual": 0.0}, "entre 0 e 100"),
        ({"abrangencia": "parcial", "valor": 300.0}, "menor que o valor do item"),
        ({"abrangencia": "parcial", "valor": 400.0}, "menor que o valor do item"),
        ({"abrangencia": "metade"}, "Abrangência do vale inválida"),
    ])
    def test_parcial_mal_informado_e_recusado_sem_gravar_nada(self, ambiente, vale_parcial, trecho_erro):
        c, engine = ambiente
        corpo_vale = {
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
            **vale_parcial,
        }
        resposta = _lancamento_com_vale(c, valor_item=300.0, quantidade=3.0, vale=corpo_vale)
        assert resposta.status_code == 400, resposta.text
        assert trecho_erro in resposta.json()["detail"]
        with Session(engine) as s:
            assert s.exec(select(LancamentoItem)).all() == [], "a nota inteira tem de ser recusada antes de gravar"


# ===========================================================================
# C) As duas portas abertas
# ===========================================================================
class TestCompetenciaJaPaga:
    def test_lancar_vale_em_competencia_paga_e_recusado(self, ambiente):
        """PORTA 1: `criar_vale` nunca olhou a competência de DESTINO. A
        parcela entrava no banco e o holerite já pago passava a mostrar um
        desconto que não foi descontado do dinheiro que saiu."""
        c, engine = ambiente
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = c.post("/cadastro/vales", headers=_cab(), json={
            "pessoa_id": 1, "valor_total": 500.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
            "conta_corrente_id": 1,
        })
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"]
        assert "já foi paga" in resposta.json()["detail"]
        with Session(engine) as s:
            assert s.exec(select(ValeParcela)).all() == []

    def test_vale_parcelado_que_alcanca_competencia_paga_e_recusado(self, ambiente):
        """A trava é por competência, não só pela primeira: um vale que começa
        num mês aberto e ESTICA até um mês pago também mente no holerite."""
        c, engine = ambiente
        _criar_folha(c, competencia="2026-09", paga=True)

        resposta = c.post("/cadastro/vales", headers=_cab(), json={
            "pessoa_id": 1, "valor_total": 900.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-10", "parcelas": 3, "competencia_inicio": "2026-07",
            "conta_corrente_id": 1,
        })
        assert resposta.status_code == 400, resposta.text
        assert "2026-09" in resposta.json()["detail"]

    def test_mover_vale_para_competencia_paga_e_recusado(self, ambiente):
        """PORTA 2: `atualizar_vale` só olhava as competências ATUAIS do vale
        — mover o `competencia_inicio` para dentro de um mês pago passava."""
        c, engine = ambiente
        vale = _criar_vale(c, valor=300.0, parcelas=1, competencia="2026-08")
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = c.put(f"/cadastro/vales/{vale['id']}", headers=_cab(), json={
            "pessoa_id": 1, "valor_total": 300.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
            "conta_corrente_id": 1,
        })
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"]
        # E o vale continua exatamente onde estava.
        assert [p.competencia for p in _parcelas(engine, vale["id"])] == ["2026-08"]

    def test_vale_de_item_de_nota_em_competencia_paga_e_recusado_sem_gravar_a_nota(self, ambiente):
        """O mesmo furo pelo outro caminho de criação de vale (o checkbox "é
        vale?" na linha da nota). Aqui a recusa tem de vir ANTES de gravar
        qualquer coisa — senão sobra uma nota fiscal sem o vale dela."""
        c, engine = ambiente
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _lancamento_com_vale(c, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"]
        with Session(engine) as s:
            assert s.exec(select(LancamentoItem)).all() == []
            assert s.exec(select(ValeFuncionario)).all() == []

    def test_competencia_em_aberto_continua_aceitando_vale(self, ambiente):
        """A trava não pode ter fechado o caminho normal."""
        c, engine = ambiente
        _criar_folha(c, competencia="2026-07", paga=True)
        vale = _criar_vale(c, valor=300.0, parcelas=1, competencia="2026-08")
        assert [p.competencia for p in _parcelas(engine, vale["id"])] == ["2026-08"]


# ===========================================================================
# Isolamento entre fazendas-clientes
# ===========================================================================
class TestIsolamentoEntreFazendas:
    def test_a_fazenda_vizinha_nao_enxerga_nem_age_no_vale(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)

        for resposta in (
            c.get(f"/cadastro/vales/{vale['id']}/acoes", headers=_cab("admin2", 2)),
            _acao(c, vale["id"], {"acao": "cancelar"}, headers=_cab("admin2", 2)),
        ):
            assert resposta.status_code == 404, (
                "o vale da outra fazenda tem de ser NÃO ENCONTRADO — 403 confirmaria que o id existe. "
                f"Resposta: {resposta.status_code} {resposta.text[:200]}"
            )

        # E nada foi tocado.
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]).status == "ativo"

    def test_vale_orfao_sem_fazenda_nao_e_alcancavel_por_ninguem(self, ambiente):
        """Registro com `fazenda_id` nulo (o que a migração de backfill assume
        que sobra) não pode ser editável por qualquer tenant — é justamente o
        que o `if fazenda_id not in (None, x)` deixava passar."""
        c, engine = ambiente
        with Session(engine) as s:
            orfao = ValeFuncionario(
                pessoa_id=1, valor_total=500.0, forma_pagamento="pix",
                data_pagamento=__import__("datetime").date(2026, 6, 10), parcelas=1,
                competencia_inicio="2026-07", fazenda_id=None,
            )
            s.add(orfao)
            s.commit()
            s.refresh(orfao)
            orfao_id = orfao.id

        for headers in (_cab("admin1", 1), _cab("admin2", 2)):
            resposta = _acao(c, orfao_id, {"acao": "cancelar"}, headers=headers)
            assert resposta.status_code == 404, resposta.text
