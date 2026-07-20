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

from fazenda.database import get_session
from fazenda.models import MetodoServicoReprodutivo, SeedFlag, ServicoCadastro, TipoServicoReprodutivo

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



_listar_servicos, _criar_servico, _atualizar_servico = _crud_nome_ativo(ServicoCadastro)
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
_listar_tipos_servico, _criar_tipo_servico, _atualizar_tipo_servico = _crud_nome_ativo(TipoServicoReprodutivo)
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
def listar_metodos_servico(session: Session = Depends(get_session)) -> list[dict]:
    tipos = {t.id: t.nome for t in session.exec(select(TipoServicoReprodutivo)).all()}
    metodos = session.exec(select(MetodoServicoReprodutivo).order_by(MetodoServicoReprodutivo.nome)).all()
    return [_serializar_metodo(m, tipos) for m in metodos]


@router.post("/metodos-servico")
def criar_metodo_servico(dados: MetodoServicoIn, session: Session = Depends(get_session)) -> dict:
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if not session.get(TipoServicoReprodutivo, dados.tipo_servico_id):
        raise HTTPException(status_code=400, detail="Tipo de serviço não encontrado")
    if session.exec(select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.nome == nome)).first():
        raise HTTPException(status_code=409, detail=f"Já existe um método com o nome '{nome}'")
    metodo = MetodoServicoReprodutivo(nome=nome, tipo_servico_id=dados.tipo_servico_id, ativo=dados.ativo)
    session.add(metodo)
    session.commit()
    session.refresh(metodo)
    tipos = {t.id: t.nome for t in session.exec(select(TipoServicoReprodutivo)).all()}
    return _serializar_metodo(metodo, tipos)


@router.put("/metodos-servico/{item_id}")
def atualizar_metodo_servico(item_id: int, dados: MetodoServicoIn, session: Session = Depends(get_session)) -> dict:
    metodo = session.get(MetodoServicoReprodutivo, item_id)
    if not metodo:
        raise HTTPException(status_code=404, detail="Método não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if not session.get(TipoServicoReprodutivo, dados.tipo_servico_id):
        raise HTTPException(status_code=400, detail="Tipo de serviço não encontrado")
    metodo.nome = nome
    metodo.tipo_servico_id = dados.tipo_servico_id
    metodo.ativo = dados.ativo
    session.add(metodo)
    session.commit()
    session.refresh(metodo)
    tipos = {t.id: t.nome for t in session.exec(select(TipoServicoReprodutivo)).all()}
    return _serializar_metodo(metodo, tipos)


def seed_tipos_metodos_servico(session: Session) -> None:
    """Cadastra Cobertura/IA e os 3 métodos já suportados pelo sistema. Roda
    uma vez (SeedFlag) — depois disso os rótulos ficam livres para o usuário
    editar em Configurações > Cadastro."""
    chave = "tipos_metodos_servico_v1"
    if session.get(SeedFlag, chave):
        return

    def _tipo(nome: str) -> TipoServicoReprodutivo:
        t = session.exec(select(TipoServicoReprodutivo).where(TipoServicoReprodutivo.nome == nome)).first()
        if not t:
            t = TipoServicoReprodutivo(nome=nome)
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
        if not session.exec(select(MetodoServicoReprodutivo).where(MetodoServicoReprodutivo.nome == nome)).first():
            session.add(MetodoServicoReprodutivo(nome=nome, tipo_servico_id=tipo.id, codigo_interno=codigo))

    session.add(SeedFlag(chave=chave))
    session.commit()


