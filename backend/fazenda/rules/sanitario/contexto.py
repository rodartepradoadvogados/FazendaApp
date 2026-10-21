"""
Carga do contexto do motor — uma leva de consultas, SÓ LEITURA.

`carregar_caixas` achata a versão vigente de cada caixa em `CaixaDef`
(categorias por ID). `carregar_animais` monta o `AnimalCtx` de cada animal:
nascimento, sexo, saída, gestações (parto previsto por serviço positivo e
parto real), entrada em IA, partos, secagens, compra, peso, registros
válidos por caixa, dispensas, dias abertos e o classificador PURO de
categoria projetada (mesma classificação de Recria/Lote, por ID).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlmodel import Session, select

from fazenda.rules.datas import hoje_local
from fazenda.rules.sanitario.tipos import AnimalCtx, CaixaDef, Gestacao, RegistroCtx

logger = logging.getLogger(__name__)

DIAS_ABERTOS = ("marcado", "em_execucao")


def caixa_def(caixa, versao, categorias: Iterable[int] = (), hist_nome: Optional[str] = None) -> CaixaDef:
    """`SanitarioCaixa` + `SanitarioCaixaVersao` -> `CaixaDef` (puro)."""
    return CaixaDef(
        caixa_id=caixa.id, versao_id=versao.id if versao is not None else None,
        nome=caixa.nome, nome_curto=caixa.nome_curto or caixa.nome, tipo=caixa.tipo,
        ativada_em=caixa.ativada_em,
        produto_modo=versao.produto_modo, estoque_id=versao.estoque_id,
        dose_valor=versao.dose_valor, dose_unidade=versao.dose_unidade, dose_x_kg=versao.dose_x_kg,
        pub_sexo=versao.pub_sexo or "ambos", pub_cat_modo=versao.pub_cat_modo or "incluir",
        categorias=frozenset(int(c) for c in categorias),
        pub_idade_min_dias=versao.pub_idade_min_dias, pub_idade_max_dias=versao.pub_idade_max_dias,
        pub_condicoes=tuple(versao.pub_condicoes or ()),
        pub_hist_tipo=versao.pub_hist_tipo, pub_hist_caixa_id=versao.pub_hist_caixa_id, pub_hist_nome=hist_nome,
        jan_usa_evento=bool(versao.jan_usa_evento), evento_tipo=versao.evento_tipo,
        evento_de_dias=versao.evento_de_dias, evento_ate_dias=versao.evento_ate_dias,
        jan_usa_periodo=bool(versao.jan_usa_periodo), periodo_modo=versao.periodo_modo,
        periodo_grupos=tuple(tuple(g) for g in (versao.periodo_grupos or ())),
        periodo_anos=versao.periodo_anos, periodo_ano_base=versao.periodo_ano_base,
        data_base_dia=versao.data_base_dia or 15, comecar_em=versao.comecar_em,
        ao_fechar=versao.ao_fechar or "manter", serie=tuple(versao.serie or ()),
        aglo_min=versao.aglo_min if versao.aglo_min is not None else 4,
        aviso_antecedencia_dias=versao.aviso_antecedencia_dias if versao.aviso_antecedencia_dias is not None else 30,
        aviso_fim_janela_dias=versao.aviso_fim_janela_dias,
    )


def carregar_caixas(
    session: Session, fazenda_id: int, caixa_ids: Optional[Iterable[int]] = None, so_ativas: bool = True,
) -> list[CaixaDef]:
    from fazenda.models import SanitarioCaixa, SanitarioCaixaVersao, SanitarioCaixaVersaoCategoria

    q = select(SanitarioCaixa).where(SanitarioCaixa.fazenda_id == fazenda_id)
    if so_ativas:
        q = q.where(SanitarioCaixa.estado == "ativa")
    else:
        q = q.where(SanitarioCaixa.estado != "arquivada")
    if caixa_ids is not None:
        ids = [int(i) for i in caixa_ids]
        if not ids:
            return []
        q = q.where(SanitarioCaixa.id.in_(ids))
    caixas = list(session.exec(q.order_by(SanitarioCaixa.id)).all())
    if not caixas:
        return []
    vids = [c.versao_atual_id for c in caixas if c.versao_atual_id]
    versoes = {
        v.id: v for v in session.exec(select(SanitarioCaixaVersao).where(
            SanitarioCaixaVersao.fazenda_id == fazenda_id, SanitarioCaixaVersao.id.in_(vids or [-1]),
        )).all()
    }
    cats: dict[int, list[int]] = {}
    for vc in session.exec(select(SanitarioCaixaVersaoCategoria).where(
        SanitarioCaixaVersaoCategoria.fazenda_id == fazenda_id,
        SanitarioCaixaVersaoCategoria.versao_id.in_(vids or [-1]),
    )).all():
        cats.setdefault(vc.versao_id, []).append(vc.categoria_manejo_id)
    hist_ids = {v.pub_hist_caixa_id for v in versoes.values() if v.pub_hist_caixa_id}
    nomes = {}
    if hist_ids:
        nomes = {c.id: (c.nome_curto or c.nome) for c in session.exec(select(SanitarioCaixa).where(
            SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.id.in_(hist_ids))).all()}
    out = []
    for c in caixas:
        v = versoes.get(c.versao_atual_id)
        if v is None:
            continue  # caixa sem versão não gera nada
        out.append(caixa_def(c, v, cats.get(v.id, ()), nomes.get(v.pub_hist_caixa_id)))
    return out


# ── classificação de categoria (pura, depois de carregada) ─────────────────
def _parametros_vivo() -> tuple:
    try:
        from fazenda.api.routers.recria import _parametros_estado_vivo
        return _parametros_estado_vivo()
    except Exception:  # pragma: no cover - parâmetros indisponíveis: padrões do sistema
        logger.exception("sanitario: parâmetros do estado reprodutivo indisponíveis; usando padrões")
        return (45, 100, 396, 340.0, 913, 120)


def _classificador(numero, raca, nasc, sit_rep, servicos, partos, secagens, pesagens, categorias, params):
    """Fecha sobre os objetos já carregados e devolve f(d) -> (categoria_id, nome),
    projetando a idade/peso para a data `d` (mesmo critério de
    rules/projecao_categoria.py, mas devolvendo o ID)."""
    from fazenda.api.routers.recria import _contexto_categoria, _dentro_faixa, situacao_reprodutiva_casa

    pev, del_max, idade_apta, peso_apta, idade_atraso, dias_pos_apt = params
    ordenadas = sorted(categorias, key=lambda c: (c.ordem, c.dia_min))
    pes = sorted(pesagens)

    def f(d: date) -> tuple:
        if nasc is None:
            return (None, "sem data de nascimento")
        dias = (d - nasc).days
        peso = None
        for dt, kg in pes:
            if dt <= d:
                peso = kg
        try:
            ctx = _contexto_categoria(
                dias, peso, sit_rep, d, servicos, partos, secagens, raca=raca, numero=numero,
                pev_dias=pev, del_max_1o_servico=del_max, idade_apta_dias=idade_apta, peso_apta_kg=peso_apta,
                idade_atraso_dias=idade_atraso, data_nasc=nasc, pesagens=pes, dias_atraso_apos_aptidao=dias_pos_apt,
            )
        except Exception:  # pragma: no cover - dado reprodutivo inconsistente não derruba o motor
            logger.exception("sanitario: falha ao classificar o animal %s", numero)
            return (None, "sem categoria")
        sit3 = ctx.get("situacao_reprodutiva_viva")
        for cat in ordenadas:
            if dias < cat.dia_min or (cat.dia_max is not None and dias > cat.dia_max):
                continue
            if (cat.peso_min_kg is not None and (peso is None or peso < cat.peso_min_kg)) or (
                    cat.peso_max_kg is not None and peso is not None and peso > cat.peso_max_kg):
                continue
            if not situacao_reprodutiva_casa(cat.situacao_reprodutiva, sit3):
                continue
            if cat.situacao_produtiva and cat.situacao_produtiva != ctx.get("situacao_produtiva"):
                continue
            if not _dentro_faixa(ctx.get("dias_gestacao"), cat.dias_gestacao_min, cat.dias_gestacao_max):
                continue
            if not _dentro_faixa(ctx.get("dias_desde_servico"), cat.dias_desde_servico_min, cat.dias_desde_servico_max):
                continue
            if not _dentro_faixa(ctx.get("dias_para_parto"), cat.dias_para_parto_min, cat.dias_para_parto_max):
                continue
            if not _dentro_faixa(ctx.get("dias_pos_parto"), cat.dias_pos_parto_min, cat.dias_pos_parto_max):
                continue
            return (cat.id, cat.nome)
        return (None, "fora das faixas de categoria")

    return f


def _dias_gestacao(raca: Optional[str]) -> int:
    try:
        from fazenda.rules.gestation import dias_gestacao
        return int(round(dias_gestacao(raca)))
    except Exception:  # pragma: no cover
        return 283


def carregar_animais(
    session: Session, fazenda_id: int, animal_ids: Optional[Iterable[int]] = None, hoje: Optional[date] = None,
) -> dict[int, AnimalCtx]:
    from fazenda.models import (
        Animal, CategoriaManejo, CompraAnimal, Parto, PesagemCorporal, SanitarioDia, SanitarioDiaItem,
        SanitarioRegistro, SanitarioSituacao, Secagem, Servico,
    )
    from fazenda.rules.parametros import fazenda_atual

    hoje = hoje or hoje_local()
    q = select(Animal).where(Animal.fazenda_id == fazenda_id, Animal.eh_semen == False)  # noqa: E712
    if animal_ids is not None:
        ids = [int(i) for i in animal_ids]
        if not ids:
            return {}
        q = q.where(Animal.id.in_(ids))
    animais = list(session.exec(q).all())
    if not animais:
        return {}
    numeros = {a.numero for a in animais}
    por_numero: dict[str, Animal] = {a.numero: a for a in animais}
    ids = [a.id for a in animais]

    def _por_num(modelo, campo_num="numero_matriz"):
        col = getattr(modelo, campo_num)
        rows = session.exec(select(modelo).where(modelo.fazenda_id == fazenda_id, col.in_(numeros))).all()
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(getattr(r, campo_num), []).append(r)
        return out

    servicos = _por_num(Servico)
    partos = _por_num(Parto)
    secagens = _por_num(Secagem)
    pesagens = _por_num(PesagemCorporal)
    compras = _por_num(CompraAnimal, "numero_animal")
    categorias = list(session.exec(select(CategoriaManejo).where(
        CategoriaManejo.fazenda_id == fazenda_id, CategoriaManejo.ativo == True,  # noqa: E712
    )).all())

    token = fazenda_atual.set(fazenda_id)
    try:
        params = _parametros_vivo()
        cache_gest: dict[Optional[str], int] = {}
        for a in animais:
            if a.raca not in cache_gest:
                cache_gest[a.raca] = _dias_gestacao(a.raca)
    finally:
        fazenda_atual.reset(token)

    registros: dict[int, dict[int, list]] = {}
    for r in session.exec(select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.estado == "valido",
        SanitarioRegistro.animal_id.in_(ids),
    )).all():
        if r.caixa_id is None:
            continue
        registros.setdefault(r.animal_id, {}).setdefault(r.caixa_id, []).append(RegistroCtx(
            id=r.id, caixa_id=r.caixa_id, ciclo_chave=r.ciclo_chave, dose_num=r.dose_num or 1,
            data=r.data, so_registro=bool(r.so_registro),
        ))
    dispensas: dict[int, set] = {}
    for s in session.exec(select(SanitarioSituacao).where(
        SanitarioSituacao.fazenda_id == fazenda_id, SanitarioSituacao.animal_id.in_(ids),
        SanitarioSituacao.dispensada_em != None,  # noqa: E711
    )).all():
        dispensas.setdefault(s.animal_id, set()).add((s.caixa_id, s.ciclo_chave, s.dose_num))
    dias: dict[int, dict[int, tuple]] = {}
    for item, dia in session.exec(
        select(SanitarioDiaItem, SanitarioDia).where(
            SanitarioDiaItem.fazenda_id == fazenda_id, SanitarioDiaItem.dia_id == SanitarioDia.id,
            SanitarioDia.fazenda_id == fazenda_id, SanitarioDia.estado.in_(DIAS_ABERTOS),
            SanitarioDiaItem.estado == "pendente", SanitarioDiaItem.animal_id.in_(ids),
        )
    ).all():
        atual = dias.setdefault(item.animal_id, {}).get(item.caixa_id)
        if atual is None or dia.data < atual[1]:
            dias[item.animal_id][item.caixa_id] = (dia.id, dia.data)

    out: dict[int, AnimalCtx] = {}
    for a in animais:
        n = a.numero
        servs = sorted((s for s in servicos.get(n, []) if s.data_servico), key=lambda s: (s.data_servico, s.id))
        pts = sorted(p.data_parto for p in partos.get(n, []) if p.data_parto)
        secs = sorted(s.data_secagem for s in secagens.get(n, []) if s.data_secagem)
        gest = []
        for s in servs:
            if (s.diagnostico or "").strip().upper() != "POSITIVO":
                continue
            prev = s.data_servico + timedelta(days=cache_gest.get(a.raca, 283))
            real = next((p for p in pts if p > s.data_servico + timedelta(days=60)), None)
            gest.append(Gestacao(servico_id=s.id, data_servico=s.data_servico, parto_previsto=prev,
                                 parto_real=real, perda=s.data_perda_prenhez))
        # Entrada em IA: o primeiro serviço da novilha (antes de qualquer parto).
        entrada = None
        for s in servs:
            if not pts or s.data_servico < pts[0]:
                entrada = s.data_servico
                break
        compra = min((c.data_compra for c in compras.get(n, []) if c.data_compra), default=None)
        pes = [(p.data_pesagem, p.peso_kg) for p in pesagens.get(n, []) if p.data_pesagem and p.peso_kg]
        peso = max(pes)[1] if pes else None
        saida = None
        if not a.ativo:
            quando = f" em {a.data_baixa.strftime('%d/%m/%Y')}" if a.data_baixa else ""
            saida = f"{(a.motivo_baixa or 'Saiu do rebanho').strip()}{quando}"
        out[a.id] = AnimalCtx(
            id=a.id, numero=n, hoje=hoje, sexo=(a.sexo or None), nasc=a.data_nasc, ativo=bool(a.ativo),
            saida_txt=saida, gestacoes=tuple(gest), entrada_ia=entrada, partos=tuple(pts), secagens=tuple(secs),
            compra=compra, peso=peso, idade_apta_dias=int(params[2] or 396),
            registros={k: sorted(v, key=lambda r: (r.data, r.id)) for k, v in registros.get(a.id, {}).items()},
            dispensas=frozenset(dispensas.get(a.id, ())),
            dias=dias.get(a.id, {}),
            classificador=_classificador(
                n, a.raca, a.data_nasc, a.sit_rep, servs, partos.get(n, []), secagens.get(n, []), pes, categorias, params,
            ),
        )
    del por_numero
    return out
