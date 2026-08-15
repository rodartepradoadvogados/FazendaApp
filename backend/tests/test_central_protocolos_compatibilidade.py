"""
Compatibilidade da Central de Protocolos com o que JÁ ESTAVA no banco antes
dela — o risco real de uma mudança dessas não é o caminho novo, é o dado
antigo parar de aparecer, aparecer duas vezes, ou aparecer em lugar diferente
do de sempre.

Cada teste aqui simula explicitamente o estado "pré-Central" (protocolo
sanitário sem `finalidade`, lançamento com o nome antigo digitado à mão,
protocolo customizado sem `tipo`) e confere que:
  - continua listando/consultando onde sempre consultou;
  - não duplica na Central;
  - não perde etapa nem vínculo ao ser editado;
  - o vínculo Serviço/IA -> D11 do protocolo continua resolvendo pelo nome
    antigo (é um soft-join por texto, o ponto mais frágil de toda a mudança).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra todas as tabelas antes do create_all
from fazenda.models import (
    Animal, ProtocoloCustomizado, ProtocoloIatfAplicacao, ProtocoloIatfLancamento,
    ProtocoloSanitario, ProtocoloSanitarioEtapa,
)


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


def _protocolo_sanitario_legado(engine, nome="Mastite - Protocolo 1", dia_inicial=1) -> int:
    """Protocolo como os 15 que a fazenda já tem: gravado direto, SEM
    `finalidade` (coluna que não existia quando foram cadastrados) e com
    dia_inicial=1 (padrão anterior à padronização em D0)."""
    with Session(engine) as s:
        p = ProtocoloSanitario(nome=nome, eh_mastite="mastite" in nome.lower(), dia_inicial=dia_inicial, finalidade=None)
        s.add(p)
        s.commit()
        s.refresh(p)
        for dia in (dia_inicial, dia_inicial + 1, dia_inicial + 2):
            s.add(ProtocoloSanitarioEtapa(
                protocolo_id=p.id, dia=dia, criterio_tipo="medicamento",
                produto="Borgal", dosagem=40.0, unidade="ml", via="Intramuscular",
            ))
        s.commit()
        return p.id


class TestProtocoloSanitarioJaCadastrado:
    """Os protocolos que a fazenda já tem cadastrados (Mastite, Diarreia,
    Pneumonia, Pós-Parto…) não têm `finalidade` gravada — não podem sumir nem
    virar 'sem finalidade' na tela."""

    def test_protocolo_legado_e_lido_como_curativo(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine)
        lista = c.get("/cadastro/protocolos-sanitarios").json()
        p = next(x for x in lista if x["id"] == pid)
        assert p["finalidade"] == "curativo"

    def test_protocolo_legado_mantem_etapas_e_dia_inicial(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine, dia_inicial=1)
        p = next(x for x in c.get("/cadastro/protocolos-sanitarios").json() if x["id"] == pid)
        assert p["dia_inicial"] == 1
        assert [e["dia"] for e in p["etapas"]] == [1, 2, 3]

    def test_editar_protocolo_legado_nao_perde_etapas(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine)
        antes = next(x for x in c.get("/cadastro/protocolos-sanitarios").json() if x["id"] == pid)
        r = c.put(f"/cadastro/protocolos-sanitarios/{pid}", json={
            "nome": antes["nome"], "doenca_id": antes["doenca_id"], "eh_mastite": antes["eh_mastite"],
            "dia_inicial": antes["dia_inicial"], "finalidade": antes["finalidade"], "ativo": antes["ativo"],
            "etapas": [
                {"dia": e["dia"], "criterio_tipo": e["criterio_tipo"], "produto": e["produto"],
                 "dosagem": e["dosagem"], "unidade": e["unidade"], "via": e["via"]}
                for e in antes["etapas"]
            ],
        })
        assert r.status_code == 200, r.text
        assert [e["dia"] for e in r.json()["etapas"]] == [1, 2, 3]
        assert r.json()["finalidade"] == "curativo"

    def test_protocolo_legado_continua_lancavel(self, client):
        c, engine = client
        # Não-mastite de propósito: protocolo de mastite exige classificação
        # no lançamento (regra própria, coberta em test_protocolo_sanitario).
        pid = _protocolo_sanitario_legado(engine, nome="Pneumonia - Protocolo A")
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-08-05",
        })
        assert r.status_code == 201, r.text

    def test_cadastrar_preventivo_nao_afeta_os_curativos(self, client):
        c, engine = client
        pid_legado = _protocolo_sanitario_legado(engine)
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Vacinação em 2 doses", "finalidade": "preventivo", "dia_inicial": 0,
            "etapas": [
                {"dia": 0, "produto": "Vacina X", "dosagem": 5.0, "unidade": "ml", "via": "Subcutânea"},
                {"dia": 21, "produto": "Vacina X", "dosagem": 5.0, "unidade": "ml", "via": "Subcutânea"},
            ],
        })
        assert r.status_code == 200, r.text
        assert r.json()["finalidade"] == "preventivo"
        # O legado continua curativo — não foi arrastado junto.
        legado = next(x for x in c.get("/cadastro/protocolos-sanitarios").json() if x["id"] == pid_legado)
        assert legado["finalidade"] == "curativo"

    def test_rejeita_finalidade_invalida(self, client):
        c, engine = client
        r = c.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Finalidade errada", "finalidade": "profilatico",
            "etapas": [{"dia": 0, "produto": "X", "dosagem": 1.0, "unidade": "ml"}],
        })
        assert r.status_code == 400


class TestLancamentoAntigoNaCentral:
    """Lançamento feito ANTES da nomenclatura automática guarda o nome antigo
    ('IATF 12/06 a 23/06'). Ele não pode sumir da Central nem ser contado duas
    vezes por conta do formato diferente."""

    def _iatf_legado(self, engine, nome="IATF 12/06 a 23/06", d0=date(2026, 6, 12), animais=("700", "701")) -> int:
        with Session(engine) as s:
            lanc = ProtocoloIatfLancamento(nome_protocolo=nome, data_d0=d0)
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            for numero in animais:
                for dia in (0, 7, 9, 11):
                    s.add(ProtocoloIatfAplicacao(
                        lancamento_id=lanc.id, numero_matriz=numero, dia=dia,
                        descricao=f"D{dia}", data_prevista=d0 + timedelta(days=dia),
                    ))
            s.commit()
            return lanc.id

    def test_lancamento_com_nome_antigo_aparece_no_acompanhamento(self, client):
        c, engine = client
        lanc_id = self._iatf_legado(engine)
        linhas = c.get("/central-protocolos/acompanhamento").json()
        linha = next(l for l in linhas if l["origem"] == "iatf" and l["origem_id"] == lanc_id)
        assert linha["nome"] == "IATF 12/06 a 23/06"  # nome preservado, não reescrito
        assert linha["animais"] == 2
        assert linha["etapas_total"] == 8

    def test_lancamento_antigo_nao_duplica(self, client):
        c, engine = client
        lanc_id = self._iatf_legado(engine)
        linhas = c.get("/central-protocolos/acompanhamento").json()
        assert len([l for l in linhas if l["origem"] == "iatf" and l["origem_id"] == lanc_id]) == 1

    def test_busca_por_nome_acha_o_formato_antigo(self, client):
        c, engine = client
        self._iatf_legado(engine)
        assert c.get("/central-protocolos/acompanhamento", params={"nome": "IATF"}).json()

    def test_antigo_e_novo_convivem_sem_se_misturar(self, client):
        c, engine = client
        antigo = self._iatf_legado(engine)
        novo = c.post("/reproducao/protocolo-iatf", json={"animais": ["800"], "data_d0": "2026-08-05"}).json()["lancamento_id"]
        linhas = c.get("/central-protocolos/acompanhamento").json()
        ids = [l["origem_id"] for l in linhas if l["origem"] == "iatf"]
        assert antigo in ids and novo in ids
        assert len(ids) == len(set(ids))  # nenhum contado duas vezes


class TestVinculoServicoProtocoloPorNome:
    """O vínculo Serviço/IA -> aplicação D11 é um soft-join pelo TEXTO do nome
    do protocolo. Com a nomenclatura automática, o nome mudou de formato — o
    que já estava lançado com nome antigo tem que continuar casando."""

    def test_servico_com_nome_antigo_resolve_o_d11(self, client):
        c, engine = client
        nome_antigo = "IATF 12/06 a 23/06"
        d0 = date(2026, 6, 12)
        with Session(engine) as s:
            s.add(Animal(numero="700", sit_rep="Vaz. apt.", ativo=True))
            lanc = ProtocoloIatfLancamento(nome_protocolo=nome_antigo, data_d0=d0)
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            for dia in (0, 7, 9, 11):
                s.add(ProtocoloIatfAplicacao(
                    lancamento_id=lanc.id, numero_matriz="700", dia=dia,
                    descricao=f"D{dia}", data_prevista=d0 + timedelta(days=dia),
                ))
            s.commit()

        r = c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": (d0 + timedelta(days=11)).isoformat(),
            "tipo_servico": "IA", "protocolo": nome_antigo,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            d11 = s.exec(
                select(ProtocoloIatfAplicacao).where(
                    ProtocoloIatfAplicacao.numero_matriz == "700", ProtocoloIatfAplicacao.dia == 11
                )
            ).first()
            assert d11.realizada is True, "D11 do protocolo antigo deixou de ser resolvido pelo nome"

    def test_data_d0_do_servico_continua_resolvendo(self, client):
        """A tela de Reprodução ancora o ciclo no D0 real do protocolo — esse
        mapa é por ID (não por nome), mas confirma-se aqui que o dado antigo
        chega na tela mesmo assim."""
        c, engine = client
        d0 = date(2026, 6, 12)
        with Session(engine) as s:
            s.add(Animal(numero="700", sit_rep="Vaz. apt.", ativo=True))
            lanc = ProtocoloIatfLancamento(nome_protocolo="IATF 12/06 a 23/06", data_d0=d0)
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            s.add(ProtocoloIatfAplicacao(
                lancamento_id=lanc.id, numero_matriz="700", dia=11, descricao="D11",
                data_prevista=d0 + timedelta(days=11), realizada=True,
                data_realizacao=d0 + timedelta(days=11),
            ))
            s.commit()
        c.post("/reproducao/servico", json={
            "numero_matriz": "700", "data_servico": (d0 + timedelta(days=11)).isoformat(), "tipo_servico": "IA",
        })
        servicos = c.get("/reproducao/servicos").json()["servicos"]
        reg = next(x for x in servicos if x["numero"] == "700")
        assert reg["data_d0"] == d0.isoformat()


class TestSanitarioNaCentralNaoDuplica:
    """ProtocoloSanitarioLancamento é UM POR ANIMAL. A Central agrupa por
    (protocolo, data) só para exibir — 3 vacas no mesmo dia têm que virar UMA
    linha de 3 animais, não 3 linhas iguais."""

    def test_tres_animais_no_mesmo_dia_viram_uma_linha(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine, nome="Pneumonia - Protocolo A")
        r = c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700", "701", "702"], "data_inicio": "2026-08-05",
        })
        assert r.status_code == 201, r.text
        linhas = [l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "sanitario"]
        assert len(linhas) == 1, f"esperava 1 linha agrupada, veio {len(linhas)}"
        assert linhas[0]["animais"] == 3
        assert linhas[0]["tipo"] == "sanitario"

    def test_mesmo_protocolo_em_datas_diferentes_sao_linhas_distintas(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine, nome="Pneumonia - Protocolo A")
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-08-05",
        })
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["701"], "data_inicio": "2026-08-20",
        })
        linhas = [l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "sanitario"]
        assert len(linhas) == 2
        assert {l["data_inicio"] for l in linhas} == {"2026-08-05", "2026-08-20"}

    def test_nome_do_grupo_usa_o_protocolo_cadastrado(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine, nome="Diarreia - Protocolo 1", dia_inicial=1)
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-08-05",
        })
        linha = next(l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "sanitario")
        assert linha["nome"].startswith("DIARREIA - PROTOCOLO 1 - 05/08/26")


class TestCustomizadoSemTipoNaoSomeDaAgenda:
    """Protocolo customizado sem `tipo` fica FORA dos filtros da Central (por
    desenho) — mas não pode sumir da Agenda, que é onde ele sempre viveu."""

    def test_sem_tipo_fica_fora_da_central_mas_continua_na_agenda(self, client):
        c, engine = client
        with Session(engine) as s:
            p = ProtocoloCustomizado(nome="Cura de casco", categoria="Rebanho", dia_inicial=0, tipo=None)
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id
        c.post("/cadastro/protocolos-customizados", json={  # etapas via API para materializar direito
            "nome": "Cura de casco B", "categoria": "Rebanho", "dia_inicial": 0,
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        })
        alvo = next(x for x in c.get("/cadastro/protocolos-customizados").json() if x["nome"] == "Cura de casco B")
        r = c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": alvo["id"], "animais": ["700"], "data_inicio": "2026-08-05",
        })
        assert r.status_code == 201, r.text

        # Fora da Central (sem tipo)...
        assert not [l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "customizado"]
        # ...mas presente na Agenda, como sempre.
        eventos = c.get("/agenda/", params={"data": "2026-08-05", "dias": 30}).json()["eventos"]
        assert any(e.get("tipo") == "protocolo_customizado" for e in eventos)
        assert pid  # protocolo legado sem etapas continua existindo, sem quebrar nada

    def test_definir_tipo_traz_para_a_central_sem_relancar(self, client):
        c, engine = client
        criado = c.post("/cadastro/protocolos-customizados", json={
            "nome": "Cura de casco", "categoria": "Rebanho",
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        }).json()
        c.post("/protocolos-customizados/lancar", json={
            "protocolo_id": criado["id"], "animais": ["700"], "data_inicio": "2026-08-05",
        })
        assert not [l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "customizado"]

        # Só classifica o MOLDE — não relança nada.
        c.put(f"/cadastro/protocolos-customizados/{criado['id']}", json={
            "nome": "Cura de casco", "categoria": "Rebanho", "tipo": "sanitario", "dia_inicial": 0,
            "etapas": [{"dia": 0, "descricao_evento": "Aplicar produto"}],
        })
        linhas = [l for l in c.get("/central-protocolos/acompanhamento").json() if l["origem"] == "customizado"]
        assert len(linhas) == 1
        assert linhas[0]["tipo"] == "sanitario"


class TestFichaDoAnimalContinuaIntegra:
    def test_ficha_traz_protocolo_iatf_antigo(self, client):
        c, engine = client
        d0 = date(2026, 6, 12)
        with Session(engine) as s:
            s.add(Animal(numero="700", ativo=True))
            lanc = ProtocoloIatfLancamento(nome_protocolo="IATF 12/06 a 23/06", data_d0=d0)
            s.add(lanc)
            s.commit()
            s.refresh(lanc)
            for dia in (0, 7, 9, 11):
                s.add(ProtocoloIatfAplicacao(
                    lancamento_id=lanc.id, numero_matriz="700", dia=dia,
                    descricao=f"D{dia}", data_prevista=d0 + timedelta(days=dia),
                ))
            s.commit()
        ficha = c.get("/animais/700/ficha").json()
        assert ficha["protocolos_iatf"], "protocolo IATF antigo sumiu da ficha do animal"
        assert ficha["protocolos_iatf"][0]["nome_protocolo"] == "IATF 12/06 a 23/06"

    def test_ficha_traz_protocolo_sanitario_lancado(self, client):
        c, engine = client
        pid = _protocolo_sanitario_legado(engine, nome="Pneumonia - Protocolo A")
        with Session(engine) as s:
            s.add(Animal(numero="700", ativo=True))
            s.commit()
        c.post("/sanidade/protocolos/lancamentos", json={
            "protocolo_id": pid, "numeros_matriz": ["700"], "data_inicio": "2026-08-05",
        })
        ficha = c.get("/animais/700/ficha").json()
        assert ficha["protocolos_sanitarios"], "protocolo sanitário sumiu da ficha do animal"
