"""Réguas de referência: o arquivo versionado obedece às regras de validação, e as
regras do parecer jurídico de 08/10/2026 (dossiê por faixa, dupla validação, termos
das fontes, interruptores) decidem o que vai ao ar."""
import copy
from datetime import date

import pytest

from fazenda.rules import reguas_referencia as rr
from fazenda.rules import textos_juridicos as tj

HOJE = date(2026, 10, 9)


def _dados():
    return copy.deepcopy(rr.carregar())


def _textos(empresa: bool = True):
    t = copy.deepcopy(tj.carregar())
    if empresa:
        t["empresa"].update({"razao_social": "CowData Tecnologia Ltda.", "cnpj": "00.000.000/0001-00",
                             "email_responsavel": "reguas@cowdata.example"})
    return t


def _regua(d, codigo):
    return next(x for x in d["reguas"] if x["codigo"] == codigo)


def _fontes(d):
    return {f["id"]: f for f in d["fontes"]}


def _deixar_publicavel(d, codigo="comida_receita", validador="Dono"):
    """Completa o dossiê da régua como a dupla validação humana faria."""
    r = _regua(d, codigo)
    dos = r["dossie"]
    dos["fonte_br"]["pagina_ou_tabela"] = dos["fonte_br"]["pagina_ou_tabela"] or "Tabela 2"
    dos["fonte_estrangeira"]["pagina_ou_tabela"] = dos["fonte_estrangeira"]["pagina_ou_tabela"] or "Quadro 1"
    dos["independencia"] = {"sim_nao": "sim", "justificativa": "Levantamentos distintos."}
    dos["validado_por"] = [{"nome": validador, "em": "2026-10-09", "faixa": copy.deepcopy(r["faixa"])},
                           {"nome": "Alexandre Scarpa", "em": "2026-10-09", "faixa": copy.deepcopy(r["faixa"])}]
    dos["pendente_de"] = []
    dos["termos_verificados_em"] = "2026-10-09"
    por_id = _fontes(d)
    for fid in r["fontes"]:
        f = por_id[fid]
        f["termos_verificados_em"] = "2026-10-09"
        f["uso_comercial_confirmado_em"] = "2026-10-09"
        if f["licenca"] == "nao_verificada":
            f["licenca"] = "citar_com_link"
    return r


def _liberar(d):
    d["publicacao"].update({"liberada": True, "liberada_por": "Dono", "liberada_em": "2026-10-09"})


def _situacao(d, codigo, textos=None):
    av = rr.avaliar(d, hoje=HOJE, textos=textos or _textos())
    return next(a for a in av["reguas"] if a["codigo"] == codigo)


def _publicado():
    d = _dados()
    _deixar_publicavel(d)
    _liberar(d)
    return d


# ---------------------------------------------------------------------------
# Arquivos versionados
# ---------------------------------------------------------------------------
def test_arquivo_versionado_e_valido():
    assert rr.validar(rr.carregar(), hoje=HOJE) == []


def test_textos_versionados_sao_validos():
    assert tj.validar(tj.carregar()) == []


def test_estado_versionado_nao_publica_nada():
    """Hoje nada foi validado pelo dono nem pelo Alexandre Scarpa e a empresa não
    existe: nenhuma régua pode estar publicada."""
    av = rr.avaliar(hoje=HOJE)
    assert av["liberada"] is False and av["empresa_pendente"] is True
    assert {a["situacao"] for a in av["reguas"]} <= {"em_validacao", "sem_faixa"}
    d = rr.carregar()
    assert d["publicacao"]["liberada"] is False
    for r in d["reguas"]:
        assert r["dossie"]["validado_por"] == []
        assert r["dossie"]["termos_verificados_em"] is None
        assert r["dossie"]["pendente_de"] == ["dono", "Alexandre Scarpa"]
    assert all(f["termos_verificados_em"] is None and f["uso_comercial_confirmado_em"] is None for f in d["fontes"])


def test_nenhuma_fonte_cita_cepea():
    d = _dados()
    d["fontes"][0]["nome"] = "CNA/Senar/Cepea — Campo Futuro"
    assert any("Cepea" in e for e in rr.validar(d, hoje=HOJE))


# ---------------------------------------------------------------------------
# Regras que já valiam
# ---------------------------------------------------------------------------
def test_validada_exige_fonte_nacional_e_internacional():
    d = _dados()
    r = _regua(d, "comida_receita")
    nacionais = {f["id"] for f in d["fontes"] if f["origem"] == "nacional"}
    r["fontes"] = [x for x in r["fontes"] if x in nacionais]
    assert any("exige ao menos uma fonte nacional e uma internacional" in e for e in rr.validar(d, hoje=HOJE))


def test_selo_alto_exige_duas_de_cada_lado():
    d = _dados()
    r = _regua(d, "comida_receita")
    r["fontes"] = [x for x in r["fontes"] if x not in ("minnesota_fbm_2024", "dfmp_wa_2023_24")]
    assert any("selo alta" in e for e in rr.validar(d, hoje=HOJE))


def test_regua_nao_validada_nao_pode_exibir_faixa():
    d = _dados()
    r = _regua(d, "parcelas_receita")
    r["exibir_faixa"] = True
    r["faixa"] = {"max": 20}
    assert any("NAO_VALIDADA" in e for e in rr.validar(d, hoje=HOJE))


def test_fonte_com_licenca_vetada_e_recusada():
    d = _dados()
    d["fontes"].append({"id": "ahdb", "nome": "AHDB", "url": "https://ahdb.org.uk/dairy/x", "origem": "internacional",
                        "ano": 2025, "licenca": "citar_com_link", "ativa": True, "caminho_parecer": "verificar_antes",
                        "termos_verificados_em": None, "uso_comercial_confirmado_em": None})
    assert any("não permite uso comercial" in e for e in rr.validar(d, hoje=HOJE))


def test_datas_no_futuro_e_fonte_inexistente_sao_recusadas():
    d = _dados()
    d["conferida_em"] = "2026-12-01"
    d["reguas"][0]["fontes"].append("nao_existe")
    erros = rr.validar(d, hoje=HOJE)
    assert any("futuro" in e for e in erros)
    assert any("inexistentes" in e for e in erros)


def test_regua_com_condicao_pendente_nao_exibe_faixa():
    d = _dados()
    cob = _regua(d, "cobertura_divida")
    assert cob["exibir_faixa"] is False and cob["condicao_para_exibir"]
    cob["exibir_faixa"] = True
    assert any("condição pendente" in e for e in rr.validar(d, hoje=HOJE))


# ---------------------------------------------------------------------------
# Dossiê (parecer 3.5) e dupla validação
# ---------------------------------------------------------------------------
def test_dossie_completo_validado_e_liberado_publica():
    d = _publicado()
    assert rr.validar(d, hoje=HOJE, textos=_textos()) == []
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "publicada" and a["publicavel"] is True and a["motivos"] == []


@pytest.mark.parametrize("campo", ["pagina_ou_tabela", "valor_lido"])
def test_dossie_incompleto_nao_publica(campo):
    d = _publicado()
    _regua(d, "comida_receita")["dossie"]["fonte_br"][campo] = None
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao"
    assert any(campo in m for m in a["motivos"])


def test_sem_fonte_estrangeira_no_dossie_nao_publica():
    d = _publicado()
    _regua(d, "comida_receita")["dossie"]["fonte_estrangeira"] = None
    assert _situacao(d, "comida_receita")["situacao"] == "em_validacao"


def test_independencia_nao_comprovada_nao_publica():
    d = _publicado()
    _regua(d, "comida_receita")["dossie"]["independencia"]["sim_nao"] = "nao"
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao" and any("independência" in m for m in a["motivos"])


def test_quem_compilou_nao_pode_validar():
    d = _publicado()
    r = _regua(d, "comida_receita")
    r["dossie"]["validado_por"] = [{"nome": "  claude (PESQUISA assistida por IA, rodada 2, a pedido do dono) ",
                                    "em": "2026-10-09", "faixa": copy.deepcopy(r["faixa"])}]
    assert any("dupla validação" in e for e in rr.validar(d, hoje=HOJE, textos=_textos()))
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao"
    assert any("pessoa diferente" in m for m in a["motivos"])


def test_sem_validacao_nao_publica():
    d = _publicado()
    r = _regua(d, "comida_receita")
    r["dossie"]["validado_por"] = []
    r["dossie"]["pendente_de"] = ["dono", "Alexandre Scarpa"]
    assert _situacao(d, "comida_receita")["situacao"] == "em_validacao"


def test_validacao_pela_metade_continua_pendente():
    """O dono validou, o Alexandre Scarpa ainda não: a dupla validação não acabou."""
    d = _publicado()
    r = _regua(d, "comida_receita")
    r["dossie"]["validado_por"] = r["dossie"]["validado_por"][:1]
    r["dossie"]["pendente_de"] = ["Alexandre Scarpa"]
    assert rr.validar(d, hoje=HOJE, textos=_textos()) == []
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao" and any("Alexandre Scarpa" in m for m in a["motivos"])


def test_faixa_alterada_depois_da_validacao_e_recusada():
    """A rotina mensal mudou a faixa: a validação humana não vale para a faixa nova."""
    d = _publicado()
    _regua(d, "comida_receita")["faixa"]["max"] = 57
    assert any("faixa mudou depois da validação" in e for e in rr.validar(d, hoje=HOJE, textos=_textos()))
    assert _situacao(d, "comida_receita")["situacao"] == "em_validacao"


def test_quem_validou_nao_pode_continuar_pendente():
    d = _publicado()
    _regua(d, "comida_receita")["dossie"]["pendente_de"] = ["Dono"]
    assert any("continua em pendente_de" in e for e in rr.validar(d, hoje=HOJE, textos=_textos()))


def test_vencimento_do_dossie_no_maximo_12_meses():
    d = _dados()
    _regua(d, "comida_receita")["dossie"]["vence_em"] = "2027-10-20"
    assert any("12 meses" in e for e in rr.validar(d, hoje=HOJE))


# ---------------------------------------------------------------------------
# Termos das fontes (parecer 3.3)
# ---------------------------------------------------------------------------
def test_fonte_sem_termos_verificados_nao_sustenta_faixa():
    d = _publicado()
    f = _fontes(d)["minnesota_fbm_2024"]
    f["termos_verificados_em"] = None
    f["uso_comercial_confirmado_em"] = None
    f["licenca"] = "nao_verificada"
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao"
    assert any("minnesota_fbm_2024" in m for m in a["motivos"])


def test_fonte_sem_uso_comercial_confirmado_nao_sustenta_faixa():
    d = _publicado()
    _fontes(d)["penn_state_iofc"]["uso_comercial_confirmado_em"] = None
    assert _situacao(d, "comida_receita")["situacao"] == "em_validacao"


def test_estados_inconsistentes_de_termos_sao_recusados():
    d = _dados()
    f = _fontes(d)
    f["penn_state_iofc"]["uso_comercial_confirmado_em"] = "2026-10-01"  # sem termos lidos
    f["minnesota_fbm_2024"]["termos_verificados_em"] = "2026-10-01"  # licença ainda "nao_verificada"
    _regua(d, "coe_receita")["dossie"]["termos_verificados_em"] = "2026-10-01"  # fontes da régua sem termos
    erros = rr.validar(d, hoje=HOJE)
    assert any("uso comercial confirmado sem termos" in e for e in erros)
    assert any("continua 'nao_verificada'" in e for e in erros)
    assert any("coe_receita: dossie.termos_verificados_em preenchido" in e for e in erros)


def test_fonte_so_de_corroboracao_nao_serve_de_base():
    d = _dados()
    _deixar_publicavel(d, "coe_receita")  # fonte BR do dossiê: SIA/Feed&Food (corroboração)
    _liberar(d)
    a = _situacao(d, "coe_receita")
    assert a["situacao"] == "em_validacao" and any("corroboração" in m for m in a["motivos"])


# ---------------------------------------------------------------------------
# Interruptores (kill switch)
# ---------------------------------------------------------------------------
def test_interruptor_geral_desligado_nao_publica():
    d = _publicado()
    d["publicacao"]["liberada"] = False
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "em_validacao" and a["publicavel"] is True
    assert any("publicacao.liberada" in m for m in a["motivos"])


def test_interruptor_geral_nao_liga_com_empresa_pendente():
    d = _publicado()
    sem_empresa = _textos(empresa=False)
    assert any("empresa pendente" in e for e in rr.validar(d, hoje=HOJE, textos=sem_empresa))
    assert _situacao(d, "comida_receita", textos=sem_empresa)["situacao"] == "em_validacao"


def test_interruptor_geral_exige_quem_e_quando():
    d = _publicado()
    d["publicacao"]["liberada_por"] = None
    assert any("liberada_por" in e for e in rr.validar(d, hoje=HOJE, textos=_textos()))


def test_interruptor_da_regua():
    d = _publicado()
    _regua(d, "comida_receita")["ativa"] = False
    assert _situacao(d, "comida_receita")["situacao"] == "retirada"


def test_fonte_desligada_some_da_regua():
    d = _publicado()
    _fontes(d)["minnesota_fbm_2024"]["ativa"] = False
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "publicada"
    p = rr.publico(d, hoje=HOJE, textos=_textos())
    comida = next(r for r in p["reguas"] if r["codigo"] == "comida_receita")
    assert "minnesota_fbm_2024" not in {f["id"] for f in comida["fontes"]}


def test_regua_sai_do_ar_quando_perde_o_lado_internacional():
    d = _publicado()
    for fid in ("penn_state_iofc", "minnesota_fbm_2024", "dfmp_wa_2023_24"):
        _fontes(d)[fid]["ativa"] = False
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "retirada" and any("fonte desligada" in m for m in a["motivos"])


def test_regua_sai_do_ar_quando_a_fonte_base_do_dossie_e_desligada():
    d = _publicado()
    _fontes(d)["penn_state_iofc"]["ativa"] = False
    a = _situacao(d, "comida_receita")
    assert a["situacao"] == "retirada" and any("penn_state_iofc" in m for m in a["motivos"])


def test_dossie_vencido_sai_do_ar():
    d = _publicado()
    av = rr.avaliar(d, hoje=date(2027, 10, 9), textos=_textos())
    assert next(a for a in av["reguas"] if a["codigo"] == "comida_receita")["situacao"] == "vencida"


def test_regua_sem_faixa_por_desenho():
    d = _publicado()
    for cod in ("reserva_caixa", "concentrado_receita", "parcelas_receita", "cobertura_divida"):
        assert _situacao(d, cod)["situacao"] == "sem_faixa"


# ---------------------------------------------------------------------------
# Carga pública
# ---------------------------------------------------------------------------
def test_publico_sem_publicacao_nao_leva_numero_nenhum():
    p = rr.publico(hoje=HOJE)
    assert p["publicacao"]["liberada"] is False and p["empresa_pendente"] is True
    for r in p["reguas"]:
        assert r["situacao"] in rr.SITUACOES
        assert r["faixa"] is None and r["ressalva"] is None and r["fontes"] == [] and r["exibir_faixa"] is False
    assert "fontes" not in p and "aviso" not in p


def test_publico_publicado_mostra_so_a_regua_publicada():
    p = rr.publico(_publicado(), hoje=HOJE, textos=_textos())
    por = {r["codigo"]: r for r in p["reguas"]}
    assert por["comida_receita"]["situacao"] == "publicada"
    assert por["comida_receita"]["faixa"]["max"] == 55 and por["comida_receita"]["fontes"]
    assert por["comida_receita"]["fidedignidade"] == "alta" and por["comida_receita"]["vence_em"] == "2027-10-08"
    assert por["coe_receita"]["faixa"] is None and por["coe_receita"]["situacao"] == "em_validacao"


def test_publico_oculta_faixas_enquanto_o_aceite_esta_pendente():
    p = rr.publico(_publicado(), hoje=HOJE, textos=_textos(), ocultar_faixas=True)
    assert p["faixas_ocultas_ate_aceite"] is True
    assert all(r["faixa"] is None and r["ressalva"] is None for r in p["reguas"])


def test_publico_vencida_esconde_todas_as_faixas():
    p = rr.publico(_publicado(), hoje=date(2027, 10, 9), textos=_textos())
    assert p["vencida"] is True
    assert all(r["faixa"] is None and r["exibir_faixa"] is False for r in p["reguas"])


# ---------------------------------------------------------------------------
# Textos (parecer 7)
# ---------------------------------------------------------------------------
def test_alerta_sem_fontes_nem_cepea_e_com_empresa_pendente():
    p = rr.publico(hoje=HOJE)
    alerta = p["textos"]["alerta"]["texto"]
    assert alerta.startswith("ESTIMATIVA DE MERCADO. NÃO É META NEM RECOMENDAÇÃO.")
    assert "Cepea" not in alerta and "Penn State" not in alerta and "{{" not in alerta
    assert "compiladas por CowData" in alerta and "Última revisão: 08/10/2026." in alerta


def test_trecho_do_metodo_so_entra_com_dossie_comprovado():
    trecho = "Mostramos uma faixa quando pelo menos uma fonte brasileira e uma estrangeira"
    sem = rr.publico(hoje=HOJE)["textos"]["modal"]
    com = rr.publico(_publicado(), hoje=HOJE, textos=_textos())["textos"]["modal"]
    assert trecho not in sem["texto"]
    assert trecho in com["texto"]
    assert sem["sha256"] != com["sha256"], "texto diferente pede aceite novo"
    assert "fazendas leiteiras. Mostramos" in com["texto"] and "fazendas leiteiras. Não copiamos" in sem["texto"]


def test_empresa_preenchida_muda_o_texto_e_o_hash():
    sem = tj.descrever("reguas_modal", dados=_textos(empresa=False))
    com = tj.descrever("reguas_modal", dados=_textos())
    assert tj.EMAIL_PENDENTE in sem["texto"] and "reguas@cowdata.example" in com["texto"]
    assert sem["versao"] == com["versao"] and sem["sha256"] != com["sha256"]
    assert tj.empresa_pendente(_textos(empresa=False)) and not tj.empresa_pendente(_textos())


def test_hash_ignora_espaco_invisivel_mas_nao_o_texto():
    assert tj.sha256("Linha 1  \r\nLinha 2\n\n") == tj.sha256("Linha 1\nLinha 2")
    assert tj.sha256("Linha 1\nLinha 2") != tj.sha256("Linha 1\nLinha 3")


def test_mudar_texto_sem_nova_versao_e_recusado():
    t = _textos()
    t["textos"]["reguas_modal"]["modelo"] += " Frase nova."
    assert any("modelo mudou" in e for e in tj.validar(t))


def test_alerta_nao_pode_voltar_a_citar_cepea():
    t = _textos()
    t["textos"]["reguas_alerta"]["modelo"] += " Fontes: Cepea."
    t["textos"]["reguas_alerta"]["sha256_modelo"] = tj.sha256(t["textos"]["reguas_alerta"]["modelo"])
    assert any("Cepea" in e for e in tj.validar(t))


def test_termos_gerais_ficam_pendentes():
    for chave in ("termos_aceite", "termos_clausula_aceite"):
        d = tj.descrever(chave)
        assert d["pendente"] and d["disponivel_para_aceite"] is False
    assert tj.descrever("reguas_modal")["disponivel_para_aceite"] is True


def test_rodape_e_texto_do_botao_sao_os_do_parecer():
    rod = tj.renderizar("reguas_rodape_exportacao", {
        "gerado_em": "09/10/2026 10:00", "usuario": "Maria", "destinatario": "Banco X", "versao_reguas": "2026-10"})
    assert rod.startswith("Este relatório contém faixas de referência de mercado, que são estimativas de terceiros")
    assert "Gerado em 09/10/2026 10:00 por Maria, com autorização para Banco X. Versão das réguas: 2026-10." in rod
    botao = tj.renderizar("compartilhamento_parametro")
    assert botao == ("Permitir exportar relatórios com réguas de referência\n"
                     "(Desligado por padrão. A cada envio, você informa o destinatário e autoriza.)")
