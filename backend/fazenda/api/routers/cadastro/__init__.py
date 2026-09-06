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

from fastapi import APIRouter, Depends

from fazenda.auth import bloquear_escrita_contador, exigir_modulo, exigir_modulo_contratado

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
    rh_folha_rubricas,
    rh_vale_acoes,
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
from .pessoas import (
    seed_pessoa_robo_milknews, seed_pessoas, seed_tipo_geral, seed_tipos_papel_administrativo, seed_tipos_pessoa,
)
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
# RH/Folha (folha de pagamento, férias, 13º, rescisão, vale, empreitada,
# diária, contrato de trabalho) exige o módulo comercial "financeiro"
# contratado pela fazenda — antes só a permissão genérica "parametros" do
# funcionário (herdada do include deste router inteiro em main.py) travava
# aqui, então RH ficava liberado até no plano Standard. Mesmo grupo de rotas
# já tratado como financeiro-adjacente em main.py::_PREFIXOS_RH_MODO_SUPORTE
# (bloqueio de escrita/leitura em modo suporte) — esta trava só estende essa
# mesma decisão para o módulo contratado.
#
# `exigir_modulo_contratado` só confere se a FAZENDA (tenant) contratou o
# módulo — não confere se o USUÁRIO logado tem a permissão "financeiro" (o
# frontend esconde a tela de Folha de Pagamento de quem só tem "parametros",
# mas sem `exigir_modulo` aqui o backend deixava passar: um operador com
# "parametros" e sem "financeiro" conseguia ler/editar folha, rescisão, vale
# e pagamento de diária/empreita chamando a API direto).
#
# BUG DE SEGURANÇA CORRIGIDO: faltava `bloquear_escrita_contador()` aqui.
# O vínculo `contador` (Painel do Contador, ver
# fazenda/models/multitenant.py::UsuarioFazenda) é documentado como
# "só enxerga Financeiro, sempre em modo leitura/exportação" — mas o Painel
# do Contador só funciona com os módulos 'parametros'+'financeiro' (a mesma
# combinação exigida acima para RH/Folha), então na prática todo contador
# tinha acesso de ESCRITA às rotas de folha/rescisão/vale/diária/contrato de
# trabalho: nada aqui checava o vínculo `contador`, diferente de
# financeiro.router/cartao_credito.router/etc. em main.py, que já aplicam
# `Depends(bloquear_escrita_contador())` no próprio include_router. Mesma
# trava, mesmo lugar (dependência de router, não de endpoint individual) —
# sem inventar mecanismo novo.
_exige_financeiro = [
    Depends(exigir_modulo("financeiro")),
    Depends(exigir_modulo_contratado("financeiro")),
    Depends(bloquear_escrita_contador()),
]
router.include_router(rh_folha.router, dependencies=_exige_financeiro)
router.include_router(rh_contratos.router, dependencies=_exige_financeiro)
# Rubricas do holerite — vencimentos e descontos acrescentados a uma
# competência (ver rh_folha_rubricas.py). Montado DEPOIS de rh_folha
# porque os dois moram sob /folha-pagamento: nenhum caminho colide (aqui
# todos têm três segmentos, /folha-pagamento/{id}/rubricas e
# /folha-pagamento/rubricas/...), e a ordem deixa isso explícito.
router.include_router(rh_folha_rubricas.router, dependencies=_exige_financeiro)
router.include_router(rh_vale_item.router, dependencies=_exige_financeiro)
# Ações do dono sobre um vale já lançado (reparcelar/abater/desconsiderar/
# cancelar) — montado DEPOIS de rh_folha de propósito: ambos moram sob
# /cadastro/vales/{id}, e o router que chega primeiro é o que resolve as
# rotas que ele declara. Nenhum caminho colide (aqui só /vales/{id}/acoes),
# mas a ordem deixa isso explícito.
router.include_router(rh_vale_acoes.router, dependencies=_exige_financeiro)

__all__ = [
    "router",
    "router_touros_leitura",
    "GATILHOS_EVENTO",
    "_calcular_encargo_projetado",
    "seed_pessoas",
    "seed_pessoa_robo_milknews",
    "seed_tipos_pessoa",
    "seed_tipo_geral",
    "seed_tipos_papel_administrativo",
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
