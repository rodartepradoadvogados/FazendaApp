"""Estrutura de dados do impacto de uma exclusão (Fase 1 do "Excluir
lançamentos", plano `docs/mockups/excluir-lancamentos/plano-implementacao.md`).

Antes desta fase o impacto era uma lista de strings soltas (`impacto:
list[str]`) — a tela exibia e pronto. Agora o impacto é ESTRUTURADO em quatro
blocos que a tela renda como "BLOQUEIA / SERÁ APAGADO / SERÁ REVERTIDO /
AVISOS", cada item com uma consequência em frase simples.

Estas são dataclasses simples (não SQLModel): são o contrato da API, serializam
direto com `asdict`. A lista antiga `impacto: list[str]` continua sendo devolvida
junto (títulos de `apagar`), por compatibilidade, até a UI nova (Fase 2) assumir.

Convenção: nenhum campo carrega dado sensível (CPF, dado de saúde de pessoa).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Linha:
    """Um item de impacto.

    - `titulo`: o quê (ex.: "Ficha do animal 1042", "2 parcelas").
    - `consequencia`: frase simples do que acontece (ex.: "a vaca deixa de
      existir no sistema", "saem das contas a pagar").
    - `qtd`: quantos registros este item resume (agrega itens idênticos).
    - `valor`: dinheiro em aberto, em reais, quando o item representa conta ainda
      não paga/recebida — é o sinal que sobe o risco para "médio". None = não há
      dinheiro em aberto envolvido.
    - `filhos`: linhas de detalhe prontas para exibir (ex.: "1/2 · vence 15/10 ·
      R$ 4.200,00 · em aberto"), já formatadas.
    - `chip`: rótulo curto (ex.: "Mexe no estoque", "Mexe na lactação").
    """

    titulo: str
    consequencia: str
    qtd: int = 1
    valor: Optional[float] = None
    filhos: list[str] = field(default_factory=list)
    chip: Optional[str] = None


@dataclass
class Bloqueio:
    """Motivo que IMPEDE a exclusão (≠ aviso, que só alerta). Quando `bloqueia`
    não está vazio, nada mais é apagado. `fazer` diz o que fazer antes de
    tentar de novo; `acao` é o atalho de navegação quando houver
    ({"rota", "params"})."""

    titulo: str
    motivo: str
    fazer: str
    acao: dict = field(default_factory=dict)  # {"rota": "...", "params": {...}} opcional


@dataclass
class Impacto:
    """O impacto completo de excluir `item`, em blocos.

    - `bloqueia`  → motivos que impedem (se houver, é o que importa);
    - `apagar`    → o que some de vez;
    - `reverter`  → o que é ajustado/restaurado (não apagado);
    - `avisos`    → consequências que merecem atenção mas não travam;
    - `risco`     → "baixo" | "medio" | "alto". None = calcular; o tipo pode
      FORÇAR um valor (ex.: ficha de animal é sempre "alto");
    - `porque`    → justificativas do risco (uma frase por linha);
    - `editar_url`→ atalho "corrigir em vez de apagar" (rota para editar o alvo).
    """

    item: dict  # {"tipo", "id", "titulo"}
    apagar: list[Linha] = field(default_factory=list)
    reverter: list[Linha] = field(default_factory=list)
    bloqueia: list[Bloqueio] = field(default_factory=list)
    avisos: list[Linha] = field(default_factory=list)
    risco: Optional[str] = None  # "baixo" | "medio" | "alto"
    porque: list[str] = field(default_factory=list)
    editar_url: Optional[str] = None

    def dict(self) -> dict:
        return asdict(self)

    def tem_bloqueio(self) -> bool:
        return bool(self.bloqueia)


class ExclusaoBloqueada(Exception):
    """Um bloqueio de exclusão. Levantada onde hoje se faria
    `raise HTTPException(400)` — carrega o `Bloqueio` ESTRUTURADO para que a API
    devolva o objeto no impacto (`/impacto` → 200 com `bloqueia`) ou recuse a
    confirmação com 409. A mensagem é o `titulo` (não vaza dado sensível)."""

    def __init__(self, bloqueio: Bloqueio):
        self.bloqueio = bloqueio
        super().__init__(bloqueio.titulo)