"""
Serviço ÚNICO de escrita do histórico sanitário (`sanitario_registro`).

Todas as portas gravam por aqui — dia marcado no desktop, app de campo
(inclusive a sincronização offline), lançamento simples/retroativo, ficha de
campo e importação de planilha:

    registrar(session, fazenda_id, itens, origem=..., canal=..., usuario_id=...,
              eh_admin=..., dia=None, dispositivo_id=None, hoje=None)

Regras (modelo_v1 §3, §5, §6, §12, §13):
  - Grava UM registro por animal; idempotente por `chave_idempotencia` e pela
    chave única animal × caixa × ciclo × dose (a 2ª escrita vira "duplicado",
    com log `escrita.duplicada`; vinda do celular, vira CONFLITO com log
    `offline.conflito` para o aplicador ou o administrador decidir).
  - NUNCA cria caixa: caixa inexistente/arquivada é erro do item; "outro"
    (texto livre) só registra (`so_registro=True`).
  - NUNCA trava: fora da regra devolve o aviso com código e pede
    CONSENTIMENTO explícito (o item fica "pendente" até vir `consentimento`);
    com o consentimento grava `fora_da_regra=True` e o log
    `consentimento.*`. Quando a caixa não tem atestado configurado, pergunta
    se quer fazer atestado (não bloqueia).
  - Carência desconhecida ou sem aceite: pop-up para o ADMINISTRADOR decidir
    (bloqueio/descarte/tanque), gravado em `sanitario_carencia_aceite` (no
    dia) e no log. Operador sem decisão disponível: grava com "tanque · sem
    aceite" (log + nota para os administradores) — nunca trava.
  - Estoque baixa POR ANIMAL pela baixa única do curativo
    (`rules/estoque_baixa.movimentar`, origem `sanitario_registro`), com dose
    por peso (peso médio da categoria marcado "estimado" quando falta).
  - Prazos legais conforme as etapas ligadas na caixa (atestado: o que vencer
    primeiro entre aplicação e NF-e; comprovação periódica).
  - Dia já fechado: grava com `apos_fechamento=True`.
  - `recalcular()` do motor na MESMA transação. Nunca dá commit.

Também aqui: `desfazer` (até 10 s, quem gravou ou o admin), `estornar` (só
admin, com motivo; devolve estoque, tira a carência e a próxima dose não
aplicada), `lancar_resultado` (leitura de exame por veterinário ou admin
informando o veterinário responsável; reagente gera só aviso) e
`decidir_conflito`.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local

logger = logging.getLogger(__name__)

DESFAZER_SEGUNDOS = 10
TOLERANCIA_REDE_SEGUNDOS = 5
RESULTADOS = ("positivo", "negativo", "inconclusivo", "nao_lido")
ORIGENS = ("dia", "lancamento_simples", "ficha", "importado")
CANAIS = ("site", "app", "curral", "importacao")
UNIDADE_BAIXA = {"mL": "mL", "mL_por_kg": "mL", "mL_por_x_kg": "mL", "dose": "dose", "g": "g",
                 "comprimido": "unidade"}
MODO_TXT = {"bloqueio": "bloqueio total", "descarte": "confirma com descarte", "tanque": "vai para o tanque"}


# ════════════════════════════════════════════════════════════════════════════
# Utilidades
# ════════════════════════════════════════════════════════════════════════════
def _aviso(codigo: str, texto: str, **extra) -> dict:
    return {"codigo": codigo, "texto": texto, **extra}


def _log(session: Session, fazenda_id: int, tipo: str, **kw):
    from fazenda.models import SanitarioLog

    lg = SanitarioLog(fazenda_id=fazenda_id, tipo=tipo, **kw)
    session.add(lg)
    session.flush()
    return lg


def produto_efetivo(base: dict, override: Optional[dict]) -> dict:
    """Produto/dose da caixa (ou do dia), com a troca feita na hora por cima."""
    p = dict(base)
    if override:
        for k, v in override.items():
            if v is not None or k in ("estoque_id", "texto", "lote_estoque_id"):
                p[k] = v
        if override.get("modo") and override["modo"] != "estoque":
            p["estoque_id"] = None
    return p


def produto_da_versao(v) -> dict:
    return {
        "modo": v.produto_modo or "vazio", "estoque_id": v.estoque_id, "texto": v.produto_texto,
        "dose_valor": v.dose_valor, "dose_unidade": v.dose_unidade, "dose_x_kg": v.dose_x_kg,
        "lote_estoque_id": None,
    }


def produto_do_dia_caixa(dc) -> dict:
    return {
        "modo": dc.produto_modo or "vazio", "estoque_id": dc.estoque_id, "texto": dc.produto_texto,
        "dose_valor": dc.dose_valor, "dose_unidade": dc.dose_unidade, "dose_x_kg": dc.dose_x_kg,
        "lote_estoque_id": None,
    }


def quantidade_baixa(prod: dict, peso: Optional[float]) -> Optional[float]:
    """Quanto sai do estoque para UM animal (None = não dá para calcular)."""
    dv, un = prod.get("dose_valor"), prod.get("dose_unidade")
    if dv is None:
        return None
    if un == "mL_por_kg":
        return None if peso is None else round(float(peso) * float(dv), 3)
    if un == "mL_por_x_kg":
        x = prod.get("dose_x_kg")
        if peso is None or not x:
            return None
        return round(float(peso) / float(x) * float(dv), 3)
    return float(dv)


def _dose_por_peso(prod: dict) -> bool:
    return prod.get("dose_unidade") in ("mL_por_kg", "mL_por_x_kg")


def peso_medio_categoria(session: Session, fazenda_id: int, animais_ctx: dict, a, ref: date) -> Optional[float]:
    """Peso médio (última pesagem) dos animais da MESMA categoria em `ref`."""
    cat_id, _ = a.categoria_em(ref)
    pesos = [b.peso for b in animais_ctx.values() if b.peso and b.ativo and b.categoria_em(ref)[0] == cat_id]
    if not pesos:
        return None
    return round(sum(pesos) / len(pesos), 1)


def _data_nfe(session: Session, fazenda_id: int, estoque_id: Optional[int], lote_id: Optional[int]) -> Optional[date]:
    """Substituto da NF-e da compra: `LoteEstoque.data_compra` (plano)."""
    from fazenda.models import LoteEstoque

    if lote_id:
        lote = session.get(LoteEstoque, lote_id)
        if lote is not None and lote.fazenda_id in (None, fazenda_id):
            return lote.data_compra
    if estoque_id:
        lote = session.exec(select(LoteEstoque).where(
            LoteEstoque.fazenda_id == fazenda_id, LoteEstoque.estoque_id == estoque_id,
        ).order_by(LoteEstoque.data_compra.desc())).first()
        return lote.data_compra if lote else None
    return None


def _aceite_da_versao(session: Session, fazenda_id: int, versao_id: Optional[int]):
    from fazenda.models import SanitarioCarenciaAceite

    if not versao_id:
        return None
    return session.exec(select(SanitarioCarenciaAceite).where(
        SanitarioCarenciaAceite.fazenda_id == fazenda_id, SanitarioCarenciaAceite.escopo == "caixa_versao",
        SanitarioCarenciaAceite.caixa_versao_id == versao_id,
    ).order_by(SanitarioCarenciaAceite.id.desc())).first()


def _carencia_do_item_estoque(session: Session, estoque_id: Optional[int]) -> dict:
    """Carência da bula/cadastro do item (leite/carne); {} sem item."""
    from fazenda.models import Estoque
    from fazenda.rules.estoque_baixa import carencia_para_item, resolver_marca_comercial

    if not estoque_id:
        return {}
    item = session.get(Estoque, estoque_id)
    if item is None:
        return {}
    marca = resolver_marca_comercial(session, item=item, nome=item.nome, principio_ativo_id=item.principio_ativo_id)
    c = carencia_para_item(item, marca)
    return {"leite": c.get("leite_dias"), "carne": c.get("carne_dias"), "proibido": c.get("proibido_lactacao")}


# ════════════════════════════════════════════════════════════════════════════
# Carência
# ════════════════════════════════════════════════════════════════════════════
def carencia_precisa_decisao(session: Session, fazenda_id: int, versao, prod: dict, dia_caixa=None) -> Optional[str]:
    """Motivo do pop-up de carência, ou None quando já há decisão/aceite.
    Mesma regra do mockup (`carDesconhecida`): sem aceite da caixa, produto
    incluído sem estoque, ou produto trocado sem carência cadastrada."""
    if dia_caixa is not None and dia_caixa.carencia_decisao_id:
        return None
    if prod.get("modo") == "sem_estoque":
        return f"{prod.get('texto') or 'O produto'} foi incluído sem estoque e não tem carência cadastrada."
    if prod.get("modo") == "estoque" and prod.get("estoque_id") and versao is not None \
            and prod.get("estoque_id") != versao.estoque_id:
        c = _carencia_do_item_estoque(session, prod["estoque_id"])
        if c.get("leite") is None and c.get("carne") is None and not c.get("proibido"):
            return "O produto trocado não tem carência cadastrada."
    if versao is None:
        return None
    if _aceite_da_versao(session, fazenda_id, versao.id) is None:
        return "A caixa está sem aceite de carência."
    return None


def carencia_efetiva(session: Session, fazenda_id: int, versao, prod: dict, decisao: Optional[dict],
                     dia_caixa=None) -> dict:
    """{modo, leite, carne, aceite_id, fonte}. Prioridade: decisão explícita
    > decisão do dia > aceite da caixa > caixa > bula do produto."""
    from fazenda.models import SanitarioCarenciaAceite

    if decisao:
        return {"modo": decisao.get("modo"), "leite": decisao.get("leite_dias"), "carne": decisao.get("carne_dias"),
                "aceite_id": decisao.get("aceite_id"), "fonte": "decisao"}
    if dia_caixa is not None and dia_caixa.carencia_decisao_id:
        ac = session.get(SanitarioCarenciaAceite, dia_caixa.carencia_decisao_id)
        if ac is not None:
            return {"modo": ac.modo_leite, "leite": ac.leite_dias, "carne": ac.carne_dias, "aceite_id": ac.id,
                    "fonte": "dia"}
    bula = _carencia_do_item_estoque(session, prod.get("estoque_id")) if prod.get("modo") == "estoque" else {}
    leite = versao.car_leite_dias if versao is not None else None
    carne = versao.car_carne_dias if versao is not None else None
    modo = versao.car_modo_leite if versao is not None else None
    aceite = _aceite_da_versao(session, fazenda_id, versao.id) if versao is not None else None
    if aceite is not None:
        leite = aceite.leite_dias if aceite.leite_dias is not None else leite
        carne = aceite.carne_dias if aceite.carne_dias is not None else carne
        modo = aceite.modo_leite or modo
    if leite is None:
        leite = bula.get("leite")
    if carne is None:
        carne = bula.get("carne")
    return {"modo": modo, "leite": leite, "carne": carne, "aceite_id": aceite.id if aceite else None,
            "fonte": "aceite" if aceite else "caixa"}


def gravar_decisao_dia(session: Session, fazenda_id: int, dia_caixa, decisao: dict, usuario_id: Optional[int]):
    """Pop-up de carência dentro de um dia: vale para o dia todo (aceite com
    escopo `dia_caixa`), com log `carencia.decisao`."""
    from fazenda.models import SanitarioCarenciaAceite

    ac = SanitarioCarenciaAceite(
        fazenda_id=fazenda_id, escopo="dia_caixa", dia_caixa_id=dia_caixa.id, caixa_versao_id=dia_caixa.caixa_versao_id,
        modo_leite=decisao.get("modo"), leite_dias=decisao.get("leite_dias"), carne_dias=decisao.get("carne_dias"),
        origem="popup", aceito_por_usuario_id=usuario_id,
    )
    session.add(ac)
    session.flush()
    dia_caixa.carencia_decisao_id = ac.id
    session.add(dia_caixa)
    _log(session, fazenda_id, "carencia.decisao", dia_id=dia_caixa.dia_id, caixa_id=dia_caixa.caixa_id,
         usuario_id=usuario_id, decisao=decisao.get("modo"),
         texto_livre=f"Carência decidida: {MODO_TXT.get(decisao.get('modo'), decisao.get('modo'))} · "
                     f"leite {decisao.get('leite_dias')} d · carne {decisao.get('carne_dias')} d.",
         payload={k: decisao.get(k) for k in ("modo", "leite_dias", "carne_dias")})
    return ac


# ════════════════════════════════════════════════════════════════════════════
# Prazos legais
# ════════════════════════════════════════════════════════════════════════════
def _anexar_prazo(session: Session, fazenda_id: int, tipo: str, caixa_id: int, ref: str, vence: date,
                  destinatario: Optional[str], registro_id: Optional[int]):
    from fazenda.models import SanitarioPrazoLegal

    p = session.exec(select(SanitarioPrazoLegal).where(
        SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.tipo == tipo,
        SanitarioPrazoLegal.caixa_id == caixa_id, SanitarioPrazoLegal.referencia_chave == ref,
    )).first()
    if p is None:
        p = SanitarioPrazoLegal(fazenda_id=fazenda_id, tipo=tipo, caixa_id=caixa_id, referencia_chave=ref,
                                vence_em=vence, destinatario=destinatario, registro_ids=[])
    else:
        p.vence_em = min(p.vence_em, vence)
        if p.estado == "dispensado":
            p.estado = "aberto"
    if registro_id is not None and registro_id not in (p.registro_ids or []):
        p.registro_ids = [*(p.registro_ids or []), registro_id]
    session.add(p)
    session.flush()
    return p


def criar_prazos(session: Session, fazenda_id: int, reg, versao, quer_atestado: Optional[dict]) -> list[int]:
    """Prazos legais do registro (conforme as etapas ligadas na caixa)."""
    from fazenda.models import SanitarioPrazoLegal
    from fazenda.rules.sanitario.legal import vencimento_atestado

    ids: list[int] = []
    if reg.caixa_id is None or versao is None:
        return ids
    ref = f"dia:{reg.dia_id}" if reg.dia_id else f"data:{reg.data.isoformat()}"
    atestado = versao.legal_atestado or (quer_atestado and {"quando": "aplicacao", "dias": 30,
                                                             "destinatario_texto": quer_atestado.get("destinatario")})
    if atestado:
        vence = vencimento_atestado(atestado, reg.data, _data_nfe(session, fazenda_id, reg.estoque_id, reg.lote_estoque_id))
        dest = atestado.get("destinatario_texto") or (quer_atestado or {}).get("destinatario")
        ids.append(_anexar_prazo(session, fazenda_id, "atestado", reg.caixa_id, ref, vence, dest, reg.id).id)
    comp = versao.legal_comprovacao
    if comp:
        existe = session.exec(select(SanitarioPrazoLegal.id).where(
            SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.tipo == "comprovacao",
            SanitarioPrazoLegal.caixa_id == reg.caixa_id, SanitarioPrazoLegal.estado == "aberto",
        )).first()
        if existe is None:
            vence = reg.data + timedelta(days=int(comp.get("dias") or 180))
            ids.append(_anexar_prazo(session, fazenda_id, "comprovacao", reg.caixa_id, f"data:{vence.isoformat()}",
                                     vence, (versao.legal_atestado or {}).get("destinatario_texto"), None).id)
    return ids


def _soltar_dos_prazos(session: Session, fazenda_id: int, registro_id: int) -> None:
    from fazenda.models import SanitarioPrazoLegal

    for p in session.exec(select(SanitarioPrazoLegal).where(
        SanitarioPrazoLegal.fazenda_id == fazenda_id, SanitarioPrazoLegal.tipo == "atestado",
        SanitarioPrazoLegal.estado == "aberto",
    )).all():
        if registro_id in (p.registro_ids or []):
            p.registro_ids = [i for i in p.registro_ids if i != registro_id]
            if not p.registro_ids:
                p.estado = "dispensado"
            session.add(p)


# ════════════════════════════════════════════════════════════════════════════
# Estoque
# ════════════════════════════════════════════════════════════════════════════
def _baixar_estoque(session: Session, fazenda_id: int, reg, prod: dict, qtd: Optional[float],
                    usuario_id: Optional[int]) -> list[dict]:
    from fazenda.models import Estoque, MovimentoEstoque
    from fazenda.rules.estoque_baixa import movimentar

    if prod.get("modo") != "estoque" or not prod.get("estoque_id"):
        return []
    item = session.get(Estoque, prod["estoque_id"])
    if item is None or item.fazenda_id not in (None, fazenda_id):
        return [_aviso("estoque_inexistente", "Produto não está no estoque desta fazenda — registrado sem baixa.")]
    if item.ativo is False:
        return [_aviso("estoque_inativo", f'"{item.nome}" está inativo no estoque — registrado sem baixa.')]
    if qtd is None:
        return [_aviso("estoque_sem_quantidade", f'Sem dose/peso para calcular a baixa de "{item.nome}" — registrado sem baixa.')]
    try:
        textos = movimentar(
            session, item=item, quantidade=qtd, unidade=UNIDADE_BAIXA.get(prod.get("dose_unidade"), prod.get("dose_unidade")),
            data=reg.data, fazenda_id=fazenda_id, movimento="Aplicação",
            observacao=f"Sanitário preventivo · registro {reg.id} · animal {reg.numero_animal_texto or reg.animal_id}",
            usuario_id=usuario_id, origem_tipo="sanitario_registro", origem_id=reg.id, sinal=-1,
            lote_id=prod.get("lote_estoque_id"),
        )
    except Exception as e:  # nunca trava o registro por causa do estoque
        logger.exception("sanitario: baixa de estoque falhou (registro %s)", reg.id)
        return [_aviso("estoque_falhou", f"Baixa de estoque não aplicada: {e}")]
    mov = session.exec(select(MovimentoEstoque).where(
        MovimentoEstoque.fazenda_id == fazenda_id, MovimentoEstoque.origem_tipo == "sanitario_registro",
        MovimentoEstoque.origem_id == reg.id,
    ).order_by(MovimentoEstoque.id.desc())).first()
    if mov is not None:
        reg.movimento_estoque_id = mov.id
        reg.quantidade_baixada = qtd
        reg.lote_estoque_id = mov.lote_id or reg.lote_estoque_id
        vu = mov.valor_unitario if mov.valor_unitario is not None else item.valor_unitario
        reg.custo = round(qtd * vu, 2) if vu is not None else None
        session.add(reg)
    return [_aviso("estoque", t) for t in textos]


def _devolver_estoque(session: Session, fazenda_id: int, reg, usuario_id: Optional[int], motivo: str) -> list[dict]:
    from fazenda.models import Estoque
    from fazenda.rules.estoque_baixa import devolver

    if not reg.movimento_estoque_id or not reg.quantidade_baixada or not reg.estoque_id:
        return []
    item = session.get(Estoque, reg.estoque_id)
    textos = devolver(
        session, item=item, quantidade=reg.quantidade_baixada, unidade=item.unidade if item else None, data=hoje_local(),
        fazenda_id=fazenda_id, observacao=f"Sanitário preventivo · {motivo} do registro {reg.id}",
        usuario_id=usuario_id, origem_tipo="sanitario_registro_estorno", origem_id=reg.id,
        lote_id=reg.lote_estoque_id,
    )
    return [_aviso("estoque", t) for t in textos]


# ════════════════════════════════════════════════════════════════════════════
# registrar
# ════════════════════════════════════════════════════════════════════════════
class _Cache:
    def __init__(self, session: Session, fazenda_id: int, hoje: date):
        self.session, self.fazenda_id, self.hoje = session, fazenda_id, hoje
        self.caixas: dict[int, Any] = {}
        self.defs: dict[int, Any] = {}
        self.versoes: dict[int, Any] = {}
        self.animais: dict[int, Any] = {}

    def caixa(self, caixa_id: int):
        from fazenda.models import SanitarioCaixa, SanitarioCaixaVersao
        from fazenda.rules.sanitario.contexto import carregar_caixas

        if caixa_id not in self.caixas:
            cx = self.session.get(SanitarioCaixa, caixa_id)
            if cx is None or cx.fazenda_id != self.fazenda_id:
                cx = None
            self.caixas[caixa_id] = cx
            if cx is not None:
                defs = carregar_caixas(self.session, self.fazenda_id, caixa_ids=[caixa_id], so_ativas=False)
                self.defs[caixa_id] = defs[0] if defs else None
                self.versoes[caixa_id] = self.session.get(SanitarioCaixaVersao, cx.versao_atual_id) if cx.versao_atual_id else None
        return self.caixas[caixa_id]

    def carregar_animais(self, ids: set[int]):
        from fazenda.rules.sanitario.contexto import carregar_animais

        faltam = {i for i in ids if i not in self.animais}
        if faltam:
            # Carrega também a fazenda inteira só uma vez se houver dose por peso
            # (peso médio da categoria); aqui, só os pedidos.
            self.animais.update(carregar_animais(self.session, self.fazenda_id, animal_ids=faltam, hoje=self.hoje))


def _resolver_animal(session: Session, fazenda_id: int, it: dict):
    from fazenda.models import Animal

    if it.get("animal_id"):
        a = session.get(Animal, int(it["animal_id"]))
        if a is None or a.fazenda_id != fazenda_id:
            return None, "animal_inexistente"
        return a, None
    numero = (it.get("numero_animal") or "").strip()
    if not numero:
        return None, "sem_animal"
    a = session.exec(select(Animal).where(Animal.fazenda_id == fazenda_id, Animal.numero == numero)).first()
    return a, None  # None = brinco sem cadastro (registra assim mesmo)


def registrar(
    session: Session, fazenda_id: int, itens: list[dict], *, origem: str, canal: str = "site",
    usuario_id: Optional[int] = None, eh_admin: bool = False, dia=None, dispositivo_id: Optional[int] = None,
    hoje: Optional[date] = None, so_registro: bool = False,
) -> dict:
    """Ver o docstring do módulo. `itens`: dicts com animal_id|numero_animal,
    caixa_id|outro_texto, data, hora, dose_num, produto{modo, estoque_id,
    lote_estoque_id, texto, dose_valor, dose_unidade, dose_x_kg}, peso_kg,
    partida_texto, fabricante, validade, aplicador_pessoa_id/texto,
    veterinario_pessoa_id/texto, crmv_texto, resultado, resultado_valor,
    resultado_detalhe, atestado_numero, atestado_destinatario,
    consentimento{aceito, motivo_exibido, quer_atestado, atestado_destinatario},
    carencia{modo, leite_dias, carne_dias}, retroativo_motivo,
    chave_idempotencia.

    Devolve {"itens": [{indice, status, registro_id, animal_id, numero,
    caixa_id, avisos, requer, ...}], "gravados", "duplicados", "pendentes",
    "conflitos", "erros", "registro_ids", "desfazer_ate"}."""
    from fazenda.models import (
        SanitarioDiaCaixa, SanitarioDiaItem, SanitarioRegistro,
    )
    from fazenda.rules.sanitario.ciclos import ciclo_de
    from fazenda.rules.sanitario.motor import motivo_inelegivel, ok_na_data, recalcular, situacao_atual

    if origem not in ORIGENS:
        raise ValueError(f"origem inválida: {origem}")
    hoje = hoje or hoje_local()
    cache = _Cache(session, fazenda_id, hoje)
    saida: list[dict] = []
    afetados: set[int] = set()
    novos: list[int] = []

    # Contexto dos animais de uma vez.
    resolvidos: list[tuple] = []
    for i, it in enumerate(itens):
        a, erro = _resolver_animal(session, fazenda_id, it)
        resolvidos.append((i, it, a, erro))
    cache.carregar_animais({a.id for _i, _it, a, _e in resolvidos if a is not None})
    precisa_peso_medio = False

    dia_caixas: dict[int, Any] = {}
    if dia is not None:
        for dc in session.exec(select(SanitarioDiaCaixa).where(
            SanitarioDiaCaixa.fazenda_id == fazenda_id, SanitarioDiaCaixa.dia_id == dia.id,
        )).all():
            dia_caixas[dc.caixa_id] = dc

    for i, it, animal, erro in resolvidos:
        r: dict = {"indice": i, "status": "erro", "registro_id": None, "animal_id": animal.id if animal else None,
                   "numero": animal.numero if animal else (it.get("numero_animal") or None),
                   "caixa_id": it.get("caixa_id"), "avisos": [], "requer": [],
                   "chave_idempotencia": it.get("chave_idempotencia")}
        saida.append(r)
        chave = (it.get("chave_idempotencia") or "").strip() or None

        # 1) idempotência por chave
        if chave:
            ja = session.exec(select(SanitarioRegistro).where(
                SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.chave_idempotencia == chave,
            )).first()
            if ja is not None:
                r.update(status="duplicado", registro_id=ja.id)
                continue
        if erro:
            r["avisos"].append(_aviso(erro, "Animal não encontrado nesta fazenda." if erro == "animal_inexistente"
                                      else "Informe o animal (brinco)."))
            continue

        # 2) o quê: caixa (nunca cria) ou "outro"
        caixa_id = it.get("caixa_id")
        cx = versao = cxd = None
        outro = (it.get("outro_texto") or "").strip() or None
        if caixa_id:
            cx = cache.caixa(int(caixa_id))
            if cx is None:
                r["avisos"].append(_aviso("caixa_inexistente", "Vacina/exame não cadastrado nesta fazenda."))
                continue
            if cx.estado == "arquivada":
                r["avisos"].append(_aviso("caixa_arquivada", f"{cx.nome} está arquivada — reative no Cadastro."))
                continue
            versao, cxd = cache.versoes.get(cx.id), cache.defs.get(cx.id)
            if dia is not None and cx.id not in dia_caixas:
                r["avisos"].append(_aviso("caixa_fora_do_dia", f"{cx.nome_curto or cx.nome} não faz parte deste dia."))
                continue
        elif not outro:
            r["avisos"].append(_aviso("sem_o_que", "Escolha a vacina/exame ou escreva o que foi feito."))
            continue
        eh_exame = bool(cx is not None and cx.tipo == "exame")
        so_reg = bool(so_registro or cx is None)

        # 3) data e ciclo
        data = it.get("data") or (dia.data if dia is not None and dia.data <= hoje else hoje)
        if isinstance(data, str):
            data = date.fromisoformat(data)
        if isinstance(it.get("validade"), str):  # item reaplicado do log (conflito offline)
            it = {**it, "validade": date.fromisoformat(it["validade"])}
        ctx = cache.animais.get(animal.id) if animal else None
        ciclo_chave, dose_num = None, int(it.get("dose_num") or 1)
        if ctx is not None and cxd is not None:
            s = situacao_atual(cxd, ctx, data)
            if s.ciclo is not None:
                ciclo_chave = s.ciclo.chave
                dose_num = int(it.get("dose_num") or s.dose_num or 1)
            else:
                c = ciclo_de(cxd, ctx, data, "proximo") or ciclo_de(cxd, ctx, data, "ultimo")
                ciclo_chave = c.chave if c else f"X:{data.isoformat()}"
        elif cx is not None:
            ciclo_chave = f"X:{data.isoformat()}"

        # 3b) animal que SAIU do rebanho não recebe aplicação pelo dia
        # (decisão do dono, out/2026): a fila do celular já o esconde, mas uma
        # cópia antiga do pacote ainda podia mandá-lo. Aplicação com data até
        # a da baixa (vacinou de manhã, vendeu à tarde, sincronizou à noite)
        # é história verdadeira e entra.
        if dia is not None and animal is not None and not animal.ativo and (
                animal.data_baixa is None or data > animal.data_baixa):
            motivo_saida = (animal.motivo_baixa or "").strip()
            quando = f" em {animal.data_baixa.strftime('%d/%m/%Y')}" if animal.data_baixa else ""
            r["avisos"].append(_aviso("saiu_do_rebanho", f"{animal.numero} saiu do rebanho{quando}"
                                      f"{f' ({motivo_saida})' if motivo_saida else ''} — aplicação não registrada."))
            continue

        # 4) chave única (animal × caixa × ciclo × dose)
        if animal is not None and cx is not None and not so_reg:
            existente = session.exec(select(SanitarioRegistro).where(
                SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.animal_id == animal.id,
                SanitarioRegistro.caixa_id == cx.id, SanitarioRegistro.ciclo_chave == ciclo_chave,
                SanitarioRegistro.dose_num == dose_num, SanitarioRegistro.estado == "valido",
                SanitarioRegistro.so_registro == False,  # noqa: E712
            )).first()
            if existente is not None:
                offline = canal in ("app", "curral") and chave is not None and existente.chave_idempotencia != chave
                tipo = "offline.conflito" if offline else "escrita.duplicada"
                lg = _log(session, fazenda_id, tipo, dia_id=dia.id if dia else None, caixa_id=cx.id,
                          animal_id=animal.id, registro_id=existente.id, usuario_id=usuario_id,
                          dispositivo_id=dispositivo_id,
                          texto_livre=f"{animal.numero} × {cx.nome_curto or cx.nome} × ciclo {ciclo_chave} já existe: "
                                      + ("conflito entre aparelhos, aguardando decisão." if offline
                                         else "a segunda gravação foi ignorada (chave única)."),
                          payload={"item": _serializavel(it), "origem": origem, "canal": canal,
                                   "existente_id": existente.id, "dia_id": dia.id if dia else None,
                                   "resolvido": False} if offline else None)
                r.update(status="conflito" if offline else "duplicado", registro_id=existente.id)
                if offline:
                    r["conflito_log_id"] = lg.id
                    r["avisos"].append(_aviso("conflito", "Outro aparelho já registrou este animal neste ciclo. "
                                                          "O aplicador ou o administrador decide qual vale."))
                continue

        # 5) fora da regra -> consentimento explícito (nunca trava)
        dia_item = None
        if dia is not None and animal is not None and cx is not None:
            dia_item = session.exec(select(SanitarioDiaItem).where(
                SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == dia.id,
                SanitarioDiaItem.animal_id == animal.id, SanitarioDiaItem.caixa_id == cx.id,
            )).first()
            if dia_item is not None and dia_item.estado == "removido":
                dia_item = None
        cons = it.get("consentimento") or {}
        fora_motivo = None
        fora_kind = None
        if animal is not None and cxd is not None and ctx is not None and not so_reg and dia_item is None:
            a_sem = ctx
            if cxd.caixa_id in ctx.dias:
                a_sem = replace(ctx, dias={k: v for k, v in ctx.dias.items() if k != cxd.caixa_id}, _cache_cat=ctx._cache_cat)
            nd = ok_na_data(cxd, a_sem, data)
            if not nd.ok and nd.kind != "aplicada":
                fora_motivo, fora_kind = motivo_inelegivel(cxd, a_sem, data), nd.kind
        if dia_item is not None and ctx is not None and cxd is not None:
            nd = ok_na_data(cxd, ctx, data)
            if not nd.ok and nd.kind not in ("aplicada",) and dia_item.origem == "janela":
                r["avisos"].append(_aviso("saiu_da_janela", f"{animal.numero}: {nd.texto} (marcado pela janela)."))
        cons_log = None
        if fora_motivo:
            r["motivo_fora"] = fora_motivo
            if not (cons and cons.get("aceito")):
                r["status"] = "pendente"
                r["requer"].append("consentimento")
                r["pergunta_atestado"] = bool(versao is not None and not versao.legal_atestado)
                r["avisos"].append(_aviso("fora_da_regra", f"{animal.numero}: {fora_motivo}"))
                continue
            tipo_log = "consentimento.fora_janela" if fora_kind in ("fecha", "antes", "idade", "parto", "ciclo") \
                else "consentimento.inelegivel"
            cons_log = _log(session, fazenda_id, tipo_log, dia_id=dia.id if dia else None, caixa_id=cx.id,
                            animal_id=animal.id, usuario_id=usuario_id, dispositivo_id=dispositivo_id,
                            motivo_exibido=cons.get("motivo_exibido") or fora_motivo, decisao="incluir",
                            texto_livre=f"Fora da regra ({fora_motivo}); incluído com consentimento.",
                            payload={"quer_atestado": bool(cons.get("quer_atestado")), "canal": canal})

        # 6) exame: resultado (modo da fazenda) — leitura exige vet ou admin com vet
        resultado = it.get("resultado")
        if resultado is not None and resultado not in RESULTADOS:
            r["avisos"].append(_aviso("resultado_invalido", f"Resultado inválido: {resultado}."))
            continue

        # 7) produto/dose (troca na hora)
        if eh_exame:
            prod = {"modo": "nao_se_aplica", "estoque_id": None, "texto": None, "dose_valor": None,
                    "dose_unidade": None, "dose_x_kg": None, "lote_estoque_id": None}
        else:
            base = produto_do_dia_caixa(dia_caixas[cx.id]) if (dia is not None and cx is not None) else (
                produto_da_versao(versao) if versao is not None else
                {"modo": "vazio", "estoque_id": None, "texto": None, "dose_valor": None, "dose_unidade": None,
                 "dose_x_kg": None, "lote_estoque_id": None})
            prod = produto_efetivo(base, it.get("produto"))
            if prod.get("modo") == "estoque" and prod.get("estoque_id"):
                from fazenda.models import Estoque
                e = session.get(Estoque, int(prod["estoque_id"]))
                if e is None or e.fazenda_id not in (None, fazenda_id):
                    r["avisos"].append(_aviso("estoque_inexistente", "Produto não está no estoque desta fazenda."))
                    prod["estoque_id"] = None
                    prod["modo"] = "sem_estoque"

        # 8) carência (não para exame nem importação)
        car = {"modo": None, "leite": None, "carne": None, "aceite_id": None, "fonte": None}
        dc = dia_caixas.get(cx.id) if (dia is not None and cx is not None) else None
        if not eh_exame and origem != "importado" and (cx is not None or it.get("carencia")):
            decisao = it.get("carencia")
            if decisao and all(decisao.get(k) is None for k in ("modo", "leite_dias", "carne_dias")):
                decisao = None
            if decisao and decisao.get("modo") and not eh_admin:
                r["avisos"].append(_aviso("carencia_modo_so_admin",
                                          "Só o administrador escolhe o modo da carência; vale a regra da caixa."))
                decisao = {**decisao, "modo": None}
            motivo_car = None
            if not decisao:
                motivo_car = carencia_precisa_decisao(session, fazenda_id, versao, prod, dc) if cx is not None else None
            if motivo_car:
                if eh_admin and canal != "importacao":
                    r.update(status="pendente", motivo_carencia=motivo_car)
                    r["requer"].append("carencia_decisao")
                    sug = carencia_efetiva(session, fazenda_id, versao, prod, None, dc)
                    r["carencia_sugerida"] = {"leite_dias": sug["leite"], "carne_dias": sug["carne"],
                                              "modo": sug["modo"]}
                    r["avisos"].append(_aviso("carencia_decisao", motivo_car))
                    continue
                car = carencia_efetiva(session, fazenda_id, versao, prod, None, dc)
                car["modo"] = "tanque"
                car["fonte"] = "sem_aceite"
                r["avisos"].append(_aviso("carencia_sem_aceite",
                                          "Carência sem aceite: o leite segue para o tanque e fica no log "
                                          "até o administrador decidir."))
            else:
                if decisao and decisao.get("modo") and dc is not None:
                    ac = gravar_decisao_dia(session, fazenda_id, dc, decisao, usuario_id)
                    decisao = {**decisao, "aceite_id": ac.id}
                elif decisao and decisao.get("modo"):
                    _log(session, fazenda_id, "carencia.decisao", caixa_id=cx.id if cx else None,
                         animal_id=animal.id if animal else None, usuario_id=usuario_id, decisao=decisao.get("modo"),
                         texto_livre=f"Carência decidida no lançamento: {MODO_TXT.get(decisao.get('modo'))}.",
                         payload={k: decisao.get(k) for k in ("modo", "leite_dias", "carne_dias")})
                if decisao and not decisao.get("modo"):
                    # Dias informados no lançamento, sem modo: vale o modo já
                    # decidido para o dia/caixa (aceite); senão, "sem aceite".
                    decisao = {**decisao, "modo": carencia_efetiva(session, fazenda_id, versao, prod, None, dc)["modo"]}
                car = carencia_efetiva(session, fazenda_id, versao, prod, decisao, dc)
                if (car.get("leite") or 0) > 0 and not car.get("modo"):
                    car["modo"] = "tanque"
                    car["fonte"] = "sem_aceite"

        # 9) peso e quantidade
        peso, peso_est = it.get("peso_kg"), False
        if prod.get("modo") == "estoque" and _dose_por_peso(prod) and peso is None and ctx is not None:
            peso = ctx.peso
            if peso is None:
                if not precisa_peso_medio:
                    from fazenda.rules.sanitario.contexto import carregar_animais as _ca
                    for k, v in _ca(session, fazenda_id, hoje=hoje).items():
                        cache.animais.setdefault(k, v)
                    precisa_peso_medio = True
                peso = peso_medio_categoria(session, fazenda_id, cache.animais, ctx, data)
                peso_est = peso is not None
                if peso_est:
                    r["avisos"].append(_aviso("peso_estimado", f"{animal.numero}: sem pesagem; usado o peso médio "
                                                               f"da categoria ({peso:g} kg, estimado)."))
        qtd = quantidade_baixa(prod, peso) if prod.get("modo") == "estoque" else None

        # 10) grava
        apos_fech = bool(dia is not None and dia.estado == "fechado")
        retro = origem in ("lancamento_simples", "ficha") and data < hoje
        reg = SanitarioRegistro(
            fazenda_id=fazenda_id, animal_id=animal.id if animal else None,
            numero_animal_texto=animal.numero if animal else (it.get("numero_animal") or None),
            caixa_id=cx.id if cx else None, caixa_versao_id=versao.id if versao else None,
            outro_texto=outro if cx is None else None, ciclo_chave=ciclo_chave, dose_num=dose_num,
            dia_id=dia.id if dia else None, data=data, hora=it.get("hora"),
            origem=origem, canal=canal, so_registro=so_reg,
            decisao_curral=bool(canal in ("app", "curral") and fora_motivo) or bool(dia_item and dia_item.origem == "curral"),
            apos_fechamento=apos_fech, retroativo=retro,
            retroativo_motivo=(it.get("retroativo_motivo") or None) if retro else None,
            fora_da_regra=bool(fora_motivo),
            produto_modo=prod.get("modo"), estoque_id=prod.get("estoque_id") if prod.get("modo") == "estoque" else None,
            lote_estoque_id=prod.get("lote_estoque_id"), partida_texto=it.get("partida_texto"),
            fabricante=it.get("fabricante"), validade=it.get("validade"), produto_texto=prod.get("texto"),
            dose_valor=prod.get("dose_valor"), dose_unidade=prod.get("dose_unidade"),
            peso_usado=peso if qtd is not None else it.get("peso_kg"), peso_estimado=peso_est,
            aplicador_pessoa_id=it.get("aplicador_pessoa_id"), aplicador_texto=it.get("aplicador_texto"),
            veterinario_pessoa_id=it.get("veterinario_pessoa_id") or (dia.veterinario_pessoa_id if dia else None),
            veterinario_texto=it.get("veterinario_texto") or (dia.veterinario_texto if dia else None),
            crmv_texto=it.get("crmv_texto") or (dia.crmv_texto if dia else None),
            resultado=resultado, resultado_valor=it.get("resultado_valor"),
            resultado_detalhe=it.get("resultado_detalhe"),
            leitura_em=datetime.utcnow() if resultado else None,
            carencia_leite_ate=(data + timedelta(days=int(car["leite"]))) if car.get("leite") else None,
            carencia_carne_ate=(data + timedelta(days=int(car["carne"]))) if car.get("carne") else None,
            carencia_modo=car.get("modo") if (car.get("leite") or car.get("carne")) else None,
            carencia_aceite_id=car.get("aceite_id"),
            atestado_numero=it.get("atestado_numero"), atestado_destinatario=it.get("atestado_destinatario"),
            chave_idempotencia=chave, dispositivo_id=dispositivo_id, criado_por_usuario_id=usuario_id,
        )
        session.add(reg)
        session.flush()
        if cons_log is not None:
            cons_log.registro_id = reg.id
            session.add(cons_log)
        if car.get("fonte") == "sem_aceite" and (car.get("leite") or car.get("carne") or cx is not None):
            _log(session, fazenda_id, "carencia.sem_aceite", dia_id=dia.id if dia else None,
                 caixa_id=cx.id if cx else None, animal_id=animal.id if animal else None, registro_id=reg.id,
                 usuario_id=usuario_id, decisao="tanque",
                 texto_livre="Sem aceite de carência: leite segue para o tanque.")
            from fazenda.rules.sanitario.notas import upsert_nota
            nome = (cx.nome_curto or cx.nome) if cx else (outro or "lançamento")
            upsert_nota(session, fazenda_id, f"carencia_registro:{cx.id if cx else 'outro'}:{(dia.id if dia else data.isoformat())}",
                        tipo="carencia_pendente", caixa_id=cx.id if cx else None, dia_id=dia.id if dia else None,
                        titulo=f"Carência de {nome} sem decisão do administrador",
                        texto="Registros gravados com o leite indo para o tanque. Decida o modo da carência.",
                        so_admin=True, data_ref=hoje)
        if retro:
            _log(session, fazenda_id, "registro.retroativo", caixa_id=cx.id if cx else None,
                 animal_id=animal.id if animal else None, registro_id=reg.id, usuario_id=usuario_id,
                 texto_livre=f"Lançamento retroativo de {data.strftime('%d/%m/%Y')}: "
                             f"{it.get('retroativo_motivo') or 'motivo não informado'}.")
        if not so_reg or (cx is None and prod.get("modo") == "estoque"):
            r["avisos"].extend(_baixar_estoque(session, fazenda_id, reg, prod, qtd, usuario_id))
        if not so_reg:
            quer = None
            if cons.get("aceito") and cons.get("quer_atestado"):
                quer = {"destinatario": cons.get("atestado_destinatario")}
            criar_prazos(session, fazenda_id, reg, versao, quer)
        if resultado == "positivo" and versao is not None and versao.legal_reagente_aviso:
            _nota_reagente(session, fazenda_id, reg, cx, animal, hoje)
            r["avisos"].append(_aviso("reagente", f"{animal.numero if animal else reg.numero_animal_texto}: reagente "
                                                  f"em {cx.nome_curto or cx.nome} — só aviso."))
        if dia is not None and animal is not None and cx is not None:
            if dia_item is None:
                dia_item = SanitarioDiaItem(
                    fazenda_id=fazenda_id, dia_id=dia.id, animal_id=animal.id, caixa_id=cx.id,
                    origem="curral" if (dia.data <= hoje) else "manual",
                    consentimento_log_id=cons_log.id if cons_log else None,
                )
            dia_item.estado = "feito"
            session.add(dia_item)
            session.flush()
            reg.dia_item_id = dia_item.id
            reg.decisao_curral = reg.decisao_curral or dia_item.origem == "curral"
            session.add(reg)
        if apos_fech:
            r["avisos"].append(_aviso("apos_fechamento", "Lançado após o fechamento do dia."))
        if animal is None:
            r["avisos"].append(_aviso("sem_cadastro", f"Brinco {reg.numero_animal_texto}: sem cadastro — registrado assim."))
        r.update(status="gravado", registro_id=reg.id, ciclo_chave=ciclo_chave, dose_num=dose_num,
                 carencia={"modo": reg.carencia_modo, "leite_ate": _iso(reg.carencia_leite_ate),
                           "carne_ate": _iso(reg.carencia_carne_ate)})
        novos.append(reg.id)
        if animal is not None:
            afetados.add(animal.id)

    if dia is not None and novos and dia.estado == "marcado":
        dia.estado = "em_execucao"
        session.add(dia)
    if afetados:
        recalcular(session, fazenda_id, animal_ids=afetados, motivo=f"registrar:{origem}", hoje=hoje)
    session.flush()
    cont = {k: sum(1 for x in saida if x["status"] == v) for k, v in (
        ("gravados", "gravado"), ("duplicados", "duplicado"), ("pendentes", "pendente"),
        ("conflitos", "conflito"), ("erros", "erro"))}
    return {
        "itens": saida, **cont, "registro_ids": novos,
        "desfazer_ate": (datetime.utcnow() + timedelta(seconds=DESFAZER_SEGUNDOS)).isoformat() + "Z" if novos else None,
    }


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _serializavel(v):
    if isinstance(v, dict):
        return {k: _serializavel(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_serializavel(x) for x in v]
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _nota_reagente(session: Session, fazenda_id: int, reg, cx, animal, hoje: date) -> None:
    from fazenda.rules.sanitario.notas import upsert_nota

    numero = animal.numero if animal else reg.numero_animal_texto
    upsert_nota(session, fazenda_id, f"reagente:{reg.id}", tipo="reagente", caixa_id=cx.id if cx else None,
                titulo=f"{numero}: reagente em {cx.nome_curto or cx.nome}",
                texto="Aviso de reagente (sem pendência). Siga a orientação do veterinário.",
                dados={"registro_id": reg.id, "animal_id": reg.animal_id}, so_admin=True, data_ref=hoje)


# ════════════════════════════════════════════════════════════════════════════
# Leitura de exame
# ════════════════════════════════════════════════════════════════════════════
def lancar_resultado(session: Session, fazenda_id: int, registro_id: int, dados: dict, *, usuario_id: Optional[int],
                     eh_admin: bool, pessoa_vet=None, hoje: Optional[date] = None) -> dict:
    """Leitura/resultado de um exame já coletado. Veterinário (pela própria
    Pessoa) ou administrador informando o veterinário responsável. Reagente
    gera só aviso. Levanta PermissionError / LookupError / ValueError."""
    from fazenda.models import SanitarioCaixa, SanitarioCaixaVersao, SanitarioRegistro

    hoje = hoje or hoje_local()
    reg = session.get(SanitarioRegistro, registro_id)
    if reg is None or reg.fazenda_id != fazenda_id or reg.estado != "valido":
        raise LookupError("Registro não encontrado.")
    cx = session.get(SanitarioCaixa, reg.caixa_id) if reg.caixa_id else None
    if cx is None or cx.tipo != "exame":
        raise ValueError("Só exames recebem leitura/resultado.")
    resultado = dados.get("resultado")
    if resultado not in RESULTADOS:
        raise ValueError("Resultado inválido.")
    vet_pid, vet_txt, crmv = dados.get("veterinario_pessoa_id"), dados.get("veterinario_texto"), dados.get("crmv_texto")
    if pessoa_vet is not None:
        vet_pid, vet_txt, crmv = pessoa_vet.id, pessoa_vet.nome, crmv or pessoa_vet.crmv
    elif eh_admin:
        if not (vet_pid or (vet_txt or "").strip()):
            raise ValueError("Informe o veterinário responsável pela leitura.")
    else:
        raise PermissionError("A leitura é lançada pelo veterinário ou pelo administrador.")
    reg.resultado, reg.resultado_valor = resultado, dados.get("resultado_valor")
    reg.resultado_detalhe = dados.get("resultado_detalhe")
    reg.leitura_em = datetime.utcnow()
    reg.veterinario_pessoa_id, reg.veterinario_texto, reg.crmv_texto = vet_pid, vet_txt, crmv
    session.add(reg)
    avisos = []
    versao = session.get(SanitarioCaixaVersao, reg.caixa_versao_id) if reg.caixa_versao_id else None
    if resultado == "positivo" and (versao is None or versao.legal_reagente_aviso):
        from fazenda.models import Animal
        _nota_reagente(session, fazenda_id, reg, cx, session.get(Animal, reg.animal_id) if reg.animal_id else None, hoje)
        avisos.append(_aviso("reagente", "Reagente: aviso registrado para os administradores (sem pendência)."))
    _log(session, fazenda_id, "registro.resultado", caixa_id=cx.id, animal_id=reg.animal_id, registro_id=reg.id,
         usuario_id=usuario_id, decisao=resultado, texto_livre=f"Leitura: {resultado}.")
    session.flush()
    return {"registro_id": reg.id, "resultado": resultado, "avisos": avisos}


# ════════════════════════════════════════════════════════════════════════════
# Desfazer (10 s) e estorno (admin)
# ════════════════════════════════════════════════════════════════════════════
def _reabrir_item_do_dia(session: Session, reg) -> None:
    from fazenda.models import SanitarioDia, SanitarioDiaItem

    if not reg.dia_item_id:
        return
    item = session.get(SanitarioDiaItem, reg.dia_item_id)
    dia = session.get(SanitarioDia, reg.dia_id) if reg.dia_id else None
    if item is not None and dia is not None and dia.estado in ("marcado", "em_execucao"):
        item.estado = "pendente"
        session.add(item)


def _soltar_situacoes(session: Session, fazenda_id: int, registro_id: int) -> None:
    from fazenda.models import SanitarioSituacao

    for s in session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.registro_id == registro_id,
    )).all():
        s.registro_id = None
        session.add(s)
    session.flush()


def desfazer(session: Session, fazenda_id: int, registro_ids: list[int], *, usuario_id: Optional[int],
             eh_admin: bool, agora: Optional[datetime] = None, hoje: Optional[date] = None) -> dict:
    """Desfaz registros gravados há no máximo DESFAZER_SEGUNDOS (com folga de
    rede): devolve o estoque e apaga o registro (nada fica no histórico; o log
    guarda o que foi desfeito)."""
    from fazenda.models import SanitarioRegistro
    from fazenda.rules.sanitario.motor import recalcular

    agora = agora or datetime.utcnow()
    limite = timedelta(seconds=DESFAZER_SEGUNDOS + TOLERANCIA_REDE_SEGUNDOS)
    feitos, recusados, afetados = [], [], set()
    for rid in registro_ids:
        reg = session.get(SanitarioRegistro, rid)
        if reg is None or reg.fazenda_id != fazenda_id or reg.estado != "valido":
            recusados.append({"registro_id": rid, "motivo": "não encontrado"})
            continue
        if not eh_admin and reg.criado_por_usuario_id not in (None, usuario_id):
            recusados.append({"registro_id": rid, "motivo": "só quem gravou (ou o administrador) desfaz"})
            continue
        if agora - reg.criado_em > limite:
            recusados.append({"registro_id": rid, "motivo": "passou o tempo de desfazer; peça o estorno ao administrador"})
            continue
        _devolver_estoque(session, fazenda_id, reg, usuario_id, "desfazer")
        _soltar_dos_prazos(session, fazenda_id, reg.id)
        _reabrir_item_do_dia(session, reg)
        _soltar_situacoes(session, fazenda_id, reg.id)
        _log(session, fazenda_id, "registro.desfeito", dia_id=reg.dia_id, caixa_id=reg.caixa_id, animal_id=reg.animal_id,
             registro_id=reg.id, usuario_id=usuario_id, texto_livre="Registro desfeito (até 10 s): estoque devolvido.",
             payload={"data": reg.data.isoformat(), "ciclo": reg.ciclo_chave, "dose": reg.dose_num})
        if reg.animal_id:
            afetados.add(reg.animal_id)
        session.delete(reg)
        feitos.append(rid)
    session.flush()
    if afetados:
        recalcular(session, fazenda_id, animal_ids=afetados, motivo="desfazer", hoje=hoje)
    return {"desfeitos": feitos, "recusados": recusados}


def estornar(session: Session, fazenda_id: int, registro_id: int, motivo: str, *, usuario_id: Optional[int],
             hoje: Optional[date] = None) -> dict:
    """Estorno (só administrador, com motivo): o registro fica no histórico
    marcado "estornado", o estoque volta, a carência sai e a próxima dose não
    aplicada da série some (o motor recalcula sem este registro)."""
    from fazenda.models import SanitarioRegistro
    from fazenda.rules.sanitario.motor import recalcular

    if not (motivo or "").strip():
        raise ValueError("Informe o motivo do estorno.")
    reg = session.get(SanitarioRegistro, registro_id)
    if reg is None or reg.fazenda_id != fazenda_id:
        raise LookupError("Registro não encontrado.")
    if reg.estado == "estornado":
        return {"registro_id": reg.id, "estado": "estornado", "avisos": [], "ja_estornado": True}
    avisos = _devolver_estoque(session, fazenda_id, reg, usuario_id, "estorno")
    antes = {"carencia_leite_ate": _iso(reg.carencia_leite_ate), "carencia_carne_ate": _iso(reg.carencia_carne_ate),
             "carencia_modo": reg.carencia_modo, "quantidade_baixada": reg.quantidade_baixada}
    reg.estado, reg.estornado_em, reg.estornado_por_usuario_id = "estornado", datetime.utcnow(), usuario_id
    reg.estornado_motivo = motivo.strip()
    reg.carencia_leite_ate = reg.carencia_carne_ate = None
    session.add(reg)
    _soltar_dos_prazos(session, fazenda_id, reg.id)
    _reabrir_item_do_dia(session, reg)
    _soltar_situacoes(session, fazenda_id, reg.id)
    _log(session, fazenda_id, "registro.estorno", dia_id=reg.dia_id, caixa_id=reg.caixa_id, animal_id=reg.animal_id,
         registro_id=reg.id, usuario_id=usuario_id, texto_livre=f"Estorno: {motivo.strip()}", payload=antes)
    session.flush()
    if reg.animal_id:
        recalcular(session, fazenda_id, animal_ids=[reg.animal_id], motivo="estorno", hoje=hoje)
    return {"registro_id": reg.id, "estado": "estornado", "avisos": avisos}


# ════════════════════════════════════════════════════════════════════════════
# Conflito entre aparelhos (offline)
# ════════════════════════════════════════════════════════════════════════════
def decidir_conflito(session: Session, fazenda_id: int, log_id: int, manter: str, *, usuario_id: Optional[int],
                     eh_admin: bool, hoje: Optional[date] = None) -> dict:
    """`manter`: "existente" (descarta o que chegou depois) ou "novo" (estorna
    o existente e grava o que chegou). Decide o aplicador (quem gravou um dos
    dois) ou o administrador."""
    from fazenda.models import SanitarioDia, SanitarioLog, SanitarioRegistro

    lg = session.get(SanitarioLog, log_id)
    if lg is None or lg.fazenda_id != fazenda_id or lg.tipo != "offline.conflito":
        raise LookupError("Conflito não encontrado.")
    payload = dict(lg.payload or {})
    if payload.get("resolvido"):
        return {"log_id": lg.id, "ja_resolvido": True, "decisao": payload.get("decisao")}
    existente = session.get(SanitarioRegistro, payload.get("existente_id")) if payload.get("existente_id") else None
    envolvidos = {lg.usuario_id, existente.criado_por_usuario_id if existente else None}
    if not eh_admin and usuario_id not in envolvidos:
        raise PermissionError("O conflito é decidido pelo aplicador ou pelo administrador.")
    if manter not in ("existente", "novo"):
        raise ValueError("Decisão inválida (use existente ou novo).")
    res: dict = {"log_id": lg.id, "decisao": manter}
    if manter == "novo":
        if existente is not None and existente.estado == "valido":
            estornar(session, fazenda_id, existente.id, "conflito entre aparelhos: vale o registro que chegou depois",
                     usuario_id=usuario_id, hoje=hoje)
        dia = session.get(SanitarioDia, payload.get("dia_id")) if payload.get("dia_id") else None
        item = dict(payload.get("item") or {})
        item["chave_idempotencia"] = None
        item.setdefault("consentimento", {"aceito": True, "motivo_exibido": "decisão de conflito"})
        r = registrar(session, fazenda_id, [item], origem=payload.get("origem") or "dia",
                      canal=payload.get("canal") or "app", usuario_id=usuario_id, eh_admin=eh_admin, dia=dia, hoje=hoje)
        res["registro"] = r["itens"][0]
    payload.update(resolvido=True, decisao=manter, decidido_por=usuario_id)
    lg.payload = payload
    session.add(lg)
    _log(session, fazenda_id, "offline.conflito_decidido", dia_id=lg.dia_id, caixa_id=lg.caixa_id, animal_id=lg.animal_id,
         usuario_id=usuario_id, decisao=manter, texto_livre=f"Conflito {lg.id}: vale o registro {manter}.")
    session.flush()
    return res
