"""
Motor de projeção de categoria de manejo para data futura — Fase 0, passo 2
do redesenho do evento sanitário (risco R-2, ver docs/redesenho-evento-sanitario.md).

Responde "quem vai estar na categoria-alvo na data X?" para regras do
calendário sanitário por ÉPOCA (frequência), que hoje não sugerem ninguém
automaticamente — só regra por evento de vida tem sugestão automática
(`fazenda.rules.eventos_sanitarios._datas_gatilho`).

Não é motor novo de classificação: reaproveita a MESMA classificação por
categoria já usada em Recria/Lote (`fazenda.rules.lote_criterios._contexto_animal`
+ `fazenda.api.routers.recria.classificar_categoria`), que já recebe `hoje`
como parâmetro livre — a idade em dias já é `(hoje - data_nasc).days`, então
passar uma data futura em vez de `date.today()` já projeta a idade sozinho.

O contexto reprodutivo/produtivo (situação reprodutiva, dias de gestação,
dias pós-parto) usa sempre o estado ATUAL do animal (última Secagem/Parto/
Serviço já lançado) como melhor estimativa disponível — este módulo NUNCA
simula um serviço, parto ou secagem que ainda vai acontecer entre hoje e a
data futura. Por isso, quando a categoria-alvo depende de critério
reprodutivo (não só idade/peso), o chamador deve tratar o resultado como
"projeção estimada, pode mudar até a data da Ocorrência" (ver seção 3.2.2 do
redesenho) — não como garantia. Para critério puramente etário a projeção é
tão confiável quanto a classificação de hoje.

Este módulo é deliberadamente "sem I/O": recebe pronto o `dados` que
`fazenda.api.routers.lotes.coletar_dados_criterios` já monta (mesmo dict
que `lote_criterios.animal_atende_criterios` consome), para não duplicar
nenhuma query nem regra de negócio. Quem acopla à Ocorrência (Fase 1,
passo 6) é responsável por chamar `coletar_dados_criterios` uma vez e
reaproveitar o resultado para todas as regras do dia, não uma vez por regra.
"""
from __future__ import annotations

from datetime import date

from fazenda.api.routers.recria import classificar_categoria
from fazenda.rules.lote_criterios import _contexto_animal

# Mesmo separador usado no cadastro da Regra (categoria_alvo é texto livre com
# várias categorias) — ver SEP_CATEGORIAS em
# frontend/components/lancamentos/FormCalendarioSanitario.tsx e
# frontend/components/mobile/lancar/FormSanidade.tsx. Mantido em um só lugar
# aqui para o backend nunca divergir do que o frontend grava.
SEP_CATEGORIAS = ", "


def projetar_categoria_animal(animal: dict, data_futura: date, dados: dict) -> str:
    """Categoria de manejo projetada de UM animal (dict, mesmo formato de
    `dados["animais"]`) para `data_futura`. `dados` é o dict inteiro devolvido
    por `coletar_dados_criterios` (traz `categorias_ativas` e todo o histórico
    por animal que a classificação precisa)."""
    ctx = _contexto_animal(animal, data_futura, dados)
    return classificar_categoria(ctx, dados["categorias_ativas"])


def projetar_categorias(dados: dict, data_futura: date) -> dict[str, str]:
    """`numero_matriz` → categoria projetada para `data_futura`, para todos
    os animais em `dados["animais"]`."""
    return {
        animal["numero"]: projetar_categoria_animal(animal, data_futura, dados)
        for animal in dados["animais"]
    }


def animais_projetados_na_categoria(categoria_alvo: str, data_futura: date, dados: dict) -> list[str]:
    """`numero_matriz` dos animais cuja categoria PROJETADA para `data_futura`
    bate com `categoria_alvo` — texto livre, podendo listar mais de uma
    categoria separada por `SEP_CATEGORIAS` (mesma convenção do cadastro da
    Regra). Comparação por nome, sem diferenciar maiúsculas/espaços nas
    pontas. `categoria_alvo` vazio devolve lista vazia (regra sem categoria
    definida não sugere ninguém — mais seguro que sugerir o rebanho todo)."""
    alvos = {c.strip().lower() for c in (categoria_alvo or "").split(SEP_CATEGORIAS) if c.strip()}
    if not alvos:
        return []
    projetadas = projetar_categorias(dados, data_futura)
    return sorted(numero for numero, categoria in projetadas.items() if categoria.strip().lower() in alvos)
