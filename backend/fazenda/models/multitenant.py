"""
Multi-fazenda (piloto conservador) — Fazenda e vínculo Usuario↔Fazenda.

Aditivo e isolado: nenhuma tabela existente foi alterada por causa disto.
Enquanto um usuário tiver só uma fazenda vinculada (o caso de todo mundo hoje,
via backfill da migração a3f7c9d1e246→<esta>), o comportamento do sistema
continua idêntico a antes — login auto-seleciona a única fazenda, sem tela de
escolha, e as consultas que já sabem filtrar por fazenda_id enxergam os mesmos
dados de sempre. A tela de seleção só aparece quando há de fato mais de uma
fazenda vinculada ao mesmo usuário (ex.: um consultor, ou um teste interno).

Ver fazenda/auth.py (token passa a carregar "fid") e
fazenda/api/routers/fazendas.py (cadastro de fazenda + vínculo).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class Fazenda(SQLModel, table=True):
    """Uma propriedade/cliente do sistema. Hoje só existe uma fazenda "real"
    (a que já está em uso diário) — esta tabela nasce com ela mais qualquer
    fazenda de teste criada depois."""

    __tablename__ = "fazenda"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    cidade: Optional[str] = None
    uf: Optional[str] = None
    ativa: bool = True
    criado_em: datetime = Field(default_factory=datetime.utcnow)

    # Dados jurídicos da fazenda-cliente — usados pelo contrato-modelo
    # (fazenda/rules/contrato_render.py) e pela cobrança (Asaas/ZapSign) como
    # padrão, sem precisar redigitar toda vez. Todos opcionais/aditivos.
    documento: Optional[str] = None  # CPF ou CNPJ
    endereco: Optional[str] = None
    representante_nome: Optional[str] = None
    representante_cpf: Optional[str] = None


class EmpresaOperadora(SQLModel, table=True):
    """A empresa de software que opera esta instalação — distinta de cada
    `Fazenda` (cliente/tenant) e distinta da fazenda do próprio dono do
    software, que é só mais uma linha em `Fazenda` como qualquer outra.

    Nasce como um cadastro único (linha id=1), sem CNPJ preenchido — existe
    para servir de âncora estável a quem vier depois (contrato/DPA de
    operador, cabeçalho de e-mail, relatório), sem precisar reconstruir nada
    quando a empresa for formalizada: só preencher `cnpj`. Ver a proposta de
    separação fazenda/empresa (Parte 3.2) para o raciocínio completo."""

    __tablename__ = "empresa_operadora"

    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str
    cnpj: Optional[str] = None
    endereco: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)


class UsuarioFazenda(SQLModel, table=True):
    """Vínculo N:N entre Usuario e Fazenda. Um usuário com mais de um vínculo
    vê a tela de seleção de fazenda ao logar (ver POST /auth/login e
    POST /auth/selecionar-fazenda).

    `contratante` marca o usuário mestre DESTA fazenda — pode gerenciar tudo
    dela (ex.: vincular/desvincular outros usuários, ver
    fazenda/api/routers/fazendas.py::exigir_contratante_ou_dono em auth.py),
    mas não as ações reservadas só ao dono da plataforma (criar fazenda nova,
    administrar News/Blog — ver exigir_dono). Um usuário pode ser contratante
    de mais de uma fazenda (vínculos independentes).

    `consultor` marca um vínculo externo (ex.: veterinário, contador,
    agrônomo) convidado por uma fazenda no plano Diamond — mesmo acesso de um
    funcionário comum dentro dela (não administra a fazenda), mas o vínculo
    só é aceito se a fazenda tiver o módulo comercial "consultor" contratado
    e ativo (ver fazenda/api/routers/fazendas.py::vincular_usuario). Nunca é
    True ao mesmo tempo que `contratante` — são papéis mutuamente exclusivos."""

    __tablename__ = "usuario_fazenda"
    __table_args__ = (UniqueConstraint("usuario_id", "fazenda_id", name="uq_usuario_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    contratante: bool = False
    consultor: bool = False
    criado_em: datetime = Field(default_factory=datetime.utcnow)
