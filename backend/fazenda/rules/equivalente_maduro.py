"""
Equivalente maduro (EM) — ver `docs/equivalente-maduro-proposta.md` §"Redesign
por vaca" para o histórico da decisão (a versão original deste módulo, com
fator calibrado no rebanho e mínimo de 20 lactações por classe, foi
substituída pelo design abaixo; ficou registrada no documento, e a máquina de
calibração continua neste arquivo — só que demovida a painel de aferição, ver
seção 2).

## 1. Padronização por vaca, fatores fixos de tabela (Holandês)

Antes, o fator de ajuste era calibrado nas lactações ENCERRADAS do próprio
rebanho, e uma classe inteira ficava "sem base" abaixo de um mínimo de
lactações (20 para publicar, 50 para confiança alta) — na prática isso
significava que uma novilha de 1ª cria não recebia número nenhum enquanto o
rebanho não acumulasse histórico suficiente na classe madura.

Decisão aprovada: os animais são padronizados como raça HOLANDÊS,
independente da raça/grau de sangue cadastrado do animal, com fatores FIXOS
de tabela — não mais calibrados no rebanho:

    1ª cria (classe 1): 1,22
    2ª cria (classe 2): 1,08
    Madura  (classe 3+): 1,00

Isso remove a dependência de massa de dados: qualquer vaca com pelo menos 2
controles utilizáveis na lactação atual recebe o trio completo, inclusive
uma primípara de DEL 100 num rebanho pequeno.

[risco] Os valores 1,22/1,08/1,00 e a curva de referência do trecho final
(`rules/curva_lactacao_referencia.py`) vêm de conhecimento treinado sobre o
padrão de curva/maturidade de Holandês, NÃO de tabela CDCB/ICAR conferida ao
vivo (rede bloqueada neste ambiente). São constantes editáveis
(`FATOR_HOLANDES` abaixo) — não normas verificadas. O painel de aferição
(seção 2) existe justamente para o usuário comparar este número de tabela
com o que o próprio rebanho vem mostrando, e ajustar `FATOR_HOLANDES` se a
divergência for grande e sustentada.

## 2. Painel de aferição — a máquina antiga, demovida

`calcular_fatores` (a calibração por rebanho) continua existindo, mas não
alimenta mais o trio principal — vira dado de um painel de CONFERÊNCIA:
fator observado no próprio rebanho × fator da tabela fixa × divergência
percentual, por classe. Puramente informativo: nunca bloqueia nem muda a
conta do trio (`montar_trio`). `montar_painel_afericao` monta essa
comparação.

## 3. Confiança — não mais tamanho de amostra do rebanho, e sim medição

Antes, "confiança" media quantas lactações encerradas sustentavam o FATOR da
classe (tamanho de amostra do rebanho). Definição nova, por vaca:

    confiança = kg_medido / kg_projetado

isto é, que fração do total de 305 dias projetado é leite REALMENTE medido
NESTA vaca (trapézios entre dois controles reais — `Producao305.
producao_medida_kg`), e não extrapolação para nenhum dos dois lados (nem a
ponta inicial do parto ao 1º controle, nem a ponta final projetada pela
curva de referência). Cai com o DEL (mais lactação pela frente, mais
projeção); sobe com o controle em dia (último controle perto de hoje, pouco
trecho para projetar).

Quatro níveis (pontos de corte redondos, calibrados para bater com os 7
exemplos do mockup aprovado: 23%→baixa, 7%→muito baixa, 66%→média, 81%→alta,
89%→alta, 42%→baixa, 58%→média):

    < 15%           muito baixa
    15% a < 45%     baixa
    45% a < 75%     média
    >= 75%          alta

Classe madura (fator 1,00 por definição) também recebe confiança — o número
"produzirá" dela é o mesmo "produz hoje", mas a fração medida/projetada
ainda diz o quanto esse "produz hoje" em si é medição ou projeção.

## 4. `sem_base` só por duas causas agora

Removido: "classe sem lactações suficientes para ter fator" (a causa mais
comum antes, some com o mínimo de 20). Sobra:

  - produção de 305 dias não calculável (menos de 2 controles utilizáveis);
  - ordem de parto desconhecida (parto sem `ordem_parto` gravada, ou sem
    parto algum no histórico do animal) — não dá para escolher fator sem
    saber a classe.

Tudo aqui é puro — sem Session — igual a `rules/ordem_parto_historica.py` e
`rules/producao_305.py`. A montagem a partir do banco fica no router.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from fazenda.rules.producao_305 import Producao305

CLASSE_MADURA = 3

# [risco] Fatores fixos de tabela — Holandês, conhecimento treinado, NÃO
# conferido ao vivo contra CDCB/ICAR (rede bloqueada neste ambiente).
# Editáveis; o painel de aferição (montar_painel_afericao) compara este
# número com o que o próprio rebanho observa.
FATOR_HOLANDES: dict[int, float] = {1: 1.22, 2: 1.08, CLASSE_MADURA: 1.00}

# Pontos de corte de confiança (fração kg_medido/kg_projetado) — ver §3.
CONFIANCA_MUITO_BAIXA_ATE = 0.15
CONFIANCA_BAIXA_ATE = 0.45
CONFIANCA_MEDIA_ATE = 0.75

# Machinery de calibração no rebanho — só alimenta o painel de aferição
# (§2), não o trio principal. Mantidos os mesmos guarda-corpos de bom senso
# de antes (não são estatística formal, são sugestão de
# `docs/equivalente-maduro-proposta.md` §6.2): 20 lactações para publicar um
# fator observado, 50 para confiança alta nesse fator observado.
MINIMO_PUBLICAVEL = 20
MINIMO_CONFIANCA_ALTA = 50


def classe_de_ordem(ordem_parto: int | None) -> int | None:
    """1, 2 ou 3 (= "3ª ou mais"). `None` quando a ordem de parto não é
    conhecida — não dá para classificar o que não se sabe."""
    if ordem_parto is None or ordem_parto < 1:
        return None
    return ordem_parto if ordem_parto < CLASSE_MADURA else CLASSE_MADURA


def nivel_confianca(fracao_medida: float | None) -> str | None:
    """Fração `kg_medido/kg_projetado` -> um dos 4 níveis do mockup. `None`
    quando a fração não é calculável (ex.: projeção zero ou negativa)."""
    if fracao_medida is None:
        return None
    if fracao_medida < CONFIANCA_MUITO_BAIXA_ATE:
        return "muito baixa"
    if fracao_medida < CONFIANCA_BAIXA_ATE:
        return "baixa"
    if fracao_medida < CONFIANCA_MEDIA_ATE:
        return "média"
    return "alta"


@dataclass(frozen=True)
class AmostraLactacao:
    """Uma lactação ENCERRADA do rebanho, já classificada — a unidade de
    entrada do painel de aferição (§2)."""

    classe: int
    producao_305_kg: float


@dataclass(frozen=True)
class FatorClasse:
    classe: int
    n_lactacoes: int
    media_305_kg: float
    fator: float  # media_305(madura) / media_305(classe) — 1,00 para a própria madura
    desvio_fator: float  # dispersão dos fatores individuais da classe (0,0 para a madura)
    confianca: str  # "baixa" (20-49 lactações) | "ok" (50+)


@dataclass(frozen=True)
class FatoresRebanho:
    por_classe: dict[int, FatorClasse]
    # Motivo textual quando a própria classe madura não tem lactações
    # suficientes — `por_classe` fica vazio nesse caso: sem madura confiável,
    # NENHUMA classe recebe fator OBSERVADO no painel de aferição (não afeta
    # o trio principal, que usa `FATOR_HOLANDES` fixo independentemente).
    sem_base_geral: str | None


def contagem_lactacoes_por_classe(amostras: list[AmostraLactacao]) -> dict[int, int]:
    """Quantas lactações ENCERRADAS (de qualquer animal, todo o histórico)
    cada classe (1, 2, 3+) já acumulou — sempre as 3 classes presentes, 0
    quando a classe não tem nenhuma."""
    contagem = {1: 0, 2: 0, CLASSE_MADURA: 0}
    for a in amostras:
        if a.classe in contagem:
            contagem[a.classe] += 1
    return contagem


def calcular_fatores(amostras: list[AmostraLactacao]) -> FatoresRebanho:
    """Fatores OBSERVADOS no próprio rebanho, calibrados nas lactações
    encerradas passadas em `amostras` — só para o painel de aferição (§2),
    não para o trio principal (esse usa `FATOR_HOLANDES`, fixo)."""
    grupos: dict[int, list[float]] = {}
    for a in amostras:
        grupos.setdefault(a.classe, []).append(a.producao_305_kg)

    madura = grupos.get(CLASSE_MADURA, [])
    if len(madura) < MINIMO_PUBLICAVEL:
        motivo = (
            f"menos de {MINIMO_PUBLICAVEL} lactações encerradas na classe madura (3ª parto ou mais) "
            f"para aferir o fator observado — há {len(madura)}. Sem base madura confiável, nenhuma "
            f"classe tem fator observado no painel de aferição (o fator de tabela continua valendo)."
        )
        return FatoresRebanho(por_classe={}, sem_base_geral=motivo)

    media_madura = sum(madura) / len(madura)
    por_classe: dict[int, FatorClasse] = {}
    for classe in (1, 2, CLASSE_MADURA):
        grupo = grupos.get(classe, [])
        if len(grupo) < MINIMO_PUBLICAVEL:
            continue
        media = sum(grupo) / len(grupo)
        if classe == CLASSE_MADURA:
            fator = 1.0
            desvio_fator = 0.0
        else:
            fator = (media_madura / media) if media else 0.0
            fatores_individuais = [media_madura / p for p in grupo if p > 0]
            desvio_fator = pstdev(fatores_individuais) if len(fatores_individuais) > 1 else 0.0
        confianca = "ok" if len(grupo) >= MINIMO_CONFIANCA_ALTA else "baixa"
        por_classe[classe] = FatorClasse(
            classe=classe, n_lactacoes=len(grupo), media_305_kg=round(media, 1),
            fator=round(fator, 4), desvio_fator=round(desvio_fator, 4), confianca=confianca,
        )
    return FatoresRebanho(por_classe=por_classe, sem_base_geral=None)


@dataclass(frozen=True)
class LinhaAfericao:
    """Uma linha do painel de aferição: fator observado no rebanho ao lado
    do fator fixo de tabela, para o usuário decidir se a tabela (Holandês,
    §1) ainda está representando bem ESTE rebanho."""

    classe: int
    n_lactacoes: int
    fator_observado: float | None  # None quando a classe (ou a madura) não bateu MINIMO_PUBLICAVEL
    fator_tabela: float
    divergencia_pct: float | None  # (observado - tabela) / tabela × 100; None para a madura (sempre 1,00 = 1,00) ou sem observado
    confianca_observado: str | None  # "baixa"/"ok" do FatorClasse — só sobre o OBSERVADO, nada a ver com §3


def montar_painel_afericao(amostras: list[AmostraLactacao]) -> list[LinhaAfericao]:
    """Compara, por classe, o fator observado no rebanho com o fator fixo de
    tabela — puramente informativo (collapsible no front), nunca entra na
    conta do trio principal."""
    fatores = calcular_fatores(amostras)
    contagem = contagem_lactacoes_por_classe(amostras)
    linhas = []
    for classe in (1, 2, CLASSE_MADURA):
        fator_classe = fatores.por_classe.get(classe)
        fator_tabela = FATOR_HOLANDES[classe]
        divergencia = None
        if fator_classe is not None and classe != CLASSE_MADURA and fator_tabela:
            divergencia = round((fator_classe.fator - fator_tabela) / fator_tabela * 100, 1)
        linhas.append(LinhaAfericao(
            classe=classe, n_lactacoes=contagem.get(classe, 0),
            fator_observado=fator_classe.fator if fator_classe else None,
            fator_tabela=fator_tabela, divergencia_pct=divergencia,
            confianca_observado=fator_classe.confianca if fator_classe else None,
        ))
    return linhas


@dataclass(frozen=True)
class TrioEquivalenteMaduro:
    """O par (na verdade trio) que toda tela mostra: produz hoje, produzirá
    na maturidade, diferença — nunca o EM sozinho."""

    ordem_parto: int | None
    classe: int | None
    producao_hoje_kg: float | None
    n_controles: int
    ja_maduro: bool
    producao_maturidade_kg: float | None
    diferenca_kg: float | None
    confianca_nivel: str | None  # "muito baixa" | "baixa" | "média" | "alta" | None (sem_base)
    confianca_fracao: float | None  # kg_medido / kg_projetado, 0..1 — o número cru por trás do nível
    sem_base: bool
    motivo: str | None


def montar_trio(producao_hoje: Producao305, ordem_parto: int | None) -> TrioEquivalenteMaduro:
    """Aplica o fator FIXO de tabela (`FATOR_HOLANDES`) da classe atual à
    produção real de hoje — não depende mais de calibração no rebanho nem de
    mínimo de lactações. `sem_base` cobre só duas causas (ambas com `motivo`
    textual): produção de 305 dias não calculável, ou ordem de parto
    desconhecida. Em nenhum caso o front recebe um número fabricado."""
    classe = classe_de_ordem(ordem_parto)
    hoje_kg = producao_hoje.producao_kg
    n = producao_hoje.n_controles

    fracao_medida = None
    if hoje_kg is not None and hoje_kg > 0 and producao_hoje.producao_medida_kg is not None:
        fracao_medida = min(producao_hoje.producao_medida_kg / hoje_kg, 1.0)
    nivel = nivel_confianca(fracao_medida)

    def _sem_base(motivo: str) -> TrioEquivalenteMaduro:
        return TrioEquivalenteMaduro(
            ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
            ja_maduro=False, producao_maturidade_kg=None, diferenca_kg=None,
            confianca_nivel=None, confianca_fracao=None, sem_base=True, motivo=motivo,
        )

    if hoje_kg is None:
        return _sem_base(producao_hoje.motivo or "produção de 305 dias não calculável")
    if classe is None:
        return _sem_base("ordem de parto desconhecida para este animal nesta data")

    if classe == CLASSE_MADURA:
        return TrioEquivalenteMaduro(
            ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
            ja_maduro=True, producao_maturidade_kg=hoje_kg, diferenca_kg=0.0,
            confianca_nivel=nivel, confianca_fracao=fracao_medida, sem_base=False, motivo=None,
        )

    fator = FATOR_HOLANDES[classe]
    producao_maturidade = round(hoje_kg * fator, 1)
    diferenca = round(producao_maturidade - hoje_kg, 1)

    return TrioEquivalenteMaduro(
        ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
        ja_maduro=False, producao_maturidade_kg=producao_maturidade, diferenca_kg=diferenca,
        confianca_nivel=nivel, confianca_fracao=fracao_medida, sem_base=False, motivo=None,
    )
