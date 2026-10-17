"""
Detecção de cio de repasse — regra configurável POR FAZENDA (fatia 10, item C).

Antes, o adesivo/detector ("Scratch") era fixo: 14 dias após o último serviço
(`scratch_pev.DIAS_SCRATCH`), para todo mundo, sempre na Agenda. Agora a fazenda
escolhe: usar ou não, o produto (item de estoque da categoria de produto
"Detecção de cio de repasse"), quantos dias após o serviço fazer a 1ª checagem,
se repete (ciclo estral: 18 a 24 dias é o sugerido), se aparece como tarefa na
Agenda e quais serviços entram (todas | IATF | monta natural).

Fonte única (17/10/2026): a chave mestra "Utiliza adesivos para detecção de cio de repasse?" de Parâmetros ›
Reinseminação e observação de cio É o campo `usar` desta configuração — liga/desliga o aviso na Agenda, a lista
"Observação de cio" e o método "Cio de repasse" do diagnóstico. "Avisar na agenda após [x] dias" vazio = não avisar
(`mostrar_na_agenda=False`). Os produtos vinculados são vários itens de estoque (`estoque_ids_json`); sem nenhum, a
escolha do produto é livre. Item de estoque apagado ou inativo sai da seleção sozinho, sem travar nada.

Fazenda SEM linha em `repasse_config`: o padrão passa a depender da chave mestra antiga (parâmetro
`usa_adesivo_deteccao_cio`, padrão NÃO). Antes o aviso de 14 dias caía na Agenda mesmo com o parâmetro desligado — quem
nunca configurou e não usa adesivo deixa de receber o aviso; quem usa (parâmetro ligado) segue com 14 dias, todas as
inseminações e aviso na Agenda. `ler_config` devolve esse padrão com `configurado=False`. Leitura pura: nunca grava.
"""
from __future__ import annotations

import json
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
        "usar": True, "estoque_id": None, "estoque_ids": [], "dias_apos_servico": DIAS_PADRAO,
        "repetir": False, "repetir_cada_dias": 21, "repeticoes": 1,
        "mostrar_na_agenda": True, "quem_entra": "todas", "configurado": False,
    }


def _linha(session: Session, fazenda_id: int | None) -> RepasseConfig | None:
    return session.exec(select(RepasseConfig).where(RepasseConfig.fazenda_id == fazenda_id)).first()


def _ids_da_linha(linha: RepasseConfig) -> list[int]:
    """Ids dos produtos vinculados: a lista nova (`estoque_ids_json`) ou, em linha antiga, o `estoque_id` único."""
    try:
        ids = [int(x) for x in json.loads(linha.estoque_ids_json or "[]")]
    except (ValueError, TypeError):
        ids = []
    if not ids and linha.estoque_id:
        ids = [linha.estoque_id]
    return ids


def ler_config(session: Session, fazenda_id: int | None) -> dict:
    """Configuração vigente da fazenda (ou o padrão). Não escreve.

    Sem linha salva: `usar` segue o parâmetro `usa_adesivo_deteccao_cio` (padrão NÃO) — ver o topo do módulo.
    Os campos `avisar_apos_dias` (None = não avisar) e `estoque_ids` são a visão que Parâmetros mostra."""
    from fazenda.rules.parametros import get_param_bool

    linha = _linha(session, fazenda_id)
    cfg = padrao()
    if linha is None:
        cfg["usar"] = get_param_bool("usa_adesivo_deteccao_cio", False)
        cfg["mostrar_na_agenda"] = cfg["usar"]
    else:
        for campo in ("usar", "estoque_id", "dias_apos_servico", "repetir", "repetir_cada_dias", "repeticoes",
                      "mostrar_na_agenda", "quem_entra"):
            cfg[campo] = getattr(linha, campo)
        cfg["estoque_ids"] = _ids_da_linha(linha)
        cfg["configurado"] = True
        cfg["atualizado_em"] = linha.atualizado_em.isoformat() if linha.atualizado_em else None
    cfg["avisar_apos_dias"] = cfg["dias_apos_servico"] if cfg["mostrar_na_agenda"] else None
    return cfg


def usa_adesivo_vigente(session: Session | None = None) -> bool:
    """O adesivo está em uso na fazenda do pedido atual? Quem decide é a configuração de repasse salva (chave mestra
    de Parâmetros); sem ela, o parâmetro `usa_adesivo_deteccao_cio` (padrão NÃO). Lê pelo contexto da requisição
    (como `get_param`), então serve para as regras que não recebem sessão; quem já tem a sessão da requisição a
    passa para não abrir outra."""
    from sqlalchemy.exc import OperationalError, ProgrammingError

    import fazenda.database as database
    from fazenda.rules.parametros import fazenda_atual, get_param_bool

    fid = fazenda_atual.get()
    try:
        if session is not None:
            linha = _linha(session, fid)
        else:
            with Session(database.engine) as propria:
                propria.info["fazenda_id"] = fid
                linha = _linha(propria, fid)
        if linha is not None:
            return bool(linha.usar)
    except (OperationalError, ProgrammingError):
        pass  # tabela ainda não existe (regra "pura" sem startup): cai no parâmetro
    return get_param_bool("usa_adesivo_deteccao_cio", False)


def produtos_da_config(session: Session, cfg: dict) -> list[dict]:
    """Itens de estoque vinculados (nome/saldo/unidade) — só leitura. Item apagado, inativo ou de outra fazenda sai
    da lista sozinho, sem erro: a seleção nunca trava o lançamento."""
    saida: list[dict] = []
    for ident in cfg.get("estoque_ids") or []:
        e = session.get(Estoque, ident)
        if e is None or e.ativo is False:
            continue
        saida.append({"id": e.id, "nome": e.nome, "quantidade": e.quantidade, "unidade": e.unidade})
    return saida


def produto_da_config(session: Session, cfg: dict) -> dict | None:
    """Primeiro produto vinculado (compatibilidade com quem só conhece um)."""
    produtos = produtos_da_config(session, cfg)
    return produtos[0] if produtos else None


def nomes_dos_produtos(session: Session, cfg: dict) -> str | None:
    """"A", "A ou B", "A, B ou C" — para o texto da tarefa na Agenda; None sem produto vinculado."""
    nomes = [p["nome"] for p in produtos_da_config(session, cfg)]
    if not nomes:
        return None
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " ou " + nomes[-1]


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


def validar(dados: dict, session: Session, fazenda_id: int | None, base: dict | None = None) -> tuple[dict, list[str]]:
    """Normaliza e valida. Devolve (config limpa, avisos não bloqueantes).

    `base` é a configuração atual da fazenda: o que não vier em `dados` fica como está (atualização parcial). Sem
    `base`, o que não vier cai no padrão.

    `avisar_apos_dias`, quando vem no corpo, manda no aviso da Agenda: vazio (None) = não avisar
    (`mostrar_na_agenda=False`, mantém os dias já guardados); número = avisar após esse número de dias."""
    cfg = padrao()
    cfg.pop("configurado")
    cfg.pop("estoque_id")  # derivado: é sempre o primeiro de `estoque_ids`
    if base:
        cfg.update({k: base[k] for k in cfg if k in base})
    if dados.get("estoque_ids") is None and dados.get("estoque_id") is not None:
        dados = {**dados, "estoque_ids": [dados["estoque_id"]]}  # corpo antigo: um produto só
    for k, v in dados.items():
        if k in cfg and v is not None:
            cfg[k] = v
    if "avisar_apos_dias" in dados:
        if dados["avisar_apos_dias"] is None:
            cfg["mostrar_na_agenda"] = False
        else:
            cfg["mostrar_na_agenda"] = True
            cfg["dias_apos_servico"] = dados["avisar_apos_dias"]
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
            rot = {"dias_apos_servico": "Avisar na agenda após (dias)", "repetir_cada_dias": "Repetir a cada (dias)",
                   "repeticoes": "Quantidade de repetições"}[campo]
            raise RepasseError(f"{rot}: use um valor entre {lo} e {hi}.")
    # Produtos vinculados: qualquer item de estoque da fazenda (não exige categoria); sem nenhum, a escolha é livre.
    ids: list[int] = []
    for bruto in cfg.get("estoque_ids") or []:
        try:
            ident = int(bruto)
        except (TypeError, ValueError):
            raise RepasseError("Produto inválido na lista de produtos vinculados.")
        if ident in ids:
            continue
        e = session.get(Estoque, ident)
        if e is None or (fazenda_id is not None and e.fazenda_id != fazenda_id):
            raise RepasseError("Produto não encontrado nesta fazenda.")
        ids.append(ident)
    if len(ids) > 20:
        raise RepasseError("Produtos vinculados demais (máximo 20).")
    cfg["estoque_ids"] = ids
    cfg["estoque_id"] = ids[0] if ids else None
    avisos: list[str] = []
    if cfg["repetir"] and not CICLO_SUGERIDO[0] <= cfg["repetir_cada_dias"] <= CICLO_SUGERIDO[1]:
        avisos.append(f"O ciclo estral costuma ser de {CICLO_SUGERIDO[0]} a {CICLO_SUGERIDO[1]} dias; "
                      f"você escolheu {cfg['repetir_cada_dias']}.")
    return cfg, avisos


def salvar_config(session: Session, fazenda_id: int | None, dados: dict, usuario_id: int | None = None) -> tuple[dict, list[str]]:
    linha = _linha(session, fazenda_id)
    # Com configuração salva, o que não vier no corpo fica como está; na primeira gravação o que não vier parte do padrão
    # (ligado, 14 dias, todas, com aviso) — quem liga o adesivo pela primeira vez já recebe um comportamento completo.
    cfg, avisos = validar(dados, session, fazenda_id, base=ler_config(session, fazenda_id) if linha is not None else None)
    if linha is None:
        linha = RepasseConfig(fazenda_id=fazenda_id)
    for campo, valor in cfg.items():
        if campo == "estoque_ids":
            linha.estoque_ids_json = json.dumps(valor)
        else:
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
    """`produto_nome` já vem com todos os vinculados ("A ou B") — ver `nomes_dos_produtos`."""
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
