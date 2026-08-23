"""
Equivalente maduro (EM) — Camadas 2 e 3 de `docs/equivalente-maduro-proposta.md`.

Camada 2: fatores calibrados no próprio rebanho, não numa tabela publicada
(o 305-ME americano foi aposentado pelo CDCB em 2024; a tabela da Embrapa é
de Gir/Girolando, com estação de parto regionalizada de um jeito que não
transplanta). Para cada classe de ordem de parto, o fator é a razão entre a
média de produção de 305 dias (Camada 1, `rules/producao_305.py`) das
lactações ENCERRADAS da classe madura e da própria classe — por construção,
o fator da classe madura é 1,00.

Classe madura = 3ª parto ou mais, sempre (convenção padrão de buckets de
paridade 1 / 2 / 3+ da pecuária leiteira) — decisão fechada, não um "3ª ou
4ª a escolher com dados". Se a classe madura não tiver lactações
suficientes, o indicador INTEIRO degrada para "sem base" em vez de tratar a
2ª cria como se fosse madura: melhor não ajustar do que inventar uma
maturidade que os dados não sustentam.

Mínimo de 20 lactações encerradas por classe para publicar um fator; entre
20 e 50, publica mas marca confiança "baixa". Abaixo de 20, a classe (ou o
sistema inteiro, se for a madura que falha) fica sem fator. IMPORTANTE: 20 e
50 são um guarda-corpo de bom senso contra média de amostra pequena (poucas
lactações puxam a média para qualquer lado por acaso) — NÃO são números
derivados de um cálculo estatístico formal (intervalo de confiança, poder de
teste). Vieram como sugestão de `docs/equivalente-maduro-proposta.md` §6.2 e
foram adotados como estão; são livremente ajustáveis (`MINIMO_PUBLICAVEL`/
`MINIMO_CONFIANCA_ALTA` abaixo) se o rebanho em questão justificar outro
corte. "Lactação encerrada" conta em TODO o histórico do rebanho, de
qualquer animal (viva, vendida, morta) — a lactação de 1ª cria de uma vaca
que hoje está na 4ª cria também soma na classe 1, por exemplo.

Camada 3: o trio de apresentação — produz hoje, produzirá, diferença — nunca
o número do EM sozinho. Vaca já madura: `ja_maduro=True`, diferença zero (o
front mostra a frase "já está na maturidade", não "0 kg"). 1ª cria: a
diferença vem como faixa, porque é onde o ajuste é maior e a incerteza
também — usamos o desvio-padrão dos fatores individuais da classe (o fator
que cada lactação da classe implicaria sozinha, `media_madura / produção
daquela lactação`) como a medida de dispersão mais simples que ainda é
honesta sobre o quanto o ajuste varia de vaca para vaca.

Tudo aqui é puro — sem Session — igual a `rules/ordem_parto_historica.py` e
`rules/producao_305.py`. A montagem a partir do banco (quais lactações
entram, ordem de parto derivada por `ordem_parto_na_data`) fica no router.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from fazenda.rules.producao_305 import Producao305

MINIMO_PUBLICAVEL = 20
MINIMO_CONFIANCA_ALTA = 50
CLASSE_MADURA = 3


def classe_de_ordem(ordem_parto: int | None) -> int | None:
    """1, 2 ou 3 (= "3ª ou mais"). `None` quando a ordem de parto não é
    conhecida — não dá para classificar o que não se sabe."""
    if ordem_parto is None or ordem_parto < 1:
        return None
    return ordem_parto if ordem_parto < CLASSE_MADURA else CLASSE_MADURA


@dataclass(frozen=True)
class AmostraLactacao:
    """Uma lactação ENCERRADA do rebanho, já classificada — a unidade de
    entrada do cálculo de fatores."""

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
    # NENHUMA classe recebe fator (não só a que faltou dado).
    sem_base_geral: str | None


def contagem_lactacoes_por_classe(amostras: list[AmostraLactacao]) -> dict[int, int]:
    """Quantas lactações ENCERRADAS (de qualquer animal, todo o histórico)
    cada classe (1, 2, 3+) já acumulou — sempre as 3 classes presentes, 0
    quando a classe não tem nenhuma. Ao contrário de `calcular_fatores`
    (cujo `por_classe` omite silenciosamente a classe que não bateu
    `MINIMO_PUBLICAVEL`), esta contagem é para o usuário enxergar a distância
    exata até o mínimo — é o "quanto falta" que a resposta de
    `calcular_fatores` sozinha não deixa visível."""
    contagem = {1: 0, 2: 0, CLASSE_MADURA: 0}
    for a in amostras:
        if a.classe in contagem:
            contagem[a.classe] += 1
    return contagem


def calcular_fatores(amostras: list[AmostraLactacao]) -> FatoresRebanho:
    """Fatores de ajuste por classe, calibrados nas lactações encerradas do
    próprio rebanho passadas em `amostras`."""
    grupos: dict[int, list[float]] = {}
    for a in amostras:
        grupos.setdefault(a.classe, []).append(a.producao_305_kg)

    madura = grupos.get(CLASSE_MADURA, [])
    if len(madura) < MINIMO_PUBLICAVEL:
        motivo = (
            f"menos de {MINIMO_PUBLICAVEL} lactações encerradas na classe madura (3ª parto ou mais) "
            f"para calibrar o ajuste — há {len(madura)}. Sem base madura confiável, nenhuma classe "
            f"recebe fator."
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
    faixa_diferenca_kg: tuple[float, float] | None  # só para 1ª cria, quando há desvio
    confianca_fator: str | None
    sem_base: bool
    motivo: str | None


def montar_trio(
    producao_hoje: Producao305,
    ordem_parto: int | None,
    fatores: FatoresRebanho,
) -> TrioEquivalenteMaduro:
    """Aplica o fator da classe atual à produção real de hoje. `sem_base`
    cobre três causas distintas (todas com `motivo` textual): produção de
    305 dias não calculável, ordem de parto desconhecida, ou classe (própria
    ou madura) sem lactações suficientes para ter fator — em nenhum caso o
    front deve receber um número fabricado."""
    classe = classe_de_ordem(ordem_parto)
    hoje_kg = producao_hoje.producao_kg
    n = producao_hoje.n_controles

    def _sem_base(motivo: str) -> TrioEquivalenteMaduro:
        return TrioEquivalenteMaduro(
            ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
            ja_maduro=False, producao_maturidade_kg=None, diferenca_kg=None, faixa_diferenca_kg=None,
            confianca_fator=None, sem_base=True, motivo=motivo,
        )

    if hoje_kg is None:
        return _sem_base(producao_hoje.motivo or "produção de 305 dias não calculável")
    if classe is None:
        return _sem_base("ordem de parto desconhecida para este animal nesta data")

    if classe == CLASSE_MADURA:
        fator_madura = fatores.por_classe.get(CLASSE_MADURA)
        return TrioEquivalenteMaduro(
            ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
            ja_maduro=True, producao_maturidade_kg=hoje_kg, diferenca_kg=0.0, faixa_diferenca_kg=None,
            confianca_fator=fator_madura.confianca if fator_madura else None,
            sem_base=False, motivo=None,
        )

    fator_classe = fatores.por_classe.get(classe)
    if fator_classe is None:
        motivo = fatores.sem_base_geral or (
            f"menos de {MINIMO_PUBLICAVEL} lactações encerradas na classe {classe}ª para calibrar o ajuste"
        )
        return _sem_base(motivo)

    producao_maturidade = round(hoje_kg * fator_classe.fator, 1)
    diferenca = round(producao_maturidade - hoje_kg, 1)

    faixa = None
    if classe == 1 and fator_classe.desvio_fator:
        fator_baixo = max(fator_classe.fator - fator_classe.desvio_fator, 0.0)
        fator_alto = fator_classe.fator + fator_classe.desvio_fator
        faixa = (
            round(hoje_kg * fator_baixo - hoje_kg, 1),
            round(hoje_kg * fator_alto - hoje_kg, 1),
        )

    return TrioEquivalenteMaduro(
        ordem_parto=ordem_parto, classe=classe, producao_hoje_kg=hoje_kg, n_controles=n,
        ja_maduro=False, producao_maturidade_kg=producao_maturidade, diferenca_kg=diferenca,
        faixa_diferenca_kg=faixa, confianca_fator=fator_classe.confianca, sem_base=False, motivo=None,
    )
