"""
Ferramentas de leitura COM PARÂMETROS do Assistente do site e do agente /agente
(fazenda/rules/assistente_consultas.py).

Para cada ferramenta nova:
- contrato (nome, schema, descrição em português, módulo, sem 'limite'/'offset'
  no schema — a ponte MCP já os acrescenta);
- somente leitura (TODA execução aqui roda na sessão read-only de /agente:
  qualquer escrita estoura);
- isolamento por fazenda (a "fazenda 2" tem linhas marcadas SEGREDO);
- permissão de módulo;
- sanitização na saída HTTP;
- validação de parâmetros (data inválida, período invertido, > 5 anos);
- CONSISTÊNCIA com o número que o site/endpoint equivalente devolve.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import MODULOS
from fazenda.models import (
    Animal, CalendarioSanitario, ContaGerencial, ControleLeiteiro, Cotacao, CotacaoFornecedor, CotacaoItem,
    CotacaoResposta, CronogramaSanitario, CronogramaSanitarioAnimal, Estoque, EventoSanitario, Fazenda, Fornecedor,
    LoteEstoque, Parto, Pedido, PedidoItem, ProtocoloCustomizado, ProtocoloCustomizadoEtapa, ProtocoloIatf,
    ProtocoloIatfAplicacao, ProtocoloIatfEtapa, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa, ProtocoloSanitario, ProtocoloSanitarioAplicacao,
    ProtocoloSanitarioEtapa, ProtocoloSanitarioLancamento, ProtocoloSanitarioLote, Sanidade, Secagem, Servico,
)
from fazenda.rules import agente_leitura as al
from fazenda.rules import assistente_consultas as ac
from fazenda.rules.assistente import _TOOLS_DISPONIVEIS, _executar_tool, _ferramentas_do_usuario
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()
TOKEN = "t" * 20 + "-token-de-teste-do-agente-" + "x" * 10
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PERIODO = {"data_inicio": "2026-01-01", "data_fim": "2026-07-01"}


class _Usuario:
    def __init__(self, papel="admin", permissoes=""):
        self.id, self.papel, self.permissoes = 1, papel, permissoes


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for v in ("AGENTE_API_TOKEN", "AGENTE_FAZENDA_ID", "AGENTE_IPS_PERMITIDOS", "AGENTE_RATE_LIMIT_POR_MIN",
              "AGENTE_MAX_BYTES", "AGENTE_MODULOS"):
        monkeypatch.delenv(v, raising=False)
    al._resetar_estado_para_testes()


def _serv(numero, data, diag, touro="TouroA", fid=1, perda=None, protocolo=None):
    return Servico(
        numero_matriz=numero, data_servico=data, tipo_servico="Inseminação", reprodutor=touro, diagnostico=diag,
        fazenda_id=fid, data_perda_prenhez=perda, protocolo=protocolo, ordem_parto=1, ordem_tentativa=1,
        inseminador="Joao" if fid == 1 else "SEGREDO",
    )


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        s.commit()
        for num, nome, fid in (("500", "Estrela", 1), ("501", "Mimosa", 1), ("900", "SEGREDO", 2)):
            s.add(Animal(numero=num, nome=nome, sexo="F", fazenda_id=fid, grupo_primario="04 - SECAS", ativo=True))
        # --- reprodução ---
        s.add_all([
            _serv("500", date(2026, 1, 10), "POSITIVO", protocolo="P1"),
            _serv("501", date(2026, 2, 10), "NEGATIVO"),
            _serv("500", date(2026, 3, 10), "POSITIVO", touro="TouroB", perda=date(2026, 5, 1)),
            _serv("501", date(2026, 4, 10), None, touro="TouroB"),
            _serv("500", date(2025, 11, 10), "POSITIVO"),  # fora do período
            _serv("900", date(2026, 2, 2), "POSITIVO", touro="TouroSEGREDO", fid=2),
        ])
        s.add(Parto(numero_matriz="500", data_parto=date(2026, 3, 1), tipo_parto="normal", ordem_parto=1, fazenda_id=1))
        s.add(Parto(numero_matriz="900", data_parto=date(2026, 3, 1), tipo_parto="SEGREDO", fazenda_id=2))
        s.add(Secagem(numero_matriz="501", data_secagem=date(2026, 5, 1), motivo="rotina", fazenda_id=1))
        s.add(Secagem(numero_matriz="900", data_secagem=date(2026, 5, 1), motivo="SEGREDO", fazenda_id=2))
        # --- leite ---
        for num, d, kg, fid in (("500", date(2026, 3, 2), 30.0, 1), ("501", date(2026, 3, 2), 20.0, 1),
                                ("500", date(2026, 4, 1), 28.0, 1), ("900", date(2026, 3, 2), 99.0, 2)):
            s.add(ControleLeiteiro(numero_matriz=num, data_controle=d, producao_kg=kg, fazenda_id=fid))
        # --- sanidade ---
        s.add(Sanidade(numero_matriz="500", data_aplicacao=date(2026, 2, 1), produto="Ivermectina", fazenda_id=1, natureza="curativo"))
        s.add(Sanidade(numero_matriz="501", data_aplicacao=date(2026, 3, 1), produto="Lactotropin", atividade="BST", fazenda_id=1))
        s.add(Sanidade(numero_matriz="500", data_aplicacao=date(2026, 4, 1), produto="Boostin", atividade="BST", fazenda_id=1,
                       obs="avisar fulano@exemplo.com CPF 123.456.789-09"))
        s.add(Sanidade(numero_matriz="900", data_aplicacao=date(2026, 3, 1), produto="Lactotropin SEGREDO", atividade="BST", fazenda_id=2))
        # --- financeiro ---
        for desc, tipo, total, pago, venc, pgto, cat, fid in (
            ("Vacina aftosa", "despesa", 100.0, 0.0, HOJE + timedelta(days=3), None, "Medicamentos", 1),
            ("Racao atrasada", "despesa", 50.0, 0.0, HOJE - timedelta(days=5), None, "Alimentação", 1),
            ("Despesa distante", "despesa", 80.0, 0.0, HOJE + timedelta(days=20), None, "Medicamentos", 1),
            ("Venda de leite", "receita", 200.0, 0.0, HOJE + timedelta(days=1), None, "Leite", 1),
            ("Conta paga", "despesa", 60.0, 60.0, HOJE - timedelta(days=9), HOJE - timedelta(days=2), "Medicamentos", 1),
            ("Conta SEGREDO", "despesa", 999.0, 0.0, HOJE + timedelta(days=2), None, "SEGREDO", 2),
        ):
            s.add(ContaGerencial(descricao=desc, tipo=tipo, valor_total=total, valor_pago=pago, data_vencimento=venc,
                                 data_pagamento=pgto, data_competencia=venc, classificacao=cat, fazenda_id=fid,
                                 fornecedor_cliente="Agrovet" if fid == 1 else "SEGREDO"))
        # --- estoque ---
        s.add(Fornecedor(nome="Agrovet", tipo="fornecedor", fazenda_id=1))
        iver = Estoque(nome="Ivermectina", categoria="Medicamento", finalidade="Medicamento", quantidade=5, estoque_minimo=10,
                       abaixo_minimo=True, unidade="frasco", valor_total=250.0, fazenda_id=1)
        s.add(iver)
        s.add(Estoque(nome="Ração X", quantidade=100, estoque_minimo=10, abaixo_minimo=False, valor_total=1000.0, fazenda_id=1))
        s.add(Estoque(nome="Item Inativo", quantidade=1, estoque_minimo=10, abaixo_minimo=True, ativo=False, fazenda_id=1))
        s.add(Estoque(nome="Ração SEGREDO", quantidade=1, estoque_minimo=10, abaixo_minimo=True, fazenda_id=2))
        s.commit()
        s.add(LoteEstoque(estoque_id=iver.id, numero_lote="L1", data_compra=HOJE - timedelta(days=100), quantidade_comprada=5,
                          quantidade_restante=5, validade=HOJE + timedelta(days=30), fazenda_id=1))
        # --- pedidos / cotações ---
        for numero, status, forn, fid in (("PED-1", "aberto", "Agrovet", 1), ("PED-2", "atendido", "Outro", 1),
                                           ("PED-S", "aberto", "SEGREDO", 2)):
            p = Pedido(numero_pedido=numero, tipo="compra", status=status, fornecedor_cliente=forn,
                       data_pedido=HOJE - timedelta(days=3), fazenda_id=fid)
            s.add(p)
            s.commit()
            s.add(PedidoItem(pedido_id=p.id, tipo_item="produto", produto_servico="Vacina" if fid == 1 else "SEGREDO",
                             valor_total_estimado=300.0, quantidade=3, fazenda_id=fid))
        for numero, fid in (("COT-1", 1), ("COT-S", 2)):
            c = Cotacao(numero_cotacao=numero, categoria="Medicamentos", prazo_resposta=datetime.utcnow() + timedelta(days=3),
                        status="enviada", fazenda_id=fid)
            s.add(c)
            s.commit()
            item = CotacaoItem(cotacao_id=c.id, produto="Vacina" if fid == 1 else "SEGREDO", quantidade=10, fazenda_id=fid)
            f = Fornecedor(nome="Agrovet" if fid == 1 else "FornSEGREDO", tipo="fornecedor", fazenda_id=fid)
            s.add_all([item, f])
            s.commit()
            cf = CotacaoFornecedor(cotacao_id=c.id, fornecedor_id=f.id, token_publico=f"token-publico-secreto-{fid}",
                                   status_envio="respondido", fazenda_id=fid)
            s.add(cf)
            s.commit()
            s.add(CotacaoResposta(cotacao_fornecedor_id=cf.id, cotacao_item_id=item.id, preco_unitario=12.5, fazenda_id=fid))
        # --- sanidade preventiva ---
        for nome, fid in (("Aftosa", 1), ("Regra SEGREDO", 2)):
            ev = EventoSanitario(nome=nome, categoria_preventiva="vacina", produto_padrao=nome, fazenda_id=fid)
            s.add(ev)
            s.commit()
            cal = CalendarioSanitario(evento_sanitario_id=ev.id, frequencia_valor=6, frequencia_unidade="meses",
                                      data_evento=HOJE - timedelta(days=10), produto=nome, usa_cronograma=True, fazenda_id=fid)
            s.add(cal)
            s.commit()
            cron = CronogramaSanitario(calendario_sanitario_id=cal.id, data_evento=HOJE - timedelta(days=10), status="aberto", fazenda_id=fid)
            s.add(cron)
            s.commit()
            nums = ("500", "501") if fid == 1 else ("900",)
            for n in nums:
                s.add(CronogramaSanitarioAnimal(cronograma_id=cron.id, numero_matriz=n, status="sugerido",
                                                data_sugestao=HOJE - timedelta(days=10), fazenda_id=fid))
            if fid == 1:  # 501 JÁ recebeu Aftosa no ciclo: sai da lista de espera (a reconciliação do site gravaria isso)
                s.add(Sanidade(numero_matriz="501", data_aplicacao=HOJE - timedelta(days=3), produto="Aftosa", fazenda_id=1))
        # --- protocolos cadastrados ---
        for nome, fin, fid in (("Mastite A", "curativo", 1), ("Vermifugo Preventivo", "preventivo", 1), ("Prot SEGREDO", "curativo", 2)):
            p = ProtocoloSanitario(nome=nome, finalidade=fin, fazenda_id=fid)
            s.add(p)
            s.commit()
            s.add(ProtocoloSanitarioEtapa(protocolo_id=p.id, dia=1, produto="Ceftiofur", dosagem=5, unidade="ml", fazenda_id=fid))
        for nome, fid in (("IATF D0-D9", 1), ("IATF SEGREDO", 2)):
            p = ProtocoloIatf(nome=nome, fazenda_id=fid)
            s.add(p)
            s.commit()
            s.add(ProtocoloIatfEtapa(protocolo_id=p.id, dia=0, produto="Benzoato", fazenda_id=fid))
        p = ProtocoloInducaoLactacao(nome="Inducao Padrao", fazenda_id=1)
        s.add(p)
        s.commit()
        s.add(ProtocoloInducaoLactacaoEtapa(protocolo_id=p.id, dia=0, produto="Estradiol", fazenda_id=1))
        p = ProtocoloCustomizado(nome="Meu Proprio", tipo="reprodutivo", fazenda_id=1)
        s.add(p)
        s.commit()
        s.add(ProtocoloCustomizadoEtapa(protocolo_id=p.id, dia=0, descricao_evento="Pesar", fazenda_id=1))
        # --- protocolos lançados (IATF em andamento, concluído, cancelado; sanitário) ---
        for nome, ativo, feitas, fid in (("IATF em andamento", True, False, 1), ("IATF concluido", True, True, 1),
                                         ("IATF cancelado", False, False, 1), ("IATF SEGREDO", True, False, 2)):
            l = ProtocoloIatfLancamento(nome_protocolo=nome, data_d0=HOJE - timedelta(days=2), ativo=ativo, fazenda_id=fid)
            s.add(l)
            s.commit()
            for dia in (0, 9):
                s.add(ProtocoloIatfAplicacao(lancamento_id=l.id, numero_matriz="500" if fid == 1 else "900", dia=dia, descricao=f"D{dia}",
                                             data_prevista=HOJE - timedelta(days=2) + timedelta(days=dia), realizada=feitas, fazenda_id=fid))
            s.add(ProtocoloIatfHormonio(lancamento_id=l.id, dia=0, produto="Benzoato de estradiol", dose=2, unidade="ml", fazenda_id=fid))
        molde = s.exec(select(ProtocoloSanitario).where(ProtocoloSanitario.nome == "Mastite A")).first()
        etapa = s.exec(select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == molde.id)).first()
        lote = ProtocoloSanitarioLote(protocolo_id=molde.id, nome_protocolo="Mastite lote", data_inicio=HOJE - timedelta(days=1),
                                      ativo=False, fazenda_id=1)  # cancelado
        s.add(lote)
        s.commit()
        lanc = ProtocoloSanitarioLancamento(protocolo_id=molde.id, numero_matriz="500", data_inicio=HOJE - timedelta(days=1),
                                            lote_id=lote.id, fazenda_id=1)
        s.add(lanc)
        s.commit()
        s.add(ProtocoloSanitarioAplicacao(lancamento_id=lanc.id, etapa_id=etapa.id, data_prevista=HOJE, dia=1, numero_matriz="500", fazenda_id=1))
        s.commit()
    return eng


def _rodar(engine, nome, entrada=None, fid=1, usuario=None):
    """Executa a ferramenta como o /agente: sessão SOMENTE LEITURA + contexto de fazenda."""
    with Session(engine) as s:
        gen = al.sessao_somente_leitura(s)
        next(gen)
        marca = fazenda_atual.set(fid)
        try:
            return _executar_tool(nome, dict(entrada or {}), s, usuario or _Usuario(), fid)
        finally:
            fazenda_atual.reset(marca)
            gen.close()


NOVAS = sorted(ac.NOMES)

# Parâmetros "típicos" para exercitar cada ferramenta de ponta a ponta.
TIPICOS = {
    "consultar_indicadores_reprodutivos": PERIODO,
    "consultar_ciclos_21_dias": {},
    "consultar_servicos_reprodutivos": PERIODO,
    "consultar_partos_secagens": PERIODO,
    "listar_relatorios": {},
    "executar_relatorio": {"relatorio": "fluxo_lactacao", "meses": "3"},
    "consultar_protocolos_lancados": {},
    "consultar_bst": PERIODO,
    "consultar_protocolos_cadastrados": {},
    "consultar_regras_preventivo": {},
    "consultar_lista_espera_preventivo": {},
    "consultar_agendamentos_preventivo": {"situacao": "todos"},
    "consultar_aplicacoes_sanitarias": PERIODO,
    "consultar_pedidos": {},
    "consultar_cotacoes": {},
    "consultar_contas_financeiras": {"situacao": "aberta"},
    "consultar_estoque_itens": {"incluir_lotes": "true"},
    "consultar_producao_leite": PERIODO,
}


def test_todas_as_ferramentas_novas_tem_parametros_tipicos():
    assert set(TIPICOS) == set(NOVAS)


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------
class TestContrato:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_spec(self, nome):
        t = next(t for t in _TOOLS_DISPONIVEIS if t["spec"]["name"] == nome)
        spec = t["spec"]
        assert spec["name"] == nome and len(spec["description"]) > 120
        esquema = spec["input_schema"]
        assert esquema["type"] == "object" and esquema["additionalProperties"] is False
        # a ponte MCP acrescenta limite/offset sozinha: repetir quebraria a assinatura
        assert "limite" not in esquema["properties"] and "offset" not in esquema["properties"]
        assert set(esquema.get("required", [])) <= set(esquema["properties"])
        for k, v in esquema["properties"].items():
            assert v["type"] in ("string", "integer", "boolean") and v["description"], k
            if k.startswith("data_") or k == "ancora":
                assert "AAAA-MM-DD" in v["description"], k
        modulos = (t["modulo"],) if isinstance(t["modulo"], str) else t["modulo"]
        assert modulos and set(modulos) <= set(MODULOS)

    def test_descricoes_em_portugues_com_exemplo(self):
        for t in _TOOLS_DISPONIVEIS:
            if t["spec"]["name"] in ac.NOMES:
                assert "Use para" in t["spec"]["description"] or "Use primeiro" in t["spec"]["description"], t["spec"]["name"]

    def test_nomes_unicos(self):
        nomes = [t["spec"]["name"] for t in _TOOLS_DISPONIVEIS]
        assert len(nomes) == len(set(nomes))

    def test_modulo_do_agente_aceita_tupla(self):
        from fazenda.rules.assistente import modulo_na_lista
        assert modulo_na_lista(("reproducao", "analise"), {"analise"}) and not modulo_na_lista(("reproducao", "analise"), {"estoque"})
        assert modulo_na_lista("estoque", {"estoque"})

    def test_modulo_fonte_nao_escreve(self):
        import inspect
        fonte = inspect.getsource(ac)
        for proibido in ("session.add(", "session.commit(", "session.flush(", "session.delete(", ".post(", "reconciliar=True"):
            assert proibido not in fonte, proibido


# ---------------------------------------------------------------------------
# Somente leitura + execução + isolamento
# ---------------------------------------------------------------------------
class TestExecucaoSomenteLeitura:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_executa_na_sessao_read_only(self, engine, nome):
        r = _rodar(engine, nome, TIPICOS[nome])
        assert isinstance(r, dict) and "erro" not in r, (nome, r)

    @pytest.mark.parametrize("nome", NOVAS)
    def test_nao_vaza_outra_fazenda(self, engine, nome):
        texto = json.dumps(_rodar(engine, nome, TIPICOS[nome]), default=str, ensure_ascii=False)
        assert "SEGREDO" not in texto and "secreto-2" not in texto, nome

    def test_fazenda_2_ve_so_o_dela(self, engine):
        r = _rodar(engine, "consultar_servicos_reprodutivos", PERIODO, fid=2)
        assert r["total"] == 1 and r["servicos"][0]["touro"] == "TouroSEGREDO"
        r = _rodar(engine, "consultar_contas_financeiras", {"situacao": "aberta"}, fid=2)
        assert r["total_lancamentos"] == 1 and r["a_pagar"]["valor_total"] == 999.0

    def test_lista_de_espera_nao_grava_a_reconciliacao(self, engine):
        """O endpoint do site reconcilia e ESCREVE; a ferramenta tem de devolver a mesma lista sem escrever."""
        def _estado():
            with Session(engine) as s:
                return [(l.numero_matriz, l.status, l.motivo) for l in s.exec(select(CronogramaSanitarioAnimal).order_by(CronogramaSanitarioAnimal.id)).all()]
        antes = _estado()
        r = _rodar(engine, "consultar_lista_espera_preventivo", {})
        assert _estado() == antes
        assert {a["numero_matriz"] for g in r["grupos"] for a in g["animais"]} == {"500"}  # 501 já aplicou
        # o endpoint do site chega ao MESMO resultado depois de reconciliar (e aí sim grava)
        from fazenda.rules.cronograma_sanitario import lista_espera
        with Session(engine) as s:
            site = lista_espera(s, HOJE, 1, None)
        assert {a["numero_matriz"] for g in site["grupos"] for a in g["animais"]} == {"500"}
        assert r["total"] == site["total"] and r["atrasadas"] == site["atrasadas"]
        assert _estado() != antes  # prova de que o caminho do site realmente escreve


# ---------------------------------------------------------------------------
# Permissão de módulo
# ---------------------------------------------------------------------------
class TestPermissao:
    def test_operador_so_ve_o_que_o_modulo_libera(self):
        nomes = lambda perm: {t["name"] for t in _ferramentas_do_usuario(_Usuario("operador", perm))}  # noqa: E731
        assert "consultar_contas_financeiras" in nomes("financeiro") and "consultar_estoque_itens" not in nomes("financeiro")
        assert "consultar_estoque_itens" in nomes("estoque") and "consultar_contas_financeiras" not in nomes("estoque")
        assert {"consultar_pedidos", "consultar_cotacoes"} <= nomes("pedidos")
        assert "consultar_producao_leite" in nomes("producao") and "consultar_bst" in nomes("producao")
        assert "consultar_indicadores_reprodutivos" in nomes("analise") and "consultar_indicadores_reprodutivos" in nomes("reproducao")
        assert "consultar_lista_espera_preventivo" in nomes("sanidade") and "consultar_lista_espera_preventivo" not in nomes("pedidos")
        assert nomes("") == set()
        assert len(nomes("") | nomes("rebanho")) == len(nomes("rebanho"))

    @pytest.mark.parametrize("nome", NOVAS)
    def test_executar_sem_modulo_e_barrado(self, engine, nome):
        r = _rodar(engine, nome, TIPICOS[nome], usuario=_Usuario("operador", ""))
        assert "erro" in r and "permissão" in r["erro"]

    def test_relatorio_exige_o_modulo_do_proprio_relatorio(self, engine):
        u = _Usuario("operador", "reproducao")
        r = _rodar(engine, "executar_relatorio", {"relatorio": "dre", **PERIODO}, usuario=u)
        assert "erro" in r and "financeiro" in r["erro"]
        catalogo = {x["relatorio"] for x in _rodar(engine, "listar_relatorios", {}, usuario=u)["relatorios"]}
        assert "fluxo_lactacao" in catalogo and "dre" not in catalogo
        r = _rodar(engine, "executar_relatorio", {"relatorio": "fluxo_lactacao", "meses": "2"}, usuario=u)
        assert "erro" not in r

    def test_agente_respeita_agente_modulos(self, engine, monkeypatch):
        import main
        import fazenda.database as database

        def _sess():
            with Session(engine) as s:
                yield s
        monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
        monkeypatch.setenv("AGENTE_MODULOS", "estoque")
        main.app.dependency_overrides[database.get_session] = _sess
        try:
            with TestClient(main.app) as c:
                nomes = {f["nome"] for f in c.get("/agente/ferramentas", headers=AUTH).json()["ferramentas"]}
                assert "consultar_estoque_itens" in nomes and "consultar_contas_financeiras" not in nomes
                assert c.get("/agente/consultar/consultar_contas_financeiras", headers=AUTH).status_code == 404
        finally:
            main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Validação de parâmetros
# ---------------------------------------------------------------------------
class TestValidacao:
    COM_PERIODO_OBRIGATORIO = ("consultar_indicadores_reprodutivos", "consultar_producao_leite")

    @pytest.mark.parametrize("nome", COM_PERIODO_OBRIGATORIO)
    def test_periodo_obrigatorio(self, engine, nome):
        r = _rodar(engine, nome, {"data_inicio": "2026-01-01"})
        assert "data_fim" in r["erro"] and "pergunte" in r["erro"].lower()
        assert "erro" in _rodar(engine, nome, {})

    @pytest.mark.parametrize("nome", NOVAS)
    def test_data_invalida(self, engine, nome):
        spec = next(t["spec"] for t in _TOOLS_DISPONIVEIS if t["spec"]["name"] == nome)
        if "data_inicio" not in spec["input_schema"]["properties"]:
            pytest.skip("sem parâmetro de data")
        entrada = {**TIPICOS[nome], "data_inicio": "2026-02-30", "data_fim": "2026-07-01"}
        r = _rodar(engine, nome, entrada)
        assert "Data inválida" in r["erro"] and "AAAA-MM-DD" in r["erro"], (nome, r)

    @pytest.mark.parametrize("nome", NOVAS)
    def test_periodo_invertido_e_maior_que_5_anos(self, engine, nome):
        spec = next(t["spec"] for t in _TOOLS_DISPONIVEIS if t["spec"]["name"] == nome)
        if "data_inicio" not in spec["input_schema"]["properties"]:
            pytest.skip("sem parâmetro de data")
        r = _rodar(engine, nome, {**TIPICOS[nome], "data_inicio": "2026-07-01", "data_fim": "2026-01-01"})
        assert "invertido" in r["erro"], (nome, r)
        r = _rodar(engine, nome, {**TIPICOS[nome], "data_inicio": "2019-01-01", "data_fim": "2026-01-01"})
        assert "5 anos" in r["erro"], (nome, r)

    def test_data_brasileira_e_aceita(self, engine):
        a = _rodar(engine, "consultar_indicadores_reprodutivos", {"data_inicio": "01/01/2026", "data_fim": "01/07/2026"})
        b = _rodar(engine, "consultar_indicadores_reprodutivos", PERIODO)
        assert a == b

    def test_valores_fora_da_lista(self, engine):
        r = _rodar(engine, "consultar_contas_financeiras", {"situacao": "talvez", **PERIODO})
        assert "situacao" in r["erro"] and "aberta" in r["erro"]
        assert "erro" in _rodar(engine, "consultar_pedidos", {"status": "inventado"})
        assert "n_ciclos" in _rodar(engine, "consultar_ciclos_21_dias", {"n_ciclos": "99"})["erro"]
        assert "inteiro" in _rodar(engine, "consultar_ciclos_21_dias", {"n_ciclos": "abc"})["erro"]

    def test_contas_pagas_sem_periodo_pede_periodo(self, engine):
        assert "período" in _rodar(engine, "consultar_contas_financeiras", {})["erro"]

    def test_aplicacoes_sem_nenhum_filtro(self, engine):
        assert "ao menos um filtro" in _rodar(engine, "consultar_aplicacoes_sanitarias", {})["erro"]

    def test_relatorio_desconhecido_e_parametros(self, engine):
        assert "desconhecido" in _rodar(engine, "executar_relatorio", {"relatorio": "xyz"})["erro"]
        assert "Informe" in _rodar(engine, "executar_relatorio", {"relatorio": "dre"})["erro"]
        assert "Parâmetro(s) desconhecido(s)" in _rodar(engine, "executar_relatorio", {"relatorio": "fluxo_lactacao", "gta": "1"})["erro"]
        assert "erro" in _rodar(engine, "executar_relatorio", {})


# ---------------------------------------------------------------------------
# (a) Consistência: reprodução por período e relatórios
# ---------------------------------------------------------------------------
class TestReproducao:
    def test_taxa_de_concepcao_do_periodo_bate_com_a_tela(self, engine):
        r = _rodar(engine, "consultar_indicadores_reprodutivos", PERIODO)
        # período 01/01–01/07/2026: 4 serviços, 3 diagnosticados (2 positivos, 1 negativo), 1 pendente
        assert (r["servicos_total"], r["diagnosticados"], r["positivos"], r["negativos"], r["sem_diagnostico"]) == (4, 3, 2, 1, 1)
        assert r["taxa_concepcao_pct"] == 66.7 and r["perdas_prenhez"] == 1
        assert r["partos_no_periodo"]["total"] == 1 and r["secagens_no_periodo"]["total"] == 1

    def test_mesma_conta_do_navegador(self, engine):
        """Reconstrói a conta de frontend/app/analise-reprodutiva/page.tsx (taxa(): positivos/diagnosticados,
        Math.round(1000*x)/10) direto do endpoint /reproducao/servicos — oráculo independente da ferramenta."""
        from fazenda.api.routers.reproducao import listar_servicos_analise
        with Session(engine) as s:
            regs = listar_servicos_analise(session=s, fazenda_id=1)["servicos"]
        for ini, fim, filtro in (("2026-01-01", "2026-07-01", None), ("2026-01-01", "2026-02-28", None),
                                 ("2025-01-01", "2026-12-31", ("touro", "TouroB")), ("2026-01-01", "2026-07-01", ("metodo_ia", "IATF"))):
            sel = [r for r in regs if ini <= (r["data"] or "") <= fim and (not filtro or str(r[filtro[0]]) == filtro[1])]
            diag = sum(1 for r in sel if r["diagnosticado"])
            pos = sum(1 for r in sel if r["positivo"])
            esperado = None if not diag else int(1000 * pos / diag + 0.5) / 10
            entrada = {"data_inicio": ini, "data_fim": fim, **({filtro[0]: filtro[1]} if filtro else {})}
            r = _rodar(engine, "consultar_indicadores_reprodutivos", entrada)
            assert r["taxa_concepcao_pct"] == esperado, entrada
            assert (r["diagnosticados"], r["positivos"], r["servicos_total"]) == (diag, pos, len(sel))

    def test_arredondamento_igual_ao_math_round_do_javascript(self):
        from fazenda.rules.reproducao_analise import resumo_periodo
        regs = [{"diagnosticado": True, "positivo": i == 0, "perda": False} for i in range(16)]  # 1/16 = 6.25%
        assert resumo_periodo(regs)["taxa_concepcao_pct"] == 6.3  # round() do Python daria 6.2
        assert resumo_periodo([])["taxa_concepcao_pct"] is None

    def test_quebra_por_touro(self, engine):
        r = _rodar(engine, "consultar_indicadores_reprodutivos", {**PERIODO, "agrupar_por": "touro"})
        por = {q["grupo"]: q for q in r["quebra"]}
        assert por["TouroA"]["taxa_concepcao_pct"] == 50.0 and por["TouroB"]["taxa_concepcao_pct"] == 100.0
        assert "erro" in _rodar(engine, "consultar_indicadores_reprodutivos", {**PERIODO, "agrupar_por": "cor"})

    def test_serie_mensal_e_a_do_endpoint_do_grafico(self, engine):
        from fazenda.api.routers.reproducao import indicadores_mensais_analise
        with Session(engine) as s:
            site = indicadores_mensais_analise(session=s, fazenda_id=1, ini="2026-01-01", fim="2026-07-01", tipo_servico=None,
                                               metodo_ia=None, touro=None, inseminador=None, ordem_parto=None, ordem_tentativa=None)
        r = _rodar(engine, "consultar_indicadores_reprodutivos", PERIODO)
        assert [m["mes"] for m in r["serie_mensal_criterio_r7"]] == site["meses"]
        assert [m["taxa_concepcao"] for m in r["serie_mensal_criterio_r7"]] == site["series"]["taxa_concepcao"]
        assert [m["num_servicos"] for m in r["serie_mensal_criterio_r7"]] == site["series"]["num_servicos"]

    def test_ciclos_21_dias_igual_ao_endpoint(self, engine):
        from fazenda.api.routers.reproducao import ciclos_de_21_dias
        fazenda_atual.set(1)
        with Session(engine) as s:
            site = ciclos_de_21_dias(ancora=date(2026, 7, 1), modo="fim", n_ciclos=9, categoria="todas", session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_ciclos_21_dias", PERIODO)  # 181 dias -> 9 ciclos terminando em 01/07
        assert r["resumo"] == site["resumo"] and r["periodo"] == site["periodo"]
        assert [{k: v for k, v in c.items() if k != "animais"} for c in site["ciclos"]] == r["ciclos"]
        assert all("animais" not in c for c in r["ciclos"])
        r2 = _rodar(engine, "consultar_ciclos_21_dias", {"ancora": "2026-07-01", "n_ciclos": "9"})
        assert r2["resumo"] == site["resumo"]

    def test_servicos_filtros(self, engine):
        todos = _rodar(engine, "consultar_servicos_reprodutivos", PERIODO)
        assert todos["total"] == 4 and todos["positivos"] == 2 and todos["perdas"] == 1
        assert [s["data"] for s in todos["servicos"]] == sorted((s["data"] for s in todos["servicos"]), reverse=True)
        assert _rodar(engine, "consultar_servicos_reprodutivos", {**PERIODO, "touro": "touroa"})["total"] == 2
        assert _rodar(engine, "consultar_servicos_reprodutivos", {**PERIODO, "diagnostico": "pendente"})["total"] == 1
        assert _rodar(engine, "consultar_servicos_reprodutivos", {**PERIODO, "apenas_perdas": "true"})["total"] == 1
        assert _rodar(engine, "consultar_servicos_reprodutivos", {"numero": "500"})["total"] == 3  # sem período: histórico do animal
        padrao = _rodar(engine, "consultar_servicos_reprodutivos", {})
        assert padrao["periodo"]["padrao_ultimos_90_dias"] is True

    def test_partos_e_secagens_batem_com_os_endpoints(self, engine):
        from fazenda.api.routers.reproducao import listar_partos_historico, listar_secagens_historico
        with Session(engine) as s:
            partos = listar_partos_historico(session=s, fazenda_id=1)["total"]
            secagens = listar_secagens_historico(session=s, fazenda_id=1)["total"]
        r = _rodar(engine, "consultar_partos_secagens", {"data_inicio": "2022-01-01", "data_fim": "2026-12-31"})
        assert (r["total_partos"], r["total_secagens"]) == (partos, secagens) == (1, 1)
        assert "partos" not in _rodar(engine, "consultar_partos_secagens", {**PERIODO, "tipo": "secagens"})


class TestRelatorios:
    def test_catalogo(self, engine):
        r = _rodar(engine, "listar_relatorios", {})
        ids = {x["relatorio"] for x in r["relatorios"]}
        assert {"manejo", "fluxo_lactacao", "dre", "custo_litro_leite", "compra_semen", "taxa_cura", "relatorio_personalizado"} <= ids
        assert all(x["titulo"] and x["descricao"] for x in r["relatorios"])
        assert {x["relatorio"] for x in _rodar(engine, "listar_relatorios", {"busca": "custo"})["relatorios"]} >= {"custo_litro_leite", "custo_hectare"}

    def test_fluxo_lactacao_igual_ao_endpoint(self, engine):
        from fazenda.api.routers.relatorios import gerencial_fluxo_lactacao
        with Session(engine) as s:
            site = gerencial_fluxo_lactacao(meses=3, fazenda_id=1, session=s)
        r = _rodar(engine, "executar_relatorio", {"relatorio": "fluxo_lactacao", "meses": 3})
        assert r["dados"] == json.loads(json.dumps(site, default=str)) or r["dados"] == site

    def test_dre_igual_ao_endpoint(self, engine):
        from fazenda.api.routers.financeiro import dre
        with Session(engine) as s:
            site = dre(data_inicio=date(2026, 1, 1), data_fim=date(2026, 12, 31), centro_custo=None, regime="competencia", session=s, fazenda_id=1)
        r = _rodar(engine, "executar_relatorio", {"relatorio": "dre", "data_inicio": "2026-01-01", "data_fim": "2026-12-31"})
        assert r["dados"]["resultado"] == site["resultado"] and r["dados"]["receitas_total"] == site["receitas_total"]

    def test_relatorio_personalizado_igual_ao_endpoint(self, engine):
        from fazenda.api.routers.indicadores import RelatorioPersonalizadoIn, relatorio_personalizado
        with Session(engine) as s:
            site = relatorio_personalizado(RelatorioPersonalizadoIn(parametros=["numero", "numero_servicos"]), s, 1)
        r = _rodar(engine, "executar_relatorio", {"relatorio": "relatorio_personalizado", "colunas": "numero,numero_servicos"})
        assert r["dados"] == site

    def test_relatorios_que_dependem_de_parametro(self, engine):
        r = _rodar(engine, "executar_relatorio", {"relatorio": "compra_semen", **PERIODO})
        assert "erro" not in r
        r = _rodar(engine, "executar_relatorio", {"relatorio": "custo_litro_leite", **PERIODO})
        assert "erro" not in r
        assert "erro" in _rodar(engine, "executar_relatorio", {"relatorio": "acasalamento", "numero": "999"})  # animal inexistente -> 404 vira erro


# ---------------------------------------------------------------------------
# (b) protocolos lançados, BST
# ---------------------------------------------------------------------------
class TestProtocolosLancadosEBst:
    def test_status_batem_com_acompanhamento_e_historico_do_site(self, engine):
        from fazenda.api.routers.central_protocolos import acompanhamento, historico
        with Session(engine) as s:
            em_andamento = {l["nome"] for l in acompanhamento(nome=None, tipo=None, session=s, fazenda_id=1)}
            hist = {l["nome"]: l["status"] for l in historico(nome=None, tipo=None, data_de=None, data_ate=None, session=s, fazenda_id=1)}
        assert em_andamento == {"IATF em andamento"} and set(hist) >= {"IATF concluido", "IATF cancelado", "Mastite lote"}
        r = _rodar(engine, "consultar_protocolos_lancados", {"status": "andamento"})
        assert {p["nome"] for p in r["protocolos"]} == em_andamento
        for status in ("concluido", "cancelado"):
            r = _rodar(engine, "consultar_protocolos_lancados", {"status": status})
            assert {p["nome"] for p in r["protocolos"]} == {n for n, st in hist.items() if st == status}
        r = _rodar(engine, "consultar_protocolos_lancados", {})
        assert r["total"] == 4 and r["por_status"]["cancelado"] == 2  # IATF cancelado + sanitário cancelado (correção de status em Sanidade)

    def test_status_cancelado_do_sanitario(self, engine):
        r = _rodar(engine, "consultar_protocolos_lancados", {"origem": "sanitario"})
        assert [(p["nome"], p["status"]) for p in r["protocolos"]] == [("Mastite lote", "cancelado")]

    def test_filtros_nome_tipo_periodo(self, engine):
        assert _rodar(engine, "consultar_protocolos_lancados", {"nome": "concluido"})["total"] == 1
        assert _rodar(engine, "consultar_protocolos_lancados", {"tipo": "sanitario"})["total"] == 1
        r = _rodar(engine, "consultar_protocolos_lancados", {"data_inicio": "2000-01-01", "data_fim": "2000-02-01"})
        assert r["total"] == 0

    def test_detalhe_com_hormonios(self, engine):
        lista = _rodar(engine, "consultar_protocolos_lancados", {"origem": "iatf", "status": "andamento"})
        item = lista["protocolos"][0]
        d = _rodar(engine, "consultar_protocolos_lancados", {"origem": "iatf", "origem_id": item["origem_id"]})
        d0 = next(x for x in d["dias"] if x["dia"] == 0)
        assert d0["hormonios"][0]["produto"] == "Benzoato de estradiol" and "opcoes" not in d0["hormonios"][0]
        assert "origem" in _rodar(engine, "consultar_protocolos_lancados", {"origem_id": "1"})["erro"]
        assert "erro" in _rodar(engine, "consultar_protocolos_lancados", {"origem": "iatf", "origem_id": "99999"})

    def test_bst_igual_ao_relatorio_do_site(self, engine):
        from fazenda.api.routers.producao import relatorio_bst
        with Session(engine) as s:
            site = relatorio_bst(session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_bst", PERIODO)
        assert r["total_aplicacoes"] == site["total"] == 2 and r["animais_distintos"] == 2
        assert _rodar(engine, "consultar_bst", {"numero": "500"})["total_aplicacoes"] == 1


# ---------------------------------------------------------------------------
# (c) sanidade
# ---------------------------------------------------------------------------
class TestSanidade:
    def test_cadastrados_batem_com_as_listas_do_cadastro(self, engine):
        from fazenda.api.routers.cadastro.protocolos_customizados import listar_protocolos_customizados
        from fazenda.api.routers.cadastro.protocolos_sanitarios import (
            listar_protocolos_iatf_cadastrados, listar_protocolos_inducao, listar_protocolos_sanitarios,
        )
        with Session(engine) as s:
            sanit = listar_protocolos_sanitarios(session=s, fazenda_id=1)
            iatf = listar_protocolos_iatf_cadastrados(session=s, fazenda_id=1)
            indu = listar_protocolos_inducao(session=s, fazenda_id=1)
            prop = listar_protocolos_customizados(session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_protocolos_cadastrados", {})
        assert r["total"] == len(sanit) + len(iatf) + len(indu) + len(prop) == 5
        assert r["por_tipo"] == {"sanitario_curativo": 1, "sanitario_preventivo": 1, "iatf": 1, "inducao": 1, "proprio": 1}
        cur = _rodar(engine, "consultar_protocolos_cadastrados", {"tipo": "sanitario_curativo"})
        assert [p["nome"] for p in cur["protocolos"]] == ["Mastite A"] and cur["protocolos"][0]["etapas"][0]["produto"] == "Ceftiofur"
        assert [p["nome"] for p in _rodar(engine, "consultar_protocolos_cadastrados", {"tipo": "sanitario_preventivo"})["protocolos"]] == ["Vermifugo Preventivo"]
        assert _rodar(engine, "consultar_protocolos_cadastrados", {"nome": "iatf"})["total"] == 1
        assert "erro" in _rodar(engine, "consultar_protocolos_cadastrados", {"tipo": "outro"})

    def test_regras_do_preventivo_igual_ao_calendario_do_site(self, engine):
        from fazenda.api.routers.sanidade import listar_calendario
        with Session(engine) as s:
            site = listar_calendario(data_inicio="", data_fim="", evento_sanitario_id=None, session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_regras_preventivo", {})
        assert [(x["id"], x["proxima_ocorrencia"]) for x in r["regras"]] == [(x["id"], x["proxima_ocorrencia"]) for x in site]
        assert r["regras"][0]["evento_sanitario_nome"] == "Aftosa"
        assert _rodar(engine, "consultar_regras_preventivo", {"nome": "nada"})["total_regras"] == 0
        r = _rodar(engine, "consultar_regras_preventivo", {"data_inicio": str(HOJE), "data_fim": str(HOJE + timedelta(days=400))})
        assert "ocorrencias_no_periodo" in r

    def test_agendamentos_batem_com_acompanhamento_e_concluidos(self, engine):
        from fazenda.rules import aplicacao_preventiva as ap
        with Session(engine) as s:
            ac_site = ap.acompanhamento(s, 1)
            co_site = ap.concluidos(s, 1)
        r = _rodar(engine, "consultar_agendamentos_preventivo", {"situacao": "todos"})
        assert r["agendados"]["total"] == len(ac_site["agendamentos"]) and r["agendados"]["totais_gerais"] == ac_site["totais"]
        assert r["concluidos"] == json.loads(json.dumps(co_site, default=str)) or r["concluidos"] == co_site

    def test_aplicacoes_batem_com_o_historico_do_site(self, engine):
        from fazenda.api.routers.sanidade import listar_aplicacoes
        with Session(engine) as s:
            site = listar_aplicacoes(session=s, fazenda_id=1)["aplicacoes"]
        esperado = [a for a in site if "2026-01-01" <= (a["data"] or "") <= "2026-07-01"]
        r = _rodar(engine, "consultar_aplicacoes_sanitarias", PERIODO)
        assert r["total"] == len(esperado) == 3
        assert {(a["numero"], a["data"], a["produto"]) for a in r["aplicacoes"]} == {(a["numero"], a["data"], a["produto"]) for a in esperado}
        assert _rodar(engine, "consultar_aplicacoes_sanitarias", {"numero": "500"})["total"] == 2
        assert _rodar(engine, "consultar_aplicacoes_sanitarias", {"produto": "iverm"})["total"] == 1
        assert _rodar(engine, "consultar_aplicacoes_sanitarias", {**PERIODO, "natureza": "curativo"})["total"] == 3


# ---------------------------------------------------------------------------
# (d) pedidos e cotações
# ---------------------------------------------------------------------------
class TestPedidosECotacoes:
    def test_pedidos_batem_com_a_lista_do_site(self, engine):
        from fazenda.api.routers.pedidos import listar_pedidos
        with Session(engine) as s:
            site = listar_pedidos(tipo=None, status="aberto", fornecedor_cliente=None, data_inicio=None, data_fim=None, session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_pedidos", {"status": "aberto"})
        assert [p["numero_pedido"] for p in r["pedidos"]] == [p["numero_pedido"] for p in site] == ["PED-1"]
        assert r["valor_total_estimado"] == 300.0 and r["pedidos"][0]["itens"][0]["produto_servico"] == "Vacina"
        assert _rodar(engine, "consultar_pedidos", {})["por_status"] == {"aberto": {"pedidos": 1, "valor_estimado": 300.0},
                                                                       "atendido": {"pedidos": 1, "valor_estimado": 300.0}}
        assert _rodar(engine, "consultar_pedidos", {"fornecedor": "agro"})["total"] == 1
        assert _rodar(engine, "consultar_pedidos", {"produto": "vacina"})["total"] == 2
        assert _rodar(engine, "consultar_pedidos", {"data_inicio": "2000-01-01", "data_fim": "2000-12-31"})["total"] == 0

    def test_cotacoes_e_comparacao_sem_token(self, engine):
        from fazenda.api.routers.cotacoes import listar_cotacoes
        with Session(engine) as s:
            site = listar_cotacoes(status=None, fazenda_id=1, session=s)
        r = _rodar(engine, "consultar_cotacoes", {})
        assert [c["numero_cotacao"] for c in r["cotacoes"]] == [c["numero_cotacao"] for c in site] == ["COT-1"]
        d = _rodar(engine, "consultar_cotacoes", {"numero_cotacao": "COT-1"})["detalhe"]
        assert d["respostas"][0]["preco_unitario"] == 12.5 and d["respostas"][0]["fornecedor"] == "Agrovet"
        assert "token" not in json.dumps(d)
        assert _rodar(engine, "consultar_cotacoes", {"status": "cancelada"})["total"] == 0


# ---------------------------------------------------------------------------
# (e) financeiro e estoque    (f) leite
# ---------------------------------------------------------------------------
class TestFinanceiroEstoqueLeite:
    def test_contas_a_pagar_igual_ao_endpoint_do_site(self, engine):
        from fazenda.api.routers.financeiro import contas_a_pagar
        with Session(engine) as s:
            site = contas_a_pagar(dias=10, data_referencia=HOJE, session=s, fazenda_id=1)
        r = _rodar(engine, "consultar_contas_financeiras", {
            "tipo": "pagar", "situacao": "aberta", "data_inicio": str(HOJE), "data_fim": str(HOJE + timedelta(days=10)),
        })
        assert [c["id"] for c in r["lancamentos"]] == [c["id"] for c in site] and r["total_lancamentos"] == 1
        assert r["a_pagar"]["valor_em_aberto"] == sum(c["valor_total"] - (c["valor_pago"] or 0) for c in site) == 100.0

    def test_totais_batem_com_consultar_financeiro(self, engine):
        antigo = _rodar(engine, "consultar_financeiro", {})
        r = _rodar(engine, "consultar_contas_financeiras", {"situacao": "aberta"})
        assert r["a_pagar"]["valor_total"] == antigo["total_em_aberto_a_pagar"] == 230.0
        assert r["a_receber"]["valor_total"] == antigo["total_em_aberto_a_receber"] == 200.0
        venc = _rodar(engine, "consultar_contas_financeiras", {"situacao": "vencida"})
        assert venc["total_lancamentos"] == antigo["qtd_contas_vencidas_a_pagar"] + antigo["qtd_contas_vencidas_a_receber"] == 1

    def test_filtros_e_categoria(self, engine):
        r = _rodar(engine, "consultar_contas_financeiras", {"data_inicio": str(HOJE - timedelta(days=30)), "data_fim": str(HOJE + timedelta(days=30)),
                                                           "categoria": "medicamentos"})
        assert r["total_lancamentos"] == 3 and r["por_categoria"]["Medicamentos"]["despesas"] == 240.0
        paga = _rodar(engine, "consultar_contas_financeiras", {"situacao": "paga", "campo_data": "pagamento",
                                                              "data_inicio": str(HOJE - timedelta(days=5)), "data_fim": str(HOJE)})
        assert paga["total_lancamentos"] == 1 and paga["lancamentos"][0]["situacao"] == "paga" and paga["lancamentos"][0]["valor_em_aberto"] == 0
        assert _rodar(engine, "consultar_contas_financeiras", {"situacao": "aberta", "tipo": "receber"})["total_lancamentos"] == 1
        assert _rodar(engine, "consultar_contas_financeiras", {"situacao": "aberta", "fornecedor": "agrovet", "texto": "aftosa"})["total_lancamentos"] == 1

    def test_estoque_igual_ao_site_e_sem_inativos(self, engine):
        from fazenda.api.routers.estoque import listar_estoque
        with Session(engine) as s:
            site = listar_estoque(fazenda_id=1, session=s)["itens"]
        ativos_abaixo = {i["nome"] for i in site if i["abaixo_minimo"] and i.get("ativo") is not False}
        r = _rodar(engine, "consultar_estoque_itens", {"situacao": "abaixo_minimo"})
        assert {i["nome"] for i in r["itens"]} == ativos_abaixo == {"Ivermectina"}
        antigo = _rodar(engine, "consultar_estoque", {})
        assert {i["nome"] for i in antigo["abaixo_do_minimo"]} == ativos_abaixo
        todos = _rodar(engine, "consultar_estoque_itens", {})
        assert {i["nome"] for i in todos["itens"]} == {"Ivermectina", "Ração X"}
        assert "Item Inativo" in {i["nome"] for i in _rodar(engine, "consultar_estoque_itens", {"incluir_inativos": "true"})["itens"]}
        assert todos["itens"][0]["fornecedor"] is None or isinstance(todos["itens"][0]["fornecedor"], str)

    def test_estoque_lotes_e_validade(self, engine):
        r = _rodar(engine, "consultar_estoque_itens", {"vencendo_em_dias": 60})
        assert [i["nome"] for i in r["itens"]] == ["Ivermectina"]
        lote = r["itens"][0]["lotes"][0]
        assert lote["numero_lote"] == "L1" and lote["dias_para_vencer"] == 30 and lote["vencido"] is False
        assert _rodar(engine, "consultar_estoque_itens", {"vencendo_em_dias": 10})["total"] == 0

    def test_producao_de_leite_igual_ao_controle_do_site(self, engine):
        from fazenda.api.routers.producao import listar_controles
        with Session(engine) as s:
            site = listar_controles(session=s, fazenda_id=1)["controles"]
        sel = [c for c in site if "2026-01-01" <= c["data"] <= "2026-07-01"]
        r = _rodar(engine, "consultar_producao_leite", {**PERIODO, "agrupar_por": "nenhum"})
        assert r["controles"] == len(sel) == 3 and r["total_kg"] == sum(c["producao_kg"] for c in sel) == 78.0
        assert r["animais_distintos"] == 2 and r["media_kg_por_controle"] == 26.0
        mes = _rodar(engine, "consultar_producao_leite", PERIODO)
        assert {g["grupo"]: g["total_kg"] for g in mes["grupos"]} == {"2026-03": 50.0, "2026-04": 28.0}
        animal = _rodar(engine, "consultar_producao_leite", {**PERIODO, "numero": "500"})
        assert animal["total_kg"] == 58.0 and len(animal["controles_do_animal"]) == 2
        lote = _rodar(engine, "consultar_producao_leite", {**PERIODO, "agrupar_por": "lote"})
        assert lote["grupos"][0]["grupo"] == "04 - SECAS"


# ---------------------------------------------------------------------------
# Sanitização e paginação na saída HTTP (/agente)  +  chat do site
# ---------------------------------------------------------------------------
@pytest.fixture
def client(engine, monkeypatch):
    import main
    import fazenda.database as database

    def _sess():
        with Session(engine) as s:
            yield s
    monkeypatch.setenv("AGENTE_API_TOKEN", TOKEN)
    main.app.dependency_overrides[database.get_session] = _sess
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


class TestHttpEChat:
    @pytest.mark.parametrize("nome", NOVAS)
    def test_todas_respondem_200_pelo_agente(self, client, nome):
        r = client.get(f"/agente/consultar/{nome}", params=TIPICOS[nome], headers=AUTH)
        assert r.status_code == 200, (nome, r.text)
        assert "resultado" in r.json() and "SEGREDO" not in r.text

    def test_parametros_desconhecidos_sao_recusados(self, client):
        assert client.get("/agente/consultar/consultar_pedidos", params={"x": "1"}, headers=AUTH).status_code == 400

    def test_sanitizacao_email_e_cpf(self, client):
        r = client.get("/agente/consultar/consultar_aplicacoes_sanitarias", params={"numero": "500"}, headers=AUTH)
        texto = r.text
        assert "fulano@exemplo.com" not in texto and "123.456.789-09" not in texto
        assert "[e-mail oculto]" in texto and "***.***.***-09" in texto

    def test_cotacao_nunca_expoe_token_publico(self, client):
        r = client.get("/agente/consultar/consultar_cotacoes", params={"numero_cotacao": "COT-1"}, headers=AUTH)
        assert "token-publico" not in r.text

    def test_paginacao_e_limite_de_bytes(self, client, engine, monkeypatch):
        with Session(engine) as s:
            for i in range(60):
                s.add(Sanidade(numero_matriz="500", data_aplicacao=date(2026, 5, 1), produto=f"Produto {i}", fazenda_id=1))
            s.commit()
        r = client.get("/agente/consultar/consultar_aplicacoes_sanitarias", params={"numero": "500", "limite": "10"}, headers=AUTH).json()
        assert r["truncado"] is True and len(r["resultado"]["aplicacoes"]) == 10
        assert r["resultado"]["total"] >= 60  # o total real continua informado
        r2 = client.get("/agente/consultar/consultar_aplicacoes_sanitarias", params={"numero": "500", "limite": "10", "offset": "10"}, headers=AUTH).json()
        assert r2["resultado"]["aplicacoes"] != r["resultado"]["aplicacoes"]
        monkeypatch.setenv("AGENTE_MAX_BYTES", "3000")
        r3 = client.get("/agente/consultar/consultar_aplicacoes_sanitarias", params={"numero": "500"}, headers=AUTH)
        assert len(r3.content) < 6000 and r3.json()["truncado"] is True

    def test_chat_formata_com_sanitizacao_e_truncamento(self, engine):
        resultado = _rodar(engine, "consultar_aplicacoes_sanitarias", {"numero": "500"})
        saida = ac.formatar_para_chat(resultado, {})
        assert "fulano@exemplo.com" not in json.dumps(saida) and saida["total"] == 2
        grande = {"itens": list(range(500)), "total": 500}
        env = ac.formatar_para_chat(grande, {})
        assert env["truncado"] is True and len(env["resultado"]["itens"]) == al.LIMITE_PADRAO

    def test_chat_usa_o_formatador_no_laco_de_tool_use(self, engine, monkeypatch):
        from fazenda.rules import assistente, assistente_llm
        respostas = iter([
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "consultar_aplicacoes_sanitarias", "arguments": {"numero": "500"}}]},
            {"role": "assistant", "content": "ok"},
        ])
        monkeypatch.setattr(assistente_llm, "completar", lambda *a, **k: next(respostas))
        with Session(engine) as s:
            out = assistente.responder("o que a 500 tomou?", [], s, _Usuario(), 1)
        tool_msg = next(m for m in out["historico"] if m.get("role") == "tool")
        assert "fulano@exemplo.com" not in tool_msg["content"] and "Ivermectina" in tool_msg["content"]
