"""
Regressão dos 6 achados da onda "vazamento de leitura" (auditoria de
02/09/2026, ver docs/security-audit) nos routers de apoio/formulário
(fornecedores/clientes/serviços, Portal, importação de CSV, não
conformidades e cadastro de estoque):

  F-C-02 — Ficha do animal vaza compra/venda/baixa/ocorrência de outra
           fazenda com o mesmo número (JÁ CORRIGIDO antes desta onda — ver
           tests/test_multi_fazenda_isolamento.py::
           TestBuscaEFichaAnimalIsolada::
           test_ficha_animal_nao_mistura_historico_de_numero_colidente,
           que já cobre exatamente este cenário).
  F-C-05 — GET /pedidos/opcoes devolve fornecedores/clientes/serviços de
           TODAS as fazendas.
  F-C-11 — Portal aceita destinatario_usuario_id de OUTRA fazenda em
           enviar_mensagem/delegar_tarefa (escrita cross-tenant).
  F-C-12 — Importação de baixas de pendências resolve EventoSanitario/
           CalendarioSanitario por nome sem fazenda_id.
  F-C-17 — Não conformidades soma a ContaGerencial de TODAS as fazendas no
           indicador "Custo por hectare" (chama a função Python direto, sem
           passar fazenda_id).
  F-C-22 — Editar metas do item de estoque aceita fornecedor_id/
           estoque_semen_id de outra fazenda (referência cruzada + escrita
           no EstoqueSemen alheio via movimentação normal).

Mesma fixture/convenção de tests/test_isolamento_relatorios_fornecedor.py e
tests/test_seguranca_p1_multitenant.py: banco SQLite descartável por teste,
duas fazendas com contrato ativo + todos os módulos comerciais, usuário
fake "admin" (ignora `tem_modulo`), fazenda atual trocada via
`dependency_overrides[get_fazenda_atual_id]`.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Estoque, EstoqueSemen, EventoRealizado,
    EventoSanitario, Fazenda, Fornecedor, ParametroFazenda, PortalMensagem, Sanidade, ServicoCadastro, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Área total (Configurações > Parâmetros) — parâmetro GLOBAL
        # (fazenda_id nulo), só para o indicador "Custo por hectare" ter
        # denominador != 0 e aparecer na resposta de /nao-conformidades/.
        s.add(ParametroFazenda(chave="area_total_hectares", fazenda_id=None, valor="100", tipo="float", grupo="estrutura", label="Área total"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user
    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "admin@example.com"
        permissoes = ""
        nome = "Usuária Teste"
        pessoa_id = None

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


# ---------------------------------------------------------------------------
# F-C-05 — GET /pedidos/opcoes
# ---------------------------------------------------------------------------
class TestPedidosOpcoesIsoladoPorFazenda:
    def test_fornecedores_e_servicos_de_outra_fazenda_nao_aparecem(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Fornecedor(nome="Fornecedor Próprio F1", tipo="fornecedor", fazenda_id=1))
            s.add(Fornecedor(nome="Cliente Próprio F1", tipo="cliente", fazenda_id=1))
            s.add(Fornecedor(nome="Fornecedor Secreto F2", tipo="fornecedor", fazenda_id=2))
            s.add(Fornecedor(nome="Cliente Secreto F2", tipo="cliente", fazenda_id=2))
            s.add(ServicoCadastro(nome="Serviço Próprio F1", fazenda_id=1))
            s.add(ServicoCadastro(nome="Serviço Secreto F2", fazenda_id=2))
            # Catálogo GLOBAL (seed de cadastro/servicos.py::seed_servicos —
            # fazenda_id nulo) — precisa CONTINUAR aparecendo para todo mundo;
            # a correção não pode virar filtro estrito.
            s.add(ServicoCadastro(nome="Frete"))
            s.commit()

        _como_fazenda(1)
        r = c.get("/pedidos/opcoes")
        assert r.status_code == 200, r.text
        corpo = r.json()

        assert "Fornecedor Secreto F2" not in corpo["fornecedores"], "vazou fornecedor da fazenda 2"
        assert "Cliente Secreto F2" not in corpo["clientes"], "vazou cliente da fazenda 2"
        assert "Serviço Secreto F2" not in corpo["servicos"], "vazou serviço da fazenda 2"

        assert "Fornecedor Próprio F1" in corpo["fornecedores"]
        assert "Cliente Próprio F1" in corpo["clientes"]
        assert "Serviço Próprio F1" in corpo["servicos"]
        # Catálogo global tem que continuar visível — não é "dado da
        # fazenda" (ServicoCadastro nasce com fazenda_id nulo no seed).
        assert "Frete" in corpo["servicos"], "filtro estrito escondeu o catálogo global"


# ---------------------------------------------------------------------------
# F-C-11 — POST /portal/mensagens e POST /portal/tarefas
# ---------------------------------------------------------------------------
class TestPortalDestinatarioDeOutraFazenda:
    def _preparar_usuarios(self, engine):
        with Session(engine) as s:
            s.add(Usuario(id=1, username="admin_f1", senha_hash="x", papel="admin", nome="Admin F1"))
            s.add(Usuario(id=2, username="user_f2", senha_hash="x", papel="operador", nome="Vítima F2"))
            s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
            s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
            s.commit()

    def test_enviar_mensagem_para_usuario_de_outra_fazenda_e_recusado(self, client):
        c, engine = client
        self._preparar_usuarios(engine)
        _como_fazenda(1)
        r = c.post("/portal/mensagens", json={
            "destinatarios_usuario_id": [2], "corpo": "phishing interno", "pede_retorno": True,
        })
        assert r.status_code == 404, r.text
        with Session(engine) as s:
            assert s.exec(select(PortalMensagem)).all() == [], (
                "mensagem cross-tenant foi gravada e cairia na caixa de entrada do usuário da fazenda 2"
            )

    def test_delegar_tarefa_para_usuario_de_outra_fazenda_e_recusado(self, client):
        c, engine = client
        self._preparar_usuarios(engine)
        _como_fazenda(1)
        r = c.post("/portal/tarefas", json={"destinatarios_usuario_id": [2], "corpo": "faça isso"})
        assert r.status_code == 404, r.text
        with Session(engine) as s:
            assert s.exec(select(PortalMensagem)).all() == [], "tarefa cross-tenant foi gravada"

    def test_enviar_mensagem_para_usuario_da_propria_fazenda_continua_funcionando(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Usuario(id=1, username="admin_f1", senha_hash="x", papel="admin", nome="Admin F1"))
            s.add(Usuario(id=3, username="colega_f1", senha_hash="x", papel="operador", nome="Colega F1"))
            s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
            s.add(UsuarioFazenda(usuario_id=3, fazenda_id=1))
            s.commit()
        _como_fazenda(1)
        r = c.post("/portal/mensagens", json={"destinatarios_usuario_id": [3], "corpo": "oi"})
        assert r.status_code == 200, r.text
        assert r.json()["criadas"] == 1


# ---------------------------------------------------------------------------
# F-C-12 — POST /importar/baixas_pendencias_agenda
# ---------------------------------------------------------------------------
def _csv_baixas(linhas: list[list[str]]) -> bytes:
    colunas = [
        "tipo", "nome_evento", "numero_animal", "data_pendencia", "produto_aplicado", "dose", "unidade", "via",
        "responsavel", "observacao",
    ]
    texto = ";".join(colunas) + "\r\n" + "\r\n".join(";".join(l) for l in linhas) + "\r\n"
    return texto.encode("windows-1252")


class TestImportarBaixasPendenciasNaoResolveEventoDeOutraFazenda:
    def test_evento_sanitario_de_outra_fazenda_nao_e_usado_para_dispensar(self, client):
        """POC do dossiê: CSV com `tipo=evento_sanitario,nome_evento=<nome só
        cadastrado na fazenda B>` — a fazenda A (atacante) não tem esse
        EventoSanitario, mas antes da correção o `.first()` sem fazenda_id
        resolvia o da fazenda B mesmo assim, aplicando o produto/dose PADRÃO
        secreto dela no lançamento local (e dispensando, com `eid` que
        embute o id da regra da fazenda B, uma pendência que é dela)."""
        c, engine = client
        with Session(engine) as s:
            # Fazenda A (1, atacante): só o animal "1" — nenhum EventoSanitario
            # próprio chamado "Brucelose RB51".
            s.add(Animal(numero="1", data_nasc=date(2026, 1, 1), sexo="F", ativo=True, fazenda_id=1))
            # Fazenda B (2, vítima): o EventoSanitario com o mesmo nome usado
            # no CSV, configurado com um produto padrão SIGILOSO.
            s.add(EventoSanitario(
                nome="Brucelose RB51", tipo_agendamento="evento", gatilho="nascimento", offset_dias=0,
                produto_padrao="Vacina Secreta da Fazenda B", dose_padrao=2.0, unidade_padrao="ml",
                fazenda_id=2,
            ))
            s.commit()

        _como_fazenda(1)
        r = c.post(
            "/importar/baixas_pendencias_agenda",
            files={"file": ("b.csv", _csv_baixas([
                ["evento_sanitario", "Brucelose RB51", "1", "01/01/2026", "", "", "", "", "", ""],
            ]), "text/csv")},
            data={"data_corte": ""},
        )
        assert r.status_code == 200, r.text
        corpo = r.json()

        assert corpo["criados"] == 0, "aplicou o padrão da fazenda B na fazenda A"
        assert corpo["dispensados"] == 0
        assert len(corpo["erros"]) == 1, "deveria recusar por não achar o evento NA PRÓPRIA fazenda"

        with Session(engine) as s:
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.fazenda_id == 1)).all()
            assert aplicacoes == [], "não pode existir Sanidade com o produto secreto da fazenda B"
            vazou_produto = s.exec(
                select(Sanidade).where(Sanidade.produto == "Vacina Secreta da Fazenda B")
            ).first()
            assert vazou_produto is None

    def test_evento_sanitario_da_propria_fazenda_continua_funcionando(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="1", data_nasc=date(2026, 1, 1), sexo="F", ativo=True, fazenda_id=1))
            s.add(EventoSanitario(
                nome="Brucelose RB51", tipo_agendamento="evento", gatilho="nascimento", offset_dias=0,
                produto_padrao="Vacina Própria da Fazenda A", dose_padrao=2.0, unidade_padrao="ml",
                fazenda_id=1,
            ))
            s.commit()
        _como_fazenda(1)
        r = c.post(
            "/importar/baixas_pendencias_agenda",
            files={"file": ("b.csv", _csv_baixas([
                ["evento_sanitario", "Brucelose RB51", "1", "01/01/2026", "", "", "", "", "", ""],
            ]), "text/csv")},
            data={"data_corte": ""},
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["criados"] == 1, corpo
        assert corpo["dispensados"] == 1
        assert not corpo["erros"]
        with Session(engine) as s:
            aplicacoes = s.exec(select(Sanidade).where(Sanidade.fazenda_id == 1)).all()
            assert len(aplicacoes) == 1
            assert aplicacoes[0].produto == "Vacina Própria da Fazenda A"
            # EventoRealizado gravado JÁ com fazenda_id (não mais None) —
            # senão a linha "dispensa para todo mundo" (agenda.py lê com
            # `fazenda_id.in_((fid, None))`).
            realizado = s.exec(select(EventoRealizado)).first()
            assert realizado is not None
            assert realizado.fazenda_id == 1


# ---------------------------------------------------------------------------
# F-C-17 — GET /nao-conformidades/
# ---------------------------------------------------------------------------
class TestNaoConformidadesCustoHectareIsolado:
    def test_despesa_de_outra_fazenda_nao_entra_no_custo_por_hectare(self, client):
        c, engine = client
        hoje = date.today()
        ini_mes = hoje.replace(day=1)
        with Session(engine) as s:
            s.add(ContaGerencial(
                numero_lancamento="LC-F1", codigo_conta="3.01", descricao="Despesa F1", tipo="despesa",
                origem="manual", valor_total=7.0, data_competencia=ini_mes, fazenda_id=1,
            ))
            s.add(ContaGerencial(
                numero_lancamento="LC-F2", codigo_conta="3.01", descricao="Despesa secreta F2", tipo="despesa",
                origem="manual", valor_total=100000.0, data_competencia=ini_mes, fazenda_id=2,
            ))
            s.commit()

        _como_fazenda(1)
        r = c.get("/nao-conformidades/")
        assert r.status_code == 200, r.text
        hectare = next((i for i in r.json()["sem_meta"] if i["chave"] == "custo_hectare"), None)
        assert hectare is not None, "indicador nem apareceu — confira o parâmetro de área global"
        # Só a despesa da própria fazenda (7,00 / 100 ha = 0,07) — nunca
        # 100.007,00 / 100 ha (o valor que sairia somando a da fazenda 2 também).
        assert hectare["valor"] == pytest.approx(0.07), (
            f"custo por hectare contaminado com despesa de outra fazenda: {hectare['valor']}"
        )


# ---------------------------------------------------------------------------
# F-C-22 — PUT /cadastro/estoque-itens/{item_id}
# ---------------------------------------------------------------------------
class TestEstoqueMetaNaoAceitaReferenciaDeOutraFazenda:
    def test_fornecedor_id_de_outra_fazenda_e_recusado(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Ração X", unidade="kg", fazenda_id=1)
            fornecedor_f2 = Fornecedor(nome="Fornecedor Secreto F2", tipo="fornecedor", fazenda_id=2)
            s.add(item)
            s.add(fornecedor_f2)
            s.commit()
            s.refresh(item)
            s.refresh(fornecedor_f2)
            item_id, fornecedor_f2_id = item.id, fornecedor_f2.id

        _como_fazenda(1)
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"fornecedor_id": fornecedor_f2_id})
        assert r.status_code == 400, r.text

        with Session(engine) as s:
            item = s.get(Estoque, item_id)
            assert item.fornecedor_id is None, "item da fazenda 1 ficou apontando fornecedor da fazenda 2"

    def test_estoque_semen_id_de_outra_fazenda_e_recusado(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Ração X", unidade="kg", fazenda_id=1)
            touro_f2 = EstoqueSemen(touro_nome="Touro Secreto F2", doses=50, fazenda_id=2)
            s.add(item)
            s.add(touro_f2)
            s.commit()
            s.refresh(item)
            s.refresh(touro_f2)
            item_id, touro_f2_id = item.id, touro_f2.id

        _como_fazenda(1)
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"estoque_semen_id": touro_f2_id})
        assert r.status_code == 400, r.text

        with Session(engine) as s:
            item = s.get(Estoque, item_id)
            assert item.estoque_semen_id is None, (
                "item da fazenda 1 ficou apontando EstoqueSemen da fazenda 2 — toda movimentação "
                "normal do item passaria a somar/subtrair doses no estoque de sêmen alheio"
            )

    def test_fornecedor_e_estoque_semen_da_propria_fazenda_continuam_aceitos(self, client):
        c, engine = client
        with Session(engine) as s:
            item = Estoque(nome="Ração X", unidade="kg", fazenda_id=1)
            fornecedor = Fornecedor(nome="Fornecedor Próprio F1", tipo="fornecedor", fazenda_id=1)
            touro = EstoqueSemen(touro_nome="Touro Próprio F1", doses=10, fazenda_id=1)
            s.add(item)
            s.add(fornecedor)
            s.add(touro)
            s.commit()
            s.refresh(item)
            s.refresh(fornecedor)
            s.refresh(touro)
            item_id, fornecedor_id, touro_id = item.id, fornecedor.id, touro.id

        _como_fazenda(1)
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"fornecedor_id": fornecedor_id, "estoque_semen_id": touro_id})
        assert r.status_code == 200, r.text
        assert r.json()["fornecedor_id"] == fornecedor_id
        assert r.json()["estoque_semen_id"] == touro_id
