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
    classificar_animal, descrever_servico,
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
