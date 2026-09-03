"""
Relatório de Não Conformidades — visão única de tudo que está fora da
meta/parâmetro/padrão cadastrado na fazenda hoje (reprodução, recria,
financeiro, manejo).

Não recalcula nada: é um agregador que chama, em processo, as mesmas
funções/endpoints que cada tela já usa (`calcular_indicadores_fazenda` da
Capa, `relatorios_manejo` das Listas, os endpoints de Recria e o RMCA do
Financeiro) e normaliza o resultado num formato comum — indicador, valor
atual, meta, e status (ok/atencao/critico). Cada item linka de volta para a
tela de origem, onde o gráfico completo já existe.

Endpoint: GET /nao-conformidades
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import select

from fazenda.auth import get_current_user, get_fazenda_atual_id, tem_modulo
from fazenda.database import get_session
from fazenda.models import EstoqueSemen, Usuario
from fazenda.rules import relatorios_gerenciais as rg

router = APIRouter(prefix="/nao-conformidades", tags=["nao-conformidades"])


def _item(chave: str, dominio: str, label: str, sublabel: str, valor: float, meta: float | None,
          unidade: str, maior_melhor: bool, status: str, rota: str, rota_label: str) -> dict:
    return {
        "chave": chave, "dominio": dominio, "label": label, "sublabel": sublabel,
        "valor": valor, "meta": meta, "unidade": unidade, "maior_melhor": maior_melhor,
        "status": status, "rota": rota, "rota_label": rota_label,
    }


def _status(valor: float | None, meta: float | None, maior_melhor: bool, limiar_critico: float = 0.20) -> str | None:
    """ok / atencao / critico a partir de valor vs. meta — None se não dá pra
    avaliar (falta valor ou meta). O desvio relativo (sobre a meta, ou sobre
    o próprio valor quando a meta é zero, ex.: RMCA) decide crítico x
    atenção: 20% ou mais de distância da meta = crítico."""
    if valor is None or meta is None:
        return None
    diff = (valor - meta) if maior_melhor else (meta - valor)
    if diff >= -1e-9:
        return "ok"
    referencia = abs(meta) or abs(valor) or 1
    return "critico" if abs(diff) / referencia >= limiar_critico else "atencao"


def _status_contagem(n: int) -> str:
    """Itens de manejo são contagens de animais fora do padrão (meta = 0) —
    severidade por faixa em vez de desvio relativo (0 é indefinido como base)."""
    if n <= 0:
        return "ok"
    return "atencao" if n <= 2 else "critico"


@router.get("/")
def relatorio_nao_conformidades(
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session=Depends(get_session),
) -> dict:
    from fazenda.api.routers.financeiro import custo_litro_leite, rmca as calcular_rmca_view
    from fazenda.api.routers.indicadores import calcular_indicadores_fazenda
    from fazenda.api.routers.recria import reproducao_idade_parto, reproducao_taxa_prenhez
    from fazenda.api.routers.relatorio_custo_hectare import custo_por_hectare
    from fazenda.api.routers.relatorios import _dados as _dados_manejo, _dados_estado_vivo

    hoje = date.today()
    itens: list[dict] = []
    sem_meta: list[dict] = []

    # ---- Reprodução — mesmo benchmark da Capa (sem gate de módulo próprio,
    # mesma regra do router de indicadores). ----
    if tem_modulo(user, "reproducao") or tem_modulo(user, "indicadores"):
        ind = calcular_indicadores_fazenda(session, fazenda_id, hoje)
        for b in ind.get("benchmark_categorias", {}).get("todas", []):
            status = _status(b.get("valor"), b.get("meta"), b.get("maior_melhor", True))
            if status is None:
                continue
            itens.append(_item(
                chave=f"benchmark_{b['chave']}", dominio="reproducao", label=b["label"],
                sublabel="Benchmark reprodutivo", valor=b["valor"], meta=b["meta"],
                unidade=b.get("unidade") or "", maior_melhor=b.get("maior_melhor", True),
                status=status, rota="/", rota_label="Ver na Capa",
            ))

    # ---- Recria ----
    if tem_modulo(user, "recria"):
        idade = reproducao_idade_parto(session=session, fazenda_id=fazenda_id)
        est = idade.get("estatisticas")
        if est and (est.get("n") or 0) >= 3:
            media, meta_idade = est.get("media"), idade.get("meta_idade_parto")
            if media is not None and meta_idade is not None:
                delta = abs(media - meta_idade)
                status_idade = "ok" if delta <= 1 else "atencao" if delta <= 3 else "critico"
                itens.append(_item(
                    chave="recria_idade_1o_parto", dominio="recria", label="Idade média ao 1º parto",
                    sublabel="Método Wisconsin", valor=media, meta=meta_idade, unidade=" m",
                    maior_melhor=False, status=status_idade, rota="/recria", rota_label="Ver na Recria",
                ))
            dp, meta_dp = est.get("desvio_padrao"), idade.get("meta_desvio_padrao")
            status_dp = _status(dp, meta_dp, maior_melhor=False)
            if status_dp is not None:
                itens.append(_item(
                    chave="recria_desvio_padrao", dominio="recria", label="Desvio-padrão da idade ao parto",
                    sublabel="Método Wisconsin", valor=dp, meta=meta_dp, unidade=" m",
                    maior_melhor=False, status=status_dp, rota="/recria", rota_label="Ver na Recria",
                ))

        prenhez = reproducao_taxa_prenhez(
            ini=hoje - timedelta(days=365), fim=hoje, vwp_dias=0, session=session, fazenda_id=fazenda_id,
        )
        status_prenhez = _status(prenhez.get("taxa_prenhez_media"), prenhez.get("meta_taxa_prenhez"), maior_melhor=True)
        if status_prenhez is not None:
            itens.append(_item(
                chave="recria_taxa_prenhez", dominio="recria", label="Taxa de prenhez (ciclos de 21 dias)",
                sublabel="Últimos 12 meses", valor=prenhez["taxa_prenhez_media"],
                meta=prenhez.get("meta_taxa_prenhez"), unidade="%", maior_melhor=True,
                status=status_prenhez, rota="/recria", rota_label="Ver na Recria",
            ))

    # ---- Financeiro — RMCA (mês corrente) + custo/litro e custo/hectare,
    # que ainda não têm meta cadastrada em lugar nenhum (ver "sem_meta"). ----
    ini_mes = hoje.replace(day=1)
    if tem_modulo(user, "financeiro"):
        financeiro = calcular_rmca_view(data_inicio=ini_mes, data_fim=hoje, session=session, fazenda_id=fazenda_id)
        if financeiro.get("configurado"):
            meta_rmca_valor = financeiro.get("meta_rmca")
            for chave_rmca, label_rmca in (("gerencial", "RMCA gerencial"), ("fisico", "RMCA físico")):
                valor = (financeiro.get(chave_rmca) or {}).get("rmca")
                status_rmca = _status(valor, meta_rmca_valor, maior_melhor=True)
                if status_rmca is not None:
                    itens.append(_item(
                        chave=f"rmca_{chave_rmca}", dominio="financeiro", label=label_rmca,
                        sublabel="Mês corrente", valor=valor, meta=meta_rmca_valor, unidade="R$",
                        maior_melhor=True, status=status_rmca, rota="/financeiro", rota_label="Ver no Financeiro",
                    ))

        litro = custo_litro_leite(data_inicio=ini_mes, data_fim=hoje, session=session, fazenda_id=fazenda_id)
        if litro.get("custo_por_litro") is not None:
            sem_meta.append({
                "chave": "custo_litro_leite", "dominio": "financeiro", "label": "Custo por litro de leite",
                "sublabel": "Mês corrente", "valor": litro["custo_por_litro"], "unidade": "R$/L",
                "rota": "/financeiro", "rota_label": "Ver no Financeiro",
            })
        hectare = custo_por_hectare(data_inicio=ini_mes, data_fim=hoje, centro_custo=None, session=session)
        if hectare.get("custo_por_hectare") is not None:
            sem_meta.append({
                "chave": "custo_hectare", "dominio": "financeiro", "label": "Custo por hectare",
                "sublabel": "Mês corrente", "valor": hectare["custo_por_hectare"], "unidade": "R$/ha",
                "rota": "/financeiro", "rota_label": "Ver no Financeiro",
            })

    # ---- Manejo — contagem de "vermelho" nas listas semaforizadas (meta = 0
    # animais fora do prazo). Só as listas que representam atraso real —
    # PEV, prenhes e previsão de partos ficam de fora: seu "vermelho" é uma
    # marcação informativa de estágio, não um problema a corrigir. ----
    if tem_modulo(user, "reproducao"):
        animais, servicos, partos, secagens = _dados_manejo(session, fazenda_id)
        aplicacoes_iatf, peso_por_animal = _dados_estado_vivo(session, fazenda_id)
        # BUG DE SEGURANÇA CORRIGIDO: mesmo vazamento de relatorios.py — sem
        # filtro, trazia o estoque de sêmen de todas as fazendas.
        query_semen = select(EstoqueSemen)
        if fazenda_id is not None:
            query_semen = query_semen.where(EstoqueSemen.fazenda_id == fazenda_id)
        semen = [s.model_dump() for s in session.exec(query_semen).all()]
        manejo = rg.relatorios_manejo(animais, servicos, partos, semen, hoje, secagens=secagens,
                                       aplicacoes_iatf=aplicacoes_iatf, peso_por_animal=peso_por_animal)
        for chave_lista, label in (
            # "Atrasadas", não "Vacas atrasadas": a lista semaforizada conta
            # novilha em atraso para a 1ª cobertura junto com a vaca que
            # passou do DEL máximo (ver rules/relatorios_gerenciais.py).
            ("a_inseminar", "Atrasadas para inseminar"),
            ("inseminados", "Inseminadas sem diagnóstico há muito tempo"),
            ("a_tocar", "Toque atrasado"),
            ("a_reconfirmar", "Reconfirmação atrasada"),
            ("secagem", "Secagem atrasada"),
        ):
            n = sum(1 for x in manejo.get(chave_lista, []) if x.get("cor") == "vermelho")
            itens.append(_item(
                chave=f"manejo_{chave_lista}", dominio="manejo", label=label, sublabel="Lista semaforizada",
                valor=n, meta=0, unidade=" animais", maior_melhor=False,
                status=_status_contagem(n), rota="/relatorios", rota_label="Ver em Listas",
            ))
        n_semen = sum(1 for x in manejo.get("estoque_semen", []) if x.get("cor") == "vermelho")
        itens.append(_item(
            chave="manejo_estoque_semen", dominio="manejo", label="Lotes de sêmen com estoque crítico",
            sublabel="Lista semaforizada", valor=n_semen, meta=0, unidade=" lotes",
            maior_melhor=False, status=_status_contagem(n_semen), rota="/relatorios", rota_label="Ver em Listas",
        ))

    resumo = {
        "critico": sum(1 for i in itens if i["status"] == "critico"),
        "atencao": sum(1 for i in itens if i["status"] == "atencao"),
        "ok": sum(1 for i in itens if i["status"] == "ok"),
        "total": len(itens),
    }
    return {"itens": itens, "sem_meta": sem_meta, "resumo": resumo, "atualizado_em": hoje.isoformat()}
