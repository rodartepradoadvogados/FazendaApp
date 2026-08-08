"""
Cadastro > Serviços — Cadastro de Serviços (ServicoCadastro, lançamento
financeiro > produto OU serviço) e o vocabulário de Serviço/Inseminação
(TipoServicoReprodutivo, MetodoServicoReprodutivo).
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import MetodoServicoReprodutivo, SeedFlag, ServicoCadastro, TipoServicoReprodutivo
from fazenda.rules.auditoria import fazenda_id_seguro

from ._comum import _crud_nome_ativo

router = APIRouter()

# ---------------------------------------------------------------------------
# Cadastro de Serviços (lançamento financeiro > produto OU serviço) — ex.:
# manutenção de trator, frete, quilometragem. Lista aberta/extensível.
# ---------------------------------------------------------------------------
SEED_SERVICOS = [
    "Manutenção em tratores", "Manutenção em câmeras", "Frete", "Quilometragem (km)",
    "Manutenção periódica programada de ordenha", "Manutenção extraordinária de ordenha",
    "Revisão em máquinas", "Revisão em equipamentos", "Revisão em implementos",
]

# Serviços de exames — usados no botão "lançar financeiro" do calendário
# sanitário (exames não têm baixa de estoque, viram despesa/serviço). O
# guarda-chuva "Exames" mais as 3 categorias pedidas.
SEED_SERVICOS_EXAMES = [
    "Exames", "Exame de tuberculose", "Exame de brucelose", "Outros exames",
]


def seed_servicos(session: Session) -> None:
    """Cria os serviços padrão (se a tabela estiver vazia) e garante, sempre,
    os serviços de exames — estes por checagem nome a nome, para também
    aparecerem em bancos que já foram semeados antes."""
    if not session.exec(select(ServicoCadastro)).first():
        for nome in SEED_SERVICOS:
            session.add(ServicoCadastro(nome=nome))
        session.commit()
    existentes = {s.nome for s in session.exec(select(ServicoCadastro)).all()}
    novos = [nome for nome in SEED_SERVICOS_EXAMES if nome not in existentes]
    if novos:
        for nome in novos:
            session.add(ServicoCadastro(nome=nome))
        session.commit()



_listar_servicos, _criar_servico, _atualizar_servico, _ = _crud_nome_ativo(ServicoCadastro, com_fazenda=True)
router.get("/servicos")(_listar_servicos)
router.post("/servicos")(_criar_servico)
router.put("/servicos/{item_id}")(_atualizar_servico)


# ---------------------------------------------------------------------------
# Tipo de serviço / Método reprodutivo — cadastro do vocabulário do lançamento
# de Serviço/Inseminação (Lançamentos > Reprodutivo). "Monta Natural",
# "IA em cio natural" e "IATF" são os 3 métodos que o motor de lançamento já
# trata de forma especial (dose de hormônio, protocolo etc.) — por isso vêm
# pré-cadastrados; o usuário pode renomear os rótulos, desativar ou criar
# métodos adicionais (informativos, sem lógica especial própria).
# ---------------------------------------------------------------------------
_listar_tipos_servico, _criar_tipo_servico, _atualizar_tipo_servico, _ = _crud_nome_ativo(TipoServicoReprodutivo, com_fazenda=True)
router.get("/tipos-servico")(_listar_tipos_servico)
router.post("/tipos-servico")(_criar_tipo_servico)
router.put("/tipos-servico/{item_id}")(_atualizar_tipo_servico)


class MetodoServicoIn(BaseModel):
    nome: str
    tipo_servico_id: int
    ativo: bool = True


def _serializar_metodo(m: MetodoServicoReprodutivo, tipos: dict[int, str]) -> dict:
    return {**m.model_dump(), "tipo_servico_nome": tipos.get(m.tipo_servico_id)}


@router.get("/metodos-servico")
def listar_metodos_servico(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_tipos = select(TipoServicoReprodutivo)
    query_metodos = select(MetodoServicoReprodutivo).order_by(MetodoServicoReprodutivo.nome)
    if fazenda_id is not None:
        query_tipos = query_tipos.where(TipoServicoReprodutivo.fazenda_id == fazenda_id)
        query_metodos = query_metodos.where(MetodoServicoReprodutivo.fazenda_id == fazenda_id)
    tipos = {t.id: t.nome for t in session.exec(query_tipos).all()}
    metodos = session.exec(query_metodos).all()
    return [_serializar_metodo(m, tipos) for m in metodos]


@router.post("/metodos-servico")
def criar_metodo_servico(
    dados: MetodoServicoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    tipo = session.get(TipoServicoReprodutivo, dados.tipo_servico_id)
    if not tipo or (fazenda_id is not None and tipo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Tipo de serviço não encontrado")
    query_dup = select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(MetodoServicoReprodutivo.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um método com o nome '{nome}'")
    metodo = MetodoServicoReprodutivo(
        nome=nome, tipo_servico_id=dados.tipo_servico_id, ativo=dados.ativo, fazenda_id=fazenda_id,
    )
    session.add(metodo)
    session.commit()
    session.refresh(metodo)
    tipos = {t.id: t.nome for t in session.exec(select(TipoServicoReprodutivo)).all()}
    return _serializar_metodo(metodo, tipos)


@router.put("/metodos-servico/{item_id}")
def atualizar_metodo_servico(
    item_id: int, dados: MetodoServicoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    metodo = session.get(MetodoServicoReprodutivo, item_id)
    if not metodo or (fazenda_id is not None and metodo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Método não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    tipo = session.get(TipoServicoReprodutivo, dados.tipo_servico_id)
    if not tipo or (fazenda_id is not None and tipo.fazenda_id != fazenda_id):
        raise HTTPException(status_code=400, detail="Tipo de serviço não encontrado")
    metodo.nome = nome
    metodo.tipo_servico_id = dados.tipo_servico_id
    metodo.ativo = dados.ativo
    session.add(metodo)
    session.commit()
    session.refresh(metodo)
    tipos = {t.id: t.nome for t in session.exec(select(TipoServicoReprodutivo)).all()}
    return _serializar_metodo(metodo, tipos)


def seed_tipos_metodos_servico(session: Session, fazenda_id: int | None = None) -> None:
    """Cadastra Cobertura/IA e os 3 métodos já suportados pelo sistema, para a
    `fazenda_id` informada (None = execução legada/global, mantida por
    compatibilidade com bancos antigos de fazenda única). Roda uma vez por
    fazenda (SeedFlag com chave específica) — depois disso os rótulos ficam
    livres para o usuário editar em Configurações > Cadastro. Chamada tanto no
    startup (fazenda #1) quanto no provisionamento de cada fazenda nova (ver
    fazendas.py::provisionar_fazenda_nova) — sem isso, uma fazenda nova nasce
    sem nenhum tipo/método e o lançamento de Serviço/Inseminação fica vazio."""
    chave = f"tipos_metodos_servico_v1_fazenda_{fazenda_id}" if fazenda_id is not None else "tipos_metodos_servico_v1"
    if session.get(SeedFlag, chave):
        return

    def _tipo(nome: str) -> TipoServicoReprodutivo:
        query = select(TipoServicoReprodutivo).where(TipoServicoReprodutivo.nome == nome)
        if fazenda_id is not None:
            query = query.where(TipoServicoReprodutivo.fazenda_id == fazenda_id)
        t = session.exec(query).first()
        if not t:
            t = TipoServicoReprodutivo(nome=nome, fazenda_id=fazenda_id)
            session.add(t)
            session.commit()
            session.refresh(t)
        return t

    cobertura = _tipo("Cobertura")
    ia = _tipo("IA")

    for nome, tipo, codigo in [
        ("Monta Natural", cobertura, "monta_natural"),
        ("IA em cio natural", ia, "cio_natural"),
        ("IATF", ia, "iatf"),
    ]:
        query = select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.nome == nome)
        if fazenda_id is not None:
            query = query.where(MetodoServicoReprodutivo.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(MetodoServicoReprodutivo(
                nome=nome, tipo_servico_id=tipo.id, codigo_interno=codigo, fazenda_id=fazenda_id,
            ))

    session.add(SeedFlag(chave=chave))
    session.commit()


