#!/usr/bin/env python3
"""Cria, no banco SQLite LOCAL e descartável, a fazenda fictícia "Fazenda Vale Verde".

Rodar de dentro de backend/ com DATABASE_URL apontando para um SQLite (nunca produção) e
DEPOIS de o backend ter subido ao menos uma vez (o startup cria as tabelas e os seeds):

    DATABASE_URL=sqlite:////tmp/cowdata-demo/tutorial.db python ../docs/tutoriais-video/ambiente-demo/setup_fazenda.py

O que faz: fazenda + contrato "gold" ativo com os módulos + vínculo do usuário `teste_local`
(contratante) + "Preparar financeiro" oficial (plano de contas rascunho de 73 contas e regras
v2 ligadas) + nome do usuário "Administrador" + `eh_teste = False` (senão o app mostra a faixa
vermelha "AMBIENTE DE TESTE — cópia da fazenda real ..." no topo de todas as telas).

Recusa rodar fora de SQLite.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))  # rodar a partir de backend/
from sqlmodel import Session, select  # noqa: E402

from fazenda.database import engine  # noqa: E402
from fazenda.models import Usuario  # noqa: E402
from fazenda.models.multitenant import Fazenda, UsuarioFazenda  # noqa: E402
from fazenda.models.planos import PLANOS_CATALOGO, ContratoFazenda, ContratoFazendaModulo  # noqa: E402

if engine.url.get_backend_name() != "sqlite":
    sys.exit("ABORTADO: este script só opera em SQLite local.")

NOME = "Fazenda Vale Verde"
with Session(engine) as s:
    u = s.exec(select(Usuario).where(Usuario.username == "teste_local")).first()
    if u is None:
        sys.exit("Crie antes o usuário: python scripts/criar_usuario_teste_local.py")
    f = s.exec(select(Fazenda).where(Fazenda.nome == NOME)).first()
    if f is None:
        f = Fazenda(nome=NOME, cidade="Cidade Exemplo", uf="MG")
        s.add(f)
        s.commit()
        s.refresh(f)
    f.eh_teste = False
    u.nome = "Administrador"
    s.add(f)
    s.add(u)
    if not s.exec(select(UsuarioFazenda).where(UsuarioFazenda.usuario_id == u.id, UsuarioFazenda.fazenda_id == f.id)).first():
        s.add(UsuarioFazenda(usuario_id=u.id, fazenda_id=f.id, contratante=True))
    if not s.exec(select(ContratoFazenda).where(ContratoFazenda.fazenda_id == f.id)).first():
        s.add(ContratoFazenda(fazenda_id=f.id, plano="gold", status="ativo", preco_mensal_fechado=420.0,
                              aprovado_por_usuario_id=u.id, data_fechamento=datetime.utcnow()))
    for m in PLANOS_CATALOGO["gold"]["modulos"]:
        if not s.exec(select(ContratoFazendaModulo).where(ContratoFazendaModulo.fazenda_id == f.id, ContratoFazendaModulo.modulo == m)).first():
            s.add(ContratoFazendaModulo(fazenda_id=f.id, modulo=m, preco=0.0, ativo=True))
    s.commit()
    print("fazenda_id", f.id)

from fazenda.api.routers.financeiro_preparar import preparar_financeiro  # noqa: E402

with Session(engine) as s:
    r = preparar_financeiro(f.id, None, s)  # a função do endpoint "Preparar financeiro", chamada direto
    s.commit()
    print("preparar_financeiro:", {k: r[k] for k in ("plano_contas_carregado", "contas_criadas", "regras_v2_ligadas")})
