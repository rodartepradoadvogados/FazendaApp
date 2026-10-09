"""
Painel CowData > Réguas de referência — o lado do operador (parecer jurídico de
08/10/2026, itens 3.5, 6.1.6 e 7.4).

- `GET  /diagnostico`: situação de cada régua e o que falta para ela ir ao ar
  (dossiê, dupla validação, termos das fontes, interruptores). Só leitura: a régua
  é liberada ou retirada por PR no JSON, nunca por aqui (ver
  docs/agents/reguas-referencia-mensal.md, "Como liberar e como retirar");
- `GET  /erros`: fila do botão "Reportar erro na faixa", de todas as fazendas;
- `PATCH /erros/{id}`: andamento do reporte (em_analise | resolvido | descartado);
- `GET  /aceites/comprovante`: comprovante de aceite de um usuário em uma fazenda,
  para defesa da CowData (item 6.1.6).

Permissões no padrão do Painel: leitura com a área "produto"; escrita e o
comprovante (que traz IP e user-agent) só para o dono-equivalente — não há
permissão de edição própria para esta área (criar uma exigiria migração em
`permissao_equipe_cowdata`).

RLS: `get_session_manutencao`, mesmo motivo de painel_cowdata_parametros.py (o
Painel não tem fazenda selecionada e lê linhas de todas as fazendas).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata, exigir_dono
from fazenda.database import get_session_manutencao
from fazenda.models import Fazenda, Usuario
from fazenda.models.juridico import ReguaErroReportado
from fazenda.rules import aceites, reguas_referencia

router = APIRouter(prefix="/painel-cowdata/reguas-referencia", tags=["painel-cowdata-reguas"])

_dep = Depends(exigir_area_painel_cowdata("produto"))


@router.get("/diagnostico")
def diagnostico(_: Usuario = _dep) -> dict:
    return reguas_referencia.diagnostico()


def _erro_dict(e: ReguaErroReportado, fazendas: dict, usuarios: dict) -> dict:
    u = usuarios.get(e.usuario_id)
    return {
        "id": e.id, "regua_codigo": e.regua_codigo, "texto": e.texto, "versao_reguas": e.versao_reguas,
        "status": e.status, "resposta": e.resposta,
        "fazenda": {"id": e.fazenda_id, "nome": getattr(fazendas.get(e.fazenda_id), "nome", None)},
        "usuario": {"id": e.usuario_id, "username": getattr(u, "username", None)},
        "criado_em_utc": aceites.utc_iso(e.criado_em), "tratado_em_utc": aceites.utc_iso(e.tratado_em),
    }


@router.get("/erros")
def listar_erros(
    status: Optional[str] = None,
    _: Usuario = _dep,
    session: Session = Depends(get_session_manutencao),
) -> list[dict]:
    q = select(ReguaErroReportado)
    if status:
        q = q.where(ReguaErroReportado.status == status)
    linhas = session.exec(q.order_by(ReguaErroReportado.criado_em.desc(), ReguaErroReportado.id.desc()).limit(500)).all()
    fazendas = {f.id: f for f in session.exec(select(Fazenda).where(Fazenda.id.in_({e.fazenda_id for e in linhas}))).all()} if linhas else {}
    usuarios = {u.id: u for u in session.exec(select(Usuario).where(Usuario.id.in_({e.usuario_id for e in linhas}))).all()} if linhas else {}
    return [_erro_dict(e, fazendas, usuarios) for e in linhas]


class AndamentoIn(BaseModel):
    status: Literal["em_analise", "resolvido", "descartado"]
    resposta: Optional[str] = Field(default=None, max_length=2000)


@router.patch("/erros/{erro_id}")
def registrar_andamento(
    erro_id: int, dados: AndamentoIn,
    user: Usuario = Depends(exigir_dono),
    session: Session = Depends(get_session_manutencao),
) -> dict:
    linha = session.get(ReguaErroReportado, erro_id)
    if linha is None:
        raise HTTPException(status_code=404, detail="Reporte não encontrado")
    linha.status = dados.status
    linha.resposta = (dados.resposta or "").strip() or linha.resposta
    linha.tratado_por_usuario_id = user.id
    linha.tratado_em = datetime.utcnow()
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return _erro_dict(linha, {}, {})


@router.get("/aceites/comprovante")
def comprovante(
    usuario_id: int, fazenda_id: int,
    _: Usuario = Depends(exigir_dono),
    session: Session = Depends(get_session_manutencao),
) -> dict:
    alvo = session.get(Usuario, usuario_id)
    if alvo is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return aceites.comprovante(session, alvo, fazenda_id)
