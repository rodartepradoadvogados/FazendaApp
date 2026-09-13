"""
Mesclagem de itens de Estoque (POST /estoque/{sobrevivente_id}/mesclar) e
restaurar padrão CowData (POST /estoque/{id}/restaurar-padrao) — ver
fazenda/api/routers/estoque.py e fazenda/auth.exigir_sessao_suporte.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import criar_token, get_current_user, get_fazenda_atual_id, hash_senha
from fazenda.models import (
    Alimento, CategoriaMedicamento, ContratoFazenda, ContratoFazendaModulo, Estoque, EstoqueAliasMesclado,
    EstoqueCategoriaMedicamento, Fazenda, LoteEstoque, MedicamentoCategoria, MedicamentoComercial, MovimentoEstoque,
    PrincipioAtivo, Usuario,
)
from fazenda.models.cofre_acesso import PedidoAcessoSuporte, SessaoAcessoSuporte
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        fa = Fazenda(nome="Fazenda A", ativa=True)
        fb = Fazenda(nome="Fazenda B", ativa=True)
        s.add_all([fa, fb])
        s.commit()
        s.refresh(fa)
        s.refresh(fb)
        fa_id, fb_id = fa.id, fb.id

        # Selecionar a fazenda (override de get_fazenda_atual_id, mais
        # abaixo) faz valer as travas de tenant que antes ficavam de fora
        # justamente por não haver fazenda na sessão: além do filtro por
        # fazenda_id nas consultas, o router de Estoque exige contrato ativo
        # E o módulo comercial contratado (exigir_modulo_contratado("estoque")
        # em main.py). Sem estas linhas o teste passa a receber 403.
        for fid in (fa_id, fb_id):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

        usuario = Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email="dono@x.com")
        s.add(usuario)
        s.commit()
        s.refresh(usuario)
        usuario_id = usuario.id

        # `_token_suporte` abaixo emite um token com sessao_suporte_id=1 —
        # desde a correção do cofre_acesso.py::encerrar_sessao (o middleware
        # de modo suporte agora confere no banco se a sessão do "ssid" ainda
        # está ativa, não só a claim do JWT), esse id precisa corresponder a
        # uma SessaoAcessoSuporte real, ativa, não encerrada.
        from datetime import datetime, timedelta
        pedido = PedidoAcessoSuporte(fazenda_id=fa_id, usuario_id=usuario_id, motivo="Diagnosticar erro relatado", status="aprovado")
        s.add(pedido)
        s.commit()
        s.refresh(pedido)
        s.add(SessaoAcessoSuporte(
            id=1, pedido_id=pedido.id, fazenda_id=fa_id, usuario_id=usuario_id,
            motivo=pedido.motivo, nivel_sigilo="total", expira_em=datetime.utcnow() + timedelta(hours=1),
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    class _FakeUser:
        id = usuario_id
        papel = "admin"
        ativo = True
        username = "dono"

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    # Fazenda A é a fazenda "de trabalho" desta suíte — é o equivalente, no
    # teste, ao "fid" que o login carimba no token. Havendo fazenda
    # cadastrada (as duas acima), `exigir_fazenda_selecionada`
    # (fazenda/auth.py, montada em todo router de tenant em main.py) recusa
    # com 409 a requisição que não disser em qual fazenda ela acontece —
    # antes desta trava a suíte inteira rodava "sem fazenda", o que também
    # desligava o isolamento entre A e B que ela quer justamente exercitar.
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fa_id

    with TestClient(main.app) as c:
        yield c, engine, fa_id, fb_id, usuario_id
    main.app.dependency_overrides.clear()


def _token_suporte(fazenda_id: int) -> str:
    return criar_token("dono", fazenda_id=fazenda_id, suporte=True, sessao_suporte_id=1, nivel_sigilo="total")


def test_mescla_repointa_movimentos_e_alimento_preferido(client):
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        sobrevivente = Estoque(nome="Meloxicam Novo", fazenda_id=fa_id, ativo=True, estocavel=True, quantidade=5)
        perdedor = Estoque(nome="Meloxicam Antigo", fazenda_id=fa_id, ativo=True, estocavel=True, quantidade=2, carencia_dias=10)
        s.add_all([sobrevivente, perdedor])
        s.commit()
        s.refresh(sobrevivente)
        s.refresh(perdedor)
        sob_id, perd_id = sobrevivente.id, perdedor.id

        mov = MovimentoEstoque(nome_item="Meloxicam Antigo", movimento="Aplicação", quantidade=1, unidade="ml",
                                data_movimento=date(2026, 1, 1), estoque_id=perd_id, fazenda_id=fa_id)
        alimento = Alimento(nome="Dieta X", fazenda_id=fa_id, estoque_preferido_id=perd_id)
        s.add_all([mov, alimento])
        s.commit()
        mov_id, alimento_id = mov.id, alimento.id

    r = c.post(f"/estoque/{sob_id}/mesclar", json={"perdedor_ids": [perd_id]})
    assert r.status_code == 200, r.text
    assert r.json()["mesclados"] == 1

    with Session(engine) as s:
        mov_depois = s.get(MovimentoEstoque, mov_id)
        assert mov_depois.estoque_id == sob_id  # FK real repontada

        alimento_depois = s.get(Alimento, alimento_id)
        assert alimento_depois.estoque_preferido_id == sob_id  # FK real repontada

        perdedor_depois = s.get(Estoque, perd_id)
        assert perdedor_depois is not None  # NUNCA excluído
        assert perdedor_depois.nome == "Meloxicam Antigo"  # nome histórico NUNCA reescrito
        assert perdedor_depois.ativo is False and perdedor_depois.estocavel is False

        alias = s.exec(select(EstoqueAliasMesclado).where(EstoqueAliasMesclado.estoque_perdedor_id == perd_id)).first()
        assert alias is not None
        assert alias.nome_perdedor == "Meloxicam Antigo"
        assert alias.estoque_sobrevivente_id == sob_id
        assert alias.carencia_carne_dias_congelada == 10  # carência do PERDEDOR congelada, não herdada do sobrevivente


def test_mescla_soma_quantidade_e_repontea_lotes(client):
    """Pedido do usuário (01/09/2026): mesclar "sem perder... estoque" — o
    saldo físico e os lotes/frascos abertos (Fase G) do perdedor precisam
    ir pro sobrevivente, não desaparecer quando o perdedor vira alias
    inativo."""
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        sobrevivente = Estoque(nome="Meloxicam Novo", fazenda_id=fa_id, ativo=True, estocavel=True, quantidade=5)
        perdedor = Estoque(nome="Meloxicam Antigo", fazenda_id=fa_id, ativo=True, estocavel=True, quantidade=20)
        s.add_all([sobrevivente, perdedor])
        s.commit()
        s.refresh(sobrevivente)
        s.refresh(perdedor)
        sob_id, perd_id = sobrevivente.id, perdedor.id

        lote = LoteEstoque(
            estoque_id=perd_id, fazenda_id=fa_id, data_compra=date(2026, 1, 1),
            quantidade_comprada=20, quantidade_restante=20, ativo=True,
        )
        s.add(lote)
        s.commit()
        lote_id = lote.id

    r = c.post(f"/estoque/{sob_id}/mesclar", json={"perdedor_ids": [perd_id]})
    assert r.status_code == 200, r.text
    assert r.json()["estoque_transferido"] == 20

    with Session(engine) as s:
        sobrevivente_depois = s.get(Estoque, sob_id)
        assert sobrevivente_depois.quantidade == 25  # 5 + 20, nada perdido

        perdedor_depois = s.get(Estoque, perd_id)
        assert perdedor_depois.quantidade == 0  # saldo movido, não duplicado

        lote_depois = s.get(LoteEstoque, lote_id)
        assert lote_depois.estoque_id == sob_id  # lote repontado pro sobrevivente


def test_mescla_alinha_item_com_padrao_cowdata(client):
    """Pedido do usuário: mesclar serve pra "o tenant alinhar com o padrão
    CowData" — quando o item padrão do fan-out (medicamento_comercial_id
    setado) é um dos dois lados, o SOBREVIVENTE (que fica com histórico e
    estoque) herda a identidade padrão, sem nunca trocar de nome."""
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Tulatromicina", fazenda_id=None)
        s.add(pa)
        s.commit()
        s.refresh(pa)
        medicamento = MedicamentoComercial(nome_comercial="Draxxin KP", principio_ativo_id=pa.id, laboratorio="Zoetis", fazenda_id=None)
        s.add(medicamento)
        s.commit()
        s.refresh(medicamento)
        medicamento_id = medicamento.id

        categoria = CategoriaMedicamento(nome="Antibiótico", fazenda_id=None)
        s.add(categoria)
        s.commit()
        s.refresh(categoria)
        categoria_id = categoria.id

        # Item real da fazenda, com histórico — nome digitado antes de o
        # Painel CowData cadastrar o medicamento oficial.
        sobrevivente = Estoque(
            nome="Draxxin da Zoetis", fazenda_id=fa_id, ativo=True, estocavel=True,
            quantidade=10, principio_ativo_id=pa.id,
        )
        # Item-fantasma criado pelo fan-out (ver _fan_out_medicamento) —
        # sempre ativo=False/estocavel=False, sem histórico nenhum, mas já
        # com a identidade padrão.
        perdedor = Estoque(
            nome="Draxxin KP", fazenda_id=fa_id, ativo=False, estocavel=False, quantidade=0,
            principio_ativo_id=pa.id, medicamento_comercial_id=medicamento.id,
            categoria="Medicamentos", laboratorio="Zoetis", carencia_leite_dias=4, carencia_carne_dias=21,
            proibido_lactacao=False,
        )
        s.add_all([sobrevivente, perdedor])
        s.commit()
        s.refresh(sobrevivente)
        s.refresh(perdedor)
        sob_id, perd_id = sobrevivente.id, perdedor.id

        s.add(EstoqueCategoriaMedicamento(estoque_id=perd_id, categoria_medicamento_id=categoria.id))
        s.commit()

    r = c.post(f"/estoque/{sob_id}/mesclar", json={"perdedor_ids": [perd_id]})
    assert r.status_code == 200, r.text
    assert r.json()["alinhou_padrao_cowdata"] is True

    with Session(engine) as s:
        sobrevivente_depois = s.get(Estoque, sob_id)
        assert sobrevivente_depois.nome == "Draxxin da Zoetis"  # nome NUNCA trocado
        assert sobrevivente_depois.medicamento_comercial_id == medicamento_id
        assert sobrevivente_depois.laboratorio == "Zoetis"
        assert sobrevivente_depois.carencia_leite_dias == 4
        assert sobrevivente_depois.carencia_carne_dias == 21
        assert sobrevivente_depois.proibido_lactacao is False

        tags = s.exec(
            select(EstoqueCategoriaMedicamento).where(EstoqueCategoriaMedicamento.estoque_id == sob_id)
        ).all()
        assert {t.categoria_medicamento_id for t in tags} == {categoria_id}


def test_mescla_bloqueia_itens_de_fazendas_diferentes(client):
    """Item da fazenda B nunca é mesclado numa sessão da fazenda A.

    A recusa hoje vem UMA CAMADA ANTES do que quando este teste foi escrito:
    com a fazenda selecionada na sessão (ver a fixture), o próprio filtro de
    tenant não enxerga o perdedor de outra fazenda e devolve 404 "não
    encontrado" — a guarda de mesma-fazenda lá dentro (400) só seria
    alcançada por uma sessão sem fazenda nenhuma, que
    `exigir_fazenda_selecionada` não deixa mais entrar. O que importa é o
    mesmo de sempre: nada mesclou, e o item da fazenda B ficou intacto."""
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        sobrevivente = Estoque(nome="Item A", fazenda_id=fa_id)
        perdedor = Estoque(nome="Item B", fazenda_id=fb_id)
        s.add_all([sobrevivente, perdedor])
        s.commit()
        s.refresh(sobrevivente)
        s.refresh(perdedor)
        sob_id, perd_id = sobrevivente.id, perdedor.id

    r = c.post(f"/estoque/{sob_id}/mesclar", json={"perdedor_ids": [perd_id]})
    assert r.status_code == 404

    with Session(engine) as s:
        perdedor_depois = s.get(Estoque, perd_id)
        assert perdedor_depois.ativo is not False  # nada foi inativado na fazenda B
        assert s.exec(select(EstoqueAliasMesclado)).first() is None  # nenhuma mesclagem registrada


def test_sugestoes_mesclagem_agrupa_por_principio_ativo(client):
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", fazenda_id=None)
        s.add(pa)
        s.commit()
        s.refresh(pa)
        s.add_all([
            Estoque(nome="Maxicam 2%", fazenda_id=fa_id, ativo=True, principio_ativo_id=pa.id, quantidade=3),
            Estoque(nome="Meloxicam Genérico", fazenda_id=fa_id, ativo=True, principio_ativo_id=pa.id, quantidade=10),
            Estoque(nome="Outro item sem princípio", fazenda_id=fa_id, ativo=True),
        ])
        s.commit()

    r = c.get("/estoque/sugestoes-mesclagem")
    assert r.status_code == 200
    sugestoes = r.json()
    assert len(sugestoes) == 1
    assert len(sugestoes[0]["itens"]) == 2
    assert sugestoes[0]["sobrevivente_sugerido_id"] is not None


def test_restaurar_padrao_bloqueado_fora_de_sessao_suporte(client):
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        item = Estoque(nome="Maxicam 2%", fazenda_id=fa_id)
        s.add(item)
        s.commit()
        s.refresh(item)
        item_id = item.id

    r = c.post(f"/estoque/{item_id}/restaurar-padrao")
    assert r.status_code == 403


def test_restaurar_padrao_funciona_em_sessao_suporte(client):
    c, engine, fa_id, fb_id, usuario_id = client
    with Session(engine) as s:
        pa = PrincipioAtivo(nome="Meloxicam", fazenda_id=None)
        s.add(pa)
        s.commit()
        s.refresh(pa)
        cat = CategoriaMedicamento(nome="Anti-inflamatório", fazenda_id=None)
        s.add(cat)
        s.commit()
        s.refresh(cat)
        cat_id = cat.id
        medicamento = MedicamentoComercial(
            nome_comercial="Maxicam 2%", principio_ativo_id=pa.id, laboratorio="Ourofino", fazenda_id=None,
            classificacao_medicamento="Anti-inflamatório", carencia_leite_dias=4, carencia_carne_dias=15, proibido_lactacao=True,
        )
        s.add(medicamento)
        s.commit()
        s.refresh(medicamento)
        s.add(MedicamentoCategoria(medicamento_comercial_id=medicamento.id, categoria_medicamento_id=cat.id))
        s.commit()

        item = Estoque(
            nome="Maxicam 2% (personalizado)", fazenda_id=fa_id, medicamento_comercial_id=medicamento.id,
            principio_ativo_id=pa.id, finalidade="Medicamento", classificacao_medicamento="Medicamentos", ativo=True,
        )
        s.add(item)
        s.commit()
        s.refresh(item)
        item_id = item.id

    token = _token_suporte(fa_id)
    r = c.post(f"/estoque/{item_id}/restaurar-padrao", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["nome"] == "Maxicam 2%"
    assert corpo["ativo"] is True  # nunca toca em ativo/estocavel/quantidade
    # Bug real corrigido (05/09/2026): gravava "Medicamentos" no campo errado
    # (classificacao_medicamento) e nunca propagava tags/carência/lactação.
    assert corpo["categoria"] == "Medicamentos"
    assert corpo["classificacao_medicamento"] == "Anti-inflamatório"
    assert corpo["carencia_leite_dias"] == 4
    assert corpo["carencia_carne_dias"] == 15
    assert corpo["proibido_lactacao"] is True
    with Session(engine) as s:
        vinculo = s.exec(
            select(EstoqueCategoriaMedicamento).where(EstoqueCategoriaMedicamento.estoque_id == item_id)
        ).first()
        assert vinculo is not None and vinculo.categoria_medicamento_id == cat_id
