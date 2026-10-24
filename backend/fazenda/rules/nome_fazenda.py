"""
Nome da fazenda ATUAL para textos que saem do sistema (rodapé de e-mail,
cabeçalho do PDF do Manual, prompt do Assistente, campo padrão da leitura de
guia FGTS/DCTFWeb).

BUG CORRIGIDO: esses pontos traziam o nome fixo de UMA fazenda-cliente
("Fazenda Estreito Ponte de Pedra") — com o sistema multi-fazenda, qualquer
outra fazenda recebia e-mail, PDF e guia lida com o nome da fazenda alheia.
Agora o nome vem do cadastro (`Fazenda.nome`) da fazenda do contexto — a do
token (`get_fazenda_atual_id`) ou a do registro em questão.

Sem fazenda resolvida (token legado, instalação de fazenda única com a tabela
`fazenda` vazia, id que não existe mais) NUNCA se usa o nome de outra fazenda:
`nome_da_fazenda` devolve None e `nome_fazenda_ou_padrao` cai no nome do
produto (`NOME_PADRAO`).
"""
from __future__ import annotations

from sqlmodel import Session

from fazenda.models import Fazenda

# Nome do produto — o que aparece quando não há fazenda conhecida.
NOME_PADRAO = "CowData Milk"


def nome_da_fazenda(session: Session, fazenda_id: int | None) -> str | None:
    """Nome cadastrado da fazenda (sem espaços nas pontas) ou None quando não
    há fazenda resolvida / o cadastro não tem nome."""
    if not isinstance(fazenda_id, int):
        return None
    fazenda = session.get(Fazenda, fazenda_id)
    nome = (fazenda.nome or "").strip() if fazenda else ""
    return nome or None


def nome_fazenda_ou_padrao(session: Session, fazenda_id: int | None) -> str:
    """Igual a `nome_da_fazenda`, mas com o nome do produto como fallback —
    para texto que precisa de ALGUM nome (rodapé, cabeçalho)."""
    return nome_da_fazenda(session, fazenda_id) or NOME_PADRAO
