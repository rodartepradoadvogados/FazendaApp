"""
Router de Importar dados (Configurações > Importar dados) — CSV manual e
simplificado para as categorias que não têm um parser rico do Ideagri.

Efetividade: cada linha é processada chamando a MESMA função que já grava de
verdade quando o usuário lança manualmente pela tela (criar_pesagens,
criar_lancamento, movimentar_estoque) ou grava direto nas mesmas tabelas
reais (Estoque, Fornecedor) usadas em todo o site — nunca numa tabela à
parte. As categorias que já têm parser rico do Ideagri (animais,
reprodutivo, produção, sanidade) continuam em POST /upload/{tipo}; aqui só
listamos seus modelos para aparecerem lado a lado na mesma tela.
"""
from __future__ import annotations

import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.api.routers.agenda import _baixar_aplicacao_agendada
from fazenda.api.routers.cadastro.animais import _completar_genealogia_paterna
from fazenda.api.routers.estoque import MovimentoIn, _criar_movimento_estoque
from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
from fazenda.api.routers.producao import (
    ControlesIn, OrdenhaIn, PesagensIn, PesoIn, QualidadeLeiteIn, _gravar_controles, criar_controles,
    criar_pesagens, criar_qualidade_leite,
)
from fazenda.api.routers.sanidade import AplicacaoIn, ItemAplicacaoIn, registrar_aplicacao
from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal, AplicacaoAgendada, CalendarioSanitario, ContaGerencial, CurvaABC, Dieta, Doenca, Estoque,
    EventoRealizado, EventoSanitario, Fornecedor, LancamentoItem, Parto, Sanidade, Usuario,
)
from fazenda.parsers.utils import iter_csv_rows, parse_date, parse_float, parse_int
from fazenda.rules.auditoria import fazenda_id_seguro, usuario_id_seguro
from fazenda.rules.calendario_sanitario import proxima_ocorrencia
from fazenda.rules.eventos_sanitarios import _datas_gatilho

router = APIRouter(prefix="/importar", tags=["importar"])

CATEGORIAS_NOVAS = {
    "pesagem": {
        "label": "Histórico de pesagem corporal",
        "colunas": ["numero_matriz", "data_pesagem (DD/MM/AAAA)", "peso_kg"],
        "colunas_csv": ["numero_matriz", "data_pesagem", "peso_kg"],
        "exemplo": ["464", "08/07/2026", "350"],
    },
    "controle_leiteiro_simples": {
        "label": "Controle leiteiro simplificado (1ª e 2ª ordenha) — diário/semanal/mensal",
        "colunas": ["numero_matriz", "ordenha1_kg", "ordenha2_kg", "data_controle (opcional, DD/MM/AAAA)"],
        "colunas_csv": ["numero_matriz", "ordenha1_kg", "ordenha2_kg", "data_controle"],
        "exemplo": ["464", "14,5", "13,0", "05/07/2026"],
        # Data única no upload (o site sabe o DEL pela ficha e soma o total).
        # Flexível: se cada linha trouxer a coluna data_controle, o arquivo pode
        # conter vários dias/semanas/meses de uma vez.
        "precisa_data_controle": True,
    },
    "financeiro": {
        "label": "Financeiro simplificado (uma parcela à vista por linha)",
        "colunas": ["data (DD/MM/AAAA)", "tipo (receita/despesa)", "descricao", "valor", "fornecedor_cliente"],
        "colunas_csv": ["data", "tipo", "descricao", "valor", "fornecedor_cliente"],
        "exemplo": ["08/07/2026", "despesa", "Ração concentrada", "1500,00", "Agropecuária Central"],
    },
    "estoque_movimento": {
        "label": "Movimentação de estoque simplificada",
        "colunas": [
            "nome_item", "movimento (Aplicação/Saída de ajuste/Entrada de ajuste/Entrada de cortesia/Doação)",
            "quantidade", "unidade", "data_movimento (DD/MM/AAAA)", "observacao",
        ],
        "colunas_csv": ["nome_item", "movimento", "quantidade", "unidade", "data_movimento", "observacao"],
        "exemplo": ["Ração concentrada", "Saída de ajuste", "50", "kg", "08/07/2026", "Consumo do dia"],
    },
    "produtos_estoque": {
        "label": "Cadastro de sêmen/medicamento/hormônio/alimento",
        "colunas": ["nome", "categoria", "unidade", "ensacado (Sim/Não)", "kg_por_saco", "fornecedor_nome"],
        "colunas_csv": ["nome", "categoria", "unidade", "ensacado", "kg_por_saco", "fornecedor_nome"],
        "exemplo": ["Sal mineral", "alimento", "kg", "Sim", "25", ""],
    },
    "fornecedores": {
        "label": "Fornecedores, fabricantes e clientes",
        "colunas": ["nome", "tipo (fornecedor/fabricante/cliente)", "categoria", "cnpj_cpf", "telefone", "email"],
        "colunas_csv": ["nome", "tipo", "categoria", "cnpj_cpf", "telefone", "email"],
        "exemplo": ["Agropecuária Central", "fornecedor", "Ração e insumos alimentares", "12.345.678/0001-00", "(67) 3222-1000", "contato@agropecuaria.com.br"],
    },
    "animais_cadastro": {
        "label": "Cadastro de animais em lote (ficha simplificada)",
        "colunas": [
            "numero", "nome", "sexo (F/M)", "raca", "data_nasc (DD/MM/AAAA)", "lote", "data_entrada (DD/MM/AAAA)",
            "pai_nome (opcional)", "pai_naab (opcional)", "mae_numero (opcional)", "mae_nome (opcional)",
        ],
        "colunas_csv": ["numero", "nome", "sexo", "raca", "data_nasc", "lote", "data_entrada", "pai_nome", "pai_naab", "mae_numero", "mae_nome"],
        "exemplo": ["465", "Mimosa", "F", "Girolando", "10/03/2024", "01 - BEZ 1 (0 A 30)", "10/03/2024", "Touro Estrela", "7HO16011", "", ""],
    },
    "animais_genealogia": {
        "label": "Genealogia complementar (pai/mãe) de animais já cadastrados",
        "colunas": ["numero", "pai_nome (opcional)", "pai_naab (opcional)", "mae_numero (opcional)", "mae_nome (opcional)"],
        "colunas_csv": ["numero", "pai_nome", "pai_naab", "mae_numero", "mae_nome"],
        "exemplo": ["465", "Touro Estrela", "7HO16011", "", "Mimosa"],
    },
    "qualidade_leite": {
        "label": "Qualidade do leite — Clínica do Leite / LQL (tanque ou por vaca)",
        "colunas": [
            "numero_matriz (vazio = tanque)", "data_coleta (DD/MM/AAAA)", "ccs", "cbt", "gordura_pct", "proteina_pct",
            "solidos_totais_pct", "esd_pct", "lactose_pct", "nul (ureia)",
        ],
        "colunas_csv": [
            "numero_matriz", "data_coleta", "ccs", "cbt", "gordura_pct", "proteina_pct", "solidos_totais_pct",
            "esd_pct", "lactose_pct", "nul",
        ],
        "exemplo": ["", "05/07/2026", "181", "11", "3,69", "3,42", "12,69", "9,00", "4,69", "14,0"],
    },
    "dairycomp": {
        "label": "DairyComp 305 — nascimentos e partos (idade ao 1º parto)",
        "colunas": [
            "numero_matriz (ID)", "data_nascimento/BDAT (DD/MM/AAAA)", "data_parto/FDAT (DD/MM/AAAA, vazio = novilha)",
            "ordem_parto/LACT",
        ],
        "colunas_csv": ["numero_matriz", "data_nascimento", "data_parto", "ordem_parto"],
        "exemplo": ["464", "10/03/2022", "05/06/2024", "1"],
    },
    "calendario_sanitario": {
        "label": "Calendário sanitário (preventivo) da fazenda",
        "colunas": [
            "evento (nome, ex.: Vacina pré-parto)", "categoria (vacina/exame/tratamento)", "categoria_alvo (lote/categoria)",
            "doenca (nome, opcional)", "produto (opcional)", "dosagem (opcional)",
            "frequencia_valor", "frequencia_unidade (dias/meses/anos)", "data_evento (DD/MM/AAAA)",
        ],
        "colunas_csv": [
            "evento", "categoria", "categoria_alvo", "doenca", "produto", "dosagem",
            "frequencia_valor", "frequencia_unidade", "data_evento",
        ],
        "exemplo": ["Brucelose B19", "vacina", "Bezerras (3 a 8 meses)", "Brucelose", "Vacina B19", "2 mL",
                    "1", "anos", "10/03/2026"],
    },
    "baixas_pendencias_agenda": {
        "label": "Baixa em massa de pendências antigas da Agenda (sanitário)",
        "colunas": [
            "tipo (evento_sanitario/calendario_sanitario/aplicacao_agendada)", "nome_evento (só p/ evento_sanitario e calendario_sanitario)",
            "numero_animal", "data_pendencia (DD/MM/AAAA, a data original da pendência)",
            "produto_aplicado (opcional — vazio usa o produto padrão do evento)", "dose (opcional)",
            "unidade (opcional)", "via (opcional)", "responsavel (opcional)", "observacao (opcional)",
        ],
        "colunas_csv": [
            "tipo", "nome_evento", "numero_animal", "data_pendencia", "produto_aplicado", "dose", "unidade", "via",
            "responsavel", "observacao",
        ],
        "exemplo": ["evento_sanitario", "Brucelose B19", "464", "10/04/2026", "Vacina B19", "2", "ml", "Subcutânea", "Carlos", ""],
        "precisa_data_corte": True,
    },
    "touros_naab": {
        "label": "Touros — catálogo NAAB/provas do fornecedor (Excel ou CSV)",
        "colunas": [
            "NAAB (código)", "Nome", "Raça", "Central", "Leite", "Gordura kg", "Gordura %", "Proteína kg",
            "Proteína %", "TPI", "NM$", "Tipo (PTAT)", "Úbere (UDC)", "Pernas (FLC)", "CCS (SCS)",
            "Fertilidade (DPR)", "Facilidade de parto",
        ],
        "colunas_csv": [
            "naab", "nome", "raca", "central", "leite", "gordura_kg", "gordura", "proteina_kg", "proteina",
            "tpi", "nm", "tipo", "ubere", "pernas", "ccs", "dpr", "facilidade de parto",
        ],
        "exemplo": ["7HO16011", "FRAZZLED", "Holandês", "Select Sires", "800", "45", "0.03", "35", "0.02",
                    "2850", "780", "2.10", "1.80", "1.20", "2.85", "1.5", "6.2"],
        "aceita_excel": True,
    },
}

# Categorias que já têm parser rico do Ideagri — seguem usando POST /upload/{tipo}.
# colunas_csv/exemplo usam os nomes EXATOS de coluna que cada parser real lê
# (fazenda/parsers/*.py), para o modelo baixado já vir pronto para reenviar.
CATEGORIAS_EXISTENTES = {
    "animais": {
        "label": "Animais / rebanho geral", "tipo_upload": "geral",
        "colunas_csv": [
            "Nº animal", "Dt. nasc.", "Idade em meses", "Grupos atuais", "Categoria completa",
            "Categoria abreviada", "Sit. rep.", "DEL", "Dt. últ. leite", "Últ. CL (kg)", "Dt. últ. diag.", "Diag.",
        ],
        "exemplo": ["464", "15/03/2022", "52", "01 - Alta", "Vaca em lactação", "Vaca", "Ins.", "120", "07/07/2026", "28,5", "20/05/2026", "POSITIVO"],
    },
    "reprodutivo": {
        "label": "Reprodutivo (serviços e partos)", "tipo_upload": "reprodutivo",
        "colunas_csv": [
            "NÚMERO DA MATRIZ", "RAÇA DA MATRIZ", "DATA DE NASCIMENTO", "DATA DO ÚLTIMO PARTO", "ORDEM DE PARTO",
            "DATA DO SERVIÇO", "TIPO DO SERVIÇO", "PROTOCOLO", "REPRODUTOR", "ORDEM DE TENTATIVA",
            "INTERVALO ENTRE TENTATIVAS", "DATA DO DIAGNOSTICO", "DIAGNÓSTICO", "DATA DA PERDA DE PRENHEZ", "PEV",
            "CATEGORIA", "PRODUÇÃO LACTAÇÃO ANTERIOR", "DURAÇÃO DA LACTAÇÃO ANTERIOR (D", "PERIODO SECO ANTERIOR (DIAS)",
            "PARTO_REAL", "TIPO_PARTO_REAL", "SEXO CRIA 1 - ÚLTIMO PARTO REAL", "SEXO CRIA 2 - ÚLTIMO PARTO REAL",
            "RETENÇÃO DE PLACENTA", "GEMELAR ÚLTIMO PARTO",
        ],
        "exemplo": [
            "464", "Girolando", "15/03/2020", "01/05/2026", "3", "03/07/2026", "IATF", "Protocolo padrão", "COORS",
            "1", "", "", "", "", "283", "Vaca", "32", "305", "60", "", "", "", "", "", "",
        ],
    },
    "producao_leiteira": {
        "label": "Produção / controle leiteiro", "tipo_upload": "controle_leiteiro",
        "colunas_csv": ["NUMERO", "NOME_RESUMIDO", "RGD", "RACA", "DATA_LEITE", "PESO_TOTAL_LEITE", "DATA_ULTIMO_PARTO", "DATA_BAIXA"],
        "exemplo": ["464", "Estrela", "", "Girolando", "08/07/2026", "28,5", "01/05/2026", ""],
    },
    "sanitario": {
        "label": "Sanitário", "tipo_upload": "sanidade",
        "colunas_csv": ["Nº animal", "Nome", "Dt. nasc.", "Sx", "Raça", "Dt. aplic.", "Produto aplic.", "Dose", "Lote", "Atividade", "Obs. aplic."],
        "exemplo": ["464", "Estrela", "15/03/2020", "F", "Girolando", "08/07/2026", "Ivermectina", "10", "L123", "Vacas em lactação", ""],
    },
    "estoque": {
        "label": "Estoque (inventário completo)", "tipo_upload": "estoque",
        "colunas_csv": ["Categoria", "Número", "Nome", "Quantidade", "Estoque mínimo", "Unidade", "Valor médio unitário", "Valor total", "LOCALARMAZENAMENTO"],
        "exemplo": ["Alimento", "1001", "Ração concentrada", "5000", "500", "kg", "2,50", "12500", ""],
    },
    "dieta": {
        "label": "Dieta (plano alimentar por lote)", "tipo_upload": "dieta",
        "colunas_csv": ["Lote", "Categoria", "Qtde Silagem (kg)", "Qtde Concentrado (kg)", "Qtde Sal Mineral (kg)"],
        "exemplo": ["01", "Vaca em lactação", "25", "6", "0,15"],
    },
    "curva_abc": {
        "label": "Curva ABC (Pareto de compras)", "tipo_upload": "curva_abc",
        "colunas_csv": [
            "Item", "Classificação", "Produto/Serviço", "UN", "Preço unitário", "Qtde", "Vlr. da compra",
            "Valor da compra acumulado", "% sobre valor total acumulado", "% sobre valor total",
        ],
        "exemplo": ["1", "A", "Ração concentrada", "kg", "2,50", "5000", "12500,00", "12500,00", "45,2", "45,2"],
    },
    "conta_gerencial": {
        "label": "Financeiro completo (conta gerencial)", "tipo_upload": "conta_gerencial",
        "colunas_csv": [
            "Conta gerencial", "Descrição", "Data venc.", "Data pag. / receb.", "Data comp.", "Fornecedor / cliente",
            "Nº da nota", "Parcela", "Valor total da parcela", "Valor parcela aprop. ct. gerencial",
            "Valor aprop. centros de custos", "Valor pago receb.", "TIPO", "Centro de custo", "DATAEMISSAO",
        ],
        "exemplo": [
            "3.01.01.01", "Ração concentrada", "10/07/2026", "08/07/2026", "30/06/2026", "Agropecuária Central",
            "1234", "1/1", "1500,00", "1500,00", "1500,00", "1500,00", "2", "PL", "05/07/2026",
        ],
    },
    "plano_conta_gerencial": {
        "label": "Plano de contas gerenciais", "tipo_upload": "plano_conta_gerencial",
        "colunas_csv": ["Nº ct. ger.", "Nome ct. ger.", "Ativa", "Part. ativ.", "Fluxo", "Tipo F/V"],
        "exemplo": ["3.01.01.01", "Concentrado protéico", "Sim", "Sim", "Sim", "Variável"],
    },
    "patrimonio": {
        "label": "Patrimônio (bens/imobilizado)", "tipo_upload": "patrimonio",
        "colunas_csv": [
            "Tipo patr.", "Nome Patr.", "Nº patr.", "Ativ. cul.", "Placa", "Dt. imob.", "Mét. depr.",
            "Vd. útil", "Vlr. res.", "Quant.", "Uni.", "Vlr. tot.", "Dt. baixa pat.",
        ],
        "exemplo": ["Veículo", "Caminhonete Hilux", "V001", "Pecuária", "ABC-1234", "10/01/2020", "Linear", "5 anos", "20000", "1", "un", "150000", ""],
    },
}


@router.get("/modelos")
def listar_modelos() -> dict:
    return {"novas": CATEGORIAS_NOVAS, "existentes": CATEGORIAS_EXISTENTES}


@router.post("/pesagem")
async def importar_pesagem(
    file: UploadFile, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    por_data: dict[date, list[PesoIn]] = {}
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        numero = row.get("numero_matriz", "").strip()
        data = parse_date(row.get("data_pesagem", ""))
        peso = parse_float(row.get("peso_kg", ""))
        if not numero or not data or not peso:
            erros.append(f"Linha {i}: número, data e peso são obrigatórios")
            continue
        por_data.setdefault(data, []).append(PesoIn(numero_matriz=numero, peso_kg=peso))

    criados = 0
    for data, entradas in por_data.items():
        # `user`/`fazenda_id` SEMPRE por keyword — chamada direta (fora do
        # ciclo HTTP) igual ao bug original do telegram_fluxos.py: sem isso,
        # `criar_pesagens` recebe os `Depends(...)` não resolvidos como
        # `user`/`fazenda_id` e `_usuario_id_seguro`/`fazenda_id_seguro`
        # caem pra None — toda pesagem importada nascia órfã e sem autor.
        resultado = criar_pesagens(PesagensIn(data_pesagem=data, entradas=entradas), session=session, user=user, fazenda_id=fazenda_id)
        criados += resultado["criados"]
    return {"categoria": "pesagem", "criados": criados, "erros": erros}


@router.post("/controle_leiteiro_simples")
async def importar_controle_leiteiro_simples(
    file: UploadFile,
    data_controle: date = Form(...),
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    CSV enxuto (só nº da matriz + 1ª/2ª ordenha) para quando não se quer
    preencher a planilha rica do Ideagri — DEL e total vêm do próprio site
    (mesma lógica de criar_controles), a data é uma só para o lote inteiro.
    """
    content = await file.read()
    erros: list[str] = []
    # Agrupa por data: cada linha pode trazer sua própria coluna `data_controle`
    # (permite subir um único arquivo com vários dias/semanas/meses); quando a
    # coluna não vem, usa a data única informada no upload.
    por_data: dict[date, list[OrdenhaIn]] = {}

    for i, row in enumerate(iter_csv_rows(content), start=2):
        numero = row.get("numero_matriz", "").strip()
        ord1 = parse_float(row.get("ordenha1_kg", ""))
        ord2 = parse_float(row.get("ordenha2_kg", ""))
        if not numero or (ord1 is None and ord2 is None):
            erros.append(f"Linha {i}: número da matriz e ao menos uma ordenha são obrigatórios")
            continue
        data_linha = parse_date(row.get("data_controle", "")) or data_controle
        por_data.setdefault(data_linha, []).append(OrdenhaIn(numero_matriz=numero, ordenhas=[ord1 or 0, ord2 or 0]))

    criados = 0
    for dia, entradas in por_data.items():
        # Importação em massa usa o caminho NÃO estrito: a vaca sem lactação
        # aberta é pulada e reportada em `erros`, em vez de derrubar o arquivo
        # inteiro (ver producao._gravar_controles).
        resultado = _gravar_controles(session, ControlesIn(data_controle=dia, entradas=entradas),
                                      user.id if isinstance(user, Usuario) else None, fazenda_id, estrito=False)
        criados += resultado["criados"]
        erros.extend(i["motivo"] for i in resultado["ignorados"])
    return {"categoria": "controle_leiteiro_simples", "criados": criados, "erros": erros}


@router.post("/financeiro")
async def importar_financeiro(
    file: UploadFile, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    criados = 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        tipo = row.get("tipo", "").strip().lower()
        data = parse_date(row.get("data", ""))
        valor = parse_float(row.get("valor", ""))
        descricao = row.get("descricao", "").strip()
        if tipo not in ("receita", "despesa") or not data or not valor or not descricao:
            erros.append(f"Linha {i}: data, tipo (receita/despesa), descrição e valor são obrigatórios")
            continue
        try:
            dados = LancamentoIn(
                tipo=tipo,
                itens=[ItemIn(produto=descricao, valor_total=valor)],
                centro_custo=row.get("centro_custo", "").strip() or "Pecuária Leiteira",
                fornecedor_cliente=row.get("fornecedor_cliente", "").strip() or None,
                data_emissao=data,
                data_competencia=data,
                parcelas=[ParcelaIn(data_vencimento=data, valor=valor)],
            )
            criar_lancamento(dados, session=session, user=user, fazenda_id=fazenda_id)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "financeiro", "criados": criados, "erros": erros}


@router.post("/estoque_movimento")
async def importar_estoque_movimento(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    criados = 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome_item", "").strip()
        movimento = row.get("movimento", "").strip()
        quantidade = parse_float(row.get("quantidade", ""))
        data_movimento = parse_date(row.get("data_movimento", ""))
        if not nome or not movimento or not quantidade or not data_movimento:
            erros.append(f"Linha {i}: item, movimento, quantidade e data são obrigatórios")
            continue
        try:
            dados = MovimentoIn(
                nome=nome, movimento=movimento, quantidade=quantidade,
                unidade=row.get("unidade", "").strip() or None,
                data_movimento=data_movimento,
                observacao=row.get("observacao", "").strip() or None,
            )
            _criar_movimento_estoque(dados, session, fazenda_id=fazenda_id)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "estoque_movimento", "criados": criados, "erros": erros}


@router.post("/produtos_estoque")
async def importar_produtos_estoque(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome", "").strip()
        if not nome:
            erros.append(f"Linha {i}: nome é obrigatório")
            continue

        fornecedor_id = None
        fornecedor_nome = row.get("fornecedor_nome", "").strip()
        if fornecedor_nome:
            fornecedor_query = select(Fornecedor).where(Fornecedor.nome == fornecedor_nome)
            if fazenda_id is not None:
                fornecedor_query = fornecedor_query.where(Fornecedor.fazenda_id == fazenda_id)
            fornecedor = session.exec(fornecedor_query).first()
            if not fornecedor:
                erros.append(f"Linha {i}: fornecedor '{fornecedor_nome}' não encontrado — cadastre-o antes")
            else:
                fornecedor_id = fornecedor.id

        item_query = select(Estoque).where(Estoque.nome == nome)
        if fazenda_id is not None:
            item_query = item_query.where(Estoque.fazenda_id == fazenda_id)
        item = session.exec(item_query).first()
        if not item:
            item = Estoque(nome=nome, categoria=row.get("categoria", "").strip() or None,
                            unidade=row.get("unidade", "").strip() or None, quantidade=0,
                            fazenda_id=fazenda_id)
            criados += 1
        else:
            atualizados += 1
        unidade_embalagem = row.get("unidade_embalagem", "").strip()
        if unidade_embalagem:
            item.unidade_embalagem = unidade_embalagem
        medida_embalagem = row.get("medida_embalagem", "").strip()
        if medida_embalagem:
            item.medida_embalagem = medida_embalagem
        quantidade_embalagem = parse_float(row.get("quantidade_embalagem", ""))
        if quantidade_embalagem is not None:
            item.quantidade_embalagem = quantidade_embalagem
        if fornecedor_id is not None:
            item.fornecedor_id = fornecedor_id
        session.add(item)

    session.commit()
    return {"categoria": "produtos_estoque", "criados": criados, "atualizados": atualizados, "erros": erros}


@router.post("/fornecedores")
async def importar_fornecedores(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome", "").strip()
        tipo = row.get("tipo", "").strip().lower()
        if not nome or tipo not in ("fornecedor", "fabricante", "cliente"):
            erros.append(f"Linha {i}: nome e tipo (fornecedor/fabricante/cliente) são obrigatórios")
            continue

        fornecedor_query = select(Fornecedor).where(Fornecedor.nome == nome)
        if fazenda_id is not None:
            fornecedor_query = fornecedor_query.where(Fornecedor.fazenda_id == fazenda_id)
        f = session.exec(fornecedor_query).first()
        if not f:
            f = Fornecedor(nome=nome, tipo=tipo, fazenda_id=fazenda_id)
            criados += 1
        else:
            f.tipo = tipo
            atualizados += 1
        f.categoria = row.get("categoria", "").strip() or None
        f.cnpj_cpf = row.get("cnpj_cpf", "").strip() or None
        f.telefone = row.get("telefone", "").strip() or None
        f.email = row.get("email", "").strip() or None
        session.add(f)

    session.commit()
    return {"categoria": "fornecedores", "criados": criados, "atualizados": atualizados, "erros": erros}


@router.post("/animais_cadastro")
async def importar_animais_cadastro(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Cadastro em lote de animais pela ficha simplificada — cria os que não
    existem e atualiza os que já existem (casado por número), sem exigir a
    planilha rica do Ideagri (que é para o rebanho já em operação).
    """
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        numero = row.get("numero", "").strip()
        if not numero:
            erros.append(f"Linha {i}: número é obrigatório")
            continue

        # BUG DE SEGURANÇA CORRIGIDO: sem o filtro de fazenda_id, um número
        # coincidente com o de outra fazenda-cliente sobrescrevia o cadastro
        # dela; animais novos eram criados sem fazenda_id (órfãos).
        animal = session.exec(
            select(Animal).where(Animal.numero == numero, Animal.fazenda_id == fazenda_id)
        ).first()
        if not animal:
            # `Animal.numero` passou a ser único só POR FAZENDA (ver migração
            # c24befa94c1b) — duas fazendas diferentes podem legitimamente ter
            # cada uma o seu animal "100" (é justamente o caso da Fazenda
            # Teste, cópia da fazenda real com os mesmos números). Por isso
            # NÃO existe mais aqui a checagem de "número já usado em outra
            # fazenda": ela vinha de quando a unicidade era global e hoje
            # bloquearia uma importação legítima.
            animal = Animal(numero=numero, ativo=True, fazenda_id=fazenda_id)
            criados += 1
        else:
            atualizados += 1
        animal.nome = row.get("nome", "").strip() or None
        sexo = row.get("sexo", "").strip().upper() or None
        if sexo:
            animal.sexo = sexo
        animal.raca = row.get("raca", "").strip() or None
        data_nasc = parse_date(row.get("data_nasc", ""))
        if data_nasc:
            animal.data_nasc = data_nasc
        lote = row.get("lote", "").strip()
        if lote:
            animal.grupo_primario = lote
            animal.grupo_manual = True  # protege do próximo upload do GERAL.csv sobrescrever
        data_entrada = parse_date(row.get("data_entrada", ""))
        if data_entrada:
            animal.data_entrada = data_entrada
        # Genealogia (opcional) — permite já trazer o pai/mãe no cadastro em
        # lote, sem precisar preencher depois um a um na ficha manual.
        pai_nome = row.get("pai_nome", "").strip()
        if pai_nome:
            animal.pai_nome = pai_nome
        pai_naab = row.get("pai_naab", "").strip()
        if pai_naab:
            animal.pai_naab = pai_naab
        mae_numero = row.get("mae_numero", "").strip()
        if mae_numero:
            animal.mae_numero = mae_numero
        mae_nome = row.get("mae_nome", "").strip()
        if mae_nome:
            animal.mae_nome = mae_nome
        if pai_nome:
            _completar_genealogia_paterna(session, animal)
        session.add(animal)

    session.commit()
    return {"categoria": "animais_cadastro", "criados": criados, "atualizados": atualizados, "erros": erros}


@router.post("/animais_genealogia")
async def importar_animais_genealogia(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Complemento de genealogia (pai/mãe) para animais JÁ CADASTRADOS — ao
    contrário de /animais_cadastro, NÃO cria animal novo (número não
    encontrado vira erro). Pensado para quem cadastrou o animal comprado só
    com número e data de nascimento e quer voltar depois e preencher o pai
    (touro/sêmen) sem duplicar o cadastro. Só grava a coluna que veio
    preenchida na planilha — célula vazia não apaga o que já estava salvo.
    """
    content = await file.read()
    atualizados = 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        numero = row.get("numero", "").strip()
        if not numero:
            erros.append(f"Linha {i}: número é obrigatório")
            continue
        # BUG DE SEGURANÇA CORRIGIDO: sem este filtro, esta rota editava a
        # genealogia de um animal de OUTRA fazenda se o número coincidisse.
        animal = session.exec(
            select(Animal).where(Animal.numero == numero, Animal.fazenda_id == fazenda_id)
        ).first()
        if not animal:
            erros.append(f"Linha {i}: animal {numero} não encontrado — cadastre-o primeiro (ex.: em \"Cadastro de animais em lote\")")
            continue

        pai_nome = row.get("pai_nome", "").strip()
        if pai_nome:
            animal.pai_nome = pai_nome
        pai_naab = row.get("pai_naab", "").strip()
        if pai_naab:
            animal.pai_naab = pai_naab
        mae_numero = row.get("mae_numero", "").strip()
        if mae_numero:
            animal.mae_numero = mae_numero
        mae_nome = row.get("mae_nome", "").strip()
        if mae_nome:
            animal.mae_nome = mae_nome

        if not (pai_nome or pai_naab or mae_numero or mae_nome):
            erros.append(f"Linha {i}: nenhuma coluna de genealogia preenchida para o animal {numero}")
            continue

        if pai_nome:
            _completar_genealogia_paterna(session, animal)
        animal.atualizado_em = datetime.utcnow()
        session.add(animal)
        atualizados += 1

    session.commit()
    return {"categoria": "animais_genealogia", "atualizados": atualizados, "erros": erros}


@router.post("/qualidade_leite")
async def importar_qualidade_leite(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    """Histórico de qualidade do leite — uma linha por coleta (tanque quando
    numero_matriz vem vazio, ou de uma vaca específica)."""
    content = await file.read()
    criados = 0
    erros: list[str] = []

    import re as _re
    import unicodedata as _ud

    def _norm(s: str) -> str:
        s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return _re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

    # Apelidos de coluna para tolerar os exports da Clínica do Leite (ESALQ) e do
    # LQL, que trazem cabeçalhos variados.
    APELIDOS = {
        "numero_matriz": ["numero matriz", "numero", "vaca", "animal", "id", "brinco"],
        "data_coleta": ["data coleta", "data", "data da coleta", "coleta"],
        "ccs": ["ccs", "ccs mil ml", "ccs x1000", "celulas somaticas"],
        "cbt": ["cbt", "cpp", "cbt mil ufc ml", "contagem bacteriana", "ufc"],
        "gordura_pct": ["gordura pct", "gordura", "gordura g", "teor de gordura"],
        "proteina_pct": ["proteina pct", "proteina", "proteina g", "teor de proteina"],
        "solidos_totais_pct": ["solidos totais pct", "solidos totais", "est", "extrato seco total"],
        "esd_pct": ["esd pct", "esd", "extrato seco desengordurado"],
        "lactose_pct": ["lactose pct", "lactose"],
        "nul": ["nul", "ureia", "mun", "num", "nitrogenio ureico", "nitrogenio ureico no leite"],
    }

    def get(row_norm: dict, campo: str) -> str:
        for ap in APELIDOS[campo]:
            if ap in row_norm and (row_norm[ap] or "").strip() != "":
                return row_norm[ap]
        return ""

    for i, row in enumerate(iter_csv_rows(content), start=2):
        row_norm = {_norm(k): v for k, v in row.items()}
        data_coleta = parse_date(get(row_norm, "data_coleta"))
        if not data_coleta:
            erros.append(f"Linha {i}: data_coleta é obrigatória")
            continue
        dados = QualidadeLeiteIn(
            numero_matriz=get(row_norm, "numero_matriz").strip() or None,
            data_coleta=data_coleta,
            ccs=parse_float(get(row_norm, "ccs")),
            cbt=parse_float(get(row_norm, "cbt")),
            gordura_pct=parse_float(get(row_norm, "gordura_pct")),
            proteina_pct=parse_float(get(row_norm, "proteina_pct")),
            solidos_totais_pct=parse_float(get(row_norm, "solidos_totais_pct")),
            esd_pct=parse_float(get(row_norm, "esd_pct")),
            lactose_pct=parse_float(get(row_norm, "lactose_pct")),
            nul=parse_float(get(row_norm, "nul")),
        )
        criar_qualidade_leite(dados, session)
        criados += 1

    return {"categoria": "qualidade_leite", "criados": criados, "erros": erros}


@router.post("/dairycomp")
async def importar_dairycomp(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Importa um export do DairyComp 305 (uma linha por animal/parto) com a data
    de nascimento e as datas de parto — alimenta a idade ao 1º parto (Wisconsin)
    do Dossiê da Recria. Cria/atualiza a data de nascimento do animal e insere
    os partos que ainda não existem (deduplicados por animal + data). Nunca
    apaga nada; só acrescenta o que falta.
    """
    content = await file.read()
    animais_atualizados = 0
    partos_criados = 0
    erros: list[str] = []

    # BUG DE SEGURANÇA CORRIGIDO: sem o filtro de fazenda_id, um número
    # coincidente com o de outra fazenda-cliente alterava a data de
    # nascimento dela e podia anexar um Parto ao animal errado. O índice de
    # dedup também é escopado por fazenda — senão um (numero, data) já
    # existente em OUTRA fazenda escondia um parto legítimo desta.
    existentes = {
        (p.numero_matriz, p.data_parto)
        for p in session.exec(select(Parto).where(Parto.fazenda_id == fazenda_id)).all()
        if p.data_parto
    }

    # O DairyComp exporta separado por vírgula; o resto do site usa ';'. Aceita
    # os dois — detecta pelo cabeçalho e lê com o csv padrão.
    import csv as _csv
    import io as _io
    texto = content.decode("utf-8-sig", errors="replace")
    primeira = texto.splitlines()[0] if texto.strip() else ""
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    linhas_dict = [
        {k.strip(): (v or "").strip() for k, v in r.items()}
        for r in _csv.DictReader(_io.StringIO(texto), delimiter=delim)
    ]

    for i, row in enumerate(linhas_dict, start=2):
        numero = (row.get("numero_matriz") or "").strip()
        if not numero:
            erros.append(f"Linha {i}: número do animal (ID) é obrigatório")
            continue
        data_nasc = parse_date(row.get("data_nascimento", ""))
        data_parto = parse_date(row.get("data_parto", ""))
        ordem = parse_int(row.get("ordem_parto", ""))

        animal = session.exec(
            select(Animal).where(Animal.numero == numero, Animal.fazenda_id == fazenda_id)
        ).first()
        if not animal:
            # Mesma observação de importar_animais_cadastro acima: numero é
            # único só por fazenda desde c24befa94c1b, então coincidir com o
            # número de outra fazenda não é mais motivo para recusar.
            animal = Animal(numero=numero, data_nasc=data_nasc, ativo=True, fazenda_id=fazenda_id)
            session.add(animal)
            session.commit()
            session.refresh(animal)
            animais_atualizados += 1
        elif data_nasc and animal.data_nasc != data_nasc:
            animal.data_nasc = data_nasc
            session.add(animal)
            animais_atualizados += 1

        if data_parto and (numero, data_parto) not in existentes:
            session.add(Parto(
                animal_id=animal.id, numero_matriz=numero, data_parto=data_parto, ordem_parto=ordem,
                fazenda_id=fazenda_id,
            ))
            existentes.add((numero, data_parto))
            partos_criados += 1

    session.commit()
    # Partos importados também precisam existir como LACTAÇÃO — senão o
    # controle leiteiro dessas vacas passa a ser recusado (ver
    # POST /producao/controles) por uma lactação que só falta materializar.
    # Idempotente: reprocessar não duplica (ver rules/lactacao.py).
    if partos_criados:
        from fazenda.rules.lactacao import backfill_lactacoes
        backfill_lactacoes(session)
        session.commit()
    return {
        "categoria": "dairycomp", "criados": partos_criados,
        "animais_atualizados": animais_atualizados, "erros": erros,
    }


@router.post("/calendario_sanitario")
async def importar_calendario_sanitario(
    file: UploadFile, session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Calendário sanitário (preventivo) da fazenda — uma regra por linha. Casa o
    evento sanitário pelo nome (cria se não existir, já com a categoria
    preventiva e a doença), casa a doença pelo nome (cria se não existir) e
    grava a regra recorrente em CalendarioSanitario. Nunca apaga nada; só
    acrescenta o que falta (dedup por evento+categoria_alvo+data).
    """
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    CATS_PREVENTIVAS = {"vacina", "exame", "tratamento"}

    # BUG DE SEGURANÇA CORRIGIDO: EventoSanitario/Doenca são cadastros POR
    # FAZENDA (uq_..._nome_fazenda) — buscar/criar sem fazenda_id podia
    # editar o evento de OUTRA fazenda com o mesmo nome, ou criar um
    # registro órfão (fazenda_id=NULL) global a todas as fazendas.
    def _evento(nome: str, categoria: str | None, doenca_id: int | None) -> EventoSanitario:
        ev = session.exec(
            select(EventoSanitario).where(EventoSanitario.nome == nome, EventoSanitario.fazenda_id == fazenda_id)
        ).first()
        if not ev:
            ev = EventoSanitario(nome=nome, fazenda_id=fazenda_id)
            session.add(ev)
        if categoria and not ev.categoria_preventiva:
            ev.categoria_preventiva = categoria
        if doenca_id and not ev.doenca_id:
            ev.doenca_id = doenca_id
        session.flush()
        return ev

    def _doenca(nome: str) -> int | None:
        nome = (nome or "").strip()
        if not nome:
            return None
        d = session.exec(
            select(Doenca).where(Doenca.nome == nome, Doenca.fazenda_id == fazenda_id)
        ).first()
        if not d:
            d = Doenca(nome=nome, fazenda_id=fazenda_id)
            session.add(d)
            session.flush()
        return d.id

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome_evento = row.get("evento", "").strip()
        if not nome_evento:
            erros.append(f"Linha {i}: evento é obrigatório")
            continue
        data_evento = parse_date(row.get("data_evento", ""))
        if not data_evento:
            erros.append(f"Linha {i}: data_evento é obrigatória (DD/MM/AAAA)")
            continue
        freq_valor = parse_int(row.get("frequencia_valor", "")) or 1
        freq_unidade = (row.get("frequencia_unidade", "") or "meses").strip().lower()
        if freq_unidade not in ("dias", "meses", "anos"):
            freq_unidade = "meses"
        categoria = (row.get("categoria", "") or "").strip().lower() or None
        if categoria and categoria not in CATS_PREVENTIVAS:
            categoria = None

        doenca_id = _doenca(row.get("doenca", ""))
        ev = _evento(nome_evento, categoria, doenca_id)
        categoria_alvo = row.get("categoria_alvo", "").strip() or None

        regra = session.exec(
            select(CalendarioSanitario).where(
                CalendarioSanitario.evento_sanitario_id == ev.id,
                CalendarioSanitario.data_evento == data_evento,
            )
        ).first()
        if regra and (regra.categoria_alvo or "") == (categoria_alvo or ""):
            regra.doenca_id = doenca_id or regra.doenca_id
            regra.produto = row.get("produto", "").strip() or regra.produto
            regra.dosagem = row.get("dosagem", "").strip() or regra.dosagem
            regra.frequencia_valor = freq_valor
            regra.frequencia_unidade = freq_unidade
            atualizados += 1
        else:
            session.add(CalendarioSanitario(
                evento_sanitario_id=ev.id, categoria_alvo=categoria_alvo, doenca_id=doenca_id,
                produto=row.get("produto", "").strip() or None, dosagem=row.get("dosagem", "").strip() or None,
                frequencia_valor=freq_valor, frequencia_unidade=freq_unidade, data_evento=data_evento,
                fazenda_id=fazenda_id,
            ))
            criados += 1

    session.commit()
    return {"categoria": "calendario_sanitario", "criados": criados, "atualizados": atualizados, "erros": erros}


def _ocorrencia_valida(base: date | None, valor: int | None, unidade: str | None, alvo: date) -> bool:
    """True quando `alvo` cai exatamente numa ocorrência da recorrência que
    começa em `base` — usado para validar uma data de pendência antiga sem
    limitar a busca a nenhuma janela de tempo (ao contrário de
    `_ocorrencias_recorrentes`, feita para a Agenda ao vivo)."""
    if not (base and valor and unidade) or valor <= 0 or alvo < base:
        return False
    d = base
    guarda = 0
    while d < alvo and guarda < 3000:
        d = proxima_ocorrencia(d, valor, unidade)
        guarda += 1
    return d == alvo


@router.post("/baixas_pendencias_agenda")
async def importar_baixas_pendencias_agenda(
    file: UploadFile, data_corte: str = Form(""), session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Baixa em massa de pendências antigas da Agenda (sanitário) — uma linha por
    pendência. Resolve exatamente como o usuário resolveria uma a uma na tela
    (mesma função `registrar_aplicacao`/`_baixar_aplicacao_agendada` de sempre):
    grava a aplicação de verdade em Sanidade (com baixa de estoque quando a
    unidade bate) e dispensa a pendência da Agenda (EventoRealizado). Não cria
    nenhuma regra nova de calendário — só fecha o que já estava pendente.
    Linhas com data_pendencia >= data_corte são ignoradas (mantidas na Agenda).
    """
    content = await file.read()
    corte = parse_date(data_corte) if data_corte else None
    criados, dispensados, erros = 0, 0, []

    def _ja_realizado(eid: str) -> bool:
        # `fazenda_id` gravado abaixo (não mais None) — filtra por ele também
        # aqui: o par (evento_id, fazenda_id) é a chave real (uq em
        # models/sistema.py::EventoRealizado), não só evento_id.
        query = select(EventoRealizado).where(EventoRealizado.evento_id == eid)
        if fazenda_id is not None:
            query = query.where(EventoRealizado.fazenda_id == fazenda_id)
        return session.exec(query).first() is not None

    def _dispensar(eid: str) -> bool:
        """Marca o evento como realizado; False se já estava (evita duplicar Sanidade)."""
        if _ja_realizado(eid):
            return False
        # BUG DE SEGURANÇA CORRIGIDO: gravava sem `fazenda_id` (None); como
        # agenda.py lê EventoRealizado com `fazenda_id.in_((fazenda_id, None))`
        # (a linha NULL "dispensa para todo mundo"), um `eid` que a cadeia
        # acima resolvesse para a REGRA de outra fazenda dispensava a
        # pendência dela na Agenda dela — sem ela ter feito nada. Combinado
        # com o filtro de fazenda_id nas duas seleções abaixo, `eid` agora só
        # pode se referir a uma regra da PRÓPRIA fazenda, e fica gravado como
        # tal.
        session.add(EventoRealizado(evento_id=eid, fazenda_id=fazenda_id))
        session.flush()
        return True

    for i, row in enumerate(iter_csv_rows(content), start=2):
        tipo = (row.get("tipo", "") or "").strip().lower()
        nome_evento = (row.get("nome_evento", "") or "").strip()
        numeros = [n.strip() for n in (row.get("numero_animal", "") or "").replace(";", ",").split(",") if n.strip()]
        data_pendencia = parse_date(row.get("data_pendencia", ""))
        produto = (row.get("produto_aplicado", "") or "").strip() or None
        dose = parse_float(row.get("dose", ""))
        unidade = (row.get("unidade", "") or "").strip() or None
        via = (row.get("via", "") or "").strip() or None
        responsavel = (row.get("responsavel", "") or "").strip() or None
        observacao = (row.get("observacao", "") or "").strip() or None

        if not data_pendencia:
            erros.append(f"Linha {i}: data_pendencia é obrigatória (DD/MM/AAAA)")
            continue
        if corte and data_pendencia >= corte:
            erros.append(f"Linha {i}: data_pendencia {data_pendencia.isoformat()} não é anterior à data de corte — ignorada (mantida na Agenda)")
            continue

        try:
            if tipo == "evento_sanitario":
                if not nome_evento:
                    raise ValueError("nome_evento é obrigatório para tipo evento_sanitario")
                # BUG DE SEGURANÇA CORRIGIDO: faltava o filtro por fazenda_id
                # (uq real é (nome, fazenda_id) — models/sanidade.py — e cada
                # fazenda cria seu próprio "Vermífugo"/"Brucelose B19" com o
                # mesmo nome do catálogo semeado). Sem o filtro, um nome_evento
                # que também existisse em OUTRA fazenda podia resolver o
                # EventoSanitario dela — produto/dose padrão e regras de
                # gatilho alheios entrando no lançamento local.
                query_ev = select(EventoSanitario).where(EventoSanitario.nome == nome_evento)
                if fazenda_id is not None:
                    query_ev = query_ev.where(EventoSanitario.fazenda_id == fazenda_id)
                ev = session.exec(query_ev).first()
                if not ev:
                    raise ValueError(f'evento sanitário "{nome_evento}" não encontrado')

                if ev.tipo_agendamento == "evento":
                    if len(numeros) != 1:
                        raise ValueError("este evento é por gatilho (por animal) — informe exatamente 1 numero_animal")
                    numero = numeros[0]
                    # `fazenda_id` explícito (antes ficava None por posição —
                    # mesmo defeito do F-C-01): sem ele, a validação do
                    # gatilho considerava animal/secagem/parto/etc. de
                    # QUALQUER fazenda, não só da própria.
                    candidatos = _datas_gatilho(
                        session, ev.gatilho, ev.gatilho_lote, ev.gatilho_idade_meses, ev.offset_dias or 0, ev.sexo_alvo,
                        fazenda_id=fazenda_id,
                    )
                    if not any(n == numero and d == data_pendencia for n, d in candidatos):
                        raise ValueError(f"nenhuma ocorrência do gatilho deste evento para a matriz {numero} em {data_pendencia.isoformat()}")
                    eid = f"evento_sanitario_{ev.id}__{numero}__{data_pendencia.isoformat()}"
                    alvo_animais = [numero]
                elif ev.tipo_agendamento == "epoca":
                    if not _ocorrencia_valida(ev.data_primeiro, ev.frequencia_valor, ev.frequencia_unidade, data_pendencia):
                        raise ValueError("data_pendencia não corresponde a nenhuma ocorrência da recorrência por época deste evento")
                    eid = f"evento_sanitario_{ev.id}__rebanho__{data_pendencia.isoformat()}"
                    if not numeros:
                        raise ValueError("informe ao menos 1 numero_animal — quem de fato recebeu a aplicação")
                    alvo_animais = numeros
                else:
                    raise ValueError("evento sanitário não está configurado com agendamento por época ou por gatilho")

                eh_exame = ev.categoria_preventiva == "exame"
                if not eh_exame:
                    produto_final = produto or ev.produto_padrao
                    dose_final = dose if dose is not None else ev.dose_padrao
                    unidade_final = unidade or ev.unidade_padrao
                    via_final = via or ev.via_padrao
                    if not (produto_final and dose_final is not None and unidade_final):
                        raise ValueError("produto_aplicado/dose/unidade são obrigatórios (ou cadastre o padrão no evento sanitário)")

                # Validado — só agora dispensa a pendência (nunca antes de garantir
                # que a aplicação de verdade também vai ser gravada com sucesso).
                novo = _dispensar(eid)
                if novo:
                    if not eh_exame:
                        registrar_aplicacao(
                            AplicacaoIn(
                                data_aplicacao=data_pendencia, animais=alvo_animais,
                                itens=[ItemAplicacaoIn(produto=produto_final, via=via_final, quantidade=dose_final, unidade=unidade_final)],
                                responsavel=responsavel, observacao=observacao or f"Baixa retroativa: {ev.nome}",
                                aplicado=True, natureza="preventivo",
                            ),
                            session=session, user=user, fazenda_id=fazenda_id,
                        )
                        criados += len(alvo_animais)
                    dispensados += 1

            elif tipo == "calendario_sanitario":
                if not nome_evento:
                    raise ValueError("nome_evento é obrigatório para tipo calendario_sanitario")
                # BUG DE SEGURANÇA CORRIGIDO: mesma omissão do ramo
                # `evento_sanitario` acima — o JOIN casava regras de
                # CalendarioSanitario de QUALQUER fazenda que tivesse um
                # EventoSanitario com esse nome. `_dispensar` abaixo usa o id
                # da regra encontrada (`c.id`) no `eid` — resolver a regra
                # errada dispensava a pendência de OUTRA fazenda na Agenda
                # dela (ver rules/eventos_sanitarios.py e agenda.py, mesmo
                # padrão de filtro estrito por fazenda_id usado nesses dois
                # arquivos para CalendarioSanitario).
                query_regras = (
                    select(CalendarioSanitario)
                    .join(EventoSanitario, CalendarioSanitario.evento_sanitario_id == EventoSanitario.id)
                    .where(EventoSanitario.nome == nome_evento, CalendarioSanitario.ativo == True)  # noqa: E712
                )
                if fazenda_id is not None:
                    query_regras = query_regras.where(CalendarioSanitario.fazenda_id == fazenda_id)
                regras = session.exec(query_regras).all()
                validas = [c for c in regras if _ocorrencia_valida(c.data_evento, c.frequencia_valor, c.frequencia_unidade, data_pendencia)]
                if not validas:
                    raise ValueError(f'nenhuma regra do calendário sanitário "{nome_evento}" tem ocorrência em {data_pendencia.isoformat()}')
                if not numeros:
                    raise ValueError("informe ao menos 1 numero_animal — quem de fato recebeu a aplicação")

                ev = session.get(EventoSanitario, validas[0].evento_sanitario_id)
                eh_exame = (ev.categoria_preventiva if ev else None) == "exame"
                for c in validas:
                    eid = f"calendario_sanitario_{c.id}__{data_pendencia.isoformat()}"
                    if not eh_exame:
                        produto_final = produto or c.produto
                        dose_final = dose if dose is not None else parse_float(c.dosagem or "")
                        unidade_final = unidade or c.unidade
                        if not (produto_final and dose_final is not None and unidade_final):
                            raise ValueError("produto_aplicado/dose/unidade são obrigatórios (ou cadastre o padrão na regra do calendário)")

                    novo = _dispensar(eid)
                    if novo:
                        if not eh_exame:
                            registrar_aplicacao(
                                AplicacaoIn(
                                    data_aplicacao=data_pendencia, animais=numeros,
                                    itens=[ItemAplicacaoIn(produto=produto_final, via=via, quantidade=dose_final, unidade=unidade_final)],
                                    responsavel=responsavel, observacao=observacao or f"Baixa retroativa: {nome_evento}",
                                    aplicado=True, natureza="preventivo",
                                ),
                                session=session, user=user, fazenda_id=fazenda_id,
                            )
                            criados += len(numeros)
                        dispensados += 1

            elif tipo == "aplicacao_agendada":
                if len(numeros) != 1:
                    raise ValueError("informe exatamente 1 numero_animal para tipo aplicacao_agendada")
                numero = numeros[0]
                # BUG DE SEGURANÇA CORRIGIDO: sem o filtro de fazenda_id, uma
                # colisão de numero_matriz com outra fazenda (numero deixou
                # de ser único globalmente — ver Animal.numero) podia pegar a
                # AplicacaoAgendada PENDENTE DE OUTRA FAZENDA e, pior, o
                # `_baixar_aplicacao_agendada` abaixo era chamado sem
                # `fazenda_id` (ficava None por default) — perdia até a
                # trava de segurança que a própria função já tem.
                ag = session.exec(
                    select(AplicacaoAgendada).where(
                        AplicacaoAgendada.numero_matriz == numero,
                        AplicacaoAgendada.data == data_pendencia,
                        AplicacaoAgendada.aplicado == False,  # noqa: E712
                        AplicacaoAgendada.fazenda_id == fazenda_id,
                    )
                ).first()
                if not ag:
                    raise ValueError(f"nenhuma aplicação agendada pendente para a matriz {numero} em {data_pendencia.isoformat()}")
                eid = f"aplic_agendada_{ag.id}"
                novo = _dispensar(eid)
                if novo:
                    _baixar_aplicacao_agendada(
                        session, eid, produto, dose, unidade, via,
                        fazenda_id=fazenda_id, usuario_id=usuario_id_seguro(user),
                    )
                    criados += 1
                    dispensados += 1

            else:
                raise ValueError('tipo deve ser "evento_sanitario", "calendario_sanitario" ou "aplicacao_agendada"')

        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")
        except ValueError as exc:
            erros.append(f"Linha {i}: {exc}")

    session.commit()
    return {"categoria": "baixas_pendencias_agenda", "criados": criados, "dispensados": dispensados, "erros": erros}


@router.post("/touros_naab")
async def importar_touros_naab(
    file: UploadFile,
    fonte: str = Form(""),
    rodada: str = Form(""),
    session: Session = Depends(get_session),
) -> dict:
    """
    Catálogo genético de touros (provas do fornecedor / NAAB-CDCB). Aceita o
    Excel (.xlsx) ou CSV exportado do ABS BullSearch, Alta, Select Sires etc.

    Catálogos completos (dezenas de colunas de provas, ex.: exportação da
    Alta Genetics) são lidos por posição de coluna, preservando TODOS os
    dados por touro; CSVs simples continuam usando o casamento por apelidos.
    Upsert por código NAAB; nunca apaga touros existentes.
    """
    from fazenda.rules.touros import eh_planilha_rica, importar_touros, importar_touros_planilha_rica, ler_planilha
    content = await file.read()
    nome = (file.filename or "").lower()
    try:
        if nome.endswith((".xlsx", ".xlsm")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            cabecalhos = next(wb.active.iter_rows(values_only=True), [])
            if eh_planilha_rica(list(cabecalhos)):
                resultado = importar_touros_planilha_rica(session, content, fonte.strip() or None, rodada.strip() or None)
                return {"categoria": "touros_naab", **resultado}
        linhas = ler_planilha(content, file.filename)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — arquivo ilegível vira erro amigável
        raise HTTPException(status_code=400, detail=f"Não consegui ler o arquivo: {e}")
    resultado = importar_touros(session, linhas, fonte.strip() or None, rodada.strip() or None)
    return {"categoria": "touros_naab", **resultado}


@router.post("/backfill")
def backfill_fornecedores_e_estoque(
    session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Varre os dados já importados (financeiro, curva ABC, dieta, sanidade) e
    cadastra automaticamente os fornecedores e itens de estoque citados neles
    que ainda não existem — idempotente, seguro de rodar quantas vezes quiser.
    Não sobrescreve nada que já existe, só preenche o que falta.
    """
    fornecedor_query = select(Fornecedor.nome)
    conta_query = select(ContaGerencial.fornecedor_cliente)
    if fazenda_id is not None:
        fornecedor_query = fornecedor_query.where(Fornecedor.fazenda_id == fazenda_id)
        conta_query = conta_query.where(ContaGerencial.fazenda_id == fazenda_id)
    fornecedores_existentes = set(session.exec(fornecedor_query).all())
    nomes_conta = {c.strip() for c in session.exec(conta_query).all() if c and c.strip()}
    fornecedores_criados = []
    for nome in sorted(nomes_conta - fornecedores_existentes):
        f = Fornecedor(nome=nome, tipo="fornecedor", fazenda_id=fazenda_id)
        session.add(f)
        fornecedores_criados.append(nome)

    estoque_query = select(Estoque.nome)
    curva_query = select(CurvaABC.produto)
    # NÃO aplicar sem_itens_de_vale aqui — são candidatos a cadastro de
    # estoque a partir de nomes de produto já usados; excluir os itens de
    # vale só empobreceria a lista de sugestões (ver rules/vale_item.py).
    lancamento_query = select(LancamentoItem.produto)
    sanidade_query = select(Sanidade.produto)
    if fazenda_id is not None:
        estoque_query = estoque_query.where(Estoque.fazenda_id == fazenda_id)
        curva_query = curva_query.where(CurvaABC.fazenda_id == fazenda_id)
        lancamento_query = lancamento_query.where(LancamentoItem.fazenda_id == fazenda_id)
        sanidade_query = sanidade_query.where(Sanidade.fazenda_id == fazenda_id)
    estoque_existente = set(session.exec(estoque_query).all())
    candidatos_estoque: set[str] = set()
    for produto in session.exec(curva_query).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for produto in session.exec(lancamento_query).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for ingrediente in session.exec(select(Dieta.ingrediente)).all():
        if ingrediente and ingrediente.strip():
            candidatos_estoque.add(ingrediente.strip())
    for produto in session.exec(sanidade_query).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())

    estoque_criados = []
    for nome in sorted(candidatos_estoque - estoque_existente):
        session.add(Estoque(nome=nome, quantidade=0, fazenda_id=fazenda_id))
        estoque_criados.append(nome)

    session.commit()
    return {
        "fornecedores_criados": fornecedores_criados,
        "estoque_criados": estoque_criados,
        "total_fornecedores_criados": len(fornecedores_criados),
        "total_estoque_criados": len(estoque_criados),
    }
