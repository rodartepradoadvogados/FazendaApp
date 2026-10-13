"""
POST /fazendas/{fazenda_id}/financeiro/preparar — "Preparar financeiro"
(Plano Financeiro §1.8, item G do contrato de API).

Botão do dono no Painel CowData (NÃO automático) para deixar uma fazenda
recém-criada pronta a lançar: o contador precisa de plano de contas e das
regras novas desde o dia 1. Idempotente — chamar de novo não duplica nada.

O que faz, nesta ordem:
  1. Plano de contas: se a fazenda não tem NENHUMA conta, carrega o plano
     padrão rural-leiteiro (fazenda/rules/plano_padrao_rural.py — RASCUNHO,
     validar com o contador). Fazenda com plano (ex.: importado do Ideagri)
     nunca é tocada.
  2. Contas do sistema (3.03.01.16 Retenções, 3.03.01.17 Vales e
     adiantamentos): `plano_padrao.garantir_contas_do_sistema`.
  3. Regras v2 (`financeiro_regras_v2`): liga SOMENTE se a fazenda não tem
     nenhum lançamento — fazenda com histórico muda de número quando a flag
     liga e segue o roteiro de impacto (docs/financeiro-regras-v2.md), nunca
     este botão.

Fica num router próprio (e não em fazendas.py) para não conflitar com a
trilha do contrato/preço, que edita aquele arquivo.

Resposta (formato G):
  { plano_contas_carregado: bool  — a fazenda TEM plano de contas ao final,
    contas_criadas: int           — contas criadas NESTA chamada (plano + sistema),
    regras_v2_ligadas: bool       — a flag está ligada ao final,
    ja_preparado: bool            — nada precisou ser feito nesta chamada,
    mensagens: [str] }
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from fazenda.auth import exigir_dono
from fazenda.database import get_session, sessao_sem_recorte_de_fazenda
from fazenda.models import ContaGerencial, ContratoFazendaModulo, Fazenda, ParametroFazenda, Usuario
from fazenda.rules.parametros import CHAVE_FINANCEIRO_REGRAS_V2, regras_v2_ativas
from fazenda.rules.plano_padrao import garantir_contas_do_sistema
from fazenda.rules.plano_padrao_rural import carregar_plano_padrao_rural, fazenda_tem_plano_de_contas

router = APIRouter(prefix="/fazendas", tags=["fazendas"])

_LABEL_REGRAS_V2 = (
    "Relatórios do Financeiro — usar as regras novas (Fase A: natureza do lançamento; "
    "compra de bem, principal e aporte fora da DRE e dos custos)"
)


def _ligar_regras_v2(s: Session, fazenda_id: int) -> None:
    """Grava a linha DA FAZENDA (a global é só o modelo da tela e é ignorada na leitura —
    ver `regras_v2_ativas`)."""
    linha = s.exec(select(ParametroFazenda).where(
        ParametroFazenda.chave == CHAVE_FINANCEIRO_REGRAS_V2, ParametroFazenda.fazenda_id == fazenda_id,
    )).first()
    if linha is None:
        modelo = s.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == CHAVE_FINANCEIRO_REGRAS_V2, ParametroFazenda.fazenda_id.is_(None),
        )).first()
        linha = ParametroFazenda(
            chave=CHAVE_FINANCEIRO_REGRAS_V2, fazenda_id=fazenda_id,
            grupo=modelo.grupo if modelo else "financeiro", label=modelo.label if modelo else _LABEL_REGRAS_V2,
            tipo="bool", valor="true",
        )
    else:
        linha.valor = "true"
    linha.atualizado_em = datetime.utcnow()
    s.add(linha)


@router.post("/{fazenda_id}/financeiro/preparar")
def preparar_financeiro(
    fazenda_id: int, _: Usuario = Depends(exigir_dono), session: Session = Depends(get_session),
) -> dict:
    # `sessao_sem_recorte_de_fazenda`: o dono opera em fazenda diferente da
    # selecionada no token — sob RLS (PostgreSQL) a sessão da requisição leria
    # "zero lançamentos" por engano e ligaria a flag numa fazenda com histórico.
    # Em SQLite devolve a mesma sessão.
    with sessao_sem_recorte_de_fazenda(session) as s:
        if s.get(Fazenda, fazenda_id) is None:
            raise HTTPException(status_code=404, detail="Fazenda não encontrada")
        tem_financeiro = s.exec(select(ContratoFazendaModulo).where(
            ContratoFazendaModulo.fazenda_id == fazenda_id, ContratoFazendaModulo.modulo == "financeiro",
            ContratoFazendaModulo.ativo == True,  # noqa: E712
        )).first()
        if tem_financeiro is None:
            raise HTTPException(
                status_code=400,
                detail="Esta fazenda não tem o módulo Financeiro no contrato — defina o plano antes de preparar.",
            )

        mensagens: list[str] = []
        fez_algo = False

        # 1. Plano de contas padrão (só se a fazenda não tem nenhuma conta).
        tinha_plano = fazenda_tem_plano_de_contas(s, fazenda_id)
        criadas = 0
        if not tinha_plano:
            criadas += carregar_plano_padrao_rural(s, fazenda_id)
            fez_algo = True
            mensagens.append(
                f"Plano de contas padrão carregado ({criadas} contas). É um rascunho: "
                "peça ao contador para revisar antes de classificar os lançamentos."
            )
        else:
            mensagens.append("A fazenda já tem plano de contas — nada foi alterado nele.")

        # 2. Contas do sistema (Retenções, Vales e adiantamentos).
        garantidas = garantir_contas_do_sistema(s, fazenda_id)
        if garantidas.criadas:
            criadas += len(garantidas.criadas)
            fez_algo = True
            mensagens.append("Contas do sistema criadas: " + ", ".join(garantidas.criadas) + ".")
        elif garantidas.sem_grupo:
            mensagens.append(
                "O plano de contas não tem o grupo 3.03.01 (Pessoal); as contas de retenções e vales "
                "do sistema não foram criadas."
            )

        # 3. Regras v2 — só em fazenda sem nenhum lançamento.
        ja_ligadas = regras_v2_ativas(s, fazenda_id)
        if ja_ligadas:
            ligadas = True
            mensagens.append("As regras novas dos relatórios do Financeiro já estavam ligadas.")
        else:
            total_lancamentos = s.exec(
                select(func.count()).select_from(ContaGerencial).where(ContaGerencial.fazenda_id == fazenda_id)
            ).one()
            if total_lancamentos == 0:
                _ligar_regras_v2(s, fazenda_id)
                ligadas = True
                fez_algo = True
                mensagens.append("Regras novas dos relatórios do Financeiro ligadas desde o primeiro lançamento.")
            else:
                ligadas = False
                mensagens.append(
                    "A fazenda já tem lançamentos: as regras novas dos relatórios NÃO foram ligadas "
                    "(mudam números históricos; ligue em Parâmetros depois de revisar o impacto)."
                )

        if fez_algo:
            s.commit()
        else:
            s.rollback()

        return {
            "plano_contas_carregado": fazenda_tem_plano_de_contas(s, fazenda_id),
            "contas_criadas": criadas,
            "regras_v2_ligadas": ligadas,
            "ja_preparado": not fez_algo,
            "mensagens": mensagens,
        }
