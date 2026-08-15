"""
Visibilidade de CATÁLOGO num banco multi-fazenda.

Há dois tipos de tabela no sistema, e eles não se filtram do mesmo jeito:

  • DADO DA FAZENDA (Estoque, Sanidade, Servico, ContaGerencial…) — pertence a
    uma fazenda e só a ela. Filtro estrito: `Model.fazenda_id == fazenda_id`.
    É o que garante o isolamento entre clientes.

  • CATÁLOGO (PrincipioAtivo, Doenca, MedicamentoComercial,
    IndicacaoTerapeutica) — nasce GLOBAL, com `fazenda_id` nulo, semeado igual
    para todo produtor, e cada fazenda pode ter as suas próprias linhas por
    cima (cadastro próprio ou personalização do padrão). Aqui o filtro estrito
    é um BUG: `fazenda_id == 1` exclui `fazenda_id IS NULL` em SQL, e a
    fazenda com `fid` no token via a Farmácia inteira vazia — nenhum erro no
    log, só listas em branco.

`visivel()` é o filtro do segundo caso: o global MAIS o da fazenda atual.
Continua sem vazar nada entre clientes — a linha de OUTRA fazenda segue de
fora, só o `NULL` (que é de todo mundo por definição) entra junto.
"""
from __future__ import annotations


def visivel(query, modelo, fazenda_id: int | None):
    """Restringe `query` ao catálogo visível pela fazenda atual: as linhas
    globais (`fazenda_id IS NULL`) e as da própria fazenda.

    `fazenda_id is None` (token legado, sem fazenda resolvida) não filtra
    nada — mesmo comportamento de antes do retrofit multi-fazenda.
    """
    if fazenda_id is None:
        return query
    return query.where(
        (modelo.fazenda_id == fazenda_id) | (modelo.fazenda_id.is_(None))
    )
