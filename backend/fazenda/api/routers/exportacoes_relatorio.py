"""Exportação e compartilhamento de relatórios (parecer jurídico de 08/10/2026, item 6.2).

O front chama `POST /relatorios/exportacoes` ANTES de gerar o arquivo (PDF/planilha)
ou o link, e só gera se a resposta for 201. A resposta traz o rodapé automático
(texto 7.5) já preenchido, que o arquivo leva NO MESMO BLOCO da régua e sem opção de
remover.

Regras:
- sem réguas (`com_reguas: false`): sempre permitido; fica registrado no log;
- com réguas: exige o parâmetro da fazenda `permitir_exportar_com_reguas` (padrão
  desligado; só o administrador liga em Configurações > Parâmetros) — senão 403;
  exige destinatário, finalidade e a confirmação "Autorizo o envio deste relatório a
  [destinatário]" — senão 400; exige que o usuário já tenha aceitado o modal das
  réguas e que haja régua publicada — senão 409.
- `GET /relatorios/exportacoes`: o log da fazenda, só para administrador.

O log (`exportacao_relatorio_log`) é append-only: é ele que permite avisar quem
exportou se uma faixa estiver errada (política 7.4, item 5).
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Usuario
from fazenda.models.juridico import ExportacaoRelatorioLog
from fazenda.rules import aceites, reguas_referencia, textos_juridicos
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.datas import agora_local
from fazenda.rules.parametros import exportar_com_reguas_permitido

router = APIRouter(prefix="/relatorios/exportacoes", tags=["relatorios"])

ERRO_PARAMETRO_DESLIGADO = (
    "A exportação de relatórios com réguas de referência está desligada nesta fazenda. "
    "O administrador pode ligá-la em Configurações > Parâmetros. Você pode exportar sem as réguas."
)


class ExportacaoIn(BaseModel):
    relatorio: str = Field(min_length=1, max_length=120)
    formato: Optional[Literal["pdf", "xlsx", "csv", "link"]] = None
    com_reguas: bool = False
    destinatario: Optional[str] = Field(default=None, max_length=200)
    destinatario_tipo: Optional[Literal["banco", "contador", "comprador", "outro"]] = None
    finalidade: Optional[str] = Field(default=None, max_length=300)
    autorizacao_confirmada: bool = False


def _limpo(v: Optional[str]) -> Optional[str]:
    v = " ".join((v or "").split())
    return v or None


def _como_dict(e: ExportacaoRelatorioLog, usuario: Optional[Usuario] = None) -> dict:
    d = {
        "id": e.id, "relatorio": e.relatorio, "formato": e.formato, "com_reguas": e.com_reguas,
        "destinatario": e.destinatario, "destinatario_tipo": e.destinatario_tipo, "finalidade": e.finalidade,
        "autorizacao_confirmada": e.autorizacao_confirmada, "versao_reguas": e.versao_reguas,
        "rodape_versao": e.rodape_versao, "rodape_sha256": e.rodape_sha256,
        "usuario_id": e.usuario_id, "criado_em_utc": aceites.utc_iso(e.criado_em),
    }
    if usuario is not None:
        d["usuario"] = {"id": usuario.id, "username": usuario.username, "nome": usuario.nome}
    return d


@router.post("", status_code=201)
def registrar_exportacao(
    dados: ExportacaoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_id_escrita),
) -> dict:
    if not isinstance(fazenda_id, int):
        raise HTTPException(status_code=409, detail="A exportação precisa de uma fazenda selecionada. Saia e entre novamente.")
    destinatario, finalidade = _limpo(dados.destinatario), _limpo(dados.finalidade)
    rodape = None
    versao = None
    if dados.com_reguas:
        if not exportar_com_reguas_permitido(session, fazenda_id):
            raise HTTPException(status_code=403, detail=ERRO_PARAMETRO_DESLIGADO)
        if not destinatario or not finalidade:
            raise HTTPException(status_code=400, detail="Para exportar com réguas, informe o destinatário e a finalidade.")
        if not dados.autorizacao_confirmada:
            raise HTTPException(status_code=400, detail="Confirme a autorização de envio ao destinatário.")
        if aceites.aceite_pendente(session, user.id, fazenda_id, "reguas"):
            raise HTTPException(status_code=409, detail="Leia e confirme o aviso das réguas de referência antes de exportá-las.")
        dados_reguas = reguas_referencia.carregar()
        if not reguas_referencia.alguma_publicada(dados_reguas):
            raise HTTPException(status_code=409, detail="Não há régua de referência publicada. Exporte sem as réguas.")
        versao = reguas_referencia.versao_reguas(dados_reguas)
        rodape = textos_juridicos.descrever("reguas_rodape_exportacao", {
            "gerado_em": agora_local().strftime("%d/%m/%Y %H:%M") + " (horário de Brasília)",
            "usuario": user.nome or user.username,
            "destinatario": destinatario,
            "versao_reguas": versao,
        })
    linha = ExportacaoRelatorioLog(
        fazenda_id=fazenda_id, usuario_id=user.id, relatorio=dados.relatorio.strip(), formato=dados.formato,
        com_reguas=dados.com_reguas, destinatario=destinatario, destinatario_tipo=dados.destinatario_tipo,
        finalidade=finalidade, autorizacao_confirmada=bool(dados.autorizacao_confirmada),
        versao_reguas=versao, rodape_versao=rodape["versao"] if rodape else None,
        rodape_sha256=rodape["sha256"] if rodape else None,
    )
    session.add(linha)
    session.commit()
    session.refresh(linha)
    return {**_como_dict(linha), "rodape": rodape}


@router.get("")
def listar_exportacoes(
    limite: int = 200,
    session: Session = Depends(get_session),
    _: Usuario = Depends(exigir_admin),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is None:
        return []
    linhas = session.exec(
        select(ExportacaoRelatorioLog).where(ExportacaoRelatorioLog.fazenda_id == fazenda_id)
        .order_by(ExportacaoRelatorioLog.criado_em.desc(), ExportacaoRelatorioLog.id.desc())
        .limit(max(1, min(limite, 1000)))
    ).all()
    usuarios = {u.id: u for u in session.exec(select(Usuario).where(Usuario.id.in_({e.usuario_id for e in linhas}))).all()} if linhas else {}
    return [_como_dict(e, usuarios.get(e.usuario_id)) for e in linhas]
