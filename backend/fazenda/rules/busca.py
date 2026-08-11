"""
Normalização de texto para BUSCA — nunca para exibição/gravação (par exato
do `frontend/lib/busca.ts`, para os dois lados tratarem "acha isso" da mesma
forma; não dá pra importar um módulo Python de um módulo TypeScript, então a
lógica é replicada — mesmos casos, cobertos nos dois lados por teste).

O valor exibido/gravado no banco continua com acento e maiúscula normais; só
a COMPARAÇÃO ignora o que não deveria importar para achar um resultado:
caixa alta/baixa, acento/cedilha, e hífen/underscore/espaço ("sal-mineral",
"sal_mineral" e "sal mineral" devem casar com o termo digitado "salmineral").

Ponto único para isso no backend: antes deste módulo, cada router com um
parâmetro `busca`/`termo` reinventava sua própria normalização — algumas só
com `.lower()` (sem tratar acento), outras com uma cópia colada de
`unicodedata.normalize(...)` (repetida em mais de um arquivo, cada um com
sua leve variação), e nenhuma tratava hífen/underscore/espaço. `_contem`, em
`rules/exclusao_tipos/_base.py`, é reaproveitado por praticamente toda busca
de "excluir lançamento" (estoque, rebanho, produção, financeiro, pessoal,
agricultura) só por delegar pra cá.
"""
from __future__ import annotations

import unicodedata


def normalizar_busca(texto: str | None) -> str:
    if not texto:
        return ""
    # NFD decompõe cada caractere acentuado em base + marca combinante (ex.:
    # "ç" -> "c" + cedilha combinante, "ã" -> "a" + til combinante);
    # unicodedata.combining() identifica exatamente essas marcas, então
    # filtrá-las fora depois do NFD é o jeito padrão de tirar acento/cedilha
    # sem depender de biblioteca externa (unidecode etc.).
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )
    sem_separador = "".join(c for c in sem_acento.lower() if c not in "-_ \t\n\r")
    return sem_separador


def casa_busca(termo: str | None, *valores: object) -> bool:
    """True se `termo` (o que o usuário digitou) aparece em algum de
    `valores`, ignorando caixa/acento/hífen/underscore/espaço dos dois
    lados. Termo vazio (ou só espaços) sempre casa — o padrão "busca vazia
    mostra tudo" que toda tela de busca/exclusão já espera."""
    termo_norm = normalizar_busca(termo)
    if not termo_norm:
        return True
    return any(termo_norm in normalizar_busca(str(v)) for v in valores if v is not None)
