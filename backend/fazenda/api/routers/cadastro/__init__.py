"""
Router de Cadastro (Configurações > Cadastro) — dados mestres que antes viviam
misturados em Lançamentos: ficha do animal, fornecedores/fabricantes/clientes
e metadados de itens de estoque (ensacado/kg por saco/fornecedor) usados pela
Alimentação. Lotes já tinham seu próprio router (lotes.py); Fornecedor e a
ficha do animal gravam nas MESMAS tabelas (Animal, Estoque) usadas em todo o
site — não há tabela paralela/inerte.

Este pacote é o resultado de dividir o antigo `cadastro.py` monolítico
(~4500 linhas cobrindo dezenas de domínios não relacionados) em submódulos
por domínio, mantendo EXATAMENTE os mesmos caminhos/HTTP methods/schemas —
é uma reorganização de arquivos, não uma reescrita. `router` (com o mesmo
prefix="/cadastro", tags=["cadastro"] de sempre) e `router_touros_leitura`
continuam sendo os dois pontos de montagem usados por main.py, e todas as
funções de seed antes importadas de `fazenda.api.routers.cadastro` continuam
disponíveis aqui, reexportadas dos submódulos onde agora vivem.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    animais,
    estoque,
    genetica,
    lida,
    pessoas,
    protocolos_customizados,
    protocolos_sanitarios,
    rh_contratos,
    rh_folha,
    rh_vale_item,
    sanitario,
    servicos,
)
from .animais import seed_motivos_baixa, seed_motivos_venda, seed_racas_grau_sangue
from .estoque import seed_cadastros_estoque, sindicar_conta_gerencial_estoque
from .genetica import (
    atualizar_estoque_semen_202607,
    router_touros_leitura,
    seed_estoque_semen_inicial,
    seed_semen_categorias,
)
from .pessoas import seed_pessoa_robo_milknews, seed_pessoas, seed_tipo_geral, seed_tipos_pessoa
from .protocolos_sanitarios import (
    seed_inducao_lactacao_ativos1_d0,
    seed_protocolos_inducao_lactacao,
    seed_protocolos_sanitarios_curativos,
)
from .rh_folha import _calcular_encargo_projetado
from .sanitario import GATILHOS_EVENTO, configurar_calendario_sanitario_padrao, seed_cadastro_sanitario
from .servicos import seed_servicos, seed_tipos_metodos_servico

router = APIRouter(prefix="/cadastro", tags=["cadastro"])
router.include_router(pessoas.router)
router.include_router(estoque.router)
router.include_router(animais.router)
router.include_router(genetica.router)
router.include_router(sanitario.router)
router.include_router(protocolos_sanitarios.router)
router.include_router(protocolos_customizados.router)
router.include_router(lida.router)
router.include_router(servicos.router)
router.include_router(rh_folha.router)
router.include_router(rh_contratos.router)
router.include_router(rh_vale_item.router)

__all__ = [
    "router",
    "router_touros_leitura",
    "GATILHOS_EVENTO",
    "_calcular_encargo_projetado",
    "seed_pessoas",
    "seed_pessoa_robo_milknews",
    "seed_tipos_pessoa",
    "seed_tipo_geral",
    "seed_motivos_baixa",
    "seed_motivos_venda",
    "seed_racas_grau_sangue",
    "sindicar_conta_gerencial_estoque",
    "seed_cadastros_estoque",
    "seed_cadastro_sanitario",
    "configurar_calendario_sanitario_padrao",
    "seed_protocolos_inducao_lactacao",
    "seed_inducao_lactacao_ativos1_d0",
    "seed_protocolos_sanitarios_curativos",
    "seed_semen_categorias",
    "seed_estoque_semen_inicial",
    "atualizar_estoque_semen_202607",
    "seed_servicos",
    "seed_tipos_metodos_servico",
]
