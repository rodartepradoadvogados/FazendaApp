"""
Estado reprodutivo ao vivo — cada teste reproduz um erro de classificação
REAL reportado pelo produtor em 28/07/2026 (animais e datas verdadeiros da
Fazenda Estreito Ponte de Pedra), provando que a lista agora lê os registros
em vez do texto congelado de Animal.sit_rep.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.estado_reprodutivo import (
    APTA, ATRASADA, EM_PROTOCOLO, GESTANTE, INSEMINADA, NAO_APTA, PEV,
    classificar_animal, data_em_que_ficou_apta, descrever_servico,
)

HOJE = date(2026, 7, 28)
PEV_DIAS = 45
DEL_MAX_1O_SERVICO = 90


def _classificar(numero, **kw):
    base = dict(
        hoje=HOJE, partos=[], servicos=[], aplicacoes_iatf=[],
        pev_dias=PEV_DIAS, del_max_1o_servico=DEL_MAX_1O_SERVICO, eh_vaca=True,
    )
    base.update(kw)
    return classificar_animal(numero, **base)


class TestPartoDerrubaGestacao:
    """Novilha 18: aparecia como GESTANTE com parto previsto 02/08/2026,
    mas PARIU em 26/07/2026. O parto tem que zerar o ciclo."""

    def test_novilha_18_pariu_nao_e_mais_gestante(self):
        r = _classificar(
            "18",
            partos=[{"data_parto": date(2026, 7, 26)}],
            servicos=[{"data_servico": date(2025, 10, 26), "diagnostico": "POSITIVO"}],
        )
        assert r["estado"] != GESTANTE
        # Pariu há 2 dias → está em descanso pós-parto, não "vazia" solta.
        assert r["estado"] == PEV
        assert r["del_dias"] == 2

    def test_gestante_de_verdade_continua_gestante(self):
        """Contraprova: sem parto posterior, o diagnóstico positivo vale."""
        r = _classificar(
            "77",
            servicos=[{"data_servico": date(2026, 3, 1), "diagnostico": "POSITIVO"}],
        )
        assert r["estado"] == GESTANTE
        assert r["dias_gestacao"] == 149
        assert r["parto_previsto"] == "2026-12-06"


class TestPevExpira:
    """Vaca 431: pariu 08/06/2026; em 28/07/2026 são 50 dias, já passou do
    PEV de 45 — não pode continuar listada em PEV."""

    def test_vaca_431_passou_do_pev(self):
        r = _classificar("431", partos=[{"data_parto": date(2026, 6, 8)}])
        assert r["del_dias"] == 50
        assert r["estado"] != PEV
        assert r["estado"] == APTA

    def test_dentro_do_pev_continua_em_pev(self):
        r = _classificar("432", partos=[{"data_parto": date(2026, 7, 1)}])
        assert r["del_dias"] == 27
        assert r["estado"] == PEV


class TestInseminadaNaoEAtrasada:
    """Novilhas 43 e 09 apareciam em ATRASADAS mesmo estando inseminadas —
    'não tem o que fazer com ela, só esperar o dia de dar toque'."""

    def test_novilha_43_inseminada_em_17_07(self):
        r = _classificar(
            "43", eh_vaca=False,
            servicos=[{"data_servico": date(2026, 7, 17)}],
        )
        assert r["estado"] == INSEMINADA
        assert r["estado"] != ATRASADA
        assert r["dias_desde_servico"] == 11

    def test_novilha_09_inseminada(self):
        r = _classificar(
            "09", eh_vaca=False,
            servicos=[{"data_servico": date(2026, 7, 10)}],
        )
        assert r["estado"] == INSEMINADA

    def test_vaca_vazia_muito_atrasada_continua_atrasada(self):
        """Contraprova: sem serviço e passando do DEL máximo, é atrasada."""
        r = _classificar("500", partos=[{"data_parto": date(2026, 1, 10)}])
        assert r["del_dias"] == 199
        assert r["estado"] == ATRASADA


class TestProtocoloExcluiApta:
    """Vaca 068 aparecia em APTAS estando em protocolo de IATF — quem está
    em protocolo já está sendo trabalhada, não é candidata a novo serviço."""

    def test_vaca_068_em_protocolo_nao_e_apta(self):
        aplicacoes = [
            {"lancamento_id": 1, "dia": 0, "data_prevista": date(2026, 7, 22)},
            {"lancamento_id": 1, "dia": 7, "data_prevista": date(2026, 7, 29)},
            {"lancamento_id": 1, "dia": 9, "data_prevista": date(2026, 7, 31)},
            {"lancamento_id": 1, "dia": 11, "data_prevista": date(2026, 8, 2)},
        ]
        r = _classificar(
            "068", partos=[{"data_parto": date(2026, 4, 1)}], aplicacoes_iatf=aplicacoes,
        )
        assert r["estado"] == EM_PROTOCOLO
        assert r["estado"] != APTA
        assert r["protocolo_d0"] == "2026-07-22"
        assert r["protocolo_dia_atual"] == 6

    def test_protocolo_encerrado_volta_a_ser_apta(self):
        """Protocolo de maio já fechou (D0+11 < hoje) e o parto de 01/06 deixa
        a vaca com DEL 57 — fora do PEV (45) e dentro do DEL máximo (90),
        logo APTA de novo, não mais EM_PROTOCOLO."""
        aplicacoes = [{"lancamento_id": 9, "dia": 0, "data_prevista": date(2026, 5, 1)}]
        r = _classificar(
            "069", partos=[{"data_parto": date(2026, 6, 1)}], aplicacoes_iatf=aplicacoes,
        )
        assert r["estado"] != EM_PROTOCOLO
        assert r["estado"] == APTA

    def test_inseminada_no_protocolo_vira_inseminada(self):
        """Ao chegar no D11 e inseminar, sai de EM_PROTOCOLO para INSEMINADA."""
        aplicacoes = [{"lancamento_id": 2, "dia": 0, "data_prevista": date(2026, 7, 20)}]
        r = _classificar(
            "070",
            partos=[{"data_parto": date(2026, 4, 1)}],
            aplicacoes_iatf=aplicacoes,
            servicos=[{"data_servico": date(2026, 7, 27)}],
        )
        assert r["estado"] == INSEMINADA


class TestNovilhaAptidao:
    """Aptidão da novilha nulípara: idade E peso, conforme parâmetros."""

    def test_novilha_sem_idade_nem_peso_nao_e_apta(self):
        r = _classificar(
            "300", eh_vaca=False, idade_dias=300, peso_kg=250,
            idade_apta_dias=420, peso_apta_kg=350,
        )
        assert r["estado"] == NAO_APTA

    def test_novilha_com_idade_e_peso_e_apta(self):
        r = _classificar(
            "301", eh_vaca=False, idade_dias=450, peso_kg=380,
            idade_apta_dias=420, peso_apta_kg=350,
        )
        assert r["estado"] == APTA

    def test_novilha_com_idade_mas_sem_peso_nao_e_apta(self):
        r = _classificar(
            "302", eh_vaca=False, idade_dias=450, peso_kg=300,
            idade_apta_dias=420, peso_apta_kg=350,
        )
        assert r["estado"] == NAO_APTA


class TestDiagnosticoNegativoLiberaAnimal:
    def test_negativo_sem_novo_servico_volta_a_apta(self):
        r = _classificar(
            "601",
            partos=[{"data_parto": date(2026, 3, 1)}],
            servicos=[{"data_servico": date(2026, 5, 1), "diagnostico": "NEGATIVO"}],
        )
        assert r["estado"] in (APTA, ATRASADA)
        assert r["estado"] != INSEMINADA

    def test_perda_de_prenhez_nao_conta_como_gestante(self):
        r = _classificar(
            "602",
            partos=[{"data_parto": date(2026, 1, 5)}],
            servicos=[{
                "data_servico": date(2026, 3, 1), "diagnostico": "POSITIVO",
                "data_perda_prenhez": date(2026, 6, 1),
            }],
        )
        assert r["estado"] != GESTANTE


class TestDescreverServico:
    def test_iatf(self):
        assert "IATF" in descrever_servico({"tipo_servico": "IA", "protocolo": "IATF 9 dias"})

    def test_cio_natural(self):
        assert descrever_servico({"tipo_servico": "IA", "protocolo": None}) == "IA — cio natural"

    def test_monta_natural(self):
        assert descrever_servico({"tipo_servico": "Monta natural"}) == "Monta natural"


# ---------------------------------------------------------------------------
# Integração: GET /indicadores/estados-reprodutivos
# ---------------------------------------------------------------------------
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

import fazenda.database as database  # noqa: E402
from fazenda.models import Animal, Parto, ProtocoloIatfAplicacao, Servico  # noqa: E402


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


class TestEndpointEstadosReprodutivos:
    def test_reproduz_os_casos_reais_da_fazenda(self, client):
        """Os 4 animais que o produtor reportou classificados errado, num só
        cenário — com `sit_rep` gravado com o valor ERRADO de propósito, para
        provar que o endpoint ignora o texto do CSV."""
        c, engine = client
        with Session(engine) as s:
            # 18: sit_rep diz "Ges.", mas pariu 26/07 → tem que virar PEV.
            s.add(Animal(numero="18", sexo="F", ativo=True, sit_rep="Ges."))
            s.add(Parto(numero_matriz="18", data_parto=date(2026, 7, 26)))
            s.add(Servico(numero_matriz="18", data_servico=date(2025, 10, 26), diagnostico="POSITIVO"))
            # 431: sit_rep diz "Vaz. pev", mas pariu 08/06 (DEL 50 > PEV 45).
            s.add(Animal(numero="431", sexo="F", ativo=True, sit_rep="Vaz. pev"))
            s.add(Parto(numero_matriz="431", data_parto=date(2026, 6, 8)))
            # 43: sit_rep diz "Vaz. atr.", mas foi inseminada 17/07.
            s.add(Animal(numero="43", sexo="F", ativo=True, sit_rep="Vaz. atr."))
            s.add(Servico(numero_matriz="43", data_servico=date(2026, 7, 17)))
            # 068: sit_rep diz "Vaz. apt.", mas está em protocolo IATF.
            s.add(Animal(numero="068", sexo="F", ativo=True, sit_rep="Vaz. apt."))
            s.add(Parto(numero_matriz="068", data_parto=date(2026, 4, 1)))
            s.add(ProtocoloIatfAplicacao(
                lancamento_id=1, numero_matriz="068", dia=0,
                descricao="Implante", data_prevista=date(2026, 7, 22),
            ))
            s.commit()

        r = c.get("/indicadores/estados-reprodutivos", params={"data": "2026-07-28"})
        assert r.status_code == 200, r.text
        por_numero = {a["numero"]: a for a in r.json()["animais"]}

        assert por_numero["18"]["estado"] == PEV           # não mais gestante
        assert por_numero["431"]["estado"] != PEV          # PEV já venceu
        assert por_numero["43"]["estado"] == INSEMINADA    # não atrasada
        assert por_numero["068"]["estado"] == EM_PROTOCOLO  # não apta

    def test_ficha_conta_protocolo_iatf_como_um(self, client):
        """Um protocolo (D0/D7/D9/D11) tem que aparecer como 1 IATF na ficha,
        não como 4 — era o que inflava o histórico reprodutivo do animal."""
        from fazenda.models import ProtocoloIatfLancamento
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="777", sexo="F", ativo=True))
            s.add(ProtocoloIatfLancamento(
                id=5, nome_protocolo="IATF 11 dias", responsavel="Dr. Ana", data_d0=date(2026, 7, 1),
            ))
            for dia, desc in ((0, "Implante"), (7, "Retirada"), (9, "Estradiol"), (11, "Inseminação (IATF)")):
                s.add(ProtocoloIatfAplicacao(
                    lancamento_id=5, numero_matriz="777", dia=dia, descricao=desc,
                    data_prevista=date(2026, 7, 1 + dia), realizada=True,
                ))
            s.commit()

        r = c.get("/animais/777/ficha")
        assert r.status_code == 200, r.text
        protocolos = r.json()["protocolos_iatf"]
        assert len(protocolos) == 1
        assert protocolos[0]["nome_protocolo"] == "IATF 11 dias"
        assert protocolos[0]["etapas_total"] == 4
        assert protocolos[0]["concluido"] is True
        assert protocolos[0]["data_d0"] == "2026-07-01"

    def test_capa_e_rebanho_contam_a_mesma_coisa(self, client):
        """A Capa (calcular_indicadores) e as listas de Rebanho
        (estados-reprodutivos) tem que ler os MESMOS registros. Antes a Capa
        lia sit_rep congelado e o Rebanho lia os lancamentos, entao as duas
        telas mostravam numeros diferentes para o mesmo rebanho."""
        c, engine = client
        with Session(engine) as s:
            # sit_rep gravado ERRADO de proposito nos dois animais.
            s.add(Animal(numero="900", sexo="F", ativo=True, sit_rep="Ges."))
            s.add(Parto(numero_matriz="900", data_parto=date(2026, 7, 26)))
            s.add(Servico(numero_matriz="900", data_servico=date(2025, 10, 1), diagnostico="POSITIVO"))
            s.add(Animal(numero="901", sexo="F", ativo=True, sit_rep="Vaz. atr."))
            s.add(Servico(numero_matriz="901", data_servico=date(2026, 7, 20)))
            s.commit()

        estados = c.get("/indicadores/estados-reprodutivos", params={"data": "2026-07-28"}).json()
        indicadores = c.get("/indicadores/", params={"data": "2026-07-28"}).json()

        # 900 pariu (nao e gestante); 901 foi inseminada (nao esta atrasada).
        por_numero = {a["numero"]: a["estado"] for a in estados["animais"]}
        assert por_numero["900"] == PEV
        assert por_numero["901"] == INSEMINADA

        rep = indicadores["reproducao"]
        assert rep["prenhes"] == 0, "Capa ainda conta a vaca que ja pariu como prenhe"
        assert rep["inseminadas"] == 1, "Capa nao viu a inseminacao lancada"

    def test_ordena_por_numero_do_brinco_crescente(self, client):
        """Toda listagem abre em ordem crescente de brinco (pedido do produtor)."""
        c, engine = client
        with Session(engine) as s:
            for numero in ("100", "9", "23", "007"):
                s.add(Animal(numero=numero, sexo="F", ativo=True))
            s.commit()

        r = c.get("/indicadores/estados-reprodutivos")
        assert r.status_code == 200, r.text
        numeros = [a["numero"] for a in r.json()["animais"]]
        assert numeros == ["007", "9", "23", "100"]


class TestRecriaSituacaoAoVivo:
    """recria._contexto_categoria classificava a situação reprodutiva pelo
    texto congelado de sit_rep; agora deriva dos lançamentos, igual ao resto
    do sistema (senão a categoria de manejo do animal ficava presa ao último
    upload de CSV)."""

    def test_parto_derruba_prenha_mesmo_com_sit_rep_gestante(self):
        from fazenda.api.routers.recria import _contexto_categoria
        from fazenda.models import Parto as P, Servico as S
        # Parto há 60 dias (> pev_dias padrão de 45): já saiu do PEV e está
        # livre para novo serviço — "vazia" de verdade, não só "não mais
        # prenha". Um parto de 2 dias atrás (valor antigo deste teste) cai em
        # PEV — descanso pós-parto obrigatório, um estado real e distinto de
        # "vazia" (ver estado_reprodutivo.py) — o que já provaria "não é mais
        # prenha", mas não provaria "vazia" especificamente.
        ctx = _contexto_categoria(
            dias=1200, peso=500, sit_rep="Ges.", hoje=HOJE,
            servicos=[S(numero_matriz="1", data_servico=date(2025, 10, 1), diagnostico="POSITIVO")],
            partos=[P(numero_matriz="1", data_parto=HOJE - timedelta(days=60))],
            secagens=[],
        )
        assert ctx["situacao_reprodutiva_viva"] == "vazia"

    def test_servico_recente_vira_inseminada(self):
        from fazenda.api.routers.recria import _contexto_categoria
        from fazenda.models import Servico as S
        ctx = _contexto_categoria(
            dias=600, peso=380, sit_rep="Vaz. atr.", hoje=HOJE,
            servicos=[S(numero_matriz="2", data_servico=date(2026, 7, 17))],
            partos=[], secagens=[],
        )
        assert ctx["situacao_reprodutiva_viva"] == "inseminada"

    def test_sem_lancamento_nenhum_cai_no_sit_rep(self):
        from fazenda.api.routers.recria import _contexto_categoria
        ctx = _contexto_categoria(
            dias=300, peso=250, sit_rep="Ges.", hoje=HOJE,
            servicos=[], partos=[], secagens=[],
        )
        assert ctx["situacao_reprodutiva_viva"] is None


class TestAptidaoDeNovilhaSemPesagem:
    """A regra 7 exigia idade E peso para a novilha nulípara ser APTA. Como
    `peso_kg` só vem de PesagemCorporal e NENHUM importador escreve essa
    tabela, a fazenda que não pesa tinha toda novilha em NAO_APTA todos os
    dias — fora do BR ELIG de todo ciclo, com as três taxas do painel voltando
    None.

    Nesta fazenda (GERAL.csv na raiz) isso apagava a maior parte do rebanho da
    medição: 74 novilhas contra 37 vacas, com 59 prenhezes de novilha
    invisíveis ao painel. E, como "Todas" é derivado somando vaca + novilha,
    somar zero fazia "Todas" virar cópia exata de "Vacas" — passando por
    número do rebanho inteiro.

    A regra agora distingue peso AUSENTE (não afirma nada, a idade decide) de
    peso LANÇADO abaixo do mínimo (o dado existe e diz que ela não está
    pronta).
    """

    def _novilha(self, *, idade_dias, peso_kg=None):
        return _classificar(
            "N1", eh_vaca=False, idade_dias=idade_dias, peso_kg=peso_kg,
            idade_apta_dias=457, peso_apta_kg=300.0,
        )

    def test_sem_pesagem_a_idade_decide(self):
        r = self._novilha(idade_dias=600)
        assert r["estado"] == APTA
        assert r["aptidao_por_idade"] is True, "a tela precisa poder avisar que foi só por idade"

    def test_sem_pesagem_e_nova_demais_continua_nao_apta(self):
        assert self._novilha(idade_dias=200)["estado"] == NAO_APTA

    def test_peso_lancado_abaixo_do_minimo_ainda_desqualifica(self):
        """Quem PESA continua com o critério completo — este é o ponto que
        separa 'dado ausente' de 'dado que diz não'."""
        r = self._novilha(idade_dias=600, peso_kg=250.0)
        assert r["estado"] == NAO_APTA

    def test_idade_e_peso_ok_nao_marca_aptidao_por_idade(self):
        r = self._novilha(idade_dias=600, peso_kg=320.0)
        assert r["estado"] == APTA
        assert r["aptidao_por_idade"] is False

    def test_sem_idade_e_sem_peso_nao_ha_o_que_afirmar(self):
        r = _classificar("N9", eh_vaca=False, idade_dias=None, peso_kg=None,
                         idade_apta_dias=457, peso_apta_kg=300.0)
        assert r["estado"] == NAO_APTA

    def test_sem_data_de_nascimento_o_peso_sozinho_nao_basta(self):
        """A assimetria é deliberada: peso ausente é perdoado, data de
        nascimento ausente não.

        O motivo é a origem do dado. `data_nasc` vem em toda importação do
        GERAL.csv, então a ausência dela é excepcional e merece desconfiança.
        `peso_kg` não vem de importação nenhuma — só de lançamento manual de
        pesagem —, então a ausência dele é o caso NORMAL, e tratá-la como
        reprovação apagava o rebanho da medição.

        (Este comportamento já era o de antes da mudança: com
        `idade_apta_dias` configurado e `idade_dias` None, `atingiu_idade` era
        falso e o animal caía em NAO_APTA.)"""
        r = _classificar("N8", eh_vaca=False, idade_dias=None, peso_kg=320.0,
                         idade_apta_dias=457, peso_apta_kg=300.0)
        assert r["estado"] == NAO_APTA


class TestEhVacaVemDoParto:
    """`montar_perfil` aceitava o TEXTO da categoria ("vaca" em
    categoria_abrev/completa) como prova de que o animal era vaca, enquanto os
    cards usavam só o registro de Parto. Além de separar os dois painéis em
    grupos diferentes, o texto sozinho abria um buraco pior: sem parto,
    `del_dias` é None, o teste de ATRASADA não dispara, e o animal volta APTA
    todo dia — entrando no BR ELIG de vacas indefinidamente."""

    def test_categoria_dizendo_vaca_nao_faz_vaca_sem_parto(self):
        from fazenda.rules.programa_reprodutivo import montar_perfil
        perfil = montar_perfil(
            {"numero": "V1", "categoria_completa": "Vaca em lactação",
             "data_nasc": HOJE - timedelta(days=1600)},
            partos=[], servicos=[], aplicacoes_iatf=[],
        )
        assert perfil.eh_vaca is False
        assert perfil.categoria == "novilha"

    def test_com_parto_e_vaca(self):
        from fazenda.rules.programa_reprodutivo import montar_perfil
        perfil = montar_perfil(
            {"numero": "V2", "categoria_completa": "Indefinido"},
            partos=[{"data_parto": HOJE - timedelta(days=100)}],
            servicos=[], aplicacoes_iatf=[],
        )
        assert perfil.eh_vaca is True
        assert perfil.categoria == "vaca"

    def test_vaca_sem_parto_nao_fica_apta_para_sempre(self):
        """O buraco antigo: `eh_vaca=True` sem parto deixava del_dias None, o
        ramo de ATRASADA não disparava e o animal caía em APTA todo dia. Com
        `eh_vaca` derivado do parto, ela é avaliada como nulípara — e uma
        bezerra nova continua NAO_APTA."""
        r = _classificar("V3", eh_vaca=False, idade_dias=120, peso_kg=None,
                         idade_apta_dias=457, peso_apta_kg=300.0)
        assert r["estado"] == NAO_APTA


class TestNovilhaEmAtraso:
    """ATRASADA era sintaticamente inalcançável para quem nunca pariu: o único
    `return ATRASADA` está dentro do ramo `eh_vaca or ultimo_parto is not
    None`, e a definição no docstring do módulo era inteiramente DEL-based —
    DEL só existe com parto.

    Isso fazia o sistema PERDER uma informação que o GERAL.csv do Ideagri já
    entregava. Nesta fazenda, de recria pesada (74 novilhas contra 37 vacas),
    o CSV classifica 11 como "Novilha vazia em atraso" e — o detalhe que
    calibra o teto — **nenhuma** como "Novilha vazia apta". Lá o teto de
    atraso coincide com o piso de aptidão, nos 16 meses.

    As idades abaixo são as reais, calculadas das datas de nascimento do CSV
    (a coluna "Idade em meses" do arquivo foi computada na data da exportação,
    então não serve para conferir contra hoje).
    """

    APTA_DIAS = 457      # 15 meses — piso de aptidão
    ATRASO_DIAS = 487    # 16 meses — teto para a 1ª cobertura

    def _novilha(self, idade_dias, servicos=()):
        return _classificar(
            "N", eh_vaca=False, servicos=list(servicos), idade_dias=idade_dias, peso_kg=None,
            idade_apta_dias=self.APTA_DIAS, peso_apta_kg=300.0,
            idade_atraso_dias=self.ATRASO_DIAS,
        )["estado"]

    def test_as_onze_do_csv_saem_todas_como_atrasadas(self):
        """As 11 "Novilha vazia em atraso" reais, em dias de idade."""
        reais = [538, 538, 538, 617, 726, 748, 748, 748, 748, 809, 918]
        assert [self._novilha(d) for d in reais] == [ATRASADA] * 11

    def test_o_teto_nao_atropela_os_estados_anteriores_da_matriz(self):
        """As 4 novilhas INSEMINADAS do CSV têm as MESMAS idades de algumas
        atrasadas (538, 538, 652, 748 dias). O que as separa é o serviço, não a
        idade — se o teto fosse testado antes da matriz, elas virariam
        atrasadas e o painel passaria a acusar atraso em quem acabou de ser
        coberta."""
        recente = [{"data_servico": HOJE - timedelta(days=20)}]
        assert [self._novilha(d, recente) for d in (538, 538, 652, 748)] == [INSEMINADA] * 4

    def test_a_gestante_velha_continua_gestante(self):
        prenha = [{"data_servico": HOJE - timedelta(days=60), "diagnostico": "POSITIVO"}]
        assert self._novilha(918, prenha) == GESTANTE

    def test_a_janela_de_apta_existe_entre_o_piso_e_o_teto(self):
        assert self._novilha(450) == NAO_APTA, "abaixo do piso — impúbere"
        assert self._novilha(457) == APTA, "no piso"
        assert self._novilha(480) == APTA, "dentro da janela"
        assert self._novilha(487) == APTA, "no teto ainda é apta"
        assert self._novilha(488) == ATRASADA, "um dia além do teto"

    def test_sem_o_parametro_o_comportamento_e_o_de_antes(self):
        """Retrocompatibilidade: quem não passa `idade_atraso_dias` (chamador
        legado, teste antigo) continua vendo APTA, como antes da mudança."""
        r = _classificar("N", eh_vaca=False, idade_dias=918, peso_kg=None,
                         idade_apta_dias=self.APTA_DIAS, peso_apta_kg=300.0)
        assert r["estado"] == APTA

    def test_atrasada_por_idade_sem_pesagem_mantem_o_sinal(self):
        """A novilha atrasada classificada sem pesagem continua marcada como
        tal — o aviso da tela ("classificada só por idade") não pode sumir só
        porque ela passou do teto."""
        r = _classificar("N", eh_vaca=False, idade_dias=918, peso_kg=None,
                         idade_apta_dias=self.APTA_DIAS, peso_apta_kg=300.0,
                         idade_atraso_dias=self.ATRASO_DIAS)
        assert r["estado"] == ATRASADA
        assert r["aptidao_por_idade"] is True


class TestNovilhaAtrasadaPorDiasAposAptidao:
    """O segundo gatilho de ATRASADA para novilha, em paralelo ao teto de
    idade (decisão do usuário: os dois valem, o que vier primeiro marca
    ATRASADA). Ele existe porque o teto de idade sozinho só pega quem já
    passou de 16 meses — uma novilha que ficou apta bem ANTES do teto (idade
    dentro da janela apta/não-atrasada) e segue vazia por muito tempo não
    tinha nenhum alarme até esbarrar no teto. Contar a partir da data em que
    ELA ficou apta, como o DEL conta a partir do PARTO da vaca, dá esse
    alarme mais cedo — sem tirar o teto de idade como rede de segurança para
    quem nunca foi pesada."""

    APTA_DIAS = 457    # 15 meses
    ATRASO_DIAS = 487  # 16 meses — teto de idade, continua valendo em paralelo
    DIAS_APOS_APTIDAO = 30
    IDADE_DENTRO_DA_JANELA_APTA = 470  # entre o piso (457) e o teto (487)

    def _novilha(self, idade_dias, data_ficou_apta):
        return _classificar(
            "N", eh_vaca=False, idade_dias=idade_dias, peso_kg=320.0,
            idade_apta_dias=self.APTA_DIAS, peso_apta_kg=300.0,
            idade_atraso_dias=self.ATRASO_DIAS,
            dias_atraso_apos_aptidao=self.DIAS_APOS_APTIDAO,
            data_ficou_apta=data_ficou_apta,
        )

    def test_ficou_apta_ha_muito_tempo_e_segue_vazia_vira_atrasada_antes_do_teto(self):
        """Idade ainda dentro da janela apta (470 &lt; 487, o teto) — sem o novo
        gatilho ela seria só APTA. Como ficou apta há 40 dias (&gt; 30), o novo
        gatilho pega o atraso antes de a idade sozinha chegar no teto."""
        r = self._novilha(self.IDADE_DENTRO_DA_JANELA_APTA, HOJE - timedelta(days=40))
        assert r["estado"] == ATRASADA

    def test_dentro_da_janela_pos_aptidao_ainda_e_apta(self):
        r = self._novilha(self.IDADE_DENTRO_DA_JANELA_APTA, HOJE - timedelta(days=10))
        assert r["estado"] == APTA

    def test_no_limite_exato_ainda_nao_e_atrasada(self):
        r = self._novilha(self.IDADE_DENTRO_DA_JANELA_APTA, HOJE - timedelta(days=self.DIAS_APOS_APTIDAO))
        assert r["estado"] == APTA

    def test_um_dia_alem_do_limite_ja_e_atrasada(self):
        r = self._novilha(self.IDADE_DENTRO_DA_JANELA_APTA, HOJE - timedelta(days=self.DIAS_APOS_APTIDAO + 1))
        assert r["estado"] == ATRASADA

    def test_sem_data_ficou_apta_so_o_teto_de_idade_se_aplica(self):
        """Sem histórico de pesagem que confirme a data (fazenda que não
        pesa), o segundo gatilho não pode disparar — só o teto de idade,
        exatamente o comportamento de antes desta mudança."""
        r = _classificar(
            "N", eh_vaca=False, idade_dias=self.IDADE_DENTRO_DA_JANELA_APTA, peso_kg=None,
            idade_apta_dias=self.APTA_DIAS, peso_apta_kg=300.0,
            idade_atraso_dias=self.ATRASO_DIAS,
            dias_atraso_apos_aptidao=self.DIAS_APOS_APTIDAO,
            data_ficou_apta=None,
        )
        assert r["estado"] == APTA

    def test_o_que_vier_primeiro_idade_pode_vencer(self):
        """Novilha que ficou apta há só 5 dias (dentro da janela de 30), mas
        já passou do teto de idade (488 dias) — o teto de idade dispara
        primeiro, confirmando que os dois gatilhos valem em paralelo."""
        r = self._novilha(488, HOJE - timedelta(days=5))
        assert r["estado"] == ATRASADA


class TestDataEmQueFicouApta:
    """`data_em_que_ficou_apta` — função pura, sem Session, que ancora o novo
    gatilho: o MAIOR entre a data em que completou a idade mínima e a
    primeira pesagem que bateu o peso mínimo."""

    NASC = date(2024, 1, 1)
    IDADE_APTA_DIAS = 457  # 15 meses

    def test_peso_bate_depois_da_idade_vence_a_data_do_peso(self):
        data_idade = self.NASC + timedelta(days=self.IDADE_APTA_DIAS)
        pesagens = [(data_idade + timedelta(days=20), 310.0)]
        r = data_em_que_ficou_apta(
            data_nasc=self.NASC, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=pesagens, peso_apta_kg=300.0,
        )
        assert r == data_idade + timedelta(days=20)

    def test_peso_bate_antes_da_idade_vence_a_data_da_idade(self):
        """Novilha precoce: já pesava 300kg bem antes dos 15 meses — o que
        falta é a idade, não o peso."""
        data_idade = self.NASC + timedelta(days=self.IDADE_APTA_DIAS)
        pesagens = [(self.NASC + timedelta(days=100), 320.0)]
        r = data_em_que_ficou_apta(
            data_nasc=self.NASC, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=pesagens, peso_apta_kg=300.0,
        )
        assert r == data_idade

    def test_usa_a_primeira_pesagem_que_bate_o_minimo_nao_a_ultima(self):
        """O evento é quando ela CRUZOU o mínimo pela primeira vez — pesagens
        posteriores (ainda acima do mínimo) não empurram a data pra frente."""
        pesagens = [
            (date(2025, 6, 1), 305.0),
            (date(2025, 8, 1), 330.0),
            (date(2025, 4, 1), 290.0),  # ainda abaixo — não conta
        ]
        r = data_em_que_ficou_apta(
            data_nasc=self.NASC, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=pesagens, peso_apta_kg=300.0,
        )
        assert r == max(self.NASC + timedelta(days=self.IDADE_APTA_DIAS), date(2025, 6, 1))

    def test_nenhuma_pesagem_bate_o_minimo_devolve_none(self):
        """Nunca confirmou o peso — não afirma nada (mesma disciplina de
        `classificar_animal` para peso ausente): o chamador cai de volta no
        teto de idade como única rede de segurança."""
        pesagens = [(date(2025, 6, 1), 250.0)]
        r = data_em_que_ficou_apta(
            data_nasc=self.NASC, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=pesagens, peso_apta_kg=300.0,
        )
        assert r is None

    def test_sem_pesagem_nenhuma_devolve_none(self):
        r = data_em_que_ficou_apta(
            data_nasc=self.NASC, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=[], peso_apta_kg=300.0,
        )
        assert r is None

    def test_sem_data_nascimento_devolve_none(self):
        r = data_em_que_ficou_apta(
            data_nasc=None, idade_apta_dias=self.IDADE_APTA_DIAS,
            pesagens=[(date(2025, 6, 1), 320.0)], peso_apta_kg=300.0,
        )
        assert r is None
