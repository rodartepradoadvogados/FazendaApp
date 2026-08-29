"""
Onda "Protocolo à Mostra" — Fase 1: dose fixa ou por peso vivo do protocolo
sanitário.

Cobre: o motor puro de interpretação/cálculo (rules/dose_protocolo.py), a
validação da lista fechada no cadastro, e o backfill report-first que separa
a referência de peso embutida como texto em `unidade` — incluindo o caso
real que motivou a onda: Banamine cadastrado a 40kg no protocolo, 45kg na
bula, e ninguém percebendo porque os dois nunca foram lidos juntos.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models.sanidade import MedicamentoComercial, PrincipioAtivo, ProtocoloSanitario, ProtocoloSanitarioEtapa
from fazenda.rules.dose_protocolo import calcular_dose, formula_legivel, interpretar_unidade_legada


# ---------------------------------------------------------------------------
# Motor puro
# ---------------------------------------------------------------------------
class TestInterpretarUnidadeLegada:
    @pytest.mark.parametrize("texto,modo_esperado,unidade_esperada,referencia_esperada", [
        ("ml / 15kg PV", "por_peso", "ml", 15.0),
        ("ML/15 KG PV", "por_peso", "ML", 15.0),
        ("ml/15kg", "por_peso", "ml", 15.0),
        ("mL / 45 Kg P.V.", "por_peso", "mL", 45.0),
        ("ml / 100kg PV", "por_peso", "ml", 100.0),
    ])
    def test_reconhece_referencia_de_peso_em_grafias_variadas(self, texto, modo_esperado, unidade_esperada, referencia_esperada):
        assert interpretar_unidade_legada(texto) == (modo_esperado, unidade_esperada, referencia_esperada)

    def test_unidade_sem_referencia_de_peso_e_dose_fixa(self):
        """Aliv V no protocolo real é "10 mL" sem "/kg" — dose fixa de
        verdade, não um caso a migrar."""
        assert interpretar_unidade_legada("ml") == ("fixa", "ml", None)

    def test_vazio_ou_none_nao_quebra(self):
        assert interpretar_unidade_legada("") == ("fixa", "", None)
        assert interpretar_unidade_legada(None) == ("fixa", None, None)

    def test_texto_que_nao_casa_o_padrao_nao_inventa_referencia(self):
        """Errar para "não calculado" é sempre mais seguro que adivinhar uma
        referência de peso que não estava escrita."""
        assert interpretar_unidade_legada("2 comprimidos ao dia") == ("fixa", "2 comprimidos ao dia", None)


class TestCalcularDose:
    def test_resflor_640kg(self):
        """2 mL a cada 15 kg, animal de 640 kg -> 85,3 mL."""
        assert calcular_dose(dosagem=2, dose_referencia_kg=15, peso_animal_kg=640) == pytest.approx(85.3, abs=0.05)

    def test_banamine_com_referencia_correta_da_bula_640kg(self):
        assert calcular_dose(dosagem=2, dose_referencia_kg=45, peso_animal_kg=640) == pytest.approx(28.4, abs=0.05)

    def test_peso_igual_a_referencia_devolve_a_dosagem_pura(self):
        assert calcular_dose(dosagem=2.5, dose_referencia_kg=100, peso_animal_kg=100) == pytest.approx(2.5)

    def test_dose_referencia_zero_ou_negativa_rejeitada(self):
        with pytest.raises(ValueError):
            calcular_dose(dosagem=2, dose_referencia_kg=0, peso_animal_kg=640)
        with pytest.raises(ValueError):
            calcular_dose(dosagem=2, dose_referencia_kg=-15, peso_animal_kg=640)

    def test_formula_legivel(self):
        assert formula_legivel(2, "mL", 15) == "2 mL a cada 15 kg PV"
        assert formula_legivel(2.5, "mL", 100) == "2.5 mL a cada 100 kg PV"


# ---------------------------------------------------------------------------
# Integração via API — cadastro e backfill
# ---------------------------------------------------------------------------
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
        c._engine = engine  # type: ignore[attr-defined]
        yield c

    main.app.dependency_overrides.clear()


def _etapa_fixa(dia=1, produto="Aliv V", dosagem=10.0, unidade="mL", via="Intramuscular"):
    return {"dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": via, "modo_dose": "fixa"}


def _etapa_por_peso(dia=1, produto="Resflor", dosagem=2.0, dose_referencia_kg=15.0, unidade="mL", via="Subcutânea"):
    return {
        "dia": dia, "produto": produto, "dosagem": dosagem, "unidade": unidade, "via": via,
        "modo_dose": "por_peso", "dose_referencia_kg": dose_referencia_kg,
    }


class TestCadastroComModoDose:
    def test_cadastra_etapa_fixa_sem_precisar_de_referencia(self, client):
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo Teste Fixa", "etapas": [_etapa_fixa()],
        })
        assert r.status_code == 200, r.text
        etapa = r.json()["etapas"][0]
        assert etapa["modo_dose"] == "fixa"
        assert etapa["dose_referencia_kg"] is None

    def test_cadastra_etapa_por_peso_com_referencia(self, client):
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo Teste Peso", "etapas": [_etapa_por_peso()],
        })
        assert r.status_code == 200, r.text
        etapa = r.json()["etapas"][0]
        assert etapa["modo_dose"] == "por_peso"
        assert etapa["dose_referencia_kg"] == 15.0

    def test_etapa_legada_sem_modo_dose_no_payload_vira_fixa(self, client):
        """Compatibilidade: importação por planilha e qualquer chamador antigo
        nunca mandam `modo_dose`/`dose_referencia_kg` — o default tem que
        reproduzir exatamente o comportamento de sempre."""
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "Protocolo Sem Modo Dose",
            "etapas": [{"dia": 1, "produto": "X", "dosagem": 10.0, "unidade": "ml"}],
        })
        assert r.status_code == 200, r.text
        assert r.json()["etapas"][0]["modo_dose"] == "fixa"

    def test_modo_dose_invalido_e_rejeitado(self, client):
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "X", "etapas": [{**_etapa_fixa(), "modo_dose": "inventado"}],
        })
        assert r.status_code == 400

    def test_por_peso_sem_referencia_e_rejeitado(self, client):
        """Dose por peso sem o kg de referência não tem como ser calculada —
        travar aqui é melhor que deixar `dose_referencia_kg=None` chegar ao
        lançamento e a divisão quebrar lá."""
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "X", "etapas": [{**_etapa_por_peso(), "dose_referencia_kg": None}],
        })
        assert r.status_code == 400

    def test_por_peso_com_referencia_zero_e_rejeitado(self, client):
        r = client.post("/cadastro/protocolos-sanitarios", json={
            "nome": "X", "etapas": [{**_etapa_por_peso(), "dose_referencia_kg": 0}],
        })
        assert r.status_code == 400


class TestBackfillDoseMigrar:
    def _criar_legado(self, engine, *, produto: str, unidade: str, dosagem: float = 2.0):
        with Session(engine) as s:
            protocolo = ProtocoloSanitario(nome="Pneumonia - Protocolo A")
            s.add(protocolo)
            s.commit()
            s.refresh(protocolo)
            etapa = ProtocoloSanitarioEtapa(
                protocolo_id=protocolo.id, dia=1, produto=produto, dosagem=dosagem, unidade=unidade, via="Intramuscular",
            )
            s.add(etapa)
            s.commit()
            s.refresh(etapa)
            return protocolo.id, etapa.id

    def _seed_bula_banamine(self, engine, dose_referencia_kg: float = 45.0):
        with Session(engine) as s:
            principio = PrincipioAtivo(nome="Flunixina Meglumina")
            s.add(principio)
            s.commit()
            s.refresh(principio)
            s.add(MedicamentoComercial(
                principio_ativo_id=principio.id, nome_comercial="Banamine",
                dose_padrao=2.0, unidade_dose="ml", dose_base="por_kg_pv",
                dose_referencia_kg=dose_referencia_kg, dose_texto=f"2 mL/{dose_referencia_kg:g} kg PV",
            ))
            s.commit()

    def test_previa_nao_grava_nada(self, client):
        _protocolo_id, etapa_id = self._criar_legado(client._engine, produto="Resflor", unidade="ml / 15kg PV")
        previa = client.post("/cadastro/protocolos-sanitarios/dose-migrar").json()
        assert previa["aplicado"] is False
        assert previa["total"] == 1
        with Session(client._engine) as s:
            etapa = s.get(ProtocoloSanitarioEtapa, etapa_id)
            assert etapa.modo_dose == "fixa", "prévia não pode gravar"
            assert etapa.dose_referencia_kg is None

    def test_migra_pelo_texto_quando_nao_ha_bula(self, client):
        """Resflor não está no catálogo de bula — usa o número que já estava
        escrito no próprio protocolo."""
        _protocolo_id, etapa_id = self._criar_legado(client._engine, produto="Resflor", unidade="ml / 15kg PV")
        aplicado = client.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true").json()
        assert aplicado["aplicado"] is True and aplicado["total"] == 1
        item = aplicado["itens"][0]
        assert item["origem"] == "texto_da_unidade"
        assert item["dose_referencia_kg"] == 15.0
        assert item["divergencia"] is None
        with Session(client._engine) as s:
            etapa = s.get(ProtocoloSanitarioEtapa, etapa_id)
            assert etapa.modo_dose == "por_peso"
            assert etapa.dose_referencia_kg == 15.0
            assert etapa.unidade == "ml"

    def test_banamine_migra_para_o_valor_da_bula_e_sinaliza_a_divergencia(self, client):
        """O caso real que motivou a onda: protocolo cadastrado a 40kg, bula
        (fonte mais confiável, mantida por princípio ativo) a 45kg. A bula
        manda, e a divergência fica registrada no relatório."""
        self._seed_bula_banamine(client._engine, dose_referencia_kg=45.0)
        _protocolo_id, etapa_id = self._criar_legado(client._engine, produto="Banamine", unidade="ml / 40kg PV")

        previa = client.post("/cadastro/protocolos-sanitarios/dose-migrar").json()
        item = previa["itens"][0]
        assert item["origem"] == "bula_medicamento_comercial"
        assert item["dose_referencia_kg"] == 45.0
        assert "40" in item["divergencia"] and "45" in item["divergencia"]
        assert previa["divergencias"] == 1

        aplicado = client.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true").json()
        assert aplicado["total"] == 1
        with Session(client._engine) as s:
            etapa = s.get(ProtocoloSanitarioEtapa, etapa_id)
            assert etapa.dose_referencia_kg == 45.0, "a bula prevalece sobre o texto do protocolo"

    def test_bula_sem_referencia_preenchida_nao_e_usada(self, client):
        """Aliv V está no catálogo real com dose_referencia_kg=None (marcado
        'a revisar') — bula não confiável não pode substituir um número que
        já existia escrito no protocolo."""
        self._seed_bula_banamine(client._engine, dose_referencia_kg=45.0)
        with Session(client._engine) as s:
            principio = PrincipioAtivo(nome="Meloxicam")
            s.add(principio)
            s.commit()
            s.refresh(principio)
            s.add(MedicamentoComercial(
                principio_ativo_id=principio.id, nome_comercial="Aliv V",
                dose_base="por_kg_pv", dose_referencia_kg=None,
            ))
            s.commit()
        _protocolo_id, etapa_id = self._criar_legado(client._engine, produto="Aliv V", unidade="ml / 30kg PV")

        aplicado = client.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true").json()
        item = aplicado["itens"][0]
        assert item["origem"] == "texto_da_unidade"
        assert item["dose_referencia_kg"] == 30.0

    def test_dose_fixa_de_verdade_nao_entra_no_relatorio(self, client):
        """"10 mL" sem "/kg" (Aliv V neste protocolo, na vida real) não é um
        caso a migrar — não deve nem aparecer na prévia."""
        self._criar_legado(client._engine, produto="Aliv V", unidade="ml", dosagem=10.0)
        previa = client.post("/cadastro/protocolos-sanitarios/dose-migrar").json()
        assert previa["total"] == 0

    def test_backfill_e_idempotente(self, client):
        """Rodar de novo depois de aplicado não encontra mais nada a migrar —
        a etapa já está em modo_dose='por_peso' e sai do filtro."""
        self._criar_legado(client._engine, produto="Resflor", unidade="ml / 15kg PV")
        client.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true")
        segunda = client.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true").json()
        assert segunda["total"] == 0

    def test_varios_produtos_um_so_com_bula_confiavel(self, client):
        """Mistura realista: Resflor (sem bula) e Banamine (com bula
        divergente) no mesmo backfill — cada um resolvido pela sua própria
        regra, sem um contaminar o outro."""
        self._seed_bula_banamine(client._engine, dose_referencia_kg=45.0)
        self._criar_legado(client._engine, produto="Resflor", unidade="ml / 15kg PV")
        self._criar_legado(client._engine, produto="Banamine", unidade="ml / 40kg PV")
        previa = client.post("/cadastro/protocolos-sanitarios/dose-migrar").json()
        assert previa["total"] == 2
        por_produto = {i["produto"]: i for i in previa["itens"]}
        assert por_produto["Resflor"]["dose_referencia_kg"] == 15.0
        assert por_produto["Banamine"]["dose_referencia_kg"] == 45.0
