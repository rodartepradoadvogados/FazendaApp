"""
Pacote /sanitario — API do Sanitário Preventivo v2 (fase F5).

  - `router`: tudo sob o prefixo /sanitario (montado em main.py com a trava
    de fazenda selecionada e o módulo contratado "sanitario");
  - `router_cowdata`: /painel-cowdata/sanitario (catálogo central, cockpit).

Arquivos: cadastro.py (caixas/wizard/catálogo da fazenda/parâmetros),
dias.py (dias marcados, registros, estorno, resultado, conflitos),
consulta.py (painel, janela, calendário, histórico, notas, prazos, leite
separado — só leitura), campo.py (app: hoje, pacote offline, sincronização,
heartbeat), lancamento.py (lançamento simples, ficha, planilha), cockpit.py.
"""
from fastapi import APIRouter

from fazenda.api.routers.sanitario import cadastro, campo, consulta, dias, lancamento
from fazenda.api.routers.sanitario.cockpit import router as router_cowdata

router = APIRouter(prefix="/sanitario")
# A ordem importa: rotas fixas (/dias/simular, /dias/data-prevista) antes das
# com parâmetro (/dias/{dia_id}) — cada sub-router já declara nessa ordem.
router.include_router(cadastro.router)
router.include_router(dias.router)
router.include_router(campo.router)
router.include_router(consulta.router)
router.include_router(lancamento.router)

__all__ = ["router", "router_cowdata"]
