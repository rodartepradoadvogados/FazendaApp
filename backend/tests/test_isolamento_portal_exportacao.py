"""
ACHADO CRÍTICO 49 da auditoria de segurança (03/09) — o pior VAZAMENTO do
relatório, porque manda o dado para FORA do sistema, por e-mail:

  * `POST /portal/exportar` montava o ZIP com 10 tabelas (Animal, Servico,
    Parto, ControleLeiteiro, Estoque, MovimentoEstoque, Sanidade,
    CompraAnimal, VendaAnimal, ContaGerencial) SEM nenhum filtro de
    `fazenda_id` — qualquer admin de qualquer fazenda-cliente recebia no
    próprio e-mail o banco inteiro de TODOS os outros clientes da
    plataforma;
  * `POST /portal/email` chamava `dre()/rmca()/custo_litro_leite()` como
    função Python pura, sem `fazenda_id` — o parâmetro ficava com o objeto
    `Depends(...)` não resolvido, `fazenda_id_seguro()` o convertia para
    None e o filtro por fazenda de dentro do relatório desligava inteiro;
  * `POST /portal/email` ainda aceita qualquer `usuario_id` como
    destinatário, sem conferir a fazenda dele — o relatório da fazenda 2
    podia ser despachado para o e-mail de um funcionário da fazenda 1
    (`enviar_mensagem` e `delegar_tarefa` já validavam isso, esta rota
    não).

Todos os testes usam TOKEN DE VERDADE (`criar_token`) — é o isolamento de
ponta a ponta que está em julgamento. O `enviar_email` é o único ponto
substituído: precisamos LER o anexo que teria saído do sistema.

Estilo: mesmo molde de test_trava_fazenda_selecionada.py.
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    Animal, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main
    from fazenda.api.routers import portal as portal_router

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    # `_executar_exportacao` roda em BackgroundTask e abre a PRÓPRIA sessão a
    # partir do engine importado por nome no módulo — o override de
    # get_session não a alcança.
    monkeypatch.setattr(portal_router, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda 1"))
        s.add(Fazenda(id=2, nome="Fazenda 2"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(Usuario(id=1, username="admin2", senha_hash=hash_senha("x"), papel="admin",
                      ativo=True, email="admin2@fazenda2.com", nome="Admin 2"))
        s.add(Usuario(id=2, username="func1", senha_hash=hash_senha("x"), papel="operador",
                      permissoes="", ativo=True, email="func1@fazenda1.com", nome="Funcionário 1"))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=2))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=1))

        # Dado sensível de CADA fazenda, com o MESMO número de animal (numero
        # deixou de ser único globalmente na migração c24befa94c1b).
        s.add(Animal(numero="500", nome="Mimosa da Fazenda 1", fazenda_id=1, ativo=True))
        s.add(Animal(numero="500", nome="Estrela da Fazenda 2", fazenda_id=2, ativo=True))
        s.add(ContaGerencial(tipo="despesa", valor_total=111111.11, fazenda_id=1,
                             data_competencia=date(2026, 1, 15), fornecedor_cliente="Sigiloso Fazenda 1"))
        s.add(ContaGerencial(tipo="despesa", valor_total=222.22, fazenda_id=2,
                             data_competencia=date(2026, 1, 15), fornecedor_cliente="Normal Fazenda 2"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override

    enviados: list[dict] = []

    def _enviar_email_fake(destinatario, assunto, corpo_html, anexo_nome=None, anexo_bytes=None):
        enviados.append({
            "destinatario": destinatario, "assunto": assunto, "corpo_html": corpo_html,
            "anexo_nome": anexo_nome, "anexo_bytes": anexo_bytes,
        })

    monkeypatch.setattr(portal_router, "enviar_email", _enviar_email_fake)

    with TestClient(main.app) as c:
        yield c, engine, enviados
    main.app.dependency_overrides.clear()


def _cabecalho(fazenda_id):
    return {"Authorization": f"Bearer {criar_token('admin2', fazenda_id=fazenda_id)}"}


class TestExportacaoDoPortalNaoVazaOutraFazenda:
    def test_zip_exportado_pela_fazenda_2_nao_contem_linha_da_fazenda_1(self, ambiente):
        c, _engine, enviados = ambiente
        r = c.post(
            "/portal/exportar",
            json={"itens": [
                {"chave": "animal_ficha"},
                {"chave": "financeiro_lancamentos", "data_inicio": "2026-01-01", "data_fim": "2026-01-31"},
            ]},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        # O TestClient executa as BackgroundTasks antes de devolver a resposta,
        # então o ZIP já foi montado e "enviado" aqui.
        assert len(enviados) == 1, f"a exportação não chegou a gerar e-mail: {enviados}"
        assert enviados[0]["destinatario"] == "admin2@fazenda2.com"

        zf = zipfile.ZipFile(io.BytesIO(enviados[0]["anexo_bytes"]))
        animais_csv = zf.read("animal_ficha.csv").decode("utf-8-sig")
        financeiro_csv = zf.read("financeiro_lancamentos.csv").decode("utf-8-sig")

        assert "Estrela da Fazenda 2" in animais_csv, "a exportação nem trouxe o dado da própria fazenda"
        assert "Mimosa da Fazenda 1" not in animais_csv, (
            "o ZIP exportado pela fazenda 2 contém a ficha de animal da fazenda 1 — "
            "vazamento de dados de outro cliente da plataforma, por e-mail"
        )
        assert "Normal Fazenda 2" in financeiro_csv
        assert "Sigiloso Fazenda 1" not in financeiro_csv, (
            "o ZIP exportado pela fazenda 2 contém o livro financeiro da fazenda 1"
        )

    def test_relatorio_financeiro_do_zip_e_da_propria_fazenda(self, ambiente):
        """A DRE/RMCA/custo por litro entram no ZIP por chamada DIRETA das
        funções de rota do financeiro — o furo original era justamente o
        `fazenda_id` não passado, que virava `Depends(...)` e caía para None."""
        c, _engine, enviados = ambiente
        r = c.post(
            "/portal/exportar",
            json={"itens": [{"chave": "dre", "data_inicio": "2026-01-01", "data_fim": "2026-01-31"}]},
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        zf = zipfile.ZipFile(io.BytesIO(enviados[0]["anexo_bytes"]))
        dre_csv = zf.read("dre.csv").decode("utf-8-sig")
        assert "111111.11" not in dre_csv and "111111,11" not in dre_csv, (
            "a DRE exportada pela fazenda 2 somou a despesa da fazenda 1"
        )


class TestEmailDoPortalNaoVazaOutraFazenda:
    def test_relatorio_por_email_soma_so_a_propria_fazenda(self, ambiente):
        c, _engine, enviados = ambiente
        r = c.post(
            "/portal/email",
            json={
                "destinatarios_usuario_id": [1], "assunto": "DRE", "relatorio": "dre",
                "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
            },
            headers=_cabecalho(2),
        )
        assert r.status_code == 200, r.text
        anexo = enviados[0]["anexo_bytes"].decode("utf-8-sig")
        assert "111111.11" not in anexo and "111111,11" not in anexo, (
            "a DRE enviada por e-mail pela fazenda 2 inclui a despesa da fazenda 1"
        )
        assert "222.22" in anexo or "222,22" in anexo

    def test_nao_envia_email_para_usuario_de_outra_fazenda(self, ambiente):
        """`func1` é usuário da fazenda 1. O admin da fazenda 2 não pode
        despachar nada pelo sistema para ele — nem o relatório da própria
        fazenda 2 (que aí sai do tenant), nem um texto livre que chega
        parecendo comunicação oficial da plataforma."""
        c, _engine, enviados = ambiente
        r = c.post(
            "/portal/email",
            json={"destinatarios_usuario_id": [2], "assunto": "Oi", "corpo": "texto"},
            headers=_cabecalho(2),
        )
        assert r.status_code == 404, (
            f"o Portal aceitou enviar e-mail para um usuário de OUTRA fazenda: {r.status_code} {r.text[:200]}"
        )
        assert enviados == [], f"o e-mail cross-tenant chegou a ser disparado: {enviados}"
