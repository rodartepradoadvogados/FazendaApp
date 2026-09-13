"""
Geração do contrato CowData (fazenda/templates/contrato_cowdata.{html,md}) a
partir dos dados reais do plano contratado pela fazenda — usado tanto pelo
"Baixar contrato" (HTML) quanto pelo envio ao ZapSign (markdown_text, ver
fazenda/rules/zapsign.py). Os dois templates têm os mesmos placeholders
Jinja2 propositalmente, para nunca divergir o texto entre as duas saídas.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from fazenda.models.multitenant import EmpresaOperadora, Fazenda
from fazenda.models.planos import DESCONTO_CICLO_PAGAMENTO, MESES_POR_CICLO, PLANOS_CATALOGO

_DIR_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# BUG DE SEGURANÇA CORRIGIDO: `Template(texto)` sem Environment nunca escapa
# nada — nome/endereço de fazenda vindos do cadastro (e portanto de
# entrada do usuário) iam direto pro HTML do contrato. `select_autoescape`
# decide pela extensão do nome carregado via loader: escapa o ".html", mas
# não mexe no ".md" (mesmo padrão de contrato_equipe_render.py).
_AMBIENTE = Environment(
    loader=FileSystemLoader(str(_DIR_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)

MODULO_LABEL = {
    "rebanho": "Rebanho", "reprodutivo": "Reprodutivo", "produtivo": "Produtivo",
    "sanitario": "Sanitário", "financeiro": "Financeiro", "planejamento": "Planejamento",
    "pedidos": "Pedidos", "estoque": "Estoque", "alimentacao": "Alimentação",
    "agricultura": "Agricultura", "consultor": "Consultor externo",
}


def _contexto(
    fazenda: Fazenda, empresa: Optional[EmpresaOperadora],
    plano: Optional[str], modulos: list[str], preco_mensal: float, ciclo_pagamento: str,
    documento: str | None, endereco: str | None,
    representante_nome: str | None, representante_cpf: str | None,
    cidade_foro: str | None, estado_foro: str | None,
) -> dict:
    desconto_pct = DESCONTO_CICLO_PAGAMENTO.get(ciclo_pagamento, 0.0) * 100
    meses = MESES_POR_CICLO.get(ciclo_pagamento, 1)
    valor_total_ciclo = preco_mensal * meses * (1 - desconto_pct / 100)
    return {
        "empresa_nome": empresa.nome if empresa else "CowData",
        "empresa_cnpj": empresa.cnpj if empresa else None,
        "empresa_endereco": empresa.endereco if empresa else None,
        "fazenda_nome": fazenda.nome,
        "fazenda_documento": documento,
        "fazenda_endereco": endereco,
        "representante_nome": representante_nome,
        "representante_cpf": representante_cpf,
        "plano_nome": PLANOS_CATALOGO.get(plano or "", {}).get("nome", plano or "Sob medida"),
        "preco_mensal": f"{preco_mensal:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "modulos_lista": ", ".join(MODULO_LABEL.get(m, m) for m in modulos) or "—",
        "periodicidade": ciclo_pagamento,
        "desconto_pct": int(desconto_pct) if desconto_pct else None,
        "valor_total_ciclo": f"{valor_total_ciclo:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
        "cidade_foro": cidade_foro or fazenda.cidade,
        "estado_foro": estado_foro or fazenda.uf,
        "data_hoje": date.today().strftime("%d/%m/%Y"),
    }


def render_contrato(
    formato: str, fazenda: Fazenda, empresa: Optional[EmpresaOperadora],
    plano: Optional[str], modulos: list[str], preco_mensal: float, ciclo_pagamento: str = "mensal",
    documento: str | None = None, endereco: str | None = None,
    representante_nome: str | None = None, representante_cpf: str | None = None,
    cidade_foro: str | None = None, estado_foro: str | None = None,
) -> str:
    """`formato`: "html" (Baixar contrato) ou "md" (envio ao ZapSign)."""
    contexto = _contexto(
        fazenda, empresa, plano, modulos, preco_mensal, ciclo_pagamento,
        documento, endereco, representante_nome, representante_cpf, cidade_foro, estado_foro,
    )
    return _AMBIENTE.get_template(f"contrato_cowdata.{formato}").render(**contexto)
