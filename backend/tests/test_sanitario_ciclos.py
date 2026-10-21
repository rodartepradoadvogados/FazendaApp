"""
Sanitário v2 — ciclo por tipo de janela (modelo_v1 §12 "Ciclo"), puro.

U (dose única), G:{servico} (pré-parto), IA:{data}, M:AAAA-MM, grupo de meses
(jun/jul = 1 dose), F:AAAA (a cada N anos com ano-base), C (contínuo),
"começar em", e a série D1 -> D2 que continua mesmo mudando de categoria.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.rules.sanitario.ciclos import ciclo_de, ciclos_periodo
from fazenda.rules.sanitario.motor import avaliar
from fazenda.rules.sanitario.tipos import AnimalCtx, CaixaDef, Gestacao, RegistroCtx

HOJE = date(2026, 10, 21)


def _a(**kw) -> AnimalCtx:
    base = dict(id=1, numero="100", hoje=HOJE, sexo="F", nasc=HOJE - timedelta(days=150))
    base.update(kw)
    return AnimalCtx(**base)


def _cx(**kw) -> CaixaDef:
    base = dict(caixa_id=10, versao_id=1, nome="X", nome_curto="X")
    base.update(kw)
    return CaixaDef(**base)


def test_dose_unica_por_idade_chave_U():
    cx = _cx(jan_usa_evento=True, evento_tipo="idade", evento_de_dias=120, evento_ate_dias=240,
             jan_usa_periodo=True, periodo_modo="continuo")
    a = _a()
    c = ciclo_de(cx, a, HOJE)
    assert c.chave == "U"
    assert c.ini == a.nasc + timedelta(days=120) and c.fim == a.nasc + timedelta(days=240)


def test_pre_parto_chave_por_gestacao():
    g = Gestacao(servico_id=77, data_servico=HOJE - timedelta(days=260), parto_previsto=HOJE + timedelta(days=20))
    cx = _cx(jan_usa_evento=True, evento_tipo="pre_parto", evento_de_dias=-30, evento_ate_dias=0)
    c = ciclo_de(cx, _a(gestacoes=(g,)), HOJE)
    assert c.chave == "G:77" and c.aberta
    assert c.ini == g.parto_previsto - timedelta(days=30)


def test_entrada_ia_chave_com_data():
    cx = _cx(jan_usa_evento=True, evento_tipo="entrada_ia", evento_de_dias=0, evento_ate_dias=30)
    c = ciclo_de(cx, _a(entrada_ia=date(2026, 10, 3)), HOJE)
    assert c.chave == "IA:2026-10-03"
    assert ciclo_de(cx, _a(), HOJE) is None  # não entrou em IA: sem ciclo


def test_meses_um_ciclo_por_mes_marcado():
    cx = _cx(jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=((0,), (4,), (8,)))
    chaves = [c.chave for c in ciclos_periodo(cx, date(2027, 1, 1), date(2027, 12, 31)) if c.ini.year == 2027]
    assert chaves == ["M:2027-01", "M:2027-05", "M:2027-09"]


def test_grupo_de_meses_e_uma_dose():
    cx = _cx(jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=((0,), (5, 6), (11,)))
    c = [c for c in ciclos_periodo(cx, date(2026, 1, 1), date(2026, 12, 31)) if c.chave == "M:2026-06..07"][0]
    assert c.ini == date(2026, 6, 1) and c.fim == date(2026, 7, 31)
    # quem recebeu em julho cumpriu o grupo inteiro
    a = _a(nasc=date(2020, 1, 1), registros={10: [RegistroCtx(1, 10, "M:2026-06..07", 1, date(2026, 7, 8))]})
    s = avaliar(cx, a, date(2026, 7, 20))[0]
    assert s.estado == "aplicada"


def test_frequencia_quatro_anos_ano_base_2026():
    cx = _cx(jan_usa_periodo=True, periodo_modo="frequencia", periodo_anos=4, periodo_ano_base=2026,
             periodo_grupos=((6,),))
    anos = [c.chave for c in ciclos_periodo(cx, date(2025, 1, 1), date(2034, 12, 31))]
    assert "F:2026" in anos and "F:2030" in anos and "F:2034" in anos
    assert "F:2027" not in anos and "F:2028" not in anos
    assert ciclo_de(cx, _a(), HOJE).chave == "F:2030"  # julho/2026 já passou


def test_continuo_sem_evento_chave_C():
    assert ciclo_de(_cx(), _a(), HOJE).chave == "C"


def test_comecar_em_pula_ciclos_anteriores():
    cx = _cx(jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=((3,),), comecar_em=date(2027, 1, 1))
    assert ciclo_de(cx, _a(), HOJE).chave == "M:2027-04"
    assert all(c.ini >= date(2027, 1, 1) for c in ciclos_periodo(cx, date(2025, 1, 1), date(2027, 12, 31)))


def test_serie_d2_continua_mesmo_mudando_de_categoria():
    """Reprodutiva D1/D2 só para a categoria "Novilha" (id 4). Depois da D1 a
    novilha muda de categoria (id 9): a D2 continua devida."""
    cx = _cx(pub_sexo="F", categorias=frozenset({4}), jan_usa_evento=True, evento_tipo="entrada_ia",
             evento_de_dias=0, evento_ate_dias=30, serie=({"dose": 2, "apos_dias": 30, "janela_dias": 30},))
    d1 = date(2026, 9, 20)
    a = _a(entrada_ia=date(2026, 9, 20), classificador=lambda d: (9, "Prenha"),
           registros={10: [RegistroCtx(5, 10, "IA:2026-09-20", 1, d1)]})
    lista = avaliar(cx, a, HOJE)
    assert lista[0].estado == "aplicada"
    assert lista[1].dose_num == 2 and lista[1].ciclo.chave == "IA:2026-09-20"
    assert lista[1].estado == "janela"  # 20/10..19/11 contado da D1, ainda que a categoria mudou
    assert avaliar(cx, a, date(2026, 10, 1))[1].estado == "prevista"
