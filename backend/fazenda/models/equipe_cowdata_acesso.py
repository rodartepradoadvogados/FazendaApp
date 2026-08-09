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
]


class PermissaoEquipeCowData(SQLModel, table=True):
    __tablename__ = "permissao_equipe_cowdata"

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", unique=True, index=True)
    areas: str = ""  # CSV de AREAS_PAINEL_COWDATA

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

    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
