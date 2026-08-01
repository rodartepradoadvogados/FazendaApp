"""
Testes de fazenda.rules.sugestao_documento.sugestoes_cadastro — liga o motor
puro de casamento (test_casamento_cadastro.py) ao cadastro real da fazenda
(Fornecedor/Estoque/ServicoCadastro). Só confiança "provavel" deve aparecer
no resultado — "exato" (nada a confirmar) e "incerto" (nada parecido) ficam
de fora, ver docstring do módulo.
"""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Estoque, Fornecedor, ServicoCadastro
from fazenda.rules.sugestao_documento import sugestoes_cadastro


def _engine_seedado():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fornecedor(nome="Agropecuária São José", tipo="fornecedor"))
        s.add(Estoque(nome="Ração Concentrada", categoria="Ração"))
        s.add(ServicoCadastro(nome="Consultoria Veterinária"))
        s.commit()
    return engine


class TestSugestoesCadastro:
    def test_fornecedor_provavel_aparece(self):
        # "Norte" não é palavra-ruído (ver PALAVRAS_RUIDO) — sobra na
        # comparação e dá um score alto mas não idêntico: provável, não exato.
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"fornecedor_cliente": "Agropecuaria Sao Jose Norte", "itens": []})
        assert r["fornecedor"]["texto"] == "Agropecuaria Sao Jose Norte"
        assert r["fornecedor"]["candidato"] == "Agropecuária São José"
        assert r["fornecedor"]["confianca"] == "provavel"

    def test_fornecedor_exato_nao_aparece(self):
        # Só "LTDA" (palavra-ruído) de diferença — normaliza para o mesmo
        # texto do cadastro, então é EXATO, não PROVAVEL (nada a confirmar).
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"fornecedor_cliente": "AGROPECUARIA SAO JOSE LTDA", "itens": []})
        assert r["fornecedor"] is None

    def test_fornecedor_sem_nenhuma_semelhanca_nao_aparece(self):
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"fornecedor_cliente": "Distribuidora Totalmente Diferente", "itens": []})
        assert r["fornecedor"] is None

    def test_item_produto_provavel_marcado_como_produto(self):
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"itens": [{"produto": "Ração Concentrada 25kg"}]})
        assert len(r["itens"]) == 1
        assert r["itens"][0]["candidato"] == "Ração Concentrada"
        assert r["itens"][0]["tipo"] == "produto"
        assert r["itens"][0]["confianca"] == "provavel"
        assert r["itens"][0]["indice"] == 0

    def test_item_servico_provavel_marcado_como_servico(self):
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"itens": [{"produto": "Consultoria Veterinaria Mensal"}]})
        assert len(r["itens"]) == 1
        assert r["itens"][0]["candidato"] == "Consultoria Veterinária"
        assert r["itens"][0]["tipo"] == "servico"

    def test_indice_aponta_para_a_posicao_no_dados_itens_nao_no_resultado(self):
        # 1º item (índice 0) não tem semelhança e é pulado — o item com
        # sugestão (o 2º) precisa levar o índice 1 de verdade, não 0
        # recontado a partir do resultado filtrado.
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"itens": [
                {"produto": "Vacina Aftosa"}, {"produto": "Ração Concentrada 25kg"},
            ]})
        assert len(r["itens"]) == 1
        assert r["itens"][0]["indice"] == 1

    def test_item_sem_semelhanca_nao_aparece(self):
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {"itens": [{"produto": "Vacina Aftosa"}]})
        assert r["itens"] == []

    def test_dados_vazios_nao_quebra(self):
        engine = _engine_seedado()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, None, {})
        assert r == {"fornecedor": None, "itens": []}

    def test_isolamento_por_fazenda(self):
        # Só a fazenda 2 tem um fornecedor parecido — consultando pela
        # fazenda 1 não pode "vazar" esse candidato de outra fazenda.
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(Fornecedor(nome="Agropecuária São José", tipo="fornecedor", fazenda_id=2))
            s.commit()
        with Session(engine) as s:
            r = sugestoes_cadastro(s, 1, {"fornecedor_cliente": "Agropecuaria Sao Jose Norte", "itens": []})
        assert r["fornecedor"] is None
        with Session(engine) as s:
            r2 = sugestoes_cadastro(s, 2, {"fornecedor_cliente": "Agropecuaria Sao Jose Norte", "itens": []})
        assert r2["fornecedor"]["candidato"] == "Agropecuária São José"
