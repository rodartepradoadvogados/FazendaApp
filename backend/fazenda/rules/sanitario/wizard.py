"""
Wizard do cadastro (9 etapas que deslizam) — validação etapa a etapa,
prévia "entram / ficam de fora e por quê" SEM GRAVAR, e a ida-e-volta da
definição (o GET devolve exatamente o formato que o wizard envia).

Etapas: 1 identificação · 2 produto · 3 público · 4 janela · 5 aglomeração
e aviso · 6 veterinário e etapas legais · 7 carência (sempre visível,
opcional) · 8 ficha de campo · 9 revisão (= todas).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlmodel import Session, select

from fazenda.models.sanitario_preventivo import (
    AO_FECHAR, CARENCIA_MODOS_LEITE, CONDICOES, DOSE_UNIDADES, EVENTO_TIPOS, PERIODO_MODOS, PRODUTO_MODOS, TIPOS_CAIXA,
)
from fazenda.rules.sanitario.definicao import CAMPOS_CAIXA, CAMPOS_VERSAO, normalizar
from fazenda.rules.sanitario.tipos import CaixaDef

ETAPAS = {
    1: ("identificacao", ("nome", "nome_curto", "tipo", "obrigatoria")),
    2: ("produto", ("produto_modo", "estoque_id", "produto_texto", "dose_valor", "dose_unidade", "dose_x_kg",
                    "peso_ausente")),
    3: ("publico", ("pub_sexo", "pub_cat_modo", "categorias", "pub_idade_min_dias", "pub_idade_max_dias",
                    "pub_condicoes", "pub_hist_tipo", "pub_hist_caixa_id")),
    4: ("janela", ("jan_usa_evento", "evento_tipo", "evento_de_dias", "evento_ate_dias", "jan_usa_periodo",
                   "periodo_modo", "periodo_grupos", "periodo_anos", "periodo_ano_base", "data_base_dia",
                   "comecar_em", "ao_fechar", "serie")),
    5: ("aviso", ("aglo_min", "aviso_antecedencia_dias", "aviso_fim_janela_dias", "push_admin")),
    6: ("legal", ("legal_crmv_pedir", "legal_atestado", "legal_comprovacao", "legal_leitura", "legal_reagente_aviso",
                  "legal_marca_texto")),
    7: ("carencia", ("car_leite_dias", "car_carne_dias", "car_modo_leite")),
    8: ("ficha", ("ficha_colunas", "observacao")),
}
COLUNAS_FICHA_OK = ("brinco", "categoria", "lote", "idade", "peso", "dose", "partida", "aplicado", "resultado",
                    "assinatura", "obs")


def _e(erros: list, etapa: int, campo: str, msg: str) -> None:
    erros.append({"etapa": etapa, "campo": campo, "mensagem": msg})


def validar(session: Session, fazenda_id: int, d: dict, etapa: Optional[int] = None,
            caixa_id: Optional[int] = None) -> list[dict]:
    """Erros da etapa pedida (ou de todas, etapa 9/None). Não grava nada."""
    from fazenda.models import CategoriaManejo, Estoque, SanitarioCaixa

    erros: list[dict] = []
    alvo = range(1, 9) if etapa in (None, 9) else [etapa]
    tipo = d.get("tipo") or "vacina"
    for et in alvo:
        if et == 1:
            nome = (d.get("nome") or "").strip()
            if not nome:
                _e(erros, 1, "nome", "Dê um nome ao cadastro para seguir.")
            elif session is not None:
                dup = session.exec(select(SanitarioCaixa).where(
                    SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.nome_normalizado == normalizar(nome),
                    SanitarioCaixa.estado != "arquivada")).first()
                if dup is not None and dup.id != caixa_id:
                    _e(erros, 1, "nome", f'Já existe "{dup.nome}" nesta fazenda (arquive ou mescle antes).')
            if tipo not in TIPOS_CAIXA:
                _e(erros, 1, "tipo", "Tipo inválido.")
        elif et == 2 and tipo != "exame":
            modo = d.get("produto_modo") or "vazio"
            if modo not in PRODUTO_MODOS:
                _e(erros, 2, "produto_modo", "Escolha como o produto é controlado.")
            if modo == "estoque":
                eid = d.get("estoque_id")
                e = session.get(Estoque, int(eid)) if (eid and session is not None) else None
                if e is None or e.fazenda_id not in (None, fazenda_id):
                    _e(erros, 2, "estoque_id", "Escolha um item do estoque desta fazenda.")
            un = d.get("dose_unidade")
            if un is not None and un not in DOSE_UNIDADES:
                _e(erros, 2, "dose_unidade", "Unidade de dose fora da lista.")
            if d.get("dose_valor") is not None and float(d["dose_valor"]) < 0:
                _e(erros, 2, "dose_valor", "A dose não pode ser negativa.")
            if un == "mL_por_x_kg" and not d.get("dose_x_kg"):
                _e(erros, 2, "dose_x_kg", 'Informe o "X kg" da dose (ex.: 1 mL por 50 kg).')
            if (d.get("peso_ausente") or "estimado") not in ("exigir", "estimado"):
                _e(erros, 2, "peso_ausente", "Use exigir ou estimado.")
        elif et == 3:
            if (d.get("pub_sexo") or "ambos") not in ("F", "M", "ambos"):
                _e(erros, 3, "pub_sexo", "Sexo: F, M ou ambos.")
            if (d.get("pub_cat_modo") or "incluir") not in ("incluir", "excluir"):
                _e(erros, 3, "pub_cat_modo", "Use incluir ou excluir.")
            cats = [int(c) for c in (d.get("categorias") or [])]
            if cats and session is not None:
                ok = set(session.exec(select(CategoriaManejo.id).where(
                    CategoriaManejo.fazenda_id == fazenda_id, CategoriaManejo.id.in_(cats))).all())
                if set(cats) - ok:
                    _e(erros, 3, "categorias", "Há categoria que não é desta fazenda.")
            mi, ma = d.get("pub_idade_min_dias"), d.get("pub_idade_max_dias")
            if mi is not None and ma is not None and int(mi) > int(ma):
                _e(erros, 3, "pub_idade_max_dias", "A idade máxima é menor que a mínima.")
            for c in d.get("pub_condicoes") or []:
                if c not in CONDICOES:
                    _e(erros, 3, "pub_condicoes", f"Condição fora da lista: {c}.")
            ht = d.get("pub_hist_tipo")
            if ht is not None:
                if ht not in ("ja", "nunca"):
                    _e(erros, 3, "pub_hist_tipo", "Histórico: ja ou nunca.")
                hc = d.get("pub_hist_caixa_id")
                cx = session.get(SanitarioCaixa, int(hc)) if (hc and session is not None) else None
                if cx is None or cx.fazenda_id != fazenda_id:
                    _e(erros, 3, "pub_hist_caixa_id", 'Escolha a vacina de referência do "já/nunca recebeu".')
        elif et == 4:
            ev, per = bool(d.get("jan_usa_evento")), bool(d.get("jan_usa_periodo"))
            if not ev and not per:
                _e(erros, 4, "jan_usa_evento", "Use a janela por evento de vida, por período do ano, ou as duas.")
            if ev:
                if d.get("evento_tipo") not in EVENTO_TIPOS:
                    _e(erros, 4, "evento_tipo", "Escolha o evento de vida.")
                de, ate = d.get("evento_de_dias"), d.get("evento_ate_dias")
                if de is None or ate is None:
                    _e(erros, 4, "evento_ate_dias", 'Informe "de X dias" e "até Y dias".')
                elif int(de) > int(ate):
                    _e(erros, 4, "evento_ate_dias", "O fim da janela vem antes do começo.")
            if per:
                modo = d.get("periodo_modo")
                if modo not in PERIODO_MODOS:
                    _e(erros, 4, "periodo_modo", "Escolha meses, frequência ou contínuo.")
                grupos = d.get("periodo_grupos") or []
                if modo in ("meses", "frequencia"):
                    if not grupos:
                        _e(erros, 4, "periodo_grupos", "Marque ao menos um mês.")
                    vistos: set[int] = set()
                    for g in grupos:
                        if not g or any((not isinstance(m, int)) or m < 0 or m > 11 for m in g):
                            _e(erros, 4, "periodo_grupos", "Meses vão de 0 (jan) a 11 (dez).")
                            break
                        if vistos & set(g):
                            _e(erros, 4, "periodo_grupos", "Um mês aparece em dois grupos.")
                            break
                        vistos |= set(g)
                if modo == "frequencia" and not (d.get("periodo_anos") and int(d["periodo_anos"]) >= 1):
                    _e(erros, 4, "periodo_anos", "Informe a cada quantos anos.")
                dbd = d.get("data_base_dia")
                if dbd is not None and not (1 <= int(dbd) <= 28):
                    _e(erros, 4, "data_base_dia", "Dia da data-base entre 1 e 28.")
            if (d.get("ao_fechar") or "manter") not in AO_FECHAR:
                _e(erros, 4, "ao_fechar", "Ao fechar: perder, manter ou descartar.")
            for s in d.get("serie") or []:
                if int(s.get("dose") or 0) < 2 or int(s.get("apos_dias") or 0) < 1:
                    _e(erros, 4, "serie", "Série: dose 2 em diante, após N dias (N ≥ 1).")
                    break
        elif et == 5:
            if d.get("aglo_min") is not None and int(d["aglo_min"]) < 1:
                _e(erros, 5, "aglo_min", "O mínimo para avisar é pelo menos 1 animal.")
            if d.get("aviso_antecedencia_dias") is not None and int(d["aviso_antecedencia_dias"]) < 0:
                _e(erros, 5, "aviso_antecedencia_dias", "Antecedência não pode ser negativa.")
        elif et == 6:
            at = d.get("legal_atestado")
            if at:
                if (at.get("quando") or "primeiro") not in ("aplicacao", "nfe", "primeiro"):
                    _e(erros, 6, "legal_atestado", "Quando: aplicacao, nfe ou primeiro.")
                if at.get("dias") is not None and int(at["dias"]) < 0:
                    _e(erros, 6, "legal_atestado", "Prazo do atestado inválido.")
            co = d.get("legal_comprovacao")
            if co and int(co.get("dias") or 0) < 1:
                _e(erros, 6, "legal_comprovacao", "Informe a cada quantos dias (ex.: 180).")
            le = d.get("legal_leitura")
            if le and (le.get("modo") or "so_resultado") not in ("so_resultado", "diferenca", "medidas"):
                _e(erros, 6, "legal_leitura", "Modo de leitura: so_resultado, diferenca ou medidas.")
        elif et == 7:
            for k in ("car_leite_dias", "car_carne_dias"):
                if d.get(k) is not None and int(d[k]) < 0:
                    _e(erros, 7, k, "Carência não pode ser negativa.")
            m = d.get("car_modo_leite")
            if m is not None and m not in CARENCIA_MODOS_LEITE:
                _e(erros, 7, "car_modo_leite", "Modo do leite: bloqueio, descarte ou tanque.")
        elif et == 8:
            for c in d.get("ficha_colunas") or []:
                if c not in COLUNAS_FICHA_OK:
                    _e(erros, 8, "ficha_colunas", f"Coluna fora da lista: {c}.")
    return erros


def caixa_def_de_definicao(d: dict, caixa_id: int = 0, hist_nome: Optional[str] = None,
                           ativada_em: Optional[date] = None) -> CaixaDef:
    """Definição (payload do wizard) -> CaixaDef PURA, sem tocar no banco —
    serve à prévia "entram / ficam de fora" sem gravar."""
    comecar = d.get("comecar_em")
    if isinstance(comecar, str):
        comecar = date.fromisoformat(comecar)
    return CaixaDef(
        caixa_id=caixa_id, versao_id=None, nome=d.get("nome") or "(sem nome)",
        nome_curto=d.get("nome_curto") or d.get("nome") or "(sem nome)", tipo=d.get("tipo") or "vacina",
        ativada_em=ativada_em,
        produto_modo=d.get("produto_modo") or "vazio", estoque_id=d.get("estoque_id"),
        dose_valor=d.get("dose_valor"), dose_unidade=d.get("dose_unidade"), dose_x_kg=d.get("dose_x_kg"),
        pub_sexo=d.get("pub_sexo") or "ambos", pub_cat_modo=d.get("pub_cat_modo") or "incluir",
        categorias=frozenset(int(c) for c in (d.get("categorias") or [])),
        pub_idade_min_dias=d.get("pub_idade_min_dias"), pub_idade_max_dias=d.get("pub_idade_max_dias"),
        pub_condicoes=tuple(d.get("pub_condicoes") or ()),
        pub_hist_tipo=d.get("pub_hist_tipo"), pub_hist_caixa_id=d.get("pub_hist_caixa_id"), pub_hist_nome=hist_nome,
        jan_usa_evento=bool(d.get("jan_usa_evento")), evento_tipo=d.get("evento_tipo"),
        evento_de_dias=d.get("evento_de_dias"), evento_ate_dias=d.get("evento_ate_dias"),
        jan_usa_periodo=bool(d.get("jan_usa_periodo")), periodo_modo=d.get("periodo_modo"),
        periodo_grupos=tuple(tuple(g) for g in (d.get("periodo_grupos") or ())),
        periodo_anos=d.get("periodo_anos"), periodo_ano_base=d.get("periodo_ano_base"),
        data_base_dia=d.get("data_base_dia") or 15, comecar_em=comecar, ao_fechar=d.get("ao_fechar") or "manter",
        serie=tuple(d.get("serie") or ()),
        aglo_min=d.get("aglo_min") if d.get("aglo_min") is not None else 4,
        aviso_antecedencia_dias=d.get("aviso_antecedencia_dias") if d.get("aviso_antecedencia_dias") is not None else 30,
        aviso_fim_janela_dias=d.get("aviso_fim_janela_dias"),
    )


def previa(session: Session, fazenda_id: int, d: dict, data_base: date, hoje: Optional[date] = None) -> dict:
    """"Entram / ficam de fora e por quê" na data-base — SÓ LÊ."""
    from fazenda.models import SanitarioCaixa
    from fazenda.rules.sanitario.contexto import carregar_animais
    from fazenda.rules.sanitario.motor import ok_na_data, situacao_atual

    hist_nome = None
    if d.get("pub_hist_caixa_id"):
        cx = session.get(SanitarioCaixa, int(d["pub_hist_caixa_id"]))
        hist_nome = (cx.nome_curto or cx.nome) if cx and cx.fazenda_id == fazenda_id else None
    cxd = caixa_def_de_definicao(d, caixa_id=-1, hist_nome=hist_nome)
    animais = carregar_animais(session, fazenda_id, hoje=hoje)
    entram, fora = [], []
    for a in sorted(animais.values(), key=lambda x: x.numero):
        if not a.ativo:
            continue
        nd = ok_na_data(cxd, a, data_base)
        s = situacao_atual(cxd, a, data_base)
        motivos = [{"ok": m.ok, "texto": m.texto} for m in s.motivos]
        linha = {"animal_id": a.id, "numero": a.numero, "categoria": a.categoria_em(data_base)[1],
                 "estado": s.estado, "texto": s.texto, "motivos": motivos}
        if nd.ok:
            entram.append(linha)
        else:
            linha["motivo"] = nd.texto
            fora.append(linha)
    return {"data_base": data_base.isoformat(), "entram": entram, "fora": fora,
            "contagem": {"entram": len(entram), "fora": len(fora)}}


def definicao_da_versao(session: Session, caixa, versao) -> dict:
    """GET devolve exatamente o formato do wizard (ida-e-volta)."""
    from fazenda.models import SanitarioCaixaVersaoCategoria

    d = {k: getattr(caixa, k) for k in CAMPOS_CAIXA}
    if versao is None:
        return d
    for k in CAMPOS_VERSAO:
        v = getattr(versao, k)
        d[k] = v.isoformat() if isinstance(v, date) else v
    d["categorias"] = sorted(session.exec(select(SanitarioCaixaVersaoCategoria.categoria_manejo_id).where(
        SanitarioCaixaVersaoCategoria.fazenda_id == caixa.fazenda_id,
        SanitarioCaixaVersaoCategoria.versao_id == versao.id)).all())
    return d
