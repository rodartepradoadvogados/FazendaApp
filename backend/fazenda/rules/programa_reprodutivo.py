"""
Programa reprodutivo — quem está no jogo, quem está suspenso, e quem entra no
denominador de cada indicador reprodutivo.

## Por que este módulo existe

Os indicadores reprodutivos do sistema tinham três defeitos estruturais que
este módulo corrige de uma vez, num lugar só:

1. **Denominador com gestante dentro.** `indicadores._repro_benchmark` somava
   `prenhes + vazias + inseminadas` e chamava isso de "aptas". Vaca prenhe não
   pode ser inseminada — não pode estar no denominador de uma taxa de serviço.
2. **Denominador só com quem foi inseminado.** `reproducao_dossie.
   taxa_prenhez_ciclos` usava "os próprios serviços como universo de animais
   avaliáveis". A vaca elegível que atravessou o ciclo inteiro SEM ser
   inseminada não tem linha de `Servico` — e sumia do denominador. Isso inflava
   a taxa de serviço exatamente onde o manejo foi pior.
3. **Taxa de prenhez = serviço × concepção.** Atalho que o DairyComp não faz:
   os denominadores são diferentes (PG ELIG vs BR ELIG) e as populações são
   acompanhadas em janelas diferentes.

## O modelo lógico (é o contrato deste módulo)

Predicados de base, todos avaliados NUMA DATA `d` — nada aqui olha o "agora":

    ATINGIU_PUBERDADE(a,d) novilha: idade/peso >= parâmetros; vaca: após o 1º parto
    A_DESCARTAR(a,d)       Animal.a_descartar
    BAIXADA(a,d)           Animal.ativo = False, ou data_baixa <= d
    DENTRO_PEV(a,d)        d < último_parto + pev_dias
    GESTANTE(a,d)          serviço vigente POSITIVO, sem perda registrada
    VAZIA(a,d)             sem serviço vigente, ou vigente NEGATIVO, ou com perda
    INSEMINADA_SEM_DG(a,d) serviço vigente sem diagnóstico até d

CUIDADO com "aptidão": ATINGIU_PUBERDADE é um marco permanente da vida do
animal (bateu idade e peso), enquanto APTA (R4) é a disponibilidade DAQUELE
dia e muda todo dia. São conceitos sem relação; o nome antigo do primeiro era
`ATINGIU_APTIDAO` e confundia os dois.

Regras:

    R1  ATIVA_PROGRAMA(a,d) <-> ATINGIU_PUBERDADE(a,d) & ~A_DESCARTAR(a,d)
                                                       & ~BAIXADA(a,d)

        De novilha apta em diante todos estão ativos. `a_descartar` e baixa são
        as ÚNICAS portas de saída do programa.

    R2  ATIVA_PROGRAMA(a,d) & ( DENTRO_PEV(a,d) | GESTANTE(a,d) ) -> SUSPENSA(a,d)

        Suspensa NÃO é inativa: o animal continua no programa, apenas não conta
        como apto naquele dia.

    R3  DISPONIVEL(a,d) <-> ATIVA_PROGRAMA(a,d) & ~DENTRO_PEV(a,d)

        "Disponível" = terminou o PEV. É o vocabulário do produtor.

    R4  APTA(a,d) <-> DISPONIVEL(a,d) & ~GESTANTE(a,d)
                      & ( VAZIA(a,d) XOR INSEMINADA_SEM_DG(a,d) )

        O "ou ou" é exclusivo e verdadeiro por construção: os dois estados são
        mutuamente excludentes. Gestante nunca é apta; inseminada NÃO é
        automaticamente apta — depende de ainda não ter DG.

    R5  ELEGIVEL_IA(a,C) <-> | { d em C : APTA*(a,d) } | >= 11       (BR ELIG)

        Não precisa estar apta os 21 dias do ciclo: precisa ter participado de
        pelo menos metade dele. 11 = ceil(21/2) — é aritmética, não um limiar
        biológico; se `dias` do ciclo mudar, `dias_minimos` NÃO acompanha
        sozinho e precisa ser passado junto.

    R5a APTA*(a,d) = APTA(a,d) avaliado sobre o animal SEM os serviços lançados
        dentro do próprio ciclo C.

        Esta é a regra que o código executa, e ela NÃO é a R4 pura — por isso
        está escrita. A pergunta que a elegibilidade responde é "este animal
        estava disponível para ser inseminado durante este ciclo?", não "como
        ele terminou o ciclo?". Sem o recorte, a vaca inseminada no dia 5 que
        CONCEBEU vira gestante do dia 5 em diante, acumula 4 dias aptos e cai
        fora do BR ELIG — excluída por ter dado certo, sumindo ao mesmo tempo
        do numerador e do denominador. Implementado em
        `_perfil_sem_servicos_do_ciclo`.

        Efeito colateral, para não assustar quem for depurar: sem o serviço, o
        animal deixa de ser INSEMINADA e passa a VAZIA nos dias seguintes. Os
        dois estão em ESTADOS_APTOS, então a contagem não muda.

    R6  ELEGIVEL_PRENHEZ(a,C) <-> ELEGIVEL_IA(a,C)
                                  & ~BAIXADA(a, fim da janela de DG)   (PG ELIG)

        É aqui que PG ELIG fica MENOR que BR ELIG: a vaca BAIXADA (morta ou
        vendida) durante a janela de avaliação estava no BR ELIG e cai fora do
        PG ELIG.

        CUIDADO com a palavra "descartada": no português de fazenda ela
        significa `a_descartar`, e é justamente o caso onde esta regra NÃO
        opera. `a_descartar` não tem data, então R1 já derrubou o animal em
        TODOS os dias e ele nunca chegou ao BR ELIG. Só `data_baixa`, que é
        datada, produz o efeito descrito aqui.

    R-BRED  BRED(C) = { a em BR ELIG(C) : existe serviço de `a` com
                        data_servico dentro de C }

        BRED é subconjunto de BR ELIG por construção: um animal inseminado no
        ciclo mas que não acumulou 11 dias aptos não entra em nenhum dos dois.

    R-PREG  PREG(C) = { a em PG ELIG(C) : existe serviço de `a` dentro de C com
                        diagnóstico POSITIVO, sem perda registrada, e com
                        CONTA_EM_TAXA verdadeiro }

        Exige PG ELIG, não só BR ELIG — a vaca que concebeu e foi vendida antes
        do fim da janela sai do numerador e do denominador ao mesmo tempo.

    R7  RESULTADO_CONHECIDO(s,hoje) <-> TEM_DG(s) | PERDA_REGISTRADA(s)
                                        | REINSEMINADA_CIO_REPASSE(s)

        DG negativo é um caso de TEM_DG, não um termo separado.

        REINSEMINADA_CIO_REPASSE(s) exige uma nova IA depois de `s`, na mesma
        lactação, com pelo menos `dias_minimos_repasse` de distância (padrão
        `DIAS_MINIMOS_REPASSE_PADRAO` = 18, o mesmo piso do parâmetro editável
        `dias_reinseminacao_min`). Sem essa janela, uma segunda IA lançada 1-2
        dias depois da primeira — a mesma cobertura relançada, ou erro de
        data — provaria "a anterior falhou" sem nenhum cio de verdade ter
        acontecido. Ver `tem_reinseminacao_posterior`.

        CONTA_EM_TAXA(s,hoje) <-> ( data_servico(s) <= hoje - 28 )
                                  | RESULTADO_CONHECIDO(s,hoje)

        Serviço dos últimos 27 dias não entra em taxa nenhuma — salvo quando o
        desfecho JÁ é conhecido (DG negativo, ou nova IA em cio de repasse, que
        prova que a anterior falhou; nesse caso o animal não é "inseminado
        aguardando DG").

        A recíproca NÃO vale: serviço com 28 dias ou mais entra em taxa mesmo
        SEM nenhum DG lançado, e entra como fracasso. É deliberado — a fazenda
        que não lança diagnóstico tem que ver a concepção cair — mas contradiz
        o nome do campo `servicos_com_resultado`, que conta esses também.

        R7 vale para o NUMERADOR de prenhez (PREG). O denominador (PG ELIG) não
        tem essa porta: enquanto a janela de DG do ciclo não fechar, PG ELIG já
        está cheio e PREG ainda não. Por isso `ResultadoCiclo` carrega
        `janela_dg_completa` — sem respeitar essa flag, o ciclo mais recente
        aparece sempre como fracasso.

    R8  Taxa de serviço(C)   = |BRED(C)| / |BR ELIG(C)|
        Taxa de prenhez(C)   = |PREG(C)| / |PG ELIG(C)|
        Taxa de concepção(C) = |PREG(C)| / |serviços de C com resultado conhecido|

    R9  Taxa de prenhez  =/=  Taxa de serviço × Taxa de concepção

        Denominadores diferentes. Há um teste-sentinela que falha se alguém
        reintroduzir o atalho (ver tests/test_programa_reprodutivo.py).

## Reconstrução histórica de `a_descartar` — RESOLVIDO

`Animal.a_descartar` era booleano SEM data: a marcação feita hoje retroagia
para todo o período avaliado, e a vaca sumia de TODOS os ciclos passados,
inclusive dos denominadores em que estava legitimamente ativa. Isso encolhia o
BR ELIG histórico justamente nas vacas problema e INFLAVA a taxa de serviço do
passado — uma versão atenuada do defeito nº 2 que este módulo existe para
corrigir, e tanto pior quanto mais antigo o ciclo.

A coluna `Animal.a_descartar_em` fechou isso: `descartada_em(perfil, d)`
responde "a marcação já valia nesta data?", exatamente como `baixada_em` faz
com `data_baixa`.

Fica um resíduo conhecido, e é deliberado: os animais marcados ANTES da coluna
existir têm `a_descartar_em = NULL` e seguem tratados como marcados desde
sempre — o comportamento antigo. Não houve backfill porque inventar uma data
produziria um histórico plausível e falso, indistinguível de um retroativo
real. Ou seja: nenhum número muda no dia do deploy; a precisão histórica passa
a valer para as marcações feitas de agora em diante, e o resíduo se dissolve
com o tempo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fazenda.rules.estado_reprodutivo import (
    APTA as _E_APTA,
    ATRASADA as _E_ATRASADA,
    EM_PROTOCOLO as _E_EM_PROTOCOLO,
    GESTANTE as _E_GESTANTE,
    INSEMINADA as _E_INSEMINADA,
    NAO_APTA as _E_NAO_APTA,
    PEV as _E_PEV,
    VAZIA as _E_VAZIA,
    classificar_animal,
)

# Situação no programa reprodutivo (R1/R2) — não confundir com o estado
# reprodutivo de `estado_reprodutivo.py`, que é mais granular.
ATIVA = "ativa"
SUSPENSA = "suspensa"
INATIVA = "inativa"

# Motivos de não estar apta — o que a tela mostra no drill-down.
MOTIVO_A_DESCARTAR = "a_descartar"
MOTIVO_BAIXADA = "baixada"
MOTIVO_IMPUBERE = "impubere"
MOTIVO_DENTRO_PEV = "dentro_pev"
MOTIVO_GESTANTE = "gestante"
# Salvaguarda: nenhum dos estados que `classificar_animal` devolve hoje cai
# aqui — os que ficam de fora de ESTADOS_APTOS (NAO_APTA/PEV/GESTANTE) já têm
# branch explícito acima, e os demais estão todos dentro do conjunto. Ou seja:
# esta constante é inalcançável ENQUANTO os dois lados continuarem
# sincronizados manualmente — e é exatamente esse acoplamento implícito o
# problema. Se `estado_reprodutivo` ganhar um estado novo sem que alguém
# lembre de somá-lo a ESTADOS_APTOS (ou de dar um branch explícito aqui), a
# linha final de `estado_no_dia` devolvia `apta=False, motivo=None` — e o
# drill-down da tela, que mostra `motivo`, ficava em branco bem no animal que
# o usuário mais queria entender. Agora sempre há um motivo.
MOTIVO_ESTADO_NAO_MAPEADO = "estado_nao_mapeado"

# Estados de `estado_reprodutivo` que satisfazem R4 (apta no dia).
#
# INSEMINADA entra: é o "inseminada aguardando diagnóstico" da regra.
# EM_PROTOCOLO entra: está em D0–D11 e ainda sem serviço, ou seja, VAZIA e
#   disponível — o protocolo não a tira do denominador, só descreve o manejo.
# ATRASADA entra, e é o caso mais importante de todos: é exatamente a vaca que
#   deveria ter sido inseminada e não foi. Tirá-la do denominador é o erro que
#   inflava a taxa de serviço.
ESTADOS_APTOS = frozenset({_E_APTA, _E_ATRASADA, _E_EM_PROTOCOLO, _E_INSEMINADA, _E_VAZIA})

_POSITIVO = "POSITIVO"
_NEGATIVO = "NEGATIVO"

DIAS_CICLO_PADRAO = 21
DIAS_MINIMOS_PADRAO = 11
DIAS_RESULTADO_CONHECIDO_PADRAO = 28
# Janela mínima para uma segunda IA valer como "cio de repasse" (ver
# `tem_reinseminacao_posterior`). Mesmo valor e mesma origem do parâmetro
# editável `dias_reinseminacao_min` de `fazenda.rules.parametros` (grupo
# "reinseminacao_cio"): o ciclo estral da vaca gira em torno de 21 dias, e 18
# é o piso que a fazenda já usa para reconhecer um cio CURTO como legítimo,
# não uma repetição de lançamento. Este módulo é regra pura e não importa
# `parametros` (ver o docstring do módulo); quem chama a partir de uma fazenda
# real lê `dias_reinseminacao_min()` e passa como `dias_minimos_repasse`, do
# mesmo jeito que já faz com `pev_dias` — ver `_parametros_ciclos` em
# rules/indicadores.py e os dois routers. Este número é só o piso de
# segurança de quem chama sem configurar nada.
DIAS_MINIMOS_REPASSE_PADRAO = 18


def _d(valor: Any) -> date | None:
    """Aceita date ou 'AAAA-MM-DD' — os dois formatos circulam no projeto."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _get(obj: Any, campo: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def _diag(servico: Any) -> str:
    return (_get(servico, "diagnostico") or "").strip().upper()


# ---------------------------------------------------------------------------
# Ciclos de 21 dias — âncora configurável (início OU fim)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Ciclo:
    """Uma janela fechada de `dias` dias. `inicio` e `fim` são inclusivos, de
    forma que um ciclo de 21 dias tem exatamente 21 datas dentro."""

    indice: int
    inicio: date
    fim: date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    def contem(self, d: date) -> bool:
        return self.inicio <= d <= self.fim

    def datas(self) -> list[date]:
        return [self.inicio + timedelta(days=i) for i in range(self.dias)]


def ciclos_21_dias(
    ancora: date, modo: str = "inicio", n_ciclos: int = 12, dias: int = DIAS_CICLO_PADRAO,
) -> list[Ciclo]:
    """Série de ciclos consecutivos ancorada numa data escolhida pelo usuário.

    Substitui a ancoragem FECHADA que existia antes (o ciclo só podia começar
    no D11 de um protocolo IATF ou numa inseminação, e só corria para frente).

      - `modo="inicio"` → a âncora é o primeiro dia do 1º ciclo e a série corre
        PARA FRENTE.
      - `modo="fim"` → a âncora é o último dia do ÚLTIMO ciclo e a série corre
        PARA TRÁS (o resultado continua devolvido em ordem cronológica).

    Devolve sempre em ordem cronológica, com `indice` 1..n.
    """
    if modo not in ("inicio", "fim"):
        raise ValueError('modo deve ser "inicio" ou "fim"')
    if n_ciclos < 1:
        raise ValueError("n_ciclos deve ser >= 1")
    if dias < 1:
        raise ValueError("dias deve ser >= 1")

    if modo == "inicio":
        primeiro_inicio = ancora
    else:
        # A âncora é o FIM do último ciclo: recua (n_ciclos * dias) - 1 dias.
        primeiro_inicio = ancora - timedelta(days=n_ciclos * dias - 1)

    return [
        Ciclo(
            indice=i + 1,
            inicio=primeiro_inicio + timedelta(days=i * dias),
            fim=primeiro_inicio + timedelta(days=(i + 1) * dias - 1),
        )
        for i in range(n_ciclos)
    ]


# ---------------------------------------------------------------------------
# Perfil do animal — registros pré-ordenados uma vez só
# ---------------------------------------------------------------------------
@dataclass
class PerfilAnimal:
    """Tudo que é preciso para reconstruir o estado do animal em QUALQUER data,
    já normalizado. Montar isto uma vez por animal evita reordenar as mesmas
    listas a cada um dos 21 dias de cada ciclo."""

    numero: str
    partos: list[Any] = field(default_factory=list)
    servicos: list[Any] = field(default_factory=list)
    aplicacoes_iatf: list[Any] = field(default_factory=list)
    eh_vaca: bool = False
    data_nasc: date | None = None
    peso_kg: float | None = None
    raca: str | None = None
    a_descartar: bool = False
    # Data em que a marcação de descarte passou a valer — é ela que permite
    # reconstruir o passado (ver `descartada_em`). `None` com `a_descartar=True`
    # é registro anterior à coluna, sem backfill de propósito: tratado como
    # marcação já vigente.
    a_descartar_em: date | None = None
    ativo: bool = True
    data_baixa: date | None = None
    categoria: str | None = None  # "vaca" | "novilha" — para o filtro da tela

    def idade_dias_em(self, d: date) -> int | None:
        return (d - self.data_nasc).days if self.data_nasc else None


def montar_perfil(
    animal: Any, *, partos: list[Any], servicos: list[Any], aplicacoes_iatf: list[Any],
) -> PerfilAnimal:
    """Normaliza um `Animal` + seus registros num `PerfilAnimal`.

    `eh_vaca` deriva EXCLUSIVAMENTE de ter parto registrado. O fallback pelo
    texto da categoria ("vaca" em `categoria_abrev`/`categoria_completa`) foi
    removido por dois motivos:

    1. **Dois critérios divergiam dentro do mesmo painel.** Os cards e o donut
       usam `vacas_nums` (`rules/indicadores.py`), que é só parto; os medidores
       usavam este `eh_vaca`, que aceitava o texto. Uma fêmea com categoria
       "Vaca" e sem parto importado caía no grupo novilha de um painel e no
       grupo vaca do outro.
    2. **O texto sozinho abria um buraco pior.** `eh_vaca=True` sem parto deixa
       `del_dias = None` em `estado_reprodutivo.classificar_animal`; o teste de
       ATRASADA não dispara e o animal volta APTA todo santo dia, entrando no
       BR ELIG de vacas indefinidamente e inflando o denominador. Derivar de
       parto fecha isso por construção: `eh_vaca` passa a implicar que existe
       um parto, logo existe DEL.

    Efeito colateral aceito: uma vaca real cujo histórico de partos não foi
    importado é tratada como novilha. É a resposta honesta — sem parto não há
    DEL, e sem DEL não dá para dizer se ela está no PEV ou atrasada.
    """
    tem_parto = any(_d(_get(p, "data_parto")) for p in partos)
    eh_vaca = tem_parto
    return PerfilAnimal(
        numero=_get(animal, "numero"),
        partos=list(partos),
        servicos=list(servicos),
        aplicacoes_iatf=list(aplicacoes_iatf),
        eh_vaca=eh_vaca,
        data_nasc=_d(_get(animal, "data_nasc")),
        peso_kg=_get(animal, "peso_kg"),
        raca=_get(animal, "raca"),
        a_descartar=bool(_get(animal, "a_descartar")),
        a_descartar_em=_d(_get(animal, "a_descartar_em")),
        ativo=_get(animal, "ativo") is not False,
        data_baixa=_d(_get(animal, "data_baixa")),
        categoria="vaca" if eh_vaca else "novilha",
    )


# ---------------------------------------------------------------------------
# Estado num dia (R1–R4)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EstadoDia:
    data: date
    situacao: str          # ATIVA | SUSPENSA | INATIVA  (R1/R2)
    apta: bool             # R4
    motivo: str | None     # por que não está apta
    estado_reprodutivo: str  # o estado granular de estado_reprodutivo.py


def baixada_em(perfil: PerfilAnimal, d: date) -> bool:
    """R1 — o animal já tinha saído do rebanho nesta data?

    `data_baixa` é datada, então a baixa é reconstruída corretamente no
    passado. `ativo=False` sem data de baixa é tratado como baixa já vigente
    (é o que o dado permite afirmar)."""
    if perfil.data_baixa is not None:
        return d >= perfil.data_baixa
    return not perfil.ativo


def estado_no_dia(
    perfil: PerfilAnimal, d: date, *, pev_dias: int, del_max_1o_servico: int | None = None,
    idade_apta_dias: int | None = None, peso_apta_kg: float | None = None,
    idade_atraso_dias: int | None = None,
) -> EstadoDia:
    """Situação do animal no programa reprodutivo NA DATA `d` (R1–R4).

    Delega a classificação granular a `estado_reprodutivo.classificar_animal`,
    que já reconstrói o estado numa data arbitrária (filtra por `data <= hoje`)
    — em vez de reimplementar a matriz de exclusão, que tem ordem própria e é
    fonte única de verdade das listas de Rebanho.
    """
    # R1 — portas de saída do programa, avaliadas antes de tudo.
    if baixada_em(perfil, d):
        return EstadoDia(d, INATIVA, False, MOTIVO_BAIXADA, _E_NAO_APTA)
    if descartada_em(perfil, d):
        return EstadoDia(d, INATIVA, False, MOTIVO_A_DESCARTAR, _E_NAO_APTA)

    classificacao = classificar_animal(
        perfil.numero,
        hoje=d,
        partos=perfil.partos,
        servicos=perfil.servicos,
        aplicacoes_iatf=perfil.aplicacoes_iatf,
        pev_dias=pev_dias,
        del_max_1o_servico=del_max_1o_servico,
        eh_vaca=perfil.eh_vaca,
        idade_dias=perfil.idade_dias_em(d),
        peso_kg=perfil.peso_kg,
        idade_apta_dias=idade_apta_dias,
        idade_atraso_dias=idade_atraso_dias,
        peso_apta_kg=peso_apta_kg,
        raca=perfil.raca,
    )
    estado = classificacao["estado"]

    # R1 — novilha que ainda não atingiu idade/peso não entrou no programa.
    if estado == _E_NAO_APTA:
        return EstadoDia(d, INATIVA, False, MOTIVO_IMPUBERE, estado)

    # R2 — suspensões temporárias: continua no programa, não conta como apta.
    if estado == _E_PEV:
        return EstadoDia(d, SUSPENSA, False, MOTIVO_DENTRO_PEV, estado)
    if estado == _E_GESTANTE:
        return EstadoDia(d, SUSPENSA, False, MOTIVO_GESTANTE, estado)

    # R4 — vazia XOR inseminada-sem-DG, ambas já disponíveis (pós-PEV).
    #
    # `apta` sai de ESTADOS_APTOS, mas `motivo` NÃO pode sair de "None por
    # construção": um estado que escape de ESTADOS_APTOS sem ter passado por um
    # dos branches explícitos acima cairia aqui com `apta=False` e nenhuma
    # explicação — ver MOTIVO_ESTADO_NAO_MAPEADO.
    apta = estado in ESTADOS_APTOS
    motivo = None if apta else MOTIVO_ESTADO_NAO_MAPEADO
    return EstadoDia(d, ATIVA, apta, motivo, estado)


def descartada_em(perfil: PerfilAnimal, d: date) -> bool:
    """R1 — a marcação de descarte já valia nesta data?

    Espelho de `baixada_em`, e pela mesma razão: sem data, a marcação feita
    hoje retroagia para TODOS os ciclos passados e a vaca sumia até dos
    denominadores em que estava legitimamente ativa — encolhendo o BR ELIG
    histórico justamente nas vacas problema, e inflando a taxa de serviço do
    passado.

    `a_descartar=True` SEM data é tratado como marcação já vigente: é o que o
    dado permite afirmar, e é o mesmo critério que `baixada_em` usa para
    `ativo=False` sem `data_baixa`. São os registros anteriores à coluna
    `a_descartar_em`, deixados sem backfill de propósito — inventar uma data
    produziria um histórico plausível e falso, indistinguível de um retroativo
    real.

    NÃO lê `Animal.descarte_previsto_em`, e isso é deliberado. Aquela coluna é
    a data em que se PRETENDE tirar o animal do rebanho (a boiada, o caminhão);
    esta função responde outra pergunta: a partir de quando o animal saiu do
    PROGRAMA REPRODUTIVO. Quem decide descartar para de inseminar naquele
    momento — a saída reprodutiva é a decisão, não o transporte. Ler a previsão
    aqui manteria no denominador uma vaca que ninguém mais vai inseminar, e
    inflaria a taxa de serviço exatamente como fazia a ausência de data.

    Há teste sentinela travando isso: preencher a previsão não pode mover
    nenhuma taxa do painel.
    """
    if not perfil.a_descartar:
        return False
    if perfil.a_descartar_em is not None:
        return d >= perfil.a_descartar_em
    return True


def _perfil_sem_servicos_do_ciclo(perfil: PerfilAnimal, ciclo: Ciclo) -> PerfilAnimal:
    """Cópia do perfil sem os serviços lançados DENTRO do ciclo.

    Sutileza central do BR ELIG, e a que é fácil errar: a pergunta que a
    elegibilidade responde é *"este animal estava disponível para ser
    inseminado durante este ciclo?"* — não *"como ele terminou o ciclo?"*.

    Sem este recorte, a vaca inseminada no dia 5 do ciclo que CONCEBEU vira
    gestante do dia 5 em diante, acumula só 4 dias aptos e cai fora do BR ELIG.
    Ou seja: seria excluída do denominador justamente por ter dado certo — e,
    pior, sairia também do numerador, sumindo dos dois lados da conta. A
    prenhez originada de um serviço DO PRÓPRIO ciclo é o desfecho que se está
    medindo, não uma desqualificação.

    Prenhez vinda de ciclo ANTERIOR continua valendo e segue tirando o animal
    do denominador, como manda a R4 — essa sim é uma vaca que não estava
    disponível.
    """
    from dataclasses import replace

    fora_do_ciclo = [
        s for s in perfil.servicos
        if (ds := _d(_get(s, "data_servico"))) is None or not ciclo.contem(ds)
    ]
    if len(fora_do_ciclo) == len(perfil.servicos):
        return perfil
    return replace(perfil, servicos=fora_do_ciclo)


def dias_aptos(
    perfil: PerfilAnimal, ciclo: Ciclo, *, pev_dias: int,
    ignorar_servicos_do_ciclo: bool = True, **kwargs: Any,
) -> int:
    """Quantos dos dias do ciclo o animal esteve apto (R4, dia a dia).

    `ignorar_servicos_do_ciclo=True` (padrão) é o que se quer para elegibilidade
    — ver `_perfil_sem_servicos_do_ciclo`. Passe `False` para medir aptidão
    factual dia a dia (ex.: um gráfico de disponibilidade do rebanho).
    """
    alvo = _perfil_sem_servicos_do_ciclo(perfil, ciclo) if ignorar_servicos_do_ciclo else perfil
    return sum(
        1 for d in ciclo.datas()
        if estado_no_dia(alvo, d, pev_dias=pev_dias, **kwargs).apta
    )


# ---------------------------------------------------------------------------
# Elegibilidade (R5/R6) — BR ELIG e PG ELIG
# ---------------------------------------------------------------------------
def elegivel_ia(
    perfil: PerfilAnimal, ciclo: Ciclo, *, pev_dias: int,
    dias_minimos: int = DIAS_MINIMOS_PADRAO, **kwargs: Any,
) -> bool:
    """R5 (BR ELIG) — participou de pelo menos metade do ciclo estando apta.

    Não exige estar apta os 21 dias: exige `dias_minimos` (11) dias aptos.
    """
    return dias_aptos(perfil, ciclo, pev_dias=pev_dias, **kwargs) >= dias_minimos


def elegivel_prenhez(
    perfil: PerfilAnimal, ciclo: Ciclo, *, pev_dias: int,
    dias_minimos: int = DIAS_MINIMOS_PADRAO, dias_janela_dg: int = DIAS_CICLO_PADRAO,
    **kwargs: Any,
) -> bool:
    """R6 (PG ELIG) — elegível para IA no ciclo E ainda presente no fim da
    janela de avaliação de prenhez (o ciclo seguinte).

    É esta segunda condição que faz PG ELIG < BR ELIG: a vaca descartada
    durante a janela de avaliação estava no BR ELIG e sai daqui.
    """
    if not elegivel_ia(perfil, ciclo, pev_dias=pev_dias, dias_minimos=dias_minimos, **kwargs):
        return False
    fim_janela = ciclo.fim + timedelta(days=dias_janela_dg)
    return not baixada_em(perfil, fim_janela) and not descartada_em(perfil, fim_janela)


# ---------------------------------------------------------------------------
# Resultado conhecido (R7) — a regra dos 28 dias
# ---------------------------------------------------------------------------
def tem_reinseminacao_posterior(
    perfil: PerfilAnimal, servico: Any, *,
    dias_minimos_repasse: int = DIAS_MINIMOS_REPASSE_PADRAO,
) -> bool:
    """Houve nova inseminação depois desta, na mesma lactação, e longe o
    suficiente para valer como "reinseminação em cio de repasse"? A nova IA
    prova que a anterior não pegou, então o desfecho da anterior É conhecido
    mesmo sem DG lançado.

    `dias_minimos_repasse` é a guarda que faltava: sem ela, uma segunda IA um
    ou dois dias depois da primeira (a mesma cobertura relançada, ou um erro de
    digitação de data) também contava como "prova de que a anterior falhou" —
    o ciclo estral de uma vaca gira em torno de 21 dias; nada biológico
    acontece entre o dia 1 e o dia 2. O padrão (ver
    `DIAS_MINIMOS_REPASSE_PADRAO`) reaproveita o número do parâmetro editável
    `dias_reinseminacao_min` da fazenda, para não inventar um segundo critério
    de "cio curto" divergente do que a tela de Reprodução já usa."""
    ds = _d(_get(servico, "data_servico"))
    if ds is None:
        return False
    ultimo_parto = max(
        (p for p in (_d(_get(x, "data_parto")) for x in perfil.partos) if p), default=None
    )
    for outro in perfil.servicos:
        d_outro = _d(_get(outro, "data_servico"))
        if d_outro is None or d_outro <= ds:
            continue
        if ultimo_parto is not None and d_outro <= ultimo_parto:
            continue  # lactação anterior, já resolvida pelo parto
        if (d_outro - ds).days < dias_minimos_repasse:
            continue  # perto demais para ser cio de repasse — provável duplicidade de lançamento
        return True
    return False


def resultado_conhecido(servico: Any, *, servico_posterior: bool = False) -> bool:
    """R7 — o desfecho desta inseminação já é conhecido?

    Verdadeiro quando há DG lançado (positivo ou negativo), quando houve perda
    de prenhez registrada, ou quando uma nova IA em cio de repasse já provou
    que esta não pegou.
    """
    if _diag(servico) in (_POSITIVO, _NEGATIVO):
        return True
    if _d(_get(servico, "data_perda_prenhez")) is not None:
        return True
    return servico_posterior


def conta_em_taxa(
    servico: Any, hoje: date, *, servico_posterior: bool = False,
    dias: int = DIAS_RESULTADO_CONHECIDO_PADRAO,
) -> bool:
    """R7 — este serviço pode entrar no cálculo de qualquer taxa?

    Serviço dos últimos `dias`-1 dias (padrão: 27) fica de fora, porque ainda
    não deu tempo de saber se pegou — a não ser que o desfecho já seja
    conhecido. Sem esta janela, toda taxa fica artificialmente pessimista nos
    dias recentes: as IAs recentes entram no denominador da concepção sem
    nenhuma chance de já terem virado prenhez.
    """
    ds = _d(_get(servico, "data_servico"))
    if ds is None:
        return False
    if ds <= hoje - timedelta(days=dias):
        return True
    return resultado_conhecido(servico, servico_posterior=servico_posterior)


# ---------------------------------------------------------------------------
# Métricas do ciclo (R8) — o BREDSUM\E
# ---------------------------------------------------------------------------
@dataclass
class ResultadoCiclo:
    ciclo: Ciclo
    br_elig: list[str]
    bred: list[str]
    pg_elig: list[str]
    preg: list[str]
    # Nome herdado, e ele mente um pouco: conta também o serviço com 28+ dias
    # que NINGUÉM diagnosticou — que entra como fracasso na concepção. Ver R7.
    servicos_com_resultado: int
    # False enquanto não passaram `dias_resultado` dias do fim do ciclo. Quem
    # exibe a taxa de prenhez tem que respeitar: com a janela aberta, o
    # denominador já está cheio e o numerador não. Ver R7 e `taxa_prenhez`.
    janela_dg_completa: bool = True

    def _pct(self, num: int, den: int) -> float | None:
        return round(100 * num / den, 1) if den else None

    @property
    def taxa_servico(self) -> float | None:
        """R8 — BRED / BR ELIG."""
        return self._pct(len(self.bred), len(self.br_elig))

    @property
    def taxa_prenhez(self) -> float | None:
        """R8 — PREG / PG ELIG. NÃO é serviço × concepção (ver R9).

        ATENÇÃO ao ler esta taxa quando `janela_dg_completa` é False: o
        denominador (PG ELIG) já está cheio, mas o numerador (PREG) exige
        `conta_em_taxa`, ou seja, 28 dias ou desfecho conhecido. Enquanto a
        janela não fecha, a taxa está estruturalmente subestimada — não é
        piora de manejo. Quem exibe esta taxa tem que respeitar a flag.
        """
        return self._pct(len(self.preg), len(self.pg_elig))

    @property
    def taxa_concepcao(self) -> float | None:
        """R8 — PREG / serviços do ciclo com resultado conhecido."""
        return self._pct(len(self.preg), self.servicos_com_resultado)

    def para_dict(self) -> dict:
        return {
            "ciclo": self.ciclo.indice,
            "inicio": self.ciclo.inicio.isoformat(),
            "fim": self.ciclo.fim.isoformat(),
            "br_elig": len(self.br_elig),
            "bred": len(self.bred),
            "taxa_servico": self.taxa_servico,
            "pg_elig": len(self.pg_elig),
            "preg": len(self.preg),
            "taxa_prenhez": self.taxa_prenhez,
            "taxa_concepcao": self.taxa_concepcao,
            "servicos_com_resultado": self.servicos_com_resultado,
            "janela_dg_completa": self.janela_dg_completa,
            "animais": {
                "br_elig": sorted(self.br_elig),
                "bred": sorted(self.bred),
                "pg_elig": sorted(self.pg_elig),
                "preg": sorted(self.preg),
            },
        }


def calcular_ciclo(
    perfis: list[PerfilAnimal], ciclo: Ciclo, hoje: date, *, pev_dias: int,
    dias_minimos: int = DIAS_MINIMOS_PADRAO,
    dias_resultado: int = DIAS_RESULTADO_CONHECIDO_PADRAO,
    dias_janela_dg: int = DIAS_CICLO_PADRAO,
    dias_minimos_repasse: int = DIAS_MINIMOS_REPASSE_PADRAO,
    **kwargs: Any,
) -> ResultadoCiclo:
    """Um ciclo do BREDSUM\\E: BR ELIG → BRED → PG ELIG → PREG.

    O denominador é o REBANHO elegível, não os animais que por acaso têm um
    serviço lançado — é a correção central em relação ao cálculo anterior.

    Devolve também `janela_dg_completa`: se ainda não passaram `dias_resultado`
    dias desde o fim do ciclo, a última IA do ciclo ainda não teve tempo de
    virar prenhez, o PREG está incompleto e a taxa de prenhez sai subestimada.
    A flag existe para a tela não comparar esse ciclo com a meta. Ver a nota em
    `ResultadoCiclo.taxa_prenhez`.

    `dias_janela_dg` e `dias_minimos_repasse` são declarados aqui DE PROPÓSITO —
    não deixados para dentro de `**kwargs`. `elegivel_ia` (BR ELIG) não conhece
    nenhum dos dois; se eles vazassem pelo `**kwargs` compartilhado com
    `elegivel_prenhez`, cairiam na cadeia `elegivel_ia` → `dias_aptos` →
    `estado_no_dia`, que não tem `**kwargs` nenhum, e explodiam em `TypeError`.
    Declará-los aqui os retira do saco genérico e os entrega só a quem sabe o
    que fazer com eles.
    """
    janela_dg_completa = ciclo.fim + timedelta(days=dias_resultado) <= hoje

    br_elig: list[str] = []
    bred: list[str] = []
    pg_elig: list[str] = []
    preg: list[str] = []
    servicos_com_resultado = 0

    for perfil in perfis:
        if not elegivel_ia(perfil, ciclo, pev_dias=pev_dias, dias_minimos=dias_minimos, **kwargs):
            continue
        br_elig.append(perfil.numero)

        elegivel_pg = elegivel_prenhez(
            perfil, ciclo, pev_dias=pev_dias, dias_minimos=dias_minimos,
            dias_janela_dg=dias_janela_dg, **kwargs
        )
        if elegivel_pg:
            pg_elig.append(perfil.numero)

        # Serviços DESTE animal dentro da janela do ciclo.
        no_ciclo = [
            s for s in perfil.servicos
            if (ds := _d(_get(s, "data_servico"))) is not None and ciclo.contem(ds)
        ]
        if not no_ciclo:
            continue
        bred.append(perfil.numero)

        for s in no_ciclo:
            posterior = tem_reinseminacao_posterior(
                perfil, s, dias_minimos_repasse=dias_minimos_repasse
            )
            if conta_em_taxa(s, hoje, servico_posterior=posterior, dias=dias_resultado):
                servicos_com_resultado += 1

        # PREG: concebeu a partir de um serviço deste ciclo, com o desfecho já
        # conhecido, e continua elegível para prenhez.
        concebeu = any(
            _diag(s) == _POSITIVO and _d(_get(s, "data_perda_prenhez")) is None
            and conta_em_taxa(
                s, hoje,
                servico_posterior=tem_reinseminacao_posterior(
                    perfil, s, dias_minimos_repasse=dias_minimos_repasse
                ),
                dias=dias_resultado,
            )
            for s in no_ciclo
        )
        if concebeu and elegivel_pg:
            preg.append(perfil.numero)

    return ResultadoCiclo(
        ciclo, br_elig, bred, pg_elig, preg, servicos_com_resultado, janela_dg_completa
    )


def calcular_series(
    perfis: list[PerfilAnimal], ciclos: list[Ciclo], hoje: date, *, pev_dias: int, **kwargs: Any,
) -> list[ResultadoCiclo]:
    """Aplica `calcular_ciclo` a uma série inteira de ciclos."""
    return [calcular_ciclo(perfis, c, hoje, pev_dias=pev_dias, **kwargs) for c in ciclos]
