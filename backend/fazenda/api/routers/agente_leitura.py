"""\nAPI de LEITURA para agentes externos (Hermes Agent: Telegram + Desktop) —\nprefixo /agente. SOMENTE GET... exceto POST /agente/ensinamentos.\n\n- Desativada por padrão: sem AGENTE_API_TOKEN (>= 32 caracteres) toda rota\n  responde 404, como se não existisse.\n- Auth: `Authorization: Bearer <AGENTE_API_TOKEN>` (comparação em tempo\n  constante). Opcional: AGENTE_IPS_PERMITIDOS, AGENTE_RATE_LIMIT_POR_MIN.\n- Fazenda alvo fixa por AGENTE_FAZENDA_ID (padrão 1); o agente não escolhe.\n- Executa as MESMAS ferramentas `_tool_*` do Assistente do site\n  (fazenda.rules.assistente), numa sessão de banco SOMENTE LEITURA, com a\n  saída sanitizada (sem segredos/dados bancários/e-mails; CPF/CNPJ mascarados)\n  e paginada. Cada chamada é auditada (log `fazenda.agente_auditoria`).\n\nEndpoints: GET /agente/saude · /agente/ferramentas · /agente/instrucoes ·\n/agente/consultar/{ferramenta}?param=...&limite=50&offset=0\nPOST /agente/ensinamentos  (cria ensinamento — ESCRITA)\n"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.database import get_session
from fazenda.models import AssistenteEnsinamento, Fazenda, Usuario
from fazenda.rules import agente_leitura as al
from fazenda.rules import assistente
from fazenda.rules.parametros import fazenda_atual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agente", tags=["agente-leitura"])


@dataclass
class _Contexto:
    ip: str
    inicio: float


def _desativada() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _contexto(request: Request) -> _Contexto:
    """Porteiro de TODAS as rotas: ativação -> IP -> token -> rate limit."""
    if not al.agente_ativado():
        raise _desativada()
    ctx = _Contexto(
        ip=al.ip_do_cliente(request.headers.get("x-forwarded-for"), request.client.host if request.client else None),
        inicio=time.monotonic(),
    )
    nome = request.path_params.get("ferramenta") or request.url.path.removeprefix("/agente/") or "?"
    params = dict(request.query_params)

    def _recusar(status: int, detalhe: str, headers: dict | None = None):
        al.auditar(nome, params, ctx.ip, status, int((time.monotonic() - ctx.inicio) * 1000))
        raise HTTPException(status_code=status, detail=detalhe, headers=headers)

    if not al.ip_permitido(ctx.ip):
        _recusar(403, "Acesso não permitido a partir deste endereço.")
    autorizacao = request.headers.get("authorization")
    if not al.token_valido(autorizacao):
        espera = al.verificar_limite_falhas(ctx.ip)
        if espera:
            _recusar(429, "Muitas tentativas inválidas. Aguarde.", {"Retry-After": str(espera)})
        _recusar(401, "Token inválido ou ausente.", {"WWW-Authenticate": "Bearer"})
    espera = al.verificar_limite_token_valido((autorizacao or "").split(" ", 1)[-1].strip())
    if espera:
        _recusar(429, "Limite de requisições por minuto excedido.", {"Retry-After": str(espera)})
    return ctx


def _sessao_somente_leitura(session: Session = Depends(get_session)):
    # Contexto de fazenda para o RLS (listener `after_begin` em database.py):
    # o `get_session` leria a fazenda de um JWT de usuário, que o agente não
    # tem — então marca a fazenda alvo fixa aqui, antes de abrir a transação.
    session.info["fazenda_id"] = al.fazenda_alvo_id()
    yield from al.sessao_somente_leitura(session)


def _sessao_escrita(session: Session = Depends(get_session)):
    """Sessão COM ESCRITA para endpoints que criam/atualizam (ex.: ensinamentos)."""
    session.info["fazenda_id"] = al.fazenda_alvo_id()
    yield session


@contextmanager
def _auditado(ctx: _Contexto, nome: str, params: dict):
    """Registra a chamada (ferramenta, parâmetros resumidos, IP, status,
    duração) — nunca o token."""
    status = 200
    try:
        yield
    except HTTPException as e:
        status = e.status_code
        raise
    except Exception:
        status = 500
        raise
    finally:
        al.auditar(nome, params, ctx.ip, status, int((time.monotonic() - ctx.inicio) * 1000))


def _usuario_do_agente() -> Usuario:
    """Usuário sintético (NÃO persistido) que as ferramentas esperam. Sem
    AGENTE_MODULOS ele é "admin" (todas as ferramentas, como o dono vê no
    site); com AGENTE_MODULOS vira operador só com esses módulos."""
    modulos = al.modulos_permitidos()
    if modulos is None:
        return Usuario(id=0, username="agente-externo", senha_hash="", papel="admin", ativo=True)
    return Usuario(id=0, username="agente-externo", senha_hash="", papel="operador", ativo=True,
                   permissoes=",".join(sorted(modulos)))


def _ferramentas_expostas() -> dict[str, dict]:
    """nome -> spec, das MESMAS ferramentas do assistente, filtradas por
    AGENTE_MODULOS quando definido."""
    modulos = al.modulos_permitidos()
    return {
        spec["name"]: spec
        for modulo, spec in assistente.todas_as_ferramentas()
        if modulos is None or assistente.modulo_na_lista(modulo, modulos)
    }


def _fazenda_alvo(session: Session) -> int:
    fid = al.fazenda_alvo_id()
    if session.get(Fazenda, fid) is None:
        logger.error("agente_leitura: AGENTE_FAZENDA_ID=%s não existe", fid)
        raise HTTPException(status_code=503, detail="Fazenda alvo do agente não encontrada (verifique AGENTE_FAZENDA_ID).")
    return fid


def _inteiro(params: dict, nome: str, padrao: int) -> int:
    bruto = params.get(nome)
    if bruto is None or bruto == "":
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Parâmetro '{nome}' deve ser um número inteiro.") from None
    if valor < 0:
        raise HTTPException(status_code=400, detail=f"Parâmetro '{nome}' não pode ser negativo.")
    return valor


def _usuario_admin_da_fazenda(session: Session, fazenda_id: int) -> int:
    """Retorna o ID do primeiro usuário admin ativo da fazenda (para FK usuario_id)."""
    # Busca usuários que têm vínculo com a fazenda via UsuarioFazenda e são admin
    from fazenda.models import UsuarioFazenda
    stmt = (
        select(Usuario.id)
        .join(UsuarioFazenda, UsuarioFazenda.usuario_id == Usuario.id)
        .where(
            UsuarioFazenda.fazenda_id == fazenda_id,
            Usuario.papel == "admin",
            Usuario.ativo == True,
        )
        .limit(1)
    )
    resultado = session.exec(stmt).first()
    if resultado is None:
        # Fallback: qualquer admin ativo do sistema
        fallback = session.exec(select(Usuario.id).where(Usuario.papel == "admin", Usuario.ativo == True).limit(1)).first()
        if fallback is None:
            raise HTTPException(status_code=503, detail="Nenhum usuário admin ativo encontrado para atribuir o ensinamento.")
        return fallback
    return resultado


# ---------------------------------------------------------------------------
# Schemas para escrita de ensinamentos (apenas o necessário)
# ---------------------------------------------------------------------------
class EnsinamentoCriarIn(BaseModel):
    titulo: str
    texto: str
    ativo: bool = True


@router.get("/saude")
def saude(request: Request, ctx: _Contexto = Depends(_contexto), session: Session = Depends(_sessao_somente_leitura)) -> dict:
    with _auditado(ctx, "saude", {}):
        fid = _fazenda_alvo(session)
        return {
            "ok": True, "fazenda_id": fid, "somente_leitura": True,
            "ferramentas": len(_ferramentas_expostas()),
            "hora": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


@router.get("/ferramentas")
def ferramentas(request: Request, ctx: _Contexto = Depends(_contexto)) -> dict:
    with _auditado(ctx, "ferramentas", {}):
        return {
            "ferramentas": [
                {"nome": s["name"], "descricao": s.get("description", ""), "parametros": s.get("input_schema", {})}
                for s in _ferramentas_expostas().values()
            ],
            "paginacao": {
                "parametros": {"limite": f"itens por lista (padrão {al.LIMITE_PADRAO}, máximo {al.LIMITE_MAXIMO})",
                               "offset": "quantos itens pular em cada lista (padrão 0)"},
                "observacao": "Se 'truncado' vier true, repita a consulta com offset maior para ver o resto.",
            },
            "somente_leitura": True,
        }


@router.get("/instrucoes")
def instrucoes(request: Request, ctx: _Contexto = Depends(_contexto), session: Session = Depends(_sessao_somente_leitura)) -> dict:
    """System prompt base do Assistente + Ensinamentos ATIVOS da fazenda alvo
    — o treino fica centralizado no CowData (aba Ensinamentos)."""
    with _auditado(ctx, "instrucoes", {}):
        fid = _fazenda_alvo(session)
        texto = assistente._system_prompt(session, fid)
        return {"instrucoes": al.sanitizar(texto), "base": assistente.SYSTEM_PROMPT, "fazenda_id": fid}


@router.get("/consultar/{ferramenta}")
def consultar(
    ferramenta: str,
    request: Request,
    ctx: _Contexto = Depends(_contexto),
    session: Session = Depends(_sessao_somente_leitura),
) -> dict:
    params = dict(request.query_params)
    with _auditado(ctx, ferramenta, params):
        spec = _ferramentas_expostas().get(ferramenta)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"Ferramenta desconhecida: {ferramenta}")
        limite = _inteiro(params, "limite", al.LIMITE_PADRAO)
        offset = _inteiro(params, "offset", 0)
        entrada = {k: v for k, v in params.items() if k not in al.PARAMETROS_RESERVADOS}

        esquema = spec.get("input_schema", {})
        conhecidos = set((esquema.get("properties") or {}).keys())
        desconhecidos = sorted(set(entrada) - conhecidos)
        if desconhecidos:
            raise HTTPException(status_code=400, detail=f"Parâmetro(s) desconhecido(s): {', '.join(desconhecidos)}")
        faltando = [p for p in esquema.get("required", []) if not entrada.get(p)]
        if faltando:
            raise HTTPException(status_code=400, detail=f"Parâmetro(s) obrigatório(s) ausente(s): {', '.join(faltando)}")

        fid = _fazenda_alvo(session)
        # `get_param` (regras que leem parâmetros da fazenda) lê esta variável
        # de contexto — no site vem do token; aqui, da fazenda alvo fixa.
        marca = fazenda_atual.set(fid)
        try:
            resultado = assistente._executar_tool(ferramenta, entrada, session, _usuario_do_agente(), fid)
        except al.SomenteLeituraError:
            logger.warning("agente_leitura: ferramenta %s tentou escrever — bloqueado", ferramenta)
            raise HTTPException(status_code=500, detail="A consulta tentou escrever no banco e foi bloqueada.") from None
        except Exception as e:
            logger.exception("agente_leitura: falha na ferramenta %s", ferramenta)
            raise HTTPException(status_code=500, detail=f"Falha ao executar a consulta ({type(e).__name__}).") from None
        finally:
            fazenda_atual.reset(marca)
            session.rollback()

        envelope = al.paginar(al.sanitizar(resultado), limite, offset, al.max_bytes())
        envelope["ferramenta"] = ferramenta
        return envelope


# ---------------------------------------------------------------------------
# POST /agente/ensinamentos — cria ensinamento (ESCRITA) via AGENTE_API_TOKEN
# ---------------------------------------------------------------------------
@router.post("/ensinamentos")
def criar_ensinamento_agente(
    dados: EnsinamentoCriarIn,
    request: Request,
    ctx: _Contexto = Depends(_contexto),
    session: Session = Depends(_sessao_escrita),
) -> dict:
    """Cria um Ensinamento ativo na fazenda alvo (AGENTE_FAZENDA_ID).
    
    Usa a MESMA autenticação das rotas de leitura (AGENTE_API_TOKEN).
    Requer AGENTE_API_TOKEN válido + IP permitido + rate limit OK.
    Retorna o ID criado para o agente gravar no vault local."""
    with _auditado(ctx, "criar_ensinamento", {"titulo": dados.titulo[:50]}):
        if not dados.titulo.strip() or not dados.texto.strip():
            raise HTTPException(status_code=400, detail="Título e texto são obrigatórios")

        fid = _fazenda_alvo(session)
        usuario_id = _usuario_admin_da_fazenda(session, fid)
        e = AssistenteEnsinamento(
            fazenda_id=fid,
            usuario_id=usuario_id,
            titulo=dados.titulo.strip(),
            texto=dados.texto.strip(),
            ativo=dados.ativo,
        )
        session.add(e)
        session.commit()
        session.refresh(e)
        logger.info("agente_leitura: ensinamento criado id=%s fazenda=%s usuario_id=%s titulo=%s", e.id, fid, usuario_id, dados.titulo[:50])
        return {"id": e.id, "titulo": e.titulo, "ativo": e.ativo, "criado_em": e.criado_em.isoformat()}
