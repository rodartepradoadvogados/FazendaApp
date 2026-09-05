"""
Teste-sentinela do PR claude/fazenda-id-raiz — a garantia de que a torneira
ficou fechada de verdade.

Percorre TODOS os modelos com coluna `fazenda_id` (`fazenda.models`, ~147
tabelas) e falha se QUALQUER linha ficar nula depois de um fluxo normal de
criação — sem exceções de tabela, com UMA única exceção de FORMA de contagem
(ver `_ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO` abaixo). Exercita um
usuário vinculado a uma ÚNICA fazenda real via UsuarioFazenda, com a fazenda
SELECIONADA na sessão, passando por um recorte representativo dos domínios
tocados no Passo 1 — reprodutivo (protocolo IATF), sanitário
(cadastro + lançamento de protocolo), produtivo (indução de lactação),
financeiro (lançamento) e Formulação de Dietas (biblioteca de alimentos +
simulação — Passo 2, ver PR claude/biblioteca-fracoes-cncps). Tabelas fora
deste recorte simplesmente não têm linha nenhuma neste banco isolado — a
checagem "zero NULL" continua válida pra elas por vacuidade, e cresce
sozinha conforme mais fluxos forem cobertos por outros testes que reusem
este mesmo `client` (ver fixture).

A sessão tem fazenda selecionada porque é a única forma de CHEGAR nas rotas:
a trava de tenant (fazenda/auth.py::exigir_fazenda_selecionada, montada em
todo router de fazenda em main.py) recusa com 409, antes do endpoint, toda
requisição sem "fid" quando existe qualquer fazenda cadastrada — e este banco
tem a Fazenda Sentinela. Antes desta trava a varredura rodava com token SEM
"fid" (cenário da causa raiz #1: sessão legada/"manter conectado"), cobrindo o
ramo do vínculo único de `resolver_fazenda_id_escrita`; esse ramo deixou de
ser alcançável por HTTP — quem prova a recusa na porta agora é
tests/test_trava_fazenda_selecionada.py. O que esta sentinela garante segue
igual e é o que dá nome ao arquivo: nenhuma escrita de nenhum módulo deixa
`fazenda_id` nulo, pois todo endpoint continua carimbando via
`get_fazenda_id_escrita` (agora pelo "fid" da sessão, ramo 1 do resolvedor).

Selecionar a fazenda liga também as travas comerciais que o `fazenda_id=None`
pulava ("SEM RETROATIVIDADE" documentado em `exigir_contrato_ativo`/
`exigir_modulo_contratado`) — daí o contrato ativo e TODOS os módulos
contratados semeados na fixture, sem os quais o recorte de módulos abaixo
tomaria 403.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


def _como_fazenda(fazenda_id: int | None):
    """Sessão com (ou sem) fazenda selecionada — o equivalente, no teste, ao
    "fid" do token que a trava de tenant exige."""
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Sentinela", ativa=True))
        # Contrato ativo + todos os módulos: com a fazenda selecionada (ver
        # docstring do arquivo) as travas comerciais deixam de ser puladas.
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        usuario = Usuario(username="funcionario_campo", senha_hash="x", papel="admin", ativo=True)
        s.add(usuario)
        s.commit()
        s.refresh(usuario)
        s.add(UsuarioFazenda(usuario_id=usuario.id, fazenda_id=1))
        s.commit()
        usuario_id = usuario.id

    main.app.dependency_overrides[database.get_session] = _get_session_override

    def _usuario_do_token():
        with Session(engine) as s:
            return s.get(Usuario, usuario_id)

    main.app.dependency_overrides[get_current_user] = _usuario_do_token
    # Sessão com a Fazenda Sentinela selecionada — sem isso a trava de tenant
    # recusa toda rota de fazenda com 409 e a varredura não sai do lugar.
    _como_fazenda(1)

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _tabelas_com_fazenda_id() -> list[str]:
    # `.tables.values()` (não `.sorted_tables`) — só precisamos dos nomes e
    # colunas, não da ordem topológica (que nem sempre existe: algumas
    # tabelas têm FK mutuamente dependente, ver aviso do SQLAlchemy).
    return [
        t.name for t in SQLModel.metadata.tables.values()
        if "fazenda_id" in t.columns
    ]


def _linhas_nulas(engine, tabela: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(f'SELECT COUNT(*) FROM "{tabela}" WHERE fazenda_id IS NULL').scalar() or 0


# `alimento_nutricional` é a ÚNICA tabela do sistema em que `fazenda_id`
# NULO é dado BOM, de propósito — marca a linha da BIBLIOTECA MESTRE CowData
# (global, semeada em runtime por `semear_biblioteca_mestre`; ver docstring
# de `AlimentoNutricional` em fazenda/models/formulacao.py e
# fazenda.rules.biblioteca_alimentos). O fluxo abaixo abre a aba Biblioteca
# (GET /formulacao/alimentos), que semeia essas linhas mestre — contá-las
# como "vazamento da torneira" seria falso positivo.
#
# Toda escrita de verdade grava `usuario_id` (ver criar_alimento_nutricional/
# obter_para_editar em formulacao_dietas.py); a semeadura da mestre nunca
# grava. Por isso "NULO com usuario_id preenchido" continua sendo o sinal
# correto de vazamento também nesta tabela — só "NULO com usuario_id nulo"
# (a mestre) é tolerado.
_ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO = "alimento_nutricional"


def _linhas_nulas_de_escrita_real(engine, tabela: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE fazenda_id IS NULL AND usuario_id IS NOT NULL'
        ).scalar() or 0


class TestSentinelaFazendaIdNuncaNulo:
    def test_fluxo_normal_de_criacao_nao_deixa_fazenda_id_nulo(self, client):
        c, engine = client

        # ── Reprodutivo: protocolo IATF ad-hoc (sem catálogo — protocolo_id
        # opcional) — mesmo caminho usado pelo bot do Telegram (ver
        # rules/telegram_fluxos.py, ramo "protocolo_iatf").
        r = c.post("/reproducao/protocolo-iatf", json={"animais": ["501"], "data_d0": date.today().isoformat()})
        assert r.status_code in (200, 201), r.text

        # ── Sanitário: cadastra o molde (Configurações > Cadastro) e lança.
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Mastite — sentinela", "eh_mastite": False, "dia_inicial": 0,
            "etapas": [{"dia": 0, "produto": "Penicilina", "dosagem": 10, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        protocolo_id = r.json()["id"]
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": protocolo_id, "numeros_matriz": ["502"], "data_inicio": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Produtivo: indução de lactação (o sintoma original do PR).
        r = c.post("/cadastro/protocolos-inducao-lactacao", json={
            "nome": "Indução — sentinela",
            "etapas": [{"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        molde_id = r.json()["id"]
        r = c.post("/producao/inducao-lactacao", json={
            "protocolo_id": molde_id, "animais": ["503"], "data_d0": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Financeiro: lançamento avulso.
        r = c.post("/financeiro/lancamentos", json={
            "tipo": "despesa",
            "itens": [{"produto": "Ração concentrada", "valor_total": 150.0}],
            "data_emissao": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Formulação de Dietas (Passo 2 — #488 tinha deixado este módulo
        # de fora). A permissão de acesso ao módulo é mais estrita que o
        # resto do site (exigir_admin_ou_consultor_fazenda, backlog #127:
        # só dono-equivalente ou Consultor CowData vinculado) — sem isso o
        # "funcionario_campo" comum tomaria 403 antes mesmo de chegar no
        # resolvedor de fazenda_id que este teste quer exercitar. O e-mail
        # dono-equivalente só destrava essa checagem DE PERMISSÃO; a
        # RESOLUÇÃO de fazenda_id em si continua vindo do MESMO vínculo
        # UsuarioFazenda(fazenda_id=1) configurado no setup acima — é
        # exatamente esse caminho (token sem "fid" + vínculo único) que a
        # correção do PR claude/fazenda-id-raiz garante.
        with Session(engine) as s:
            # `usuario_id` do fixture não sobrevive fora do `with` em que foi
            # atribuído — busca pelo username fixo do fixture em vez disso.
            usuario = s.exec(select(Usuario).where(Usuario.username == "funcionario_campo")).one()
            usuario.email = EMAIL_DONO
            s.add(usuario)
            s.commit()

        # Abre a aba Biblioteca — semeia a biblioteca mestre CowData
        # (fazenda_id NULO de propósito, ver
        # _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO abaixo).
        r = c.get("/formulacao/alimentos")
        assert r.status_code == 200, r.text

        r = c.post("/formulacao/alimentos", json={
            "alimento_id": None, "nome": "Farelo sentinela", "categoria_nasem": "Concentrado proteico",
            "conc_pct": 100.0, "fonte": None, "observacao": None, "valores": {},
        })
        assert r.status_code == 201, r.text
        alimento_nutricional_id = r.json()["id"]

        r = c.post("/formulacao/simulacoes", json={"nome": "Sentinela"})
        assert r.status_code == 201, r.text
        simulacao_id = r.json()["id"]
        r = c.put(f"/formulacao/simulacoes/{simulacao_id}", json={
            "animal": {
                "estado_fisiologico": "vaca_lactante", "raca": "Holandes", "peso_vivo_kg": 650.0,
                "peso_maturo_kg": 680.0, "ecc": 3.0, "paridade": 2.0, "del_dias": 150, "eq_cms": 8,
                "producao_leite_kg_dia": 35.0, "gordura_leite_pct": 3.8, "proteina_leite_pct": 3.2,
            },
            "itens": [
                {"nome": "Silagem de milho", "categoria_nasem": "Forragem", "conc_pct": 0.0, "proporcao_ms_pct": 60.0, "origem": "manual"},
                {"nome": "Farelo de soja", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0, "proporcao_ms_pct": 40.0, "origem": "manual"},
            ],
            "etapa_atual": 1,
        })
        assert r.status_code == 200, r.text

        # Checagem pontual (não só a varredura geral abaixo): o item da
        # biblioteca, a simulação e os itens da grade têm que ter ido para a
        # MESMA fazenda do vínculo, não fazenda_id nulo nem outra fazenda.
        with Session(engine) as s:
            from fazenda.models import AlimentoNutricional, DietaSimulacao, DietaSimulacaoItem
            assert s.get(AlimentoNutricional, alimento_nutricional_id).fazenda_id == 1
            sim = s.get(DietaSimulacao, simulacao_id)
            assert sim.fazenda_id == 1
            itens_sim = s.exec(select(DietaSimulacaoItem).where(DietaSimulacaoItem.simulacao_id == simulacao_id)).all()
            assert itens_sim and all(i.fazenda_id == 1 for i in itens_sim)

        # ── Varredura: NENHUMA tabela com fazenda_id pode ter linha nula —
        # exceto a mestre CowData de `alimento_nutricional`, que é nulo de
        # propósito (ver _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO).
        tabelas_com_linha_nula: dict[str, int] = {}
        for tabela in _tabelas_com_fazenda_id():
            n = (
                _linhas_nulas_de_escrita_real(engine, tabela)
                if tabela == _ALIMENTO_NUTRICIONAL_TOLERA_NULO_LEGITIMO
                else _linhas_nulas(engine, tabela)
            )
            if n:
                tabelas_com_linha_nula[tabela] = n

        assert not tabelas_com_linha_nula, (
            "Linha(s) com fazenda_id NULO depois de um fluxo normal de escrita — a torneira "
            f"não fechou de verdade: {tabelas_com_linha_nula}"
        )

    def test_modulos_rh_estoque_farmacia_planejamento_pedidos_recria_alimentacao_nao_deixam_fazenda_id_nulo(self, client):
        """Extensão do PR claude/migracoes-e-varredura-fazenda-id (ENTREGA B) —
        mesma garantia do teste acima, agora cobrindo os módulos que o #488
        declarou fora do escopo por não terem aparecido na causa raiz
        original: RH/Folha (rh_contratos.py/rh_folha.py/rh_vale_item.py),
        Estoque, Farmácia, Planejamento, Pedidos, Recria e Alimentação.
        Também cobre o caminho indireto encontrado nesta varredura —
        `POST /upload/{tipo}` (parser Ideagri) chamando `get_fazenda_id_escrita`
        como qualquer outro endpoint de escrita, e `POST /importar/pesagem`
        (importar.py), que chamava `criar_pesagens` sem `user=`/`fazenda_id=`
        (mesmo padrão do bug do telegram_fluxos.py corrigido no #488)."""
        c, engine = client

        with Session(engine) as s:
            pessoa = Pessoa(
                nome="Diarista Sentinela", tipo="Diarista", ativo=True,
                salario_base=2000.0, data_admissao=date(2020, 1, 1),
                fazenda_id=1,  # mesma fazenda semeada pela fixture `client` (Fazenda id=1)
            )
            s.add(pessoa)
            s.commit()
            s.refresh(pessoa)
            pessoa_id = pessoa.id

        # ── RH: Diária (cadastro + pagamento) + Vale avulso abatido dela.
        r = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": date.today().isoformat(),
        })
        assert r.status_code == 200, r.text
        diaria_id = r.json()["id"]
        r = c.post(f"/cadastro/diarias/{diaria_id}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 100.0,
        })
        assert r.status_code == 200, r.text
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria_id, "valor": 50.0,
            "forma_pagamento": "desconto_proximo_pagamento", "data_pagamento": date.today().isoformat(),
        })
        assert r.status_code == 200, r.text

        # ── RH: Empreitada (por etapa, sem parcela — mesmo passo que cria
        # EmpreitadaEtapa direto no cadastro).
        r = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Cerca nova", "valor_total": 500.0,
            "tipo_pagamento": "por_etapa", "etapas": [{"nome": "Etapa única", "valor": 500.0}],
        })
        assert r.status_code == 200, r.text

        # ── RH: Folha de pagamento, Férias, 13º e Vale de funcionário.
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-01", "valor_bruto": 2000.0,
        })
        assert r.status_code == 200, r.text
        r = c.post("/cadastro/ferias", json={
            "pessoa_id": pessoa_id,
            "periodo_aquisitivo_inicio": "2025-01-01", "periodo_aquisitivo_fim": "2026-01-01",
            "dias_gozados": 30, "data_inicio_gozo": date.today().isoformat(),
            "data_fim_gozo": (date.today() + timedelta(days=29)).isoformat(),
        })
        assert r.status_code == 200, r.text
        r = c.post("/cadastro/decimo-terceiro", json={"pessoa_id": pessoa_id, "ano": 2026, "meses_trabalhados": 12})
        assert r.status_code == 200, r.text
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 200.0, "forma_pagamento": "desconto_integral_folha",
            "data_pagamento": date.today().isoformat(), "competencia_inicio": "2026-02",
        })
        assert r.status_code == 200, r.text

        # ── Estoque: cadastro do item + movimentação (baixa).
        r = c.post("/estoque/", json={"nome": "Ração Sentinela", "unidade": "kg", "quantidade": 100.0})
        assert r.status_code == 201, r.text
        r = c.post("/estoque/movimentar", json={
            "nome": "Ração Sentinela", "movimento": "Saída de ajuste", "quantidade": 10.0,
            "data_movimento": date.today().isoformat(),
        })
        assert r.status_code == 200, r.text

        # ── Farmácia: princípio ativo + marca comercial.
        r = c.post("/farmacia/principios", json={"nome": "Princípio Sentinela"})
        assert r.status_code == 201, r.text
        principio_id = r.json()["id"]
        r = c.post("/farmacia/medicamentos", json={"principio_ativo_id": principio_id, "nome_comercial": "Marca Sentinela"})
        assert r.status_code == 201, r.text

        # ── Planejamento: orçamento + cenário + item de cenário.
        r = c.post("/planejamento/orcamento", json={
            "ano": 2026, "mes": 1, "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_orcado": 1000.0,
        })
        assert r.status_code == 201, r.text
        r = c.post("/planejamento/cenarios", json={"nome": "Cenário Sentinela"})
        assert r.status_code == 201, r.text
        cenario_id = r.json()["id"]
        r = c.post(f"/planejamento/cenarios/{cenario_id}/itens", json={
            "mes_competencia": "2026-01", "codigo_conta_gerencial": "3.01.01", "tipo": "despesa", "valor_previsto": 1000.0,
        })
        assert r.status_code == 201, r.text

        # ── Pedidos.
        r = c.post("/pedidos/", json={
            "tipo": "compra", "data_pedido": date.today().isoformat(),
            "itens": [{"tipo_item": "produto", "produto_servico": "Ração", "valor_total_estimado": 300.0}],
        })
        assert r.status_code == 201, r.text

        # ── Recria: categoria de manejo, leitura de cocho e ocorrência clínica.
        r = c.post("/recria/categorias", json={"nome": "Categoria Sentinela", "dia_min": 0, "dia_max": 30})
        assert r.status_code == 201, r.text
        r = c.post("/recria/cocho", json={"data": date.today().isoformat(), "lote": "01", "kg_ofertado": 100.0, "kg_sobra": 10.0})
        assert r.status_code == 201, r.text
        r = c.post("/recria/ocorrencias", json={
            "numero_matriz": "601", "doenca": "Diarreia", "data_ocorrencia": date.today().isoformat(),
        })
        assert r.status_code == 201, r.text

        # ── Alimentação: categoria + alimento + dieta lançada num lote.
        r = c.post("/alimentacao/categorias", json={"nome": "Categoria Alimento Sentinela"})
        assert r.status_code == 201, r.text
        r = c.post("/alimentacao/alimentos", json={"nome": "Alimento Sentinela"})
        assert r.status_code == 201, r.text
        r = c.post("/alimentacao/dietas", json={
            "lote": 1, "data_abertura": date.today().isoformat(),
            "itens": [{"alimento": "Silagem", "quantidade": 50.0, "unidade": "kg"}],
        })
        assert r.status_code == 201, r.text

        # ── Upload Ideagri (upload.py) — mesmo caminho de importação em massa
        # citado no PR como maior risco de chamador indireto: `_carimbar`
        # antes deixava a linha sem fazenda_id quando o resolvedor tolerante
        # devolvia None; agora usa get_fazenda_id_escrita, resolvido pelo
        # vínculo único do usuário (mesmo cenário de token legado do restante
        # deste teste).
        csv_estoque = "Nome;Quantidade\r\nInsumo Upload Sentinela;25\r\n".encode("windows-1252")
        r = c.post("/upload/estoque", files={"file": ("ESTOQUE.csv", csv_estoque, "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["registros"] >= 1, r.text

        # ── Importação de CSV manual (importar.py::importar_pesagem) — a
        # função de criação (`producao.criar_pesagens`) é chamada direto,
        # fora do ciclo HTTP da rota real; sem `user=`/`fazenda_id=`
        # explícitos por keyword, herdava os `Depends(...)` não resolvidos.
        with Session(engine) as s:
            s.add(Animal(
                numero="602", eh_semen=False, ativo=True, grupo_manual=False, a_descartar=False, excluir_bst=False,
                fazenda_id=1,
            ))
            s.commit()
        csv_pesagem = "numero_matriz;data_pesagem;peso_kg\r\n602;01/01/2026;350\r\n".encode("windows-1252")
        r = c.post("/importar/pesagem", files={"file": ("pesagem.csv", csv_pesagem, "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["criados"] >= 1, r.text

        # ── Varredura: NENHUMA tabela com fazenda_id pode ter linha nula.
        tabelas_com_linha_nula: dict[str, int] = {}
        for tabela in _tabelas_com_fazenda_id():
            n = _linhas_nulas(engine, tabela)
            if n:
                tabelas_com_linha_nula[tabela] = n

        assert not tabelas_com_linha_nula, (
            "Linha(s) com fazenda_id NULO depois de um fluxo normal de escrita nos módulos "
            f"RH/Estoque/Farmácia/Planejamento/Pedidos/Recria/Alimentação: {tabelas_com_linha_nula}"
        )

    def test_usuario_sem_nenhuma_fazenda_vinculada_e_recusado_no_lancamento(self, client):
        """Causa raiz #2 do PR: usuário sem NENHUM vínculo de fazenda e sem
        "fid" no token — recusa com 409 em vez de gravar fazenda_id nulo.

        A recusa continua sendo 409, mas hoje vem mais cedo: a trava de tenant
        barra a requisição sem "fid" na porta do router (ver docstring do
        arquivo), antes de `resolver_fazenda_id_escrita` ter chance de recusar
        por conta própria. Por isso a sessão volta explicitamente a NÃO ter
        fazenda selecionada aqui — é esse o cenário sob teste, e ele segue
        recusado; o que mudou é só quem recusa."""
        c, engine = client
        with Session(engine) as s:
            # E-mail dono-equivalente só para destravar a permissão PRÓPRIA
            # de Formulação de Dietas (exigir_admin_ou_consultor_fazenda) —
            # sem vínculo nenhum de UsuarioFazenda, exatamente o cenário que
            # este teste quer provar que continua recusado.
            usuario = Usuario(username="sem_fazenda", senha_hash="x", papel="admin", ativo=True, email=EMAIL_DONO)
            s.add(usuario)
            s.commit()
            s.refresh(usuario)
            usuario_id_sem_fazenda = usuario.id

        import main
        from fazenda.auth import get_current_user

        def _usuario_sem_fazenda():
            with Session(engine) as s:
                return s.get(Usuario, usuario_id_sem_fazenda)

        override_original = main.app.dependency_overrides[get_current_user]
        main.app.dependency_overrides[get_current_user] = _usuario_sem_fazenda
        _como_fazenda(None)
        try:
            r = c.post("/reproducao/protocolo-iatf", json={"animais": ["999"], "data_d0": date.today().isoformat()})
            assert r.status_code == 409, r.text

            # Formulação de Dietas (Passo 2): mesma recusa, mesmo caminho
            # (get_fazenda_id_escrita -> resolver_fazenda_id_escrita).
            r = c.post("/formulacao/simulacoes", json={"nome": "Sem fazenda"})
            assert r.status_code == 409, r.text
            r = c.post("/formulacao/alimentos", json={
                "alimento_id": None, "nome": "Sem fazenda", "categoria_nasem": "Outros",
                "conc_pct": 0.0, "fonte": None, "observacao": None, "valores": {},
            })
            assert r.status_code == 409, r.text
        finally:
            main.app.dependency_overrides[get_current_user] = override_original
            _como_fazenda(1)
