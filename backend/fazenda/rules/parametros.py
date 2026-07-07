"""
Parâmetros da fazenda — metas e configurações zootécnicas de referência.

São os valores que orientam metas, alertas e faixas dos indicadores (verde/
vermelho). Por enquanto ficam centralizados aqui como padrões editáveis no
código; a UI os apresenta como um painel de referência. Baseados nos
parâmetros gerenciais usuais de rebanho leiteiro e ajustáveis à realidade da
Fazenda Estreito Ponte de Pedra.
"""
from __future__ import annotations

# Valores de referência (metas / configurações atuais).
PARAMETROS: dict = {
    "manejo": {
        "titulo": "Manejo reprodutivo",
        "itens": [
            {"chave": "periodo_seco_dias", "label": "Período seco", "valor": 60, "unidade": "dias"},
            {"chave": "pev_dias", "label": "Período de espera voluntária (PEV)", "valor": 45, "unidade": "dias"},
            {"chave": "dias_toque", "label": "Dias para toque (diagnóstico)", "valor": 30, "unidade": "dias"},
            {"chave": "dias_reconfirmacao", "label": "Dias para reconfirmação", "valor": 30, "unidade": "dias"},
            {"chave": "intervalo_visita_reprodutiva", "label": "Intervalo da visita reprodutiva", "valor": 21, "unidade": "dias"},
            {"chave": "intervalo_bst", "label": "Intervalo de aplicação de BST", "valor": 12, "unidade": "dias"},
            {"chave": "intervalo_visita_vet", "label": "Intervalo de visitas do veterinário", "valor": 30, "unidade": "dias"},
            {"chave": "dias_reinseminacao", "label": "Meta de dias para re-inseminação", "valor": 15, "unidade": "dias"},
            {"chave": "idade_maturidade_novilha", "label": "Idade de maturidade da novilha", "valor": 16, "unidade": "meses"},
        ],
    },
    "metas_reproducao": {
        "titulo": "Metas reprodutivas",
        "itens": [
            {"chave": "meta_del_max_1o_servico", "label": "DEL máximo para 1º serviço", "valor": 100, "unidade": "dias"},
            {"chave": "meta_del_medio_1o_servico", "label": "DEL médio ao 1º serviço", "valor": 70, "unidade": "dias"},
            {"chave": "meta_del_medio", "label": "DEL médio do rebanho", "valor": 200, "unidade": "dias"},
            {"chave": "meta_taxa_servico", "label": "Taxa de serviço em vacas", "valor": 50, "unidade": "%"},
            {"chave": "meta_taxa_concepcao", "label": "Taxa de concepção em vacas", "valor": 35, "unidade": "%"},
            {"chave": "meta_taxa_prenhez", "label": "Taxa de prenhez em vacas", "valor": 18, "unidade": "%"},
            {"chave": "meta_concepcao_novilha", "label": "Taxa de concepção da novilha", "valor": 60, "unidade": "%"},
            {"chave": "meta_iep_meses", "label": "Intervalo entre partos (IEP)", "valor": 14, "unidade": "meses"},
            {"chave": "meta_taxa_perda_prenhez", "label": "Taxa de perda de prenhez", "valor": 15, "unidade": "%"},
        ],
    },
    "producao_descarte": {
        "titulo": "Produção e descarte",
        "itens": [
            {"chave": "taxa_reposicao", "label": "Taxa de reposição", "valor": 25, "unidade": "%"},
            {"chave": "producao_minima_secagem", "label": "Produção mínima de leite para secagem", "valor": 15, "unidade": "kg/dia"},
            {"chave": "meses_queda_reprodutiva", "label": "Meses de queda reprodutiva (ex.: estresse calórico)", "valor": 4, "unidade": "meses"},
            {"chave": "concepcao_meses_queda", "label": "Taxa de concepção nos meses de queda", "valor": 25, "unidade": "%"},
        ],
    },
}

# Metas do benchmark (nosso valor será comparado a estes) — usadas na capa.
# meta = alvo da fazenda; media_pais = referência de mercado.
BENCHMARK_METAS: dict[str, dict] = {
    "taxa_servico":        {"meta": 50.0, "media_pais": 55.0, "maior_melhor": True},
    "taxa_concepcao":      {"meta": 35.0, "media_pais": 40.0, "maior_melhor": True},
    "taxa_prenhez_ciclo":  {"meta": 18.0, "media_pais": 21.0, "maior_melhor": True},
    "del_medio":           {"meta": 200.0, "media_pais": 209.0, "maior_melhor": False},
    "taxa_perda_prenhez":  {"meta": 15.0, "media_pais": 11.0, "maior_melhor": False},
    "perc_vacas_prenhas":  {"meta": 50.0, "media_pais": 46.0, "maior_melhor": True},
    "servicos_por_prenhez": {"meta": 2.9, "media_pais": 2.5, "maior_melhor": False},
    "del_1a_ia":           {"meta": 70.0, "media_pais": 78.0, "maior_melhor": False},
    "dias_abertos":        {"meta": 145.6, "media_pais": 164.0, "maior_melhor": False},
    "iep_meses":           {"meta": 14.0, "media_pais": 14.0, "maior_melhor": False},
}
