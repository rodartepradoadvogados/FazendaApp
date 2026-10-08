"""
Backfill da natureza econômica do histórico (Fase A, PR 1) — PLANO e APLICAÇÃO
separados, para o script de impacto medir o efeito sem gravar nada.

Quem chama é o comando `python -m scripts.backfill_natureza_fin` (dry-run por
padrão; grava só com `--aplicar`, num lote do `migracao_log_financeiro`, e
desfaz com `--reverter LOTE`). A migração Alembic NÃO roda isto.

Regras (conservadoras de propósito — ver SOLUCOES.md, P0-1 passo 3):

A. Despesa ligada a um bem (`patrimonio_id`) e sem natureza: vira INVESTIMENTO
   só se o valor da nota (soma das parcelas) estiver a ±10% do valor do bem
   (`valor_base_aquisicao`) E a competência estiver a até 60 dias da
   imobilização. O resto (ex.: manutenção ligada à mão ao trator) vai para a
   LISTA DE REVISÃO, sem aplicar.
B. Compra de animal (tela Comprar animal) sem natureza: vira INVESTIMENTO se a
   conta do plano ou a descrição falam em matriz/reprodutor/touro (Q10, como o
   contador recomendou); as demais vão para revisão (recria/venda é
   OPERACIONAL, mas só quem comprou sabe).
C. Conta do plano sem natureza cujo NOME indica financiamento, capital,
   transferência ou investimento: aplica SÓ quando a conta já está fora da DRE
   (linha NAO_ENTRA_NA_DRE, própria ou herdada) — aí a natureza só dá o motivo
   ao agrupamento, sem mudar número nenhum. Nas demais é SUGESTÃO (tela de
   conferência da DRE), nunca aplicação automática.

Nunca toca `valor_total`/`valor_pago`. Nunca sobrescreve uma natureza já
preenchida (por usuário ou por outro lote).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from sqlmodel import Session, select

from fazenda.rules.dre import NAO_ENTRA_NA_DRE, resolver_linha_dre
from fazenda.rules.natureza import (
    CAPITAL, FINANCIAMENTO, INVESTIMENTO, TRANSFERENCIA, eh_matriz_ou_reprodutor, inferir_natureza_por_nome,
)

MIGRACAO = "backfill_natureza_fin_v1"
TOLERANCIA_VALOR = 0.10
JANELA_DIAS = 60
_APLICAVEIS_PLANO_FORA_DRE = frozenset({FINANCIAMENTO, CAPITAL, TRANSFERENCIA, INVESTIMENTO})


@dataclass
class PlanoBackfill:
    fazenda_id: int
    # {tabela, id, campo, de, para, motivo, numero_lancamento, valor}
    mudancas: list[dict] = field(default_factory=list)
    # {tabela, id, numero_lancamento, descricao, valor, motivo, sugestao}
    revisao: list[dict] = field(default_factory=list)
    # {codigo, nome, natureza_sugerida, motivo, linha_dre}
    sugestoes: list[dict] = field(default_factory=list)

    def sobrepor_conta(self) -> dict[int, str]:
        """{conta_gerencial.id: natureza} — para simular no motor sem gravar."""
        return {m["id"]: m["para"] for m in self.mudancas if m["tabela"] == "conta_gerencial"}

    def sobrepor_plano(self) -> dict[str, str]:
        return {m["codigo"]: m["para"] for m in self.mudancas if m["tabela"] == "plano_conta_gerencial"}


def _mapas_plano(session: Session, fazenda_id: int):
    from fazenda.models import PlanoContaGerencial

    plano = session.exec(select(PlanoContaGerencial).where(PlanoContaGerencial.fazenda_id == fazenda_id)).all()
    mapa_linha = {p.codigo: p.linha_dre for p in plano if p.linha_dre}
    nomes = {p.codigo: p.nome for p in plano}
    return plano, mapa_linha, nomes


def sugestoes_natureza_plano(session: Session, fazenda_id: int | None) -> list[dict]:
    """Contas do plano sem natureza própria cujo nome sugere uma natureza ≠
    OPERACIONAL. Só leitura. `aplicada_no_backfill` diz se o backfill a
    aplicaria sozinho (conta já fora da DRE)."""
    if not isinstance(fazenda_id, int):
        return []
    plano, mapa_linha, _nomes = _mapas_plano(session, fazenda_id)
    saida = []
    for conta in sorted(plano, key=lambda p: p.codigo):
        if conta.natureza_fin:
            continue
        natureza, motivo = inferir_natureza_por_nome(conta.nome)
        if not natureza:
            continue
        linha = resolver_linha_dre(conta.codigo, mapa_linha)
        saida.append({
            "codigo": conta.codigo, "nome": conta.nome, "natureza_sugerida": natureza,
            "motivo": motivo, "linha_dre": linha,
            "aplicada_no_backfill": linha == NAO_ENTRA_NA_DRE and natureza in _APLICAVEIS_PLANO_FORA_DRE,
        })
    return saida


def planejar(session: Session, fazenda_id: int) -> PlanoBackfill:
    """Monta o plano do backfill de UMA fazenda. Só lê."""
    from fazenda.models import CompraAnimal, ContaGerencial, Patrimonio
    from fazenda.rules.patrimonio import valor_base_aquisicao

    if not isinstance(fazenda_id, int):
        raise ValueError("Informe a fazenda (o backfill é sempre de uma fazenda por vez).")
    plano_bf = PlanoBackfill(fazenda_id=fazenda_id)
    plano, mapa_linha, nomes_plano = _mapas_plano(session, fazenda_id)

    contas = session.exec(select(ContaGerencial).where(ContaGerencial.fazenda_id == fazenda_id)).all()
    por_numero: dict[str, list] = {}
    for c in contas:
        chave = c.numero_lancamento or f"id-{c.id}"
        por_numero.setdefault(chave, []).append(c)

    # --- A. despesa ligada a bem do patrimônio --------------------------------
    for numero, parcelas in sorted(por_numero.items()):
        alvo = [c for c in parcelas if c.tipo == "despesa" and c.patrimonio_id and not c.natureza_fin]
        if not alvo:
            continue
        bem = session.get(Patrimonio, alvo[0].patrimonio_id)
        valor_nota = round(sum(c.valor_total or 0 for c in parcelas), 2)
        competencia = min((c.data_competencia for c in parcelas if c.data_competencia), default=None)
        base = valor_base_aquisicao(bem.model_dump()) if bem is not None and bem.fazenda_id == fazenda_id else 0.0
        motivo_recusa = None
        if bem is None or bem.fazenda_id != fazenda_id:
            motivo_recusa = "bem do patrimônio não encontrado nesta fazenda"
        elif not base:
            motivo_recusa = "bem sem valor de aquisição"
        elif abs(valor_nota - base) / base > TOLERANCIA_VALOR:
            motivo_recusa = f"valor da nota ({valor_nota:.2f}) difere do bem ({base:.2f}) em mais de 10%"
        elif not competencia or not bem.data_imobilizacao:
            motivo_recusa = "sem competência ou sem data de imobilização para comparar"
        elif abs((competencia - bem.data_imobilizacao).days) > JANELA_DIAS:
            motivo_recusa = (
                f"competência ({competencia:%d/%m/%Y}) a mais de 60 dias da imobilização "
                f"({bem.data_imobilizacao:%d/%m/%Y})"
            )
        if motivo_recusa:
            plano_bf.revisao.append({
                "tabela": "conta_gerencial", "ids": [c.id for c in alvo], "numero_lancamento": parcelas[0].numero_lancamento,
                "descricao": parcelas[0].descricao, "valor": valor_nota, "motivo": motivo_recusa,
                "sugestao": "Se for a compra do bem, marque Investimento; se for manutenção/uso, deixe Operacional.",
            })
            continue
        pct = round(100 * valor_nota / base, 1)
        for c in alvo:
            plano_bf.mudancas.append({
                "tabela": "conta_gerencial", "id": c.id, "campo": "natureza_fin", "de": None, "para": INVESTIMENTO,
                "numero_lancamento": c.numero_lancamento, "valor": c.valor_total,
                "motivo": f"compra do bem '{bem.nome}' (nota = {pct}% do valor do bem, competência a "
                          f"{abs((competencia - bem.data_imobilizacao).days)} dia(s) da imobilização)",
            })

    # --- B. compra de animal ---------------------------------------------------
    numeros_compra = {
        n for n in session.exec(
            select(CompraAnimal.numero_lancamento_gerado).where(CompraAnimal.fazenda_id == fazenda_id)
        ).all() if n
    }
    ja_planejadas = {m["id"] for m in plano_bf.mudancas}
    for numero in sorted(numeros_compra):
        parcelas = [c for c in por_numero.get(numero, []) if c.tipo == "despesa" and not c.natureza_fin and c.id not in ja_planejadas]
        if not parcelas:
            continue
        nome_conta = nomes_plano.get(parcelas[0].codigo_conta or "")
        if eh_matriz_ou_reprodutor(nome_conta, parcelas[0].descricao):
            for c in parcelas:
                plano_bf.mudancas.append({
                    "tabela": "conta_gerencial", "id": c.id, "campo": "natureza_fin", "de": None, "para": INVESTIMENTO,
                    "numero_lancamento": c.numero_lancamento, "valor": c.valor_total,
                    "motivo": f"compra de matriz/reprodutor (conta '{nome_conta or c.codigo_conta}')",
                })
        else:
            plano_bf.revisao.append({
                "tabela": "conta_gerencial", "ids": [c.id for c in parcelas], "numero_lancamento": numero,
                "descricao": parcelas[0].descricao, "valor": round(sum(c.valor_total or 0 for c in parcelas), 2),
                "motivo": "compra de animal sem indicação de matriz/reprodutor",
                "sugestao": "Matriz ou reprodutor: Investimento. Recria ou para venda: Operacional.",
            })

    # --- C. plano de contas ------------------------------------------------------
    for sugestao in sugestoes_natureza_plano(session, fazenda_id):
        if sugestao["aplicada_no_backfill"]:
            conta_plano = next(p for p in plano if p.codigo == sugestao["codigo"])
            plano_bf.mudancas.append({
                "tabela": "plano_conta_gerencial", "id": conta_plano.id, "codigo": conta_plano.codigo,
                "campo": "natureza_fin", "de": None, "para": sugestao["natureza_sugerida"],
                "numero_lancamento": None, "valor": None,
                "motivo": f"{sugestao['motivo']}; conta já fora da DRE (só muda o agrupamento)",
            })
        else:
            plano_bf.sugestoes.append(sugestao)
    return plano_bf


def aplicar(session: Session, plano_bf: PlanoBackfill, lote: str) -> int:
    """Grava o plano (sem commit), uma linha de log por campo. Pula o que
    mudou desde o planejamento (natureza preenchida por alguém nesse meio)."""
    from fazenda.models import ContaGerencial, PlanoContaGerencial
    from fazenda.rules.migracao_log import registrar_mudanca

    modelos = {"conta_gerencial": ContaGerencial, "plano_conta_gerencial": PlanoContaGerencial}
    aplicadas = 0
    for m in plano_bf.mudancas:
        registro = session.get(modelos[m["tabela"]], m["id"])
        if registro is None or registro.fazenda_id != plano_bf.fazenda_id:
            continue
        if getattr(registro, m["campo"]) is not None:
            continue
        registrar_mudanca(
            session, fazenda_id=plano_bf.fazenda_id, lote=lote, migracao=MIGRACAO,
            tabela=m["tabela"], registro=registro, campo=m["campo"], valor_depois=m["para"], motivo=m["motivo"],
        )
        aplicadas += 1
    return aplicadas

