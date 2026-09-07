"""
Vale de funcionário: as duas voltas atrás — `estornar_abatimento` e
`reverter_desconsideracao` (`POST /cadastro/vales/{id}/acoes`).

O CASO REAL que fez as duas existirem. O dono queria "desconsiderar o vale de
2026-08 — a fazenda assume" e clicou em "Lançar desconto/abatimento" de
R$ 167,85. O abatimento é rateado entre as parcelas pendentes, então as 12
parcelas de R$ 985,00 viraram R$ 971,01 (a última R$ 971,04) e ele ficou sem
saída: editar o vale inteiro é recusado porque uma competência dele já está em
folha paga, e abatimento negativo é recusado por desenho. É esse número, ao
centavo, que o primeiro teste deste arquivo reconstitui e desfaz.

O QUE CADA BLOCO PROVA:

 A) Estorno — a ida e a volta batem ao centavo (o rateio é a mesma conta nos
    dois sentidos), o estorno parcial, e cada uma das recusas. A recusa mais
    importante é a de "não há parcela pendente": o estorno NÃO inventa uma
    parcela nova, porque escolher sozinho em que mês cobrar seria decidir no
    lugar do dono.

 B) Reversão da desconsideração — o mês volta a ser descontado E o lançamento
    do vale volta a ser vale no Financeiro (rótulo e descrição idênticos aos
    que `_sincronizar_conta_vale` escreve, não um texto parecido).

 C) O que a reversão RECUSA, e por quê: assunção que mexeu em item de nota
    (desfazer às cegas corromperia a nota) e assunção de natureza
    indistinguível (vale sem lançamento próprio pode ser "sem lastro" ou "item
    de nota já solto" — chutar contaria a mesma despesa duas vezes).

 D) A tela só recebe o que não vai dar erro (`acoes_disponiveis`).

 E) Isolamento entre fazendas-clientes, com contraprova dentro da fazenda
    certa — senão o 404 poderia estar vindo de a ação simplesmente não existir.

TOKEN DE VERDADE em tudo (`criar_token`), nunca `dependency_overrides` do
`get_fazenda_atual_id`: falsificar a claim tiraria do teste exatamente o que
ele precisa provar.
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
        # Salário alto de propósito: o teto de 40% não pode ser o que faz um
        # teste de ação de vale falhar (a parcela real do caso é R$ 985,00).
        s.add(Pessoa(id=1, nome="Leomir Bonfim", tipo="Funcionário", salario_base=9000.0, fazenda_id=1))
        s.add(Pessoa(id=2, nome="Vizinho Silva", tipo="Funcionário", salario_base=9000.0, fazenda_id=2))
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


def _contexto(c, vale_id: int, headers: dict | None = None):
    return c.get(f"/cadastro/vales/{vale_id}/acoes", headers=headers or _cab())


def _valores(engine, vale_id: int) -> list[float]:
    with Session(engine) as s:
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
        return [p.valor for p in sorted(parcelas, key=lambda p: (p.competencia, p.id or 0))]


def _parcelas(engine, vale_id: int) -> list[ValeParcela]:
    with Session(engine) as s:
        parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all()
        return sorted(parcelas, key=lambda p: (p.competencia, p.id or 0))


def _conta(engine, numero: str) -> ContaGerencial:
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()


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
# A) Estornar o abatimento
# ===========================================================================
class TestEstornarAbatimento:
    def test_o_caso_do_dono_ida_e_volta_ao_centavo(self, ambiente):
        """12 parcelas de R$ 985,00, abatimento de R$ 167,85 lançado por
        engano: as parcelas caem para R$ 971,01 (a última R$ 971,04). O
        estorno tem de devolver EXATAMENTE R$ 985,00 em todas — é o mesmo
        rateio proporcional aplicado no sentido inverso, e é por isso que ida
        e volta fecham sem sobra de centavo."""
        c, engine = ambiente
        vale = _criar_vale(c, valor=11820.0, parcelas=12, competencia="2026-08")
        assert _valores(engine, vale["id"]) == [985.0] * 12

        abatimento = _acao(c, vale["id"], {"acao": "abater", "valor": 167.85})
        assert abatimento.status_code == 200, abatimento.text
        assert _valores(engine, vale["id"]) == [971.01] * 11 + [971.04]
        assert abatimento.json()["saldo_apos"] == 11652.15

        estorno = _acao(c, vale["id"], {"acao": "estornar_abatimento"})
        assert estorno.status_code == 200, estorno.text
        assert _valores(engine, vale["id"]) == [985.0] * 12
        assert estorno.json()["valor_estornado"] == 167.85
        assert estorno.json()["saldo_apos"] == 11820.0
        assert estorno.json()["abatimento_restante"] == 0.0

        with Session(engine) as s:
            registro = s.get(ValeFuncionario, vale["id"])
            assert registro.valor_abatido == 0.0
            assert registro.valor_total == 11820.0, "o valor adiantado é histórico e não se reescreve"

    def test_a_folha_volta_a_descontar_o_valor_de_antes(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)                    # 900 em 3x (300/mês)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        assert _folha(c, "2026-07")["valor_vale"] == 200.0

        assert _acao(c, vale["id"], {"acao": "estornar_abatimento"}).status_code == 200
        folha = _folha(c, "2026-07")
        assert folha["valor_vale"] == 300.0
        assert folha["valor_liquido"] == 2700.0

    def test_estorno_parcial_devolve_so_o_pedaco_informado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        assert _valores(engine, vale["id"]) == [200.0, 200.0, 200.0]

        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento", "valor": 150.0})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["saldo_apos"] == 750.0
        assert resposta.json()["abatimento_restante"] == 150.0
        assert _valores(engine, vale["id"]) == [250.0, 250.0, 250.0]
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]).valor_abatido == 150.0

    def test_o_que_ja_caiu_em_folha_paga_nao_recebe_estorno(self, ambiente):
        """Mesma regra do abatimento: o estorno só alcança o que ainda não foi
        descontado — o holerite de julho já é recibo."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})   # 200/200/200
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento", "valor": 200.0})
        assert resposta.status_code == 200, resposta.text
        assert _valores(engine, vale["id"]) == [200.0, 300.0, 300.0]

    def test_estorno_sem_abatimento_nenhum_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento"})
        assert resposta.status_code == 400, resposta.text
        assert "não tem abatimento a estornar" in resposta.json()["detail"]

    @pytest.mark.parametrize("valor", [0.0, -50.0])
    def test_estorno_de_valor_nao_positivo_e_recusado(self, ambiente, valor):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento", "valor": valor})
        assert resposta.status_code == 400, resposta.text
        assert "positivo" in resposta.json()["detail"]
        assert _valores(engine, vale["id"]) == [200.0, 200.0, 200.0], "nada pode ter sido escrito"

    def test_estorno_maior_que_o_abatimento_diz_quanto_ha_disponivel(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})

        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento", "valor": 500.0})
        assert resposta.status_code == 400, resposta.text
        detalhe = resposta.json()["detail"]
        assert "300,00" in detalhe and "disponíveis para estorno" in detalhe

    def test_sem_parcela_pendente_o_estorno_recusa_e_aponta_o_caminho(self, ambiente):
        """Abater o saldo inteiro apaga as parcelas (parcela de R$ 0,00 é
        ruído no holerite). O estorno então não tem onde devolver o valor — e
        não inventa uma parcela nova, porque escolher o mês da cobrança é
        decisão do dono, não do sistema."""
        c, engine = ambiente
        vale = _criar_vale(c)
        assert _acao(c, vale["id"], {"acao": "abater", "valor": 900.0}).status_code == 200
        assert _valores(engine, vale["id"]) == []

        resposta = _acao(c, vale["id"], {"acao": "estornar_abatimento"})
        assert resposta.status_code == 400, resposta.text
        detalhe = resposta.json()["detail"]
        assert "não tem parcela pendente" in detalhe
        assert "eparcele" in detalhe, "a mensagem tem de dizer por onde sair"
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]).valor_abatido == 900.0, "nada foi escrito"

    def test_o_estorno_nao_mexe_no_recebimento_da_devolucao(self, ambiente):
        """O abatimento pode ter criado uma ENTRADA de caixa (devolução em
        dinheiro). Não há vínculo persistido entre o vale e aquele lançamento,
        então apagar "o" lançamento seria apagar um chutado — o estorno deixa
        o recebimento onde está e AVISA, por escrito, que ele precisa sair à
        mão."""
        c, engine = ambiente
        vale = _criar_vale(c)
        abatimento = _acao(c, vale["id"], {"acao": "abater", "valor": 300.0, "conta_corrente_id": 1})
        numero = abatimento.json()["numero_lancamento_devolucao"]
        assert numero

        estorno = _acao(c, vale["id"], {"acao": "estornar_abatimento"})
        assert estorno.status_code == 200, estorno.text
        assert "à mão" in estorno.json()["resumo"] and "Financeiro" in estorno.json()["resumo"]
        conta = _conta(engine, numero)
        assert conta is not None and conta.valor_total == 300.0, "o recebimento continua no extrato"


# ===========================================================================
# B) Reverter a desconsideração
# ===========================================================================
class TestReverterDesconsideracao:
    def test_o_mes_volta_a_ser_descontado_do_funcionario(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07", "motivo": "trator"})
        assert _folha(c, "2026-07")["valor_vale"] == 0.0

        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["valor_revertido"] == 300.0

        folha = _folha(c, "2026-07")
        assert folha["valor_vale"] == 300.0
        assert folha["valor_liquido"] == 2700.0
        parcela = next(p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07")
        assert parcela.assumida_pela_fazenda is False
        assert parcela.motivo_assuncao is None
        assert parcela.valor == 300.0
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]).valor_assumido_fazenda == 0.0

    def test_o_lancamento_do_vale_volta_a_ser_vale_no_financeiro(self, ambiente):
        """A assunção TOTAL reclassifica o lançamento próprio do vale para
        despesa comum ("Recibo"). Revertendo, ele volta a ser a baixa
        espelhada do RH — com o mesmo rótulo e a mesma descrição que
        `_sincronizar_conta_vale` escreve na criação, não um texto parecido:
        divergir aqui faria o Financeiro voltar a aceitar estorno/edição num
        lançamento que pertence ao RH."""
        c, engine = ambiente
        vale = _criar_vale(c, valor=300.0, parcelas=1)
        with Session(engine) as s:
            numero = s.get(ValeFuncionario, vale["id"]).numero_lancamento_gerado
        assert numero

        assumir = _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert assumir.json()["financeiro"]["reclassificado"] is True
        assert _conta(engine, numero).tipo_documento == "Recibo"

        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["financeiro"] == {
            "natureza": "lancamento_proprio", "numero_lancamento": numero, "reclassificado": True,
        }
        conta = _conta(engine, numero)
        assert conta.tipo_documento == "Vale de funcionário"
        assert conta.descricao == "Vale — Leomir Bonfim (2026-07)"
        assert conta.valor_total == 300.0, "a saída de caixa aconteceu e não pode mudar de valor"

    def test_assuncao_parcial_nao_mexe_no_rotulo_na_ida_nem_na_volta(self, ambiente):
        """Com o vale ainda vivo (só um mês assumido), o lançamento nunca
        deixou de ser vale — a volta não pode inventar uma alteração."""
        c, engine = ambiente
        vale = _criar_vale(c)  # 3 parcelas
        with Session(engine) as s:
            numero = s.get(ValeFuncionario, vale["id"]).numero_lancamento_gerado

        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert _conta(engine, numero).tipo_documento == "Vale de funcionário"

        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["financeiro"]["reclassificado"] is False
        assert _conta(engine, numero).tipo_documento == "Vale de funcionário"

    def test_sem_competencia_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao"})
        assert resposta.status_code == 400, resposta.text
        assert "competência" in resposta.json()["detail"]

    def test_mes_que_nao_foi_desconsiderado_e_recusado(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-08"})
        assert resposta.status_code == 400, resposta.text
        assert "2026-08" in resposta.json()["detail"]

    def test_reverter_dentro_de_folha_paga_e_recusado(self, ambiente):
        """Voltar a descontar num mês já pago cobraria do funcionário um
        desconto que o recibo daquele mês não tem — a mesma trava da ida."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        _criar_folha(c, competencia="2026-07", paga=True)

        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 400, resposta.text
        assert "2026-07" in resposta.json()["detail"] and "já foi paga" in resposta.json()["detail"]
        parcela = next(p for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-07")
        assert parcela.assumida_pela_fazenda is True, "a parcela continua assumida"


# ===========================================================================
# C) O que a reversão recusa no Financeiro
# ===========================================================================
class TestReversaoRecusadaNoFinanceiro:
    def test_vale_de_item_de_nota_recusa_e_diz_o_que_acertar_a_mao(self, ambiente):
        """A assunção partiu o item da nota em dois (metade do funcionário,
        metade da fazenda). O gêmeo pode ter sido editado desde então, então
        juntar de volta às cegas corromperia a nota — melhor recusar dizendo
        qual lançamento acertar à mão."""
        c, engine = ambiente
        nota = _lancamento_com_vale(c, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 2, "competencia_inicio": "2026-07",
        })
        assert nota.status_code == 201, nota.text
        numero = nota.json()["numero_lancamento"]
        vale_id = nota.json()["vales_criados"][0]["vale_id"]

        assumir = _acao(c, vale_id, {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert assumir.json()["financeiro"]["natureza"] == "item_de_nota"

        resposta = _acao(c, vale_id, {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 400, resposta.text
        detalhe = resposta.json()["detail"]
        assert numero in detalhe, "a recusa tem de dizer QUAL lançamento precisa ser acertado"
        assert "à mão" in detalhe

        # E nada foi tocado: nem a marca da parcela, nem as duas linhas da nota.
        parcela = next(p for p in _parcelas(engine, vale_id) if p.competencia == "2026-07")
        assert parcela.assumida_pela_fazenda is True
        with Session(engine) as s:
            itens = s.exec(
                select(LancamentoItem).where(LancamentoItem.numero_lancamento == numero)
            ).all()
        assert round(sum(i.valor_total for i in itens), 2) == 300.0, "a nota continua fechando"

    def test_vale_sem_lancamento_proprio_recusa_por_ambiguidade(self, ambiente):
        """Vale sem saída de caixa e sem item vinculado hoje pode ser as duas
        coisas: nunca teve lastro (nada a desfazer) ou nasceu de item de nota
        cujo vínculo foi SOLTO na assunção — e as duas ficam idênticas depois.
        Reverter no escuro contaria a mesma despesa duas vezes."""
        c, engine = ambiente
        vale = _criar_vale(c, valor=300.0, parcelas=1, conta_id=None, forma="desconto_integral_folha")
        assumir = _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        assert assumir.json()["financeiro"]["natureza"] == "sem_lastro"

        resposta = _acao(c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-07"})
        assert resposta.status_code == 400, resposta.text
        assert "não dá para saber" in resposta.json()["detail"].lower()
        parcela = _parcelas(engine, vale["id"])[0]
        assert parcela.assumida_pela_fazenda is True, "recusa não pode reverter meio caminho"


# ===========================================================================
# D) A tela só recebe o que não vai dar erro
# ===========================================================================
class TestAcoesDisponiveis:
    def test_estorno_so_aparece_quando_ha_abatimento(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        assert "estornar_abatimento" not in _contexto(c, vale["id"]).json()["acoes_disponiveis"]

        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        assert "estornar_abatimento" in _contexto(c, vale["id"]).json()["acoes_disponiveis"]

    def test_estorno_some_quando_nao_ha_onde_devolver(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 900.0})  # zera e apaga as parcelas
        assert "estornar_abatimento" not in _contexto(c, vale["id"]).json()["acoes_disponiveis"]

    def test_reversao_so_aparece_quando_ha_mes_assumido_reversivel(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        contexto = _contexto(c, vale["id"]).json()
        assert "reverter_desconsideracao" not in contexto["acoes_disponiveis"]
        assert contexto["competencias_revertiveis"] == []

        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})
        contexto = _contexto(c, vale["id"]).json()
        assert "reverter_desconsideracao" in contexto["acoes_disponiveis"]
        assert contexto["competencias_revertiveis"] == ["2026-07"]

    def test_reversao_nao_e_oferecida_quando_o_financeiro_nao_tem_volta(self, ambiente):
        """A tela não pode oferecer o que o POST vai recusar: o dono clicaria
        achando que tem saída e levaria um 400."""
        c, engine = ambiente
        nota = _lancamento_com_vale(c, vale={
            "pessoa_id": 1, "modo": "folha", "parcelas": 2, "competencia_inicio": "2026-07",
        })
        vale_id = nota.json()["vales_criados"][0]["vale_id"]
        _acao(c, vale_id, {"acao": "desconsiderar_mes", "competencia": "2026-07"})

        contexto = _contexto(c, vale_id).json()
        assert contexto["competencias_revertiveis"] == ["2026-07"]
        assert "reverter_desconsideracao" not in contexto["acoes_disponiveis"]

    def test_vale_cancelado_nao_oferece_nada(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "cancelar"})
        assert _contexto(c, vale["id"]).json()["acoes_disponiveis"] == []


# ===========================================================================
# E) Isolamento entre fazendas-clientes
# ===========================================================================
class TestIsolamentoEntreFazendas:
    def test_a_fazenda_vizinha_nao_desfaz_nada_no_vale_alheio(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _acao(c, vale["id"], {"acao": "abater", "valor": 300.0})
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-09"})

        for corpo in (
            {"acao": "estornar_abatimento"},
            {"acao": "reverter_desconsideracao", "competencia": "2026-09"},
        ):
            resposta = _acao(c, vale["id"], corpo, headers=_cab("admin2", 2))
            assert resposta.status_code == 404, (
                "vale de outra fazenda tem de ser NÃO ENCONTRADO — 403 confirmaria que o id existe. "
                f"Resposta: {resposta.status_code} {resposta.text[:200]}"
            )

        # Contraprova: dentro da fazenda certa as duas ações funcionam — o 404
        # acima é do isolamento, não de a ação não existir.
        assert _acao(c, vale["id"], {"acao": "estornar_abatimento"}).status_code == 200
        assert _acao(
            c, vale["id"], {"acao": "reverter_desconsideracao", "competencia": "2026-09"}
        ).status_code == 200
        with Session(engine) as s:
            registro = s.get(ValeFuncionario, vale["id"])
            assert registro.valor_abatido == 0.0
            assert registro.valor_assumido_fazenda == 0.0

    def test_vale_orfao_sem_fazenda_nao_e_alcancavel_por_ninguem(self, ambiente):
        """Registro com `fazenda_id` nulo (o que a migração de backfill assume
        que sobra) não pode ser desfeito por qualquer tenant."""
        c, engine = ambiente
        with Session(engine) as s:
            orfao = ValeFuncionario(
                pessoa_id=1, valor_total=500.0, forma_pagamento="pix",
                data_pagamento=__import__("datetime").date(2026, 6, 10), parcelas=1,
                competencia_inicio="2026-07", valor_abatido=100.0, fazenda_id=None,
            )
            s.add(orfao)
            s.commit()
            s.refresh(orfao)
            orfao_id = orfao.id

        for headers in (_cab("admin1", 1), _cab("admin2", 2)):
            resposta = _acao(c, orfao_id, {"acao": "estornar_abatimento"}, headers=headers)
            assert resposta.status_code == 404, resposta.text
