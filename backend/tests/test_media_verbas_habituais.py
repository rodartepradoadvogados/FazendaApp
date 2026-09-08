"""
Média das parcelas SALARIAIS VARIÁVEIS habituais no 13º, nas férias e na
rescisão — o buraco antigo que a entrega do vale-alimentação revelou.

O QUE ESTES TESTES TRAVAM, e por que cada um é dinheiro de gente real:

1. **DESLIGADO = IDÊNTICO A HOJE.** É o teste mais importante do arquivo. O
   parâmetro `calcula_media_verbas_variaveis` nasce FALSO, e com ele falso as
   três funções puras têm de devolver exatamente os mesmos centavos que
   devolviam antes desta feature — com números concretos, não com "assert
   algo". Nenhuma fazenda existente pode mudar de comportamento porque um
   arquivo novo entrou no repositório.
2. **Cada verba com a SUA janela.** 13º pela média do ANO CIVIL (Decreto
   57.155/65, art. 2º), férias pela do PERÍODO AQUISITIVO (CLT, art. 142) e
   aviso prévio indenizado pela dos ÚLTIMOS 12 MESES. Usar a mesma janela nas
   três seria escolher a resposta errada para duas delas.
3. **O terço constitucional incide sobre o total JÁ com a média.** Não é
   detalhe de arredondamento: é 1/3 de uma base maior.
4. **Natureza manda, código não.** Bonificação (salarial) entra; reembolso
   (indenizatório) não. E a natureza sai da LINHA já gravada
   (`FolhaRubrica.natureza`), não do catálogo de hoje — é o mesmo dado
   congelado que faz o holerite ser prova.
5. **O vale-alimentação cruza com a árvore dele.** VA pago em DINHEIRO é
   salarial (CLT, art. 457, §2º) e entra na média; VA em CARTÃO é
   indenizatório (OJ 133 da SDI-1 do TST) e não entra. Nenhuma linha de
   `media_verbas_habituais.py` conhece essa árvore — ela lê o resultado que
   `_sincronizar_vale_alimentacao` já gravou.
6. **Folha já paga não é recalculada quando o parâmetro é ligado depois.** É a
   trava inegociável: ligar a média hoje não reescreve um centavo de nenhum
   13º, férias ou rescisão já pagos/fechados.
7. **A composição bate com o valor.** Média que ninguém consegue conferir é
   média que ninguém usa: a soma das competências exibidas dividida pelo
   divisor exibido tem de dar exatamente a média aplicada.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, DecimoTerceiro, Fazenda, FeriasFuncionario,
    FolhaRubrica, ParametroFazenda, Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import media_verbas_habituais, rubrica_folha
from fazenda.rules.folha_rh import calcular_decimo_terceiro, calcular_ferias, calcular_rescisao


SALARIO = 3000.0


# ---------------------------------------------------------------------------
# 1. DESLIGADO = IDÊNTICO A HOJE — funções puras, números concretos
#
# Estes cinco testes não usam banco nem parâmetro: eles travam o PADRÃO das
# funções puras (`media_variaveis=0.0`). Se um deles quebrar, é porque alguém
# mudou o comportamento de quem NÃO ligou nada — que é justamente o que o dono
# pediu para não acontecer.
# ---------------------------------------------------------------------------
class TestDesligadoNaoMudaNada:
    def test_ferias_sem_media_e_o_numero_de_sempre(self):
        # 30 dias, salário 3.000 → dia 100 → férias 3.000 + 1/3 = 4.000.
        sem_argumento = calcular_ferias(SALARIO, 30, 0, 1 / 3)
        com_zero_explicito = calcular_ferias(SALARIO, 30, 0, 1 / 3, 0.0)
        assert sem_argumento["valor_ferias"] == 3000.0
        assert sem_argumento["valor_terco_constitucional"] == 1000.0
        assert sem_argumento["valor_total"] == 4000.0
        assert com_zero_explicito == sem_argumento

    def test_ferias_com_abono_sem_media_e_o_numero_de_sempre(self):
        # 20 gozados + 10 vendidos, salário 3.000 → dia 100.
        r = calcular_ferias(SALARIO, 20, 10, 1 / 3)
        assert r["valor_ferias"] == 2000.0
        assert r["valor_terco_constitucional"] == 666.67
        assert r["valor_abono"] == 1333.33
        assert r["valor_total"] == 4000.0

    def test_decimo_terceiro_sem_media_e_o_numero_de_sempre(self):
        assert calcular_decimo_terceiro(3600.0, 12) == 3600.0
        assert calcular_decimo_terceiro(3600.0, 6) == 1800.0
        assert calcular_decimo_terceiro(3600.0, 6, 0.0) == 1800.0

    def test_rescisao_sem_media_e_o_numero_de_sempre(self):
        # Mesmos parâmetros de `test_calcular_rescisao_sem_justa_causa`
        # (test_folha_rh.py): admissão 20/01/2026, desligamento 20/07/2026.
        r = calcular_rescisao(SALARIO, date(2026, 1, 20), date(2026, 7, 20), "sem_justa_causa")
        assert r["saldo_salario"]["valor"] == 2000.0
        assert r["aviso_previo"]["valor"] == 3000.0
        assert r["ferias_proporcionais"]["valor_total"] == 2333.33
        assert r["decimo_terceiro_proporcional"]["valor"] == 1750.0
        assert r["fgts"]["multa"] == 672.0
        assert r["valor_total"] == 9755.33
        # E o bloco de médias existe, dizendo que nenhuma entrou.
        assert r["medias_variaveis"] == {
            "decimo_terceiro": 0.0, "ferias": 0.0, "aviso_previo": 0.0, "alguma": False,
        }

    def test_rescisao_com_as_tres_medias_em_zero_e_identica(self):
        args = (SALARIO, date(2026, 1, 20), date(2026, 7, 20), "sem_justa_causa", 30, False)
        assert calcular_rescisao(*args) == calcular_rescisao(*args, 1 / 3, 0.08, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# 2. LIGADO — as três janelas, nas funções puras
# ---------------------------------------------------------------------------
class TestMediaNasFuncoesPuras:
    def test_decimo_terceiro_soma_a_media_do_ano_civil(self):
        """Salário 3.000, média de variáveis 600, 12 meses → 13º de 3.600.
        (3.000 + 600) / 12 × 12. Sem a média, o mesmo caso dava 3.000 — os
        R$ 600 de bonificação habitual mensal ficavam de fora do 13º."""
        assert calcular_decimo_terceiro(SALARIO, 12, 600.0) == 3600.0

    def test_decimo_terceiro_proporcional_usa_o_mesmo_divisor_dos_avos(self):
        """Admitido em julho, 6 avos, R$ 3.600 de variável no semestre →
        média 600 (3.600/6) e 13º de (3.000+600)/12×6 = 1.800."""
        assert calcular_decimo_terceiro(SALARIO, 6, 3600.0 / 6) == 1800.0

    def test_ferias_o_terco_incide_sobre_o_total_ja_com_a_media(self):
        """Salário 3.000 + média 600 → base 3.600, dia 120, 30 dias = 3.600 de
        férias e 1.200 de terço (1/3 de 3.600, e NÃO 1.000, que seria o terço
        do salário puro). Total 4.800."""
        r = calcular_ferias(SALARIO, 30, 0, 1 / 3, 600.0)
        assert r["base_calculo"] == 3600.0
        assert r["valor_ferias"] == 3600.0
        assert r["valor_terco_constitucional"] == 1200.0
        assert r["valor_total"] == 4800.0

    def test_rescisao_cada_verba_com_a_sua_media(self):
        """As três médias são DIFERENTES de propósito — é assim que se prova
        que cada uma foi para a verba certa e não houve troca entre elas."""
        r = calcular_rescisao(
            SALARIO, date(2025, 1, 20), date(2026, 7, 20), "sem_justa_causa",
            dias_ferias_vencidas=30, aviso_previo_trabalhado=False,
            percentual_terco=1 / 3, percentual_estimado_fgts_mensal=0.08,
            media_variaveis_decimo_terceiro=300.0,
            media_variaveis_ferias=600.0,
            media_variaveis_aviso_previo=900.0,
        )
        # Aviso prévio: 30 + 3 (1 ano completo) = 33 dias, base 3.900 → 4.290.
        assert r["aviso_previo"]["dias"] == 33
        assert r["aviso_previo"]["valor"] == round(3900.0 / 30 * 33, 2)
        # Férias vencidas (30 dias): base 3.600 → 3.600 + 1.200 = 4.800.
        assert r["ferias_vencidas"]["valor_total"] == 4800.0
        # 13º proporcional: base 3.300, 8 avos (jan a ago, com a projeção do
        # aviso) → 3.300/12 × 8.
        meses_13 = r["decimo_terceiro_proporcional"]["meses"]
        assert r["decimo_terceiro_proporcional"]["valor"] == round(3300.0 / 12 * meses_13, 2)
        # A multa do FGTS NÃO leva média — é estimativa declarada.
        assert r["fgts"]["deposito_total_estimado"] == round(
            SALARIO * 0.08 * r["fgts"]["meses_considerados"], 2
        )
        assert r["medias_variaveis"]["alguma"] is True

    def test_saldo_de_salario_nunca_leva_media(self):
        """O saldo é o salário dos dias trabalhados no mês da rescisão, e a
        variável desse mês sai na folha desse mês. Somar média aqui pagaria a
        mesma parcela duas vezes."""
        com = calcular_rescisao(
            SALARIO, date(2025, 1, 20), date(2026, 7, 20), "sem_justa_causa",
            media_variaveis_decimo_terceiro=300.0, media_variaveis_ferias=600.0,
            media_variaveis_aviso_previo=900.0,
        )
        sem = calcular_rescisao(SALARIO, date(2025, 1, 20), date(2026, 7, 20), "sem_justa_causa")
        assert com["saldo_salario"] == sem["saldo_salario"]


# ---------------------------------------------------------------------------
# Ambiente com banco — duas fazendas, para o recorte ser testado junto
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

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Vizinha"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
        s.commit()
        for fid in (1, 2):
            pessoa = Pessoa(
                nome="Leomir Bonfim", tipo="Funcionário", salario_base=SALARIO,
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
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


def _ligar_media(engine, fazenda_id: int | None = None, ligado: bool = True) -> None:
    """Liga/desliga o parâmetro. `fazenda_id=None` grava o padrão GLOBAL (a
    linha que o seed cria); um id grava a personalização daquela fazenda —
    é assim que `parametros._linha` resolve a precedência."""
    with Session(engine) as s:
        linha = s.exec(
            select(ParametroFazenda).where(
                ParametroFazenda.chave == "calcula_media_verbas_variaveis",
                ParametroFazenda.fazenda_id == fazenda_id,
            )
        ).first()
        if linha is None:
            linha = ParametroFazenda(
                chave="calcula_media_verbas_variaveis", grupo="folha_rh",
                label="Média de verbas variáveis", tipo="bool", fazenda_id=fazenda_id,
                valor="false",
            )
        linha.valor = "true" if ligado else "false"
        s.add(linha)
        s.commit()


def _folha(c, fazenda_id: int, pessoa_id: int, competencia: str, **extra) -> int:
    corpo = {"pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": SALARIO}
    corpo.update(extra)
    r = c.post("/cadastro/folha-pagamento", json=corpo, headers=_cab(fazenda_id))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _rubrica(c, fazenda_id: int, folha_id: int, codigo: str, valor: float, especie: str = "vencimento"):
    r = c.post(
        f"/cadastro/folha-pagamento/{folha_id}/rubricas",
        json={"especie": especie, "codigo": codigo, "valor": valor, "descricao": "teste"},
        headers=_cab(fazenda_id),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _bonificar(c, engine, fazenda_id: int, pessoa_id: int, competencias: list[str], valor: float) -> None:
    """Uma folha e uma bonificação por produtividade (SALARIAL — CLT, art.
    457, §1º) em cada competência."""
    for competencia in competencias:
        folha_id = _folha(c, fazenda_id, pessoa_id, competencia)
        _rubrica(c, fazenda_id, folha_id, "bonificacao_produtividade", valor)


# ---------------------------------------------------------------------------
# 3. A apuração com banco — janelas, divisor, natureza e recorte de fazenda
# ---------------------------------------------------------------------------
class TestApuracao:
    def test_so_o_salarial_entra_o_indenizatorio_nao(self, ambiente):
        """Bonificação (salarial) entra; reembolso (indenizatório) não. A
        natureza sai da LINHA gravada, não do código nem do catálogo de hoje."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        folha_id = _folha(c, 1, pessoa_id, "2026-03")
        _rubrica(c, 1, folha_id, "bonificacao_produtividade", 600.0)
        _rubrica(c, 1, folha_id, "reembolso", 400.0)

        with Session(engine) as s:
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 600.0
        assert resultado["divisor"] == 12
        assert resultado["media"] == 50.0
        # E o reembolso nem aparece na composição — não é "somado zero", é
        # ausente: ele não é parcela salarial.
        marco = next(x for x in resultado["competencias"] if x["competencia"] == "2026-03")
        assert [r["codigo"] for r in marco["rubricas"]] == ["bonificacao_produtividade"]

    def test_divisor_conta_mes_sem_folha_lancada(self, ambiente):
        """A escolha que muda dinheiro: o mês em que o contrato estava em vigor
        mas não há folha lançada entra no divisor valendo ZERO (Decreto
        57.155/65, art. 2º — "meses de vigência do contrato"). E a composição
        DIZ quantos são, para o dono ver o divisor que produziu a média."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, ["2026-01", "2026-02"], 600.0)

        with Session(engine) as s:
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 1200.0
        assert resultado["divisor"] == 12  # e não 2
        assert resultado["media"] == 100.0
        assert resultado["competencias_sem_folha"] == 10

    def test_menos_de_doze_meses_de_casa_divide_pelos_meses_de_vigencia(self, ambiente):
        """Admitido em 10/07/2026: o ano civil de 2026 tem 6 meses de vigência
        (jul a dez, pela regra dos 15 dias — 22 dias em julho). R$ 3.600 de
        variável no semestre → média 600, e não 300 (que sairia de dividir por
        12) nem 1.800 (de dividir só pelos 2 meses com bonificação)."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        with Session(engine) as s:
            p = s.get(Pessoa, pessoa_id)
            p.data_admissao = date(2026, 7, 10)
            s.add(p)
            s.commit()
        _bonificar(c, engine, 1, pessoa_id, ["2026-08", "2026-09"], 1800.0)

        with Session(engine) as s:
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2026, 7, 10),
            )
        assert resultado["divisor"] == 6
        assert resultado["total"] == 3600.0
        assert resultado["media"] == 600.0
        # Janeiro a junho nem entram na composição: não são "mês sem folha",
        # são mês em que a pessoa não era empregada.
        assert [x["competencia"] for x in resultado["competencias"]] == [
            "2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12",
        ]

    def test_janela_do_periodo_aquisitivo_ignora_o_que_esta_fora_dela(self, ambiente):
        """A média das férias é do PERÍODO AQUISITIVO (CLT, art. 142), não do
        ano civil: uma bonificação de dezembro/2025 entra no período
        2025-06-01→2026-05-31 e uma de junho/2026 não."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, ["2025-12", "2026-06"], 1200.0)

        with Session(engine) as s:
            resultado = media_verbas_habituais.media_do_periodo_aquisitivo(
                s, pessoa_id, 1, date(2025, 6, 1), date(2026, 5, 31),
                data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 1200.0  # só a de dezembro
        assert resultado["divisor"] == 12
        assert resultado["media"] == 100.0

    def test_ultimos_12_meses_sao_doze_competencias(self, ambiente):
        """Doze, não treze: a janela fecha no mês da referência e começa 11
        meses antes. Um divisor de 13 diluiria o aviso prévio de todo mundo."""
        c, engine, ids = ambiente
        with Session(engine) as s:
            resultado = media_verbas_habituais.media_dos_ultimos_12_meses(
                s, ids["pessoa1"], 1, date(2026, 9, 20), data_admissao=date(2024, 1, 10),
            )
        assert len(resultado["competencias"]) == 12
        assert resultado["competencias"][0]["competencia"] == "2025-10"
        assert resultado["competencias"][-1]["competencia"] == "2026-09"
        assert resultado["divisor"] == 12

    def test_a_composicao_bate_com_o_valor(self, ambiente):
        """Média que ninguém consegue conferir é média que ninguém usa: a soma
        das competências exibidas, dividida pelo divisor exibido, TEM de dar a
        média aplicada — e a soma das rubricas de cada competência tem de dar o
        valor daquela competência."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        folha_id = _folha(c, 1, pessoa_id, "2026-04")
        _rubrica(c, 1, folha_id, "bonificacao_produtividade", 500.0)
        _rubrica(c, 1, folha_id, "gueltas", 220.0)
        _bonificar(c, engine, 1, pessoa_id, ["2026-05"], 280.0)

        with Session(engine) as s:
            r = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert round(sum(x["valor"] for x in r["competencias"]), 2) == r["total"]
        for competencia in r["competencias"]:
            assert round(sum(x["valor"] for x in competencia["rubricas"]), 2) == competencia["valor"]
        assert round(r["total"] / r["divisor"], 2) == r["media"]
        assert r["total"] == 1000.0
        assert r["media"] == 83.33

    def test_recorte_de_fazenda_na_consulta(self, ambiente):
        """A bonificação da fazenda 2 não pode entrar na média da fazenda 1 —
        o filtro vai DENTRO da consulta, sempre."""
        c, engine, ids = ambiente
        _bonificar(c, engine, 2, ids["pessoa2"], ["2026-03"], 6000.0)
        with Session(engine) as s:
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, ids["pessoa1"], 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 0.0
        assert resultado["media"] == 0.0

    def test_nao_apurada_diz_por_que(self):
        """`aplicada: False` é o que separa "a média deu zero" de "a média nem
        foi tentada" — o recibo mostra uma coisa ou outra."""
        r = media_verbas_habituais.nao_apurada(media_verbas_habituais.JANELA_ANO_CIVIL)
        assert r["aplicada"] is False
        assert r["media"] == 0.0
        assert "desligado" in r["motivo"]


# ---------------------------------------------------------------------------
# 4. O vale-alimentação cruzando com a árvore da natureza
# ---------------------------------------------------------------------------
class TestValeAlimentacao:
    def _configurar(self, engine, pessoa_id: int, forma: str) -> None:
        with Session(engine) as s:
            p = s.get(Pessoa, pessoa_id)
            p.vale_alimentacao = True
            p.vale_alimentacao_valor = 600.0
            p.vale_alimentacao_periodicidade = "mensal"
            p.vale_alimentacao_regime = "vencido"
            p.vale_alimentacao_forma = forma
            s.add(p)
            s.commit()

    def test_vale_alimentacao_em_dinheiro_e_salarial_e_entra(self, ambiente):
        """Pago em DINHEIRO, o auxílio é salarial (CLT, art. 457, §2º — a
        exclusão vale "vedado seu pagamento em dinheiro") e integra a média."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        self._configurar(engine, pessoa_id, "dinheiro")
        _folha(c, 1, pessoa_id, "2026-03")

        with Session(engine) as s:
            linha = s.exec(
                select(FolhaRubrica).where(FolhaRubrica.codigo == "vale_alimentacao")
            ).first()
            assert linha is not None and linha.natureza == rubrica_folha.NATUREZA_SALARIAL
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 600.0
        assert resultado["media"] == 50.0

    def test_vale_alimentacao_em_cartao_e_indenizatorio_e_nao_entra(self, ambiente):
        """Em CARTÃO/ticket é indenizatório (OJ 133 da SDI-1 do TST; Solução de
        Consulta COSIT 35/2019) — mesma verba, mesmo valor, mesmo código, e
        fora da média. Quem decidiu foi a árvore de `vale_alimentacao.py`; a
        média só leu a natureza que ela gravou na linha."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        self._configurar(engine, pessoa_id, "cartao")
        _folha(c, 1, pessoa_id, "2026-03")

        with Session(engine) as s:
            linha = s.exec(
                select(FolhaRubrica).where(FolhaRubrica.codigo == "vale_alimentacao")
            ).first()
            assert linha is not None and linha.natureza == rubrica_folha.NATUREZA_INDENIZATORIA
            resultado = media_verbas_habituais.media_do_ano_civil(
                s, pessoa_id, 1, 2026, data_admissao=date(2024, 1, 10),
            )
        assert resultado["total"] == 0.0


# ---------------------------------------------------------------------------
# 5. Ponta a ponta pelos endpoints — desligado, ligado, e o já pago
# ---------------------------------------------------------------------------
class TestEndpoints:
    def _payload_ferias(self, pessoa_id: int, **over) -> dict:
        base = {
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-06-01",
            "periodo_aquisitivo_fim": "2026-05-31",
            "dias_direito": 30, "dias_gozados": 30,
            "data_inicio_gozo": "2026-07-01", "data_fim_gozo": "2026-07-30",
            "abono_pecuniario_dias": 0,
        }
        base.update(over)
        return base

    def test_desligado_ferias_saem_so_sobre_o_salario(self, ambiente):
        """O teste mais importante do arquivo, agora ponta a ponta: com o
        parâmetro no padrão (desligado), a bonificação existe na folha e NÃO
        entra nas férias."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, ["2025-12", "2026-01"], 1200.0)

        r = c.post("/cadastro/ferias", json=self._payload_ferias(pessoa_id), headers=_cab(1))
        assert r.status_code == 200, r.text
        corpo = r.json()
        # 0.3333 é o `percentual_terco_constitucional_ferias` do parâmetro
        # (não 1/3 exato) — o mesmo que o endpoint usa desde sempre.
        assert corpo["valor_total"] == calcular_ferias(SALARIO, 30, 0, 0.3333)["valor_total"] == 3999.9
        assert corpo["media_variaveis"] is None
        assert corpo["media_variaveis_detalhe"]["aplicada"] is False

    def test_ligado_ferias_usam_a_media_do_periodo_aquisitivo(self, ambiente):
        """R$ 2.400 de bonificação dentro do período aquisitivo / 12 = 200 de
        média. Base 3.200 → dia 106,67 → 30 dias = 3.200,10 + 1/3."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _ligar_media(engine, fazenda_id=1)
        _bonificar(c, engine, 1, pessoa_id, ["2025-12", "2026-01"], 1200.0)

        r = c.post("/cadastro/ferias", json=self._payload_ferias(pessoa_id), headers=_cab(1))
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["media_variaveis"] == 200.0
        esperado = calcular_ferias(SALARIO, 30, 0, 0.3333, 200.0)
        assert corpo["valor_total"] == esperado["valor_total"]
        assert corpo["valor_total"] > calcular_ferias(SALARIO, 30, 0, 0.3333)["valor_total"]
        # A composição gravada bate com o valor aplicado.
        detalhe = corpo["media_variaveis_detalhe"]
        assert detalhe["aplicada"] is True
        assert round(detalhe["total"] / detalhe["divisor"], 2) == corpo["media_variaveis"]
        assert detalhe["total"] == 2400.0

    def test_ligado_decimo_terceiro_usa_a_media_do_ano_civil(self, ambiente):
        """R$ 7.200 de bonificação em 2026 / 12 avos = 600 de média →
        13º de (3.000 + 600) = 3.600."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _ligar_media(engine, fazenda_id=1)
        _bonificar(c, engine, 1, pessoa_id, [f"2026-{m:02d}" for m in range(1, 13)], 600.0)

        r = c.post(
            "/cadastro/decimo-terceiro",
            json={"pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12},
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["media_variaveis"] == 600.0
        assert corpo["valor_integral"] == 3600.0
        assert corpo["media_variaveis_detalhe"]["total"] == 7200.0
        assert corpo["media_variaveis_detalhe"]["divisor"] == 12

    def test_decimo_terceiro_pago_nao_e_recalculado_ao_ligar_depois(self, ambiente):
        """A trava inegociável: lançar com o parâmetro desligado, LIGAR
        depois, e o registro pago continuar valendo o que valia — a edição é
        recusada, não recalculada em silêncio."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, [f"2026-{m:02d}" for m in range(1, 13)], 600.0)
        corpo = {
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
            "status": "pago", "data_pagamento": "2026-12-20",
        }
        r = c.post("/cadastro/decimo-terceiro", json=corpo, headers=_cab(1))
        assert r.status_code == 200, r.text
        registro_id = r.json()["id"]
        assert r.json()["valor_integral"] == 3000.0

        _ligar_media(engine, fazenda_id=1)
        # O PUT (que é por onde um recálculo entraria) é RECUSADO.
        r = c.put(f"/cadastro/decimo-terceiro/{registro_id}", json=corpo, headers=_cab(1))
        assert r.status_code == 400
        assert "já pago" in r.json()["detail"]

        with Session(engine) as s:
            gravado = s.get(DecimoTerceiro, registro_id)
            assert gravado.valor_integral == 3000.0
            assert gravado.media_variaveis is None

    def test_ferias_pagas_nao_sao_recalculadas_ao_ligar_depois(self, ambiente):
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, ["2025-12", "2026-01"], 1200.0)
        payload = self._payload_ferias(pessoa_id, status="pago", data_pagamento="2026-06-29")
        r = c.post("/cadastro/ferias", json=payload, headers=_cab(1))
        assert r.status_code == 200, r.text
        registro_id = r.json()["id"]
        assert r.json()["valor_total"] == 3999.9

        _ligar_media(engine, fazenda_id=1)
        r = c.put(f"/cadastro/ferias/{registro_id}", json=payload, headers=_cab(1))
        assert r.status_code == 400
        with Session(engine) as s:
            assert s.get(FeriasFuncionario, registro_id).valor_total == 3999.9

    def test_rescisao_ligada_aplica_as_tres_medias_e_congela_a_composicao(self, ambiente):
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _ligar_media(engine, fazenda_id=1)
        _bonificar(c, engine, 1, pessoa_id, [f"2026-{m:02d}" for m in range(1, 7)], 600.0)

        r = c.post(
            "/cadastro/rescisoes",
            json={
                "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
                "data_desligamento": "2026-07-20", "dias_ferias_vencidas": 30,
            },
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        # 13º: R$ 3.600 no ano civil / 7 meses de vigência (jan–jul) = 514,29.
        assert corpo["media_variaveis_decimo_terceiro"] == 514.29
        # As três composições vêm juntas e são de janelas diferentes.
        composicoes = corpo["medias_variaveis_composicao"]
        assert set(composicoes) == {"decimo_terceiro", "ferias", "aviso_previo"}
        assert composicoes["decimo_terceiro"]["janela"] == "ano_civil"
        assert composicoes["ferias"]["janela"] == "periodo_aquisitivo"
        assert composicoes["aviso_previo"]["janela"] == "ultimos_12_meses"
        # E a média aparece no RÓTULO da verba, no documento que o dono lê.
        rotulos = " | ".join(linha["label"] for linha in corpo["detalhe"])
        assert "média de variáveis" in rotulos

    def test_rescisao_desligada_nao_muda_nada_e_nao_escreve_media(self, ambiente):
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _bonificar(c, engine, 1, pessoa_id, [f"2026-{m:02d}" for m in range(1, 7)], 600.0)
        r = c.post(
            "/cadastro/rescisao/calcular",
            json={
                "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
                "data_desligamento": "2026-07-20", "dias_ferias_vencidas": 0,
            },
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        esperado = calcular_rescisao(
            SALARIO, date(2024, 1, 10), date(2026, 7, 20), "sem_justa_causa", 0, False, 0.3333, 0.08,
        )
        assert corpo["valor_total"] == esperado["valor_total"]
        assert corpo["medias_variaveis"]["alguma"] is False
        assert corpo["medias_variaveis_composicao"]["ferias"]["aplicada"] is False

    def test_previa_da_media_404_para_pessoa_de_outra_fazenda(self, ambiente):
        """404, nunca 403: quem não é da fazenda não fica sabendo nem que o id
        existe."""
        c, engine, ids = ambiente
        _ligar_media(engine, fazenda_id=1)
        r = c.get(
            "/cadastro/media-verbas-variaveis",
            params={"pessoa_id": ids["pessoa2"], "janela": "ano_civil", "ano": 2026},
            headers=_cab(1),
        )
        assert r.status_code == 404

    def test_previa_da_media_espelha_o_que_o_lancamento_vai_gravar(self, ambiente):
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _ligar_media(engine, fazenda_id=1)
        _bonificar(c, engine, 1, pessoa_id, ["2025-12", "2026-01"], 1200.0)

        previa = c.get(
            "/cadastro/media-verbas-variaveis",
            params={
                "pessoa_id": pessoa_id, "janela": "periodo_aquisitivo",
                "inicio": "2025-06-01", "fim": "2026-05-31",
            },
            headers=_cab(1),
        )
        assert previa.status_code == 200, previa.text
        lancado = c.post("/cadastro/ferias", json=self._payload_ferias(pessoa_id), headers=_cab(1))
        assert lancado.status_code == 200, lancado.text
        assert previa.json()["media"] == lancado.json()["media_variaveis"]
        assert previa.json()["competencias"] == lancado.json()["media_variaveis_detalhe"]["competencias"]

    def test_previa_desligada_devolve_nao_apurada(self, ambiente):
        c, engine, ids = ambiente
        r = c.get(
            "/cadastro/media-verbas-variaveis",
            params={"pessoa_id": ids["pessoa1"], "janela": "ano_civil", "ano": 2026},
            headers=_cab(1),
        )
        assert r.status_code == 200, r.text
        assert r.json()["aplicada"] is False

    def test_composicao_gravada_e_json_valido_e_legivel(self, ambiente):
        """A composição vai para o banco como JSON com acentos preservados —
        `ensure_ascii=False`. Um "período aquisitivo" escrito \\u00ed no
        relatório do contador é um documento que ninguém assina."""
        c, engine, ids = ambiente
        pessoa_id = ids["pessoa1"]
        _ligar_media(engine, fazenda_id=1)
        _bonificar(c, engine, 1, pessoa_id, ["2025-12"], 1200.0)
        r = c.post("/cadastro/ferias", json=self._payload_ferias(pessoa_id), headers=_cab(1))
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            bruto = s.get(FeriasFuncionario, r.json()["id"]).media_variaveis_composicao
        assert "período aquisitivo" in bruto
        assert json.loads(bruto)["janela"] == "periodo_aquisitivo"
