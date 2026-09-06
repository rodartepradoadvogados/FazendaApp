"""
ACHADOS CRÍTICOS 40 e 42 da auditoria de segurança (03/09) — importação de
animais atravessando fazendas:

  * `POST /importar/animais_cadastro` casava o `Animal` GLOBALMENTE por
    `numero`, sem `fazenda_id`, e criava o animal novo sem carimbar a
    fazenda;
  * `POST /importar/dairycomp` fazia o mesmo e ainda anexava `Parto` ao
    animal encontrado, também sem `fazenda_id`.

O cenário concreto de ataque (ou de acidente, que aqui dá no mesmo):
`animal.numero` deixou de ser único globalmente na migração `c24befa94c1b`
— a fazenda 1 e a fazenda 2 podem ter, cada uma, o seu animal "500". Um
administrador da fazenda 2 subindo a planilha do PRÓPRIO rebanho
sobrescrevia o cadastro do animal "500" da fazenda 1 (nome, sexo, raça,
data de nascimento, genealogia, lote) e pendurava partos nele.

Os testes abaixo usam TOKEN DE VERDADE (`criar_token`), não
`dependency_overrides` em `get_fazenda_atual_id`: o que está em julgamento é
o isolamento de ponta a ponta, e falsificar a claim do token deixaria de
fora a própria trava de porta (`exigir_fazenda_selecionada`).

Estilo: mesmo molde de test_trava_fazenda_selecionada.py e
test_isolamento_mastite_del_no_caso.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Dieta, Estoque, Fazenda, Parto, QualidadeLeite,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        s.add(Usuario(id=1, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # O atacante é admin DAS DUAS fazendas — pior caso realista (consultor
        # que atende dois clientes). Mesmo assim, a importação feita com o
        # token da fazenda 2 não pode tocar em nada da fazenda 1.
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=2))

        # O animal "500" da FAZENDA 1 — a vítima.
        s.add(Animal(
            numero="500", nome="Mimosa da Fazenda 1", sexo="F", raca="Girolando",
            data_nasc=date(2020, 1, 1), fazenda_id=1, ativo=True,
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cabecalho(fazenda_id):
    return {"Authorization": f"Bearer {criar_token('admin2', fazenda_id=fazenda_id)}"}


def _csv(texto: str) -> bytes:
    return texto.encode("windows-1252")


def _animal(session: Session, numero: str, fazenda_id: int) -> Animal | None:
    return session.exec(
        select(Animal).where(Animal.numero == numero, Animal.fazenda_id == fazenda_id)
    ).first()


class TestImportarAnimaisCadastroNaoAtravessaFazenda:
    def test_importacao_da_fazenda_2_nao_sobrescreve_animal_da_fazenda_1(self, client):
        c, engine = client
        conteudo = _csv(
            "numero;nome;sexo;raca;data_nasc;lote\n"
            "500;Invasora da Fazenda 2;M;Holandesa;01/01/2024;Lote Roubado\n"
        )
        r = c.post(
            "/importar/animais_cadastro",
            files={"file": ("animais.csv", conteudo, "text/csv")},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        # A fazenda 2 ainda não tinha o "500": tem que ser CRIAÇÃO, nunca
        # "atualização" de um animal que pertence a outro cliente.
        assert r.json()["criados"] == 1, r.json()
        assert r.json()["atualizados"] == 0, r.json()

        with Session(engine) as s:
            vitima = _animal(s, "500", 1)
            assert vitima is not None, "o animal da fazenda 1 sumiu"
            assert vitima.nome == "Mimosa da Fazenda 1", (
                "a importação da fazenda 2 sobrescreveu o cadastro do animal '500' da fazenda 1 — "
                "vazamento/corrupção cross-tenant"
            )
            assert vitima.sexo == "F" and vitima.raca == "Girolando"
            assert vitima.data_nasc == date(2020, 1, 1)

            novo = _animal(s, "500", 2)
            assert novo is not None, "o animal importado não foi criado na fazenda 2"
            assert novo.nome == "Invasora da Fazenda 2"

            # Nenhum registro órfão: dado sem fazenda_id aparece em TODA
            # consulta tolerante do sistema, ou seja, em todas as fazendas.
            orfaos = s.exec(select(Animal).where(Animal.fazenda_id == None)).all()  # noqa: E711
            assert orfaos == [], f"a importação criou animal órfão (sem fazenda_id): {orfaos}"

    def test_genealogia_da_fazenda_2_nao_edita_animal_da_fazenda_1(self, client):
        c, engine = client
        conteudo = _csv("numero;pai_nome;mae_numero\n500;Touro Invasor;999\n")
        r = c.post(
            "/importar/animais_genealogia",
            files={"file": ("genealogia.csv", conteudo, "text/csv")},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        # A fazenda 2 não tem o animal "500" — a rota tem que RECUSAR a linha,
        # não "achar" o animal da fazenda 1 e escrever nele.
        assert r.json()["atualizados"] == 0, r.json()
        assert r.json()["erros"], "a linha devia virar erro de 'animal não encontrado'"

        with Session(engine) as s:
            vitima = _animal(s, "500", 1)
            assert vitima.pai_nome is None, (
                "a importação de genealogia da fazenda 2 gravou pai no animal da fazenda 1"
            )
            assert vitima.mae_numero is None


class TestImportarDairycompNaoAtravessaFazenda:
    def test_dairycomp_da_fazenda_2_nao_altera_nascimento_nem_pendura_parto_na_fazenda_1(self, client):
        c, engine = client
        conteudo = _csv(
            "numero_matriz;data_nascimento;data_parto;ordem_parto\n"
            "500;15/03/2023;10/06/2026;1\n"
        )
        r = c.post(
            "/importar/dairycomp",
            files={"file": ("dairycomp.csv", conteudo, "text/csv")},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            vitima = _animal(s, "500", 1)
            assert vitima.data_nasc == date(2020, 1, 1), (
                "o DairyComp da fazenda 2 reescreveu a data de nascimento do animal da fazenda 1"
            )

            partos_f1 = s.exec(select(Parto).where(Parto.fazenda_id == 1)).all()
            assert partos_f1 == [], "um parto da importação da fazenda 2 foi parar na fazenda 1"

            partos_orfaos = s.exec(select(Parto).where(Parto.fazenda_id == None)).all()  # noqa: E711
            assert partos_orfaos == [], (
                f"a importação criou Parto órfão (sem fazenda_id): {partos_orfaos}"
            )

            # O animal "500" da fazenda 2 nasceu carimbado e com o parto dele.
            novo = _animal(s, "500", 2)
            assert novo is not None
            assert novo.data_nasc == date(2023, 3, 15)
            partos_f2 = s.exec(select(Parto).where(Parto.fazenda_id == 2)).all()
            assert len(partos_f2) == 1
            assert partos_f2[0].animal_id == novo.id

    def test_dedup_de_parto_e_por_fazenda(self, client):
        """O índice de dedup (numero, data_parto) também precisa ser escopado:
        um parto já existente na FAZENDA 1 não pode fazer o parto legítimo da
        fazenda 2 ser silenciosamente descartado."""
        c, engine = client
        with Session(engine) as s:
            animal_f1 = _animal(s, "500", 1)
            s.add(Parto(
                animal_id=animal_f1.id, numero_matriz="500", data_parto=date(2026, 6, 10),
                ordem_parto=3, fazenda_id=1,
            ))
            s.commit()

        conteudo = _csv("numero_matriz;data_parto;ordem_parto\n500;10/06/2026;1\n")
        r = c.post(
            "/importar/dairycomp",
            files={"file": ("dairycomp.csv", conteudo, "text/csv")},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        assert r.json()["criados"] == 1, (
            "o parto da fazenda 2 foi descartado por um parto homônimo da fazenda 1 — "
            f"dedup sem escopo de fazenda: {r.json()}"
        )

        with Session(engine) as s:
            assert len(s.exec(select(Parto).where(Parto.fazenda_id == 1)).all()) == 1
            assert len(s.exec(select(Parto).where(Parto.fazenda_id == 2)).all()) == 1


class TestOutrasImportacoesNaoNascemOrfas:
    """Mesma classe de problema dos achados 40/42 — "dado que nasce sem dono
    é dado que aparece em todas as fazendas" — em duas rotas do mesmo router
    que a auditoria não listou nominalmente."""

    def test_qualidade_leite_importada_nasce_carimbada(self, client):
        """`importar_qualidade_leite` chamava `criar_qualidade_leite(dados,
        session)` POSICIONALMENTE: `user` e `fazenda_id` ficavam com o objeto
        `Depends(...)` não resolvido, `fazenda_id_seguro()` os convertia para
        None e todo registro importado nascia órfão — visível em qualquer
        consulta tolerante, ou seja, em todas as fazendas."""
        c, engine = client
        conteudo = _csv("numero_matriz;data_coleta;ccs;cbt\n500;05/07/2026;181;11\n")
        r = c.post(
            "/importar/qualidade_leite",
            files={"file": ("ql.csv", conteudo, "text/csv")},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        assert r.json()["criados"] == 1, r.json()

        with Session(engine) as s:
            registros = s.exec(select(QualidadeLeite)).all()
            assert len(registros) == 1
            assert registros[0].fazenda_id == 2, (
                f"a coleta importada nasceu com fazenda_id={registros[0].fazenda_id} — "
                "registro órfão aparece na fazenda 1 também"
            )

    def test_backfill_nao_cadastra_ingrediente_de_dieta_de_outra_fazenda(self, client):
        """`POST /importar/backfill` varre os dados já lançados e cadastra os
        itens de estoque citados neles. `Dieta.ingrediente` era a única fonte
        lida SEM filtro de fazenda: o nome do ingrediente da fazenda 1 (que
        pode ser um produto/fórmula que ela não quer expor) virava item de
        estoque cadastrado dentro da fazenda 2."""
        c, engine = client
        with Session(engine) as s:
            s.add(Dieta(ingrediente="Núcleo secreto da Fazenda 1", fazenda_id=1))
            s.add(Dieta(ingrediente="Silagem de milho", fazenda_id=2))
            s.commit()

        r = c.post("/importar/backfill", headers=_cabecalho(2))
        assert r.status_code == 200, r.text
        assert "Silagem de milho" in r.json()["estoque_criados"]
        assert "Núcleo secreto da Fazenda 1" not in r.json()["estoque_criados"], (
            "o backfill da fazenda 2 cadastrou um ingrediente da dieta da fazenda 1"
        )

        with Session(engine) as s:
            nomes = {e.nome for e in s.exec(select(Estoque)).all()}
            assert "Núcleo secreto da Fazenda 1" not in nomes
