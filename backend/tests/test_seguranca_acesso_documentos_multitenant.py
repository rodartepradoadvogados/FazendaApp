"""
Bloco "controle de acesso, cofre, usuários e documentos" da auditoria de
segurança (docs/security-audit/achados.json) — os furos que vazam feio:
escalada de privilégio no Painel CowData, dado pessoal de funcionário,
arquivo fiscal e inventário de genética.

O CowData é multi-tenant por `fazenda_id` e NÃO tem RLS: o isolamento existe
só no código da aplicação. Dois anti-padrões conhecidos, que estes testes
travam de uma vez:

  1. o tolerante — `if fazenda_id is not None: query = query.where(...)`.
     Um token sem "fid" não restringe: DESLIGA o isolamento.
  2. a tolerância a NULL — deixar o registro órfão (`fazenda_id` NULL, resíduo
     real documentado pela migração 029227481e9e) passar por qualquer
     inquilino.

TOKEN DE VERDADE, nunca `dependency_overrides[get_fazenda_atual_id]`: é o
caminho token -> get_fazenda_atual_id -> consulta que está em julgamento, e
falsificar o meio dele já deixou furo passar antes. Mesmo espírito de
tests/test_seguranca_confirmacao_por_id_multitenant.py e
tests/test_trava_fazenda_selecionada.py.

Todo teste de bloqueio vem com o controle positivo ao lado — a própria
fazenda continua conseguindo. Teste que só prova bloqueio pode estar
bloqueando tudo.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import EMAIL_DONO, EMAILS_DONO_EQUIVALENTE, criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, DocumentoArquivado, EstoqueSemen, Fazenda, Pessoa,
    PessoaAnexo, TipoDocumento, Usuario, UsuarioFazenda,
)
from fazenda.models.equipe_cowdata_acesso import PermissaoEquipeCowData
from fazenda.models.planos import MODULOS_COMERCIAIS

# O sócio dono-equivalente (ver EMAILS_DONO_EQUIVALENTE em fazenda/auth.py) é
# uma Pessoa DA FAZENDA-CLIENTE — ele está no próprio seed de pessoas
# (SEED_PESSOAS em cadastro/pessoas.py). É isso que põe uma conta com poder de
# proprietário dentro do alcance do Painel CowData > Usuários.
EMAIL_SOCIO = next(e for e in EMAILS_DONO_EQUIVALENTE if e != EMAIL_DONO)


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes (1 = alvo, 2 = atacante), a fazenda interna da
    CowData (3), e um registro atacável da fazenda 1 por rota sob teste —
    mais o par órfão (`fazenda_id` NULL) onde ele existe de verdade."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    # Storage do Supabase não existe no teste — o que importa aqui é quem
    # consegue chegar ao arquivo, não o transporte.
    import fazenda.api.routers.cadastro.pessoas as pessoas_mod
    import fazenda.api.routers.documentos as documentos_mod

    balde: dict[str, bytes] = {}
    for modulo in (pessoas_mod, documentos_mod):
        monkeypatch.setattr(modulo, "enviar_arquivo", lambda caminho, conteudo, *a, **k: balde.__setitem__(caminho, conteudo))
        monkeypatch.setattr(modulo, "baixar_arquivo", lambda caminho, *a, **k: balde.get(caminho, b"conteudo"))
        monkeypatch.setattr(modulo, "excluir_arquivo", lambda caminho, *a, **k: balde.pop(caminho, None))

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Atacante"))
        s.add(Fazenda(id=3, nome="CowData", eh_empresa_cowdata=True))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))

        # --- Painel CowData > Usuários: o sócio dono-equivalente é uma
        # pessoa DA FAZENDA 1, com login próprio. -------------------------
        socio = Pessoa(nome="Alexandre Scarpa", tipo="Funcionário", fazenda_id=1)
        comum = Pessoa(nome="Leomir Bonfim", tipo="Funcionário", fazenda_id=1)
        # Membro da Equipe CowData com UMA área de baixo privilégio.
        atendente_pessoa = Pessoa(nome="Atendente CowData", tipo="Funcionário", fazenda_id=3)
        s.add_all([socio, comum, atendente_pessoa])
        s.commit()
        s.refresh(socio)
        s.refresh(comum)
        s.refresh(atendente_pessoa)

        usuario_socio = Usuario(
            username="socio", nome="Alexandre Scarpa", pessoa_id=socio.id,
            senha_hash=hash_senha("senha-do-socio"), papel="admin", email=EMAIL_SOCIO, ativo=True,
        )
        usuario_comum = Usuario(
            username="leomir", nome="Leomir Bonfim", pessoa_id=comum.id,
            senha_hash=hash_senha("x"), papel="operador", permissoes="rebanho", ativo=True,
        )
        atendente = Usuario(
            username="atendente", nome="Atendente CowData", pessoa_id=atendente_pessoa.id,
            senha_hash=hash_senha("x"), papel="operador", email="atendente@cowdata.com.br", ativo=True,
        )
        s.add_all([usuario_socio, usuario_comum, atendente])
        s.commit()
        s.refresh(usuario_socio)
        s.refresh(usuario_comum)
        s.refresh(atendente)
        # As três permissões de usuários (set/2026) vêm LIGADAS de propósito:
        # o que está em julgamento aqui é a trava contra escalada de
        # privilégio, e ela tem de barrar o atendente MESMO quando ele tem
        # toda a permissão que a tela oferece. Sem isso, os testes de 403
        # abaixo passariam pelo motivo errado (permissão nova faltando) e
        # deixariam de vigiar a trava que realmente importa.
        s.add(PermissaoEquipeCowData(
            usuario_id=atendente.id, areas="cadastros",
            pode_consultar_usuarios=True, pode_editar_usuarios=True, pode_controlar_acesso_usuarios=True,
        ))

        # --- Inseminadores (dado pessoal de funcionário) -------------------
        s.add(Pessoa(nome="Inseminador da Alvo", tipo="Funcionário,Inseminador", ativo=True, fazenda_id=1))
        s.add(Pessoa(nome="Inseminador da Atacante", tipo="Inseminador", ativo=True, fazenda_id=2))
        s.add(Pessoa(nome="Inseminador Órfão", tipo="Inseminador", ativo=True, fazenda_id=None))

        # --- Arquivo fiscal-contábil (IRPF, matrícula, contrato...) --------
        for fid in (1, 2):
            s.add(TipoDocumento(nome="Nota fiscal", ativo=True, fazenda_id=fid))
        doc_alvo = DocumentoArquivado(
            fazenda_id=1, categoria="Nota fiscal", nome_original="irpf-do-dono.pdf",
            caminho_storage="fazenda-1/nota_fiscal/2026-09-01_NF_0001.pdf",
            mime_type="application/pdf", tamanho_bytes=10,
        )
        doc_orfao = DocumentoArquivado(
            fazenda_id=None, categoria="Nota fiscal", nome_original="orfao.pdf",
            caminho_storage="fazenda-geral/nota_fiscal/2026-09-01_NF_0001.pdf",
            mime_type="application/pdf", tamanho_bytes=10,
        )
        # Anexo gravado ANTES da allow-list de content_type, com o tipo que o
        # cliente escolheu — é o que o navegador renderizaria inline.
        doc_html = DocumentoArquivado(
            fazenda_id=1, categoria="Nota fiscal", nome_original="nota.html",
            caminho_storage="fazenda-1/nota_fiscal/2026-09-01_NF_0002.html",
            mime_type="text/html", tamanho_bytes=10,
        )
        s.add_all([doc_alvo, doc_orfao, doc_html])

        # --- Anexo de Pessoa (RG/CPF/holerite) ----------------------------
        anexo_html = PessoaAnexo(
            pessoa_id=comum.id, nome_arquivo="rg.html", mime_type="text/html", tamanho_bytes=10,
            categoria="RG", caminho_storage="fazenda-1/pessoas/1/0001_rg.html", fazenda_id=1,
        )
        s.add(anexo_html)

        # --- Inventário de sêmen (informação comercial de genética) --------
        semen_alvo = EstoqueSemen(touro_nome="HAGEN DA ALVO", tipo="sexado", doses=6, fazenda_id=1)
        semen_orfao = EstoqueSemen(touro_nome="TOURO ÓRFÃO", tipo="convencional", doses=3, fazenda_id=None)
        semen_atacante = EstoqueSemen(touro_nome="TOURO DA ATACANTE", tipo="convencional", doses=1, fazenda_id=2)
        s.add_all([semen_alvo, semen_orfao, semen_atacante])
        s.commit()

        ids.update(
            usuario_socio=usuario_socio.id, usuario_comum=usuario_comum.id, atendente=atendente.id,
            pessoa_comum=comum.id, doc_alvo=doc_alvo.id, doc_orfao=doc_orfao.id, doc_html=doc_html.id,
            anexo_html=anexo_html.id, semen_alvo=semen_alvo.id, semen_orfao=semen_orfao.id,
            semen_atacante=semen_atacante.id,
        )

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int):
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


def _cab_painel(username: str):
    """Token REAL de quem opera o Painel CowData — sem "fid", porque o painel
    administra TODAS as fazendas-clientes e não fica dentro de nenhuma."""
    return {"Authorization": f"Bearer {criar_token(username)}"}


# ---------------------------------------------------------------------------
# Painel CowData > Usuários — escalada de privilégio
# ---------------------------------------------------------------------------
def test_atendente_cowdata_nao_troca_a_senha_do_login_dono_equivalente(ambiente):
    """A trava que já existia só barrava ATRIBUIR um e-mail dono-equivalente.
    Editar um login que JÁ é dono-equivalente continuava liberado — e essa
    conta mora dentro de fazenda-cliente (o sócio é uma Pessoa dela). Um
    funcionário do CowData com SÓ a área "cadastros" trocava a senha dele e
    passava a entrar como proprietário: Painel CowData inteiro, todas as
    fazendas-clientes, cofre de acesso, financeiro."""
    c, engine, ids = ambiente
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['usuario_socio']}",
        json={"senha": "senha-escolhida-pelo-atacante"},
        headers=_cab_painel("atendente"),
    )
    assert r.status_code == 403, r.text
    login = c.post("/auth/login", json={"username": "socio", "senha": "senha-escolhida-pelo-atacante"})
    assert login.status_code != 200, (
        "a senha do login dono-equivalente foi trocada por um operador de área 'cadastros' — "
        "escalada de uma permissão estreita para controle total da plataforma"
    )
    assert c.post("/auth/login", json={"username": "socio", "senha": "senha-do-socio"}).status_code == 200


def test_atendente_cowdata_nao_sequestra_nem_desativa_o_login_dono_equivalente(ambiente):
    """Trocar o `username` (sequestro do login) e desativar a conta são o
    mesmo furo por outro campo."""
    c, engine, ids = ambiente
    for corpo in ({"username": "socio-do-atacante"}, {"ativo": False}, {"papel": "operador"}):
        r = c.put(
            f"/painel-cowdata/usuarios/1/{ids['usuario_socio']}", json=corpo,
            headers=_cab_painel("atendente"),
        )
        assert r.status_code == 403, (corpo, r.text)
    with Session(engine) as s:
        u = s.get(Usuario, ids["usuario_socio"])
        assert u.username == "socio" and u.ativo is True and u.papel == "admin"


def test_atendente_cowdata_continua_editando_usuario_comum_da_fazenda(ambiente):
    """Controle positivo: a rota continua servindo para o que ela existe —
    administrar o login de operador da fazenda-cliente."""
    c, engine, ids = ambiente
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['usuario_comum']}",
        json={"permissoes": ["rebanho", "reproducao"]},
        headers=_cab_painel("atendente"),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert "reproducao" in s.get(Usuario, ids["usuario_comum"]).permissoes


def test_dono_continua_editando_o_proprio_login_dono_equivalente(ambiente):
    """Controle positivo: quem é dono-equivalente não pode perder a própria
    tela — a trava é contra quem NÃO é."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        s.add(Usuario(username="dono", senha_hash=hash_senha("x"), papel="admin", email=EMAIL_DONO, ativo=True))
        s.commit()
    r = c.put(
        f"/painel-cowdata/usuarios/1/{ids['usuario_socio']}", json={"senha": "trocada-pelo-dono"},
        headers=_cab_painel("dono"),
    )
    assert r.status_code == 200, r.text
    assert c.post("/auth/login", json={"username": "socio", "senha": "trocada-pelo-dono"}).status_code == 200


# ---------------------------------------------------------------------------
# Cadastro > Pessoas — nome de funcionário de outra fazenda
# ---------------------------------------------------------------------------
def test_inseminadores_nao_atravessam_a_borda_da_fazenda(ambiente):
    """GET /cadastro/pessoas/inseminadores era a única consulta de pessoas.py
    sem NENHUM recorte por fazenda: varria a tabela Pessoa inteira e devolvia
    o nome dos inseminadores de todas as fazendas-clientes a qualquer usuário
    autenticado."""
    c, engine, ids = ambiente
    r = c.get("/cadastro/pessoas/inseminadores", headers=_cab(2))
    assert r.status_code == 200, r.text
    nomes = r.json()
    assert "Inseminador da Alvo" not in nomes, (
        "a fazenda 2 leu o nome do inseminador da fazenda 1 — dado pessoal de funcionário de "
        "outro cliente da plataforma"
    )
    assert "Inseminador Órfão" not in nomes, (
        "pessoa órfã (fazenda_id NULL, resíduo real do backfill 029227481e9e) apareceu para a "
        "fazenda 2 — registro sem dono não é registro de qualquer um"
    )
    assert nomes == ["Inseminador da Atacante"]


def test_inseminadores_da_propria_fazenda_continuam_listados(ambiente):
    c, engine, ids = ambiente
    r = c.get("/cadastro/pessoas/inseminadores", headers=_cab(1))
    assert r.status_code == 200, r.text
    assert r.json() == ["Inseminador da Alvo"]


def test_anexo_de_pessoa_nao_e_servido_como_html(ambiente):
    """O `mime_type` do anexo era o que o CLIENTE mandava, e o download
    devolve com Content-Disposition: inline — bastava anexar um "rg.html"
    declarado text/html para ter script rodando na origem autenticada do
    sistema (XSS armazenado). Mesmo achado 55 já fechado em documentos.py e
    fotos.py, que não tinha sido replicado no anexo de PESSOA — justamente
    onde ficam RG, CPF, carteira de trabalho e holerite."""
    c, engine, ids = ambiente
    r = c.get(f"/cadastro/pessoas/anexos/{ids['anexo_html']}", headers=_cab(1))
    assert r.status_code == 200, r.text
    assert "text/html" not in r.headers["content-type"], (
        "o anexo voltou como text/html e é servido inline — XSS armazenado na origem autenticada"
    )

    enviado = c.post(
        f"/cadastro/pessoas/{ids['pessoa_comum']}/anexos",
        files={"file": ("cpf.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>", "image/svg+xml")},
        data={"categoria": "CPF"}, headers=_cab(1),
    )
    assert enviado.status_code == 201, enviado.text
    assert enviado.json()["mime_type"] == "application/octet-stream"


def test_anexo_de_pessoa_em_pdf_continua_com_o_tipo_certo(ambiente):
    """Controle positivo: a allow-list não pode transformar todo anexo
    legítimo em download opaco."""
    c, engine, ids = ambiente
    enviado = c.post(
        f"/cadastro/pessoas/{ids['pessoa_comum']}/anexos",
        files={"file": ("contrato.pdf", b"%PDF-1.4", "application/pdf")},
        data={"categoria": "Contrato de trabalho por prazo determinado"}, headers=_cab(1),
    )
    assert enviado.status_code == 201, enviado.text
    anexo_id = enviado.json()["id"]
    r = c.get(f"/cadastro/pessoas/anexos/{anexo_id}", headers=_cab(1))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


# ---------------------------------------------------------------------------
# Arquivo fiscal-contábil — documento que sai do sistema
#
# HONESTIDADE SOBRE O QUE ESTES QUATRO TESTES PROVAM: a carga por id destas
# rotas usava o padrão tolerante (`if fazenda_id is not None`), mas o router
# de documentos está montado atrás da trava de porta em main.py, então um
# token sem "fid" já era recusado antes — o furo não estava aberto. Eles não
# falham contra o código pré-correção: travam a SEGUNDA linha de defesa (o
# filtro na própria consulta) para que ela não volte a apontar para o lado
# errado se a trava de porta for afrouxada ou a rota remontada. A exceção é
# o último teste da seção (mime_type gravado como text/html), esse sim falha
# antes da correção.
# ---------------------------------------------------------------------------
def test_documento_de_outra_fazenda_nao_e_baixado(ambiente):
    c, engine, ids = ambiente
    r = c.get(f"/documentos/{ids['doc_alvo']}/download", headers=_cab(2))
    assert r.status_code == 404, (
        "a fazenda 2 baixou o documento fiscal da fazenda 1 só chutando um id sequencial "
        f"(status {r.status_code}) — e 404 é o certo, nunca 403: um 403 já confirma que o id existe"
    )


def test_documento_orfao_nao_e_baixado_por_ninguem(ambiente):
    c, engine, ids = ambiente
    for fazenda in (1, 2):
        assert c.get(f"/documentos/{ids['doc_orfao']}/download", headers=_cab(fazenda)).status_code == 404


def test_documento_de_outra_fazenda_nao_e_excluido(ambiente):
    c, engine, ids = ambiente
    r = c.delete(f"/documentos/{ids['doc_alvo']}", headers=_cab(2))
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        assert s.get(DocumentoArquivado, ids["doc_alvo"]) is not None, (
            "a fazenda 2 apagou o documento fiscal da fazenda 1 — exclusão irreversível de arquivo "
            "de IRPF/matrícula/contrato de outro cliente"
        )


def test_documento_da_propria_fazenda_continua_sendo_baixado_e_excluido(ambiente):
    c, engine, ids = ambiente
    assert c.get(f"/documentos/{ids['doc_alvo']}/download", headers=_cab(1)).status_code == 200
    assert c.delete(f"/documentos/{ids['doc_alvo']}", headers=_cab(1)).status_code == 200
    with Session(engine) as s:
        assert s.get(DocumentoArquivado, ids["doc_alvo"]) is None


def test_documento_gravado_como_html_nao_volta_renderizavel(ambiente):
    c, engine, ids = ambiente
    r = c.get(f"/documentos/{ids['doc_html']}/download", headers=_cab(1))
    assert r.status_code == 200, r.text
    assert "text/html" not in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Central de Sêmen — inventário de genética (informação comercial)
#
# Mesma observação da seção anterior: com a trava de porta montada no router
# de cadastro, estes testes passam também contra o código pré-correção. São
# guarda de regressão da segunda linha de defesa, não prova de furo aberto.
# ---------------------------------------------------------------------------
def _corpo_semen(nome: str, doses: int = 999) -> dict:
    return {"touro_nome": nome, "tipo": "convencional", "doses": doses, "ativo": True}


def test_estoque_semen_de_outra_fazenda_nao_e_editado(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/cadastro/estoque-semen/{ids['semen_alvo']}", json=_corpo_semen("SEQUESTRADO"),
        headers=_cab(2),
    )
    assert r.status_code == 404, r.text
    with Session(engine) as s:
        item = s.get(EstoqueSemen, ids["semen_alvo"])
        assert item.touro_nome == "HAGEN DA ALVO" and item.doses == 6


def test_estoque_semen_de_outra_fazenda_nao_e_excluido(ambiente):
    c, engine, ids = ambiente
    assert c.delete(f"/cadastro/estoque-semen/{ids['semen_alvo']}", headers=_cab(2)).status_code == 404
    with Session(engine) as s:
        assert s.get(EstoqueSemen, ids["semen_alvo"]) is not None


def test_estoque_semen_orfao_nao_e_editado_por_ninguem(ambiente):
    c, engine, ids = ambiente
    for fazenda in (1, 2):
        r = c.put(
            f"/cadastro/estoque-semen/{ids['semen_orfao']}", json=_corpo_semen("ADOTADO"),
            headers=_cab(fazenda),
        )
        assert r.status_code == 404, (fazenda, r.text)
    with Session(engine) as s:
        assert s.get(EstoqueSemen, ids["semen_orfao"]).touro_nome == "TOURO ÓRFÃO"


def test_estoque_semen_da_propria_fazenda_continua_editavel(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/cadastro/estoque-semen/{ids['semen_atacante']}", json=_corpo_semen("TOURO DA ATACANTE", doses=4),
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(EstoqueSemen, ids["semen_atacante"]).doses == 4


def test_estoque_semen_nao_lista_o_de_outra_fazenda(ambiente):
    """Controle de leitura ao lado do de escrita — o inventário do concorrente
    (touro, doses, caneca) é informação comercial de genética."""
    c, engine, ids = ambiente
    r = c.get("/cadastro/estoque-semen", headers=_cab(2))
    assert r.status_code == 200, r.text
    nomes = {i["touro_nome"] for i in r.json()}
    assert nomes == {"TOURO DA ATACANTE"}
