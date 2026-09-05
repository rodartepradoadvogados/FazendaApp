"""
Painel CowData > Fazendas > Sincronizar sandbox — o botão "SINCRONIZAR
FAZENDA JAIRO NASSER COM FAZENDA TESTE": refaz a Fazenda de Teste como uma
cópia completa e atual de uma fazenda-cliente real, para a equipe testar
com dado realista sem tocar em produção.

Toda a lógica de descoberta de tabela, ordenação por FK, remapeamento de id
e travas de segurança mora em fazenda/rules/replicacao_fazenda.py — este
arquivo só valida o pedido HTTP, chama a rotina dentro de uma transação e
formata a resposta. Mesmo padrão exigir_area_painel_cowdata("fazendas") dos
demais routers do Painel CowData (cadastros/parâmetros/usuários/farmácia).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from fazenda.auth import exigir_area_painel_cowdata
from fazenda.database import get_session
from fazenda.models import Fazenda, Usuario
from fazenda.rules.replicacao_fazenda import CicloIrreparavelError, sincronizar_fazenda_teste_destrutivo

router = APIRouter(prefix="/painel-cowdata/fazendas", tags=["painel-cowdata-fazendas"])


class SincronizarIn(BaseModel):
    origem_id: int


@router.post("/{destino_id}/sincronizar")
def sincronizar_fazenda_teste(
    destino_id: int,
    dados: SincronizarIn,
    _user: Usuario = Depends(exigir_area_painel_cowdata("fazendas")),
    session: Session = Depends(get_session),
) -> dict:
    """AÇÃO DESTRUTIVA NO DESTINO: apaga todo o dado hoje existente na
    fazenda `destino_id` e substitui por uma cópia completa da fazenda
    `origem_id` (corpo `{"origem_id": ...}`). Sentido único — a fazenda de
    origem nunca é alterada. Recusa (409) se o destino não estiver marcado
    `eh_teste=True`, ou se origem e destino forem a mesma fazenda.

    Tudo roda em UMA transação: se qualquer etapa falhar, nada do destino
    fica "meio copiado" — a Session inteira reverte (ver
    fazenda.database.get_session, que só dá commit se a rota terminar sem
    exceção)."""
    try:
        resultado = sincronizar_fazenda_teste_destrutivo(session, origem_id=dados.origem_id, destino_id=destino_id)
    except CicloIrreparavelError as exc:
        # Não é erro de uso (409) — é um problema de SCHEMA que a rotina não
        # sabe resolver sozinha (ver docstring da exceção). 500 é o correto:
        # sinaliza que precisa de atenção de quem mexe em modelos, não que o
        # usuário pediu algo inválido.
        raise HTTPException(status_code=500, detail=f"Sincronização abortada — {exc}") from exc

    origem = session.get(Fazenda, dados.origem_id)
    destino = session.get(Fazenda, destino_id)
    return {
        "status": "ok",
        "origem": origem.nome if origem else str(dados.origem_id),
        "destino": destino.nome if destino else str(destino_id),
        "tabelas": resultado.tabelas,
        "linhas_copiadas": resultado.linhas_copiadas,
        "duracao_s": round(resultado.duracao_s, 2),
        "avisos": resultado.avisos,
    }
