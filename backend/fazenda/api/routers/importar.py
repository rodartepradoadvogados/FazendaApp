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

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.api.routers.estoque import MovimentoIn, movimentar_estoque
from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
from fazenda.api.routers.producao import (
    ControlesIn, OrdenhaIn, PesagensIn, PesoIn, QualidadeLeiteIn, criar_controles, criar_pesagens, criar_qualidade_leite,
)
from fazenda.database import get_session
from fazenda.models import Animal, ContaGerencial, CurvaABC, Dieta, Estoque, Fornecedor, LancamentoItem, Parto, Sanidade
from fazenda.parsers.utils import iter_csv_rows, parse_date, parse_float, parse_int

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
        "colunas": ["numero", "nome", "sexo (F/M)", "raca", "data_nasc (DD/MM/AAAA)", "lote", "data_entrada (DD/MM/AAAA)"],
        "colunas_csv": ["numero", "nome", "sexo", "raca", "data_nasc", "lote", "data_entrada"],
        "exemplo": ["465", "Mimosa", "F", "Girolando", "10/03/2024", "01 - BEZ 1 (0 A 30)", "10/03/2024"],
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
async def importar_pesagem(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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
        resultado = criar_pesagens(PesagensIn(data_pesagem=data, entradas=entradas), session)
        criados += resultado["criados"]
    return {"categoria": "pesagem", "criados": criados, "erros": erros}


@router.post("/controle_leiteiro_simples")
async def importar_controle_leiteiro_simples(
    file: UploadFile,
    data_controle: date = Form(...),
    session: Session = Depends(get_session),
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
        resultado = criar_controles(ControlesIn(data_controle=dia, entradas=entradas), session)
        criados += resultado["criados"]
    return {"categoria": "controle_leiteiro_simples", "criados": criados, "erros": erros}


@router.post("/financeiro")
async def importar_financeiro(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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
                fornecedor_cliente=row.get("fornecedor_cliente", "").strip() or None,
                data_emissao=data,
                data_competencia=data,
                parcelas=[ParcelaIn(data_vencimento=data, valor=valor)],
            )
            criar_lancamento(dados, session)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "financeiro", "criados": criados, "erros": erros}


@router.post("/estoque_movimento")
async def importar_estoque_movimento(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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
            movimentar_estoque(dados, session)
            criados += 1
        except HTTPException as exc:
            erros.append(f"Linha {i}: {exc.detail}")

    return {"categoria": "estoque_movimento", "criados": criados, "erros": erros}


@router.post("/produtos_estoque")
async def importar_produtos_estoque(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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
            fornecedor = session.exec(select(Fornecedor).where(Fornecedor.nome == fornecedor_nome)).first()
            if not fornecedor:
                erros.append(f"Linha {i}: fornecedor '{fornecedor_nome}' não encontrado — cadastre-o antes")
            else:
                fornecedor_id = fornecedor.id

        item = session.exec(select(Estoque).where(Estoque.nome == nome)).first()
        if not item:
            item = Estoque(nome=nome, categoria=row.get("categoria", "").strip() or None,
                            unidade=row.get("unidade", "").strip() or None, quantidade=0)
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
async def importar_fornecedores(file: UploadFile, session: Session = Depends(get_session)) -> dict:
    content = await file.read()
    criados, atualizados = 0, 0
    erros: list[str] = []

    for i, row in enumerate(iter_csv_rows(content), start=2):
        nome = row.get("nome", "").strip()
        tipo = row.get("tipo", "").strip().lower()
        if not nome or tipo not in ("fornecedor", "fabricante", "cliente"):
            erros.append(f"Linha {i}: nome e tipo (fornecedor/fabricante/cliente) são obrigatórios")
            continue

        f = session.exec(select(Fornecedor).where(Fornecedor.nome == nome)).first()
        if not f:
            f = Fornecedor(nome=nome, tipo=tipo)
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
async def importar_animais_cadastro(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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

        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            animal = Animal(numero=numero, ativo=True)
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
        session.add(animal)

    session.commit()
    return {"categoria": "animais_cadastro", "criados": criados, "atualizados": atualizados, "erros": erros}


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
async def importar_dairycomp(file: UploadFile, session: Session = Depends(get_session)) -> dict:
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

    # Índice dos partos já existentes por (animal, data) para deduplicar.
    existentes = {
        (p.numero_matriz, p.data_parto) for p in session.exec(select(Parto)).all() if p.data_parto
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

        animal = session.exec(select(Animal).where(Animal.numero == numero)).first()
        if not animal:
            animal = Animal(numero=numero, data_nasc=data_nasc, ativo=True)
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
            ))
            existentes.add((numero, data_parto))
            partos_criados += 1

    session.commit()
    return {
        "categoria": "dairycomp", "criados": partos_criados,
        "animais_atualizados": animais_atualizados, "erros": erros,
    }


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
    Casa as colunas por apelidos (PT/EN), faz upsert por código NAAB e nunca
    apaga touros existentes.
    """
    from fazenda.rules.touros import importar_touros, ler_planilha
    content = await file.read()
    try:
        linhas = ler_planilha(content, file.filename)
    except Exception as e:  # noqa: BLE001 — arquivo ilegível vira erro amigável
        raise HTTPException(status_code=400, detail=f"Não consegui ler o arquivo: {e}")
    resultado = importar_touros(session, linhas, fonte.strip() or None, rodada.strip() or None)
    return {"categoria": "touros_naab", **resultado}


@router.post("/backfill")
def backfill_fornecedores_e_estoque(session: Session = Depends(get_session)) -> dict:
    """
    Varre os dados já importados (financeiro, curva ABC, dieta, sanidade) e
    cadastra automaticamente os fornecedores e itens de estoque citados neles
    que ainda não existem — idempotente, seguro de rodar quantas vezes quiser.
    Não sobrescreve nada que já existe, só preenche o que falta.
    """
    fornecedores_existentes = set(session.exec(select(Fornecedor.nome)).all())
    nomes_conta = {
        c.strip() for c in session.exec(select(ContaGerencial.fornecedor_cliente)).all() if c and c.strip()
    }
    fornecedores_criados = []
    for nome in sorted(nomes_conta - fornecedores_existentes):
        f = Fornecedor(nome=nome, tipo="fornecedor")
        session.add(f)
        fornecedores_criados.append(nome)

    estoque_existente = set(session.exec(select(Estoque.nome)).all())
    candidatos_estoque: set[str] = set()
    for produto in session.exec(select(CurvaABC.produto)).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for produto in session.exec(select(LancamentoItem.produto)).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for ingrediente in session.exec(select(Dieta.ingrediente)).all():
        if ingrediente and ingrediente.strip():
            candidatos_estoque.add(ingrediente.strip())
    for produto in session.exec(select(Sanidade.produto)).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())

    estoque_criados = []
    for nome in sorted(candidatos_estoque - estoque_existente):
        session.add(Estoque(nome=nome, quantidade=0))
        estoque_criados.append(nome)

    session.commit()
    return {
        "fornecedores_criados": fornecedores_criados,
        "estoque_criados": estoque_criados,
        "total_fornecedores_criados": len(fornecedores_criados),
        "total_estoque_criados": len(estoque_criados),
    }
