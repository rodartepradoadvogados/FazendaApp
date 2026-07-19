"""
Auditoria de atividade — consulta unificada dos lançamentos feitos por um
usuário, em qualquer módulo do sistema. Restrito ao proprietário (mesma
regra do relatório de últimos acessos, ver fazenda.auth.exigir_dono).
Endpoints: GET /auditoria/opcoes · GET /auditoria/atividades
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from fazenda.auth import exigir_dono
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, AnaliseBromatologica, AplicacaoAgendada, BaixaAnimal, ColostragemBezerra,
    CompraAnimal, CompraSemen, ContaGerencial, Contrato, ControleLeiteiro, Diaria,
    DietaLancamento, DietaRegistroReal, Empreitada, EntregaLeiteMensal, FolhaPagamento,
    LancamentoAnexo, MovimentoEstoque, MovimentoLote, OcorrenciaClinica, OrcamentoItem,
    Parto, Pedido, PesagemCorporal, PlanejamentoCenario, ProtocoloIatfLancamento,
    ProtocoloInducaoLancamento, ProtocoloSanitarioLancamento, QualidadeLeite, RegistroCocho,
    Sanidade, Servico, Usuario, ValeAvulso, ValeFuncionario, VendaAnimal,
)

router = APIRouter(prefix="/auditoria", tags=["auditoria"])

# Cada entrada descreve um tipo de lançamento consultável: o model, o campo de
# data usado para filtrar/ordenar, e os campos usados para montar um resumo
# legível (o primeiro que existir e não for vazio entra no resumo — mesmo
# espírito do catálogo de exportação do Portal: uma definição genérica em vez
# de um serializer bespoke por modelo).
CATALOGO: dict[str, dict] = {
    "movimento_lote":                {"label": "Movimentação de lote",        "model": MovimentoLote,               "campo_data": "data_movimento",   "campos_resumo": ["numero_matriz", "lote_destino"]},
    "servico":                       {"label": "Serviço/IA",                  "model": Servico,                     "campo_data": "data_servico",      "campos_resumo": ["numero_matriz", "tipo_servico"]},
    "protocolo_iatf_lancamento":     {"label": "Protocolo IATF",              "model": ProtocoloIatfLancamento,     "campo_data": "data_d0",           "campos_resumo": ["nome_protocolo"]},
    "parto":                        {"label": "Parto/nascimento",            "model": Parto,                       "campo_data": "data_parto",        "campos_resumo": ["numero_matriz", "tipo_parto"]},
    "colostragem_bezerra":           {"label": "Colostragem",                 "model": ColostragemBezerra,          "campo_data": "data_colostro",     "campos_resumo": ["numero_animal"]},
    "controle_leiteiro":             {"label": "Controle leiteiro",           "model": ControleLeiteiro,            "campo_data": "data_controle",     "campos_resumo": ["numero_matriz", "producao_kg"]},
    "pesagem_corporal":              {"label": "Pesagem corporal",            "model": PesagemCorporal,             "campo_data": "data_pesagem",      "campos_resumo": ["numero_matriz", "peso_kg"]},
    "qualidade_leite":               {"label": "Qualidade do leite",          "model": QualidadeLeite,              "campo_data": "data_coleta",       "campos_resumo": ["numero_matriz"]},
    "entrega_leite_mensal":          {"label": "Venda mensal do leite",       "model": EntregaLeiteMensal,          "campo_data": "criado_em",         "campos_resumo": ["competencia", "quantidade_litros"]},
    "conta_gerencial":               {"label": "Financeiro",                  "model": ContaGerencial,              "campo_data": "data_emissao",      "campos_resumo": ["descricao", "fornecedor_cliente"]},
    "lancamento_anexo":              {"label": "Anexo de lançamento",         "model": LancamentoAnexo,             "campo_data": "criado_em",         "campos_resumo": ["nome_arquivo"]},
    "orcamento_item":                {"label": "Orçamento",                  "model": OrcamentoItem,               "campo_data": "atualizado_em",     "campos_resumo": ["codigo_conta_gerencial", "tipo"]},
    "planejamento_cenario":          {"label": "Planejamento financeiro",     "model": PlanejamentoCenario,         "campo_data": "criado_em",         "campos_resumo": ["nome"]},
    "pedido":                        {"label": "Pedido",                      "model": Pedido,                      "campo_data": "data_pedido",       "campos_resumo": ["numero_pedido", "fornecedor_cliente"]},
    "folha_pagamento":               {"label": "Folha de pagamento",          "model": FolhaPagamento,              "campo_data": "data_pagamento",    "campos_resumo": ["competencia", "valor_liquido"]},
    "vale_funcionario":              {"label": "Vale de funcionário",         "model": ValeFuncionario,             "campo_data": "data_pagamento",    "campos_resumo": ["valor_total"]},
    "vale_avulso":                   {"label": "Vale (empreita/contrato/diária)", "model": ValeAvulso,              "campo_data": "data_pagamento",    "campos_resumo": ["origem_tipo", "valor"]},
    "empreitada":                    {"label": "Empreitada",                  "model": Empreitada,                  "campo_data": "criado_em",         "campos_resumo": ["descricao"]},
    "contrato":                      {"label": "Contrato",                    "model": Contrato,                    "campo_data": "criado_em",         "campos_resumo": ["descricao"]},
    "diaria":                        {"label": "Diária",                     "model": Diaria,                      "campo_data": "data_inicio",       "campos_resumo": ["valor_diaria"]},
    "movimento_estoque":             {"label": "Estoque",                    "model": MovimentoEstoque,            "campo_data": "data_movimento",    "campos_resumo": ["nome_item", "movimento"]},
    "sanidade":                      {"label": "Sanidade",                    "model": Sanidade,                    "campo_data": "data_aplicacao",    "campos_resumo": ["numero_matriz", "produto"]},
    "aplicacao_agendada":            {"label": "Aplicação agendada",          "model": AplicacaoAgendada,           "campo_data": "data",              "campos_resumo": ["numero_matriz", "produto"]},
    "protocolo_sanitario_lancamento": {"label": "Protocolo sanitário",        "model": ProtocoloSanitarioLancamento, "campo_data": "data_inicio",       "campos_resumo": ["numero_matriz"]},
    "protocolo_inducao_lancamento":  {"label": "Indução de lactação",         "model": ProtocoloInducaoLancamento,  "campo_data": "data_d0",           "campos_resumo": ["nome_protocolo"]},
    "dieta_lancamento":              {"label": "Dieta (lote)",                "model": DietaLancamento,             "campo_data": "data_abertura",     "campos_resumo": ["lote"]},
    "analise_bromatologica":         {"label": "Análise bromatológica",       "model": AnaliseBromatologica,        "campo_data": "data",              "campos_resumo": ["alimento"]},
    "dieta_registro_real":           {"label": "Registro real de dieta",      "model": DietaRegistroReal,           "campo_data": "data",              "campos_resumo": ["alimento", "quantidade"]},
    "agenda_manual":                 {"label": "Evento manual da Agenda",     "model": AgendaManual,                "campo_data": "data_evento",       "campos_resumo": ["descricao"]},
    "baixa_animal":                  {"label": "Baixa de animal",             "model": BaixaAnimal,                 "campo_data": "data_baixa",        "campos_resumo": ["numero_animal", "tipo_baixa"]},
    "compra_animal":                 {"label": "Compra de animal",            "model": CompraAnimal,                "campo_data": "data_compra",       "campos_resumo": ["numero_animal", "vendedor"]},
    "venda_animal":                  {"label": "Venda de animal",             "model": VendaAnimal,                 "campo_data": "data_venda",        "campos_resumo": ["numero_animal", "comprador"]},
    "compra_semen":                  {"label": "Compra de sêmen",             "model": CompraSemen,                 "campo_data": "data_compra",       "campos_resumo": ["touro_nome", "doses"]},
    "ocorrencia_clinica":            {"label": "Ocorrência clínica",          "model": OcorrenciaClinica,           "campo_data": "data_ocorrencia",   "campos_resumo": ["numero_matriz", "doenca"]},
    "registro_cocho":                {"label": "Registro de cocho",           "model": RegistroCocho,               "campo_data": "data",              "campos_resumo": ["lote"]},
}


def _resumo(obj, campos: list[str]) -> str:
    partes = []
    for campo in campos:
        valor = getattr(obj, campo, None)
        if valor not in (None, ""):
            partes.append(str(valor))
    return " — ".join(partes) if partes else f"#{obj.id}"


@router.get("/opcoes")
def opcoes_auditoria(_: Usuario = Depends(exigir_dono), session: Session = Depends(get_session)) -> dict:
    usuarios = session.exec(select(Usuario)).all()
    return {
        "tipos": [{"chave": chave, "label": cfg["label"]} for chave, cfg in CATALOGO.items()],
        "usuarios": [
            {"id": u.id, "username": u.username, "nome": u.nome, "ativo": u.ativo}
            for u in sorted(usuarios, key=lambda u: (u.nome or u.username).lower())
        ],
    }


@router.get("/atividades")
def listar_atividades(
    usuario_id: int,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    chaves: Optional[str] = None,
    limit: int = 2000,
    _: Usuario = Depends(exigir_dono),
    session: Session = Depends(get_session),
) -> dict:
    """Lista os lançamentos de um usuário em todos os tipos do catálogo (ou só
    nos `chaves` informados, CSV), opcionalmente filtrados por período.

    `limit` corta a resposta (como antes, quando era fixo em 500) — o
    `total` abaixo sempre reflete a contagem real, sem o corte. Subimos o
    padrão de 500 para 2000: o volume típico de atividades por usuário/período
    não é gigantesco, e paginar de verdade contra o servidor seria
    over-engineering para este caso — a tela pagina client-side em cima do
    que já chegou (ver usePaginacao em AuditoriaAcessoView.tsx)."""
    alvo = session.get(Usuario, usuario_id)
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    selecionadas = [c for c in (chaves.split(",") if chaves else list(CATALOGO.keys())) if c in CATALOGO]

    itens: list[dict] = []
    for chave in selecionadas:
        cfg = CATALOGO[chave]
        modelo = cfg["model"]
        campo_data = getattr(modelo, cfg["campo_data"])
        consulta = select(modelo).where(modelo.usuario_id == usuario_id)
        if data_inicio:
            consulta = consulta.where(campo_data >= data_inicio)
        if data_fim:
            consulta = consulta.where(campo_data <= data_fim)
        for obj in session.exec(consulta).all():
            valor_data = getattr(obj, cfg["campo_data"])
            itens.append({
                "chave": chave,
                "label": cfg["label"],
                "id": obj.id,
                "data": valor_data.isoformat() if valor_data else None,
                "resumo": _resumo(obj, cfg["campos_resumo"]),
            })

    itens.sort(key=lambda i: i["data"] or "", reverse=True)
    return {
        "usuario": {"id": alvo.id, "username": alvo.username, "nome": alvo.nome},
        "total": len(itens),
        "itens": itens[:limit],
    }
