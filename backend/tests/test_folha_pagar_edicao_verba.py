"""
Folha: a COLUNA DE EDIÇÃO do pop-up de pagamento — alterar as demais verbas no
ato do pagamento (`POST /cadastro/folha-pagamento/{id}/pagar`).

O pedido do dono, e o que cada bloco prova:

 A) DOIS ESTADOS POR VERBA. As verbas medidas no mês (bonificação, gueltas,
    vale-transporte, desconto em folha, "outros descontos") mudam direto; as
    determinadas pela lei ou pelo contrato (INSS, IR, aumento incorporado,
    indenização, reembolso, desconto de compra) só mudam com a confirmação do
    cadeado — e a confirmação é exigida PELO SERVIDOR, não só pela tela.

 B) SALÁRIO PARA MAIOR. Passa a ser o novo salário daquele momento em diante:
    a diferença vira a rubrica "aumento na folha" desta competência, sobe para
    `Pessoa.salario_base` e corrige as competências seguintes AINDA NÃO PAGAS.
    Competência passada e folha paga não são tocadas — o que se prova aqui é
    justamente o par (grava o futuro / não reescreve o passado).

 C) SALÁRIO PARA MENOR. 400, com a frase EXATA do dono. Alteração contratual
    lesiva ao empregado é nula (CLT, art. 468) — não existe confirmar mesmo
    assim, e o teste prova que nem com `confirmado: true` passa.

 D) PAGAR A MAIS oferece DUAS saídas e só elas: reparcelar (o excedente
    antecipa o saldo do vale) e lançar acréscimo avulso (o vale fica intacto e
    a diferença vira uma linha própria do holerite, reusando a rubrica avulsa
    que já existe). Abater e desconsiderar são recusados.

 E) FOLHA PAGA RECUSA TUDO, e a discriminação congelada não é reescrita.

 F) VALE-TRANSPORTE é cadastrável no MESMO lugar das outras rubricas.

 G) ISOLAMENTO ENTRE FAZENDAS, com contraprova: rubrica de outra fazenda (e de
    outra folha da mesma fazenda) cai em 404 — nunca 403, que confirmaria a
    existência do id —, e a mesma chamada na fazenda certa passa.

TOKEN DE VERDADE em tudo (`criar_token`), nunca `dependency_overrides` do
`get_fazenda_atual_id`: falsificar a claim tiraria do teste exatamente o que o
bloco (G) precisa provar.
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
    ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento, FolhaRubrica,
    Pessoa, Usuario, UsuarioFazenda, ValeParcela,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import verba_pagamento

# O salário do funcionário-teste. As folhas de teste nascem com este MESMO
# bruto de propósito: o aumento no ato do pagamento só é gravado quando o
# bruto do mês é o salário do cadastro (ver `pode_virar_novo_salario`), e é o
# caso normal que a maioria dos blocos precisa exercitar.
SALARIO = 5000.0


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
        s.add(Pessoa(id=1, nome="Leomir Bonfim", tipo="Funcionário", salario_base=SALARIO, fazenda_id=1))
        s.add(Pessoa(id=2, nome="Vizinho Silva", tipo="Funcionário", salario_base=SALARIO, fazenda_id=2))
        s.add(Usuario(id=1, username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=1))
        s.add(Usuario(id=2, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=2))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        s.add(ContaCorrente(id=1, banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6", fazenda_id=1))
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
def _criar_folha(c, *, pessoa_id: int = 1, competencia: str, bruto: float = SALARIO,
                 headers: dict | None = None) -> dict:
    r = c.post("/cadastro/folha-pagamento", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": bruto,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _rubrica(c, folha_id: int, *, especie="vencimento", codigo="bonificacao_produtividade",
             valor=500.0, headers: dict | None = None) -> dict:
    r = c.post(f"/cadastro/folha-pagamento/{folha_id}/rubricas", headers=headers or _cab(), json={
        "especie": especie, "codigo": codigo, "valor": valor,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _folha(c, competencia: str, pessoa_id: int = 1, headers: dict | None = None) -> dict:
    r = c.get("/cadastro/folha-pagamento", headers=headers or _cab())
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["pessoa_id"] == pessoa_id and x["competencia"] == competencia)


def _pagar(c, folha_id: int, corpo: dict, headers: dict | None = None):
    corpo = {"data_pagamento": "2026-08-05", **corpo}
    return c.post(f"/cadastro/folha-pagamento/{folha_id}/pagar", headers=headers or _cab(), json=corpo)


def _pessoa(engine, pessoa_id: int = 1) -> Pessoa:
    with Session(engine) as s:
        return s.get(Pessoa, pessoa_id)


def _folha_db(engine, folha_id: int) -> FolhaPagamento:
    with Session(engine) as s:
        return s.get(FolhaPagamento, folha_id)


def _rubricas_db(engine, folha_id: int) -> list[FolhaRubrica]:
    with Session(engine) as s:
        return list(s.exec(select(FolhaRubrica).where(FolhaRubrica.folha_id == folha_id)).all())


def _criar_vale(c, *, valor=900.0, parcelas=3, competencia="2026-07", headers: dict | None = None) -> dict:
    r = c.post("/cadastro/vales", headers=headers or _cab(), json={
        "pessoa_id": 1, "valor_total": valor, "forma_pagamento": "pix", "data_pagamento": "2026-06-10",
        "parcelas": parcelas, "competencia_inicio": competencia, "conta_corrente_id": 1,
        "observacao": "mercado",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _parcela_id(c, competencia: str) -> int:
    """O id da parcela como a TELA o vê — pela origem da linha do holerite."""
    folha = _folha(c, competencia)
    return next(d for d in folha["detalhe"] if d["tipo"] == "vale")["origem"]["parcela_id"]


# ===========================================================================
# A) Os dois estados por verba: "Editar" e o cadeado
# ===========================================================================
class TestCadeadoEEdicaoLivre:
    def test_verba_livre_muda_sem_confirmacao_nenhuma(self, ambiente):
        """Bonificação é medida no mês: não há promessa a alterar, e o dono a
        nomeou entre as verbas de "Editar"."""
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        rubrica = _rubrica(c, folha["id"], valor=500.0)

        r = _pagar(c, folha["id"], {
            "rubricas": [{"rubrica_id": rubrica["id"], "valor_pago": 800.0, "confirmado": False}],
        })
        assert r.status_code == 200, r.text
        assert [x.valor for x in _rubricas_db(engine, folha["id"])] == [800.0]
        # O líquido pago é o recalculado com a verba já alterada.
        assert _folha_db(engine, folha["id"]).valor_liquido == SALARIO + 800.0

    def test_verba_contratual_sem_confirmar_o_cadeado_e_recusada(self, ambiente):
        """A trava do cadeado existe no SERVIDOR, e não só na tela: um POST
        feito por fora do navegador chega com a mesma autorização."""
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        rubrica = _rubrica(c, folha["id"], codigo="reembolso", valor=400.0)

        r = _pagar(c, folha["id"], {
            "rubricas": [{"rubrica_id": rubrica["id"], "valor_pago": 900.0, "confirmado": False}],
        })
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == verba_pagamento.MENSAGEM_SEM_CONFIRMACAO
        # E nada ficou gravado pelo caminho — a folha continua em aberto.
        assert [x.valor for x in _rubricas_db(engine, folha["id"])] == [400.0]
        assert _folha_db(engine, folha["id"]).status != "pago"

    def test_verba_contratual_confirmada_grava_o_cadeado_avisa_nao_bloqueia(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        rubrica = _rubrica(c, folha["id"], codigo="reembolso", valor=400.0)

        r = _pagar(c, folha["id"], {
            "rubricas": [{"rubrica_id": rubrica["id"], "valor_pago": 900.0, "confirmado": True}],
        })
        assert r.status_code == 200, r.text
        assert [x.valor for x in _rubricas_db(engine, folha["id"])] == [900.0]
        assert _folha_db(engine, folha["id"]).valor_liquido == SALARIO + 900.0

    def test_retencao_a_mao_exige_cadeado_e_zera_o_percentual(self, ambiente):
        """INSS/IR são determinados pela lei — cadeado. Gravados, o percentual
        é zerado junto: é assim que o próprio formulário de folha registra um
        valor digitado à mão, e é o que faz a linha do recibo dizer "Valor
        informado, sem percentual" em vez de exibir um percentual que não
        produz aquele valor."""
        c, engine = ambiente
        r = c.post("/cadastro/folha-pagamento", headers=_cab(), json={
            # O valor retido viaja junto com o percentual porque é o
            # formulário quem calcula os dois (ver `_calcular_encargo_projetado`
            # e o comentário de `FolhaPagamento.percentual_fgts`): o servidor
            # não deduz retenção a partir de percentual sozinho.
            "pessoa_id": 1, "competencia": "2026-07", "valor_bruto": SALARIO,
            "percentual_inss": 9.0, "valor_inss": 450.0,
        })
        assert r.status_code == 200, r.text
        folha = r.json()
        assert _folha_db(engine, folha["id"]).valor_inss == 450.0

        sem = _pagar(c, folha["id"], {"retencoes": [{"tipo": "inss", "valor_pago": 380.0, "confirmado": False}]})
        assert sem.status_code == 400, sem.text

        com = _pagar(c, folha["id"], {"retencoes": [{"tipo": "inss", "valor_pago": 380.0, "confirmado": True}]})
        assert com.status_code == 200, com.text
        registro = _folha_db(engine, folha["id"])
        assert (registro.valor_inss, registro.percentual_inss) == (380.0, 0.0)
        assert registro.valor_liquido == SALARIO - 380.0

    def test_outros_descontos_e_verba_livre(self, ambiente):
        c, engine = ambiente
        r = c.post("/cadastro/folha-pagamento", headers=_cab(), json={
            "pessoa_id": 1, "competencia": "2026-07", "valor_bruto": SALARIO, "descontos": 100.0,
        })
        folha = r.json()
        assert _pagar(c, folha["id"], {"outros_descontos": {"valor_pago": 250.0}}).status_code == 200
        registro = _folha_db(engine, folha["id"])
        assert (registro.descontos, registro.valor_liquido) == (250.0, SALARIO - 250.0)

    def test_rubrica_zerada_e_recusada_editar_para_zero_e_excluir(self, ambiente):
        c, _engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        rubrica = _rubrica(c, folha["id"], valor=500.0)
        r = _pagar(c, folha["id"], {
            "rubricas": [{"rubrica_id": rubrica["id"], "valor_pago": 0.0, "confirmado": True}],
        })
        assert r.status_code == 400
        assert "maior que zero" in r.json()["detail"]


# ===========================================================================
# B) Salário para MAIOR — o novo salário daquele momento em diante
# ===========================================================================
class TestSalarioParaMaior:
    def test_vira_aumento_incorporado_e_sobe_o_salario_do_cadastro(self, ambiente):
        """O pedido do dono: "aquele passará a ser o novo salário daquele
        momento em diante". O sistema já tem essa verba — "aumento na folha"
        (CLT, art. 468) —, e é ela que é lançada: a diferença entra como
        vencimento DESTE mês e sobe para `Pessoa.salario_base`."""
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")

        r = _pagar(c, folha["id"], {"salario": {"valor_pago": 5600.0, "confirmado": True}})
        assert r.status_code == 200, r.text

        rubricas = _rubricas_db(engine, folha["id"])
        assert [(x.codigo, x.valor, x.incorpora_base) for x in rubricas] == [("aumento_folha", 600.0, True)]
        # O salário do cadastro passou a ser o novo — é o que faz o mês
        # seguinte nascer com ele, em vez de o aumento "sumir".
        assert _pessoa(engine).salario_base == SALARIO + 600.0
        # O bruto DESTE mês não foi reescrito: o holerite de julho continua
        # dizendo salário 5.000 + aumento 600, que é o documento correto.
        registro = _folha_db(engine, folha["id"])
        assert registro.valor_bruto == SALARIO
        assert registro.valor_liquido == SALARIO + 600.0

    def test_corrige_a_competencia_seguinte_em_aberto_e_nao_a_ja_paga(self, ambiente):
        """O par que importa: grava o futuro, não reescreve o passado nem o
        que já virou recibo."""
        c, engine = ambiente
        julho = _criar_folha(c, competencia="2026-07")
        agosto = _criar_folha(c, competencia="2026-08")
        setembro = _criar_folha(c, competencia="2026-09")
        # Setembro é paga ANTES do aumento: vira fotografia e não pode mudar.
        assert _pagar(c, setembro["id"], {}).status_code == 200

        assert _pagar(c, julho["id"], {"salario": {"valor_pago": 5600.0, "confirmado": True}}).status_code == 200

        assert _folha_db(engine, agosto["id"]).valor_bruto == SALARIO + 600.0
        assert _folha_db(engine, setembro["id"]).valor_bruto == SALARIO
        assert _folha_db(engine, setembro["id"]).status == "pago"

    def test_bruto_do_mes_diferente_do_salario_do_cadastro_recusa_o_aumento(self, ambiente):
        """Mês de admissão proporcional (ou folha ajustada à mão): a diferença
        digitada não é um aumento de salário, e somá-la ao cadastro
        transformaria um ajuste do mês num aumento permanente que ninguém
        concedeu. Sem histórico de salário no modelo, a saída honesta é
        recusar com explicação — nunca gravar um contrato que não existiu."""
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07", bruto=2500.0)  # metade do salário
        r = _pagar(c, folha["id"], {"salario": {"valor_pago": 3000.0, "confirmado": True}})
        assert r.status_code == 400, r.text
        assert "salário-base cadastrado" in r.json()["detail"]
        assert "Cadastro > Pessoas" in r.json()["detail"]
        assert _pessoa(engine).salario_base == SALARIO
        assert _folha_db(engine, folha["id"]).status != "pago"

    def test_sem_confirmar_o_cadeado_o_aumento_nao_passa(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        r = _pagar(c, folha["id"], {"salario": {"valor_pago": 5600.0, "confirmado": False}})
        assert r.status_code == 400
        assert _pessoa(engine).salario_base == SALARIO

    def test_mesmo_valor_nao_e_alteracao_nenhuma(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        r = _pagar(c, folha["id"], {"salario": {"valor_pago": SALARIO, "confirmado": False}})
        assert r.status_code == 200, r.text
        assert _rubricas_db(engine, folha["id"]) == []
        assert _pessoa(engine).salario_base == SALARIO


# ===========================================================================
# C) Salário para MENOR — recusa dura, art. 468 da CLT
# ===========================================================================
class TestSalarioParaMenor:
    def test_recusa_com_a_mensagem_exata_do_dono(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        r = _pagar(c, folha["id"], {"salario": {"valor_pago": 4500.0, "confirmado": True}})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == (
            "O valor informado é inferior ao salário do funcionário. "
            "Não é permitida a alteração contratual lesiva."
        )
        # A mesma constante que a tela usa — as duas recusas não podem ser
        # duas frases diferentes para o mesmo fato.
        assert r.json()["detail"] == verba_pagamento.MENSAGEM_SALARIO_MENOR

    def test_nem_confirmando_o_cadeado_passa(self, ambiente):
        """Não existe "confirmar mesmo assim": a alteração contratual lesiva
        ao empregado é NULA, então nenhum consentimento a valida."""
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        for confirmado in (True, False):
            r = _pagar(c, folha["id"], {"salario": {"valor_pago": 1.0, "confirmado": confirmado}})
            assert r.status_code == 400
            # A MESMA frase nos dois casos: sem confirmar, a recusa NÃO pode
            # ser "confirme o aviso do cadeado" — isso ofereceria um caminho
            # que não existe.
            assert r.json()["detail"] == verba_pagamento.MENSAGEM_SALARIO_MENOR
        # Nada gravado: nem folha paga, nem salário mexido, nem rubrica.
        assert _folha_db(engine, folha["id"]).status != "pago"
        assert _pessoa(engine).salario_base == SALARIO
        assert _rubricas_db(engine, folha["id"]) == []

    def test_a_nota_de_observacao_aponta_o_caminho_que_existe(self):
        """A nota em itálico do pop-up — a redução, quando é legítima, se faz
        no cadastro da pessoa, não no ato de pagar um mês."""
        assert verba_pagamento.NOTA_SALARIO_MENOR == (
            "a alteração do salário do funcionário para o valor informado deverá ser feita "
            "diretamente em Administração > Configurações > Cadastro > Pessoas > "
            "Editar cadastro do funcionário > Salário-base (R$)."
        )


# ===========================================================================
# D) Pagar a MAIS: duas opções, e só elas
# ===========================================================================
class TestDescontouAMais:
    def test_acrescimo_avulso_deixa_o_vale_intacto_e_cria_a_linha_do_holerite(self, ambiente):
        """A diferença para reparcelar: aqui o excedente NÃO é vale. A parcela
        do mês fica valendo o que valia, o cronograma não muda, e o valor a
        mais vira uma linha própria do recibo — reusando a rubrica avulsa que
        já existe (CLT, art. 462), não um segundo conceito de acréscimo."""
        c, engine = ambiente
        vale = _criar_vale(c)  # 900 em 3x: 07, 08, 09
        folha = _criar_folha(c, competencia="2026-07")
        parcela = _parcela_id(c, "2026-07")

        r = _pagar(c, folha["id"], {
            "verbas": [{"parcela_id": parcela, "valor_pago": 500.0}],
            "decisao": {"tipo": "acrescimo_avulso", "motivo": "quebra de vidro do trator"},
        })
        assert r.status_code == 200, r.text
        assert r.json()["decisoes"][0]["decisao"] == "acrescimo_avulso"

        with Session(engine) as s:
            parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale["id"])).all()
        assert sorted((p.competencia, p.valor) for p in parcelas) == [
            ("2026-07", 300.0), ("2026-08", 300.0), ("2026-09", 300.0),
        ]
        rubricas = _rubricas_db(engine, folha["id"])
        assert [(x.especie, x.codigo, x.valor, x.descricao) for x in rubricas] == [
            ("desconto", "desconto_valor", 200.0, "quebra de vidro do trator"),
        ]
        # O dinheiro bate: 300 de vale + 200 de acréscimo = os 500 lançados.
        assert _folha_db(engine, folha["id"]).valor_liquido == SALARIO - 500.0

    def test_reparcelar_continua_antecipando_o_saldo(self, ambiente):
        """A outra das duas — a que já existia. Aqui o excedente É vale: a
        parcela do mês passa a valer o que foi descontado e o saldo cai."""
        c, engine = ambiente
        vale = _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela = _parcela_id(c, "2026-07")

        r = _pagar(c, folha["id"], {
            "verbas": [{"parcela_id": parcela, "valor_pago": 500.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 2, "competencia_inicio": "2026-08"},
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            parcelas = s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale["id"])).all()
        # A parcela do mês passou a valer os R$ 500 descontados, e o que
        # restava do vale (900 − 500 = 400) foi redistribuído em 2×.
        assert sorted((p.competencia, p.valor) for p in parcelas) == [
            ("2026-07", 500.0), ("2026-08", 200.0), ("2026-09", 200.0),
        ]
        assert round(sum(p.valor for p in parcelas), 2) == 900.0
        # Nenhuma linha avulsa: reparcelar mexe no vale, não no holerite.
        assert _rubricas_db(engine, folha["id"]) == []

    @pytest.mark.parametrize("tipo", ["abater", "desconsiderar"])
    def test_as_outras_duas_decisoes_nao_cabem_a_quem_descontou_a_mais(self, ambiente, tipo):
        """"Exatamente duas opções": as outras são recusadas no servidor, e não
        apenas escondidas na tela. Não há valor deixado de cobrar para abater
        nem para a fazenda assumir — o dinheiro foi descontado de verdade."""
        c, engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela = _parcela_id(c, "2026-07")
        r = _pagar(c, folha["id"], {
            "verbas": [{"parcela_id": parcela, "valor_pago": 500.0}],
            "decisao": {"tipo": tipo, "conta_corrente_id": 1},
        })
        assert r.status_code == 400, r.text
        assert "reparcelar" in r.json()["detail"] and "acréscimo avulso" in r.json()["detail"]
        assert _folha_db(engine, folha["id"]).status != "pago"

    def test_acrescimo_avulso_nao_cabe_a_quem_descontou_a_menos(self, ambiente):
        c, _engine = ambiente
        _criar_vale(c)
        folha = _criar_folha(c, competencia="2026-07")
        parcela = _parcela_id(c, "2026-07")
        r = _pagar(c, folha["id"], {
            "verbas": [{"parcela_id": parcela, "valor_pago": 100.0}],
            "decisao": {"tipo": "acrescimo_avulso"},
        })
        assert r.status_code == 400
        assert "só cabe quando se desconta MAIS" in r.json()["detail"]


# ===========================================================================
# E) Folha paga recusa tudo
# ===========================================================================
class TestFolhaPaga:
    def test_folha_paga_recusa_qualquer_alteracao_de_verba(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        rubrica = _rubrica(c, folha["id"], valor=500.0)
        assert _pagar(c, folha["id"], {}).status_code == 200
        congelado = _folha_db(engine, folha["id"]).discriminacao_congelada

        for corpo in (
            {"salario": {"valor_pago": 5600.0, "confirmado": True}},
            {"rubricas": [{"rubrica_id": rubrica["id"], "valor_pago": 900.0, "confirmado": True}]},
            {"retencoes": [{"tipo": "inss", "valor_pago": 10.0, "confirmado": True}]},
            {"outros_descontos": {"valor_pago": 10.0}},
        ):
            r = _pagar(c, folha["id"], corpo)
            assert r.status_code == 400, r.text
            assert r.json()["detail"] == "Este lançamento de folha já está pago."

        # A fotografia continua exatamente a mesma, e o salário do cadastro
        # não se mexeu: folha paga não é reescrita por nenhuma porta.
        assert _folha_db(engine, folha["id"]).discriminacao_congelada == congelado
        assert [x.valor for x in _rubricas_db(engine, folha["id"])] == [500.0]
        assert _pessoa(engine).salario_base == SALARIO


# ===========================================================================
# F) Vale-transporte cadastrável, no mesmo lugar das outras rubricas
# ===========================================================================
class TestValeTransporte:
    def test_e_lancavel_como_qualquer_rubrica_e_nao_entra_em_base_nenhuma(self, ambiente):
        """Lei 7.418/85, art. 2º: sem natureza salarial e fora das bases de
        contribuição e de FGTS. O que se prova aqui é que ele entra pelo mesmo
        POST /rubricas das demais — não há tela nova."""
        c, engine = ambiente
        r = c.post("/cadastro/folha-pagamento", headers=_cab(), json={
            # O valor retido viaja junto com o percentual porque é o
            # formulário quem calcula os dois (ver `_calcular_encargo_projetado`
            # e o comentário de `FolhaPagamento.percentual_fgts`): o servidor
            # não deduz retenção a partir de percentual sozinho.
            "pessoa_id": 1, "competencia": "2026-07", "valor_bruto": SALARIO,
            "percentual_inss": 9.0, "valor_inss": 450.0,
        })
        folha = r.json()
        vt = _rubrica(c, folha["id"], codigo="vale_transporte", valor=300.0)
        assert vt["natureza"] == "indenizatoria"

        registro = _folha_db(engine, folha["id"])
        # A base do INSS NÃO subiu com o vale-transporte.
        assert (registro.valor_rubricas_tributaveis, registro.valor_inss) == (0.0, 450.0)
        assert registro.valor_liquido == SALARIO + 300.0 - 450.0

    def test_a_cota_parte_do_empregado_e_desconto_com_fundamento_proprio(self, ambiente):
        c, engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        _rubrica(c, folha["id"], especie="desconto", codigo="desconto_vale_transporte", valor=300.0)
        assert _folha_db(engine, folha["id"]).valor_liquido == SALARIO - 300.0

    def test_a_linha_do_holerite_diz_que_o_vale_transporte_e_editavel(self, ambiente):
        """A coluna de edição da tela sai da ORIGEM da linha (`alteracao`), e
        não de uma segunda lista escrita no frontend."""
        c, _engine = ambiente
        folha = _criar_folha(c, competencia="2026-07")
        _rubrica(c, folha["id"], codigo="vale_transporte", valor=300.0)
        _rubrica(c, folha["id"], codigo="reembolso", valor=100.0)

        linhas = {d["origem"]["codigo"]: d["origem"]["alteracao"]
                  for d in _folha(c, "2026-07")["detalhe"] if d["tipo"] == "vencimento_extra"}
        assert linhas == {"vale_transporte": "livre", "reembolso": "contratual"}


# ===========================================================================
# G) Isolamento entre fazendas — com contraprova
# ===========================================================================
class TestIsolamentoEntreFazendas:
    def test_rubrica_de_outra_fazenda_cai_em_404_e_a_propria_passa(self, ambiente):
        """404 e nunca 403: responder "proibido" confirmaria que o id existe.
        A contraprova é a metade que importa — sem ela, um 404 constante
        passaria no teste sem isolar nada."""
        c, engine = ambiente
        minha = _criar_folha(c, competencia="2026-07")
        rubrica_minha = _rubrica(c, minha["id"], valor=500.0)

        vizinha = _criar_folha(c, pessoa_id=2, competencia="2026-07", headers=_cab("admin2", 2))
        rubrica_vizinha = _rubrica(c, vizinha["id"], valor=500.0, headers=_cab("admin2", 2))

        alheia = _pagar(c, minha["id"], {
            "rubricas": [{"rubrica_id": rubrica_vizinha["id"], "valor_pago": 800.0, "confirmado": True}],
        })
        assert alheia.status_code == 404, alheia.text
        assert "não pertence" in alheia.json()["detail"]

        # Contraprova: a MESMA chamada, com a rubrica da própria fazenda.
        propria = _pagar(c, minha["id"], {
            "rubricas": [{"rubrica_id": rubrica_minha["id"], "valor_pago": 800.0, "confirmado": True}],
        })
        assert propria.status_code == 200, propria.text
        # E a rubrica da vizinha continua intacta.
        assert [x.valor for x in _rubricas_db(engine, vizinha["id"])] == [500.0]

    def test_rubrica_de_outra_folha_da_mesma_fazenda_tambem_cai_em_404(self, ambiente):
        """O filtro é por fazenda E por folha: pagar julho não pode reescrever
        a bonificação de agosto."""
        c, engine = ambiente
        julho = _criar_folha(c, competencia="2026-07")
        agosto = _criar_folha(c, competencia="2026-08")
        rubrica_agosto = _rubrica(c, agosto["id"], valor=500.0)

        r = _pagar(c, julho["id"], {
            "rubricas": [{"rubrica_id": rubrica_agosto["id"], "valor_pago": 800.0, "confirmado": True}],
        })
        assert r.status_code == 404, r.text
        assert [x.valor for x in _rubricas_db(engine, agosto["id"])] == [500.0]

    def test_folha_de_outra_fazenda_cai_em_404(self, ambiente):
        c, _engine = ambiente
        vizinha = _criar_folha(c, pessoa_id=2, competencia="2026-07", headers=_cab("admin2", 2))
        r = _pagar(c, vizinha["id"], {"salario": {"valor_pago": 5600.0, "confirmado": True}})
        assert r.status_code == 404, r.text


# ===========================================================================
# H) O que o pagamento NÃO pode mexer sozinho
# ===========================================================================
class TestNaoMexeNoQueNinguemPediu:
    def test_retencao_digitada_a_mao_sobrevive_a_um_pagamento_de_vale(self, ambiente):
        """O recálculo da folha refaz as retenções a partir do percentual
        gravado. Rodá-lo num pagamento que só mexeu no vale apagaria um INSS
        que o contador digitou à mão em "Editar lançamento" — um valor que
        ninguém pediu para mudar. Por isso o recálculo só roda quando alguma
        rubrica mudou de verdade."""
        c, engine = ambiente
        _criar_vale(c)
        r = c.post("/cadastro/folha-pagamento", headers=_cab(), json={
            "pessoa_id": 1, "competencia": "2026-07", "valor_bruto": SALARIO,
            "percentual_inss": 9.0, "valor_inss": 380.0,  # 9% daria 450: valor ajustado à mão
        })
        folha = r.json()
        parcela = _parcela_id(c, "2026-07")

        assert _pagar(c, folha["id"], {
            "verbas": [{"parcela_id": parcela, "valor_pago": 100.0}],
            "decisao": {"tipo": "abater"},
        }).status_code == 200

        assert _folha_db(engine, folha["id"]).valor_inss == 380.0
