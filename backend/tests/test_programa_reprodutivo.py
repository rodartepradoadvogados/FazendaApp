"""
Programa reprodutivo — um teste por regra do modelo lógico (R1 a R9) descrito
no topo de `fazenda/rules/programa_reprodutivo.py`.

O módulo é regra pura (sem banco), então estes testes também são: montam
dicionários de Animal/Parto/Servico e conferem o resultado direto. Rápidos de
propósito — são a rede de proteção do denominador de todos os indicadores
reprodutivos do sistema.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from fazenda.rules.programa_reprodutivo import (
    ATIVA,
    DIAS_MINIMOS_REPASSE_PADRAO,
    INATIVA,
    MOTIVO_A_DESCARTAR,
    MOTIVO_BAIXADA,
    MOTIVO_DENTRO_PEV,
    MOTIVO_ESTADO_NAO_MAPEADO,
    MOTIVO_GESTANTE,
    MOTIVO_IMPUBERE,
    SUSPENSA,
    Ciclo,
    calcular_ciclo,
    ciclos_21_dias,
    conta_em_taxa,
    dias_aptos,
    elegivel_ia,
    elegivel_prenhez,
    descartada_em,
    estado_no_dia,
    montar_perfil,
    resultado_conhecido,
    tem_reinseminacao_posterior,
)

PEV = 45
HOJE = date(2026, 3, 1)
CICLO = Ciclo(indice=1, inicio=date(2026, 1, 1), fim=date(2026, 1, 21))


def _animal(numero="100", **kw):
    base = {
        "numero": numero, "ativo": True, "a_descartar": False, "data_baixa": None,
        "categoria_abrev": "Vaca", "data_nasc": date(2022, 1, 1), "raca": "Holandês",
        "peso_kg": 600.0,
    }
    return {**base, **kw}


def _perfil(animal=None, partos=(), servicos=(), aplicacoes=()):
    return montar_perfil(
        animal or _animal(), partos=list(partos), servicos=list(servicos),
        aplicacoes_iatf=list(aplicacoes),
    )


def _parto(d: date, numero="100"):
    return {"numero_matriz": numero, "data_parto": d}


def _servico(d: date, diagnostico=None, numero="100", perda=None):
    return {
        "numero_matriz": numero, "data_servico": d, "diagnostico": diagnostico,
        "data_perda_prenhez": perda, "tipo_servico": "IA", "protocolo": None,
    }


def _estado(perfil, d):
    return estado_no_dia(perfil, d, pev_dias=PEV, del_max_1o_servico=None)


# ═══════════════════ R1 — entrada e saída do programa ═══════════════════════
class TestR1EntradaNoPrograma:
    """ATIVA_PROGRAMA ↔ atingiu aptidão ∧ ¬a_descartar ∧ ¬baixada.
    `a_descartar` e baixa são as ÚNICAS portas de saída."""

    def test_vaca_pos_pev_esta_ativa_no_programa(self):
        p = _perfil(partos=[_parto(date(2025, 11, 1))])
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == ATIVA
        assert e.apta is True

    def test_marcada_a_descartar_sai_do_programa(self):
        p = _perfil(_animal(a_descartar=True), partos=[_parto(date(2025, 11, 1))])
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == INATIVA
        assert e.apta is False
        assert e.motivo == MOTIVO_A_DESCARTAR

    def test_baixada_sai_do_programa_a_partir_da_data_da_baixa(self):
        p = _perfil(_animal(data_baixa=date(2026, 1, 10)), partos=[_parto(date(2025, 11, 1))])
        assert _estado(p, date(2026, 1, 9)).situacao == ATIVA, "antes da baixa ainda contava"
        depois = _estado(p, date(2026, 1, 10))
        assert depois.situacao == INATIVA
        assert depois.motivo == MOTIVO_BAIXADA

    def test_novilha_sem_idade_nem_peso_ainda_nao_entrou_no_programa(self):
        nova = _animal(categoria_abrev="Novilha", data_nasc=date(2025, 6, 1), peso_kg=200.0)
        p = _perfil(nova)
        e = estado_no_dia(
            p, date(2026, 1, 15), pev_dias=PEV, idade_apta_dias=450, peso_apta_kg=300.0,
        )
        assert e.situacao == INATIVA
        assert e.motivo == MOTIVO_IMPUBERE


# ═══════════════════ R2 — suspensão temporária ══════════════════════════════
class TestR2Suspensao:
    """Suspensa ≠ inativa: continua no programa, só não conta como apta."""

    def test_dentro_do_pev_fica_suspensa_e_nao_apta(self):
        p = _perfil(partos=[_parto(date(2026, 1, 1))])
        e = _estado(p, date(2026, 1, 20))  # DEL 19 < PEV 45
        assert e.situacao == SUSPENSA
        assert e.apta is False
        assert e.motivo == MOTIVO_DENTRO_PEV

    def test_gestante_fica_suspensa_e_nao_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 11, 1), diagnostico="POSITIVO")],
        )
        e = _estado(p, date(2026, 1, 15))
        assert e.situacao == SUSPENSA
        assert e.apta is False
        assert e.motivo == MOTIVO_GESTANTE


# ═══════════════════ R3/R4 — disponibilidade e aptidão ══════════════════════
class TestR4Aptidao:
    """APTA ↔ disponível ∧ ¬gestante ∧ (vazia ⊻ inseminada-sem-DG)."""

    def test_vazia_pos_pev_e_apta(self):
        p = _perfil(partos=[_parto(date(2025, 11, 1))])
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_inseminada_aguardando_dg_e_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 10), diagnostico=None)],
        )
        e = _estado(p, date(2026, 1, 15))
        assert e.apta is True, "inseminada sem DG continua no denominador"

    def test_diagnostico_negativo_volta_a_ser_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2025, 12, 1), diagnostico="NEGATIVO")],
        )
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_perda_de_prenhez_volta_a_ser_apta(self):
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO", perda=date(2025, 12, 20))],
        )
        assert _estado(p, date(2026, 1, 15)).apta is True

    def test_gestante_nunca_e_apta(self):
        """O bug de `indicadores._repro_benchmark`: o denominador somava
        `prenhes + vazias + inseminadas`. Vaca prenhe não pode ser inseminada,
        logo não pode estar no denominador de uma taxa de serviço."""
        p = _perfil(
            partos=[_parto(date(2025, 9, 1))],
            servicos=[_servico(date(2025, 11, 1), diagnostico="POSITIVO")],
        )
        assert _estado(p, date(2026, 1, 15)).apta is False


# ═══════ Dívida: `motivo` sempre None no ramo final de `estado_no_dia` ══════
class TestDividaMotivoDeNaoAptidao:
    """Dívida registrada: a última linha de `estado_no_dia` devolvia
    `EstadoDia(..., apta=estado in ESTADOS_APTOS, motivo=None, ...)` — ou
    seja, sempre que o estado ficava fora de ESTADOS_APTOS SEM ter passado
    por um dos branches explícitos acima (a_descartar/baixada/impúbere/PEV/
    gestante), o drill-down da tela ficava sem explicação nenhuma.

    Investigação: dos 8 estados que `estado_reprodutivo.classificar_animal`
    pode devolver, 3 (NAO_APTA/PEV/GESTANTE) já têm branch explícito ANTES
    da linha final, e os outros 5 (APTA/ATRASADA/EM_PROTOCOLO/INSEMINADA/
    VAZIA) estão todos dentro de ESTADOS_APTOS. Ou seja: com o par de
    módulos como está HOJE, o ramo `apta=False, motivo=None` é
    inalcançável — a lacuna nunca se manifesta nos dados reais.

    O problema é o acoplamento IMPLÍCITO: essa exaustão depende de alguém
    manter ESTADOS_APTOS e os branches explícitos sincronizados manualmente
    toda vez que `estado_reprodutivo.py` ganhar um estado novo. Nada no
    código força isso. O primeiro teste prova que hoje não há vítima; o
    segundo prova que, se a sincronização falhar amanhã, a lacuna não volta
    a ficar muda."""

    def test_todo_estado_real_de_hoje_ja_vem_com_motivo_quando_nao_apta(self):
        """"Antes" — na leitura literal do código antigo, isto já não
        quebrava (prova que a dívida, apesar de real na forma como o código
        estava escrito, não tinha vítima nos estados atuais)."""
        cenarios = {
            "a_descartar": _perfil(_animal(a_descartar=True), partos=[_parto(date(2025, 11, 1))]),
            "baixada": _perfil(_animal(data_baixa=date(2026, 1, 10)), partos=[_parto(date(2025, 11, 1))]),
            "dentro_pev": _perfil(partos=[_parto(date(2026, 1, 1))]),
            "gestante": _perfil(
                partos=[_parto(date(2025, 9, 1))],
                servicos=[_servico(date(2025, 11, 1), diagnostico="POSITIVO")],
            ),
        }
        d = date(2026, 1, 20)
        for nome, p in cenarios.items():
            e = _estado(p, d)
            assert e.apta is False, nome
            assert e.motivo is not None, f"{nome}: apta=False mas motivo=None"

        nova = _animal(categoria_abrev="Novilha", data_nasc=date(2025, 6, 1), peso_kg=200.0)
        e_impubere = estado_no_dia(
            _perfil(nova), date(2026, 1, 15), pev_dias=PEV, idade_apta_dias=450, peso_apta_kg=300.0,
        )
        assert e_impubere.apta is False
        assert e_impubere.motivo is not None

    def test_estado_desconhecido_nao_fica_mais_com_motivo_none(self, monkeypatch):
        """"Depois" — simula exatamente o cenário perigoso: um estado que
        `classificar_animal` viesse a devolver no futuro sem que ninguém o
        somasse a ESTADOS_APTOS nem lhe desse um branch explícito. Antes da
        correção, isto devolvia `apta=False, motivo=None`. Agora cai na
        salvaguarda `MOTIVO_ESTADO_NAO_MAPEADO`."""
        import fazenda.rules.programa_reprodutivo as pr

        def classificar_falso(*args, **kwargs):
            return {"estado": "estado_futuro_que_ninguem_mapeou"}

        monkeypatch.setattr(pr, "classificar_animal", classificar_falso)
        p = _perfil(partos=[_parto(date(2025, 11, 1))])
        e = pr.estado_no_dia(p, date(2026, 1, 20), pev_dias=PEV)
        assert e.apta is False
        assert e.motivo == MOTIVO_ESTADO_NAO_MAPEADO, (
            "estado fora de ESTADOS_APTOS e sem branch explícito não pode "
            "mais devolver motivo=None"
        )


# ═══════════════════ R5 — BR ELIG, os 11 de 21 dias ═════════════════════════
class TestR5ElegivelParaInseminacao:
    """Não precisa estar apta os 21 dias — precisa de pelo menos 11."""

    def test_exatamente_11_dias_aptos_entra(self):
        # PEV termina em 11/01 → apta de 11/01 a 21/01 = 11 dias.
        p = _perfil(partos=[_parto(date(2025, 11, 27))])
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 11
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True

    def test_apenas_10_dias_aptos_fica_de_fora(self):
        # PEV termina em 12/01 → apta de 12/01 a 21/01 = 10 dias.
        p = _perfil(partos=[_parto(date(2025, 11, 28))])
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 10
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is False

    def test_gestante_o_ciclo_todo_tem_zero_dias_aptos(self):
        p = _perfil(
            partos=[_parto(date(2025, 8, 1))],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO")],
        )
        assert dias_aptos(p, CICLO, pev_dias=PEV) == 0
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is False


# ═══════════════════ R6 — PG ELIG < BR ELIG ═════════════════════════════════
class TestR6ElegivelParaPrenhez:
    def test_presente_ate_o_fim_da_janela_entra_nos_dois(self):
        p = _perfil(partos=[_parto(date(2025, 10, 1))])
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True
        assert elegivel_prenhez(p, CICLO, pev_dias=PEV) is True

    def test_descartada_durante_a_janela_entra_em_br_elig_mas_sai_de_pg_elig(self):
        """É exatamente isto que faz PG ELIG ser menor que BR ELIG."""
        baixa_no_meio = _animal(data_baixa=date(2026, 2, 5))  # depois do ciclo, dentro da janela de DG
        p = _perfil(baixa_no_meio, partos=[_parto(date(2025, 10, 1))])
        assert elegivel_ia(p, CICLO, pev_dias=PEV) is True, "esteve apta o ciclo inteiro"
        assert elegivel_prenhez(p, CICLO, pev_dias=PEV) is False, "saiu antes de dar para avaliar"


# ══════ Dívida: `dias_janela_dg` inalcançável via `calcular_ciclo` ══════════
class TestDividaParametroDiasJanelaDg:
    """Dívida registrada: `dias_janela_dg` (o parâmetro de `elegivel_prenhez`
    que define o fim da janela de avaliação de PG ELIG) seria inalcançável
    na prática e/ou provocaria TypeError.

    Investigação: chamado DIRETO, `elegivel_prenhez(..., dias_janela_dg=X)`
    sempre funcionou — é parâmetro nomeado explícito, primeiro na assinatura.
    O problema estava um nível acima: NENHUM caller de produção passa esse
    parâmetro (nem `reproducao.py`, nem `recria.py`, nem
    `indicadores._parametros_ciclos`), e quem tentasse fazê-lo através de
    `calcular_ciclo`/`calcular_series` — o caminho normal, já que são eles
    que chamam `elegivel_prenhez` internamente — batia num TypeError: os dois
    declaravam só `**kwargs` genérico, repassado IGUAL para `elegivel_ia`
    (BR ELIG), que não conhece `dias_janela_dg` e o empurra adiante até
    `estado_no_dia`, que não tem `**kwargs` nenhum."""

    def test_chamada_direta_a_elegivel_prenhez_sempre_funcionou(self):
        p = _perfil(partos=[_parto(date(2025, 10, 1))])
        assert elegivel_prenhez(p, CICLO, pev_dias=PEV, dias_janela_dg=30) is True

    def test_calcular_ciclo_aceita_dias_janela_dg_sem_explodir(self):
        """"Antes" da correção, esta chamada levantava
        `TypeError: estado_no_dia() got an unexpected keyword argument
        'dias_janela_dg'` — confirmado por inspeção antes de qualquer
        mudança. "Depois", `calcular_ciclo` declara o parâmetro
        explicitamente (não deixa mais vazar por `**kwargs`) e ele muda o
        PG ELIG exatamente como deveria."""
        # baixa em 05/02: dentro da janela padrão (fim do ciclo 21/01 + 21 =
        # 11/02) e fora de uma janela mais curta (21/01 + 10 = 31/01).
        p = _perfil(
            _animal("4", data_baixa=date(2026, 2, 5)), partos=[_parto(date(2025, 10, 1), "4")],
        )
        r_padrao = calcular_ciclo([p], CICLO, HOJE, pev_dias=PEV)
        assert "4" not in r_padrao.pg_elig, "janela padrão de 21 dias: a baixa cai dentro dela"

        r_janela_curta = calcular_ciclo([p], CICLO, HOJE, pev_dias=PEV, dias_janela_dg=10)
        assert "4" in r_janela_curta.pg_elig, "janela de 10 dias: a baixa cai fora dela"

    def test_dias_janela_dg_continua_sem_sentido_passado_direto_a_elegivel_ia(self):
        """Fronteira deliberada da correção: BR ELIG não usa janela de DG
        nenhuma, então `elegivel_ia(..., dias_janela_dg=X)` continua sem
        sentido e continua estourando — só `calcular_ciclo` precisava parar
        de deixar o parâmetro vazar por engano para dentro de `elegivel_ia`."""
        p = _perfil(partos=[_parto(date(2025, 10, 1))])
        with pytest.raises(TypeError):
            elegivel_ia(p, CICLO, pev_dias=PEV, dias_janela_dg=30)


# ═══════════════════ R7 — a regra dos 28 dias ═══════════════════════════════
class TestR7ResultadoConhecido:
    def test_servico_antigo_sem_dg_conta(self):
        s = _servico(HOJE - timedelta(days=30))
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_de_27_dias_sem_dg_nao_conta(self):
        s = _servico(HOJE - timedelta(days=27))
        assert conta_em_taxa(s, HOJE) is False, "ainda não deu tempo de saber se pegou"

    def test_servico_recente_com_dg_negativo_conta(self):
        s = _servico(HOJE - timedelta(days=5), diagnostico="NEGATIVO")
        assert resultado_conhecido(s) is True
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_recente_com_dg_positivo_conta(self):
        s = _servico(HOJE - timedelta(days=5), diagnostico="POSITIVO")
        assert conta_em_taxa(s, HOJE) is True

    def test_servico_recente_com_perda_registrada_conta(self):
        s = _servico(HOJE - timedelta(days=10), perda=HOJE - timedelta(days=2))
        assert conta_em_taxa(s, HOJE) is True

    def test_reinseminada_em_cio_de_repasse_conta_mesmo_sem_dg(self):
        """A nova IA prova que a anterior não pegou — o desfecho É conhecido."""
        s = _servico(HOJE - timedelta(days=20))
        assert conta_em_taxa(s, HOJE) is False
        assert conta_em_taxa(s, HOJE, servico_posterior=True) is True


# ══════ Dívida: `tem_reinseminacao_posterior` sem janela mínima de repasse ═══
class TestDividaJanelaMinimaDeRepasse:
    """Dívida registrada: `tem_reinseminacao_posterior` aceitava QUALQUER
    serviço posterior como prova de cio de repasse, por mais próximo que
    estivesse do serviço original. Biologicamente uma segunda IA lançada 1-2
    dias depois não é um novo cio — é a mesma cobertura relançada ou um erro
    de data; o ciclo estral bovino gira em torno de 21 dias.

    A correção reaproveita `dias_reinseminacao_min` (18 dias), o parâmetro
    editável que já existe em `fazenda.rules.parametros` (grupo
    "reinseminacao_cio") para o mesmo conceito de "cio curto legítimo" — não
    foi criada nenhuma constante nova de configuração, só
    `DIAS_MINIMOS_REPASSE_PADRAO` espelhando o mesmo valor-padrão para este
    módulo, que é regra pura e não lê parâmetro de banco."""

    def test_reinseminacao_2_dias_depois_nao_prova_mais_repasse(self):
        """"Antes" (`dias_minimos_repasse=0` reproduz o comportamento antigo,
        sem nenhuma janela): qualquer posterior contava. "Depois" (padrão):
        2 dias de distância não prova nada."""
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 5)), _servico(date(2026, 1, 7))],
        )
        primeiro = p.servicos[0]
        assert tem_reinseminacao_posterior(p, primeiro, dias_minimos_repasse=0) is True
        assert tem_reinseminacao_posterior(p, primeiro) is False

    def test_reinseminacao_no_proximo_cio_continua_provando_repasse(self):
        """O caso de verdade que a regra existe para capturar: repasse
        ~21 dias depois, no cio seguinte."""
        p = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 5)), _servico(date(2026, 1, 26))],
        )
        assert tem_reinseminacao_posterior(p, p.servicos[0]) is True

    def test_a_fronteira_e_exatamente_dias_minimos_repasse(self):
        assert DIAS_MINIMOS_REPASSE_PADRAO == 18, (
            "mesmo piso do parâmetro editável dias_reinseminacao_min "
            "(fazenda.rules.parametros) — documentar se algum dia divergir"
        )
        dentro = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 5)), _servico(date(2026, 1, 23))],  # 18 dias
        )
        fora = _perfil(
            partos=[_parto(date(2025, 10, 1))],
            servicos=[_servico(date(2026, 1, 5)), _servico(date(2026, 1, 22))],  # 17 dias
        )
        assert tem_reinseminacao_posterior(dentro, dentro.servicos[0]) is True
        assert tem_reinseminacao_posterior(fora, fora.servicos[0]) is False


class TestSentinelaEfeitoDaJanelaMinimaDeRepasseNasTaxas:
    """Sentinela com números explícitos: a dívida 3 MOVE a taxa de
    concepção do painel neste cenário — não é uma correção silenciosa."""

    def test_taxa_de_concepcao_deixa_de_tratar_ia_recente_como_fracasso_provado(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=21), fim=hoje - timedelta(days=1))
        # IA em 10/02 (dentro do ciclo), e uma segunda IA só 2 dias depois,
        # em 12/02 — sem DG lançado em nenhuma das duas, e sem que tenham se
        # passado os 28 dias da regra R7 desde a primeira.
        p = _perfil(
            partos=[_parto(hoje - timedelta(days=200))],
            servicos=[
                _servico(ciclo.inicio + timedelta(days=2)),
                _servico(ciclo.inicio + timedelta(days=4)),
            ],
        )

        # ANTES (`dias_minimos_repasse=0` reproduz o motor sem a correção):
        r_antigo = calcular_ciclo([p], ciclo, hoje, pev_dias=PEV, dias_minimos_repasse=0)
        assert r_antigo.servicos_com_resultado == 1, (
            "a IA de 10/02 contava como 'resultado conhecido' só por existir "
            "uma segunda IA 2 dias depois"
        )
        assert r_antigo.taxa_concepcao == 0.0, (
            "o painel ANTIGO mostrava 0% de concepção neste ciclo — tratava "
            "uma IA de 19 dias, sem DG, como fracasso PROVADO"
        )

        # DEPOIS (padrão, dias_minimos_repasse=18 via DIAS_MINIMOS_REPASSE_PADRAO):
        r_novo = calcular_ciclo([p], ciclo, hoje, pev_dias=PEV)
        assert r_novo.servicos_com_resultado == 0, (
            "nem a IA de 10/02 (ainda dentro dos 28 dias, sem repasse de "
            "verdade) nem a de 12/02 (recente demais, e nada depois dela) "
            "têm resultado conhecido"
        )
        assert r_novo.taxa_concepcao is None, (
            "o painel CORRIGIDO não afirma desfecho nenhum — 0% virou None: "
            "de 'fracasso provado' para 'ainda não se sabe', que é a verdade"
        )
        # A taxa de prenhez não se mexe neste cenário: nenhuma das duas IAs
        # teve diagnóstico positivo, então PREG já era 0 dos dois lados.
        assert r_antigo.taxa_prenhez == r_novo.taxa_prenhez == 0.0


# ═══════════════════ Ciclos com âncora configurável ═════════════════════════
class TestCiclosAncora:
    def test_ancora_no_inicio_corre_para_frente(self):
        cs = ciclos_21_dias(date(2026, 1, 1), modo="inicio", n_ciclos=3)
        assert cs[0].inicio == date(2026, 1, 1)
        assert cs[0].fim == date(2026, 1, 21), "21 dias inclusivos"
        assert cs[1].inicio == date(2026, 1, 22)
        assert cs[-1].fim == date(2026, 3, 4)

    def test_ancora_no_fim_corre_para_tras(self):
        cs = ciclos_21_dias(date(2026, 3, 4), modo="fim", n_ciclos=3)
        assert cs[-1].fim == date(2026, 3, 4), "a âncora é o último dia"
        assert cs[0].inicio == date(2026, 1, 1)
        assert [c.indice for c in cs] == [1, 2, 3], "devolve em ordem cronológica"

    def test_as_duas_ancoras_produzem_a_mesma_serie(self):
        frente = ciclos_21_dias(date(2026, 1, 1), modo="inicio", n_ciclos=4)
        tras = ciclos_21_dias(frente[-1].fim, modo="fim", n_ciclos=4)
        assert [(c.inicio, c.fim) for c in frente] == [(c.inicio, c.fim) for c in tras]

    def test_todo_ciclo_tem_21_dias(self):
        for c in ciclos_21_dias(date(2026, 1, 1), n_ciclos=5):
            assert c.dias == 21
            assert len(c.datas()) == 21

    def test_modo_invalido_e_rejeitado(self):
        with pytest.raises(ValueError):
            ciclos_21_dias(date(2026, 1, 1), modo="meio")


# ═══════════════════ R8/R9 — as métricas do ciclo ═══════════════════════════
class TestR8R9Metricas:
    def _rebanho(self):
        """4 vacas aptas o ciclo todo:
          "1" inseminada e prenhe        → BR ELIG, BRED, PG ELIG, PREG
          "2" inseminada e vazia         → BR ELIG, BRED, PG ELIG
          "3" nunca inseminada           → BR ELIG, PG ELIG   (a que o antigo perdia)
          "4" nunca inseminada, descartada durante a janela de DG
                                         → BR ELIG, mas NÃO PG ELIG
        """
        return [
            _perfil(_animal("1"), partos=[_parto(date(2025, 10, 1), "1")],
                    servicos=[_servico(date(2026, 1, 5), diagnostico="POSITIVO", numero="1")]),
            _perfil(_animal("2"), partos=[_parto(date(2025, 10, 1), "2")],
                    servicos=[_servico(date(2026, 1, 5), diagnostico="NEGATIVO", numero="2")]),
            _perfil(_animal("3"), partos=[_parto(date(2025, 10, 1), "3")]),
            _perfil(_animal("4", data_baixa=date(2026, 2, 5)),
                    partos=[_parto(date(2025, 10, 1), "4")]),
        ]

    def test_vaca_nunca_inseminada_permanece_no_denominador(self):
        """O erro central do cálculo antigo: o universo eram os animais que
        TÊM serviço, então a vaca elegível que ninguém inseminou sumia do
        denominador — inflando a taxa de serviço exatamente onde o manejo foi
        pior."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert len(r.br_elig) == 4
        assert "3" in r.br_elig, "elegível e nunca inseminada continua no denominador"
        assert len(r.bred) == 2
        assert r.taxa_servico == 50.0

    def test_vaca_que_concebeu_no_proprio_ciclo_continua_no_denominador(self):
        """Ela vira gestante no dia 5 do ciclo. Se a prenhez do próprio ciclo
        a desqualificasse, ela sairia do denominador E do numerador — sumindo
        dos dois lados da conta justamente por ter dado certo."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert "1" in r.br_elig
        assert "1" in r.bred
        assert "1" in r.preg

    def test_taxa_de_prenhez_usa_pg_elig_como_denominador(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert len(r.pg_elig) == 3, "a descartada na janela de DG saiu"
        assert r.preg == ["1"]
        assert r.taxa_prenhez == round(100 * 1 / 3, 1)

    def test_pg_elig_menor_que_br_elig_quando_ha_descarte_na_janela(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert "4" in r.br_elig, "estava apta o ciclo inteiro"
        assert "4" not in r.pg_elig, "saiu antes de dar para avaliar a prenhez"
        assert len(r.pg_elig) < len(r.br_elig)

    def test_taxa_de_concepcao_usa_so_servicos_com_resultado_conhecido(self):
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        assert r.servicos_com_resultado == 2
        assert r.taxa_concepcao == 50.0

    def test_gestante_de_ciclo_anterior_nao_entra_no_denominador(self):
        rebanho = self._rebanho()
        rebanho.append(_perfil(
            _animal("9"), partos=[_parto(date(2025, 8, 1), "9")],
            servicos=[_servico(date(2025, 10, 1), diagnostico="POSITIVO", numero="9")],
        ))
        r = calcular_ciclo(rebanho, CICLO, HOJE, pev_dias=PEV)
        assert "9" not in r.br_elig, "prenhe não pode ser inseminada"
        assert len(r.br_elig) == 4

    def test_descartada_nao_entra_no_denominador(self):
        rebanho = self._rebanho()
        rebanho.append(_perfil(
            _animal("5", a_descartar=True), partos=[_parto(date(2025, 10, 1), "5")],
        ))
        r = calcular_ciclo(rebanho, CICLO, HOJE, pev_dias=PEV)
        assert "5" not in r.br_elig
        assert len(r.br_elig) == 4

    def test_R9_prenhez_nao_e_servico_vezes_concepcao(self):
        """Teste-sentinela. O cálculo antigo fazia `taxa_prenhez = SR × CR / 100`
        em DOIS lugares (`indicadores.py:210` e `reproducao_dossie.py:148`). Os
        denominadores são diferentes — PG ELIG e BR ELIG — e as populações são
        acompanhadas em janelas diferentes. Se alguém reintroduzir o atalho,
        este teste quebra."""
        r = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV)
        atalho = round(r.taxa_servico * r.taxa_concepcao / 100, 1)
        assert atalho == 25.0
        assert r.taxa_prenhez == 33.3
        assert r.taxa_prenhez != atalho, (
            f"taxa de prenhez ({r.taxa_prenhez}%) não pode ser o produto "
            f"serviço × concepção ({atalho}%)"
        )

    def test_ciclo_sem_animal_elegivel_devolve_none_em_vez_de_zero(self):
        r = calcular_ciclo([], CICLO, HOJE, pev_dias=PEV)
        assert r.taxa_servico is None
        assert r.taxa_prenhez is None
        assert r.taxa_concepcao is None

    def test_dict_de_saida_traz_o_drill_down_de_quem_entrou(self):
        d = calcular_ciclo(self._rebanho(), CICLO, HOJE, pev_dias=PEV).para_dict()
        assert d["br_elig"] == 4 and d["bred"] == 2 and d["pg_elig"] == 3 and d["preg"] == 1
        assert d["animais"]["br_elig"] == ["1", "2", "3", "4"]
        assert d["animais"]["preg"] == ["1"]


# ═══════════ Retrofit: o painel de benchmark da Capa (indicadores.py) ═══════
# Um período que rende EXATAMENTE UM ciclo de 21 dias fechando em HOJE
# (`n_ciclos = ceil(((hoje - desde).days + 1) / 21)`): é o recorte que deixa as
# asserções de taxa de serviço legíveis como "X servidas de Y elegíveis", sem
# diluição por ciclos vizinhos.
DESDE_1_CICLO = HOJE - timedelta(days=20)   # 2026-02-09 .. 2026-03-01
# Três ciclos: 2025-12-29..01-18 (única janela de DG já fechada em HOJE),
# 01-19..02-08 e 02-09..03-01.
DESDE_3_CICLOS = date(2026, 1, 1)


class TestRetrofitBenchmarkDaCapa:
    """`indicadores._repro_benchmark` alimenta a Capa, os Indicadores e o
    Manual da Fazenda. As três taxas do painel (serviço, concepção, prenhez)
    saem do motor de ciclos deste módulo — antes eram um acumulado do período
    dividido pelas aptas de HOJE, e estouravam 100% por construção."""

    def _valores(self, animais, servicos, estados, partos=(), desde=DESDE_1_CICLO, **kw):
        from fazenda.rules.indicadores import _repro_benchmark

        lista = _repro_benchmark(
            animais, servicos, list(partos), desde, categoria="todas",
            estados=estados, hoje=HOJE, **kw,
        )
        return {x["chave"]: x["valor"] for x in lista}

    def _vacas(self, *numeros, data_parto=date(2025, 6, 1)):
        """Vacas paridas há muito tempo: fora do PEV e elegíveis todos os dias
        do ciclo, que é o que estes testes precisam de pano de fundo."""
        animais = [{"numero": n} for n in numeros]
        return animais, [_parto(data_parto, n) for n in numeros]

    def test_gestante_saiu_do_denominador_da_taxa_de_servico(self):
        """Antes: `aptas = prenhes + vazias + inseminadas`, com a prenhe
        dentro. Uma vaca prenhe não pode ser inseminada — não entra no
        denominador de uma taxa de serviço (R2/R4). A "3" está prenhe desde
        ANTES do ciclo, então fica suspensa os 21 dias e sai do BR ELIG."""
        animais, partos = self._vacas("1", "2", "3")
        estados = {"1": "apta", "2": "apta", "3": "gestante"}
        servicos = [
            _servico(date(2025, 12, 15), "POSITIVO", "3"),  # prenhe antes do ciclo
            _servico(date(2026, 2, 15), None, "1"),         # servida DENTRO do ciclo
        ]
        v = self._valores(animais, servicos, estados, partos=partos)
        assert v["taxa_servico"] == 50.0, "BRED 1 de BR ELIG 2 — a gestante não conta"

    def test_atrasada_continua_no_denominador(self):
        """A vaca que deveria ter sido inseminada e não foi é justamente a que
        o indicador precisa enxergar: ATRASADA está em ESTADOS_APTOS."""
        animais = [{"numero": "1"}, {"numero": "2"}]
        partos = [
            _parto(date(2025, 12, 1), "1"),  # DEL ~70 no ciclo: APTA
            _parto(date(2025, 6, 1), "2"),   # DEL ~250: ATRASADA (passou do DEL máx.)
        ]
        estados = {"1": "apta", "2": "atrasada"}
        servicos = [_servico(date(2026, 2, 15), None, "1")]
        v = self._valores(animais, servicos, estados, partos=partos)
        assert v["taxa_servico"] == 50.0, "a atrasada continua no BR ELIG"

    def test_ia_recente_sem_dg_conta_como_servico_mas_nao_como_prenhez(self):
        """Onde R7 opera — e onde NÃO opera.

        A taxa de serviço mede o que o manejo fez: a IA aconteceu dentro do
        ciclo, e entra no BRED no dia em que foi feita (ela não fica esperando
        o diagnóstico para "virar" serviço). Quem espera é o RESULTADO: com a
        janela de DG do ciclo ainda aberta, prenhez e concepção não são
        exibidas — o denominador já está cheio e o numerador não.
        """
        animais, partos = self._vacas("1", "2")
        estados = {"1": "apta", "2": "apta"}
        recente = [_servico(HOJE - timedelta(days=5), None, "1")]
        v = self._valores(animais, recente, estados, partos=partos)
        assert v["taxa_servico"] == 50.0, "a inseminação do ciclo conta como serviço"
        assert v["taxa_prenhez_ciclo"] is None, "janela de DG aberta — não se afirma nada"
        assert v["taxa_concepcao"] is None

    def test_prenhez_deixou_de_ser_servico_vezes_concepcao(self):
        """R9 no painel da Capa: os denominadores são diferentes (BR ELIG,
        PG ELIG e serviços com resultado), então o atalho
        serviço × concepção não reproduz a prenhez.

        Rebanho: duas vacas paridas há muito tempo. A "1" foi inseminada duas
        vezes dentro do 1º ciclo (negativo em 02/01, positivo em 12/01) — é o
        único ciclo com janela de DG já fechada; a "2" nunca foi inseminada.
        """
        animais, partos = self._vacas("1", "2")
        estados = {"1": "apta", "2": "apta"}
        servicos = [
            _servico(date(2026, 1, 2), "NEGATIVO", "1"),
            _servico(date(2026, 1, 12), "POSITIVO", "1"),
        ]
        v = self._valores(animais, servicos, estados, partos=partos, desde=DESDE_3_CICLOS)
        # 1º ciclo: BRED 1 / BR ELIG 2; PREG 1 / PG ELIG 2; 1 prenhez / 2
        # serviços com resultado. Nos 2 ciclos seguintes a "1" já está gestante
        # e só a "2" fica elegível, sem ser servida — daí o serviço diluir.
        assert v["taxa_servico"] == 25.0, "1 servida / (2 + 1 + 1) elegíveis"
        assert v["taxa_concepcao"] == 50.0, "1 prenhez / 2 serviços com resultado"
        assert v["taxa_prenhez_ciclo"] == 50.0, "1 prenhe / 2 no PG ELIG"
        atalho = round(v["taxa_servico"] * v["taxa_concepcao"] / 100, 1)
        assert atalho == 12.5
        assert v["taxa_prenhez_ciclo"] != atalho

    def test_sem_registro_nenhum_as_tres_taxas_ficam_none(self):
        """Chamador legado (só a lista de animais, sem parto nem serviço): não
        há ciclo nenhum para calcular, e as três taxas voltam None em vez de um
        número inventado. Os indicadores de INVENTÁRIO continuam saindo do
        `sit_rep` congelado, como sempre saíram."""
        animais = [
            {"numero": "1", "sit_rep": "Vaz."}, {"numero": "2", "sit_rep": "Ins."},
            {"numero": "3", "sit_rep": "Ges."},
        ]
        v = self._valores(animais, [], estados=None)
        assert v["taxa_servico"] is None
        assert v["taxa_concepcao"] is None
        assert v["taxa_prenhez_ciclo"] is None
        assert v["perc_vacas_prenhas"] == 33.3, "1 prenhe de 3 — inventário pelo sit_rep"


# ═══════════════ Janela de DG incompleta — o ciclo que ainda não fechou ══════
class TestJanelaDgIncompleta:
    """O denominador da prenhez (PG ELIG) não tem a porta dos 28 dias; o
    numerador (PREG) tem. Enquanto a janela não fecha, a taxa sai subestimada
    por construção — e a tela não pode comparar esse ciclo com a meta."""

    def _vaca(self, hoje: date, data_servico: date, diagnostico=None):
        return _perfil(
            partos=[_parto(hoje - timedelta(days=200))],
            servicos=[_servico(data_servico, diagnostico)],
        )

    def test_ciclo_recem_encerrado_marca_janela_aberta(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=21), fim=hoje - timedelta(days=1))
        r = calcular_ciclo([self._vaca(hoje, ciclo.inicio)], ciclo, hoje, pev_dias=PEV)
        assert r.janela_dg_completa is False
        assert r.para_dict()["janela_dg_completa"] is False

    def test_ciclo_antigo_marca_janela_fechada(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=date(2026, 1, 1), fim=date(2026, 1, 21))
        r = calcular_ciclo([self._vaca(hoje, date(2026, 1, 5))], ciclo, hoje, pev_dias=PEV)
        assert r.janela_dg_completa is True

    def test_a_fronteira_e_exatamente_dias_resultado(self):
        hoje = date(2026, 3, 1)
        fecha = Ciclo(indice=1, inicio=hoje - timedelta(days=48), fim=hoje - timedelta(days=28))
        abre = Ciclo(indice=1, inicio=hoje - timedelta(days=47), fim=hoje - timedelta(days=27))
        assert calcular_ciclo([], fecha, hoje, pev_dias=PEV).janela_dg_completa is True
        assert calcular_ciclo([], abre, hoje, pev_dias=PEV).janela_dg_completa is False

    def test_a_flag_acompanha_dias_resultado_configurado(self):
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=30), fim=hoje - timedelta(days=10))
        assert calcular_ciclo([], ciclo, hoje, pev_dias=PEV,
                              dias_resultado=28).janela_dg_completa is False
        assert calcular_ciclo([], ciclo, hoje, pev_dias=PEV,
                              dias_resultado=5).janela_dg_completa is True

    def test_a_prenhez_do_ciclo_aberto_e_subestimada_de_proposito(self):
        """A prova do problema. Duas vacas inseminadas no mesmo ciclo recém
        encerrado: a 100 já teve o DG lançado, a 200 ainda não — e nem poderia,
        porque não passaram 28 dias da IA. As duas estão no PG ELIG; só a 100
        está no PREG. A tela mostraria 50% de prenhez, quando o que se sabe até
        aqui é "1 de 1 diagnosticada". Não houve piora de manejo nenhuma: falta
        tempo. É para isso que serve `janela_dg_completa`."""
        hoje = date(2026, 3, 1)
        ciclo = Ciclo(indice=1, inicio=hoje - timedelta(days=21), fim=hoje - timedelta(days=1))
        diagnosticada = _perfil(
            _animal("100"),
            partos=[_parto(hoje - timedelta(days=200), "100")],
            servicos=[_servico(ciclo.inicio, "POSITIVO", "100")],
        )
        aguardando = _perfil(
            _animal("200"),
            partos=[_parto(hoje - timedelta(days=200), "200")],
            servicos=[_servico(ciclo.fim, None, "200")],
        )
        r = calcular_ciclo([diagnosticada, aguardando], ciclo, hoje, pev_dias=PEV)
        assert sorted(r.pg_elig) == ["100", "200"], "as duas no denominador"
        assert r.preg == ["100"], "só a diagnosticada no numerador"
        assert r.taxa_prenhez == 50.0
        assert r.janela_dg_completa is False, "o aviso que impede ler isso como fracasso"


# ═══════════ R1 no benchmark da Capa — `a_descartar` fora do programa ═══════
class TestDescartadaForaDoBenchmark:
    """`_repro_benchmark` filtrava o denominador por ESTADOS_APTOS mas não
    consultava `a_descartar` em lugar nenhum — `classificar_animal` não recebe
    esse campo. A vaca marcada para descarte seguia sendo cobrada por uma
    inseminação que ninguém pretende fazer."""

    def _valores(self, animais, servicos, estados, partos=(), desde=DESDE_1_CICLO, **kw):
        from fazenda.rules.indicadores import _repro_benchmark

        lista = _repro_benchmark(
            animais, servicos, list(partos), desde, categoria="todas",
            estados=estados, hoje=HOJE, **kw,
        )
        return {x["chave"]: x["valor"] for x in lista}

    def _partos_antigos(self, *numeros):
        return [_parto(date(2025, 6, 1), n) for n in numeros]

    def test_descartada_sai_do_denominador_da_taxa_de_servico(self):
        animais = [{"numero": "1"}, {"numero": "2"}, {"numero": "3", "a_descartar": True}]
        estados = {"1": "apta", "2": "apta", "3": "apta"}
        servicos = [_servico(date(2026, 2, 15), None, "1")]
        v = self._valores(animais, servicos, estados, partos=self._partos_antigos("1", "2", "3"))
        assert v["taxa_servico"] == 50.0, "1 servida de 2 no programa — a descartada não conta"

    def test_descartada_inseminada_sai_tambem_do_numerador(self):
        """O caso que quebrava a conta: marcada DEPOIS de ter sido inseminada.
        Cortar só o denominador deixaria o serviço dela no numerador e levaria
        a taxa acima de 100%."""
        animais = [{"numero": "1", "a_descartar": True}, {"numero": "2"}]
        estados = {"1": "apta", "2": "apta"}
        servicos = [
            _servico(date(2026, 2, 15), None, "1"),
            _servico(date(2026, 2, 16), None, "2"),
        ]
        v = self._valores(animais, servicos, estados, partos=self._partos_antigos("1", "2"))
        assert v["taxa_servico"] == 100.0, "1 servida de 1 no programa"
        assert v["taxa_servico"] <= 100.0

    def test_descartada_prenhe_continua_no_inventario(self):
        """`perc_vacas_prenhas` é inventário, não taxa do programa: a vaca
        marcada para descarte que está prenhe continua prenhe — ela é a
        ÚNICA exceção que a R1 (puberdade ∧ ¬a_descartar ∧ ¬baixada) não
        aplica aqui, porque `total` (o denominador) passou a ser o rebanho
        no PROGRAMA reprodutivo, não mais `len(animais)` — os dois batem
        neste exemplo só porque nenhuma das 2 fêmeas é impúbere/baixada."""
        animais = [{"numero": "1"}, {"numero": "2", "a_descartar": True}]
        estados = {"1": "apta", "2": "gestante"}
        v = self._valores(animais, [], estados)
        assert v["perc_vacas_prenhas"] == 50.0, "1 prenhe de 2 no programa — a gestante entra pela exceção"

    def test_bezerra_impubere_fora_do_denominador_de_prenhas(self):
        """O defeito relatado: o denominador ERA `len(animais)`, o rebanho
        fêmeo inteiro — uma bezerra de 6 meses (estado 'nao_apta', nunca
        atingiu puberdade) entrava nele mesmo sem poder, por definição,
        estar prenhe. Agora ela nem entra no programa (R1)."""
        animais = [{"numero": "1"}, {"numero": "2"}]  # "2" = bezerra
        estados = {"1": "gestante", "2": "nao_apta"}
        v = self._valores(animais, [], estados)
        # ANTES: 100*1/2 = 50.0 (bezerra no denominador). DEPOIS: 100*1/1 = 100.0.
        assert v["perc_vacas_prenhas"] == 100.0, "só '1' está no programa — a bezerra nunca entrou"

    def test_a_descartar_e_baixada_fora_do_denominador_de_prenhas(self):
        """Duas portas de saída do programa (R1), as duas de uma vez: a
        vazia marcada a_descartar ("2", não é gestante, não tem exceção) e a
        baixada ("3", ativo=False — já saiu da fazenda, ninguém escapa desta
        porta, nem gestante)."""
        animais = [
            {"numero": "1"},                               # apta, no programa
            {"numero": "2", "a_descartar": True},           # vazia + descarte: fora
            {"numero": "3", "ativo": False},                # baixada: fora
            {"numero": "4"},                                # gestante, no programa
        ]
        estados = {"1": "apta", "2": "vazia", "3": "apta", "4": "gestante"}
        v = self._valores(animais, [], estados)
        # ANTES (rebanho inteiro, 4): 100*1/4 = 25.0. DEPOIS (programa, 2): 100*1/2 = 50.0.
        assert v["perc_vacas_prenhas"] == 50.0, "só '1' e '4' estão no programa"

    def test_o_corte_vale_nos_indicadores_do_periodo(self):
        """As três taxas passaram a sair do motor de ciclos, que já aplica a R1
        sozinho (`estado_no_dia` derruba a descartada em todos os dias). O
        corte por `descartar_nums` continua valendo para os indicadores que
        seguem sendo contados sobre os SERVIÇOS do período — aqui,
        `servicos_por_prenhez`: o serviço da descartada "3" não entra."""
        animais = [
            {"numero": "1", "sit_rep": "Vaz."},
            {"numero": "2", "sit_rep": "Ins."},
            {"numero": "3", "sit_rep": "Vaz.", "a_descartar": True},
        ]
        servicos = [
            _servico(date(2026, 2, 12), "POSITIVO", "1"),
            _servico(date(2026, 2, 13), "POSITIVO", "3"),
        ]
        v = self._valores(animais, servicos, estados=None)
        assert v["servicos_por_prenhez"] == 1.0, "só o serviço da '1' entra na conta"

    def test_perc_vacas_prenhas_no_fallback_de_sit_rep(self):
        """Sem estado ao vivo (nenhum registro carregado), `perc_vacas_prenhas`
        cai no sit_rep congelado: sem como enxergar puberdade nesse texto, o
        corte fica parcial (só descarte/baixa) — menos preciso, mas continua
        funcionando em vez de voltar ao denominador antigo (rebanho inteiro)."""
        animais = [
            {"numero": "1", "sit_rep": "Ges."},                                  # prenhe, fica
            {"numero": "2", "sit_rep": "Vaz.", "a_descartar": True},             # descarte: fora
            {"numero": "3", "sit_rep": "Ges.", "ativo": False},                  # baixada: fora, mesmo gestante
            {"numero": "4", "sit_rep": "Vaz."},                                  # vazia, fica
        ]
        v = self._valores(animais, [], estados=None)
        # ANTES (rebanho inteiro, 4): 100*2/4 = 50.0. DEPOIS (programa, 2): 100*1/2 = 50.0.
        assert v["perc_vacas_prenhas"] == 50.0, "só '1' e '4' ficam — '3' sai mesmo gestante (baixada é porta sem exceção)"

    def test_descartar_nums_explicito_vence_o_recorte_local(self):
        """O painel de vacas recebe só os animais que já pariram, mas os
        serviços são separados por `ordem_parto` — dois cortes independentes.
        Por isso o conjunto vem do rebanho inteiro."""
        animais_vaca = [{"numero": "1"}, {"numero": "2"}]
        servicos = [
            _servico(date(2026, 2, 12), "POSITIVO", "1"),
            _servico(date(2026, 2, 13), "POSITIVO", "9"),  # novilha descartada que vazou
        ]
        estados = {"1": "apta", "2": "apta"}
        v = self._valores(animais_vaca, servicos, estados, descartar_nums={"9"})
        assert v["servicos_por_prenhez"] == 1.0, "o serviço da descartada não entra na conta"


# ═════ As três taxas da Capa saem do motor de ciclos (não de um acumulado) ═══
class TestTaxasDaCapaSaemDoMotorDeCiclos:
    """O painel da Capa dividia conjuntos ACUMULADOS desde a data de corte
    (~7,6 meses) pela contagem INSTANTÂNEA de aptas de HOJE. Toda fêmea que
    emprenhava saía do denominador e ficava no numerador: o resultado estourava
    100% por construção. Agora as três taxas vêm de `calcular_series` — os
    mesmos ciclos de 21 dias da tela de Ciclos —, agregados por SOMA de
    numeradores e denominadores.
    """

    HOJE = date(2026, 8, 19)
    DESDE = date(2026, 1, 1)   # a data de corte de produção: 11 ciclos

    def _valores(self, animais, servicos, partos, *, desde=None, hoje=None,
                 categoria="todas", **kw):
        from fazenda.rules.indicadores import _repro_benchmark

        lista = _repro_benchmark(
            animais, servicos, partos, desde or self.DESDE, categoria=categoria,
            hoje=hoje or self.HOJE, **kw,
        )
        return {x["chave"]: x["valor"] for x in lista}

    # ---------------------------------------------------------------- sentinela
    def test_sentinela_as_tres_taxas_nunca_passam_de_100(self):
        """SENTINELA do defeito relatado em produção.

        Com o cálculo ANTIGO, a Capa exibia — com estes mesmos dados reais de
        fazenda — taxa de serviço 241,9% e prenhez 161,3% em "todas"; 104,3% e
        47,8% em vacas; e 687,5% e 487,5% em novilhas. O denominador era
        `aptas` = 31 fêmeas aptas HOJE (0 aptas + 3 atrasadas + 9 em protocolo
        + 19 inseminadas), contra um numerador acumulado de 7,6 meses.

        O rebanho abaixo reproduz a mecânica: 12 vacas servidas ao longo de
        vários ciclos, 10 delas gestantes hoje (fora do denominador antigo,
        dentro do numerador antigo) e só 2 aptas. O próprio teste refaz a conta
        antiga para mostrar que ela estoura, e exige que a nova fique no lugar.
        """
        from fazenda.rules.programa_reprodutivo import ESTADOS_APTOS

        numeros = [str(100 + i) for i in range(12)]
        animais = [{"numero": n} for n in numeros]
        partos = [_parto(date(2025, 9, 1), n) for n in numeros]
        # Uma inseminação por vaca, espalhadas ao longo do período. As 10
        # primeiras pegaram e estão gestantes hoje; as 2 últimas voltaram a
        # ficar aptas (DG negativo).
        servicos = [
            _servico(date(2026, 1, 10) + timedelta(days=15 * i), "POSITIVO", n)
            for i, n in enumerate(numeros[:10])
        ] + [
            _servico(date(2026, 2, 1), "NEGATIVO", n) for n in numeros[10:]
        ]
        estados = {n: ("gestante" if n in numeros[:10] else "apta") for n in numeros}

        # --- a conta ANTIGA, refeita aqui: acumulado ÷ aptas de hoje ---------
        aptas_hoje = sum(1 for n in numeros if estados[n] in ESTADOS_APTOS)
        servidas = {s["numero_matriz"] for s in servicos}
        concebidas = {s["numero_matriz"] for s in servicos if s["diagnostico"] == "POSITIVO"}
        assert 100 * len(servidas) / aptas_hoje == 600.0, "o defeito: 12 servidas ÷ 2 aptas"
        assert 100 * len(concebidas) / aptas_hoje == 500.0

        # --- a conta NOVA ----------------------------------------------------
        for categoria in ("todas", "vaca", "novilha"):
            v = self._valores(animais, servicos, partos, categoria=categoria, estados=estados)
            for chave in ("taxa_servico", "taxa_concepcao", "taxa_prenhez_ciclo"):
                valor = v[chave]
                assert valor is None or 0 <= valor <= 100, f"{categoria}/{chave} = {valor}"

        # E não passa por vacuidade: o rebanho é todo de vacas, e as taxas
        # delas saem de verdade (~19% de serviço e ~17% de prenhez por ciclo,
        # números de manejo — não os 600% da conta antiga).
        v = self._valores(animais, servicos, partos, categoria="vaca", estados=estados)
        assert v["taxa_servico"] is not None and v["taxa_prenhez_ciclo"] is not None

    # -------------------------------------------------- janela de DG incompleta
    def test_ciclo_com_janela_de_dg_aberta_fica_fora_da_prenhez_e_da_concepcao(self):
        """R7 — no ciclo cuja janela de diagnóstico ainda não fechou, o
        denominador (PG ELIG) já está cheio e o numerador (PREG) não: a taxa
        sairia subestimada por construção. Só a taxa de SERVIÇO, que não
        depende de desfecho, enxerga esse ciclo.

        Mesma vaca, mesma prenhez, duas datas: no ciclo mais recente (janela
        aberta) ela não produz prenhez nem concepção nenhuma; deslocada para um
        ciclo antigo (janela fechada), produz as duas.
        """
        animais = [{"numero": "1"}]
        partos = [_parto(date(2025, 9, 1), "1")]

        # Período de UM ciclo, que fecha hoje: a janela de DG está aberta.
        aberta = [_servico(self.HOJE - timedelta(days=3), "POSITIVO", "1")]
        v = self._valores(animais, aberta, partos, desde=self.HOJE - timedelta(days=20))
        assert v["taxa_servico"] == 100.0, "a IA do último ciclo conta como serviço"
        assert v["taxa_prenhez_ciclo"] is None, "nenhum ciclo com janela fechada"
        assert v["taxa_concepcao"] is None

        # Três ciclos: o primeiro (que contém a IA) já passou dos 28 dias.
        fechada = [_servico(self.HOJE - timedelta(days=50), "POSITIVO", "1")]
        v = self._valores(animais, fechada, partos, desde=self.HOJE - timedelta(days=62))
        assert v["taxa_prenhez_ciclo"] == 100.0
        assert v["taxa_concepcao"] == 100.0

    # ------------------------------------------------- agregação por soma
    def test_agregacao_soma_numeradores_e_denominadores_nao_media_de_pct(self):
        """Média PONDERADA pelo tamanho de cada ciclo, não média simples das
        porcentagens — um ciclo de 2 vacas não pode pesar igual a um de 10.

        Dois ciclos: no 1º, 10 vacas elegíveis e 1 servida (10%); no 2º, 2
        vacas elegíveis e as 2 servidas (100%). A média simples daria 55%; a
        soma de numeradores e denominadores dá 3/12 = 25%.
        """
        hoje = self.HOJE
        desde = hoje - timedelta(days=41)          # exatamente 2 ciclos
        inicio_c1 = hoje - timedelta(days=41)
        inicio_c2 = hoje - timedelta(days=20)

        # Grupo A: 10 vacas elegíveis no 1º ciclo e VENDIDAS no começo do 2º.
        grupo_a = [str(200 + i) for i in range(10)]
        animais = [{"numero": n, "data_baixa": inicio_c2} for n in grupo_a]
        partos = [_parto(hoje - timedelta(days=200), n) for n in grupo_a]
        servicos = [_servico(inicio_c1 + timedelta(days=5), None, grupo_a[0])]

        # Grupo B: 2 vacas que saem do PEV (45 dias) só no meio do 2º ciclo —
        # zero dia apto no 1º, 14 no 2º, e por isso só entram no BR ELIG do 2º.
        grupo_b = ["300", "301"]
        animais += [{"numero": n} for n in grupo_b]
        partos += [_parto(hoje - timedelta(days=58), n) for n in grupo_b]
        servicos += [_servico(inicio_c2 + timedelta(days=15), None, n) for n in grupo_b]

        v = self._valores(animais, servicos, partos, desde=desde)
        assert v["taxa_servico"] == 25.0, "3 servidas / 12 elegíveis somados"
        media_simples = round((10.0 + 100.0) / 2, 1)
        assert media_simples == 55.0 and v["taxa_servico"] != media_simples

    # --------------------------------------- novilha que pariu no meio do ano
    def test_novilha_que_pariu_no_periodo_nao_conta_nas_duas_categorias(self):
        """`_benchmark_categorias` separa os ANIMAIS por parto (vaca × novilha)
        mas fatiava os SERVIÇOS por `ordem_parto`: a novilha que pariu no meio
        do período tinha as IAs de antes do parto no recorte de novilha e as de
        depois no de vaca — e era contada nos DOIS painéis. Agora a categoria
        sai do próprio perfil (`eh_vaca`), montado do rebanho inteiro.

        Rebanho: "50" é a novilha que pariu em março; "51" é uma novilha pura,
        nunca servida; "60" é uma vaca. No painel de NOVILHAS, o denominador é
        só a "51", e ninguém foi servida — 0%. Pelo recorte antigo, a IA de
        novilha da "50" caía no numerador desse painel sem que ela estivesse no
        denominador, e a taxa dava 100%.
        """
        from fazenda.rules.indicadores import _benchmark_categorias

        hoje = self.HOJE
        animais = [
            {"numero": "50", "data_nasc": date(2024, 1, 1)},
            {"numero": "51", "data_nasc": date(2024, 1, 1)},
            {"numero": "60"},
        ]
        partos = [
            {"numero_matriz": "50", "data_parto": date(2026, 3, 10), "ordem_parto": 1},
            {"numero_matriz": "60", "data_parto": date(2025, 9, 1), "ordem_parto": 3},
        ]
        servicos = [
            # IA de NOVILHA da "50" (ordem_parto 0), que a emprenhou
            {**_servico(date(2025, 6, 1), "POSITIVO", "50"), "ordem_parto": 0},
            # IA de VACA da "50", já depois do parto
            {**_servico(date(2026, 5, 20), "POSITIVO", "50"), "ordem_parto": 1},
            {**_servico(date(2026, 6, 1), "POSITIVO", "60"), "ordem_parto": 3},
        ]
        cats = _benchmark_categorias(
            animais, servicos, partos, vacas_nums={"50", "60"}, desde=self.DESDE, hoje=hoje,
            peso_por_animal={"50": 400.0, "51": 400.0},
        )

        def val(categoria, chave):
            return next(b["valor"] for b in cats[categoria] if b["chave"] == chave)

        assert val("novilha", "taxa_servico") == 0.0, "a '50' não é novilha — ela pariu"
        assert val("vaca", "taxa_servico") > 0, "as IAs dela contam no painel de vacas"


class TestTodasEDerivadaDeVacaMaisNovilha:
    """A Capa precisa das mesmas taxas para "todas", "vaca" e "novilha", e cada
    passada do motor percorre 21 dias por ciclo por animal — três passadas
    custavam ~1,0 s com 127 animais na tela inicial.

    Como a partição por `perfil.eh_vaca` é DISJUNTA e cobre o rebanho, e todos
    os contadores são aditivos (`bred`/`br_elig`/`preg`/`pg_elig` contam
    animais; `com_resultado` conta serviços de animais da partição), "todas" é
    a soma das outras duas e não precisa de uma terceira passada.

    Este teste é a CONDIÇÃO da otimização: se o derivado deixar de ser idêntico
    ao calculado direto, a otimização é inválida e tem de sair.
    """

    HOJE = date(2026, 8, 19)
    DESDE = date(2026, 1, 1)

    def _perfis(self):
        from fazenda.rules.indicadores import _montar_perfis
        animais, servicos, partos = [], [], []
        # Rebanho misto: vacas em vários pontos do ciclo, novilhas nulíparas
        # servidas, e uma novilha que PARIU no meio do período — o caso que
        # antes era contado nas duas categorias.
        for i in range(12):
            n = f"V{i}"
            animais.append({"numero": n, "data_nasc": self.HOJE - timedelta(days=1500 + i),
                            "categoria_abrev": "Vaca"})
            partos.append({"numero_matriz": n, "data_parto": self.HOJE - timedelta(days=90 + i * 15)})
            servicos.append({"numero_matriz": n, "data_servico": self.HOJE - timedelta(days=40 + i * 12),
                             "diagnostico": "POSITIVO" if i % 3 == 0 else "NEGATIVO"})
        for i in range(8):
            n = f"N{i}"
            animais.append({"numero": n, "data_nasc": self.HOJE - timedelta(days=600 + i),
                            "categoria_abrev": "Novilha"})
            servicos.append({"numero_matriz": n, "data_servico": self.HOJE - timedelta(days=50 + i * 20),
                             "diagnostico": "POSITIVO" if i % 2 else None})
        animais.append({"numero": "M1", "data_nasc": self.HOJE - timedelta(days=900), "categoria_abrev": "Novilha"})
        servicos.append({"numero_matriz": "M1", "data_servico": self.HOJE - timedelta(days=300), "diagnostico": "POSITIVO"})
        partos.append({"numero_matriz": "M1", "data_parto": self.HOJE - timedelta(days=20)})
        peso = {a["numero"]: 400.0 for a in animais}
        return _montar_perfis(animais, servicos, partos, [], peso)

    def test_contadores_derivados_sao_identicos_aos_calculados_direto(self):
        from fazenda.rules.indicadores import (
            _parametros_ciclos, contadores_ciclos, somar_contadores,
        )
        perfis = self._perfis()
        params = _parametros_ciclos()
        direto = contadores_ciclos(perfis, self.DESDE, self.HOJE, params)
        derivado = somar_contadores(
            contadores_ciclos([p for p in perfis if p.eh_vaca], self.DESDE, self.HOJE, params),
            contadores_ciclos([p for p in perfis if not p.eh_vaca], self.DESDE, self.HOJE, params),
        )
        assert derivado == direto, (
            "a soma vaca+novilha divergiu do cálculo direto sobre o rebanho — "
            "a partição deixou de ser disjunta ou algum contador deixou de ser aditivo"
        )
        assert direto["br_elig"] > 0, "cenário vazio não prova nada"

    def test_categoria_vazia_nao_quebra_a_soma(self):
        """Fazenda só de vacas: o lado das novilhas vem zerado e a soma
        continua igual ao cálculo direto (o caso que faria a otimização
        estourar se ela assumisse as duas categorias sempre povoadas)."""
        from fazenda.rules.indicadores import (
            _parametros_ciclos, contadores_ciclos, somar_contadores,
        )
        perfis = [p for p in self._perfis() if p.eh_vaca]
        params = _parametros_ciclos()
        derivado = somar_contadores(
            contadores_ciclos(perfis, self.DESDE, self.HOJE, params),
            contadores_ciclos([], self.DESDE, self.HOJE, params),
        )
        assert derivado == contadores_ciclos(perfis, self.DESDE, self.HOJE, params)

    def test_as_taxas_da_capa_nao_mudam_com_a_otimizacao(self):
        """Sentinela de ponta a ponta: o que a tela exibe tem de ser o mesmo
        antes e depois de derivar "todas" em vez de recalculá-la."""
        from fazenda.rules.indicadores import (
            _benchmark_categorias, _parametros_ciclos, contadores_ciclos, taxas_de_contadores,
        )
        perfis = self._perfis()
        animais = [{"numero": p.numero, "data_nasc": p.data_nasc,
                    "categoria_abrev": "Vaca" if p.eh_vaca else "Novilha"} for p in perfis]
        servicos = [s for p in perfis for s in p.servicos]
        partos = [x for p in perfis for x in p.partos]
        vacas_nums = {p.numero for p in perfis if p.eh_vaca}
        cats = _benchmark_categorias(
            animais, servicos, partos, vacas_nums, self.DESDE, hoje=self.HOJE,
            peso_por_animal={p.numero: 400.0 for p in perfis},
        )
        esperado = taxas_de_contadores(
            contadores_ciclos(perfis, self.DESDE, self.HOJE, _parametros_ciclos())
        )
        obtido = tuple(
            next(b["valor"] for b in cats["todas"] if b["chave"] == chave)
            for chave in ("taxa_servico", "taxa_prenhez_ciclo", "taxa_concepcao")
        )
        assert obtido == esperado


class TestPainelMedeNovilhasSemPesagem:
    """O defeito relatado pelo produtor: com o filtro "Novilhas", os três
    medidores da Capa apareciam VAZIOS (travessão), e "Todas" exibia números
    idênticos aos de "Vacas".

    Não era falha de recorte: sem PesagemCorporal lançada, toda novilha
    nulípara era NAO_APTA todos os dias, ficava fora do BR ELIG de todo ciclo,
    e as três taxas voltavam None. Como "Todas" é derivado somando vaca +
    novilha, somar zero fazia "Todas" virar cópia exata de "Vacas" — passando
    por número do rebanho inteiro quando descrevia só as vacas.

    Nesta fazenda são 74 novilhas contra 37 vacas (GERAL.csv), com 59
    prenhezes de novilha que o painel não enxergava.
    """

    HOJE = date(2026, 8, 19)
    DESDE = date(2026, 1, 1)

    def _rebanho_sem_pesagem(self):
        """Novilhas com idade de sobra e ZERO pesagens; vacas normais."""
        animais, servicos, partos = [], [], []
        for i in range(12):  # novilhas servidas ao longo do período
            n = f"N{i}"
            animais.append({"numero": n, "categoria_completa": "Novilha",
                            "data_nasc": self.HOJE - timedelta(days=640 + i)})
            servicos.append({"numero_matriz": n,
                             "data_servico": self.HOJE - timedelta(days=60 + i * 14),
                             "diagnostico": "POSITIVO" if i % 2 else "NEGATIVO"})
        for i in range(6):   # novilhas em idade, ainda não servidas
            animais.append({"numero": f"L{i}", "categoria_completa": "Novilha",
                            "data_nasc": self.HOJE - timedelta(days=600 + i)})
        for i in range(8):   # vacas
            n = f"V{i}"
            animais.append({"numero": n, "categoria_completa": "Vaca",
                            "data_nasc": self.HOJE - timedelta(days=1600)})
            partos.append({"numero_matriz": n, "data_parto": self.HOJE - timedelta(days=120 + i * 10)})
            servicos.append({"numero_matriz": n,
                             "data_servico": self.HOJE - timedelta(days=50 + i * 12),
                             "diagnostico": "POSITIVO" if i % 3 else "NEGATIVO"})
        return animais, servicos, partos

    def _cats(self):
        from fazenda.rules.indicadores import _benchmark_categorias
        animais, servicos, partos = self._rebanho_sem_pesagem()
        vacas_nums = {p["numero_matriz"] for p in partos}
        cats = _benchmark_categorias(
            animais, servicos, partos, vacas_nums, self.DESDE, hoje=self.HOJE,
            peso_por_animal={},   # <- o ponto: fazenda que não pesa
        )
        return {c: {b["chave"]: b["valor"] for b in cats[c]} for c in cats}

    def test_as_tres_taxas_de_novilha_deixam_de_ser_none(self):
        nov = self._cats()["novilha"]
        for chave in ("taxa_servico", "taxa_concepcao", "taxa_prenhez_ciclo"):
            assert nov[chave] is not None, (
                f"{chave} de novilha voltou None sem pesagem — o painel voltou a "
                "apagar o rebanho de recria da medição"
            )

    def test_todas_deixa_de_ser_copia_de_vacas(self):
        c = self._cats()
        assert c["novilha"]["taxa_servico"] > 0, "cenário sem novilha medida não prova nada"
        assert (c["todas"]["taxa_servico"], c["todas"]["taxa_prenhez_ciclo"]) != (
            c["vaca"]["taxa_servico"], c["vaca"]["taxa_prenhez_ciclo"]
        ), '"Todas" repetindo "Vacas" é o sintoma de novilha com denominador zerado'

    def test_pesagem_abaixo_do_minimo_continua_tirando_a_novilha_do_denominador(self):
        """A regra não virou permissiva: quem PESA e está abaixo do mínimo
        continua fora. Só a AUSÊNCIA de pesagem deixou de reprovar."""
        from fazenda.rules.indicadores import _benchmark_categorias
        animais, servicos, partos = self._rebanho_sem_pesagem()
        leves = {a["numero"]: 150.0 for a in animais if a["numero"].startswith(("N", "L"))}
        cats = _benchmark_categorias(
            animais, servicos, partos, {p["numero_matriz"] for p in partos},
            self.DESDE, hoje=self.HOJE, peso_por_animal=leves,
        )
        nov = {b["chave"]: b["valor"] for b in cats["novilha"]}
        assert nov["taxa_servico"] is None


class TestAtrasoDeNovilhaNaoMoveTaxa:
    """Dar ATRASADA à novilha é informação, não mudança de conta.

    ATRASADA já está em `ESTADOS_APTOS` (com a justificativa escrita no módulo:
    é justamente a fêmea que deveria ter sido inseminada e não foi, e tirá-la
    do denominador inflava a taxa de serviço) e em `ESTADOS_CANDIDATA` de
    `iatf.py`. Logo o teto apenas SUBDIVIDE o balde das aptas — nenhum animal
    entra ou sai de conjunto nenhum.

    Se esta sentinela quebrar, o teto passou a mexer em denominador, e a
    mudança deixou de ser segura.
    """

    HOJE = date(2026, 8, 19)
    DESDE = date(2026, 1, 1)

    def _cats(self, monkeypatch, *, com_teto: bool):
        import fazenda.rules.indicadores as ind
        from fazenda.rules.indicadores import _benchmark_categorias
        # Sem teto = teto tão alto que nenhuma novilha o alcança; é o
        # comportamento anterior à mudança, com o mesmo caminho de código.
        monkeypatch.setattr(ind, "idade_max_1a_cobertura_meses", (lambda: 16.0) if com_teto else (lambda: 999.0))
        animais, servicos, partos = [], [], []
        for i in range(14):   # novilhas bem acima do teto (idades reais do CSV)
            n = f"N{i}"
            animais.append({"numero": n, "categoria_completa": "Novilha",
                            "data_nasc": self.HOJE - timedelta(days=[538, 617, 726, 748, 809, 918][i % 6])})
            if i % 2:
                servicos.append({"numero_matriz": n,
                                 "data_servico": self.HOJE - timedelta(days=60 + i * 11),
                                 "diagnostico": "POSITIVO" if i % 3 else "NEGATIVO"})
        for i in range(8):
            n = f"V{i}"
            animais.append({"numero": n, "categoria_completa": "Vaca",
                            "data_nasc": self.HOJE - timedelta(days=1600)})
            partos.append({"numero_matriz": n, "data_parto": self.HOJE - timedelta(days=130 + i * 9)})
            servicos.append({"numero_matriz": n, "data_servico": self.HOJE - timedelta(days=55 + i * 10),
                             "diagnostico": "POSITIVO" if i % 3 else "NEGATIVO"})
        cats = _benchmark_categorias(
            animais, servicos, partos, {p["numero_matriz"] for p in partos},
            self.DESDE, hoje=self.HOJE, peso_por_animal={},
        )
        return {c: {b["chave"]: b["valor"] for b in cats[c]} for c in cats}

    def test_as_tres_taxas_sao_identicas_com_e_sem_o_teto(self, monkeypatch):
        com = self._cats(monkeypatch, com_teto=True)
        sem = self._cats(monkeypatch, com_teto=False)
        for cat in ("todas", "vaca", "novilha"):
            for chave in ("taxa_servico", "taxa_concepcao", "taxa_prenhez_ciclo"):
                assert com[cat][chave] == sem[cat][chave], (
                    f"{cat}/{chave} mudou ao subdividir APTA/ATRASADA — o teto "
                    "vazou para o denominador"
                )
        assert com["novilha"]["taxa_servico"] is not None, "cenário sem novilha medida não prova nada"


class TestDescarteDatado:
    """`a_descartar` era booleano sem data: a marcação feita hoje retroagia
    para TODOS os ciclos passados, e a vaca sumia até dos denominadores em que
    estava legitimamente ativa — encolhendo o BR ELIG histórico justamente nas
    vacas problema e inflando a taxa de serviço do passado.

    `Animal.a_descartar_em` (migração c576e514aa3e) fechou isso. Estes testes
    travam as três situações: com data, sem data, e não marcada."""

    def test_antes_da_marcacao_a_vaca_ainda_contava(self):
        marcada_em = date(2026, 2, 1)
        perfil = _perfil(_animal(a_descartar=True, a_descartar_em=marcada_em))
        assert descartada_em(perfil, marcada_em - timedelta(days=1)) is False
        assert descartada_em(perfil, marcada_em) is True
        assert descartada_em(perfil, marcada_em + timedelta(days=30)) is True

    def test_o_estado_do_dia_acompanha_a_data(self):
        """É o que faz a vaca voltar aos ciclos passados: no dia anterior à
        marcação ela está ATIVA, não INATIVA por descarte."""
        marcada_em = date(2026, 2, 1)
        perfil = _perfil(
            _animal(a_descartar=True, a_descartar_em=marcada_em),
            partos=[_parto(date(2025, 10, 1))],
        )
        antes = estado_no_dia(perfil, marcada_em - timedelta(days=1), pev_dias=PEV)
        depois = estado_no_dia(perfil, marcada_em, pev_dias=PEV)
        assert antes.situacao == ATIVA
        assert antes.motivo != MOTIVO_A_DESCARTAR
        assert depois.situacao == INATIVA
        assert depois.motivo == MOTIVO_A_DESCARTAR

    def test_marcada_sem_data_continua_valendo_desde_sempre(self):
        """Registros anteriores à coluna ficaram com `a_descartar_em = NULL`,
        sem backfill de propósito — inventar data produziria histórico
        plausível e falso. Sem data, o comportamento é o antigo: marcação
        já vigente. É o que garante que NENHUM número muda no dia do deploy."""
        perfil = _perfil(_animal(a_descartar=True, a_descartar_em=None))
        assert descartada_em(perfil, date(2020, 1, 1)) is True
        assert descartada_em(perfil, date(2026, 12, 31)) is True

    def test_nao_marcada_nunca_esta_descartada(self):
        perfil = _perfil(_animal(a_descartar=False, a_descartar_em=None))
        assert descartada_em(perfil, date(2026, 2, 1)) is False
        # data sobrando sem a marcação ativa não pode ressuscitar o descarte
        perfil2 = _perfil(_animal(a_descartar=False, a_descartar_em=date(2026, 1, 1)))
        assert descartada_em(perfil2, date(2026, 2, 1)) is False


class TestSentinelaPrevisaoDeDescarteNaoMoveTaxa:
    """`Animal.descarte_previsto_em` (QUANDO SE PRETENDE tirar do rebanho) é
    INFORMATIVA. Quem manda no cálculo é `a_descartar_em` (QUANDO SE DECIDIU),
    porque a saída do programa reprodutivo é a decisão, não o caminhão: quem
    decide descartar para de inseminar naquele momento.

    Se um dia alguém ligar a previsão ao motor, uma vaca que ninguém mais vai
    inseminar voltaria ao denominador e inflaria a taxa de serviço — o mesmo
    efeito que a AUSÊNCIA de data causava antes de `a_descartar_em` existir.
    Estes testes existem para essa mudança não passar despercebida."""

    def test_perfil_do_motor_nao_tem_o_campo(self):
        """A garantia mais forte é estrutural: o objeto que o motor enxerga não
        carrega a previsão, então nenhuma regra pode lê-la por acidente."""
        perfil = _perfil()
        assert not hasattr(perfil, "descarte_previsto_em")

    def test_previsao_no_dict_do_animal_nao_muda_nada(self):
        """Ponta a ponta: o mesmo animal, com e sem previsão preenchida, tem de
        produzir estado idêntico em todas as datas — inclusive com previsão no
        passado, que é o caso que mais tentaria o motor a reagir."""
        hoje = date(2026, 8, 20)
        partos = [_parto(hoje - timedelta(days=90))]
        servicos = [_servico(hoje - timedelta(days=30))]

        sem = _perfil(_animal(), partos=partos, servicos=servicos)
        com_futura = _perfil(
            _animal(descarte_previsto_em=hoje + timedelta(days=60)), partos=partos, servicos=servicos,
        )
        com_vencida = _perfil(
            _animal(descarte_previsto_em=hoje - timedelta(days=10)), partos=partos, servicos=servicos,
        )

        for d in (hoje - timedelta(days=60), hoje - timedelta(days=5), hoje, hoje + timedelta(days=30)):
            base = estado_no_dia(sem, d, pev_dias=50)
            assert estado_no_dia(com_futura, d, pev_dias=50) == base
            assert estado_no_dia(com_vencida, d, pev_dias=50) == base

    def test_quem_decide_a_saida_e_a_data_da_MARCACAO(self):
        """Contraprova do teste acima: mudar `a_descartar_em` MUDA o resultado.
        Sem esta asserção o teste anterior passaria mesmo que o motor tivesse
        parado de olhar as duas datas."""
        hoje = date(2026, 8, 20)
        marcada_ontem = _perfil(_animal(a_descartar=True, a_descartar_em=hoje - timedelta(days=1)))
        marcada_amanha = _perfil(_animal(a_descartar=True, a_descartar_em=hoje + timedelta(days=1)))
        assert descartada_em(marcada_ontem, hoje) is True
        assert descartada_em(marcada_amanha, hoje) is False
