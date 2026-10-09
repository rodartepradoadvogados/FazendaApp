"""
Backfill das contas padrão de `vale` e `caixa_retencao` (Fase A, contas do
sistema 3.03.01.16 e 3.03.01.17). Ver `rules/plano_padrao.py`.

As origens automáticas `vale` e `caixa_retencao` não tinham conta no plano;
agora o plano ganha 3.03.01.17 (Vales e adiantamentos) e 3.03.01.16
(Retenções). Os papéis dessas origens já usam a conta do sistema quando ela
existe e a origem não tem configuração (`codigo_preferido`), mas isso não
grava nada em `conta_padrao_origem` — a tela "Contas automáticas" continuaria
mostrando as duas origens sem conta, e os itens ANTIGOS (que nasceram quando
não havia conta) continuariam sem classificação.

Este comando (por fazenda, simulação por padrão, `scripts/backfill_contas_origem.py`):

  1. grava `ContaPadraoOrigem` de `vale` → 3.03.01.17 e `caixa_retencao` →
     3.03.01.16 ONDE ESTIVER VAZIA (sem linha, ou com a linha sem conta). Nunca
     troca uma conta que a fazenda já escolheu, e só grava se a conta do
     sistema existir e estiver ativa no plano da fazenda;
  2. com `repintar_itens`, dá a conta às notas antigas dos geradores de
     retenção/vale (folha, rescisão, contrato, empreita, diária, vale, caixa)
     cujos itens GERADOS estão SEM conta. Nota com item lançado por gente não
     é tocada; item que já tem conta (do sistema ou escolhida pelo usuário)
     também não.

Nunca muda `valor_total`/`valor_pago` nem a conta da nota. Cada linha
criada/preenchida vira uma linha em `migracao_log_financeiro`; `--reverter
LOTE` devolve o que foi preenchido e apaga a linha de origem criada, salvo o
que mudou à mão depois (conflito).

Com a flag `financeiro_regras_v2` desligada os relatórios ignoram itens
gerados: rodar este backfill antes de ligar a flag não muda número nenhum.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from fazenda.rules import lancamento_automatico as la
from fazenda.rules.plano_padrao import CODIGO_RETENCOES, CODIGO_VALES

MIGRACAO = "backfill_contas_origem_v1"

# origem automática -> conta do sistema que ela passa a ter.
ORIGENS_DO_SISTEMA: dict[str, str] = {"vale": CODIGO_VALES, "caixa_retencao": CODIGO_RETENCOES}


@dataclass
class PlanoBackfill:
    # Linha de ContaPadraoOrigem a criar (sem linha) ou preencher (linha sem conta).
    criar_origem: list[dict] = field(default_factory=list)
    preencher_origem: list[dict] = field(default_factory=list)
    # Origens que ficam como estão (já configuradas ou sem a conta no plano).
    mantidas: list[dict] = field(default_factory=list)
    # Itens gerados sem conta que ganham a conta da origem (--repintar-itens).
    repintar: list[dict] = field(default_factory=list)
    preservadas: list[dict] = field(default_factory=list)


def _origem_efetiva(plano: PlanoBackfill, cfg: la.Configuracao, origem: str) -> tuple[str | None, str | None]:
    """(codigo, nome) que a origem passa a ter depois do backfill."""
    for p in plano.criar_origem + plano.preencher_origem:
        if p["origem"] == origem:
            return p["codigo"], p["nome"]
    conta = cfg.conta(origem)
    return conta.codigo, conta.nome


def planejar(session: Session, fazenda_id: int, *, repintar_itens: bool = False) -> PlanoBackfill:
    from fazenda.models import ContaPadraoOrigem, LancamentoItem

    if not isinstance(fazenda_id, int):
        raise ValueError("Informe a fazenda (uma por vez).")
    cfg = la.carregar_configuracao(session, fazenda_id)
    plano = PlanoBackfill()
    linhas = {l.origem: l for l in session.exec(
        select(ContaPadraoOrigem).where(ContaPadraoOrigem.fazenda_id == fazenda_id)).all()}

    for origem, codigo in ORIGENS_DO_SISTEMA.items():
        linha = linhas.get(origem)
        if linha is not None and linha.codigo_conta_gerencial:
            plano.mantidas.append({"origem": origem, "codigo": linha.codigo_conta_gerencial,
                                   "motivo": "já configurada: não troco a escolha da fazenda"})
        elif codigo not in cfg.contas_sistema:
            plano.mantidas.append({"origem": origem, "codigo": None,
                                   "motivo": f"a conta {codigo} não existe (ou está inativa) no plano da fazenda"})
        elif linha is None:
            plano.criar_origem.append({"origem": origem, "codigo": codigo, "nome": cfg.contas_sistema[codigo]})
        else:
            plano.preencher_origem.append({"origem": origem, "codigo": codigo, "nome": cfg.contas_sistema[codigo],
                                           "linha_id": linha.id})

    if not repintar_itens:
        return plano

    papeis = sorted(p for p, info in la.PAPEIS.items() if info.origem in ORIGENS_DO_SISTEMA)
    itens = session.exec(select(LancamentoItem).where(
        LancamentoItem.fazenda_id == fazenda_id, LancamentoItem.gerado_por.in_(papeis),
    )).all()
    sem_conta = [it for it in itens if not (it.codigo_conta_gerencial or "").strip()]
    if not sem_conta:
        return plano
    numeros = sorted({it.numero_lancamento for it in sem_conta if it.numero_lancamento})
    de_gente: set[str] = set()
    if numeros:
        de_gente = {n for n in session.exec(select(LancamentoItem.numero_lancamento).where(
            LancamentoItem.fazenda_id == fazenda_id, LancamentoItem.numero_lancamento.in_(numeros),
            LancamentoItem.gerado_por.is_(None),
        )).all()}
    for it in sorted(sem_conta, key=lambda i: i.id or 0):
        if it.numero_lancamento in de_gente:
            plano.preservadas.append({"item_id": it.id, "numero_lancamento": it.numero_lancamento,
                                      "motivo": "nota com item lançado por gente: preservada"})
            continue
        origem = la.origem_do_papel(it.gerado_por)
        codigo, nome = _origem_efetiva(plano, cfg, origem)
        if not codigo:
            plano.preservadas.append({"item_id": it.id, "numero_lancamento": it.numero_lancamento,
                                      "motivo": f"origem '{origem}' sem conta: nada a aplicar"})
            continue
        plano.repintar.append({"item_id": it.id, "numero_lancamento": it.numero_lancamento, "papel": it.gerado_por,
                               "codigo": codigo, "nome": nome})
    return plano


def aplicar(session: Session, plano: PlanoBackfill, lote: str, fazenda_id: int) -> int:
    """Grava o plano (sem commit). Devolve quantas linhas de log gravou."""
    from fazenda.models import ContaPadraoOrigem, LancamentoItem
    from fazenda.rules.migracao_log import registrar_criacao, registrar_mudanca

    linhas = 0
    for p in plano.criar_origem:
        existente = session.exec(select(ContaPadraoOrigem).where(
            ContaPadraoOrigem.fazenda_id == fazenda_id, ContaPadraoOrigem.origem == p["origem"])).first()
        if existente is not None:
            continue  # alguém criou entre o plano e a aplicação: não mexo
        linha = ContaPadraoOrigem(fazenda_id=fazenda_id, origem=p["origem"], codigo_conta_gerencial=p["codigo"])
        session.add(linha)
        session.flush()
        registrar_criacao(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="conta_padrao_origem",
                          registro=linha, motivo=f"conta do sistema de {p['origem']}")
        linhas += 1
    for p in plano.preencher_origem:
        linha = session.get(ContaPadraoOrigem, p["linha_id"])
        if linha is None or linha.fazenda_id != fazenda_id or linha.codigo_conta_gerencial:
            continue
        registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="conta_padrao_origem",
                          registro=linha, campo="codigo_conta_gerencial", valor_depois=p["codigo"],
                          motivo=f"conta do sistema de {p['origem']}")
        linhas += 1
    for p in plano.repintar:
        item = session.get(LancamentoItem, p["item_id"])
        if item is None or item.fazenda_id != fazenda_id or not item.gerado_por or item.codigo_conta_gerencial:
            continue
        registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="lancamento_item",
                          registro=item, campo="codigo_conta_gerencial", valor_depois=p["codigo"],
                          motivo=f"conta de {la.origem_do_papel(p['papel'])} para item antigo sem conta")
        linhas += 1
        if p.get("nome"):
            registrar_mudanca(session, fazenda_id=fazenda_id, lote=lote, migracao=MIGRACAO, tabela="lancamento_item",
                              registro=item, campo="nome_conta_gerencial", valor_depois=p["nome"],
                              motivo="nome da conta da origem")
            linhas += 1
    return linhas
