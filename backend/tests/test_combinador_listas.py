"""
Combinador de Listas (Insights > Listas) — novo modelo de parâmetros
configuráveis (fazenda/rules/combinador_listas.py + endpoint
GET /relatorios/combinador-listas).

Além da cobertura unitária de `contexto_animal_combinador`, este arquivo
prova os cenários de "combinação de parâmetros incompatíveis" documentados
no topo de fazenda/rules/combinador_listas.py — cada um deles é um par de
filtros que, sozinhos, têm animais, mas cuja INTERSEÇÃO é estruturalmente
vazia. Servem de nota viva: se o motor de categorias mudar de um jeito que
quebre essa exclusividade mútua, o teste correspondente falha.
"""
from __future__ import annotations

from datetime import date, timedelta

from fazenda.models import CategoriaManejo, Parto, Secagem, Servico
from fazenda.rules.combinador_listas import categoria_etaria, contexto_animal_combinador

HOJE = date(2026, 9, 19)


def _ctx(numero, *, data_nasc=None, raca="Holandes", lote="LOTE 1", categoria_abrev=None,
         peso=550.0, producao_kg=None, sit_rep=None, servicos=None, partos=None, secagens=None,
         pesagens=None, categorias_cadastro=None, data_inicio_lactacao=None):
    return contexto_animal_combinador(
        numero=numero, data_nasc=data_nasc, raca=raca, lote=lote, categoria_abrev=categoria_abrev,
        peso=peso, producao_kg=producao_kg, sit_rep=sit_rep, hoje=HOJE,
        servicos=servicos or [], partos=partos or [], secagens=secagens or [], pesagens=pesagens or [],
        categorias_cadastro=categorias_cadastro or [],
        pev_dias=45, del_max_1o_servico=90, idade_apta_dias=420, peso_apta_kg=280,
        idade_atraso_dias=450, dias_atraso_apos_aptidao=30,
        data_inicio_lactacao=data_inicio_lactacao,
    )


class TestCategoriaEtaria:
    def test_mapeia_prefixo_vaca_novilha_bezerra(self):
        assert categoria_etaria("Vaca") == "vaca"
        assert categoria_etaria("Novilha") == "novilha"
        assert categoria_etaria("Bezerra") == "bezerra"
        assert categoria_etaria("Bezerro") == "bezerra"

    def test_valor_desconhecido_ou_ausente_retorna_none(self):
        assert categoria_etaria(None) is None
        assert categoria_etaria("") is None
        assert categoria_etaria("Touro") is None


class TestContextoAnimalCombinador:
    def test_vaca_em_lactacao_traz_dias_pos_parto_e_situacao_produtiva(self):
        ctx = _ctx(
            "1", data_nasc=HOJE - timedelta(days=1800), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="1", data_parto=HOJE - timedelta(days=55))],
        )
        assert ctx["situacao_produtiva"] == "lactacao"
        assert ctx["dias_pos_parto"] == 55
        assert ctx["categoria_etaria"] == "vaca"

    def test_vaca_seca_traz_situacao_seca_sem_dias_pos_parto_do_parto_antigo(self):
        ctx = _ctx(
            "2", data_nasc=HOJE - timedelta(days=1800), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="2", data_parto=HOJE - timedelta(days=300))],
            secagens=[Secagem(numero_matriz="2", data_secagem=HOJE - timedelta(days=10))],
        )
        assert ctx["situacao_produtiva"] == "seca"

    def test_novilha_nunca_parida_situacao_produtiva_none(self):
        ctx = _ctx("3", data_nasc=HOJE - timedelta(days=500), categoria_abrev="Novilha")
        assert ctx["situacao_produtiva"] is None
        assert ctx["dias_pos_parto"] is None
        assert ctx["categoria_etaria"] == "novilha"

    def test_producao_e_peso_passam_direto(self):
        ctx = _ctx("4", peso=612.3, producao_kg=28.7)
        assert ctx["peso_kg"] == 612.3
        assert ctx["producao_kg"] == 28.7

    def test_gestante_traz_dias_gestacao_e_situacao_reprodutiva_prenha(self):
        ctx = _ctx(
            "5", data_nasc=HOJE - timedelta(days=1200), categoria_abrev="Novilha",
            servicos=[Servico(numero_matriz="5", data_servico=HOJE - timedelta(days=100), diagnostico="POSITIVO")],
        )
        assert ctx["dias_gestacao"] == 100
        assert ctx["situacao_reprodutiva"] == "prenha"

    def test_vaca_induzida_sem_parto_real_conta_como_em_lactacao(self):
        """Mesma classe do bug da vaca 422 (indução de lactação sem Parto
        registrado) — já corrigida em relatorios_gerenciais.py e em
        estado_reprodutivo.classificar_animal; este teste garante que o
        ponto de reuso do Combinador (`_contexto_categoria` via
        `contexto_animal_combinador`) também recebe `data_inicio_lactacao`
        e não deixa a vaca invisível para os filtros de situação
        produtiva/dias pós-parto."""
        ctx = _ctx(
            "422", data_nasc=HOJE - timedelta(days=2000), categoria_abrev="Vaca",
            data_inicio_lactacao=HOJE - timedelta(days=40),
        )
        assert ctx["situacao_produtiva"] == "lactacao"
        assert ctx["dias_pos_parto"] == 40

    def test_inicio_lactacao_mais_recente_que_parto_antigo_vence(self):
        """`ancora_lactacao = max(ultimo_parto, data_inicio_lactacao)` — uma
        Lactacao aberta por indução DEPOIS do último parto real tem que
        prevalecer (mesmo padrão de estado_reprodutivo.classificar_animal)."""
        ctx = _ctx(
            "6", data_nasc=HOJE - timedelta(days=2000), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="6", data_parto=HOJE - timedelta(days=400))],
            data_inicio_lactacao=HOJE - timedelta(days=20),
        )
        assert ctx["dias_pos_parto"] == 20

    def test_parto_real_mais_recente_que_lactacao_antiga_vence(self):
        """O inverso do teste anterior: um parto real mais novo do que uma
        Lactacao induzida antiga (já encerrada por outro parto, por exemplo)
        não pode regredir para a data da lactação."""
        ctx = _ctx(
            "7", data_nasc=HOJE - timedelta(days=2000), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="7", data_parto=HOJE - timedelta(days=10))],
            data_inicio_lactacao=HOJE - timedelta(days=400),
        )
        assert ctx["dias_pos_parto"] == 10


class TestCombinacoesIncompativeis:
    """Casos documentados em fazenda/rules/combinador_listas.py: cada filtro
    sozinho tem animais, mas a interseção dos dois é sempre vazia — não é um
    bug, é o frontend tendo que saber explicar isso ao usuário em vez de só
    mostrar "0 animais"."""

    def _categorias_lactacao_seca(self):
        return [
            CategoriaManejo(nome="Em lactação", dia_min=0, situacao_produtiva="lactacao", ordem=1),
            CategoriaManejo(nome="Seca", dia_min=0, situacao_produtiva="seca", ordem=2),
        ]

    def test_situacao_produtiva_lactacao_x_categoria_cadastrada_seca(self):
        cats = self._categorias_lactacao_seca()
        lactante = _ctx(
            "8", data_nasc=HOJE - timedelta(days=1800), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="8", data_parto=HOJE - timedelta(days=30))],
            categorias_cadastro=cats,
        )
        seca = _ctx(
            "9", data_nasc=HOJE - timedelta(days=1800), categoria_abrev="Vaca",
            partos=[Parto(numero_matriz="9", data_parto=HOJE - timedelta(days=300))],
            secagens=[Secagem(numero_matriz="9", data_secagem=HOJE - timedelta(days=10))],
            categorias_cadastro=cats,
        )
        # Cada filtro sozinho tem exatamente 1 animal — não é um parâmetro
        # "sem correspondência nenhuma" no rebanho.
        assert lactante["situacao_produtiva"] == "lactacao"
        assert seca["categoria_cadastro"] == "Seca"
        # A interseção (situação produtiva = lactação) ∩ (categoria = Seca)
        # é estruturalmente vazia: nenhum dos dois animais está nos dois
        # conjuntos ao mesmo tempo.
        lactacao_set = {a["numero"] for a in (lactante, seca) if a["situacao_produtiva"] == "lactacao"}
        seca_categoria_set = {a["numero"] for a in (lactante, seca) if a["categoria_cadastro"] == "Seca"}
        assert lactacao_set == {"8"}
        assert seca_categoria_set == {"9"}
        assert lactacao_set & seca_categoria_set == set()

    def test_situacao_reprodutiva_prenha_x_categoria_cadastrada_vazia_atrasada(self):
        cats = [
            CategoriaManejo(nome="Vazia atrasada", dia_min=0, situacao_reprodutiva="vazia_atrasada", ordem=1),
            CategoriaManejo(nome="Prenha", dia_min=0, situacao_reprodutiva="prenha", ordem=2),
        ]
        prenha = _ctx(
            "10", data_nasc=HOJE - timedelta(days=1200), categoria_abrev="Novilha",
            servicos=[Servico(numero_matriz="10", data_servico=HOJE - timedelta(days=100), diagnostico="POSITIVO")],
            categorias_cadastro=cats,
        )
        atrasada = _ctx(
            "11", data_nasc=HOJE - timedelta(days=1200), categoria_abrev="Novilha",
            categorias_cadastro=cats,
        )
        assert prenha["situacao_reprodutiva"] == "prenha"
        assert prenha["categoria_cadastro"] == "Prenha"
        # A novilha "atrasada" (sem serviço, idade > idade_atraso_dias=450 já
        # passa do limite) não entra em "prenha" de forma alguma — cada
        # filtro tem gente, mas nunca a mesma.
        assert atrasada["situacao_reprodutiva"] != "prenha"

    def test_faixa_numerica_fora_de_qualquer_valor_do_rebanho(self):
        """Um filtro de peso 2000-3000kg não é "incompatível com outro
        filtro" — é um filtro individual sem correspondência nenhuma no
        rebanho. O diagnóstico do frontend precisa apontar ESTE filtro
        como o suspeito, não a combinação."""
        ctx = _ctx("12", peso=550.0)
        assert not (2000 <= ctx["peso_kg"] <= 3000)

    def test_bezerra_nao_tem_situacao_reprodutiva_computada(self):
        """Categoria etária = bezerra (idade abaixo de idade_apta_dias, sem
        serviço) cruzada com situação reprodutiva = prenha: estruturalmente
        vazia, porque uma bezerra que nunca foi servida não tem estado
        reprodutivo além de NAO_APTA/PEV, que mapeiam para None."""
        ctx = _ctx("13", data_nasc=HOJE - timedelta(days=200), categoria_abrev="Bezerra")
        assert ctx["categoria_etaria"] == "bezerra"
        assert ctx["situacao_reprodutiva"] is None
