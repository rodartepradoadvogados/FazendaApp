"""
Garante que os modelos de CSV baixáveis em Configurações > Importar dados
(colunas_csv + exemplo) realmente funcionam quando reenviados — monta um CSV
de verdade com essas colunas/valores e roda pelo MESMO caminho real (upload
de arquivo) usado pelo usuário, tanto para as 5 categorias novas quanto para
as 10 que reaproveitam o parser rico do Ideagri.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers.importar import CATEGORIAS_EXISTENTES, CATEGORIAS_NOVAS
from fazenda.models import Animal, Fornecedor


def _csv_de_modelo(colunas_csv: list[str], exemplo: list[str]) -> bytes:
    texto = ";".join(colunas_csv) + "\r\n" + ";".join(exemplo) + "\r\n"
    return texto.encode("windows-1252")


@pytest.fixture
def client():
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

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


class TestModelosCategoriasNovas:
    @pytest.mark.parametrize("categoria", list(CATEGORIAS_NOVAS.keys()))
    def test_modelo_e_aceito_pelo_endpoint_real(self, client, categoria):
        c, engine = client
        cfg = CATEGORIAS_NOVAS[categoria]

        # produtos_estoque/estoque_movimento e fornecedores dependem de
        # cadastro prévio para "casar" plenamente — aqui só garantimos que o
        # arquivo é bem formado e não quebra o parser (erros de negócio, como
        # "fornecedor não encontrado", não invalidam o modelo de colunas).
        if categoria == "fornecedores":
            # Fornecedores não depende de nada prévio — roda limpo.
            content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
            r = c.post(f"/importar/{categoria}", files={"file": ("modelo.csv", content, "text/csv")})
            assert r.status_code == 200
            assert r.json()["criados"] == 1
            return

        if categoria == "estoque_movimento":
            with Session(engine) as s:
                from fazenda.models import Estoque
                s.add(Estoque(nome=cfg["exemplo"][0], categoria="alimento", quantidade=1000))
                s.commit()

        if categoria == "baixas_pendencias_agenda":
            # A linha de exemplo é do tipo evento_sanitario/gatilho=nascimento — a
            # matriz 464 precisa existir e ter nascido em 10/04/2026 (mesma data
            # da pendência) para o evento cadastrado abaixo "casar" com a linha.
            from datetime import date
            from fazenda.models import EventoSanitario
            with Session(engine) as s:
                s.add(Animal(numero="464", data_nasc=date(2026, 4, 10), sexo="F"))
                s.add(EventoSanitario(
                    nome="Brucelose B19", tipo_agendamento="evento", gatilho="nascimento",
                    produto_padrao="Vacina B19", dose_padrao=2, unidade_padrao="ml", via_padrao="Subcutânea",
                ))
                s.commit()

        content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
        extra = {"data_controle": "2026-07-08"} if cfg.get("precisa_data_controle") else {}
        r = c.post(f"/importar/{categoria}", files={"file": ("modelo.csv", content, "text/csv")}, data=extra)
        assert r.status_code == 200
        d = r.json()
        assert not d.get("erros"), f"{categoria}: modelo gerou erro(s): {d.get('erros')}"


class TestModelosCategoriasExistentes:
    @pytest.mark.parametrize("categoria", list(CATEGORIAS_EXISTENTES.keys()))
    def test_modelo_e_aceito_pelo_upload_real(self, client, categoria):
        c, engine = client
        cfg = CATEGORIAS_EXISTENTES[categoria]
        content = _csv_de_modelo(cfg["colunas_csv"], cfg["exemplo"])
        r = c.post(f"/upload/{cfg['tipo_upload']}", files={"file": ("modelo.csv", content, "text/csv")})
        assert r.status_code == 200, f"{categoria} ({cfg['tipo_upload']}): {r.text}"


class TestPlanoContaGerencialReal:
    def test_arquivo_real_do_usuario_e_aceito(self, client):
        """Regressão com uma amostra real do arquivo anexado pelo usuário."""
        c, engine = client
        linhas = [
            "N° ct. ger.;Nome ct. ger.;Ativa;Part. ativ.;Fluxo;Tipo F/V;",
            "2;Receita;Não;Não;Não;;",
            "2.01;Pecuária;Não;Não;Não;;",
            "2.01.01.01;Leite indústria;Sim;Sim;Sim;;",
            "3;Despesa;Não;Não;Não;;",
            "3.01.01.01;Concentrado protéico;Sim;Sim;Sim;Variável;",
        ]
        content = ("\r\n".join(linhas) + "\r\n").encode("windows-1252")
        r = c.post("/upload/plano_conta_gerencial", files={"file": ("plano.csv", content, "text/csv")})
        assert r.status_code == 200
        assert r.json()["registros"] == 5

        # A conta postável (Sim/ativa) aparece nas opções do lançamento financeiro.
        opcoes = c.get("/financeiro/opcoes").json()
        codigos = {x["codigo"] for x in opcoes["contas_gerenciais"]}
        assert "3.01.01.01" in codigos
        assert "2.01.01.01" in codigos
        # O grupo "2.01 - Pecuária" é inativo (não postável) e não deve aparecer.
        assert "2.01" not in codigos


class TestControleLeiteiroSimplificado:
    def test_calcula_total_e_puxa_del_da_ficha(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Animal, ControleLeiteiro

        with Session(engine) as s:
            s.add(Animal(numero="464", ativo=True, del_dias=120))
            s.commit()

        content = _csv_de_modelo(["numero_matriz", "ordenha1_kg", "ordenha2_kg"], ["464", "14,5", "13,0"])
        r = c.post(
            "/importar/controle_leiteiro_simples",
            files={"file": ("modelo.csv", content, "text/csv")},
            data={"data_controle": "2026-07-08"},
        )
        assert r.status_code == 200
        assert r.json()["criados"] == 1
        assert r.json()["erros"] == []

        with Session(engine) as s:
            registro = s.exec(select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == "464")).first()
            assert registro.producao_kg == 27.5
            assert registro.del_no_controle == 120
            assert registro.data_controle == date(2026, 7, 8)

    def test_linha_sem_numero_da_erro_sem_travar_arquivo(self, client):
        c, _ = client
        texto = "numero_matriz;ordenha1_kg;ordenha2_kg\r\n;14,5;13,0\r\n464;10,0;9,0\r\n"
        r = c.post(
            "/importar/controle_leiteiro_simples",
            files={"file": ("modelo.csv", texto.encode("windows-1252"), "text/csv")},
            data={"data_controle": "2026-07-08"},
        )
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["criados"] == 1
        assert len(corpo["erros"]) == 1


class TestAnimaisCadastroEmLote:
    def test_cria_e_atualiza_por_numero(self, client):
        c, engine = client
        from datetime import date
        from fazenda.models import Animal

        texto = (
            "numero;nome;sexo;raca;data_nasc;lote;data_entrada\r\n"
            "465;Mimosa;F;Girolando;10/03/2024;01 - BEZ 1 (0 A 30);10/03/2024\r\n"
        )
        r = c.post("/importar/animais_cadastro", files={"file": ("modelo.csv", texto.encode("windows-1252"), "text/csv")})
        assert r.status_code == 200
        assert r.json()["criados"] == 1

        with Session(engine) as s:
            animal = s.exec(select(Animal).where(Animal.numero == "465")).first()
            assert animal.nome == "Mimosa"
            assert animal.sexo == "F"
            assert animal.grupo_primario == "01 - BEZ 1 (0 A 30)"
            assert animal.grupo_manual is True
            assert animal.data_nasc == date(2024, 3, 10)

        # Reenvio com lote diferente atualiza em vez de duplicar.
        texto2 = (
            "numero;nome;sexo;raca;data_nasc;lote;data_entrada\r\n"
            "465;Mimosa;F;Girolando;10/03/2024;02 - BEZ 2;10/03/2024\r\n"
        )
        r2 = c.post("/importar/animais_cadastro", files={"file": ("modelo.csv", texto2.encode("windows-1252"), "text/csv")})
        assert r2.json()["atualizados"] == 1
        with Session(engine) as s:
            animais = s.exec(select(Animal).where(Animal.numero == "465")).all()
            assert len(animais) == 1
            assert animais[0].grupo_primario == "02 - BEZ 2"

    def test_linha_sem_numero_da_erro(self, client):
        c, _ = client
        texto = "numero;nome;sexo;raca;data_nasc;lote;data_entrada\r\n;Mimosa;F;Girolando;;;\r\n"
        r = c.post("/importar/animais_cadastro", files={"file": ("modelo.csv", texto.encode("windows-1252"), "text/csv")})
        assert r.status_code == 200
        assert r.json()["erros"]


class TestBackfillFornecedoresEstoque:
    def test_cadastra_fornecedores_e_itens_faltantes(self, client):
        c, engine = client
        from fazenda.models import ContaGerencial, CurvaABC, Dieta, Estoque, Fornecedor, LancamentoItem, Sanidade

        with Session(engine) as s:
            s.add(ContaGerencial(fornecedor_cliente="Agropecuária Central", valor_total=100))
            s.add(ContaGerencial(fornecedor_cliente="Agropecuária Central", valor_total=50))  # duplicado, não deve duplicar
            s.add(ContaGerencial(fornecedor_cliente=None, valor_total=10))
            s.add(CurvaABC(produto="Sal mineral"))
            s.add(LancamentoItem(numero_lancamento="LC-1", produto="Concentrado protéico", valor_total=10))
            s.add(Dieta(lote=1, ingrediente="Silagem"))
            s.add(Sanidade(numero_matriz="1", produto="Vacina X"))
            # Já existentes — não devem ser recriados nem duplicados.
            s.add(Fornecedor(nome="Agropecuária Central", tipo="fornecedor"))
            s.add(Estoque(nome="Sal mineral", quantidade=100))
            s.commit()

        r = c.post("/importar/backfill")
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["total_fornecedores_criados"] == 0  # já existia
        assert set(corpo["estoque_criados"]) == {"Concentrado protéico", "Silagem", "Vacina X"}
        assert corpo["total_estoque_criados"] == 3

        with Session(engine) as s:
            fornecedores = s.exec(select(Fornecedor)).all()
            assert len(fornecedores) == 1  # não duplicou o já existente
            nomes_estoque = {e.nome for e in s.exec(select(Estoque)).all()}
            assert nomes_estoque == {"Sal mineral", "Concentrado protéico", "Silagem", "Vacina X"}

    def test_idempotente_ao_rodar_duas_vezes(self, client):
        c, engine = client
        from fazenda.models import ContaGerencial

        with Session(engine) as s:
            s.add(ContaGerencial(fornecedor_cliente="Fornecedor Novo", valor_total=100))
            s.commit()

        r1 = c.post("/importar/backfill")
        assert r1.json()["total_fornecedores_criados"] == 1
        r2 = c.post("/importar/backfill")
        assert r2.json()["total_fornecedores_criados"] == 0
