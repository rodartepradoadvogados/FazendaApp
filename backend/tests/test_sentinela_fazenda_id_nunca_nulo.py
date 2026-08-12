"""
Teste-sentinela do PR claude/fazenda-id-raiz — a garantia de que a torneira
ficou fechada de verdade.

Percorre TODOS os modelos com coluna `fazenda_id` (`fazenda.models`, ~147
tabelas) e falha se QUALQUER linha ficar nula depois de um fluxo normal de
criação — sem exceções, sem lista de tabelas toleradas. Exercita um usuário
com token SEM "fid" (o cenário exato da causa raiz #1: token legado/sessão
"manter conectado" que nunca deslogou) vinculado a uma ÚNICA fazenda real
via UsuarioFazenda, passando por um recorte representativo dos domínios
tocados no Passo 1 — reprodutivo (protocolo IATF), sanitário (cadastro +
lançamento de protocolo), produtivo (indução de lactação) e financeiro
(lançamento). Tabelas fora deste recorte simplesmente não têm linha
nenhuma neste banco isolado — a checagem "zero NULL" continua válida pra
elas por vacuidade, e cresce sozinha conforme mais fluxos forem cobertos por
outros testes que reusem este mesmo `client` (ver fixture).

Não precisa de ContratoFazenda/ContratoFazendaModulo: com o token sem "fid",
`exigir_contrato_ativo`/`exigir_modulo_contratado` (fazenda.auth) recebem
`fazenda_id=None` de `get_fazenda_atual_id` e pulam a checagem inteira (é o
"SEM RETROATIVIDADE" documentado nessas dependências) — só
`get_fazenda_id_escrita`, usado dentro de cada endpoint de escrita, resolve
de verdade a partir do vínculo do usuário.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Animal, Fazenda, Pessoa, Usuario, UsuarioFazenda


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
    # De propósito: NÃO sobrescreve get_fazenda_atual_id — a implementação
    # real roda, sem header Authorization, devolvendo None (token sem "fid").

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

        # ── Varredura: NENHUMA tabela com fazenda_id pode ter linha nula.
        tabelas_com_linha_nula: dict[str, int] = {}
        for tabela in _tabelas_com_fazenda_id():
            n = _linhas_nulas(engine, tabela)
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
        "fid" no token — recusa com 409 em vez de gravar fazenda_id nulo."""
        c, engine = client
        with Session(engine) as s:
            usuario = Usuario(username="sem_fazenda", senha_hash="x", papel="admin", ativo=True)
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
        try:
            r = c.post("/reproducao/protocolo-iatf", json={"animais": ["999"], "data_d0": date.today().isoformat()})
            assert r.status_code == 409, r.text
        finally:
            main.app.dependency_overrides[get_current_user] = override_original
