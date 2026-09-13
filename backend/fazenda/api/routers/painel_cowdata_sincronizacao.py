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
from fazenda.database import get_session_manutencao
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
    session: Session = Depends(get_session_manutencao),
) -> dict:
    """AÇÃO DESTRUTIVA NO DESTINO: apaga todo o dado hoje existente na
    fazenda `destino_id` e substitui por uma cópia completa da fazenda
    `origem_id` (corpo `{"origem_id": ...}`). Sentido único — a fazenda de
    origem nunca é alterada. Recusa (409) se o destino não estiver marcado
    `eh_teste=True`, ou se origem e destino forem a mesma fazenda.

    Tudo roda em UMA transação: se qualquer etapa falhar, nada do destino
    fica "meio copiado" — a exceção propaga sem passar pelo `session.commit()`
    abaixo, e `fazenda.database.get_session` fecha a sessão sem commitar
    (comportamento padrão do SQLAlchemy ao devolver a conexão pro pool sem
    commit explícito): a Session inteira reverte.

    BUG CORRIGIDO EM 11/09/2026: esta rota nunca chamava `session.commit()`
    — só `sincronizar_fazenda_teste_destrutivo` dava `session.flush()`, que
    deixa as linhas visíveis PRA MESMA transação (por isso a função sempre
    devolvia a contagem certa, "sucesso"), mas nunca persistia de verdade.
    A cada clique em "Sincronizar", a Fazenda Teste era apagada, recopiada
    por inteiro, e tudo desfeito no fim — sobrava sempre o resíduo de uma
    cópia bem mais antiga (de antes deste bug existir), nunca a cópia atual.
    Todo outro router do projeto chama `session.commit()` explicitamente
    quando quer persistir (462 ocorrências, ver docstring de
    `fazenda/database.py::get_session`); esta rota, desde a primeira versão
    (motor de replicação Fazenda -> Fazenda), nunca chamou.

    SEGUNDO BUG, achado na auditoria de RLS de 11/09/2026, MESMO SINTOMA:
    `Depends(get_session_manutencao)`, não `get_session` — esta rota copia
    linhas de UMA fazenda (`origem_id`) para OUTRA (`destino_id`) na MESMA
    transação, sem nenhuma delas ser "a fazenda selecionada no token" (o
    Painel CowData nunca tem uma). Sob RLS, pela sessão comum, a leitura da
    origem viesse sempre vazia e o DELETE do destino apagasse 0 linhas —
    sem violar nenhuma trava de escrita (não há linha pra inserir), então
    `session.commit()` passaria limpo e a rota devolveria "status": "ok"
    com `linhas_copiadas: 0` — sucesso falso, sem nenhum erro visível.
    `origem_id`/`destino_id`, os dois explícitos nos parâmetros, já são o
    recorte de segurança real; RLS nunca foi a defesa aqui."""
    try:
        resultado = sincronizar_fazenda_teste_destrutivo(session, origem_id=dados.origem_id, destino_id=destino_id)
    except CicloIrreparavelError as exc:
        # Não é erro de uso (409) — é um problema de SCHEMA que a rotina não
        # sabe resolver sozinha (ver docstring da exceção). 500 é o correto:
        # sinaliza que precisa de atenção de quem mexe em modelos, não que o
        # usuário pediu algo inválido.
        raise HTTPException(status_code=500, detail=f"Sincronização abortada — {exc}") from exc

    session.commit()

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
