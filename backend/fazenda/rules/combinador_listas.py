"""
Combinador de Listas (Insights > Listas > Combinador de Listas).

Monta, para cada animal ativo, os atributos usados pelos parâmetros
configuráveis do Combinador (lote, idade, peso, produção, situação
produtiva/reprodutiva, dias pós-parto/gestação/para o parto/desde o último
serviço, categoria vaca/novilha/bezerra e categoria de manejo cadastrada) —
puro, sem sessão de banco, para ser testável isolado (ver
tests/test_combinador_listas.py) e reaproveitado pelo endpoint real
(fazenda/api/routers/relatorios.py).

Reaproveita por completo o que já existe, sem duplicar cálculo algum:
- `_contexto_categoria`/`classificar_categoria` (recria.py) — mesmo motor
  usado pela composição de categorias e pela ficha do animal. Não muda o
  algoritmo de match (um único critério por animal, o primeiro que bate na
  ordem cadastrada) — instrução explícita do usuário ao pedir esta feature:
  "Não precisa mexer nas categorias".
- BST (aptas/a incluir no próximo lote/inaptas) NÃO é recalculado aqui: o
  frontend usa a mesma `GET /agenda/` que a versão anterior do Combinador já
  consumia (`bst_elegiveis`/`bst_nunca_aplicados`/`bst_excluidos`) — refazer
  esse cálculo aqui duplicaria o motor inteiro da Agenda (protocolos,
  hormônios etc.) só para extrair 3 listas que já existem prontas.

Cruzamento (união/interseção/diferença) e o diagnóstico de "por que este
cruzamento não retornou animais" também ficam no FRONTEND
(CombinadorListas.tsx): com os atributos brutos por animal em mãos, cada
parâmetro configurado vira um conjunto (Set de números) calculado no
cliente — exatamente como a versão anterior já fazia com as listas
pré-prontas, só que agora os parâmetros são configuráveis em vez de fixos.

── Notas de problemas possíveis (combinações que zeram o resultado) ──
Nenhuma delas é tratada como erro — o Combinador sempre pode legitimamente
não achar ninguém; o ponto é o frontend saber diagnosticar e avisar qual
filtro é o suspeito, em vez de só mostrar "0 animais". O diagnóstico é
dinâmico (conta cada filtro sozinho antes de cruzar), não uma tabela fixa
de pares incompatíveis — mas os casos abaixo foram testados e documentam a
classe de problema que motivou esse desenho:

1. Situação produtiva × categoria cadastrada incoerentes entre si
   (ex.: situação produtiva = "Em lactação" + categoria cadastrada =
   "Seca"): cada uma sozinha pode ter animais, mas a interseção é sempre
   vazia porque `situacao_produtiva` é mutuamente exclusivo por natureza
   (um animal nunca está em lactação E seco ao mesmo tempo).
2. Situação reprodutiva × categoria cadastrada incoerentes (ex.: situação
   reprodutiva = "Prenha" + categoria cadastrada = "Vazia atrasada"): mesma
   razão — `situacao_reprodutiva_viva` também é mutuamente exclusiva.
3. Faixa numérica fora de qualquer valor real do rebanho (ex.: peso 2000kg
   a 3000kg, ou dias de gestação 400+): a faixa sozinha já zera — não é bem
   uma "incompatibilidade entre filtros", é um filtro individual sem
   nenhuma correspondência; o diagnóstico aponta esse filtro específico.
4. Filtro que só se aplica a um subconjunto do rebanho cruzado com um
   subconjunto disjunto (ex.: categoria vaca/novilha/bezerra = "Bezerra" +
   situação reprodutiva = "Prenha"): bezerra nunca tem situação reprodutiva
   computada (novilha/vaca só) — a interseção é estruturalmente vazia.
5. Categoria cadastrada com `dia_min`/`dia_max` que não cobre a idade de
   nenhum animal vivo no rebanho atual (cadastro desatualizado) — mesmo
   caso do item 3, mas para o filtro de categoria cadastrada.
6. Diferença (modo "diferença") nunca deveria disparar esse diagnóstico:
   cada lista é mostrada separadamente com sua própria contagem, incluindo
   zero — "0 animais exclusivos desta lista" já É a resposta, não indica
   problema de parâmetro.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fazenda.api.routers.recria import _contexto_categoria, classificar_categoria
from fazenda.models import CategoriaManejo
from fazenda.rules.estado_reprodutivo import ATRASADA


def categoria_etaria(categoria_abrev: str | None) -> str | None:
    """"Vaca"/"Novilha"/"Bezerra"/"Bezerro" (`Animal.categoria_abrev`, herdado
    do GERAL.csv — mesmo texto que já alimenta
    `producao.py::SugestaoLoteEventoIn`) -> bucket grosso vaca/novilha/bezerra
    pedido pelo usuário para o Combinador. Sem heurística nova: só agrupa o
    texto que o Ideagri já manda."""
    if not categoria_abrev:
        return None
    txt = categoria_abrev.strip().lower()
    if txt.startswith("vaca"):
        return "vaca"
    if txt.startswith("novilha"):
        return "novilha"
    if txt.startswith("bezerr"):
        return "bezerra"
    return None


def contexto_animal_combinador(
    *,
    numero: str,
    data_nasc: date | None,
    raca: str | None,
    lote: str | None,
    categoria_abrev: str | None,
    peso: float | None,
    producao_kg: float | None,
    sit_rep: str | None,
    hoje: date,
    servicos: list[Any],
    partos: list[Any],
    secagens: list[Any],
    pesagens: list[tuple[date, float]],
    categorias_cadastro: list[CategoriaManejo],
    pev_dias: int,
    del_max_1o_servico: int | None,
    idade_apta_dias: int | None,
    peso_apta_kg: float | None,
    idade_atraso_dias: int | None,
    dias_atraso_apos_aptidao: int | None,
    data_inicio_lactacao: date | None,
    data_ultima_pesagem: date | None = None,
    data_ultima_producao: date | None = None,
) -> dict:
    """Atributos filtráveis de UM animal para o Combinador de Listas.

    `data_ultima_pesagem`/`data_ultima_producao`: só para as colunas "Peso"/
    "Produção" do resultado ao vivo mostrarem também a data do último
    lançamento (não só o valor) — o próprio filtro de faixa já usa apenas
    `peso`/`producao_kg`."""
    dias = (hoje - data_nasc).days if data_nasc else None
    ctx = _contexto_categoria(
        dias, peso, sit_rep, hoje, servicos, partos, secagens, raca=raca, numero=numero,
        pev_dias=pev_dias, del_max_1o_servico=del_max_1o_servico, idade_apta_dias=idade_apta_dias,
        peso_apta_kg=peso_apta_kg, idade_atraso_dias=idade_atraso_dias, data_nasc=data_nasc,
        pesagens=pesagens, dias_atraso_apos_aptidao=dias_atraso_apos_aptidao,
        data_inicio_lactacao=data_inicio_lactacao,
    )
    categoria_nome = classificar_categoria(ctx, categorias_cadastro) if categorias_cadastro else None
    data_ficou_apta = ctx["data_ficou_apta"]
    return {
        "numero": numero,
        "lote": lote,
        "categoria_etaria": categoria_etaria(categoria_abrev),
        "categoria_cadastro": categoria_nome,
        "idade_dias": dias,
        "peso_kg": peso,
        "producao_kg": producao_kg,
        "situacao_produtiva": ctx["situacao_produtiva"],
        "dias_pos_parto": ctx["dias_pos_parto"],
        "dias_para_parto": ctx["dias_para_parto"],
        "dias_gestacao": ctx["dias_gestacao"],
        "dias_desde_servico": ctx["dias_desde_servico"],
        "situacao_reprodutiva": ctx["situacao_reprodutiva_viva"],
        "dias_desde_pesagem": (hoje - data_ultima_pesagem).days if data_ultima_pesagem else None,
        "dias_desde_producao": (hoje - data_ultima_producao).days if data_ultima_producao else None,
        # "Apta desde" (coluna do Combinador) — a mesma data que
        # estado_reprodutivo.classificar_animal já usa para o gatilho de
        # ATRASADA por tempo. None = ainda não alcançou idade/peso de
        # aptidão (bezerra/recria), não é um "erro de dado".
        "dias_desde_aptidao": (hoje - data_ficou_apta).days if data_ficou_apta else None,
        # True = já apta (ou além: inseminada/prenha); False = alcançou a
        # aptidão mas está ATRASADA (nunca foi coberta a tempo); None = não
        # se aplica (ainda não chegou a data de aptidão).
        "apta": None if data_ficou_apta is None else ctx["estado_vivo"] != ATRASADA,
    }
