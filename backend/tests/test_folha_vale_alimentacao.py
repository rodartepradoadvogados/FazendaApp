"""
Vale-alimentação — a verba que a folha GERA a partir do cadastro do
funcionário, e não de uma rubrica lançada mês a mês.

O QUE ESTES TESTES TRAVAM, e por que cada um é dinheiro de gente real:

1. **Mensal é o valor cheio; diário é valor × dias.** E os dias são os da
   contagem que a folha JÁ usa no salário (`holerite.dias_da_competencia`,
   extraída de `_proporcional_admissao`) — inclusive a proporcionalidade do
   mês de admissão. Uma segunda contagem de dias no mesmo sistema é como um
   mês de 28 dias vira 30 num dos lugares e ninguém percebe.
2. **"Antecipado ou vencido, para fins de competência" muda o VALOR, não só o
   texto.** Vencido, a folha de fevereiro paga o VA de fevereiro (28 dias);
   antecipado, ela paga o VA de março (31 dias). Se o regime só trocasse uma
   palavra na Referência, três diárias de benefício sumiriam do holerite sem
   ninguém ver.
3. **A verba é INDENIZATÓRIA (padrão do PAT) e não entra em base nenhuma.**
   Fazer o VA integrar INSS/IRRF/FGTS é cobrar contribuição sobre alimentação
   — o mesmo erro que o catálogo de rubricas existe para impedir. (Ressalva
   registrada no código: VA pago em DINHEIRO seria salarial; o sistema assume
   o PAT por decisão do dono.)
4. **Folha PAGA não muda.** Ligar o benefício hoje acrescenta a verba nas
   competências abertas e não reescreve um centavo de nenhum recibo já
   emitido — a discriminação dele está congelada porque holerite é PROVA.
5. **Ninguém lança esta linha à mão.** O código não aparece no formulário e
   os endpoints de rubrica recusam POST/PUT/DELETE nele: aceitar seria
   permitir uma edição que a próxima leitura da folha desfaz sozinha.
6. **O isolamento entre fazendas.** O CowData não tem RLS: quem garante que a
   configuração lida é a da pessoa DA FAZENDA DO TOKEN é a própria consulta.
   Token REAL (`criar_token`), nunca `dependency_overrides` — é o caminho
   token → get_fazenda_atual_id → consulta que está em julgamento.
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
from fazenda.rules import holerite, rubrica_folha, vale_alimentacao

# Fevereiro de 2026 tem 28 dias e março tem 31 — a escolha é o teste: é a
# diferença entre os dois que faz "antecipado" e "vencido" produzirem números
# distintos, e não só uma palavra distinta na Referência.
COMPETENCIA = "2026-02"
DIAS_FEVEREIRO = 28
DIAS_MARCO = 31
VALOR_BASE = 25.0


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes com um funcionário homônimo em cada — a da
    fazenda 2 existe para ser o alvo que a fazenda 1 não pode alcançar."""
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

        for fid in (1, 2):
            pessoa = Pessoa(
                nome="Leomir Bonfim", tipo="Funcionário", salario_base=3000.0,
                data_admissao=date(2024, 1, 10), fazenda_id=fid,
            )
            s.add(pessoa)
            s.commit()
            s.refresh(pessoa)
            ids[f"pessoa{fid}"] = pessoa.id

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


def _configurar_va(
    engine, pessoa_id: int, *, ligado: bool = True, valor: float = VALOR_BASE,
    periodicidade: str = "mensal", regime: str = "vencido", data_admissao: date | None = None,
) -> None:
    """Grava a configuração direto no cadastro. Direto no banco de propósito
    nos testes de CÁLCULO: o que está em julgamento ali é a folha ler a
    configuração, não o formulário gravá-la (o endpoint tem testes próprios,
    em `TestCadastroDaConfiguracao`)."""
    with Session(engine) as s:
        p = s.get(Pessoa, pessoa_id)
        p.vale_alimentacao = ligado
        p.vale_alimentacao_valor = valor if ligado else None
        p.vale_alimentacao_periodicidade = periodicidade if ligado else None
        p.vale_alimentacao_regime = regime if ligado else None
        if data_admissao is not None:
            p.data_admissao = data_admissao
        s.add(p)
        s.commit()


def _competencia_anterior(competencia: str, meses: int) -> str:
    ano, mes = (int(x) for x in competencia.split("-"))
    total = ano * 12 + (mes - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


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


def _linha_va(folha: dict) -> dict | None:
    """A linha de vale-alimentação do discriminado, ou None."""
    return next(
        (
            d for d in folha["detalhe"]
            if d["tipo"] == "vencimento_extra"
            and (d.get("origem") or {}).get("codigo") == vale_alimentacao.CODIGO
        ),
        None,
    )


# ---------------------------------------------------------------------------
# As regras puras: quanto, de que competência e com que contagem de dias
# ---------------------------------------------------------------------------
class TestRegraPura:
    def test_mensal_e_o_valor_cheio(self):
        """"Se mensal, é o valor cheio" — inclusive no mês de admissão. Não é
        omissão: é o que o dono descreveu, e proporcionalizar por conta própria
        seria pagar menos do que foi combinado."""
        pessoa = Pessoa(
            nome="x", tipo="Funcionário", vale_alimentacao=True, vale_alimentacao_valor=600.0,
            vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
            data_admissao=date(2026, 2, 10),
        )
        calculo = vale_alimentacao.calcular(pessoa, COMPETENCIA)
        assert calculo["valor"] == 600.0
        assert calculo["dias"] is None
        assert calculo["competencia_beneficio"] == COMPETENCIA

    def test_diario_multiplica_pelos_dias_da_competencia(self):
        pessoa = Pessoa(
            nome="x", tipo="Funcionário", vale_alimentacao=True, vale_alimentacao_valor=VALOR_BASE,
            vale_alimentacao_periodicidade="diario", vale_alimentacao_regime="vencido",
            data_admissao=date(2024, 1, 10),
        )
        calculo = vale_alimentacao.calcular(pessoa, COMPETENCIA)
        assert calculo["dias"] == DIAS_FEVEREIRO
        assert calculo["valor"] == round(VALOR_BASE * DIAS_FEVEREIRO, 2)

    def test_a_contagem_de_dias_e_a_MESMA_da_folha(self):
        """A prova de que não nasceu uma segunda contagem de dias: a que o VA
        diário usa é, número por número, a que a folha já usava para sugerir o
        salário proporcional do mês de admissão."""
        from fazenda.api.routers.cadastro.rh_folha import _proporcional_admissao

        pessoa = Pessoa(nome="x", tipo="Funcionário", data_admissao=date(2026, 2, 10))
        proporcional = _proporcional_admissao(pessoa, COMPETENCIA)
        dias, dias_mes = holerite.dias_da_competencia(COMPETENCIA, pessoa.data_admissao)
        assert (dias, dias_mes) == (proporcional["dias_trabalhados"], proporcional["dias_mes"])
        assert dias == DIAS_FEVEREIRO - 10 + 1

    def test_diario_no_mes_de_admissao_e_proporcional(self):
        pessoa = Pessoa(
            nome="x", tipo="Funcionário", vale_alimentacao=True, vale_alimentacao_valor=VALOR_BASE,
            vale_alimentacao_periodicidade="diario", vale_alimentacao_regime="vencido",
            data_admissao=date(2026, 2, 10),
        )
        calculo = vale_alimentacao.calcular(pessoa, COMPETENCIA)
        assert calculo["dias"] == 19  # 28 − 10 + 1
        assert calculo["valor"] == round(VALOR_BASE * 19, 2)

    def test_competencia_do_beneficio_traduz_antecipado_e_vencido(self):
        """Vencido: a folha de C paga o VA de C. Antecipado: o VA de uma
        competência é pago junto com a folha da ANTERIOR, logo a folha de C
        carrega o VA de C+1."""
        assert vale_alimentacao.competencia_do_beneficio("2026-02", "vencido") == "2026-02"
        assert vale_alimentacao.competencia_do_beneficio("2026-02", "antecipado") == "2026-03"
        # Virada de ano pela mesma função que a folha já usa.
        assert vale_alimentacao.competencia_do_beneficio("2026-12", "antecipado") == "2027-01"

    def test_sem_configuracao_nao_ha_verba(self):
        assert vale_alimentacao.calcular(Pessoa(nome="x", tipo="Funcionário"), COMPETENCIA) is None
        ligado_sem_valor = Pessoa(
            nome="x", tipo="Funcionário", vale_alimentacao=True, vale_alimentacao_valor=0.0,
        )
        # Benefício ligado sem valor-base não vira linha de R$ 0,00: num
        # documento oficial, zero lê como "não recebeu", que é outra afirmação.
        assert vale_alimentacao.calcular(ligado_sem_valor, COMPETENCIA) is None

    def test_valor_desconhecido_cai_no_padrao_conservador(self):
        """Typo gravado no cadastro não pode derrubar a geração da folha — e o
        padrão escolhido é o que NÃO desloca dinheiro: mensal (não multiplica)
        e vencido (não muda de competência)."""
        pessoa = Pessoa(
            nome="x", tipo="Funcionário", vale_alimentacao=True, vale_alimentacao_valor=600.0,
            vale_alimentacao_periodicidade="quinzenal", vale_alimentacao_regime="sei la",
        )
        calculo = vale_alimentacao.calcular(pessoa, COMPETENCIA)
        assert calculo["periodicidade"] == "mensal"
        assert calculo["regime"] == "vencido"
        assert calculo["valor"] == 600.0


# ---------------------------------------------------------------------------
# A folha gera a linha sozinha
# ---------------------------------------------------------------------------
class TestFolhaGeraAVerba:
    def test_sem_vale_alimentacao_nao_ha_linha_nenhuma(self, ambiente):
        """Ninguém que não configurou o benefício ganha linha, valor ou
        centavo de diferença no líquido."""
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        folha = _folha(c, 1, folha_id)
        assert _linha_va(folha) is None
        assert [d for d in folha["detalhe"] if d["tipo"] == "vencimento_extra"] == []
        assert folha["valor_rubricas"] == 0.0
        assert folha["valor_liquido"] == 2730.0  # 3000 − 270 de INSS

    def test_mensal_entra_no_holerite_e_no_liquido(self, ambiente):
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0, periodicidade="mensal", regime="vencido")
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        folha = _folha(c, 1, folha_id)

        linha = _linha_va(folha)
        assert linha is not None
        assert linha["provento"] == 600.0
        assert linha["descricao"] == "Vale-alimentação"
        # A Referência diz de onde veio o número E de que mês é o benefício —
        # nenhuma linha deste documento mostra valor sem explicar.
        assert "Mensal" in linha["referencia"]
        assert "02/2026" in linha["referencia"]
        assert folha["valor_rubricas"] == 600.0
        assert folha["valor_liquido"] == 3330.0  # 2730 + 600

    def test_diario_multiplica_pelos_dias_e_diz_a_conta(self, ambiente):
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], periodicidade="diario", regime="vencido")
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        folha = _folha(c, 1, folha_id)

        esperado = round(VALOR_BASE * DIAS_FEVEREIRO, 2)  # 700,00
        linha = _linha_va(folha)
        assert linha["provento"] == esperado
        assert f"× {DIAS_FEVEREIRO} dias" in linha["referencia"]
        assert folha["valor_liquido"] == round(2730.0 + esperado, 2)

    def test_diario_no_mes_de_admissao_usa_a_proporcionalidade_da_folha(self, ambiente):
        c, engine, ids = ambiente
        _configurar_va(
            engine, ids["pessoa1"], periodicidade="diario", regime="vencido",
            data_admissao=date(2026, 2, 10),
        )
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        linha = _linha_va(_folha(c, 1, folha_id))
        assert linha["provento"] == round(VALOR_BASE * 19, 2)
        assert "× 19 dias" in linha["referencia"]

    def test_antecipado_e_vencido_caem_em_competencias_diferentes(self, ambiente):
        """O coração do "para fins de competência". Na MESMA folha de
        fevereiro: vencido paga os 28 dias de fevereiro, antecipado paga os 31
        de março — e a Referência diz qual mês está sendo pago ali."""
        c, engine, ids = ambiente

        _configurar_va(engine, ids["pessoa1"], periodicidade="diario", regime="vencido")
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        vencido = _linha_va(_folha(c, 1, folha_id))
        assert vencido["provento"] == round(VALOR_BASE * DIAS_FEVEREIRO, 2)
        assert "competência 02/2026 (vencido)" in vencido["referencia"]

        # Mesma folha, mesma pessoa, só o regime muda no cadastro: o self-heal
        # da listagem realinha a competência aberta.
        _configurar_va(engine, ids["pessoa1"], periodicidade="diario", regime="antecipado")
        antecipado = _linha_va(_folha(c, 1, folha_id))
        assert antecipado["provento"] == round(VALOR_BASE * DIAS_MARCO, 2)
        assert "competência 03/2026 (antecipado)" in antecipado["referencia"]

    def test_ligar_e_desligar_depois_reflete_na_competencia_aberta(self, ambiente):
        """Configurar o benefício não obriga o dono a reabrir e salvar cada
        folha: o self-heal da listagem alinha as competências ainda não pagas,
        inclusive a conta a pagar, que é o número que ele efetivamente paga."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        assert _linha_va(_folha(c, 1, folha_id)) is None

        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        folha = _folha(c, 1, folha_id)
        assert _linha_va(folha)["provento"] == 600.0
        assert folha["valor_liquido"] == 3330.0
        with Session(engine) as s:
            numero = s.get(FolhaPagamento, folha_id).numero_lancamento_gerado
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first()
            assert conta.valor_total == 3330.0

        _configurar_va(engine, ids["pessoa1"], ligado=False)
        folha = _folha(c, 1, folha_id)
        assert _linha_va(folha) is None
        assert folha["valor_liquido"] == 2730.0
        with Session(engine) as s:
            assert s.exec(
                select(FolhaRubrica).where(FolhaRubrica.folha_id == folha_id)
            ).all() == []


    def test_folha_que_ja_nasce_paga_leva_a_verba_e_a_conta_bate(self, ambiente):
        """O lançamento que já nasce "pago" é gravado e congelado na MESMA
        requisição. Ele precisa nascer com a verba dentro — e a conta a pagar
        dele nasce BAIXADA (`valor_pago` preenchido), o que significa que
        ninguém a reescreve depois: se o vale-alimentação só fosse somado no
        passo seguinte, o banco pagaria um valor e o holerite mostraria outro."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        folha_id = _criar_folha(
            c, 1, ids["pessoa1"], status="pago", data_pagamento="2026-03-05",
        )
        folha = _folha(c, 1, folha_id)
        assert folha["recibo_congelado"] is True
        assert _linha_va(folha)["provento"] == 600.0
        assert folha["valor_liquido"] == 3330.0
        with Session(engine) as s:
            numero = s.get(FolhaPagamento, folha_id).numero_lancamento_gerado
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first()
            assert conta.valor_total == 3330.0
            assert conta.valor_pago == 3330.0

    def test_competencia_gerada_pela_recorrencia_ja_nasce_com_a_verba(self, ambiente):
        """A folha que a recorrência cria sozinha todo mês tem de sair com o
        vale-alimentação — e a CONTA A PAGAR dela também, porque é ela que o
        dono paga."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        atual = date.today().strftime("%Y-%m")
        inicial = _competencia_anterior(atual, 2)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": ids["pessoa1"], "competencia": inicial, "valor_bruto": 3000.0,
            "percentual_inss": 9.0, "valor_inss": 270.0,
            "recorrente": True, "dia_vencimento": 5,
        }, headers=_cab(1))
        assert r.status_code == 200, r.text

        registros = c.get("/cadastro/folha-pagamento", headers=_cab(1)).json()
        gerados = [x for x in registros if x["origem_recorrencia_id"]]
        assert len(gerados) == 2
        for gerada in gerados:
            assert _linha_va(gerada)["provento"] == 600.0
            assert gerada["valor_liquido"] == 3330.0
            assert f"competência {gerada['competencia'][5:]}/{gerada['competencia'][:4]}" \
                in _linha_va(gerada)["referencia"]
        with Session(engine) as s:
            numeros = {x["numero_lancamento_gerado"] for x in gerados}
            contas = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))
            ).all()
            assert len(contas) == 2
            assert all(conta.valor_total == 3330.0 for conta in contas)


# ---------------------------------------------------------------------------
# Enquadramento: indenizatório, fora das três bases
# ---------------------------------------------------------------------------
class TestEnquadramento:
    def test_a_verba_nao_entra_em_base_de_inss_irrf_nem_fgts(self, ambiente):
        """Padrão do PAT (CLT, art. 457, §2º; Lei 14.442/2022). Se o VA
        entrasse na base, o funcionário pagaria INSS sobre a alimentação dele
        e a fazenda provisionaria FGTS sobre ela."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        folha_id = _criar_folha(c, 1, ids["pessoa1"], percentual_fgts=8.0)
        folha = _folha(c, 1, folha_id)

        # A retenção continua sendo 9% sobre o SALÁRIO, não sobre salário + VA.
        assert folha["valor_inss"] == 270.0
        assert folha["valor_fgts"] == 240.0  # 8% de 3.000, não de 3.600
        assert folha["valor_rubricas_tributaveis"] == 0.0
        assert folha["bases"]["base_inss"] == 3000.0
        assert folha["bases"]["rubricas_tributaveis"] == 0.0

        with Session(engine) as s:
            rubrica = s.exec(
                select(FolhaRubrica).where(FolhaRubrica.folha_id == folha_id)
            ).first()
            assert rubrica.natureza == rubrica_folha.NATUREZA_INDENIZATORIA
            assert not (rubrica.incide_inss or rubrica.incide_irrf or rubrica.incide_fgts)
            # Não incorpora ao salário-base: o VA não é salário do mês seguinte.
            assert not rubrica.incorpora_base

    def test_o_verbete_do_catalogo_declara_o_padrao_pat_e_a_classe(self):
        verbete = rubrica_folha.CATALOGO_VENCIMENTOS[vale_alimentacao.CODIGO]
        assert verbete["natureza"] == rubrica_folha.NATUREZA_INDENIZATORIA
        assert not (verbete["incide_inss"] or verbete["incide_irrf"] or verbete["incide_fgts"])
        # CONTRATUAL (cadeado no pop-up de pagamento) porque o valor é DERIVADO
        # do cadastro, não medido no mês — ao contrário do vale-transporte.
        assert verbete["alteracao"] == rubrica_folha.ALTERACAO_CONTRATUAL
        assert verbete["gerado_por_cadastro"] is True
        assert "14.442" in verbete["fundamento"]

    def test_o_verbete_nao_aparece_no_formulario_de_lancamento(self):
        publico = rubrica_folha.catalogo_publico()
        assert vale_alimentacao.CODIGO not in {v["codigo"] for v in publico["vencimentos"]}


# ---------------------------------------------------------------------------
# Folha paga: a fotografia não se mexe
# ---------------------------------------------------------------------------
class TestFolhaPagaNaoMuda:
    def test_ligar_o_va_hoje_nao_altera_competencia_ja_paga(self, ambiente):
        """O recibo pago é PROVA: a discriminação dele foi congelada com o
        líquido que saiu do caixa. Ligar o benefício depois não pode
        acrescentar verba nenhuma lá — nem para mais, nem para menos."""
        c, engine, ids = ambiente
        folha_id = _criar_folha(
            c, 1, ids["pessoa1"], status="pago", data_pagamento="2026-03-05",
        )
        antes = _folha(c, 1, folha_id)
        assert antes["recibo_congelado"] is True
        assert _linha_va(antes) is None

        _configurar_va(engine, ids["pessoa1"], valor=600.0)

        depois = _folha(c, 1, folha_id)
        assert _linha_va(depois) is None
        assert depois["valor_liquido"] == antes["valor_liquido"] == 2730.0
        assert depois["valor_rubricas"] == 0.0
        with Session(engine) as s:
            assert s.exec(
                select(FolhaRubrica).where(FolhaRubrica.folha_id == folha_id)
            ).all() == []

    def test_desligar_o_va_nao_apaga_a_verba_de_folha_ja_paga(self, ambiente):
        """O caminho inverso, que é o mais perigoso: a folha foi paga COM a
        verba, e desligar o benefício no cadastro não pode reescrever o recibo
        para dizer que ela nunca foi paga."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        folha_id = _criar_folha(
            c, 1, ids["pessoa1"], status="pago", data_pagamento="2026-03-05",
        )
        paga = _folha(c, 1, folha_id)
        assert _linha_va(paga)["provento"] == 600.0
        assert paga["valor_liquido"] == 3330.0

        _configurar_va(engine, ids["pessoa1"], ligado=False)

        depois = _folha(c, 1, folha_id)
        assert _linha_va(depois)["provento"] == 600.0
        assert depois["valor_liquido"] == 3330.0


# ---------------------------------------------------------------------------
# Ninguém lança esta linha à mão
# ---------------------------------------------------------------------------
class TestNaoSeLancaAMao:
    def test_post_de_rubrica_com_o_codigo_e_recusado(self, ambiente):
        c, _engine, ids = ambiente
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        r = c.post(
            f"/cadastro/folha-pagamento/{folha_id}/rubricas",
            json={"especie": "vencimento", "codigo": vale_alimentacao.CODIGO, "valor": 500.0},
            headers=_cab(1),
        )
        assert r.status_code == 400, r.text
        assert "cadastro do funcionário" in r.json()["detail"]

    def test_put_e_delete_na_linha_gerada_sao_recusados(self, ambiente):
        """Aceitar seria pior que recusar: a próxima leitura da folha repõe a
        linha do cadastro e a edição desapareceria sozinha, com o usuário
        acreditando ter mudado alguma coisa."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa1"], valor=600.0)
        folha_id = _criar_folha(c, 1, ids["pessoa1"])
        _folha(c, 1, folha_id)  # a listagem é quem gera/alinha a linha
        with Session(engine) as s:
            rubrica_id = s.exec(
                select(FolhaRubrica).where(FolhaRubrica.folha_id == folha_id)
            ).first().id

        r = c.put(
            f"/cadastro/folha-pagamento/rubricas/{rubrica_id}",
            json={"valor": 900.0}, headers=_cab(1),
        )
        assert r.status_code == 400, r.text
        r = c.delete(f"/cadastro/folha-pagamento/rubricas/{rubrica_id}", headers=_cab(1))
        assert r.status_code == 400, r.text

        # E a linha continua valendo o que o cadastro manda.
        assert _linha_va(_folha(c, 1, folha_id))["provento"] == 600.0


# ---------------------------------------------------------------------------
# O cadastro da configuração
# ---------------------------------------------------------------------------
class TestCadastroDaConfiguracao:
    def _payload(self, **extra) -> dict:
        corpo = {"nome": "Leomir Bonfim", "tipos": ["Funcionário"]}
        corpo.update(extra)
        return corpo

    def test_grava_os_quatro_campos(self, ambiente):
        c, _engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['pessoa1']}",
            json=self._payload(
                vale_alimentacao=True, vale_alimentacao_valor=25.0,
                vale_alimentacao_periodicidade="diario", vale_alimentacao_regime="antecipado",
            ),
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["vale_alimentacao"] is True
        assert corpo["vale_alimentacao_valor"] == 25.0
        assert corpo["vale_alimentacao_periodicidade"] == "diario"
        assert corpo["vale_alimentacao_regime"] == "antecipado"

    @pytest.mark.parametrize("faltando,trecho", [
        ({"vale_alimentacao_valor": 0.0, "vale_alimentacao_periodicidade": "diario",
          "vale_alimentacao_regime": "vencido"}, "valor-base"),
        ({"vale_alimentacao_valor": 25.0, "vale_alimentacao_regime": "vencido"}, "diário ou mensal"),
        ({"vale_alimentacao_valor": 25.0, "vale_alimentacao_periodicidade": "diario"}, "antecipado ou vencido"),
    ])
    def test_configuracao_incompleta_e_recusada(self, ambiente, faltando, trecho):
        """Recusa no CADASTRO, que é onde o usuário está olhando. As regras
        normalizam o nulo para o padrão conservador — mas isso é a rede de
        segurança do dado já gravado, não licença para aceitar lixo novo."""
        c, _engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['pessoa1']}",
            json=self._payload(vale_alimentacao=True, **faltando), headers=_cab(1),
        )
        assert r.status_code == 400, r.text
        assert trecho in r.json()["detail"]

    def test_beneficio_desligado_nao_exige_nada(self, ambiente):
        c, _engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['pessoa1']}", json=self._payload(), headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        assert r.json()["vale_alimentacao"] is False


# ---------------------------------------------------------------------------
# Isolamento entre fazendas — com contraprova
# ---------------------------------------------------------------------------
class TestIsolamentoEntreFazendas:
    def test_configuracao_de_outra_fazenda_nao_gera_verba_aqui(self, ambiente):
        """Os dois funcionários são homônimos (colisão de texto entre tenants é
        o caso normal). Só o da fazenda 2 tem vale-alimentação: a folha da
        fazenda 1 não pode ganhar linha nenhuma por causa disso."""
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa2"], valor=600.0)

        folha1 = _criar_folha(c, 1, ids["pessoa1"])
        assert _linha_va(_folha(c, 1, folha1)) is None
        assert _folha(c, 1, folha1)["valor_liquido"] == 2730.0

        # CONTRAPROVA: na fazenda dona da configuração, a verba aparece — ou o
        # teste acima estaria passando por a feature simplesmente não funcionar.
        folha2 = _criar_folha(c, 2, ids["pessoa2"])
        assert _linha_va(_folha(c, 2, folha2))["provento"] == 600.0
        assert _folha(c, 2, folha2)["valor_liquido"] == 3330.0

    def test_nao_se_configura_o_va_de_pessoa_de_outra_fazenda(self, ambiente):
        """404, nunca 403: um 403 confirmaria que aquele id existe."""
        c, engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['pessoa2']}",
            json={
                "nome": "Leomir Bonfim", "tipos": ["Funcionário"], "vale_alimentacao": True,
                "vale_alimentacao_valor": 999.0, "vale_alimentacao_periodicidade": "mensal",
                "vale_alimentacao_regime": "vencido",
            },
            headers=_cab(1),
        )
        assert r.status_code == 404, r.text
        with Session(engine) as s:
            assert s.get(Pessoa, ids["pessoa2"]).vale_alimentacao is False

    def test_a_rubrica_gerada_nasce_carimbada_com_a_fazenda_da_folha(self, ambiente):
        c, engine, ids = ambiente
        _configurar_va(engine, ids["pessoa2"], valor=600.0)
        folha2 = _criar_folha(c, 2, ids["pessoa2"])
        _folha(c, 2, folha2)
        with Session(engine) as s:
            rubrica = s.exec(
                select(FolhaRubrica).where(FolhaRubrica.folha_id == folha2)
            ).first()
            assert rubrica.fazenda_id == 2
            # E a fazenda 1 não alcança a linha da 2 por id (404, não 403).
            r = c.put(
                f"/cadastro/folha-pagamento/rubricas/{rubrica.id}",
                json={"valor": 1.0}, headers=_cab(1),
            )
            assert r.status_code == 404, r.text
