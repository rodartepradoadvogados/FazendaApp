"""
Detecção de cio de repasse — regra configurável POR FAZENDA (fatia 10, item C).

Antes, o adesivo/detector ("Scratch") era fixo: 14 dias após o último serviço
(`scratch_pev.DIAS_SCRATCH`), para todo mundo, sempre na Agenda. Agora a fazenda
escolhe: usar ou não, o produto (item de estoque da categoria de produto
"Detecção de cio de repasse"), quantos dias após o serviço fazer a 1ª checagem,
se repete (ciclo estral: 18 a 24 dias é o sugerido), se aparece como tarefa na
Agenda e quais serviços entram (todas | IATF | monta natural).

Compatibilidade: fazenda SEM linha em `repasse_config` continua exatamente como
antes (ligado, 14 dias, todas, com aviso) — `ler_config` devolve esse padrão com
`configurado=False`. Leitura pura: nunca grava (a Agenda só lê).
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from fazenda.models import Estoque, RepasseConfig

CATEGORIA_PRODUTO_REPASSE = "Detecção de cio de repasse"
QUEM_ENTRA = ("todas", "iatf", "monta_natural")
ROTULO_QUEM = {"todas": "Todas as inseminações e montas", "iatf": "Só IATF", "monta_natural": "Só monta natural"}

DIAS_PADRAO = 14
CICLO_SUGERIDO = (18, 24)
LIMITES = {"dias_apos_servico": (1, 60), "repetir_cada_dias": (7, 45), "repeticoes": (1, 4)}


class RepasseError(ValueError):
    """Configuração inválida (vira HTTP 422 no router)."""


def _norm(txt: str | None) -> str:
    base = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in base if not unicodedata.combining(c)).strip().lower()


def categoria_e_repasse(categoria: str | None) -> bool:
    return _norm(categoria) == _norm(CATEGORIA_PRODUTO_REPASSE)


def padrao() -> dict:
    return {
        "usar": True, "estoque_id": None, "dias_apos_servico": DIAS_PADRAO,
        "repetir": False, "repetir_cada_dias": 21, "repeticoes": 1,
        "mostrar_na_agenda": True, "quem_entra": "todas", "configurado": False,
    }


def _linha(session: Session, fazenda_id: int | None) -> RepasseConfig | None:
    return session.exec(select(RepasseConfig).where(RepasseConfig.fazenda_id == fazenda_id)).first()


def ler_config(session: Session, fazenda_id: int | None) -> dict:
    """Configuração vigente da fazenda (ou o padrão legado). Não escreve."""
    linha = _linha(session, fazenda_id)
    cfg = padrao()
    if linha is None:
        return cfg
    for campo in ("usar", "estoque_id", "dias_apos_servico", "repetir", "repetir_cada_dias", "repeticoes",
                  "mostrar_na_agenda", "quem_entra"):
        cfg[campo] = getattr(linha, campo)
    cfg["configurado"] = True
    cfg["atualizado_em"] = linha.atualizado_em.isoformat() if linha.atualizado_em else None
    return cfg


def produto_da_config(session: Session, cfg: dict) -> dict | None:
    """Item de estoque vinculado (nome/saldo/unidade) — só leitura."""
    if not cfg.get("estoque_id"):
        return None
    e = session.get(Estoque, cfg["estoque_id"])
    if e is None:
        return None
    return {"id": e.id, "nome": e.nome, "quantidade": e.quantidade, "unidade": e.unidade}


def produtos_da_categoria(session: Session, fazenda_id: int | None) -> list[dict]:
    """Itens de estoque ATIVOS da fazenda classificados na categoria de produto
    "Detecção de cio de repasse" (`Estoque.categoria` é texto livre)."""
    q = select(Estoque)
    if fazenda_id is not None:
        q = q.where(Estoque.fazenda_id == fazenda_id)
    return [
        {"id": e.id, "nome": e.nome, "quantidade": e.quantidade, "unidade": e.unidade}
        for e in session.exec(q).all()
        if categoria_e_repasse(e.categoria) and e.ativo is not False
    ]


def validar(dados: dict, session: Session, fazenda_id: int | None) -> tuple[dict, list[str]]:
    """Normaliza e valida. Devolve (config limpa, avisos não bloqueantes)."""
    cfg = padrao()
    cfg.pop("configurado")
    for k, v in dados.items():
        if k in cfg and (v is not None or k == "estoque_id"):
            cfg[k] = v
    cfg["usar"] = bool(cfg["usar"])
    cfg["repetir"] = bool(cfg["repetir"])
    cfg["mostrar_na_agenda"] = bool(cfg["mostrar_na_agenda"])
    if cfg["quem_entra"] not in QUEM_ENTRA:
        raise RepasseError("Escolha quem entra: todas, só IATF ou só monta natural.")
    for campo, (lo, hi) in LIMITES.items():
        try:
            cfg[campo] = int(cfg[campo])
        except (TypeError, ValueError):
            raise RepasseError(f"Valor inválido em {campo}.")
        if not lo <= cfg[campo] <= hi:
            rot = {"dias_apos_servico": "Dias após o serviço", "repetir_cada_dias": "Repetir a cada (dias)",
                   "repeticoes": "Quantidade de repetições"}[campo]
            raise RepasseError(f"{rot}: use um valor entre {lo} e {hi}.")
    if cfg["estoque_id"] is not None:
        e = session.get(Estoque, cfg["estoque_id"])
        if e is None or (fazenda_id is not None and e.fazenda_id != fazenda_id):
            raise RepasseError("Produto não encontrado nesta fazenda.")
        if not categoria_e_repasse(e.categoria):
            raise RepasseError(f'O produto precisa estar na categoria "{CATEGORIA_PRODUTO_REPASSE}".')
    avisos: list[str] = []
    if cfg["repetir"] and not CICLO_SUGERIDO[0] <= cfg["repetir_cada_dias"] <= CICLO_SUGERIDO[1]:
        avisos.append(f"O ciclo estral costuma ser de {CICLO_SUGERIDO[0]} a {CICLO_SUGERIDO[1]} dias; "
                      f"você escolheu {cfg['repetir_cada_dias']}.")
    if cfg["usar"] and cfg["estoque_id"] is None:
        avisos.append("Sem produto vinculado: a Agenda avisa a checagem, mas o estoque não é conferido.")
    return cfg, avisos


def salvar_config(session: Session, fazenda_id: int | None, dados: dict, usuario_id: int | None = None) -> tuple[dict, list[str]]:
    cfg, avisos = validar(dados, session, fazenda_id)
    linha = _linha(session, fazenda_id)
    if linha is None:
        linha = RepasseConfig(fazenda_id=fazenda_id)
    for campo, valor in cfg.items():
        setattr(linha, campo, valor)
    linha.atualizado_em = datetime.utcnow()
    linha.atualizado_por_usuario_id = usuario_id
    session.add(linha)
    session.commit()
    return ler_config(session, fazenda_id), avisos


# ── regras de cálculo (puras) ────────────────────────────────────────────────
def eh_monta_natural(servico: dict) -> bool:
    return (servico.get("tipo_servico") or "").strip().lower() == "monta natural" or (servico.get("tipo_semen") or "") == "fazenda"


def eh_iatf(servico: dict) -> bool:
    return not eh_monta_natural(servico) and bool((servico.get("protocolo") or "").strip())


def servico_entra(servico: dict, quem_entra: str) -> bool:
    if quem_entra == "iatf":
        return eh_iatf(servico)
    if quem_entra == "monta_natural":
        return eh_monta_natural(servico)
    return True


def datas_checagem(data_servico: date, cfg: dict) -> list[date]:
    """1ª checagem (serviço + dias) e, se repetir, as seguintes."""
    primeira = data_servico + timedelta(days=int(cfg["dias_apos_servico"]))
    datas = [primeira]
    if cfg.get("repetir"):
        for k in range(1, int(cfg["repeticoes"]) + 1):
            datas.append(primeira + timedelta(days=k * int(cfg["repetir_cada_dias"])))
    return datas


def descricao_checagem(cfg: dict, produto_nome: str | None, indice: int) -> str:
    dias = int(cfg["dias_apos_servico"])
    if indice == 0:
        if produto_nome:
            return f"Aplicar {produto_nome} — detector de cio de repasse, {dias} dias pós-IA"
        if dias == DIAS_PADRAO:
            return "Aplicar Scratch (0,5) — detector de cio, 14 dias pós-IA"
        return f"Aplicar detector de cio de repasse, {dias} dias pós-IA"
    return f"Conferir cio de repasse — {indice + 1}ª checagem (a cada {int(cfg['repetir_cada_dias'])} dias)"


def projetar(servicos: list[dict], cfg: dict, de: date, ate: date) -> list[dict]:
    """Checagens de repasse previstas entre `de` e `ate`, a partir dos serviços
    (um por animal — o último). Só contagem/datas: quem é a vaca não sai daqui.
    Ignora diagnóstico NEGATIVO, prenhez vigente e quem não entra na regra."""
    if not cfg.get("usar"):
        return []
    saida: list[dict] = []
    for s in servicos:
        ds = s.get("data_servico")
        if not ds:
            continue
        diag = (s.get("diagnostico") or "").upper().strip()
        if diag == "NEGATIVO" or (diag == "POSITIVO" and not s.get("data_perda_prenhez")):
            continue
        if not servico_entra(s, cfg["quem_entra"]):
            continue
        for i, d in enumerate(datas_checagem(ds, cfg)):
            if de <= d <= ate:
                saida.append({"data": d, "indice": i, "numero": s.get("numero_matriz")})
    saida.sort(key=lambda x: x["data"])
    return saida
