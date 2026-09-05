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
    # Marca a fazenda "lógica" que ancora Pessoa/FolhaPagamento da própria
    # equipe CowData (ver fazenda/api/routers/painel_cowdata.py) — nunca uma
    # fazenda-cliente de verdade. Sempre False para qualquer fazenda real;
    # existe uma única linha com True (seed_cowdata_empresa). Toda listagem
    # de fazendas-clientes (catálogo, MRR, FazendasAdmin) filtra por isto.
    eh_empresa_cowdata: bool = False

    # Marca fazenda de demonstração/sandbox que vive no MESMO banco de
    # produção (ex.: "Fazenda Teste") — distinta de `eh_empresa_cowdata`
    # (aquela é a fazenda "lógica" da própria CowData; esta é uma fazenda de
    # verdade no cadastro, só que não é cliente). Serve de trava dura pra
    # rotina de replicação de dados (só grava em fazenda com eh_teste=True —
    # ver rotina de replicação de outra frente do retrofit) e, no futuro,
    # exclui a fazenda de cobrança/métricas/alertas.
    eh_teste: bool = False

    # Dados jurídicos da fazenda-cliente — usados pelo contrato-modelo
    # (fazenda/rules/contrato_render.py) e pela cobrança (Asaas/ZapSign) como
    # padrão, sem precisar redigitar toda vez. Todos opcionais/aditivos.
    # tipo_documento define ANTES qual máscara/formato vale pra `documento`
    # ("cpf" ou "cnpj") — o cadastro pergunta um dos dois, não deixa livre
    # (ver FazendasAdmin.tsx e lib/masks.ts::maskCpf/maskCnpj).
    tipo_documento: Optional[str] = None  # "cpf" | "cnpj"
    documento: Optional[str] = None
    endereco: Optional[str] = None
    cep: Optional[str] = None
    representante_nome: Optional[str] = None
    representante_cpf: Optional[str] = None

    # Política de acesso de suporte da CowData aos dados desta fazenda (ver
    # fazenda/api/routers/cofre_acesso.py). False (padrão): pedido de acesso
    # já abre a sessão na hora. True: fica "aguardando_aprovacao" até o dono
    # aprovar explicitamente — cada fazenda pode escolher isso no Cofre de
    # acesso (Painel CowData → solicitar acesso a esta fazenda).
    exige_aprovacao_suporte: bool = False

    # Marca a fazenda-sandbox de testes (hoje a única linha com True é
    # "Fazenda Teste", id=2) — espelha eh_empresa_cowdata acima, mas pro
    # outro extremo: em vez de "não é fazenda-cliente", este flag diz "é
    # DESTINO seguro para receber uma cópia destrutiva de outra fazenda".
    # Ver fazenda/rules/replicacao_fazenda.py::sincronizar_fazenda_teste,
    # que RECUSA (409) qualquer destino sem este flag — é a trava dura que
    # impede a rotina de sobrescrever a fazenda-cliente real por engano.
    # NOTA (motor de replicação): este campo está sendo adicionado por outra
    # frente de trabalho via migração Alembic própria; aqui ele só existe no
    # modelo (sem migração) para permitir escrever/testar a rotina de
    # sincronização contra o campo definitivo.
    eh_teste: bool = False


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

    `consultor` marca um vínculo externo (ex.: veterinário, agrônomo)
    convidado por uma fazenda no plano Diamond — mesmo acesso de um
    funcionário comum dentro dela (não administra a fazenda), mas o vínculo
    só é aceito se a fazenda tiver o módulo comercial "consultor" contratado
    e ativo (ver fazenda/api/routers/fazendas.py::vincular_usuario). Nunca é
    True ao mesmo tempo que `contratante` — são papéis mutuamente exclusivos.

    `contador` marca o contador externo da fazenda — vínculo sem gate de
    plano/módulo (disponível em qualquer fazenda), mas de escopo restrito:
    o login cai direto no Painel do Contador (`/contador`, casca própria,
    nunca a navegação normal da fazenda) e só enxerga Financeiro, sempre em
    modo leitura/exportação — toda escrita em `/financeiro/*` é bloqueada
    para esse vínculo (ver fazenda/auth.py::bloquear_escrita_contador).
    Mutuamente exclusivo com `contratante` e `consultor`."""

    __tablename__ = "usuario_fazenda"
    __table_args__ = (UniqueConstraint("usuario_id", "fazenda_id", name="uq_usuario_fazenda"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    fazenda_id: int = Field(foreign_key="fazenda.id", index=True)
    contratante: bool = False
    consultor: bool = False
    contador: bool = False
    criado_em: datetime = Field(default_factory=datetime.utcnow)
