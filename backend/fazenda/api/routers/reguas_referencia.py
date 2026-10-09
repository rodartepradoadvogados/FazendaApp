"""Financeiro > Relatórios > Réguas de referência: faixas de mercado com fonte e validade.

Os dados vêm de `seed_data/reguas_referencia.json` (rotina mensal: ver
docs/agents/reguas-referencia-mensal.md) e os textos de `seed_data/textos_juridicos.json`.
Nenhum dado de cliente entra nas faixas.

Parecer jurídico de 08/10/2026 (ver docstring de rules/reguas_referencia.py):
- nenhuma faixa numérica sai daqui fora da situação "publicada" (interruptor geral
  `publicacao.liberada`, desligado por padrão; interruptores por régua e por fonte;
  dossiê completo com dupla validação e termos das fontes verificados);
- modal "Entendi" (6.1.3): `GET` devolve `aceite_pendente`; enquanto pendente, as
  faixas ficam ocultas também. `POST /aceite` registra o clique (versão + SHA-256);
- "Reportar erro na faixa" (6.3/7.4): `POST /reportar-erro`.

Dois routers com o MESMO prefixo, porque são montados de jeitos diferentes em main.py:
`router` (leitura) leva a trava de escrita do contador como o resto do Financeiro;
`router_registros` (aceite e reporte de erro) não leva: o contador também precisa
registrar que leu o aviso e poder apontar um erro — nada disso é lançamento.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Usuario
from fazenda.models.juridico import LIMITE_TEXTO_ERRO, ReguaErroReportado
from fazenda.rules import aceites, reguas_referencia
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/financeiro/reguas-referencia", tags=["financeiro"])
router_registros = APIRouter(prefix="/financeiro/reguas-referencia", tags=["financeiro"])


def _aceite(session: Session, user: Usuario, fazenda_id: int | None) -> dict:
    vigente = aceites.texto_vigente("reguas")
    ultimo = aceites.ultimo_aceite(session, user.id, fazenda_id, "reguas", vigente["sha256"])
    return {
        "tipo": "reguas",
        "versao": vigente["versao"],
        "sha256": vigente["sha256"],
        "pendente": ultimo is None,
        "aceito_em_utc": aceites.utc_iso(ultimo.criado_em) if ultimo else None,
    }


@router.get("")
def reguas_de_referencia(
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
):
    fazenda_id = fazenda_id_seguro(fazenda_id)
    aceite = _aceite(session, user, fazenda_id)
    carga = reguas_referencia.publico(ocultar_faixas=aceite["pendente"])
    carga["aceite"] = aceite
    carga["aceite_pendente"] = aceite["pendente"]
    return carga


@router_registros.get("/aceite")
def situacao_do_aceite(
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
):
    """O modal "Entendi" vigente (texto, versão, hash) e se este usuário, nesta
    fazenda, já o aceitou."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    return {"texto": aceites.texto_vigente("reguas"), **_aceite(session, user, fazenda_id)}


class AceiteReguasIn(BaseModel):
    versao: str = Field(min_length=1, max_length=40)
    sha256: str = Field(min_length=64, max_length=64)


@router_registros.post("/aceite", status_code=201)
def aceitar_modal(
    dados: AceiteReguasIn,
    request: Request,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
):
    """Registra o "Entendi" (append-only). Versão e hash precisam ser os vigentes."""
    a = aceites.registrar(
        session, usuario_id=user.id, fazenda_id=fazenda_id, tipo="reguas",
        versao=dados.versao, sha256=dados.sha256, request=request,
    )
    return aceites.como_dict(a)


class ReportarErroIn(BaseModel):
    regua_codigo: str = Field(min_length=1, max_length=60)
    texto: str = Field(min_length=3, max_length=LIMITE_TEXTO_ERRO)


@router_registros.post("/reportar-erro", status_code=201)
def reportar_erro(
    dados: ReportarErroIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
):
    """Botão "Reportar erro na faixa": vai para a fila do operador CowData
    (Painel CowData > Réguas de referência > Erros reportados)."""
    if not isinstance(fazenda_id, int):
        raise HTTPException(status_code=409, detail="O reporte precisa de uma fazenda selecionada. Saia e entre novamente.")
    dados_reguas = reguas_referencia.carregar()
    if dados.regua_codigo not in {r["codigo"] for r in dados_reguas["reguas"]}:
        raise HTTPException(status_code=404, detail="Régua não encontrada")
    linha = ReguaErroReportado(
        fazenda_id=fazenda_id, usuario_id=user.id, regua_codigo=dados.regua_codigo,
        texto=dados.texto.strip(), versao_reguas=reguas_referencia.versao_reguas(dados_reguas),
    )
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return {
        "id": linha.id, "regua_codigo": linha.regua_codigo, "status": linha.status,
        "versao_reguas": linha.versao_reguas, "criado_em_utc": aceites.utc_iso(linha.criado_em),
    }
