"""
A produção do painel sai dos CONTROLES LEITEIROS, não de um campo congelado
— e o card "Produção do dia" é O CONTROLE DO DIA, não mais o acumulado do
último controle de CADA animal (esse acumulado virou `ultimo_por_animal`,
ver `TestUltimoPorAnimal` abaixo).

`Animal.ult_cl_kg` tinha um único ponto de escrita em todo o backend: o
parser do GERAL.csv do Ideagri. Quem lançava controle pelo app via este
número congelado na data do último CSV importado, ao lado de um gráfico que
já mostrava os valores novos. Com a importação do Ideagri aposentada,
`ult_cl_kg` nunca mais seria escrito — segue como fallback só POR ANIMAL,
não mais dentro do card do dia (um valor congelado não tem "o dia de hoje").
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.indicadores import calcular_indicadores


def _animal(numero: str, **extra) -> dict:
    base = {"numero": numero, "grupo_primario": "02 - VACAS ALTA", "raca": "Girolando"}
    base.update(extra)
    return base


class TestBugDaChaveDataControle:
    """Regressão: `calcular_indicadores` lia `c.get("data")`, mas o dict de
    verdade que `calcular_indicadores_fazenda` passa em produção
    (`ControleLeiteiro.model_dump()`, ver `models/producao.py::ControleLeiteiro`)
    tem a chave `data_controle`, não `data`. Com a chave errada, `data_c`
    era sempre `None`, a comparação "controle mais recente" nunca disparava,
    e o valor que sobrava por animal era o que a ordem de iteração do SELECT
    deixasse por último — um bug silencioso, sem nenhum teste que o
    denunciasse (os testes montavam dict à mão com `"data"`).

    Corrigido para `c.get("data_controle") or c.get("data")` — nome real do
    campo do modelo, com o apelido antigo aceito só por compatibilidade
    (ver `test_alias_data_legado_ainda_funciona`)."""

    def test_controle_antigo_de_40kg_nao_vence_o_novo_de_20kg(self):
        animais = [_animal("100")]
        controles = [
            {"numero_matriz": "100", "producao_kg": 40.0, "data_controle": date(2026, 7, 1)},
            {"numero_matriz": "100", "producao_kg": 20.0, "data_controle": date(2026, 8, 15)},
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 20.0
        assert ind["producao"]["ultimo_por_animal"]["producao_total_kg"] == 20.0

    def test_alias_data_legado_ainda_funciona(self):
        """Compatibilidade: um chamador que ainda monta o dict com a chave
        antiga `data` (o formato usado pelos testes desta suíte antes desta
        correção) continua funcionando."""
        animais = [_animal("100", ult_cl_kg=10.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 30.0, "data": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["producao_total_dia_kg"] == 30.0


class TestControleDoDia:
    """`data_controle`/`producao_total_dia_kg`/`controle_nums` — decisão do
    dono do produto: o card "Produção do dia" passa a ser O CONTROLE DO DIA
    (o dia do controle leiteiro mais recente com produção > 0), não mais o
    último controle de cada animal em qualquer data. Antes, uma vaca
    controlada em março entrava no mesmo total de uma controlada ontem,
    enquanto o drill-down ao lado listava só o dia mais recente — card e
    lista eram dois números diferentes com o mesmo nome, por construção."""

    def test_pega_o_dia_mais_recente_do_animal(self):
        animais = [_animal("100")]
        controles = [
            {"numero_matriz": "100", "producao_kg": 22.0, "data_controle": date(2026, 8, 1)},
            {"numero_matriz": "100", "producao_kg": 28.0, "data_controle": date(2026, 8, 12)},
            {"numero_matriz": "100", "producao_kg": 25.0, "data_controle": date(2026, 8, 5)},
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["data_controle"] == "2026-08-12"
        assert ind["producao"]["producao_total_dia_kg"] == 28.0
        assert ind["producao"]["controle_nums"] == ["100"]

    def test_sentinela_total_e_a_soma_exata_de_controle_nums(self):
        """O teste mais importante desta etapa: card e drill-down NUNCA podem
        divergir, porque `producao_total_dia_kg` é somado sobre a própria
        lista `controle_nums` — não recalculado numa segunda passagem
        independente que poderia, por um bug futuro, divergir dela."""
        animais = [_animal("100"), _animal("200"), _animal("300")]
        controles = [
            {"numero_matriz": "100", "producao_kg": 30.0, "data_controle": date(2026, 8, 19)},
            {"numero_matriz": "200", "producao_kg": 25.5, "data_controle": date(2026, 8, 19)},
            {"numero_matriz": "300", "producao_kg": 19.3, "data_controle": date(2026, 8, 19)},
            {"numero_matriz": "100", "producao_kg": 99.0, "data_controle": date(2026, 7, 1)},  # dia antigo, fora
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19), controles=controles)
        p = ind["producao"]
        producao_por_numero = {
            c["numero_matriz"]: c["producao_kg"] for c in controles if c["data_controle"] == date(2026, 8, 19)
        }
        assert len(p["controle_nums"]) == p["vacas_no_controle"] == 3
        assert p["producao_total_dia_kg"] == round(sum(producao_por_numero[n] for n in p["controle_nums"]), 1)
        assert p["producao_total_dia_kg"] == round(30.0 + 25.5 + 19.3, 1)

    def test_um_dia_so_ontem_nao_entra_no_total_de_hoje(self):
        animais = [_animal("100"), _animal("200")]
        controles = [
            {"numero_matriz": "100", "producao_kg": 30.0, "data_controle": date(2026, 8, 18)},  # ontem
            {"numero_matriz": "200", "producao_kg": 25.0, "data_controle": date(2026, 8, 19)},  # hoje
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19), controles=controles)
        assert ind["producao"]["data_controle"] == "2026-08-19"
        assert ind["producao"]["producao_total_dia_kg"] == 25.0
        assert ind["producao"]["controle_nums"] == ["200"]

    def test_cobertura_controle_pct(self):
        animais = [
            _animal("100", grupo_primario="01 - LACT"),
            _animal("200", grupo_primario="02 - LACT"),
            _animal("300", grupo_primario="03 - LACT"),
        ]
        controles = [
            {"numero_matriz": "100", "producao_kg": 30.0, "data_controle": date(2026, 8, 19)},
            {"numero_matriz": "200", "producao_kg": 25.0, "data_controle": date(2026, 8, 19)},
        ]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19), controles=controles)
        assert ind["producao"]["vacas_lactacao"] == 3
        assert ind["producao"]["vacas_no_controle"] == 2
        assert ind["producao"]["cobertura_controle_pct"] == 66.7

    def test_sem_controle_nenhum_card_fica_vazio(self):
        animais = [_animal("100", ult_cl_kg=18.0)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19), controles=[])
        p = ind["producao"]
        assert p["data_controle"] is None
        assert p["controle_nums"] == []
        assert p["vacas_no_controle"] == 0
        assert p["producao_total_dia_kg"] == 0.0
        assert p["producao_media_kg"] is None
        # Compat: "vacas_com_producao" no nível de cima == vacas_no_controle
        # (era o total do acumulado antigo; agora é o total do card).
        assert p["vacas_com_producao"] == 0


class TestUltimoPorAnimal:
    """O acumulado antigo (último controle de CADA animal, em qualquer data,
    com fallback para o campo congelado do CSV) não some — vira
    `ultimo_por_animal`, com a origem visível (`de_controle` x
    `congelado`/`congelado_nums`)."""

    def test_usa_o_controle_lancado_quando_existe(self):
        animais = [_animal("100", ult_cl_kg=10.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 30.0, "data_controle": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        up = ind["producao"]["ultimo_por_animal"]
        assert up["producao_total_kg"] == 30.0
        assert up["vacas_com_producao"] == 1
        assert up["de_controle"] == 1
        assert up["congelado"] == 0
        assert up["congelado_nums"] == []

    def test_cai_no_campo_congelado_quando_nao_ha_controle(self):
        animais = [_animal("100", ult_cl_kg=18.0)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=[])
        up = ind["producao"]["ultimo_por_animal"]
        assert up["producao_total_kg"] == 18.0
        assert up["de_controle"] == 0
        assert up["congelado"] == 1
        assert up["congelado_nums"] == ["100"]

    def test_sem_controles_nenhum_mantem_o_comportamento_antigo(self):
        """Chamadas que não passam `controles` (antes desta correção, era o
        caso de `rules.manual_fazenda`/`rules.assistente`) continuam
        funcionando — caem inteiras no acumulado antigo, sem estourar."""
        animais = [_animal("100", ult_cl_kg=18.0), _animal("200", ult_cl_kg=22.0)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13))
        up = ind["producao"]["ultimo_por_animal"]
        assert up["producao_total_kg"] == 40.0
        assert up["congelado"] == 2
        assert up["de_controle"] == 0

    def test_mistura_controle_novo_com_historico_importado(self):
        # 100 já lança pelo app; 200 só tem o valor que veio do CSV antigo.
        animais = [_animal("100", ult_cl_kg=10.0), _animal("200", ult_cl_kg=22.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 30.0, "data_controle": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        up = ind["producao"]["ultimo_por_animal"]
        assert up["producao_total_kg"] == 52.0
        assert up["de_controle"] == 1
        assert up["congelado"] == 1
        assert up["congelado_nums"] == ["200"]

    def test_controle_zerado_nao_conta(self):
        animais = [_animal("100", ult_cl_kg=15.0)]
        controles = [{"numero_matriz": "100", "producao_kg": 0.0, "data_controle": date(2026, 8, 10)}]
        # Produção zero no controle não derruba o animal para zero: cai no
        # fallback, igual a um animal sem controle nenhum.
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        up = ind["producao"]["ultimo_por_animal"]
        assert up["producao_total_kg"] == 15.0
        assert up["congelado"] == 1

    def test_controle_de_animal_que_nao_esta_na_lista_e_ignorado(self):
        animais = [_animal("100", ult_cl_kg=15.0)]
        controles = [{"numero_matriz": "999", "producao_kg": 99.0, "data_controle": date(2026, 8, 10)}]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 13), controles=controles)
        assert ind["producao"]["ultimo_por_animal"]["producao_total_kg"] == 15.0


class TestDelAoVivo:
    """`producao.del_medio` — MUDANÇA DE SEMÂNTICA deliberada (decisão do
    dono do produto): passa a ser a média do DEL AO VIVO das lactantes
    (último parto lançado no app, zerado por uma Secagem posterior), a MESMA
    conta que `GET /animais/` já usa (`rules.producao_leiteira.del_dias_ao_vivo`)
    — não mais o `del_dias` congelado do CSV do Ideagri. Card e lista
    discordavam, e DEL alimenta tanto a dieta quanto a decisão de secagem."""

    def test_usa_o_del_ao_vivo_nao_o_congelado(self):
        hoje = date(2026, 8, 19)
        animais = [_animal("100", del_dias=999)]  # congelado — deve ser ignorado
        partos = [{"numero_matriz": "100", "data_parto": hoje - timedelta(days=30)}]
        ind = calcular_indicadores(animais, [], partos, data_ref=hoje)
        assert ind["producao"]["del_medio"] == 30.0
        assert ind["producao"]["del_medio_animais"] == 1

    def test_secagem_posterior_ao_parto_tira_o_animal_da_media(self):
        hoje = date(2026, 8, 19)
        animais = [_animal("100", del_dias=999), _animal("200", del_dias=999)]
        partos = [
            {"numero_matriz": "100", "data_parto": hoje - timedelta(days=30)},
            {"numero_matriz": "200", "data_parto": hoje - timedelta(days=50)},
        ]
        secagens = [{"numero_matriz": "200", "data_secagem": hoje - timedelta(days=5)}]
        ind = calcular_indicadores(animais, [], partos, data_ref=hoje, secagens=secagens)
        assert ind["producao"]["del_medio"] == 30.0  # só a 100 — a 200 já secou
        assert ind["producao"]["del_medio_animais"] == 1

    def test_sem_parto_algum_cai_no_del_congelado(self):
        """Animal sem parto lançado no app (histórico só no CSV) continua
        usando o `del_dias` congelado — mesmo fallback de sempre."""
        animais = [_animal("100", del_dias=45)]
        ind = calcular_indicadores(animais, [], [], data_ref=date(2026, 8, 19))
        assert ind["producao"]["del_medio"] == 45.0

    def test_sem_secagens_omitido_equivale_a_secagens_vazia(self):
        """`secagens` é o último parâmetro, opcional — a função é chamada por
        caminhos puros que não carregam `Secagem` (era o caso de
        `rules.manual_fazenda`/`rules.assistente` antes desta correção, e
        continua sendo o caso de qualquer chamador futuro que não a
        informe). Omitir o argumento tem que se comportar exatamente como
        passar uma lista vazia — nunca travar nem mudar de resultado."""
        hoje = date(2026, 8, 19)
        animais = [_animal("100", del_dias=999)]
        partos = [{"numero_matriz": "100", "data_parto": hoje - timedelta(days=30)}]
        omitido = calcular_indicadores(animais, [], partos, data_ref=hoje)
        vazio = calcular_indicadores(animais, [], partos, data_ref=hoje, secagens=[])
        assert omitido["producao"]["del_medio"] == vazio["producao"]["del_medio"] == 30.0
        assert omitido["producao"]["del_medio_animais"] == vazio["producao"]["del_medio_animais"] == 1
