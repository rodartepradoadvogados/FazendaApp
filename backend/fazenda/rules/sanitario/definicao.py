"""
Definição de caixa (o "payload" do cadastro) -> linhas de caixa/versão.

O mesmo formato serve ao catálogo central (`sanitario_catalogo_versao.
definicao`), ao wizard (F5/F6) e ao padrão de fábrica. Chaves aceitas:
`CAMPOS_CAIXA` (identificação) + `CAMPOS_VERSAO` (regras) + as três
referências que só o catálogo usa, por não conhecer os IDs da fazenda:

  - `categorias`: lista de IDs de categoria_manejo (wizard);
  - `categorias_ref`: trechos de NOME de categoria (catálogo) — resolvidos
    para os IDs da fazenda na ativação (sem acento, minúsculo, "contém");
  - `pub_hist_catalogo_chave`: "já/nunca recebeu" apontando para o item do
    catálogo — resolvido para a caixa da fazenda que veio dele;
  - `fallback_idade_min_dias`: usado quando nenhuma categoria casou (a caixa
    nasce inativa e a observação pede revisão).

Regras: criar caixa só aqui (o wizard e o catálogo chamam isto); aplicar
NUNCA cria caixa. Editar = versão nova a partir de hoje; a anterior fica.
Nada aqui dá commit.
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local

CAMPOS_CAIXA = ("nome", "nome_curto", "tipo", "obrigatoria")
CAMPOS_VERSAO = (
    "produto_modo", "estoque_id", "produto_texto", "dose_valor", "dose_unidade", "dose_x_kg", "peso_ausente",
    "pub_sexo", "pub_cat_modo", "pub_idade_min_dias", "pub_idade_max_dias", "pub_condicoes", "pub_hist_tipo",
    "pub_hist_caixa_id",
    "jan_usa_evento", "evento_tipo", "evento_de_dias", "evento_ate_dias", "jan_usa_periodo", "periodo_modo",
    "periodo_grupos", "periodo_anos", "periodo_ano_base", "data_base_dia", "comecar_em", "ao_fechar", "serie",
    "aglo_min", "aviso_antecedencia_dias", "aviso_fim_janela_dias", "push_admin",
    "legal_crmv_pedir", "legal_atestado", "legal_comprovacao", "legal_leitura", "legal_reagente_aviso",
    "legal_marca_texto",
    "car_leite_dias", "car_carne_dias", "car_modo_leite",
    "ficha_colunas", "observacao",
)
REFERENCIAS = ("categorias", "categorias_ref", "pub_hist_catalogo_chave", "fallback_idade_min_dias")
SEED_PADRAO = "sanitario_padrao_v1:{fazenda_id}"
FICHA_PADRAO_VACINA = ["brinco", "categoria", "idade", "dose", "aplicado", "obs"]
FICHA_PADRAO_EXAME = ["brinco", "categoria", "idade", "resultado", "obs"]


def normalizar(txt: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", (txt or "").strip().lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def resolver_categorias(session: Session, fazenda_id: int, refs: list[str]) -> list[int]:
    from fazenda.models import CategoriaManejo

    alvos = [normalizar(r) for r in refs if r and r.strip()]
    if not alvos:
        return []
    cats = session.exec(select(CategoriaManejo).where(
        CategoriaManejo.fazenda_id == fazenda_id, CategoriaManejo.ativo == True,  # noqa: E712
    )).all()
    return sorted(c.id for c in cats if any(alvo in normalizar(c.nome) for alvo in alvos))


def _versao_kwargs(definicao: dict) -> dict:
    kw: dict[str, Any] = {k: definicao[k] for k in CAMPOS_VERSAO if k in definicao}
    if isinstance(kw.get("comecar_em"), str):
        kw["comecar_em"] = date.fromisoformat(kw["comecar_em"])
    for k in ("pub_condicoes", "periodo_grupos", "serie", "ficha_colunas"):
        if kw.get(k) is None:
            kw.pop(k, None)
    return kw


def _resolver_referencias(session: Session, fazenda_id: int, definicao: dict) -> tuple[dict, list[int], list[str]]:
    """Devolve (kwargs da versão, ids de categoria, avisos)."""
    from fazenda.models import SanitarioCaixa, SanitarioCatalogo

    kw = _versao_kwargs(definicao)
    avisos: list[str] = []
    cats = [int(c) for c in (definicao.get("categorias") or [])]
    refs = definicao.get("categorias_ref") or []
    if refs and not cats:
        cats = resolver_categorias(session, fazenda_id, refs)
        if not cats:
            avisos.append("Nenhuma categoria da fazenda casou com o público do catálogo: revise o público.")
            if definicao.get("fallback_idade_min_dias") is not None and kw.get("pub_idade_min_dias") is None:
                kw["pub_idade_min_dias"] = int(definicao["fallback_idade_min_dias"])
            if kw.get("pub_cat_modo") == "incluir" and definicao.get("fallback_idade_min_dias") is None:
                avisos.append("Sem categoria resolvida, o público ficaria aberto a todos.")
    chave = definicao.get("pub_hist_catalogo_chave")
    if chave and not kw.get("pub_hist_caixa_id"):
        cx = session.exec(
            select(SanitarioCaixa).join(SanitarioCatalogo, SanitarioCatalogo.id == SanitarioCaixa.catalogo_id).where(
                SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCatalogo.chave == chave,
                SanitarioCaixa.estado != "arquivada",
            )
        ).first()
        if cx is not None:
            kw["pub_hist_caixa_id"] = cx.id
        else:
            avisos.append(f"Histórico vacinal aponta para '{chave}', que não existe na fazenda: revise o público.")
            kw.pop("pub_hist_tipo", None)
    if not kw.get("ficha_colunas"):
        kw["ficha_colunas"] = list(FICHA_PADRAO_EXAME if definicao.get("tipo") == "exame" else FICHA_PADRAO_VACINA)
    return kw, cats, avisos


def definicao_resolvida(session: Session, fazenda_id: int, definicao: dict) -> tuple[dict, list[str]]:
    """A definição do catálogo já no formato do wizard da fazenda (categorias
    por ID, "já/nunca recebeu" pela caixa) — SÓ LÊ. Usado pelo wizard "Do
    catálogo", que só cria a cópia ao concluir."""
    kw, cats, avisos = _resolver_referencias(session, fazenda_id, definicao)
    out: dict[str, Any] = {k: definicao.get(k) for k in CAMPOS_CAIXA if k in definicao}
    out.update(kw)
    if isinstance(out.get("comecar_em"), date):
        out["comecar_em"] = out["comecar_em"].isoformat()
    out["categorias"] = cats
    return out, avisos


def _gravar_versao(session: Session, caixa, numero: int, definicao: dict, vigente_desde: date,
                   usuario_id: Optional[int]) -> tuple:
    from fazenda.models import SanitarioCaixaVersao, SanitarioCaixaVersaoCategoria

    kw, cats, avisos = _resolver_referencias(session, caixa.fazenda_id, definicao)
    if avisos:
        kw["observacao"] = " ".join(filter(None, [kw.get("observacao"), *avisos]))
    v = SanitarioCaixaVersao(
        fazenda_id=caixa.fazenda_id, caixa_id=caixa.id, numero=numero, vigente_desde=vigente_desde,
        criado_por_usuario_id=usuario_id, **kw,
    )
    session.add(v)
    session.flush()
    for cid in cats:
        session.add(SanitarioCaixaVersaoCategoria(fazenda_id=caixa.fazenda_id, versao_id=v.id, categoria_manejo_id=cid))
    return v, avisos


def criar_caixa(
    session: Session, fazenda_id: int, definicao: dict, *, estado: str = "inativa",
    catalogo_id: Optional[int] = None, catalogo_versao: Optional[int] = None, padrao_fabrica: bool = False,
    usuario_id: Optional[int] = None, hoje: Optional[date] = None,
):
    """Cria a caixa + versão 1. Única porta de criação de caixa."""
    from fazenda.models import SanitarioCaixa, SanitarioLog

    hoje = hoje or hoje_local()
    nome = (definicao.get("nome") or "").strip()
    if not nome:
        raise ValueError("A caixa precisa de um nome.")
    caixa = SanitarioCaixa(
        fazenda_id=fazenda_id, nome=nome, nome_normalizado=normalizar(nome),
        nome_curto=(definicao.get("nome_curto") or nome).strip(), tipo=definicao.get("tipo") or "vacina",
        estado=estado, obrigatoria=bool(definicao.get("obrigatoria")), padrao_fabrica=padrao_fabrica,
        catalogo_id=catalogo_id, catalogo_versao=catalogo_versao,
        ativada_em=hoje if estado == "ativa" else None, criado_por_usuario_id=usuario_id,
    )
    session.add(caixa)
    session.flush()
    v, avisos = _gravar_versao(session, caixa, 1, definicao, hoje, usuario_id)
    caixa.versao_atual_id = v.id
    session.add(caixa)
    session.add(SanitarioLog(
        fazenda_id=fazenda_id, tipo="caixa.versao", caixa_id=caixa.id, usuario_id=usuario_id,
        texto_livre=f"Caixa criada (versão 1){' a partir do catálogo' if catalogo_id else ''}.",
        payload={"avisos": avisos} if avisos else None,
    ))
    session.flush()
    return caixa


def nova_versao(session: Session, caixa, definicao: dict, *, usuario_id: Optional[int] = None,
                hoje: Optional[date] = None):
    """Editar a caixa: fecha a versão vigente ontem e cria a próxima a partir
    de hoje. A versão antiga fica intocada (o histórico aponta para ela)."""
    from fazenda.models import SanitarioCaixaVersao, SanitarioLog

    hoje = hoje or hoje_local()
    atual = session.get(SanitarioCaixaVersao, caixa.versao_atual_id) if caixa.versao_atual_id else None
    numero = (atual.numero + 1) if atual else 1
    if atual is not None:
        atual.vigente_ate = hoje - timedelta(days=1)
        session.add(atual)
    for k in CAMPOS_CAIXA:
        if k in definicao and k != "nome":
            setattr(caixa, k, definicao[k])
    if definicao.get("nome"):
        caixa.nome = definicao["nome"].strip()
        caixa.nome_normalizado = normalizar(caixa.nome)
    v, avisos = _gravar_versao(session, caixa, numero, definicao, hoje, usuario_id)
    caixa.versao_atual_id = v.id
    session.add(caixa)
    session.add(SanitarioLog(
        fazenda_id=caixa.fazenda_id, tipo="caixa.versao", caixa_id=caixa.id, usuario_id=usuario_id,
        texto_livre=f"Versão {numero} vigente a partir de {hoje.strftime('%d/%m/%Y')}.",
        payload={"avisos": avisos} if avisos else None,
    ))
    session.flush()
    return v


def ativar_do_catalogo(session: Session, fazenda_id: int, catalogo_versao_id: int, *, estado: str = "inativa",
                       usuario_id: Optional[int] = None, padrao_fabrica: bool = False, hoje: Optional[date] = None,
                       definicao: Optional[dict] = None):
    """Copia a definição de uma versão do catálogo central para uma caixa da
    fazenda. `definicao` (wizard): a cópia já ajustada pelo administrador."""
    from fazenda.models import SanitarioCatalogo, SanitarioCatalogoVersao

    cv = session.get(SanitarioCatalogoVersao, catalogo_versao_id)
    if cv is None:
        raise ValueError("Versão de catálogo inexistente.")
    cat = session.get(SanitarioCatalogo, cv.catalogo_id)
    return criar_caixa(
        session, fazenda_id, dict(definicao if definicao is not None else (cv.definicao or {})), estado=estado,
        catalogo_id=cat.id,
        catalogo_versao=cv.versao, padrao_fabrica=padrao_fabrica, usuario_id=usuario_id, hoje=hoje,
    )


def garantir_parametros(session: Session, fazenda_id: int):
    from fazenda.models import Fazenda, SanitarioParametros

    p = session.exec(select(SanitarioParametros).where(SanitarioParametros.fazenda_id == fazenda_id)).first()
    if p is None:
        faz = session.get(Fazenda, fazenda_id)
        p = SanitarioParametros(fazenda_id=fazenda_id, uf=(faz.uf if faz else None))
        session.add(p)
        session.flush()
    return p


def criar_padrao_fabrica(session: Session, fazenda_id: int, hoje: Optional[date] = None) -> int:
    """Padrão de fábrica (B19, exame de tuberculose, exame de brucelose) para
    UMA fazenda, a partir do catálogo central — INATIVAS, uma única vez
    (marca `seed_flag`): apagar/arquivar depois nunca faz voltar. Chamado na
    criação de fazenda (fazendas.py) — nunca no boot. Fazendas que já
    existiam em 21/10/2026 receberam pela migração s1n2o3v4o5m6."""
    from fazenda.models import SanitarioCatalogo, SanitarioCatalogoVersao, SeedFlag

    chave = SEED_PADRAO.format(fazenda_id=fazenda_id)
    garantir_parametros(session, fazenda_id)
    if session.get(SeedFlag, chave) is not None:
        return 0
    itens = session.exec(select(SanitarioCatalogo).where(
        SanitarioCatalogo.padrao_fabrica == True, SanitarioCatalogo.ativo == True,  # noqa: E712
    ).order_by(SanitarioCatalogo.id)).all()
    if not itens:
        return 0  # catálogo ainda vazio: não marca a flag, para não perder o padrão
    n = 0
    for it in itens:
        cv = session.exec(select(SanitarioCatalogoVersao).where(
            SanitarioCatalogoVersao.catalogo_id == it.id, SanitarioCatalogoVersao.versao == it.versao_atual,
        )).first()
        if cv is None:
            continue
        ativar_do_catalogo(session, fazenda_id, cv.id, estado="inativa", padrao_fabrica=True, hoje=hoje)
        n += 1
    session.add(SeedFlag(chave=chave, aplicado_em=datetime.utcnow()))
    session.flush()
    return n
