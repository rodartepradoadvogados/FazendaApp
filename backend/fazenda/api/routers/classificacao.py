"""
Relatórios › Resultado › Classificar (docs/financeiro-regras-v2.md §14):

- `GET  /financeiro/classificacao/pendencias` — a fila do que a DRE deixa de fora por falta
  de classificação, por lançamento/item, com o motivo, os ids, o que há hoje e uma sugestão
  (nunca aplicada sozinha). Lê a MESMA lista de registros da DRE, então a fila fecha com o
  “sem classificação” e o “fora da DRE sem motivo” da cascata. Só leitura.
- `POST /financeiro/classificacao/aplicar` — o lote de ações (`conta` | `natureza` | `linha_dre`),
  administrador, tudo ou nada, com uma linha em `migracao_log_financeiro` por campo mudado.
- `POST /financeiro/classificacao/reverter/{lote}` — desfaz um lote desta tela.

Montado em main.py com as MESMAS travas do router do Financeiro (módulo financeiro, plano
contratado, fazenda selecionada e `bloquear_escrita_contador`). Toda rota de escrita usa
`get_fazenda_id_escrita`; toda leitura filtra pela fazenda. Mês fechado (só com a flag
`financeiro_regras_v2`): ver rules/classificacao_manual.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers import financeiro as fin
from fazenda.auth import exigir_admin, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import MigracaoLogFinanceiro, Usuario
from fazenda.rules import classificacao_manual as cm
from fazenda.rules import fechamento_mes
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.migracao_log import reverter_lote
from fazenda.rules.parametros import regras_v2_ativas

router = APIRouter(prefix="/financeiro/classificacao", tags=["financeiro-classificacao"])


def _fazenda(fazenda_id: int | None) -> int:
    fid = fazenda_id_seguro(fazenda_id)
    if not isinstance(fid, int):
        raise HTTPException(
            status_code=409, detail="Selecione a fazenda (saia e entre de novo) para classificar os lançamentos.",
            headers={"X-Fazenda-Nao-Selecionada": "1"},
        )
    return fid


@router.get("/pendencias")
def pendencias(
    data_inicio: Optional[date] = Query(None, description="Data inicial (mesmo parâmetro da DRE)"),
    data_fim: Optional[date] = Query(None, description="Data final (mesmo parâmetro da DRE)"),
    inicio: Optional[date] = Query(None, description="Apelido de data_inicio"),
    fim: Optional[date] = Query(None, description="Apelido de data_fim"),
    centro_custo: Optional[str] = Query(None),
    centro: Optional[str] = Query(None, description="Apelido de centro_custo"),
    regime: str = Query("competencia", description="'competencia' ou 'caixa'"),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """O que a DRE do período deixa de fora por falta de classificação, lançamento a lançamento.

    Os parâmetros são os da DRE (`data_inicio`, `data_fim`, `regime`, `centro_custo`; `inicio`,
    `fim` e `centro` são apelidos). Motivos: `conta_sem_linha_dre`, `sem_codigo_conta`,
    `item_sem_conta_automatica` (só com as regras novas) e `natureza_nao_informada` (idem).
    Com as regras antigas, a fila lista só o que elas também enxergam e a natureza vem travada,
    com o porquê, em `bloqueios`."""
    fid = _fazenda(fazenda_id)
    ini, fim_ = data_inicio or inicio, data_fim or fim
    if ini is None or fim_ is None:
        raise HTTPException(status_code=422, detail="Informe data_inicio e data_fim.")
    if regime not in ("competencia", "caixa"):
        raise HTTPException(status_code=422, detail="regime deve ser 'competencia' ou 'caixa'.")
    centro_ = centro_custo or centro or None

    regras_v2 = regras_v2_ativas(session, fid)
    filtradas, valores = fin._periodo_filtradas_dre(session, ini, fim_, centro_, regime, fid, regras_v2=regras_v2)
    contexto = fin._contexto_natureza(session, fid) if regras_v2 else None
    registros, _fallback = fin._registros_dre_para_cascata(
        session, filtradas, fin._valores_com_abatimento(filtradas, valores) if regras_v2 else valores,
        centro_, fid, contexto,
    )
    mapa_linha = contexto.mapa_linha_dre if contexto is not None else fin._mapa_linha_por_codigo(session, fid)
    fila = cm.montar_pendencias(session, fid, registros, filtradas, mapa_linha, regras_v2=regras_v2, regime=regime)
    return {
        "periodo": {"inicio": ini.isoformat(), "fim": fim_.isoformat()},
        "regime": regime, "centro_custo": centro_,
        **fila,
        "ultimo_lote": cm.ultimo_lote(session, fid),
    }


class AlvoIn(BaseModel):
    # conta do plano (linha_dre; natureza padrão da conta)
    codigo: Optional[str] = None
    # lançamento (todas as parcelas da nota) e, se for o caso, um item dela
    numero_lancamento: Optional[str] = None
    item_id: Optional[int] = None
    # nota antiga sem numero_lancamento (só a parcela)
    conta_id: Optional[int] = None


class AcaoIn(BaseModel):
    tipo: str  # conta | natureza | linha_dre
    alvo: Union[AlvoIn, str]  # texto = atalho: o código da conta (linha_dre/natureza) ou o número do lançamento (conta)
    valor: Optional[str] = None


class LoteIn(BaseModel):
    acoes: list[AcaoIn]
    motivo: Optional[str] = None


def _acao_para_regra(a: AcaoIn) -> dict:
    if isinstance(a.alvo, str):
        alvo = {"numero_lancamento": a.alvo} if a.tipo == "conta" else {"codigo": a.alvo}
    else:
        alvo = a.alvo.model_dump(exclude_none=True)
    return {"tipo": a.tipo, "alvo": alvo, "valor": a.valor}


@router.post("/aplicar")
def aplicar(
    dados: LoteIn, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: Usuario = Depends(exigir_admin),
) -> dict:
    """Aplica o lote inteiro ou nada (todas as ações são validadas antes de gravar). Só
    administrador. Devolve o `lote` para `POST /reverter/{lote}`; sem nenhuma mudança real
    (tudo já estava assim) `lote` vem nulo."""
    fid = _fazenda(fazenda_id)
    try:
        resultado = cm.aplicar_acoes(session, fid, [_acao_para_regra(a) for a in dados.acoes], motivo=dados.motivo)
    except cm.ErroAcoes as e:
        session.rollback()
        raise HTTPException(status_code=e.status, detail=e.detalhe) from None
    except Exception:
        session.rollback()
        raise
    session.commit()
    return {
        "lote": resultado.lote, "aplicadas": resultado.aplicadas, "sem_mudanca": resultado.sem_mudanca,
        "alteracoes": resultado.alteracoes, "avisos": resultado.avisos, "acoes": resultado.acoes,
    }


@router.post("/reverter/{lote}")
def reverter(
    lote: str, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita), _: Usuario = Depends(exigir_admin),
) -> dict:
    """Desfaz um lote desta tela, campo a campo, devolvendo o valor de antes SÓ onde o valor
    de hoje ainda é o que o lote gravou (quem mudou à mão depois vira `conflitos`, intocado).
    Só lotes da tela Classificar, da própria fazenda; mês fechado exige reabrir."""
    fid = _fazenda(fazenda_id)
    linhas = list(session.exec(select(MigracaoLogFinanceiro).where(
        MigracaoLogFinanceiro.lote == lote, MigracaoLogFinanceiro.fazenda_id == fid,
        MigracaoLogFinanceiro.migracao == cm.MIGRACAO)).all())
    if not linhas:
        raise HTTPException(status_code=404, detail="Lote de classificação não encontrado")
    fechamento_mes.exigir_meses_abertos(
        session, fid, cm.datas_das_linhas_do_lote(session, fid, linhas), "desfazer a classificação de")
    resultado = reverter_lote(session, lote, fazenda_id=fid, aplicar=True)
    session.commit()
    return {
        "lote": lote, "revertidas": resultado.revertidas, "ja_revertidas": resultado.ja_revertidas,
        "conflitos": resultado.conflitos, "nao_encontradas": resultado.nao_encontradas,
    }
