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

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.api.routers.cadastro.animais import _completar_genealogia_paterna
from fazenda.api.routers.estoque import MovimentoIn, _criar_movimento_estoque
from fazenda.api.routers.financeiro import ItemIn, LancamentoIn, ParcelaIn, criar_lancamento
from fazenda.api.routers.producao import (
    ControlesIn, OrdenhaIn, PesagensIn, PesoIn, QualidadeLeiteIn, _gravar_controles, criar_pesagens, criar_qualidade_leite,
)
from fazenda.auth import get_current_user, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal, ContaGerencial, CurvaABC, Dieta, Estoque,
    Fornecedor, LancamentoItem, Parto, Sanidade, Usuario,
)
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
async def importar_qualidade_leite(
    file: UploadFile, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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
        # BUG DE SEGURANÇA CORRIGIDO: `criar_qualidade_leite` é rota FastAPI
        # (`user`/`fazenda_id` são `Depends(...)`); chamada POSICIONALMENTE,
        # como estava aqui, esses dois parâmetros ficavam com o próprio objeto
        # `Depends(...)` e `_usuario_id_seguro`/`fazenda_id_seguro` os
        # convertiam para None — toda coleta importada nascia órfã, sem dono e
        # sem autor. Registro sem fazenda_id aparece em TODA consulta do
        # padrão tolerante do sistema, ou seja, dentro de todas as fazendas.
        # Mesmo bug (e mesma correção por keyword) de `importar_pesagem`.
        criar_qualidade_leite(dados, session=session, user=user, fazenda_id=fazenda_id)
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


# ── CATÁLOGO DE TOUROS NAAB: SAIU DAQUI (furo de segurança, set/2026) ──────
# `POST /importar/touros_naab` (e a categoria "touros_naab" do catálogo de
# modelos acima) viviam aqui e agora vivem em
# fazenda/api/routers/painel_cowdata_touros.py::importar_touros_naab_painel,
# sob a permissão "editar touros NAAB" do cadastro de equipe do Painel
# CowData.
#
# O QUE ESTAVA ERRADO. `Touro` é catálogo GLOBAL (sem `fazenda_id`, uma
# tabela só lida por todas as fazendas-cliente), mas esta rota era protegida
# apenas por `exigir_modulo("upload")` — a mesma trava dos importadores de
# dado da PRÓPRIA fazenda, onde ela é suficiente. Na prática, qualquer
# fazenda-cliente com o módulo Upload subia uma planilha e reescrevia por
# upsert (nome, provas, TPI/NM$, rodada) o catálogo que todas as outras
# consultam. Mesmo furo, e mesma correção, das rotas de
# POST/PUT/DELETE /cadastro/touros — ver cadastro/genetica.py.
#
# A LEITURA da fazenda não mudou: `GET /cadastro/touros` continua igual.


@router.post("/backfill")
def backfill_fornecedores_e_estoque(
    session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Varre os dados já lançados (financeiro, curva ABC, dieta, aplicações de
    sanidade curativa) e
    cadastra automaticamente os fornecedores e itens de estoque citados neles
    que ainda não existem — idempotente, seguro de rodar quantas vezes quiser.
    Não sobrescreve nada que já existe, só preenche o que falta.
    """
    # Os filtros abaixo são INCONDICIONAIS de propósito. O padrão tolerante
    # (`if fazenda_id is not None: query = query.where(...)`) não restringe
    # quando fazenda_id é None — ele DESLIGA o isolamento, e aqui isso
    # significa a fazenda 2 varrer os lançamentos/dietas/aplicações da
    # fazenda 1 e materializar os nomes de produto dela como cadastro de
    # estoque dentro da 2. `get_fazenda_id_escrita` só devolve None em
    # ambiente sem multi-fazenda provisionado (tabela `fazenda` vazia — ver
    # `resolver_fazenda_id_escrita`), e aí `== None` vira `IS NULL`, que é
    # exatamente o conjunto de linhas desse ambiente.
    fornecedor_query = select(Fornecedor.nome).where(Fornecedor.fazenda_id == fazenda_id)
    conta_query = select(ContaGerencial.fornecedor_cliente).where(ContaGerencial.fazenda_id == fazenda_id)
    fornecedores_existentes = set(session.exec(fornecedor_query).all())
    nomes_conta = {c.strip() for c in session.exec(conta_query).all() if c and c.strip()}
    fornecedores_criados = []
    for nome in sorted(nomes_conta - fornecedores_existentes):
        f = Fornecedor(nome=nome, tipo="fornecedor", fazenda_id=fazenda_id)
        session.add(f)
        fornecedores_criados.append(nome)

    estoque_query = select(Estoque.nome).where(Estoque.fazenda_id == fazenda_id)
    curva_query = select(CurvaABC.produto).where(CurvaABC.fazenda_id == fazenda_id)
    # NÃO aplicar sem_itens_de_vale aqui — são candidatos a cadastro de
    # estoque a partir de nomes de produto já usados; excluir os itens de
    # vale só empobreceria a lista de sugestões (ver rules/vale_item.py).
    lancamento_query = select(LancamentoItem.produto).where(LancamentoItem.fazenda_id == fazenda_id)
    sanidade_query = select(Sanidade.produto).where(Sanidade.fazenda_id == fazenda_id)
    # BUG DE SEGURANÇA CORRIGIDO: esta era a ÚNICA das quatro fontes lida sem
    # nenhum filtro de fazenda — o ingrediente da dieta da fazenda 1 (que pode
    # ser a fórmula/produto que ela não quer expor) virava item de estoque
    # cadastrado dentro da fazenda 2, só por rodar o backfill.
    dieta_query = select(Dieta.ingrediente).where(Dieta.fazenda_id == fazenda_id)
    estoque_existente = set(session.exec(estoque_query).all())
    candidatos_estoque: set[str] = set()
    for produto in session.exec(curva_query).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for produto in session.exec(lancamento_query).all():
        if produto and produto.strip():
            candidatos_estoque.add(produto.strip())
    for ingrediente in session.exec(dieta_query).all():
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
