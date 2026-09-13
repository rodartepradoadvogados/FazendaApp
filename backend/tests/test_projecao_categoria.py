"""
Motor de projeção de categoria de manejo para data futura (R-2, Fase 0 do
redesenho do evento sanitário) — unidade pura, sem banco de dados: constrói
o `dados` (mesmo formato de `coletar_dados_criterios`) na mão e chama
`fazenda.rules.projecao_categoria` direto.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.models import CategoriaManejo
from fazenda.rules.projecao_categoria import (
    SEP_CATEGORIAS,
    animais_projetados_na_categoria,
    projetar_categoria_animal,
    projetar_categorias,
)

# Parâmetros do estado ao vivo fixos (não-None) para nunca cair em
# `_parametros_estado_vivo()` (que abre sessão de banco própria) — mesmo
# valor em todos os testes, irrelevante para os casos puramente etários.
_PARAMS_ESTADO_VIVO = dict(
    pev_dias=365, del_max_1o_servico=100, idade_apta_dias=420, peso_apta_kg=350.0,
    idade_atraso_dias=450, dias_atraso_apos_aptidao=60,
)

CATEGORIAS = [
    CategoriaManejo(nome="Bezerra", dia_min=0, dia_max=90, ordem=1),
    CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=2),
    CategoriaManejo(nome="Vaca Adulta", dia_min=731, dia_max=None, ordem=3),
]


def _animal(numero: str, data_nasc: date) -> dict:
    return {"numero": numero, "data_nasc": data_nasc, "sit_rep": None}


def _dados(animais: list[dict]) -> dict:
    return {
        "animais": animais,
        "categorias_ativas": CATEGORIAS,
        "peso_por_animal": {},
        "servicos_obj_por_animal": {},
        "partos_obj_por_animal": {},
        "secagens_obj_por_animal": {},
        "pesagens_por_animal": {},
        **_PARAMS_ESTADO_VIVO,
    }


class TestProjecaoCategoria:
    def test_idade_projetada_avanca_de_categoria(self):
        # Nasceu há 60 dias (hoje) — é Bezerra hoje, mas em +40 dias (100
        # dias de idade) já entra em Novilha. É exatamente o caso do
        # exemplo do usuário: "vacinar >2 anos daqui a 4 meses já sugere
        # quem tem 1 ano e 10 meses hoje".
        hoje = date(2026, 9, 11)
        nasc = hoje - timedelta(days=60)
        dados = _dados([_animal("1", nasc)])

        assert projetar_categoria_animal(dados["animais"][0], hoje, dados) == "Bezerra"
        assert projetar_categoria_animal(dados["animais"][0], hoje + timedelta(days=40), dados) == "Novilha"

    def test_projetar_categorias_para_varios_animais(self):
        hoje = date(2026, 9, 11)
        td = timedelta
        dados = _dados([
            _animal("1", hoje - td(days=30)),   # Bezerra
            _animal("2", hoje - td(days=800)),  # Vaca Adulta
        ])
        resultado = projetar_categorias(dados, hoje)
        assert resultado == {"1": "Bezerra", "2": "Vaca Adulta"}

    def test_animais_projetados_na_categoria_filtra_por_nome(self):
        hoje = date(2026, 9, 11)
        td = timedelta
        dados = _dados([
            _animal("1", hoje - td(days=100)),  # Novilha hoje
            _animal("2", hoje - td(days=800)),  # Vaca Adulta
            _animal("3", hoje - td(days=10)),   # Bezerra
        ])
        assert animais_projetados_na_categoria("Novilha", hoje, dados) == ["1"]

    def test_aceita_mais_de_uma_categoria_alvo_separada_por_virgula(self):
        hoje = date(2026, 9, 11)
        td = timedelta
        dados = _dados([
            _animal("1", hoje - td(days=10)),   # Bezerra
            _animal("2", hoje - td(days=800)),  # Vaca Adulta
        ])
        alvo = SEP_CATEGORIAS.join(["Bezerra", "Vaca Adulta"])
        assert animais_projetados_na_categoria(alvo, hoje, dados) == ["1", "2"]

    def test_sem_categoria_alvo_nao_sugere_ninguem(self):
        hoje = date(2026, 9, 11)
        dados = _dados([_animal("1", hoje)])
        assert animais_projetados_na_categoria("", hoje, dados) == []
        assert animais_projetados_na_categoria(None, hoje, dados) == []

    def test_sem_data_nascimento_nao_classifica(self):
        hoje = date(2026, 9, 11)
        dados = _dados([{"numero": "1", "data_nasc": None, "sit_rep": None}])
        assert projetar_categoria_animal(dados["animais"][0], hoje, dados) == "Sem data de nascimento"
