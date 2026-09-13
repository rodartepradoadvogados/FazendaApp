"""
Login e permissões de um membro da Equipe CowData (ver painel_cowdata.py) no
próprio Painel CowData — eixo à parte do acesso "administrador desta
fazenda" (UsuarioFazenda) ou "dono-equivalente" (EMAILS_DONO_EQUIVALENTE em
fazenda/auth.py). Pedido explícito do usuário (ago/2026): ao cadastrar um
membro, oferecer também um login (Usuario.pessoa_id apontando pra ele) com
duas camadas de permissão — "tipo" (quais áreas do painel ele vê: cockpit,
assinaturas, fazendas, financeiro, equipe, produto, cofre, confianca) e
"permissão de acesso" (o que ele pode FAZER, sobretudo dentro de Fazendas).

Escopo desta primeira etapa: o login existe de verdade (permite entrar) e as
áreas controlam o que aparece no menu do painel; a aplicação das permissões
de "acesso" (suspender assinatura, modificar/suspender plano, emitir
cobranças etc.) nas rotas de fazendas.py compartilhadas com o resto do
sistema ainda não foi migrada rota a rota — só as rotas próprias do Painel
CowData (Equipe, Financeiro CowData, Suporte/Cofre) já checam a área aqui.

Terceiro eixo (#132): `nivel_sigilo` — diferente de "áreas" (o que ele vê NO
Painel CowData) e das 6 sub-permissões (o que ele pode FAZER em Fazendas),
este eixo é sobre o que ele enxerga DENTRO da fazenda-cliente quando abre uma
sessão de suporte pelo Cofre de acesso. Ver NIVEIS_SIGILO_EQUIPE_COWDATA.

Sete permissões de EDIÇÃO no próprio Painel CowData (set/2026) — ver
PERMISSOES_EDICAO_PAINEL_COWDATA. NÃO são um quarto eixo: são o segundo
grupo do MESMO eixo das sub-permissões booleanas ("o que ele pode FAZER"),
só que apontadas para dentro do painel em vez de para dentro das fazendas-
cliente — por isso não penduram em `pode_acessar_fazendas`, que é o portão
do grupo antigo.

Elas existem porque `areas` misturava duas coisas: ter a área "cadastros" ou
"farmacia" dava VER e MEXER de uma vez. O pedido do dono separa os dois —
"consulta: todos podem; editar é que precisa de permissão" — então `areas`
passa a responder só "ele VÊ esta parte do painel?" e a permissão booleana
responde "ele PODE ESCREVER aqui?". Uma nunca substitui a outra: toda rota
de escrita exige as DUAS (ver fazenda.auth.exigir_permissao_painel_cowdata),
para que a permissão nova seja sempre uma camada A MAIS e nunca um caminho
alternativo em volta da checagem de área.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

AREAS_PAINEL_COWDATA = [
    "cockpit", "assinaturas", "fazendas", "financeiro", "equipe", "produto", "cofre", "confianca",
    # Cadastros globais (motivos, raças, unidades de estoque, tipos/métodos
    # reprodutivos) aplicáveis a todas as fazendas-cliente de uma vez ou só
    # às selecionadas — ver fazenda.api.routers.painel_cowdata_cadastros.
    "cadastros",
    # Farmácia padrão CowData (doença/reprodutivo/produtivo/preventivo/
    # suporte, princípios ativos e medicamentos) — cadastro central que se
    # propaga (catálogo global) ou faz fan-out (item de Estoque, um por
    # fazenda) para todas as fazendas-cliente — ver
    # fazenda.api.routers.painel_cowdata_farmacia.
    "farmacia",
]

# Nível de sigilo por conta — QUANTO de uma fazenda-cliente um membro da
# Equipe CowData enxerga quando abre uma sessão de suporte nela (Cofre de
# acesso, ver fazenda/api/routers/cofre_acesso.py), independente das áreas do
# Painel CowData acima (aquilo é sobre o painel interno; isto é sobre o que
# ele vê DENTRO da fazenda do cliente). Do menos para o mais abrangente:
#   "basico"  — operação (rebanho, reprodução, sanidade, produção, estoque);
#               nada financeiro, nem folha/RH, nem contratos, nem custos.
#   "tecnico" — o básico + custos/financeiro operacional (lançamentos,
#               estoque valorado, indicadores de custo); ainda sem folha de
#               pagamento, salários, rescisões, vales nem dados pessoais
#               sensíveis de funcionários.
#   "total"   — sem restrição adicional (equivalente ao acesso de sempre).
# Ver main.py::_bloquear_modo_suporte (aplica o nível tanto à leitura quanto,
# combinado com _PREFIXOS_SENSIVEIS_MODO_SUPORTE, à escrita).
NIVEIS_SIGILO_EQUIPE_COWDATA = ["basico", "tecnico", "total"]

# As sete permissões de EDIÇÃO dentro do próprio Painel CowData (set/2026).
# Cada item é (campo booleano, área que precisa vir junto, rótulo humano).
#
# A área continua sendo o eixo da CONSULTA e a permissão booleana é o eixo da
# ESCRITA; as rotas de escrita exigem as duas (ver
# fazenda.auth.exigir_permissao_painel_cowdata). Nos três primeiros itens a
# assimetria é proposital e foi pedida com estas palavras: consultar cadastros
# globais, touros NAAB e farmácia é livre para quem tem a área; editar exige a
# permissão.
#
# Migração (decisão explícita do dono, set/2026): "ninguém ganha nada; você
# libera depois" — todas nascem DESLIGADAS para todo mundo que já existe, e o
# dono libera uma a uma no cadastro de equipe. O dono-equivalente
# (EMAILS_DONO_EQUIVALENTE) continua passando por cima de tudo, como já era.
PERMISSOES_EDICAO_PAINEL_COWDATA: list[tuple[str, str, str]] = [
    ("pode_editar_cadastros_globais", "cadastros", "Editar cadastros globais"),
    ("pode_editar_touros_naab", "cadastros", "Editar touros NAAB"),
    ("pode_editar_farmacia", "farmacia", "Editar Farmácia"),
    ("pode_consultar_usuarios", "cadastros", "Consultar usuários"),
    ("pode_editar_usuarios", "cadastros", "Editar usuários"),
    ("pode_controlar_acesso_usuarios", "cadastros", "Controle de acesso de usuários CowData"),
    # News não é gateada por área (as rotas de matéria são de `exigir_pode_
    # publicar`, ver fazenda/auth.py) — "cadastros" aqui é só o grupo do menu
    # onde a tela vive; quem aplica esta permissão é exigir_pode_publicar.
    ("pode_editar_news", "cadastros", "Editar News"),
]

CAMPOS_PERMISSAO_EDICAO_PAINEL_COWDATA = [campo for campo, _area, _rotulo in PERMISSOES_EDICAO_PAINEL_COWDATA]

# Padrão para quem já existe (migração) e para qualquer sessão cujo token não
# carregue a claim de nível (token antigo, claim ausente por qualquer motivo)
# — SEMPRE o mais restritivo: nunca abrir acesso por omissão.
NIVEL_SIGILO_PADRAO = "basico"


class PermissaoEquipeCowData(SQLModel, table=True):
    __tablename__ = "permissao_equipe_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", unique=True, index=True)
    areas: str = ""  # CSV de AREAS_PAINEL_COWDATA

    # Ver NIVEIS_SIGILO_EQUIPE_COWDATA acima — carimbado no token da sessão
    # de suporte no momento em que ela abre (fazenda.auth.criar_token), não
    # relido do banco a cada request.
    nivel_sigilo: str = NIVEL_SIGILO_PADRAO

    # "Permissão de acesso" — pode_acessar_fazendas é o portão; os 6
    # seguintes só valem alguma coisa quando ele também está True (checado
    # no formulário e reforçado nas rotas, nunca só num dos dois lados).
    pode_suspender_assinatura: bool = False
    pode_acessar_fazendas: bool = False
    pode_alterar_cadastro: bool = False
    pode_modificar_suspender_plano: bool = False
    pode_emitir_auditar_contratos: bool = False
    pode_emitir_cobrancas: bool = False
    pode_vincular_usuarios: bool = False
    pode_cadastrar_usuarios: bool = False

    # Segundo grupo do mesmo eixo — o que ele pode ESCREVER dentro do próprio
    # Painel CowData (ver PERMISSOES_EDICAO_PAINEL_COWDATA acima). De
    # propósito NÃO penduram em `pode_acessar_fazendas`: aquele portão é sobre
    # entrar na fazenda-cliente, e estas sete são sobre o painel interno.
    pode_editar_cadastros_globais: bool = False
    pode_editar_touros_naab: bool = False
    pode_editar_farmacia: bool = False
    pode_consultar_usuarios: bool = False
    pode_editar_usuarios: bool = False
    pode_controlar_acesso_usuarios: bool = False
    pode_editar_news: bool = False

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
