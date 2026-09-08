"""
A NATUREZA do vale-alimentação — a pergunta que decide dinheiro de verdade:
**o benefício entra ou não na base de INSS, FGTS, 13º e férias?**

A resposta não depende do valor nem da periodicidade (isso é
`test_folha_vale_alimentacao.py`). Depende de COMO o benefício é pago, de a
fazenda estar ou não no PAT, e de o funcionário já vir recebendo o benefício
antes de a fazenda mudar de ideia. É a árvore inteira que este arquivo trava,
uma linha de teste por linha da tabela:

  | Como é pago                     | Natureza          | Integra? | Fundamento                       |
  |---------------------------------|-------------------|----------|----------------------------------|
  | DINHEIRO, na folha              | SALARIAL          | SIM      | CLT, art. 457, §2º               |
  | CARTÃO/TICKET, fazenda NO PAT   | indenizatória     | não      | OJ 133/SDI-1; Lei 8.212/91, 28§9 |
  | CARTÃO/TICKET, fazenda FORA PAT | indenizatória     | não      | art. 457 §2º + SC COSIT 35/2019  |
  | REFEIÇÃO SERVIDA (in natura)    | salário-utilidade | SIM      | CLT, art. 458, caput             |
  |   ↳ ... com a fazenda NO PAT    | indenizatória     | não      | OJ 133/SDI-1                     |

Mais a TRAVA (OJ 413 da SDI-1 do TST), que vence forma e PAT: quem já vinha
recebendo o VA com natureza salarial não perde essa natureza porque a fazenda
mudou a forma de pagamento depois nem porque aderiu ao PAT depois — seria
alteração contratual lesiva (CLT, art. 468). Ela é marcador POR FUNCIONÁRIO
justamente porque a mesma fazenda pode ter DUAS populações com regras
diferentes na mesma folha, e é isso que o teste de duas pessoas na mesma
competência prova.

E mais o que a natureza provoca do outro lado do holerite: VA salarial ENTRA
na base de INSS (o funcionário paga contribuição sobre ele) e no FGTS que a
fazenda provisiona; indenizatório fica de fora. Não é preciosismo de rótulo —
é o valor retido que muda, no mesmo mês, para o mesmo salário.

FOLHA JÁ PAGA NÃO MUDA, e isso continua valendo aqui: trocar a forma de
pagamento hoje reescreve a linha das competências AINDA ABERTAS e não toca
num centavo de recibo emitido, cuja discriminação está congelada. Há teste.

A CONTAGEM DE DIAS entra neste arquivo por proximidade, não por acaso: as três
bases (corridos/úteis/trabalhados) e a proporcionalidade de admissão e de
rescisão são as outras escolhas que não têm norma legal fixando — quem manda é
a convenção coletiva rural da base, depois o contrato, depois a política da
fazenda —, e por isso viraram parâmetro em vez de constante escondida.
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
    ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaRubrica, ParametroFazenda, Pessoa,
    RescisaoFuncionario, Usuario, UsuarioFazenda,
)
from fazenda.auth import MODULOS
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import rubrica_folha, vale_alimentacao
from fazenda.rules.vale_alimentacao import (
    BASE_DIAS_CORRIDOS,
    BASE_DIAS_TRABALHADOS,
    BASE_DIAS_UTEIS,
    FORMA_CARTAO,
    FORMA_DINHEIRO,
    FORMA_IN_NATURA,
    dias_do_beneficio,
    enquadramento_do_vale_alimentacao,
    natureza_do_vale_alimentacao,
)

SALARIAL = rubrica_folha.NATUREZA_SALARIAL
INDENIZATORIA = rubrica_folha.NATUREZA_INDENIZATORIA

# Fevereiro de 2026 começa num DOMINGO e tem 28 dias — 4 domingos e 4 sábados.
# Corridos 28, trabalhados (seg-sáb) 24, úteis (seg-sex) 20: os três números
# são distintos, que é o que faz o teste das bases valer alguma coisa.
COMPETENCIA = "2026-02"
VALOR_BASE = 25.0


# ---------------------------------------------------------------------------
# A árvore, uma linha de teste por linha da tabela — regra pura, sem banco
# ---------------------------------------------------------------------------
class TestArvoreDaNatureza:
    def test_dinheiro_e_salarial_e_integra_tudo(self):
        """CLT, art. 457, §2º: a exclusão da base vale "vedado seu pagamento em
        dinheiro". Pago em dinheiro, o auxílio não entra na exclusão — é
        salário para INSS, FGTS, 13º e férias. É a linha da árvore que o
        sistema errava antes de existir o campo de forma."""
        assert natureza_do_vale_alimentacao(FORMA_DINHEIRO) == SALARIAL
        enq = enquadramento_do_vale_alimentacao(FORMA_DINHEIRO)
        assert enq["integra_bases"] is True
        assert enq["incide_inss"] and enq["incide_irrf"] and enq["incide_fgts"]
        assert "457" in enq["fundamento"]
        # E o PAT não salva o pagamento em dinheiro: o programa não autoriza
        # essa forma, então estar inscrito não muda a natureza.
        assert natureza_do_vale_alimentacao(FORMA_DINHEIRO, fazenda_no_pat=True) == SALARIAL

    def test_cartao_com_pat_e_indenizatorio(self):
        """OJ 133 da SDI-1 do TST; Lei 8.212/91, art. 28, §9º, "c"."""
        assert natureza_do_vale_alimentacao(FORMA_CARTAO, fazenda_no_pat=True) == INDENIZATORIA
        enq = enquadramento_do_vale_alimentacao(FORMA_CARTAO, fazenda_no_pat=True)
        assert enq["integra_bases"] is False
        assert not (enq["incide_inss"] or enq["incide_irrf"] or enq["incide_fgts"])
        assert "OJ 133" in enq["fundamento"]

    def test_cartao_sem_pat_tambem_e_indenizatorio(self):
        """A linha que mais surpreende quem só conhece a OJ 133: desde
        11/11/2017 o PAT deixou de ser necessário por esta via — CLT, art. 457,
        §2º, na redação da Lei 13.467/2017, e Solução de Consulta COSIT nº
        35/2019 da Receita Federal. Fazenda fora do PAT que paga em cartão NÃO
        recolhe INSS sobre o benefício."""
        assert natureza_do_vale_alimentacao(FORMA_CARTAO, fazenda_no_pat=False) == INDENIZATORIA
        enq = enquadramento_do_vale_alimentacao(FORMA_CARTAO, fazenda_no_pat=False)
        assert enq["integra_bases"] is False
        assert "COSIT" in enq["fundamento"]

    def test_refeicao_servida_fora_do_pat_e_salario_utilidade(self):
        """CLT, art. 458, caput: a alimentação fornecida in natura é
        salário-utilidade e INTEGRA a remuneração. É a segunda linha da árvore
        em que o benefício vira base de INSS/FGTS/13º/férias."""
        assert natureza_do_vale_alimentacao(FORMA_IN_NATURA, fazenda_no_pat=False) == SALARIAL
        enq = enquadramento_do_vale_alimentacao(FORMA_IN_NATURA, fazenda_no_pat=False)
        assert enq["integra_bases"] is True
        assert "458" in enq["fundamento"]

    def test_refeicao_servida_dentro_do_pat_deixa_de_integrar(self):
        """A ressalva do art. 458 — OJ 133 da SDI-1 do TST. É o ÚNICO caso em
        que estar no PAT muda a resposta, e é por isso que o PAT é parâmetro da
        fazenda e não enfeite de tela."""
        assert natureza_do_vale_alimentacao(FORMA_IN_NATURA, fazenda_no_pat=True) == INDENIZATORIA
        assert "OJ 133" in enquadramento_do_vale_alimentacao(
            FORMA_IN_NATURA, fazenda_no_pat=True,
        )["fundamento"]

    def test_forma_nao_informada_cai_no_lado_que_nao_subdeclara(self):
        """O "não sei" tem de doer para o lado certo. Assumir "cartão" tiraria
        da base do INSS e do FGTS uma verba que talvez tivesse de entrar —
        subdeclaração, que aparece anos depois com juros e multa. Assumir
        salarial recolhe a mais: caro, visível no holerite do mês seguinte e
        reversível assim que alguém escolher a forma no cadastro."""
        for valor in (None, "", "vale_refeicao", "pix"):
            assert natureza_do_vale_alimentacao(valor) == SALARIAL, valor
        enq = enquadramento_do_vale_alimentacao(None)
        assert enq["forma"] is None
        assert enq["integra_bases"] is True
        assert "não informada" in enq["rotulo"]

    def test_a_lei_14442_e_conformidade_separada_e_nao_muda_natureza(self):
        """A Lei 14.442/2022 proíbe pagar o auxílio em dinheiro e converter/
        sacar o saldo, com multa de R$ 5.000 a R$ 50.000, dobrada na
        reincidência. É infração AUTÔNOMA: o aviso viaja no enquadramento para
        a tela poder mostrá-lo, e não altera a natureza que a árvore decidiu —
        nem bloqueia, porque a decisão é do empregador."""
        assert enquadramento_do_vale_alimentacao(FORMA_DINHEIRO)["aviso_lei_14442"] is True
        for forma in (FORMA_CARTAO, FORMA_IN_NATURA, None):
            assert enquadramento_do_vale_alimentacao(forma)["aviso_lei_14442"] is False


class TestTravaOJ413:
    """A OJ 413 da SDI-1 do TST virada código."""

    def test_a_trava_vence_a_forma_e_vence_o_pat(self):
        """"A pactuação em norma coletiva conferindo caráter indenizatório à
        verba 'auxílio-alimentação' ou a adesão posterior do empregador ao PAT
        não altera a natureza salarial da parcela, instituída anteriormente,
        para aqueles empregados que, habitualmente, já percebiam o benefício."
        Ou seja: mudar a forma depois (ou entrar no PAT depois) não limpa a
        natureza de quem já vinha recebendo — CLT, art. 468."""
        for forma in (FORMA_CARTAO, FORMA_IN_NATURA, FORMA_DINHEIRO, None):
            for pat in (False, True):
                assert natureza_do_vale_alimentacao(
                    forma, fazenda_no_pat=pat, travada_salarial=True,
                ) == SALARIAL, (forma, pat)

    def test_a_trava_carimba_o_fundamento_dela_na_linha(self):
        """O holerite precisa dizer POR QUE aquela linha é salarial num
        funcionário e indenizatória no colega ao lado — senão o dono lê dois
        recibos com retenções diferentes e nenhuma explicação."""
        enq = enquadramento_do_vale_alimentacao(
            FORMA_CARTAO, fazenda_no_pat=True, travada_salarial=True,
        )
        assert enq["natureza"] == SALARIAL
        assert enq["integra_bases"] is True
        assert "OJ 413" in enq["fundamento"]
        assert "travada" in enq["rotulo"]

    def test_sem_a_trava_a_mesma_configuracao_e_indenizatoria(self):
        """A contraprova — sem ela o teste acima passaria mesmo que a trava
        não fizesse nada."""
        assert natureza_do_vale_alimentacao(
            FORMA_CARTAO, fazenda_no_pat=True, travada_salarial=False,
        ) == INDENIZATORIA


# ---------------------------------------------------------------------------
# Contagem de dias — as três bases e a proporcionalidade dos dois extremos
# ---------------------------------------------------------------------------
class TestContagemDeDias:
    def test_as_tres_bases_contam_coisas_diferentes(self):
        """Fevereiro de 2026: 28 dias corridos, 24 trabalhados (segunda a
        sábado, a jornada rural) e 20 úteis (segunda a sexta). Se as três
        devolvessem o mesmo número o parâmetro seria decoração."""
        assert dias_do_beneficio(COMPETENCIA, base_dias=BASE_DIAS_CORRIDOS) == (28, 28)
        assert dias_do_beneficio(COMPETENCIA, base_dias=BASE_DIAS_TRABALHADOS) == (24, 24)
        assert dias_do_beneficio(COMPETENCIA, base_dias=BASE_DIAS_UTEIS) == (20, 20)

    def test_base_desconhecida_cai_no_padrao_trabalhados(self):
        """Padrão de POLÍTICA pode existir (errar a base muda quantos dias se
        paga, não se a verba integra o salário) — ao contrário da forma de
        pagamento, que não tem padrão nenhum."""
        assert dias_do_beneficio(COMPETENCIA, base_dias="quinzenal") == (24, 24)
        assert dias_do_beneficio(COMPETENCIA) == (24, 24)

    def test_mes_de_admissao_e_proporcional(self):
        """O benefício custeia a refeição dos dias em que houve vínculo: pagar
        o mês cheio de quem entrou no dia 10 é pagar refeição de quem não
        estava lá."""
        admissao = date(2026, 2, 10)
        # 10 a 28/02: 19 corridos; em trabalhados, menos os domingos 15 e 22.
        assert dias_do_beneficio(COMPETENCIA, admissao, base_dias=BASE_DIAS_CORRIDOS) == (19, 28)
        assert dias_do_beneficio(COMPETENCIA, admissao, base_dias=BASE_DIAS_TRABALHADOS) == (17, 24)

    def test_o_interruptor_de_mes_de_admissao_integral(self):
        """Algumas CCTs mandam pagar o mês cheio no mês de admissão. Ligado, o
        parâmetro apaga a proporcionalidade — e só a da ADMISSÃO."""
        admissao = date(2026, 2, 10)
        assert dias_do_beneficio(
            COMPETENCIA, admissao, base_dias=BASE_DIAS_TRABALHADOS, mes_admissao_integral=True,
        ) == (24, 24)

    def test_mes_de_rescisao_e_proporcional_e_nao_tem_interruptor(self):
        """Simétrico da admissão, e sem escapatória: nenhuma norma manda pagar
        refeição depois do desligamento, então `mes_admissao_integral` NÃO
        alcança este lado."""
        desligamento = date(2026, 2, 10)
        assert dias_do_beneficio(
            COMPETENCIA, None, desligamento, base_dias=BASE_DIAS_CORRIDOS,
        ) == (10, 28)
        # 1 a 10/02/2026 em trabalhados: sem os domingos 1 e 8.
        assert dias_do_beneficio(
            COMPETENCIA, None, desligamento, base_dias=BASE_DIAS_TRABALHADOS,
        ) == (8, 24)
        assert dias_do_beneficio(
            COMPETENCIA, None, desligamento, base_dias=BASE_DIAS_TRABALHADOS,
            mes_admissao_integral=True,
        ) == (8, 24)

    def test_admissao_e_rescisao_no_mesmo_mes_contam_so_o_miolo(self):
        admitido = date(2026, 2, 5)
        desligado = date(2026, 2, 20)
        assert dias_do_beneficio(
            COMPETENCIA, admitido, desligado, base_dias=BASE_DIAS_CORRIDOS,
        ) == (16, 28)

    def test_competencia_fora_do_vinculo_nao_gera_dia_nenhum(self):
        """Admissão depois do fim da competência (alcançável no regime
        antecipado, em que a folha olha para o mês seguinte) e desligamento
        antes do início dela: zero, e quem chama transforma zero em "não há
        linha", nunca numa linha de R$ 0,00 no holerite."""
        assert dias_do_beneficio(COMPETENCIA, date(2026, 5, 1))[0] == 0
        assert dias_do_beneficio(COMPETENCIA, None, date(2025, 12, 31))[0] == 0

    def test_falta_injustificada_desconta_sempre_e_a_justificada_so_se_a_cct_mandar(self):
        """Falta INJUSTIFICADA suprime o dia (não houve jornada, não houve
        refeição a custear) e isso é fixo. Falta JUSTIFICADA, férias,
        afastamento pelo INSS e feriado normalmente NÃO suprimem — mas a CCT da
        base decide, e por isso é parâmetro."""
        base = dict(base_dias=BASE_DIAS_TRABALHADOS)
        assert dias_do_beneficio(COMPETENCIA, faltas_injustificadas=3, **base) == (21, 24)
        assert dias_do_beneficio(COMPETENCIA, faltas_justificadas=3, **base) == (24, 24)
        assert dias_do_beneficio(
            COMPETENCIA, faltas_justificadas=3, falta_justificada_desconta=True, **base,
        ) == (21, 24)
        # Mês inteiro de falta não vira dia negativo.
        assert dias_do_beneficio(COMPETENCIA, faltas_injustificadas=99, **base) == (0, 24)


# ---------------------------------------------------------------------------
# O que a natureza provoca na FOLHA — com token real e recorte por fazenda
# ---------------------------------------------------------------------------
@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.add(Usuario(id=1, username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        # Usuário comum (não-admin) para provar que a trava da OJ 413 é
        # privativa de administrador.
        s.add(Usuario(
            id=2, username="operador1", senha_hash=hash_senha("x"), papel="usuario", ativo=True,
            permissoes=",".join(MODULOS),
        ))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=1))
        s.commit()
        for chave in ("antigo", "novo"):
            pessoa = Pessoa(
                nome=f"Leomir {chave}", tipo="Funcionário", salario_base=3000.0,
                data_admissao=date(2024, 1, 10), fazenda_id=1,
            )
            s.add(pessoa)
            s.commit()
            s.refresh(pessoa)
            ids[chave] = pessoa.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(username: str = "admin1", fazenda_id: int = 1):
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


def _parametro(engine, chave: str, valor: str) -> None:
    """Grava o parâmetro DA FAZENDA 1 (clone-on-write, como o router faz) —
    é assim que o PAT e a base de dias chegam à regra."""
    with Session(engine) as s:
        linha = s.exec(
            select(ParametroFazenda).where(
                ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == 1,
            )
        ).first()
        if linha is None:
            linha = ParametroFazenda(chave=chave, fazenda_id=1, grupo="folha_rh", label=chave)
        linha.valor = valor
        linha.tipo = "bool" if valor in ("true", "false") else "texto"
        s.add(linha)
        s.commit()


def _configurar(engine, pessoa_id: int, **campos) -> None:
    with Session(engine) as s:
        p = s.get(Pessoa, pessoa_id)
        p.vale_alimentacao = True
        p.vale_alimentacao_valor = campos.pop("valor", 600.0)
        p.vale_alimentacao_periodicidade = campos.pop("periodicidade", "mensal")
        p.vale_alimentacao_regime = "vencido"
        p.vale_alimentacao_forma = campos.pop("forma", FORMA_CARTAO)
        p.vale_alimentacao_natureza_travada_salarial = campos.pop("travada", False)
        for campo, valor in campos.items():
            setattr(p, campo, valor)
        s.add(p)
        s.commit()


def _criar_folha(c, pessoa_id: int, **extra) -> int:
    corpo = {
        "pessoa_id": pessoa_id, "competencia": COMPETENCIA, "valor_bruto": 3000.0,
        "percentual_inss": 9.0, "percentual_fgts": 8.0,
    }
    corpo.update(extra)
    r = c.post("/cadastro/folha-pagamento", json=corpo, headers=_cab())
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _folha(c, folha_id: int) -> dict:
    r = c.get("/cadastro/folha-pagamento", headers=_cab())
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["id"] == folha_id)


def _rubrica(engine, folha_id: int) -> FolhaRubrica | None:
    with Session(engine) as s:
        return s.exec(
            select(FolhaRubrica).where(
                FolhaRubrica.folha_id == folha_id,
                FolhaRubrica.codigo == vale_alimentacao.CODIGO,
            )
        ).first()


class TestNaturezaNaFolha:
    def test_va_salarial_entra_na_base_de_inss_e_de_fgts(self, ambiente):
        """A prova em dinheiro: VA de R$ 600 pago EM DINHEIRO sobre um salário
        de R$ 3.000 leva a base para R$ 3.600 — o INSS de 9% passa de R$ 270
        para R$ 324 e o FGTS de 8% de R$ 240 para R$ 288."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_DINHEIRO, valor=600.0)
        folha = _folha(c, _criar_folha(c, ids["novo"]))

        assert folha["bases"]["base_inss"] == 3600.0
        assert folha["valor_inss"] == 324.0
        assert folha["valor_fgts"] == 288.0
        assert folha["valor_rubricas_tributaveis"] == 600.0
        rubrica = _rubrica(engine, folha["id"])
        assert rubrica.natureza == SALARIAL
        assert rubrica.incide_inss and rubrica.incide_irrf and rubrica.incide_fgts
        # O VA não vira salário-base do mês seguinte em enquadramento nenhum —
        # isso é do "aumento na folha", e continua vindo do catálogo.
        assert not rubrica.incorpora_base

    def test_va_indenizatorio_fica_fora_das_bases(self, ambiente):
        """A contraprova, mesma folha, mesmo valor, só a forma muda."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=600.0)
        folha = _folha(c, _criar_folha(c, ids["novo"]))

        assert folha["bases"]["base_inss"] == 3000.0
        assert folha["valor_inss"] == 270.0
        assert folha["valor_fgts"] == 240.0
        assert folha["valor_rubricas_tributaveis"] == 0.0
        rubrica = _rubrica(engine, folha["id"])
        assert rubrica.natureza == INDENIZATORIA
        assert not (rubrica.incide_inss or rubrica.incide_irrf or rubrica.incide_fgts)

    def test_o_pat_da_fazenda_muda_a_refeicao_servida(self, ambiente):
        """Refeição in natura: salário-utilidade fora do PAT (art. 458, caput),
        indenizatória dentro dele (OJ 133). O parâmetro é da FAZENDA, e é o
        único caso da árvore em que ele decide sozinho."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_IN_NATURA, valor=600.0)
        folha_id = _criar_folha(c, ids["novo"])
        assert _folha(c, folha_id)["bases"]["base_inss"] == 3600.0

        _parametro(engine, "inscrita_no_pat", "true")
        depois = _folha(c, folha_id)
        assert depois["bases"]["base_inss"] == 3000.0
        assert _rubrica(engine, folha_id).natureza == INDENIZATORIA

    def test_duas_populacoes_na_mesma_folha(self, ambiente):
        """O caso que a OJ 413 cria e que o sistema precisava saber
        representar: a fazenda entrou no PAT e passou a pagar em cartão, mas
        quem JÁ VINHA recebendo mantém a natureza salarial (art. 468 da CLT).
        Dois funcionários, mesma competência, mesma forma, mesmo PAT — e
        retenções diferentes, cada uma com o seu fundamento no papel."""
        c, engine, ids = ambiente
        _parametro(engine, "inscrita_no_pat", "true")
        _configurar(engine, ids["antigo"], forma=FORMA_CARTAO, valor=600.0, travada=True)
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=600.0, travada=False)

        antigo = _folha(c, _criar_folha(c, ids["antigo"]))
        novo = _folha(c, _criar_folha(c, ids["novo"]))

        assert antigo["bases"]["base_inss"] == 3600.0 and antigo["valor_inss"] == 324.0
        assert novo["bases"]["base_inss"] == 3000.0 and novo["valor_inss"] == 270.0
        assert _rubrica(engine, antigo["id"]).natureza == SALARIAL
        assert _rubrica(engine, novo["id"]).natureza == INDENIZATORIA

    def test_trocar_a_forma_reescreve_a_linha_da_competencia_aberta(self, ambiente):
        """Mudar a forma de pagamento não muda um centavo do VALOR do
        benefício — muda a base e o líquido. Sem este realinhamento a linha
        continuaria indenizatória para sempre, que é o defeito mais silencioso
        que este módulo poderia ter."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=600.0)
        folha_id = _criar_folha(c, ids["novo"])
        antes = _folha(c, folha_id)
        assert antes["valor_inss"] == 270.0

        _configurar(engine, ids["novo"], forma=FORMA_DINHEIRO, valor=600.0)
        depois = _folha(c, folha_id)
        assert depois["valor_inss"] == 324.0
        assert _rubrica(engine, folha_id).valor == 600.0  # o valor não mudou
        assert _rubrica(engine, folha_id).natureza == SALARIAL

    def test_folha_ja_paga_nao_e_reenquadrada(self, ambiente):
        """O recibo pago é PROVA. Trocar a forma no cadastro hoje vale para as
        competências ainda abertas e não reescreve a retenção que já saiu do
        caixa — nem para mais, nem para menos."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=600.0)
        folha_id = _criar_folha(c, ids["novo"], status="pago", data_pagamento="2026-03-05")
        paga = _folha(c, folha_id)
        assert paga["recibo_congelado"] is True
        assert paga["valor_inss"] == 270.0

        _configurar(engine, ids["novo"], forma=FORMA_DINHEIRO, valor=600.0)
        depois = _folha(c, folha_id)
        assert depois["valor_inss"] == 270.0
        assert _rubrica(engine, folha_id).natureza == INDENIZATORIA

    def test_a_referencia_do_holerite_declara_a_forma_e_o_regime(self, ambiente):
        """Duas linhas idênticas com retenções diferentes exigem explicação no
        papel — a forma vem da `descricao` gravada, a natureza e as incidências
        de `referencia_rubrica`, a partir do que ficou congelado na linha."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_DINHEIRO, valor=600.0)
        folha = _folha(c, _criar_folha(c, ids["novo"]))
        linha = next(
            d for d in folha["detalhe"]
            if (d.get("origem") or {}).get("codigo") == vale_alimentacao.CODIGO
        )
        assert "pago em dinheiro" in linha["referencia"]
        assert "natureza salarial" in linha["referencia"]
        assert "entra nas bases de INSS, IRRF e FGTS" in linha["referencia"]

    def test_a_base_de_dias_da_fazenda_chega_na_folha(self, ambiente):
        """O parâmetro não é decoração: trocar a contagem muda o valor pago no
        holerite da competência aberta."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=VALOR_BASE, periodicidade="diario")
        folha_id = _criar_folha(c, ids["novo"])
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 24, 2)

        _parametro(engine, "vale_alimentacao_base_dias", "corridos")
        _folha(c, folha_id)
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 28, 2)

        _parametro(engine, "vale_alimentacao_base_dias", "uteis")
        _folha(c, folha_id)
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 20, 2)

    def test_rescisao_fechada_encolhe_o_va_diario_do_mes_da_saida(self, ambiente):
        """Desligamento no dia 10 de fevereiro: o benefício cobre 1 a 10, não o
        mês inteiro. Simulação NÃO conta — cortar o benefício por um cenário
        que ninguém fechou seria pagar a menos por uma conta que não existe."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, valor=VALOR_BASE, periodicidade="diario")
        folha_id = _criar_folha(c, ids["novo"])
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 24, 2)

        with Session(engine) as s:
            s.add(RescisaoFuncionario(
                pessoa_id=ids["novo"], fazenda_id=1, data_desligamento=date(2026, 2, 10),
                data_admissao=date(2024, 1, 10), salario_base=3000.0,
                tipo_rescisao="sem_justa_causa", status="simulacao",
            ))
            s.commit()
        _folha(c, folha_id)
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 24, 2)

        with Session(engine) as s:
            resc = s.exec(select(RescisaoFuncionario)).first()
            resc.status = "fechada"
            s.add(resc)
            s.commit()
        _folha(c, folha_id)
        # 1 a 10/02/2026 em dias trabalhados: sem os domingos 1 e 8.
        assert _rubrica(engine, folha_id).valor == round(VALOR_BASE * 8, 2)


class TestCadastroDaFormaEDaTrava:
    def _payload(self, **extra) -> dict:
        corpo = {"nome": "Leomir novo", "tipos": ["Funcionário"]}
        corpo.update(extra)
        return corpo

    def test_a_forma_e_obrigatoria_com_o_beneficio_ligado(self, ambiente):
        c, _engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['novo']}",
            json=self._payload(
                vale_alimentacao=True, vale_alimentacao_valor=25.0,
                vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
            ),
            headers=_cab(),
        )
        assert r.status_code == 400, r.text
        assert "COMO o vale-alimentação é pago" in r.json()["detail"]

    def test_forma_invalida_e_recusada(self, ambiente):
        c, _engine, ids = ambiente
        r = c.put(
            f"/cadastro/pessoas/{ids['novo']}",
            json=self._payload(
                vale_alimentacao=True, vale_alimentacao_valor=25.0,
                vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
                vale_alimentacao_forma="pix",
            ),
            headers=_cab(),
        )
        assert r.status_code == 400, r.text

    def test_beneficio_desligado_nao_exige_forma(self, ambiente):
        c, _engine, ids = ambiente
        r = c.put(f"/cadastro/pessoas/{ids['novo']}", json=self._payload(), headers=_cab())
        assert r.status_code == 200, r.text

    def test_so_administrador_liga_a_trava_da_oj413(self, ambiente):
        """Ela é o único campo do cadastro que aumenta a carga de INSS/FGTS de
        um funcionário específico contra o que a forma diria — e o único que,
        desligado por engano, tira de alguém uma proteção que a jurisprudência
        lhe deu. 403 com explicação, não 404: o recurso é desta fazenda e o
        usuário pode editá-lo; o que falta é papel para mexer NESTE campo."""
        c, engine, ids = ambiente
        corpo = self._payload(
            vale_alimentacao=True, vale_alimentacao_valor=25.0,
            vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
            vale_alimentacao_forma=FORMA_CARTAO,
            vale_alimentacao_natureza_travada_salarial=True,
        )
        r = c.put(f"/cadastro/pessoas/{ids['novo']}", json=corpo, headers=_cab("operador1"))
        assert r.status_code == 403, r.text
        assert "OJ 413" in r.json()["detail"]
        with Session(engine) as s:
            assert not s.get(Pessoa, ids["novo"]).vale_alimentacao_natureza_travada_salarial

        r = c.put(f"/cadastro/pessoas/{ids['novo']}", json=corpo, headers=_cab())
        assert r.status_code == 200, r.text
        assert r.json()["vale_alimentacao_natureza_travada_salarial"] is True

    def test_usuario_comum_salvando_o_cadastro_nao_desliga_a_trava(self, ambiente):
        """OMITIR NÃO É DESLIGAR. A tela só mostra o campo para administrador,
        então o PUT de um usuário comum vem sem ele — e um `setattr` cru
        gravaria None por cima, apagando a trava em silêncio ao salvar um
        telefone novo."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, travada=True)

        r = c.put(
            f"/cadastro/pessoas/{ids['novo']}",
            json=self._payload(
                telefones=["34999990000"],
                vale_alimentacao=True, vale_alimentacao_valor=600.0,
                vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
                vale_alimentacao_forma=FORMA_CARTAO,
            ),
            headers=_cab("operador1"),
        )
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Pessoa, ids["novo"]).vale_alimentacao_natureza_travada_salarial is True

    def test_reenviar_o_mesmo_valor_da_trava_nao_exige_administrador(self, ambiente):
        """A tela devolve o formulário inteiro; reenviar o valor que já está lá
        não é alteração e não pode virar 403 num usuário que só queria corrigir
        o CPF."""
        c, engine, ids = ambiente
        _configurar(engine, ids["novo"], forma=FORMA_CARTAO, travada=True)
        r = c.put(
            f"/cadastro/pessoas/{ids['novo']}",
            json=self._payload(
                vale_alimentacao=True, vale_alimentacao_valor=600.0,
                vale_alimentacao_periodicidade="mensal", vale_alimentacao_regime="vencido",
                vale_alimentacao_forma=FORMA_CARTAO,
                vale_alimentacao_natureza_travada_salarial=True,
            ),
            headers=_cab("operador1"),
        )
        assert r.status_code == 200, r.text
