"""
Rubricas do holerite — os vencimentos e descontos que o dono acrescenta em
Contas > Holerites e recibos, e o regime tributário de cada um.

O QUE ESTES TESTES TRAVAM, e por que cada um deles é dinheiro:

1. **A base das retenções deixa de ser "o salário".** Bonificação, guelta e
   aumento são salariais e ENTRAM na base de INSS/IRRF/FGTS; reembolso e
   indenização são indenizatórios e NÃO entram. Antes desta feature o único
   jeito de lançar qualquer um deles era somar no salário bruto — e aí o
   funcionário pagava contribuição sobre um reembolso, que é dinheiro dele
   sendo devolvido.
2. **O "aumento na folha" incorpora ao vencimento base do mês seguinte.** É a
   única rubrica cujo efeito não acaba no mês (CLT, art. 468): sem a
   incorporação, o dono daria o aumento e a competência seguinte voltaria
   sozinha ao salário antigo.
3. **A folha PAGA não recebe rubrica.** A discriminação dela foi congelada no
   pagamento porque o holerite é prova; aceitar linha nova depois disso
   reabriria por outra porta o defeito que o congelamento fechou.
4. **O isolamento entre fazendas.** O CowData não tem RLS: quem garante que a
   folha, a rubrica e a COMPRA vinculada são da fazenda do token é a própria
   consulta. Token REAL (`criar_token`), nunca
   `dependency_overrides[get_fazenda_atual_id]` — é justamente o caminho
   token → get_fazenda_atual_id → get_fazenda_id_escrita → consulta que está
   em julgamento.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento, FolhaRubrica,
    Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import rubrica_folha

COMPETENCIA = "2026-07"


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes com um funcionário e uma compra em cada — a da
    fazenda 2 existe só para ser o alvo que a fazenda 1 não pode alcançar."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Atacante"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
        s.commit()

        # Homônimos nas duas fazendas de propósito: colisão de texto entre
        # tenants é o caso normal, não o excepcional.
        for fid in (1, 2):
            pessoa = Pessoa(
                nome="Leomir Bonfim", tipo="Funcionário", salario_base=3000.0,
                data_admissao=date(2024, 1, 10), fazenda_id=fid,
            )
            s.add(pessoa)
            s.commit()
            s.refresh(pessoa)
            ids[f"pessoa{fid}"] = pessoa.id

            compra = ContaGerencial(
                numero_lancamento=f"LC-2026-0000{fid}", descricao="Peça do trator",
                fornecedor_cliente=f"Auto Peças {fid}", numero_nota="4471",
                data_vencimento=date(2026, 6, 20), valor_total=480.0,
                tipo="despesa", origem="manual", fazenda_id=fid,
            )
            s.add(compra)
            s.commit()
            s.refresh(compra)
            ids[f"compra{fid}"] = compra.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int):
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


def _criar_folha(c, fazenda_id: int, pessoa_id: int, **extra) -> int:
    corpo = {
        "pessoa_id": pessoa_id, "competencia": COMPETENCIA, "valor_bruto": 3000.0,
        "percentual_inss": 9.0, "valor_inss": 270.0,
    }
    corpo.update(extra)
    r = c.post("/cadastro/folha-pagamento", json=corpo, headers=_cab(fazenda_id))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _folha(c, fazenda_id: int, folha_id: int) -> dict:
    r = c.get("/cadastro/folha-pagamento", headers=_cab(fazenda_id))
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["id"] == folha_id)


def _linhas(detalhe: list[dict], tipo: str) -> list[dict]:
    return [d for d in detalhe if d["tipo"] == tipo]


# ---------------------------------------------------------------------------
# O catálogo e o enquadramento de cada uma das cinco rubricas
# ---------------------------------------------------------------------------
class TestCatalogoTrabalhista:
    def test_as_rubricas_de_vencimento_existem_com_o_enquadramento(self):
        catalogo = rubrica_folha.CATALOGO_VENCIMENTOS
        assert set(catalogo) == {
            "bonificacao_produtividade", "aumento_folha", "gueltas", "vale_transporte",
            "vale_alimentacao", "indenizacao", "reembolso",
        }
        salariais = {"bonificacao_produtividade", "aumento_folha", "gueltas"}
        for codigo, dados in catalogo.items():
            esperado = (
                rubrica_folha.NATUREZA_SALARIAL if codigo in salariais
                else rubrica_folha.NATUREZA_INDENIZATORIA
            )
            assert dados["natureza"] == esperado, codigo
            # O fundamento legal vai escrito no catálogo para o dono poder
            # conferir com a contabilidade dele — verba sem fundamento é
            # exatamente o que ninguém consegue auditar depois.
            assert dados["fundamento"], codigo
        # Só o aumento muda o futuro.
        assert [c for c, d in catalogo.items() if d["incorpora_base"]] == ["aumento_folha"]

    def test_todo_verbete_declara_se_pode_ser_alterado_no_pagamento(self):
        """`alteracao` é o eixo da coluna de edição do pop-up de pagamento
        (ver rules/verba_pagamento.py). Verbete sem ele cairia em "contratual"
        por omissão — o lado seguro, mas por acidente e não por decisão. O
        teste obriga a decisão a ser escrita."""
        for catalogo in (rubrica_folha.CATALOGO_VENCIMENTOS, rubrica_folha.CATALOGO_DESCONTOS):
            for codigo, dados in catalogo.items():
                assert dados.get("alteracao") in (
                    rubrica_folha.ALTERACAO_LIVRE, rubrica_folha.ALTERACAO_CONTRATUAL,
                ), codigo

    def test_o_enquadramento_do_vale_transporte_e_o_que_a_lei_diz(self):
        """Lei 7.418/85, art. 2º: sem natureza salarial, sem incorporação à
        remuneração "para quaisquer efeitos" e fora da base de contribuição
        previdenciária e de FGTS. É o verbete menos ambíguo do catálogo, e o
        teste existe para ele não ser "arrumado" para salarial sem que alguém
        leia a lei antes."""
        vt = rubrica_folha.CATALOGO_VENCIMENTOS["vale_transporte"]
        assert vt["natureza"] == rubrica_folha.NATUREZA_INDENIZATORIA
        assert not (vt["incide_inss"] or vt["incide_irrf"] or vt["incide_fgts"])
        assert not vt["incorpora_base"]
        assert "7.418" in vt["fundamento"]
        # A cota-parte do empregado é DESCONTO, com fundamento próprio.
        assert "6%" in rubrica_folha.CATALOGO_DESCONTOS["desconto_vale_transporte"]["fundamento"]

    def test_catalogo_mantem_bases_alinhadas(self):
        """`FolhaPagamento.valor_rubricas_tributaveis` é UM número para os três
        tributos — ele só é honesto enquanto salarial significar "entra nos
        três" e indenizatória, "não entra em nenhum". Este teste quebra de
        propósito no dia em que uma rubrica nova desalinhar isso: aí o caminho
        é quebrar o cache em três colunas, não relaxar o teste."""
        for codigo, dados in rubrica_folha.CATALOGO_VENCIMENTOS.items():
            incidencias = {dados["incide_inss"], dados["incide_irrf"], dados["incide_fgts"]}
            salarial = dados["natureza"] == rubrica_folha.NATUREZA_SALARIAL
            assert incidencias == {salarial}, codigo

    def test_endpoint_do_catalogo_serve_a_tela(self, ambiente):
        c, _engine, _ids = ambiente
        r = c.get("/cadastro/folha-pagamento/rubricas/catalogo", headers=_cab(1))
        assert r.status_code == 200, r.text
        corpo = r.json()
        # O endpoint serve o formulário de LANÇAMENTO manual, e por isso ele
        # não é o catálogo inteiro: o `vale_alimentacao` é gerado a partir do
        # cadastro do funcionário e fica de fora do <select> (oferecer uma
        # escolha que o servidor recusaria seria convidar ao erro).
        assert {v["codigo"] for v in corpo["vencimentos"]} == {
            codigo for codigo, dados in rubrica_folha.CATALOGO_VENCIMENTOS.items()
            if not dados.get("gerado_por_cadastro")
        }
        assert "vale_alimentacao" not in {v["codigo"] for v in corpo["vencimentos"]}
        assert {d["codigo"] for d in corpo["descontos"]} == {
            "desconto_valor", "desconto_compra", "desconto_vale_transporte",
        }
        # O catálogo é o que a tela de rubricas do holerite lê para montar o
        # <select>: o vale-transporte ser cadastrável É estar aqui — não há
        # tela nova nem cadastro paralelo.
        assert {v["codigo"] for v in corpo["vencimentos"]} >= {"vale_transporte"}


# ---------------------------------------------------------------------------
# Regime tributário: quem entra na base das retenções e quem não entra
# ---------------------------------------------------------------------------
class TestRegimeTributarioDasRubricas:
    @pytest.mark.parametrize("codigo", ["bonificacao_produtividade", "gueltas", "aumento_folha"])
    def test_rubrica_salarial_aumenta_a_base_e_a_retencao(self, ambiente, codigo):
        """9% sobre R$ 3.000 = R$ 270. Com R$ 500 de rubrica salarial a base
        vira R$ 3.500 e a retenção, R$ 315 — e é a base corrigida que aparece
        no rodapé do documento, senão o dono confere "9% sobre R$ 3.000,00"
        contra um valor calculado sobre outra coisa e conclui que o sistema
        errou."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": codigo, "valor": 500.0},
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        assert r.json()["natureza"] == rubrica_folha.NATUREZA_SALARIAL
        assert r.json()["incide_inss"] and r.json()["incide_irrf"] and r.json()["incide_fgts"]

        folha = _folha(c, 1, folha_id)
        assert folha["valor_inss"] == 315.0
        assert folha["bases"]["base_inss"] == 3500.0
        assert folha["bases"]["salario_base"] == 3000.0
        assert folha["bases"]["rubricas_tributaveis"] == 500.0
        # Líquido: 3000 + 500 − 315 = 3185
        assert folha["valor_liquido"] == 3185.0
        # A referência da retenção fecha com a base — sem "valor ajustado à mão"
        inss = _linhas(folha["detalhe"], "inss")[0]
        assert "3.500,00" in inss["referencia"]
        assert inss["origem"]["confere"] is True

    @pytest.mark.parametrize("codigo", ["reembolso", "indenizacao"])
    def test_rubrica_indenizatoria_nao_toca_na_base(self, ambiente, codigo):
        """Reembolso e indenização repõem patrimônio: entram no líquido (o
        funcionário recebe) e ficam FORA das bases (não é remuneração)."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": codigo, "valor": 400.0, "descricao": "diesel"},
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        assert r.json()["natureza"] == rubrica_folha.NATUREZA_INDENIZATORIA

        folha = _folha(c, 1, folha_id)
        assert folha["valor_inss"] == 270.0, "retenção não pode subir por verba indenizatória"
        assert folha["bases"]["base_inss"] == 3000.0
        assert folha["bases"]["rubricas_tributaveis"] == 0.0
        assert folha["valor_liquido"] == 3130.0  # 3000 + 400 − 270

        linha = _linhas(folha["detalhe"], "vencimento_extra")[0]
        assert "indenizatória" in linha["referencia"]
        assert "sem incidência" in linha["referencia"]
        assert linha["provento"] == 400.0

    def test_a_linha_do_holerite_diz_de_onde_o_valor_veio(self, ambiente):
        """A regra da tela vale para as rubricas novas igual: nenhum valor
        aparece sem referência, e a linha é clicável até a origem."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={
                "especie": "vencimento", "codigo": "bonificacao_produtividade",
                "valor": 250.0, "descricao": "colheita de julho",
            },
            headers=_cab(1),
        )
        linha = _linhas(_folha(c, 1, folha_id)["detalhe"], "vencimento_extra")[0]
        assert linha["descricao"] == "Bonificação por produtividade — colheita de julho"
        assert "salarial" in linha["referencia"]
        assert "INSS, IRRF e FGTS" in linha["referencia"]
        origem = linha["origem"]
        assert origem["tipo"] == "rubrica"
        assert origem["codigo"] == "bonificacao_produtividade"
        assert "457" in origem["fundamento"]

    def test_retencao_digitada_a_mao_nao_e_recalculada(self, ambiente):
        """Sem percentual gravado não há base declarada — deduzir um percentual
        a partir do valor para aplicá-lo a outra base seria inventar o número
        (mesma regra que o holerite já seguia)."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"], percentual_inss=0.0, valor_inss=300.0)
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "gueltas", "valor": 500.0},
            headers=_cab(1),
        )
        folha = _folha(c, 1, folha_id)
        assert folha["valor_inss"] == 300.0
        assert _linhas(folha["detalhe"], "inss")[0]["referencia"] == "Valor informado, sem percentual"


# ---------------------------------------------------------------------------
# Aumento na folha — a incorporação ao vencimento base do mês seguinte
# ---------------------------------------------------------------------------
class TestAumentoIncorporaNoMesSeguinte:
    def test_competencia_seguinte_nasce_com_o_salario_novo(self, ambiente):
        """O caso do dono: folha recorrente de R$ 3.000, aumento de R$ 400 em
        julho. Julho paga 3.000 + 400 (o aumento é linha do mês em que foi
        concedido); agosto em diante o SALÁRIO é 3.400 — sem relançar nada."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(
            c, 1, ids["pessoa1"], competencia="2026-01", recorrente=True, dia_vencimento=5,
        )
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "aumento_folha", "valor": 400.0},
            headers=_cab(1),
        )
        # A listagem é quem dispara a geração por recorrência ("lazy pull").
        c.get("/cadastro/folha-pagamento", headers=_cab(1))

        with Session(engine) as s:
            geradas = s.exec(
                select(FolhaPagamento).where(
                    FolhaPagamento.pessoa_id == ids["pessoa1"],
                    FolhaPagamento.competencia > "2026-01",
                ).order_by(FolhaPagamento.competencia)
            ).all()
            assert geradas, "a recorrência precisa ter gerado ao menos um mês"
            assert all(f.valor_bruto == 3400.0 for f in geradas), [f.valor_bruto for f in geradas]
            # Base maior, retenção maior: 9% de 3.400 = 306.
            assert all(f.valor_inss == 306.0 for f in geradas)
            # E o mês em que o aumento foi concedido continua com o salário
            # ANTIGO no bruto — lá ele é linha de vencimento, não salário.
            modelo = s.get(FolhaPagamento, folha_id)
            assert modelo.valor_bruto == 3000.0
            assert modelo.valor_rubricas == 400.0

    def test_salario_base_da_pessoa_acompanha_o_aumento(self, ambiente):
        """`Pessoa.salario_base` é o valor VIVO que sugere o bruto de um
        lançamento novo: sem atualizá-lo, o aumento sumiria no primeiro mês
        lançado à mão."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "aumento_folha", "valor": 400.0},
            headers=_cab(1),
        )
        with Session(engine) as s:
            assert s.get(Pessoa, ids["pessoa1"]).salario_base == 3400.0

    def test_folha_seguinte_ja_lancada_e_corrigida(self, ambiente):
        """Quando o mês seguinte JÁ existe (lançado antes do aumento), ele é
        corrigido na hora — a incorporação não pode depender de a folha ainda
        não ter nascido."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        seguinte_id = _criar_folha(c, 1, ids["pessoa1"], competencia="2026-08")
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "aumento_folha", "valor": 400.0},
            headers=_cab(1),
        )
        with Session(engine) as s:
            seguinte = s.get(FolhaPagamento, seguinte_id)
            assert seguinte.valor_bruto == 3400.0
            assert seguinte.valor_inss == 306.0
            assert seguinte.valor_liquido == 3094.0  # 3400 − 306

    def test_excluir_o_aumento_desfaz_a_incorporacao(self, ambiente):
        """Desfazer é o mesmo caminho ao contrário — não uma segunda
        implementação que pode divergir da primeira."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        seguinte_id = _criar_folha(c, 1, ids["pessoa1"], competencia="2026-08")
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "aumento_folha", "valor": 400.0},
            headers=_cab(1),
        )
        rubrica_id = r.json()["id"]
        assert c.delete(
            f"/cadastro/folha-pagamento/rubricas/{rubrica_id}", headers=_cab(1),
        ).status_code == 200
        with Session(engine) as s:
            assert s.get(Pessoa, ids["pessoa1"]).salario_base == 3000.0
            assert s.get(FolhaPagamento, seguinte_id).valor_bruto == 3000.0
            assert s.get(FolhaPagamento, folha_id).valor_rubricas == 0.0

    def test_editar_o_aumento_propaga_so_a_diferenca(self, ambiente):
        """Corrigir de R$ 400 para R$ 600 mexe R$ 200 no salário-base — somar
        os R$ 600 outra vez daria o aumento em dobro."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "aumento_folha", "valor": 400.0},
            headers=_cab(1),
        )
        rubrica_id = r.json()["id"]
        r = c.put(
            f"/cadastro/folha-pagamento/rubricas/{rubrica_id}",
            json={"valor": 600.0}, headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Pessoa, ids["pessoa1"]).salario_base == 3600.0


# ---------------------------------------------------------------------------
# Descontos: valor direto e desconto associado a uma compra
# ---------------------------------------------------------------------------
class TestDescontosNoHolerite:
    def test_desconto_por_valor_sai_do_liquido_sem_tocar_na_base(self, ambiente):
        """Desconto não entra em base nenhuma: ele sai DEPOIS das retenções."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={
                "especie": "desconto", "codigo": "desconto_valor", "valor": 150.0,
                "descricao": "quebra de vidro",
            },
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        folha = _folha(c, 1, folha_id)
        assert folha["valor_inss"] == 270.0
        assert folha["valor_liquido"] == 2580.0  # 3000 − 270 − 150
        linha = _linhas(folha["detalhe"], "desconto_extra")[0]
        assert linha["desconto"] == 150.0
        assert linha["descricao"] == "Desconto em folha — quebra de vidro"
        assert "2026" in linha["referencia"] or "07/2026" in linha["referencia"]

    def test_desconto_de_compra_carrega_a_compra_ate_a_linha(self, ambiente):
        """A linha SABE qual é a origem (FK para a parcela do lançamento), e
        não um texto: é o que permite o clique chegar à compra e o papel citar
        a nota — o mesmo erro do vale por regex não se repete aqui."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={
                "especie": "desconto", "codigo": "desconto_compra", "valor": 480.0,
                "conta_gerencial_id": ids["compra1"],
            },
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        assert r.json()["numero_lancamento"] == "LC-2026-00001"

        linha = _linhas(_folha(c, 1, folha_id)["detalhe"], "desconto_extra")[0]
        assert "LC-2026-00001" in linha["referencia"]
        assert "Auto Peças 1" in linha["referencia"]
        assert "4471" in linha["referencia"]
        compra = linha["origem"]["compra"]
        assert compra["conta_id"] == ids["compra1"]
        assert compra["valor_total"] == 480.0

    def test_desconto_de_compra_exige_a_compra(self, ambiente):
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "desconto", "codigo": "desconto_compra", "valor": 480.0},
            headers=_cab(1),
        )
        assert r.status_code == 400, r.text

    def test_consulta_de_compras_da_janela_sobreposta(self, ambiente):
        """A pop-up escolhe entre as compras DA FAZENDA — e só despesa."""
        c, _engine, ids = ambiente
        r = c.get("/cadastro/folha-pagamento/rubricas/compras?busca=trator", headers=_cab(1))
        assert r.status_code == 200, r.text
        assert [x["conta_id"] for x in r.json()] == [ids["compra1"]]

    def test_valor_negativo_e_recusado(self, ambiente):
        """Quem diz se soma ou subtrai é a espécie, não o sinal — um desconto
        negativo viraria vencimento na coluna errada do documento."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "desconto", "codigo": "desconto_valor", "valor": -150.0},
            headers=_cab(1),
        )
        assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Folha paga: o recibo é prova
# ---------------------------------------------------------------------------
class TestFolhaPagaNaoRecebeRubrica:
    def test_recusa_com_explicacao(self, ambiente):
        c, _engine, ids = ambiente
        folha_id = _criar_folha(
            c, 1, ids["pessoa1"], status="pago", data_pagamento="2026-08-05",
        )
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "gueltas", "valor": 100.0},
            headers=_cab(1),
        )
        assert r.status_code == 400, r.text
        assert "estorne" in r.json()["detail"].lower()

    def test_rubrica_lancada_antes_do_pagamento_entra_no_recibo_congelado(self, ambiente):
        """A fotografia do pagamento precisa conter a rubrica: é ela que
        explica o líquido que saiu."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "reembolso", "valor": 200.0},
            headers=_cab(1),
        )
        folha = _folha(c, 1, folha_id)
        r = c.put(
            f"/cadastro/folha-pagamento/{folha_id}",
            json={
                "pessoa_id": ids["pessoa1"], "competencia": COMPETENCIA, "valor_bruto": 3000.0,
                "percentual_inss": 9.0, "valor_inss": 270.0,
                "status": "pago", "data_pagamento": "2026-08-05",
            },
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        paga = _folha(c, 1, folha_id)
        assert paga["recibo_congelado"] is True
        assert _linhas(paga["detalhe"], "vencimento_extra"), "o reembolso tem de estar na fotografia"
        # O líquido gravado continua sendo o que a discriminação soma.
        assert paga["valor_liquido"] == folha["valor_liquido"] == 2930.0


# ---------------------------------------------------------------------------
# Isolamento entre fazendas (o CowData não tem RLS)
# ---------------------------------------------------------------------------
class TestIsolamentoEntreFazendas:
    def test_nao_lanca_rubrica_na_folha_de_outra_fazenda(self, ambiente):
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "gueltas", "valor": 100.0},
            headers=_cab(2),
        )
        assert r.status_code == 404, r.text  # nunca 403: a folha não existe para ela
        with Session(engine) as s:
            assert s.exec(select(FolhaRubrica)).all() == []

    def test_nao_desconta_compra_de_outra_fazenda(self, ambiente):
        """O vínculo é a fronteira: escolher a compra da vizinha tem de ser
        "não encontrado", não um desconto silencioso de dado alheio."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={
                "especie": "desconto", "codigo": "desconto_compra", "valor": 100.0,
                "conta_gerencial_id": ids["compra2"],
            },
            headers=_cab(1),
        )
        assert r.status_code == 404, r.text

    def test_consulta_de_compras_nao_vaza_entre_fazendas(self, ambiente):
        c, _engine, ids = ambiente
        para_1 = c.get("/cadastro/folha-pagamento/rubricas/compras", headers=_cab(1)).json()
        para_2 = c.get("/cadastro/folha-pagamento/rubricas/compras", headers=_cab(2)).json()
        assert [x["conta_id"] for x in para_1] == [ids["compra1"]]
        assert [x["conta_id"] for x in para_2] == [ids["compra2"]]

    def test_nao_le_edita_nem_exclui_rubrica_de_outra_fazenda(self, ambiente):
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        rubrica_id = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "gueltas", "valor": 100.0},
            headers=_cab(1),
        ).json()["id"]

        assert c.get(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas", headers=_cab(2),
        ).status_code == 404
        assert c.put(
            f"/cadastro/folha-pagamento/rubricas/{rubrica_id}",
            json={"valor": 9999.0}, headers=_cab(2),
        ).status_code == 404
        assert c.delete(
            f"/cadastro/folha-pagamento/rubricas/{rubrica_id}", headers=_cab(2),
        ).status_code == 404
        # E o dono continua enxergando a própria (controle positivo).
        assert len(c.get(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas", headers=_cab(1),
        ).json()) == 1

    def test_token_sem_fazenda_nao_alcanca_a_folha_de_ninguem(self, ambiente):
        """Token legado, sem a claim "fid". São DUAS travas em série e este
        teste guarda as duas: a de porta (exigir_fazenda_selecionada, montada
        em main.py) recusa antes de entrar — por isso 409 e não 404 —, e, se
        um dia a de porta cair, o filtro incondicional das consultas daqui
        (`== fazenda_id`, que em None vira `IS NULL`) faz a folha da fazenda 1
        continuar sendo "não encontrada". O que não pode acontecer, em
        hipótese nenhuma, é o 200 que o anti-padrão tolerante
        (`if fazenda_id is not None: filtra`) devolveria."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        sem_fid = {"Authorization": f"Bearer {criar_token('admin1')}"}
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": "gueltas", "valor": 100.0},
            headers=sem_fid,
        )
        assert r.status_code == 409, r.text
        with Session(engine) as s:
            assert s.exec(select(FolhaRubrica)).all() == []
