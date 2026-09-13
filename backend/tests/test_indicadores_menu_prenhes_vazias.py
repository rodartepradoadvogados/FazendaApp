"""
Medição do risco descrito para os cards "Fêmeas prenhas"/"Vazias" do app de
campo (frontend/components/mobile/menu/Indicadores.tsx e
frontend/components/mobile/rebanho/Indicadores.tsx): o VALOR desses cards
vinha de `calcular_indicadores` (GET /indicadores/) e a LISTA do drill-down
vinha de `GET /indicadores/estados-reprodutivos` — dois fetches, dois caches
offline, dois momentos possivelmente diferentes.

Este arquivo prova, com número, o que estava em risco ANTES da correção:

  1. `reproducao.prenhes` (calcular_indicadores) e a contagem de
     `estado == "gestante"` que `GET /indicadores/estados-reprodutivos`
     devolveria SOBRE O MESMO REBANHO, na MESMA hora, são sempre iguais — as
     duas rotas usam a mesma função de classificação (`classificar_animal`)
     com os mesmos parâmetros, sobre a mesma população (fêmeas ativas). Não
     havia bug de REGRA aqui: o risco de "Fêmeas prenhas" era só de TEMPO
     (dois fetches podendo pegar o rebanho em dois instantes diferentes).

  2. `reproducao.vazias` (o catch-all "senão" de calcular_indicadores, que
     inclui quem está `em_protocolo`) e o filtro de 5 estados que o app
     SEMPRE usou no drill-down de "Vazias" (pev/apta/atrasada/nao_apta/vazia,
     sem `em_protocolo`) DIVERGEM sempre que existe pelo menos 1 animal em
     protocolo — não é um risco de tempo, é um bug de regra: o mesmo cálculo,
     na mesma hora, já produzia um card e uma lista contando conjuntos
     diferentes. `reproducao_categorias.todas.vazias`/`.vazias_nums` é o
     campo que já soma exatamente os 5 estados do drill-down (mesmo payload
     de `reproducao_categorias`, ver TestBaldesDrillDown em test_rules.py) —
     é ele que os dois componentes passaram a consumir, valor e lista juntos.

A correção (ver frontend/components/mobile/menu/Indicadores.tsx e
frontend/components/mobile/rebanho/Indicadores.tsx): os dois cards passam a
ler valor E lista de `reproducao_categorias.todas` — nunca mais de dois
campos ou dois fetches diferentes.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

from datetime import date, timedelta

from fazenda.rules.estado_reprodutivo import estados_ao_vivo
from fazenda.rules.indicadores import calcular_indicadores

HOJE = date(2026, 8, 19)
# Mesmos padrões default de `_estados_ao_vivo`/`estados_reprodutivos` quando
# não há ParametroFazenda no banco (ver fazenda.rules.parametros.get_param).
PEV_DIAS = 45
DEL_MAX_1O_SERVICO = 100


def _rebanho_com_animal_em_protocolo():
    """6 fêmeas cobrindo os estados que distinguem os dois campos de "vazias":
    1 gestante, 1 inseminada, 1 apta, 1 EM PROTOCOLO (D0-D11), 1 em PEV,
    1 atrasada."""
    animais = [
        {"numero": "1"},   # gestante
        {"numero": "2"},   # inseminada (serviço recente, sem diagnóstico)
        {"numero": "3"},   # apta (vaca, passou do PEV)
        {"numero": "4"},   # em protocolo IATF D0-D11
        {"numero": "5"},   # PEV (pariu há poucos dias)
        {"numero": "6"},   # atrasada (DEL > DEL_MAX_1O_SERVICO)
    ]
    servicos = [
        {"numero_matriz": "1", "data_servico": HOJE - timedelta(days=60), "diagnostico": "POSITIVO"},
        {"numero_matriz": "2", "data_servico": HOJE - timedelta(days=10)},
    ]
    partos = [
        {"numero_matriz": "1", "data_parto": HOJE - timedelta(days=200)},
        {"numero_matriz": "2", "data_parto": HOJE - timedelta(days=200)},
        {"numero_matriz": "3", "data_parto": HOJE - timedelta(days=100)},
        {"numero_matriz": "4", "data_parto": HOJE - timedelta(days=100)},
        {"numero_matriz": "5", "data_parto": HOJE - timedelta(days=20)},
        {"numero_matriz": "6", "data_parto": HOJE - timedelta(days=150)},
    ]
    aplicacoes_iatf = [
        {"lancamento_id": 1, "numero_matriz": "4", "dia": 0, "data_prevista": HOJE - timedelta(days=3)},
    ]
    return animais, servicos, partos, aplicacoes_iatf


class TestMedicaoDivergenciaPrenhesVazias:
    """Passo 1 do trabalho: mede antes de mexer. Ver docstring do módulo."""

    def _calcular(self):
        animais, servicos, partos, aplicacoes_iatf = _rebanho_com_animal_em_protocolo()
        r = calcular_indicadores(animais, servicos, partos, data_ref=HOJE, aplicacoes_iatf=aplicacoes_iatf)
        return animais, servicos, partos, aplicacoes_iatf, r

    def _estados_do_endpoint_estados_reprodutivos(self, animais, servicos, partos, aplicacoes_iatf):
        """O que `GET /indicadores/estados-reprodutivos` calcularia para o
        MESMO rebanho, na MESMA hora — via `estados_ao_vivo` (mesma função de
        lote que o router usa, ver fazenda/api/routers/indicadores.py)."""
        return estados_ao_vivo(
            animais, hoje=HOJE, partos=partos, servicos=servicos, aplicacoes_iatf=aplicacoes_iatf,
            pev_dias=PEV_DIAS, del_max_1o_servico=DEL_MAX_1O_SERVICO,
        )

    def test_prenhes_nao_diverge_quando_calculado_na_mesma_hora(self):
        """`reproducao.prenhes` (calcular_indicadores) e o que
        estados-reprodutivos devolveria sobre o MESMO rebanho batem sempre —
        as duas rotas usam a mesma `classificar_animal`, mesmos parâmetros,
        mesma população. O card "Fêmeas prenhas" nunca teve um bug de REGRA;
        só o risco de dois fetches pegarem o rebanho em instantes diferentes."""
        animais, servicos, partos, aplicacoes_iatf, r = self._calcular()
        estados = self._estados_do_endpoint_estados_reprodutivos(animais, servicos, partos, aplicacoes_iatf)
        n_gestante_endpoint = sum(1 for e in estados.values() if e["estado"] == "gestante")

        assert r["reproducao"]["prenhes"] == 1
        assert n_gestante_endpoint == 1
        assert r["reproducao"]["prenhes"] == n_gestante_endpoint
        # E o campo que o app passou a consumir (valor + lista) concorda:
        cat = r["reproducao_categorias"]["todas"]
        assert cat["prenhes"] == r["reproducao"]["prenhes"]
        assert len(cat["prenhes_nums"]) == cat["prenhes"]
        assert set(cat["prenhes_nums"]) == {n for n, e in estados.items() if e["estado"] == "gestante"}

    def test_vazias_catch_all_diverge_do_filtro_de_5_estados_do_app(self):
        """MEDIÇÃO CENTRAL deste trabalho: `reproducao.vazias` (o valor que o
        card "Vazias" mostrava) conta 4 (inclui o animal em protocolo, "4");
        o filtro de 5 estados que o próprio app sempre usou no drill-down
        (pev/apta/atrasada/nao_apta/vazia) só teria 3. Isso não é um efeito
        de dois fetches em momentos diferentes — é o MESMO cálculo, no MESMO
        instante, produzindo um card e uma lista que não fecham."""
        animais, servicos, partos, aplicacoes_iatf, r = self._calcular()
        estados = self._estados_do_endpoint_estados_reprodutivos(animais, servicos, partos, aplicacoes_iatf)
        estados_vazia_5 = {"pev", "apta", "atrasada", "nao_apta", "vazia"}
        n_vazia_5_endpoint = sum(1 for e in estados.values() if e["estado"] in estados_vazia_5)

        assert r["reproducao"]["vazias"] == 4          # catch-all: inclui "4" (em_protocolo)
        assert n_vazia_5_endpoint == 3                 # 5 estados: "3", "5", "6" (sem "4")
        assert r["reproducao"]["vazias"] != n_vazia_5_endpoint, (
            "se este assert falhar, o catch-all deixou de divergir do filtro de 5 "
            "estados — reavalie se a correção do frontend ainda faz sentido"
        )

        # `reproducao_categorias.todas.vazias`/`.vazias_nums` é o campo certo:
        # bate exatamente com o filtro de 5 estados, valor E lista juntos.
        cat = r["reproducao_categorias"]["todas"]
        assert cat["vazias"] == n_vazia_5_endpoint == 3
        assert len(cat["vazias_nums"]) == cat["vazias"]
        assert set(cat["vazias_nums"]) == {n for n, e in estados.items() if e["estado"] in estados_vazia_5}
        assert "4" not in cat["vazias_nums"]            # o animal em protocolo NÃO é "vazia"


class TestContadorEListaVemDoMesmoObjeto:
    """Sentinela permanente (Passo 3): trava o par (valor, lista) que os dois
    componentes mobile passaram a consumir — `reproducao_categorias.todas.
    {prenhes,vazias}` e seus `_nums` — para nenhuma alteração futura em
    `calcular_indicadores` fazer o contador e a lista voltarem a divergir."""

    def _calcular(self):
        animais, servicos, partos, aplicacoes_iatf = _rebanho_com_animal_em_protocolo()
        return calcular_indicadores(animais, servicos, partos, data_ref=HOJE, aplicacoes_iatf=aplicacoes_iatf)

    def test_prenhes_e_vazias_contagem_bate_com_o_tamanho_da_propria_lista(self):
        cat = self._calcular()["reproducao_categorias"]["todas"]
        assert cat["prenhes"] == len(cat["prenhes_nums"])
        assert cat["vazias"] == len(cat["vazias_nums"])

    def test_rebanho_maior_continua_sem_divergir(self):
        """Contraprova com um rebanho sem nenhum animal em protocolo — os dois
        campos (catch-all e 5-estados) devem coincidir aqui, só para deixar
        claro que a divergência do teste acima é especificamente sobre
        `em_protocolo`, não um efeito colateral de outra coisa."""
        animais = [{"numero": "1"}, {"numero": "2"}, {"numero": "3"}]
        servicos = [
            {"numero_matriz": "1", "data_servico": HOJE - timedelta(days=60), "diagnostico": "POSITIVO"},
        ]
        partos = [
            {"numero_matriz": n, "data_parto": HOJE - timedelta(days=200)} for n in ("1", "2", "3")
        ]
        r = calcular_indicadores(animais, servicos, partos, data_ref=HOJE)
        cat = r["reproducao_categorias"]["todas"]
        assert r["reproducao"]["vazias"] == cat["vazias"]
        assert cat["prenhes"] == r["reproducao"]["prenhes"] == 1
