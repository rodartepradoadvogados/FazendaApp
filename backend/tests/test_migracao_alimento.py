"""
Testes de CARACTERIZAÇÃO da Fase P0-A do refactor "elimina a camada
Alimento" (ver spec do refactor). Nenhum destes testes prescreve o
comportamento CORRETO — eles fotografam o comportamento ATUAL, para que
qualquer mudança futura no caminho Dieta → Estoque (e no wizard de
Formulação de Dietas, módulo intocável) fique visível em vez de silenciosa.

Se um teste aqui falhar depois de uma mudança de produção, a pergunta certa
não é "conserta o teste" — é "essa mudança de comportamento foi deliberada?".

Contexto (ver también backend/fazenda/api/routers/alimentacao.py e
formulacao_dietas.py): hoje existem três camadas — CategoriaAlimento (árvore
de 2 níveis) → Alimento (conceito nutricional) → Estoque (produto físico,
FK `alimento_id`). O caminho do dinheiro (linha de dieta → baixa física de
estoque) é resolvido por NOME, nunca por id:
  1. `Estoque.nome` == `Dieta.ingrediente` (exato) primeiro;
  2. na falta, via `Alimento.nome` (lowercase/trim) → `Estoque.alimento_id`,
     pegando o primeiro candidato da query arbitrariamente.
A Formulação de Dietas (módulo intocável) tem FKs duras para `alimento.id`
mas resolve sua biblioteca em cascata biblioteca → laudo bromatológico →
template, e hoje só o primeiro e o terceiro braço funcionam de fato porque
`AnaliseBromatologica.alimento_id` nunca é escrito pela API (ver T2).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Alimento, AlimentoNutricional, AnaliseBromatologica, Animal, Dieta, Estoque, Lote, MovimentoEstoque,
)

HOJE = date(2026, 8, 24)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    """Fazenda única, sem multi-fazenda provisionado (fazenda_id=None em
    tudo) — mesmo padrão de test_alimentacao.py. Serve T2/T5/T7/T10/T11, que
    exercem os routers de Alimentação e o `/resolver` de Formulação (este
    último só de LEITURA — não precisa de contrato/módulo comercial porque
    `exigir_modulo_contratado` deixa passar quando `fazenda_id is None`, e o
    usuário abaixo é "dono-equivalente" — ver `eh_email_dono_equivalente`,
    fazenda/auth.py — então também passa por `exigir_admin_ou_consultor_fazenda`
    mesmo sem fazenda selecionada nenhuma)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "jairodarte@gmail.com"  # dono-equivalente — ver docstring acima

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


@pytest.fixture
def client_formulacao():
    """Fixture dedicada ao bloco T-formulação: precisa de uma fazenda REAL
    (contrato ativo + módulo 'formulacao_dietas' contratado), porque esses
    testes exercem o fluxo de ESCRITA (criar/salvar simulação), que exige
    `fazenda_id` resolvido de verdade (`DietaSimulacao.fazenda_id` não é
    Optional — ver docstring de fazenda/models/formulacao.py). O controle de
    acesso completo (quem entra/quem não entra) já está coberto por
    TestControleDeAcesso em test_formulacao_dietas.py; aqui não repetimos —
    só usamos o usuário dono-equivalente para simplificar o setup."""
    from fazenda.models import ContratoFazenda, ContratoFazendaModulo, Fazenda, Lote

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Teste"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="formulacao_dietas", ativo=True))
        s.add(ContratoFazendaModulo(fazenda_id=1, modulo="alimentacao", ativo=True))
        s.add(Lote(codigo="01", nome="Lote 1", fazenda_id=1))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _FakeUser:
        id = 10
        papel = "admin"
        ativo = True
        username = "dono"
        email = "jairodarte@gmail.com"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: 1

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T2 — snapshot de /resolver (o contrato do módulo intocável)
# ---------------------------------------------------------------------------
class TestResolverAlimentoSnapshot:
    """`GET /formulacao/alimentos/{id}/resolver` (formulacao_dietas.py:735)
    resolve em cascata: biblioteca (AlimentoNutricional.alimento_id) → laudo
    bromatológico mais recente → template por categoria. Este é o contrato
    que a Fase 1 do wizard consome; qualquer migração futura da camada
    Alimento precisa preservar EXATAMENTE estas três formas de resposta."""

    def _montar_fazenda(self, engine):
        with Session(engine) as s:
            a_biblioteca = Alimento(nome="Silagem de milho — com biblioteca")
            a_laudo = Alimento(nome="Farelo de soja — só laudo")
            a_vazio = Alimento(nome="Ureia — sem nada")
            s.add(a_biblioteca)
            s.add(a_laudo)
            s.add(a_vazio)
            s.commit()
            s.refresh(a_biblioteca)
            s.refresh(a_laudo)
            s.refresh(a_vazio)

            s.add(AlimentoNutricional(
                alimento_id=a_biblioteca.id, nome=a_biblioteca.nome, categoria_nasem="Forragem",
                conc_pct=0.0, ms_pct=33.24, pb_pct=8.1, fdn_pct=45.0, fda_pct=28.0,
            ))
            # `AnaliseBromatologica.alimento_id` NÃO é preenchido — a API real
            # (POST /alimentacao/analise-bromatologica) não aceita esse campo
            # (ver AnaliseBromatologicaIn, alimentacao.py) — só o texto livre
            # `alimento` casa com `Alimento.nome` (ver T2b abaixo).
            s.add(AnaliseBromatologica(
                data=date(2026, 8, 1), alimento=a_laudo.nome, ms_pct=90.0, pb_pct=46.0, fdn_pct=14.0,
            ))
            s.commit()
            return a_biblioteca.id, a_laudo.id, a_vazio.id

    def test_snapshot_biblioteca_bromatologica_template(self, client):
        c, engine = client
        id_biblioteca, id_laudo, id_vazio = self._montar_fazenda(engine)

        r1 = c.get(f"/formulacao/alimentos/{id_biblioteca}/resolver")
        assert r1.status_code == 200
        corpo1 = r1.json()
        assert corpo1["origem"] == "biblioteca"
        assert corpo1["alimento_nutricional_id"] is not None
        assert corpo1["analise_bromatologica_id"] is None
        assert corpo1["categoria_nasem"] == "Forragem"
        assert corpo1["valores"]["ms_pct"] == 33.24
        assert corpo1["valores"]["pb_pct"] == 8.1

        r2 = c.get(f"/formulacao/alimentos/{id_laudo}/resolver")
        assert r2.status_code == 200
        corpo2 = r2.json()
        assert corpo2["origem"] == "bromatologica"
        assert corpo2["alimento_nutricional_id"] is None
        assert corpo2["analise_bromatologica_id"] is not None
        assert corpo2["categoria_nasem"] == "Outros"  # braço bromatológico sempre cai em "Outros"
        assert corpo2["valores"]["ms_pct"] == 90.0
        assert corpo2["valores"]["pb_pct"] == 46.0
        assert corpo2["valores"]["fdn_pct"] == 14.0
        # Campos do template que o laudo NÃO preencheu continuam com o
        # template de "Outros" por baixo (o laudo só sobrescreve o que tem).
        assert corpo2["valores"]["ca_pct"] == 0.6

        r3 = c.get(f"/formulacao/alimentos/{id_vazio}/resolver")
        assert r3.status_code == 200
        corpo3 = r3.json()
        assert corpo3["origem"] == "template"
        assert corpo3["alimento_nutricional_id"] is None
        assert corpo3["analise_bromatologica_id"] is None
        assert corpo3["categoria_nasem"] == "Outros"
        assert corpo3["valores"]["ms_pct"] == 88.0  # template puro de "Outros"

    def test_laudo_bromatologico_para_de_resolver_se_o_alimento_e_renomeado(self, client):
        """RISCO REAL, não comportamento desejado: como `AnaliseBromatologica.
        alimento_id` nunca é escrito hoje, o braço bromatológico de
        `/resolver` só casa por IGUALDADE EXATA DE STRING entre
        `AnaliseBromatologica.alimento` e `Alimento.nome`. Renomear o
        Alimento — uma operação de cadastro comum e sem nada de errado em si
        — quebra silenciosamente esse vínculo: o laudo continua no banco,
        intacto, mas "some" da Etapa 1 do wizard e o sistema cai no template
        genérico sem avisar ninguém. Este teste existe para que a migração
        futura (que vai ligar o produto direto à categoria) tenha a chance de
        CORRIGIR isso — casando por id em vez de nome — sem que a correção
        passe despercebida como "só mais uma refatoração"."""
        c, engine = client
        with Session(engine) as s:
            alimento = Alimento(nome="Silagem pré-secada")
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            alimento_id = alimento.id
            s.add(AnaliseBromatologica(data=date(2026, 8, 1), alimento="Silagem pré-secada", ms_pct=45.0))
            s.commit()

        r_antes = c.get(f"/formulacao/alimentos/{alimento_id}/resolver")
        assert r_antes.json()["origem"] == "bromatologica"

        r_renomear = c.put(
            f"/alimentacao/alimentos/{alimento_id}",
            json={"nome": "Silagem pré-secada (renomeada)", "estoque_ids": []},
        )
        assert r_renomear.status_code == 200

        r_depois = c.get(f"/formulacao/alimentos/{alimento_id}/resolver")
        assert r_depois.status_code == 200
        # O laudo continua existindo no banco (não foi apagado)...
        with Session(engine) as s:
            laudos = s.exec(select(AnaliseBromatologica)).all()
            assert len(laudos) == 1
            assert laudos[0].alimento == "Silagem pré-secada"  # nome antigo, intacto
        # ...mas /resolver não acha mais, porque o nome não bate mais.
        assert r_depois.json()["origem"] == "template"


# ---------------------------------------------------------------------------
# T5 — detector de colisão de nomes com a biblioteca semente
# ---------------------------------------------------------------------------
class TestColisaoComBibliotecaSemente:
    """A biblioteca de referência da Formulação (`_BIBLIOTECA_SEMENTE_BRUTA`,
    fazenda/rules/nutricao/biblioteca.py) tem 12 itens fixos ("Silagem de
    milho", "Caroço de algodão", "Farelo de soja"...). Uma futura ligação
    direta Estoque→categoria vai precisar saber quais produtos de estoque da
    fazenda colidem de nome com esses 12 itens (candidatos naturais a
    "casarem sozinhos" com a biblioteca). Este teste não afirma nada sobre OS
    DADOS de uma fazenda real — só comprova que o DETECTOR funciona: um caso
    de colisão conhecida bate, um caso sem colisão não bate."""

    def _nomes_biblioteca_semente(self) -> set[str]:
        from fazenda.rules.nutricao.biblioteca import biblioteca_semente
        from fazenda.rules.busca import normalizar_busca
        return {normalizar_busca(item["nome"]) for item in biblioteca_semente()}

    def _detectar_colisoes(self, nomes_estoque: list[str]) -> dict[str, str]:
        """Para cada nome de produto de estoque, devolve o nome da semente
        colidido (mesma normalização de busca — ignora caixa/acento/hífen/
        underscore/espaço, ver fazenda.rules.busca.normalizar_busca) ou
        None se não colidir com nenhum dos 12 itens semente."""
        from fazenda.rules.nutricao.biblioteca import biblioteca_semente
        from fazenda.rules.busca import normalizar_busca
        semente_por_norm = {normalizar_busca(item["nome"]): item["nome"] for item in biblioteca_semente()}
        colisoes = {}
        for nome in nomes_estoque:
            achado = semente_por_norm.get(normalizar_busca(nome))
            if achado:
                colisoes[nome] = achado
        return colisoes

    def test_biblioteca_semente_tem_12_itens_com_os_nomes_esperados(self):
        nomes = self._nomes_biblioteca_semente()
        assert len(nomes) == 12
        from fazenda.rules.busca import normalizar_busca
        for esperado in ("Silagem de milho", "Caroço de algodão", "Farelo de soja"):
            assert normalizar_busca(esperado) in nomes

    def test_detecta_colisao_de_nome_ignorando_caixa_acento_e_separador(self):
        # "silagem_de_milho" (minúsculo, underscore) precisa colidir com a
        # semente "Silagem de milho" — mesma normalização usada em qualquer
        # busca do sistema (rules/busca.py).
        nomes_estoque = ["silagem_de_milho", "Farelo de Soja 45%", "Produto totalmente novo sem colisão"]
        colisoes = self._detectar_colisoes(nomes_estoque)
        assert colisoes["silagem_de_milho"] == "Silagem de milho"
        assert "Produto totalmente novo sem colisão" not in colisoes
        # "Farelo de Soja 45%" tem texto extra (o "45%") — não é igualdade
        # exata normalizada, então HOJE não colide (relatório abaixo mostra
        # isso explicitamente — colisão por igualdade exata, não por conter).
        assert "Farelo de Soja 45%" not in colisoes

    def test_relatorio_de_colisao_para_uma_fazenda_de_teste(self, capsys):
        """Monta uma fazenda de teste com produtos de estoque (alguns batem
        na semente, outros não) e IMPRIME o relatório — não é pass/fail sobre
        os dados, é a demonstração de que o detector roda de ponta a ponta."""
        produtos_da_fazenda = [
            "Silagem de milho", "Farelo de soja", "Ração Teck Milk 24%",
            "caroço-de-algodão", "Sal mineral proprietário",
        ]
        colisoes = self._detectar_colisoes(produtos_da_fazenda)
        print("\n--- Relatório de colisão com a biblioteca semente ---")
        for produto in produtos_da_fazenda:
            achado = colisoes.get(produto)
            print(f"  {produto!r:45s} -> {'COLIDE com ' + repr(achado) if achado else 'sem colisão'}")
        saida = capsys.readouterr().out
        assert "COLIDE com 'Silagem de milho'" in saida
        assert "COLIDE com 'Caroço de algodão'" in saida
        assert "Ração Teck Milk 24%" in saida and "sem colisão" in saida
        assert colisoes == {
            "Silagem de milho": "Silagem de milho",
            "Farelo de soja": "Farelo de soja",
            "caroço-de-algodão": "Caroço de algodão",
        }


# ---------------------------------------------------------------------------
# T7 — classificação de resolução dos ingredientes de dieta
# ---------------------------------------------------------------------------
def _classificar_resolucao(session: Session, fazenda_id: int | None, ingrediente: str) -> str:
    """Reproduz a MESMA cascata usada por `_dar_baixa_automatica` e
    `_resolver_estoque_item` (fazenda/api/routers/alimentacao.py) — nome
    exato de Estoque primeiro, depois via `Alimento.nome` — mas em vez de
    pegar `candidatos[0]` arbitrariamente (o que a produção faz, ver T11),
    CONTA quantos candidatos existiriam em cada braço, para classificar:
      - "resolve_1": exatamente um candidato — sem ambiguidade.
      - "resolve_0": nenhum candidato — ingrediente do plano sem item físico
        associado (comum e válido; não gera aviso hoje).
      - "ambiguo": mais de um candidato — hoje a produção resolveria
        arbitrariamente pelo primeiro da query (T11); depois do refactor esse
        conjunto de nomes AMBÍGUOS precisa continuar sendo o mesmo conjunto,
        mesmo que o tratamento (debitar x recusar) mude.
    Reaproveita `_estoque_por_alimento` da própria produção (em vez de
    duplicar a lógica de agrupamento) para não divergir do comportamento
    real por um bug de cópia neste helper de teste."""
    from fazenda.api.routers.alimentacao import _estoque_por_alimento

    query = select(Estoque).where(Estoque.nome == ingrediente)
    if fazenda_id is not None:
        query = query.where(Estoque.fazenda_id == fazenda_id)
    exatos = session.exec(query).all()
    if exatos:
        return "ambiguo" if len(exatos) > 1 else "resolve_1"

    estoque_por_alimento, _ = _estoque_por_alimento(session, fazenda_id)
    candidatos = estoque_por_alimento.get((ingrediente or "").strip().lower(), [])
    if len(candidatos) > 1:
        return "ambiguo"
    if len(candidatos) == 1:
        return "resolve_1"
    return "resolve_0"


class TestClassificacaoResolucaoIngredientes:
    """Guarda-costas do caminho do dinheiro: o CONJUNTO {ingrediente:
    classificação} tem que ser idêntico antes e depois da migração da camada
    Alimento — mesmo que o mecanismo interno mude por completo."""

    def test_classifica_os_tres_casos(self, client):
        c, engine = client
        with Session(engine) as s:
            # Caso 1 — resolve_1: nome exato bate direto num único Estoque.
            s.add(Estoque(nome="Silagem de milho", categoria="alimento", quantidade=500.0, unidade="kg"))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))

            # Caso 2 — resolve_0: não bate em Estoque nem em Alimento nenhum.
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Suplemento fantasma", quantidade=5.0, unidade="kg"))

            # Caso 3 — ambíguo: não há Estoque "Farelo de soja" exato, mas o
            # Alimento "Farelo de soja" está vinculado a DOIS itens de estoque.
            alimento = Alimento(nome="Farelo de soja")
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            s.add(Estoque(nome="Farelo de soja — Fornecedor A", categoria="alimento",
                          quantidade=100.0, unidade="kg", alimento_id=alimento.id))
            s.add(Estoque(nome="Farelo de soja — Fornecedor B", categoria="alimento",
                          quantidade=200.0, unidade="kg", alimento_id=alimento.id))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Farelo de soja", quantidade=3.0, unidade="kg"))
            s.commit()

        with Session(engine) as s:
            ingredientes = sorted({d.ingrediente for d in s.exec(select(Dieta)).all()})
            classificacao = {ing: _classificar_resolucao(s, None, ing) for ing in ingredientes}

        assert classificacao == {
            "Silagem de milho": "resolve_1",
            "Suplemento fantasma": "resolve_0",
            "Farelo de soja": "ambiguo",
        }


# ---------------------------------------------------------------------------
# T10 — snapshot da baixa automática
# ---------------------------------------------------------------------------
class TestSnapshotBaixaAutomatica:
    """Cenário determinístico (dieta + estoque conhecidos, dias decorridos
    controlados como em test_alimentacao.py::TestBaixaAutomatica) — captura
    EXATAMENTE quais MovimentoEstoque nascem: item a item, quantidade a
    quantidade. `MovimentoEstoque` não tem uma coluna "sinal" própria — o
    sentido da baixa é dado pelo texto de `movimento` ("Saída de ajuste");
    `quantidade` é sempre gravada em valor absoluto (ver
    fazenda.rules.estoque_baixa.movimentar)."""

    def test_baixa_gera_um_movimento_por_ingrediente_com_valores_exatos(self, client):
        c, engine = client
        with Session(engine) as s:
            # Baixa automática por dias decorridos agora exige opt-in explícito
            # por lote (`Lote.modo_baixa_estoque == "automatica"`) — sem o
            # cadastro, o lote cai no padrão "consumo_real" e este cenário
            # determinístico não debitaria nada.
            s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque="automatica"))
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Animal(numero="2", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Silagem de milho", quantidade=20.0, unidade="kg"))
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Ração", quantidade=5.0, unidade="kg"))
            s.add(Estoque(nome="Silagem de milho", categoria="alimento", quantidade=1000.0, unidade="kg"))
            s.add(Estoque(nome="Ração", categoria="alimento", quantidade=1000.0, unidade="saca 30kg"))
            s.commit()

        c.get("/alimentacao/")  # estabelece baseline = hoje
        with Session(engine) as s:
            from fazenda.models import AlimentacaoEstado
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=4)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200

        with Session(engine) as s:
            movimentos = {m.nome_item: m for m in s.exec(select(MovimentoEstoque)).all()}

        assert set(movimentos) == {"Silagem de milho", "Ração"}

        m_silagem = movimentos["Silagem de milho"]
        # 20kg/cabeça * 2 animais * 4 dias = 160kg, sem conversão (Estoque em kg).
        assert m_silagem.quantidade == 160.0
        assert m_silagem.unidade == "kg"
        assert m_silagem.movimento == "Saída de ajuste"
        assert m_silagem.origem_tipo == "alimentacao"
        assert m_silagem.data_movimento == date.today()

        m_racao = movimentos["Ração"]
        # 5kg/cabeça * 2 animais * 4 dias = 40kg -> 40kg / 30kg/saca = 1.3333 sacas.
        assert m_racao.quantidade == round(40.0 / 30.0, 4)
        assert m_racao.unidade == "saca 30kg"
        assert m_racao.movimento == "Saída de ajuste"

        with Session(engine) as s:
            silagem_estoque = s.exec(select(Estoque).where(Estoque.nome == "Silagem de milho")).first()
            racao_estoque = s.exec(select(Estoque).where(Estoque.nome == "Ração")).first()
            assert silagem_estoque.quantidade == 840.0  # 1000 - 160
            assert racao_estoque.quantidade == round(1000.0 - 40.0 / 30.0, 4)


# ---------------------------------------------------------------------------
# T11 — caracteriza a escolha arbitrária de candidatos[0]
# ---------------------------------------------------------------------------
class TestEscolhaArbitrariaDeCandidato:
    """Um `Alimento` com DOIS itens de `Estoque` vinculados é uma ambiguidade
    de verdade — não há como saber qual dos dois a dieta "quis dizer". Hoje o
    sistema não recusa nem avisa: debita cegamente `candidatos[0]` (o
    primeiro que a query devolve) e deixa o outro intocado.

    ESTE COMPORTAMENTO É ARBITRÁRIO e será trocado por "não debita e registra
    ambiguidade" numa fase futura do refactor — este teste existe só para que
    essa troca seja uma decisão DELIBERADA (o teste vai quebrar e alguém vai
    precisar decidir o que documentar no lugar), não um efeito colateral
    silencioso de mexer em outra coisa."""

    def test_debita_apenas_um_dos_dois_itens_vinculados(self, client):
        c, engine = client
        with Session(engine) as s:
            # Mesmo motivo do teste acima: baixa automática exige opt-in por
            # lote (`modo_baixa_estoque == "automatica"`).
            s.add(Lote(codigo="01", nome="Alta", modo_baixa_estoque="automatica"))
            s.add(Animal(numero="1", categoria_abrev="Vaca", sexo="F", grupo_primario="01 - Alta", ativo=True))
            alimento = Alimento(nome="Farelo de soja")
            s.add(alimento)
            s.commit()
            s.refresh(alimento)
            s.add(Estoque(nome="Farelo de soja — Lote A", categoria="alimento",
                          quantidade=500.0, unidade="kg", alimento_id=alimento.id))
            s.add(Estoque(nome="Farelo de soja — Lote B", categoria="alimento",
                          quantidade=500.0, unidade="kg", alimento_id=alimento.id))
            # Dieta casa pelo NOME DO ALIMENTO (não bate em nenhum Estoque.nome
            # exato) — é exatamente o caminho que cai em `_estoque_por_alimento`.
            s.add(Dieta(lote=1, categoria="Vaca", ingrediente="Farelo de soja", quantidade=10.0, unidade="kg"))
            s.commit()
            # Query real usada por `_estoque_por_alimento`/`_dar_baixa_automatica`
            # (SELECT sem ORDER BY) — captura qual item o SQLite devolve
            # primeiro hoje, para o assert abaixo não depender de premissa
            # implícita sobre ordem de inserção.
            from fazenda.api.routers.alimentacao import _estoque_por_alimento
            estoque_por_alimento, _ = _estoque_por_alimento(s, None)
            id_esperado_debitado = estoque_por_alimento["farelo de soja"][0]["id"]

        c.get("/alimentacao/")  # baseline

        with Session(engine) as s:
            from fazenda.models import AlimentacaoEstado
            estado = s.get(AlimentacaoEstado, 1)
            estado.ultima_data_deducao = date.today() - timedelta(days=1)
            s.add(estado)
            s.commit()

        r = c.get("/alimentacao/")
        assert r.status_code == 200

        with Session(engine) as s:
            item_a = s.exec(select(Estoque).where(Estoque.nome == "Farelo de soja — Lote A")).first()
            item_b = s.exec(select(Estoque).where(Estoque.nome == "Farelo de soja — Lote B")).first()
            debitado = item_a if item_a.id == id_esperado_debitado else item_b
            intacto = item_b if debitado is item_a else item_a

            # 10kg/cabeça * 1 animal * 1 dia = 10kg debitados de UM só.
            assert debitado.quantidade == 490.0
            assert intacto.quantidade == 500.0  # o outro nem foi tocado

            movimentos = s.exec(select(MovimentoEstoque)).all()
            assert len(movimentos) == 1  # uma única baixa, não duas
            assert movimentos[0].estoque_id == debitado.id


# ---------------------------------------------------------------------------
# T-formulação — a Formulação de Dietas não pode travar
# ---------------------------------------------------------------------------
class TestFormulacaoNaoTrava:
    """Requisito explícito do usuário: o filtro futuro (que vai restringir a
    lista `cadastrados` de /formulacao/alimentos a produtos migrados) NÃO
    pode travar o processo de formulação em si. Estes três testes comprovam
    que hoje a Formulação já não depende de Estoque em ponto nenhum do
    caminho calcular→salvar→aplicar, e que biblioteca/cadastrados já
    trafegam como listas independentes."""

    _ANIMAL = {
        "estado_fisiologico": "vaca_lactante", "raca": "Holandes", "peso_vivo_kg": 650.0, "peso_maturo_kg": 680.0,
        "ecc": 3.0, "paridade": 2.0, "del_dias": 150, "eq_cms": 8,
        "producao_leite_kg_dia": 35.0, "gordura_leite_pct": 3.8, "proteina_leite_pct": 3.2,
    }

    def test_simulacao_usa_item_da_biblioteca_mestre_sem_nenhum_alimento_vinculado(self, client_formulacao):
        """`AlimentoNutricional.alimento_id` é Optional DE PROPÓSITO — as
        linhas da biblioteca MESTRE CowData nascem com `fazenda_id IS NULL`
        E `alimento_id IS NULL` (ver docstring da classe,
        fazenda/models/formulacao.py). Simula uma linha assim (sem passar
        pela API de criação, que hoje recusa `fazenda_id=None` — ver
        `criar_alimento_nutricional` — mas é exatamente como o seed real da
        biblioteca mestre povoa a tabela) e usa na simulação: nenhum
        `Alimento` precisa existir para o cálculo funcionar."""
        c, engine = client_formulacao
        with Session(engine) as s:
            mestre = AlimentoNutricional(
                fazenda_id=None, alimento_id=None, nome="Silagem de milho (mestre)",
                categoria_nasem="Forragem", conc_pct=0.0, ms_pct=33.24, pb_pct=8.1, fdn_pct=45.0,
            )
            s.add(mestre)
            s.commit()
            s.refresh(mestre)
            mestre_id = mestre.id

        # Confirma que a linha mestre aparece na listagem antes de usá-la.
        biblioteca = c.get("/formulacao/alimentos").json()["biblioteca"]
        item_biblioteca = next(a for a in biblioteca if a["id"] == mestre_id)
        assert item_biblioteca["eh_mestre"] is True
        assert item_biblioteca["alimento_id"] is None

        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Sim biblioteca sem alimento", "lote": 1}).json()["id"]
        payload = {
            "animal": self._ANIMAL,
            "itens": [
                {
                    "nome": "Silagem de milho (mestre)", "categoria_nasem": "Forragem", "conc_pct": 0.0,
                    "proporcao_ms_pct": 60.0, "origem": "biblioteca",
                    "alimento_id": None, "alimento_nutricional_id": mestre_id,
                    "ms_pct": 33.24, "pb_pct": 8.1, "fdn_pct": 45.0,
                },
                {
                    "nome": "Farelo de soja avulso", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0,
                    "proporcao_ms_pct": 40.0, "origem": "manual",
                },
            ],
        }
        r = c.put(f"/formulacao/simulacoes/{sim_id}", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["resultado"]["consumo"]["cms_kg_dia"] is not None

        with Session(engine) as s:
            # Nenhum Alimento foi criado em lugar nenhum deste fluxo.
            assert s.exec(select(Alimento)).all() == []
            item_salvo = s.exec(select(AlimentoNutricional).where(AlimentoNutricional.id == mestre_id)).first()
            assert item_salvo.alimento_id is None  # continua sem vínculo — e tudo funcionou

    def test_calcular_e_salvar_com_ingrediente_sem_item_de_estoque(self, client_formulacao):
        """Ingrediente "manual" comum, sem `alimento_id`/`alimento_nutricional_id`
        nenhum e SEM NENHUM item de Estoque cadastrado na fazenda inteira —
        `/calcular` e o salvamento da simulação nunca tocam a tabela Estoque,
        então isso já funciona hoje sem exigir vínculo físico nenhum."""
        c, engine = client_formulacao
        with Session(engine) as s:
            assert s.exec(select(Estoque)).all() == []  # de propósito: zero itens de estoque na fazenda

        payload_calcular = {
            "animal": self._ANIMAL,
            "itens": [
                {"nome": "Silagem de milho", "categoria_nasem": "Forragem", "conc_pct": 0.0,
                 "proporcao_ms_pct": 60.0, "origem": "manual"},
                {"nome": "Farelo de soja", "categoria_nasem": "Concentrado proteico", "conc_pct": 100.0,
                 "proporcao_ms_pct": 40.0, "origem": "manual"},
            ],
        }
        r_calc = c.post("/formulacao/calcular", json=payload_calcular)
        assert r_calc.status_code == 200, r_calc.text
        assert r_calc.json()["consumo"]["cms_kg_dia"] is not None

        sim_id = c.post("/formulacao/simulacoes", json={"nome": "Sem estoque", "lote": 1}).json()["id"]
        r_salvar = c.put(f"/formulacao/simulacoes/{sim_id}", json=payload_calcular)
        assert r_salvar.status_code == 200, r_salvar.text

        with Session(engine) as s:
            # Ainda zero — salvar a simulação não cria/exige Estoque nenhum.
            assert s.exec(select(Estoque)).all() == []

    def test_listagem_de_alimentos_devolve_biblioteca_e_cadastrados_independentes(self, client_formulacao):
        """`GET /formulacao/alimentos` devolve dois arrays SEM relação de
        dependência um com o outro: `biblioteca` (AlimentoNutricional,
        template/composição) e `cadastrados` (Alimento, o cadastro que o
        refactor futuro vai substituir). Um filtro que restrinja só
        `cadastrados` (ex.: a produtos já migrados) não pode, por construção,
        afetar `biblioteca` — são coleções e chaves primárias diferentes."""
        c, engine = client_formulacao
        with Session(engine) as s:
            s.add(Alimento(nome="Alimento cadastrado sem biblioteca", fazenda_id=1))
            s.add(AlimentoNutricional(
                fazenda_id=None, alimento_id=None, nome="Item só de biblioteca, sem cadastro",
                categoria_nasem="Outros", conc_pct=0.0,
            ))
            s.commit()

        corpo = c.get("/formulacao/alimentos").json()
        assert set(corpo.keys()) == {"biblioteca", "cadastrados"}
        nomes_biblioteca = {a["nome"] for a in corpo["biblioteca"]}
        nomes_cadastrados = {a["nome"] for a in corpo["cadastrados"]}
        assert "Item só de biblioteca, sem cadastro" in nomes_biblioteca
        assert "Item só de biblioteca, sem cadastro" not in nomes_cadastrados
        assert "Alimento cadastrado sem biblioteca" in nomes_cadastrados
        assert "Alimento cadastrado sem biblioteca" not in nomes_biblioteca
