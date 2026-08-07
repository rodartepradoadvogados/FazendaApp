"""
Catálogo de INDICAÇÕES da farmácia — o "por que estou aplicando isso" que
alimenta o seletor de doença/manejo e o "substituto inteligente"
(ver `rules/farmacia.seed_indicacoes` e `IndicacaoTerapeutica`).

Três blocos:

  INDICACOES — vira `Doenca` (o nome do modelo continua "doença" por razões
      históricas, mas `tipo` generaliza para reprodutivo/produtivo/preventivo/
      suporte — ver docstring de `Doenca`). Cada indicação carrega a lista de
      princípios que a tratam, com `prioridade` (1 = 1ª escolha) e `nota`
      clínica opcional — vira `IndicacaoTerapeutica`.

  MARCAS — enriquecimento das marcas comerciais que `farmacia_seed.PRINCIPIOS`
      já cria (mesmos pares princípio + nome_comercial): dose, via, carência,
      alertas. NÃO cria marca nova — só preenche os campos de bula que
      `farmacia_seed` deixou vazios.

  Honestidade de status — cada marca tem 3 status independentes:
      "referencia"       = valor de bula/literatura, pode ir pro banco.
      "a_preencher"       = NÃO confirmado — grava `None`, a UI mostra
                            "não informada". NUNCA virar 0 nem chute.
      "proibido_lactacao" = não é carência longa, é "NÃO aplicar em fêmea em
                            lactação" — `carencia_leite_dias` fica `None` e
                            `proibido_lactacao=True`.
  `alerta_gestacao=True` liga o banner de risco de aborto no lançamento
  (dexametasona, albendazol, cloprostenol).

  `princípio` casa por NOME EXATO com `farmacia_seed.PRINCIPIOS[*]["nome"]`.
  Se o princípio não existir no catálogo (não deveria acontecer — os 40 nomes
  abaixo foram conferidos contra o documento base), o seed pula o vínculo em
  vez de criar princípio novo: quem cria princípio é `seed_farmacia`.

  Os 6 nomes de `Doenca` já semeados (`ja_semeada=True`) são sagrados — ver
  aviso em `rules/farmacia.seed_indicacoes`. Nunca renomear.

ERROS DE CATÁLOGO (marcas hoje penduradas no princípio ERRADO em
`farmacia_seed.py`) — corrigidos aqui SEM mover a marca de princípio. Mover
reclassificaria retroativamente qualquer `Estoque`/`Sanidade` que já
referencia essa marca por FK, e é uma decisão clínica que cabe ao dono/
veterinário, não a uma migração automática. A correção segura e reversível é:
mantém a marca onde está e enche `alerta` (+ `alerta_gestacao` quando cabe)
para o risco aparecer bem visível na tela. Lista completa — 11 marcas, a mais
grave sinalizada com "CRÍTICO":

  * Ubrolexin (hoje em "Ceftiofur")   — é cefalexina + kanamicina intramamário.
  * Doxifin (hoje em "Sulfadoxina + Trimetoprima") — é doxiciclina.
  * Dexacito (hoje em "Cianocobalamina (B12)") — CRÍTICO: contém
    DEXAMETASONA. Um operador que escolhe "suporte metabólico" pode aplicar
    corticoide numa vaca prenhe sem nenhum aviso de aborto.
  * Cystorelin (hoje em "Buserelina") — é gonadorrelina (outra molécula GnRH).
  * Lactofur / Ready Free (Ceftiofur), Ricobendazol (Albendazol), Gentocin
    Mastite / Mastite Clínica (Gentamicina), Agrovet (Penicilina G), Gorban
    (Sulfadoxina + Trimetoprima), Orastina (Ocitocina) — gravidade média/baixa,
    ver texto do `alerta` de cada marca abaixo.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# PARTE A — INDICAÇÕES (viram `Doenca`, com `tipo`)
#           tipo ∈ doenca | reprodutivo | produtivo | preventivo | suporte
# ─────────────────────────────────────────────────────────────────────────────
INDICACOES: list[dict] = [

    # ── CURATIVAS / CLÍNICAS ────────────────────────────────────────────────
    {
        "nome": "Mastite", "tipo": "doenca",
        "descricao": "Mastite clínica e subclínica em vaca em lactação.",
        "principios": [
            {"principio": "Cefoperazona", "prioridade": 1,
             "nota": "Intramamário de lactação — 1ª escolha para Gram+ (S. aureus, Strep.)."},
            {"principio": "Ceftiofur", "prioridade": 1,
             "nota": "Sistêmico (Excenel RTU, carência leite zero) e intramamário de lactação (Lactofur)."},
            {"principio": "Cetoprofeno", "prioridade": 1,
             "nota": "AINE de apoio — carência leite zero, ideal para vaca em ordenha."},
            {"principio": "Flunixina Meglumina", "prioridade": 2,
             "nota": "Mastite tóxica/coliforme com choque endotóxico."},
            {"principio": "Meloxicam", "prioridade": 2, "nota": "AINE alternativo, analgesia prolongada."},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2,
             "nota": "Mastite severa por Gram+; atenção à carência longa das formas benzatina."},
            {"principio": "Gentamicina", "prioridade": 3,
             "nota": "REVISAR ANTES DE SEMEAR — registro intramamário no Brasil a confirmar, resíduo renal "
                     "prolongado; não deve nascer como 1ª escolha de mastite."},
        ],
    },
    {
        "nome": "Doença Respiratória Bovina (Pneumonia)", "tipo": "doenca",
        "descricao": "DRB / febre do transporte / broncopneumonia de bezerro e recria.",
        "principios": [
            {"principio": "Florfenicol", "prioridade": 1, "nota": "1ª escolha em bezerro/recria. NÃO usar em lactação."},
            {"principio": "Ceftiofur", "prioridade": 1, "nota": "1ª escolha quando a fêmea está em lactação (leite zero)."},
            {"principio": "Oxitetraciclina (LA)", "prioridade": 2, "nota": "Amplo espectro, dose única de longa ação."},
            {"principio": "Sulfadoxina + Trimetoprima", "prioridade": 2, "nota": "Boa opção em bezerro."},
            {"principio": "Enrofloxacina", "prioridade": 3, "nota": "Fluoroquinolona — reserva, quando falharam as anteriores."},
            {"principio": "Flunixina Meglumina", "prioridade": 1, "nota": "Antitérmico/anti-inflamatório de apoio — reduz lesão pulmonar."},
            {"principio": "Meloxicam", "prioridade": 2, "nota": "AINE de apoio."},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 3},
        ],
    },
    {
        "nome": "Diarreia Neonatal", "tipo": "doenca", "ja_semeada": True,
        "descricao": "Diarreia dos bezerros (E. coli, rotavírus, coronavírus, Salmonella).",
        "principios": [
            {"principio": "Pré-parto Neonatal (Rotavírus, Coronavírus, E. coli)", "prioridade": 1,
             "nota": "PREVENÇÃO via colostro — vacinar a vaca no pré-parto."},
            {"principio": "Sulfadoxina + Trimetoprima", "prioridade": 1, "nota": "Tratamento de diarreia bacteriana."},
            {"principio": "Enrofloxacina", "prioridade": 2, "nota": "Quadro septicêmico; uso restrito."},
            {"principio": "Meloxicam", "prioridade": 2, "nota": "Analgesia — melhora ingestão de leite e ganho de peso."},
        ],
    },
    {
        "nome": "Metrite / Endometrite", "tipo": "doenca",
        "descricao": "Infecção uterina pós-parto (metrite puerperal, endometrite clínica).",
        "principios": [
            {"principio": "Ceftiofur", "prioridade": 1, "nota": "1ª escolha sistêmica — carência leite zero (RTU)."},
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 1,
             "nota": "Endometrite com corpo lúteo presente; NÃO usar em metrite puerperal aguda sem CL."},
            {"principio": "Oxitetraciclina (LA)", "prioridade": 2},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2},
            {"principio": "Flunixina Meglumina", "prioridade": 2, "nota": "Metrite tóxica com febre/depressão."},
        ],
    },
    {
        "nome": "Retenção de Placenta", "tipo": "doenca",
        "descricao": "Retenção de membranas fetais (>12–24 h pós-parto).",
        "principios": [
            {"principio": "Ceftiofur", "prioridade": 1,
             "nota": "Antibiótico sistêmico SÓ se houver febre/metrite — RP isolada não é indicação de antibiótico."},
            {"principio": "Ocitocina", "prioridade": 2,
             "nota": "Eficácia só nas primeiras 6–12 h pós-parto; depois disso o miométrio não responde."},
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 3,
             "nota": "EVIDÊNCIA FRACA — a literatura atual não sustenta PGF2α de rotina para RP. Manter como 3ª opção."},
            {"principio": "Borogluconato de Cálcio", "prioridade": 3,
             "nota": "Só quando há hipocalcemia associada (causa comum de atonia uterina)."},
        ],
    },
    {
        "nome": "Doenças Podais / Pododermatite", "tipo": "doenca",
        "descricao": "Dermatite digital, flegmão interdigital, pododermatite necrótica.",
        "principios": [
            {"principio": "Ceftiofur", "prioridade": 1, "nota": "1ª escolha em lactação (leite zero)."},
            {"principio": "Oxitetraciclina (LA)", "prioridade": 1, "nota": "Clássico para flegmão interdigital."},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2},
            {"principio": "Sulfadoxina + Trimetoprima", "prioridade": 2},
            {"principio": "Meloxicam", "prioridade": 1, "nota": "Analgesia — impacto direto em consumo e produção."},
            {"principio": "Cetoprofeno", "prioridade": 2, "nota": "Alternativa com carência leite zero."},
        ],
    },
    {
        "nome": "Babesiose (Tristeza Parasitária)", "tipo": "doenca",
        "descricao": "Babesia bovis / B. bigemina — hemoparasitose transmitida pelo carrapato.",
        "principios": [
            {"principio": "Imidocarb", "prioridade": 1, "nota": "Fármaco de eleição para Babesia."},
            {"principio": "Dipirona Sódica", "prioridade": 2, "nota": "Sintomático — febre alta."},
            {"principio": "Cianocobalamina (B12)", "prioridade": 3, "nota": "Suporte à recuperação da anemia."},
        ],
    },
    {
        "nome": "Anaplasmose (Tristeza Parasitária)", "tipo": "doenca",
        "descricao": "Anaplasma marginale — separada da babesiose de propósito: o fármaco de escolha é OUTRO.",
        "principios": [
            {"principio": "Oxitetraciclina (LA)", "prioridade": 1, "nota": "Fármaco de eleição para Anaplasma."},
            {"principio": "Imidocarb", "prioridade": 2, "nota": "Ativo, mas 2ª escolha para Anaplasma."},
            {"principio": "Dipirona Sódica", "prioridade": 2},
            {"principio": "Cianocobalamina (B12)", "prioridade": 3},
        ],
    },
    {
        "nome": "Verminose (Endoparasitose)", "tipo": "doenca",
        "descricao": "Nematódeos gastrintestinais e pulmonares (Haemonchus, Cooperia, Ostertagia, Dictyocaulus).",
        "principios": [
            {"principio": "Albendazol", "prioridade": 1, "nota": "Oral, amplo espectro. NÃO usar em lactação nem no 1º terço da gestação."},
            {"principio": "Ivermectina", "prioridade": 1, "nota": "Endectocida. NÃO usar em lactação."},
            {"principio": "Doramectina", "prioridade": 2, "nota": "Maior residualidade. NÃO usar em lactação."},
        ],
    },
    {
        "nome": "Fasciolose", "tipo": "doenca",
        "descricao": "Fasciola hepatica — regiões de várzea/brejo. Dose DOBRADA de albendazol.",
        "principios": [
            {"principio": "Albendazol", "prioridade": 1,
             "nota": "DOSE DOBRADA (2 mL/20 kg do 10%) — a dose de verminose NÃO mata Fasciola adulta."},
        ],
    },
    {
        "nome": "Carrapato (Ectoparasitose)", "tipo": "doenca",
        "descricao": "Rhipicephalus (Boophilus) microplus.",
        "principios": [
            {"principio": "Fluazuron", "prioridade": 1, "nota": "Quebra do ciclo (inibidor de quitina). PROIBIDO em lactação."},
            {"principio": "Amitraz", "prioridade": 1, "nota": "Banho de aspersão — tratamento de choque."},
            {"principio": "Fipronil", "prioridade": 2, "nota": "Pour-on. PROIBIDO em lactação."},
            {"principio": "Ivermectina", "prioridade": 3, "nota": "Ação parcial sobre carrapato. PROIBIDO em lactação."},
            {"principio": "Doramectina", "prioridade": 3, "nota": "PROIBIDO em lactação."},
        ],
    },
    {
        "nome": "Mosca-do-chifre e Mosca dos Estábulos", "tipo": "doenca",
        "descricao": "Haematobia irritans / Stomoxys calcitrans — uso principal do Fipronil pour-on.",
        "principios": [
            {"principio": "Fipronil", "prioridade": 1},
            {"principio": "Fluazuron", "prioridade": 2, "nota": "Só as formulações associadas a adulticida."},
            {"principio": "Ivermectina", "prioridade": 3},
        ],
    },
    {
        "nome": "Sarna e Piolho", "tipo": "doenca",
        "descricao": "Sarcoptes/Psoroptes/Chorioptes e malófagos.",
        "principios": [
            {"principio": "Ivermectina", "prioridade": 1},
            {"principio": "Doramectina", "prioridade": 1},
            {"principio": "Amitraz", "prioridade": 2},
            {"principio": "Fipronil", "prioridade": 3},
        ],
    },
    {
        "nome": "Miíase (Bicheira)", "tipo": "doenca",
        "descricao": "Cochliomyia hominivorax — umbigo do bezerro, ferida cirúrgica, marcação.",
        "principios": [
            {"principio": "Doramectina", "prioridade": 1, "nota": "Referência para miíase (curativa e preventiva)."},
            {"principio": "Ivermectina", "prioridade": 2},
        ],
    },
    {
        "nome": "Onfalite (Infecção de Umbigo)", "tipo": "doenca",
        "descricao": "Onfaloflebite/onfaloarterite do bezerro.",
        "principios": [
            {"principio": "Ceftiofur", "prioridade": 1},
            {"principio": "Enrofloxacina", "prioridade": 1, "nota": "Uso principal declarado no próprio seed."},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2},
            {"principio": "Sulfadoxina + Trimetoprima", "prioridade": 2},
            {"principio": "Meloxicam", "prioridade": 2, "nota": "Analgesia."},
            {"principio": "Doramectina", "prioridade": 3, "nota": "Prevenção de miíase no umbigo."},
        ],
    },
    {
        "nome": "Infecções Geniturinárias", "tipo": "doenca",
        "descricao": "Pielonefrite, cistite, vaginite.",
        "principios": [
            {"principio": "Enrofloxacina", "prioridade": 1, "nota": "Uso principal declarado no seed."},
            {"principio": "Ceftiofur", "prioridade": 2},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2,
             "nota": "Clássico para pielonefrite por Corynebacterium renale — tratamento longo."},
        ],
    },
    {
        "nome": "Ceratoconjuntivite Infecciosa Bovina", "tipo": "doenca",
        "descricao": "\"Olho branco\" (Moraxella bovis). Altíssima prevalência.",
        "principios": [
            {"principio": "Oxitetraciclina (LA)", "prioridade": 1, "nota": "Referência (sistêmica e subconjuntival)."},
            {"principio": "Florfenicol", "prioridade": 2, "nota": "NÃO usar em lactação."},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2, "nota": "Via subconjuntival."},
            {"principio": "Ceftiofur", "prioridade": 3},
        ],
    },
    {
        "nome": "Hipocalcemia (Febre do Leite)", "tipo": "doenca",
        "descricao": "Paresia puerperal — hipocalcemia clínica e subclínica pós-parto.",
        "principios": [
            {"principio": "Borogluconato de Cálcio", "prioridade": 1, "nota": "IV lento, com ausculta cardíaca."},
            {"principio": "Toldimfós Sódico", "prioridade": 2, "nota": "Suporte de fósforo — decúbito que não responde só a cálcio."},
        ],
    },
    {
        "nome": "Hipomagnesemia (Tetania das Pastagens)", "tipo": "doenca",
        "descricao": "Quadro convulsivo distinto da hipocalcemia, e o tratamento é outro.",
        "principios": [
            {"principio": "Borogluconato de Cálcio", "prioridade": 1,
             "nota": "SÓ as formulações com magnésio na fórmula. Cálcio puro NÃO trata tetania."},
        ],
    },
    {
        "nome": "Cetose", "tipo": "doenca",
        "descricao": "Cetose clínica e subclínica do início de lactação.",
        "principios": [
            {"principio": "Propilenoglicol", "prioridade": 1, "nota": "Precursor gliconeogênico — 1ª escolha."},
            {"principio": "Dexametasona", "prioridade": 2, "nota": "Corticoide. ALERTA: risco de aborto e de imunossupressão."},
            {"principio": "Cianocobalamina (B12)", "prioridade": 2, "nota": "Cofator da gliconeogênese."},
            {"principio": "Toldimfós Sódico", "prioridade": 3},
        ],
    },
    {
        "nome": "Edema de Úbere", "tipo": "doenca",
        "descricao": "Uso principal declarado do Cetoprofeno no próprio seed.",
        "principios": [
            {"principio": "Cetoprofeno", "prioridade": 1, "nota": "Carência leite zero — feito sob medida para vaca recém-parida."},
            {"principio": "Meloxicam", "prioridade": 2},
            {"principio": "Dexametasona", "prioridade": 3, "nota": "ALERTA: risco de aborto; evitar em pré-parto."},
        ],
    },
    {
        "nome": "Febre / Dor", "tipo": "doenca",
        "descricao": "Sintomático inespecífico — febre, cólica, dor.",
        "principios": [
            {"principio": "Dipirona Sódica", "prioridade": 1},
            {"principio": "Flunixina Meglumina", "prioridade": 1},
            {"principio": "Meloxicam", "prioridade": 2},
            {"principio": "Cetoprofeno", "prioridade": 2, "nota": "Preferencial em vaca em ordenha (leite zero)."},
        ],
    },
    {
        "nome": "Pasteurelose e Paratifo dos Bezerros", "tipo": "doenca", "ja_semeada": True,
        "descricao": "Salmonella dublin/typhimurium e Pasteurella multocida.",
        "principios": [
            {"principio": "Pasteurelose e Paratifo dos Bezerros (Tifo-Pasteurina)", "prioridade": 1,
             "nota": "PREVENÇÃO — vacina no 8º mês de gestação, imunidade passiva via colostro."},
            {"principio": "Florfenicol", "prioridade": 1, "nota": "Tratamento. NÃO usar em lactação."},
            {"principio": "Sulfadoxina + Trimetoprima", "prioridade": 2},
            {"principio": "Enrofloxacina", "prioridade": 2},
            {"principio": "Oxitetraciclina (LA)", "prioridade": 3},
        ],
    },

    # ── PREVENTIVAS (vacinação / profilaxia programada) ─────────────────────
    {
        "nome": "Clostridiose", "tipo": "preventivo", "ja_semeada": True,
        "descricao": "Carbúnculo sintomático, gangrena gasosa, enterotoxemia, botulismo, tétano.",
        "principios": [
            {"principio": "Clostridioses (Toxoides)", "prioridade": 1},
            {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "prioridade": 2,
             "nota": "Tratamento do animal já doente (o toxoide é só profilático)."},
        ],
    },
    {
        "nome": "Brucelose", "tipo": "preventivo", "ja_semeada": True,
        "descricao": "PNCEBT — vacinação obrigatória de bezerras. Sem tratamento; animal positivo é sacrificado.",
        "principios": [
            {"principio": "Brucelose Bovina (Cepa 19 ou RB51)", "prioridade": 1,
             "nota": "B19: fêmeas de 3 a 8 meses, dose única. RB51: adultas, só com autorização do serviço oficial."},
        ],
    },
    {
        "nome": "Tuberculose", "tipo": "preventivo", "ja_semeada": True,
        "descricao": "PNCEBT — diagnóstico por tuberculinização. Sem vacina e sem tratamento.",
        "principios": [
            {"principio": "Tuberculina PPD Bovino", "prioridade": 1,
             "nota": "USO EXCLUSIVO de médico veterinário habilitado/credenciado no serviço oficial."},
        ],
    },
    {
        "nome": "Leptospirose", "tipo": "preventivo", "ja_semeada": True,
        "descricao": "Componente do complexo reprodutivo — vacina polivalente.",
        "principios": [{"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "prioridade": 1}],
    },
    {
        "nome": "IBR (Rinotraqueíte Infecciosa Bovina)", "tipo": "preventivo",
        "descricao": "Mesma vacina polivalente da Leptospirose — indicação separada para o operador achar pelo nome que ele usa.",
        "principios": [{"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "prioridade": 1}],
    },
    {
        "nome": "BVD (Diarreia Viral Bovina)", "tipo": "preventivo",
        "descricao": "Mesma vacina polivalente da Leptospirose.",
        "principios": [{"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "prioridade": 1}],
    },
    {
        "nome": "Secagem", "tipo": "preventivo",
        "descricao": "Terapia de vaca seca — antimicrobiano intramamário de longa ação na última ordenha.",
        "principios": [
            {"principio": "Cefalônio", "prioridade": 1, "nota": "Uma seringa por quarto, após a última ordenha."},
        ],
    },
    {
        "nome": "Analgesia em Procedimentos", "tipo": "preventivo",
        "descricao": "Descorna, castração, marcação. Exigência crescente de bem-estar animal.",
        "principios": [
            {"principio": "Meloxicam", "prioridade": 1, "nota": "Referência para descorna de bezerro."},
            {"principio": "Flunixina Meglumina", "prioridade": 2},
            {"principio": "Cetoprofeno", "prioridade": 2},
        ],
    },

    # ── REPRODUTIVAS ────────────────────────────────────────────────────────
    {
        "nome": "Sincronização de Cio / IATF", "tipo": "reprodutivo",
        "descricao": "Protocolo de sincronização de onda folicular e ovulação para IATF.",
        "principios": [
            {"principio": "Progesterona", "prioridade": 1, "nota": "Dispositivo intravaginal — D0."},
            {"principio": "Benzoato de Estradiol", "prioridade": 1, "nota": "D0 — sincronização da onda folicular."},
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 1, "nota": "D8/D9 — luteólise."},
            {"principio": "Cipionato de Estradiol", "prioridade": 1, "nota": "D8/D9 — indutor de ovulação."},
            {"principio": "Gonadotrofina Coriônica Equina (eCG)", "prioridade": 2, "nota": "D8 — vacas em anestro/escore baixo."},
            {"principio": "Buserelina", "prioridade": 2, "nota": "Alternativa ao cipionato como indutor de ovulação."},
        ],
    },
    {
        "nome": "Cisto Ovariano", "tipo": "reprodutivo",
        "descricao": "Uso principal declarado da Buserelina no seed.",
        "principios": [
            {"principio": "Buserelina", "prioridade": 1, "nota": "GnRH — luteiniza o cisto folicular."},
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 2, "nota": "7 a 9 dias após o GnRH; ou cisto luteínico."},
            {"principio": "Progesterona", "prioridade": 2, "nota": "Dispositivo — protocolo de cisto recorrente."},
        ],
    },
    {
        "nome": "Anestro Pós-parto", "tipo": "reprodutivo",
        "descricao": "Vaca sem ciclicidade após o período voluntário de espera.",
        "principios": [
            {"principio": "Gonadotrofina Coriônica Equina (eCG)", "prioridade": 1, "nota": "Uso principal declarado no seed."},
            {"principio": "Progesterona", "prioridade": 1, "nota": "Priming de progesterona."},
            {"principio": "Benzoato de Estradiol", "prioridade": 2},
            {"principio": "Buserelina", "prioridade": 2},
            {"principio": "Toldimfós Sódico", "prioridade": 3, "nota": "Suporte metabólico do balanço energético negativo."},
        ],
    },
    {
        "nome": "Indução de Parto", "tipo": "reprodutivo",
        "descricao": "Antecipação do parto — uso pontual, sob decisão veterinária.",
        "principios": [
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 1},
            {"principio": "Dexametasona", "prioridade": 1, "nota": "Associada ou isolada, conforme o protocolo."},
        ],
    },

    # ── PRODUTIVAS ──────────────────────────────────────────────────────────
    {
        "nome": "Indução de Lactação", "tipo": "produtivo",
        "descricao": "Protocolo hormonal em novilha/vaca não gestante. Mistura hormônio e medicamento — "
                     "é o caso que justifica indicação e doença dividirem o mesmo seletor.",
        "principios": [
            {"principio": "Benzoato de Estradiol", "prioridade": 1, "nota": "Fase de mamogênese (D1–D7)."},
            {"principio": "Progesterona", "prioridade": 1, "nota": "Fase de mamogênese (D1–D7)."},
            {"principio": "Dexametasona", "prioridade": 1, "nota": "Fase de lactogênese (D18–D20)."},
            {"principio": "Somatotropina Bovina Recombinante (bST)", "prioridade": 2, "nota": "Reforço de produção no protocolo estendido."},
            {"principio": "Cloprostenol Sódico / D-Cloprostenol", "prioridade": 3, "nota": "Alguns protocolos usam no início."},
            {"principio": "Ocitocina", "prioridade": 3, "nota": "Auxílio à descida nas primeiras ordenhas."},
        ],
    },
    {
        "nome": "Persistência de Lactação (bST)", "tipo": "produtivo",
        "descricao": "Aplicação a cada 14 dias para sustentar a curva de lactação.",
        "principios": [{"principio": "Somatotropina Bovina Recombinante (bST)", "prioridade": 1}],
    },
    {
        "nome": "Descida de Leite", "tipo": "produtivo",
        "descricao": "Auxílio à ejeção do leite (novilha de 1º parto, vaca com edema/dor).",
        "principios": [
            {"principio": "Ocitocina", "prioridade": 1,
             "nota": "Uso repetido cria dependência do reflexo — orientar uso pontual."},
        ],
    },

    # ── SUPORTE ─────────────────────────────────────────────────────────────
    {
        "nome": "Suporte Metabólico e Nutricional", "tipo": "suporte",
        "descricao": "Reforço energético, vitamínico e mineral — transição, estresse, pós-doença.",
        "principios": [
            {"principio": "Vitamina A + D3 + E", "prioridade": 1},
            {"principio": "Toldimfós Sódico", "prioridade": 1},
            {"principio": "Cianocobalamina (B12)", "prioridade": 2},
            {"principio": "Borogluconato de Cálcio", "prioridade": 2},
            {"principio": "Propilenoglicol", "prioridade": 3},
        ],
    },
    {
        "nome": "Choque / Reação Alérgica", "tipo": "suporte",
        "descricao": "Choque anafilático, endotóxico, reação vacinal.",
        "principios": [
            {"principio": "Dexametasona", "prioridade": 1, "nota": "ALERTA: risco de aborto em fêmea prenhe."},
            {"principio": "Flunixina Meglumina", "prioridade": 1, "nota": "Choque endotóxico — uso principal declarado no seed."},
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# PARTE B — MARCAS COMERCIAIS enriquecidas (campos novos de MedicamentoComercial)
#
#   dose_padrao        float | None   — quantidade
#   unidade_dose       str   | None   — "ml" | "unidade" | "dose" | "UI" | "mL/L"
#   dose_base          str           — "por_kg_pv" | "por_animal" | "por_teto" | "por_litro_agua"
#   dose_referencia_kg float | None   — quando dose_base="por_kg_pv": kg de PV que 1 unidade atende
#                                       (ex.: 1 mL/50 kg → dose_padrao=1, dose_referencia_kg=50)
#   dose_texto         str           — string humana exibida no card
#   via_padrao         str           — valor de VIAS_APLICACAO (frontend/lib/constants.ts)
#   concentracao       str  | None
#   carencia_leite_dias / carencia_carne_dias  int | None
#   status_*           "referencia" | "a_preencher" | "proibido_lactacao"
#
# O seed (`rules/farmacia.seed_indicacoes`) NUNCA grava valor de dose/carência
# quando o status correspondente é diferente de "referencia" — recalcula a
# partir do status em vez de confiar cegamente no campo bruto abaixo, então um
# eventual `0` ou valor esquecido aqui NUNCA vaza pro banco como confirmado.
# ─────────────────────────────────────────────────────────────────────────────
_R = "referencia"
_A = "a_preencher"
_P = "proibido_lactacao"

MARCAS: list[dict] = [

    # ── Penicilina G ─────────────────────────────────────────────────────────
    {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "nome_comercial": "Pentabiótico Veterinário",
     "uso_principal": "Infecção sistêmica de amplo espectro (associação com estreptomicina).",
     "concentracao": None, "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 10.0,
     "dose_texto": "1 mL/10 kg PV, IM, a cada 24 h", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A,
     "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "Formulações 'reforçado'/benzatina têm carência de carne longa (até 30 dias). Confirmar na bula do lote."},
    {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "nome_comercial": "Agropen",
     "uso_principal": "Infecção sistêmica por Gram+.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "nome_comercial": "Pencivet Plus",
     "uso_principal": "Infecção sistêmica por Gram+.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "nome_comercial": "Penfort",
     "uso_principal": "Infecção sistêmica por Gram+.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    # ERRO DE CATÁLOGO (baixa) — ver docstring do módulo e ERROS_DE_CATALOGO.
    {"principio": "Penicilina G (Procaína, Potássica e Benzatina)", "nome_comercial": "Agrovet",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: composição de 'Agrovet' (Elanco) como penicilina G não confirmada; "
               "conferir com o laboratório antes de tratar dose/carência como referência."},

    # ── Ceftiofur ────────────────────────────────────────────────────────────
    {"principio": "Ceftiofur", "nome_comercial": "Excenel",
     "uso_principal": "Pneumonia, pododermatite, metrite e diarreia — sem descarte de leite.",
     "concentracao": "50 mg/mL (ceftiofur cloridrato)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV (1 mg/kg), IM, 1×/dia por 3 dias", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": 3, "status_carencia_carne": _R},
    # ERRO DE CATÁLOGO (média) — é intramamário, o princípio é sistêmico (ver docstring do módulo).
    {"principio": "Ceftiofur", "nome_comercial": "Lactofur",
     "uso_principal": "Mastite clínica em vaca em lactação (intramamário).", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto afetado, após a ordenha", "via_padrao": "Intramamária", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: Lactofur é apresentação INTRAMAMÁRIA de ceftiofur (lactação), mas o princípio "
               "'Ceftiofur' está classificado como Antimicrobiano Sistêmico Injetável (unidade ml/frasco). "
               "Uso e baixa desta marca são por seringa/teto — não confundir com a apresentação sistêmica (Excenel)."},
    {"principio": "Ceftiofur", "nome_comercial": "Ceftiofur 50",
     "uso_principal": "Antimicrobiano sistêmico.", "concentracao": "50 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "NÃO assumir 'leite zero' — só o ceftiofur cloridrato RTU tem carência zero confirmada."},
    # ERRO DE CATÁLOGO (alta) — Ubrolexin NÃO é ceftiofur (ver docstring do módulo).
    {"principio": "Ceftiofur", "nome_comercial": "Ubrolexin",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto", "via_padrao": "Intramamária", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "ERRO DE CATÁLOGO: Ubrolexin é cefalexina + kanamicina intramamário, NÃO é ceftiofur. As doses e "
               "carências de ceftiofur NÃO se aplicam a este produto. O princípio correto ('Cefalexina + "
               "Kanamicina') ainda não existe no catálogo — cadastro pendente de decisão do dono."},
    {"principio": "Ceftiofur", "nome_comercial": "Ready Free",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": None, "unidade_dose": None, "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": None, "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: confirmar princípio e forma farmacêutica antes de manter sob Ceftiofur."},

    # ── Oxitetraciclina (LA) ─────────────────────────────────────────────────
    {"principio": "Oxitetraciclina (LA)", "nome_comercial": "Terramicina LA",
     "uso_principal": "Anaplasmose, pododermatite, ceratoconjuntivite, pneumonia.",
     "concentracao": "200 mg/mL (oxitetraciclina di-hidratada)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 10.0,
     "dose_texto": "1 mL/10 kg PV (20 mg/kg), IM profunda; repetir em 3–5 dias se necessário",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A,
     "carencia_carne_dias": 28, "status_carencia_carne": _R,
     "alerta": "Carência de LEITE divergente entre fontes (96 h x 120 h) — deixada em branco de propósito. "
               "O produtor confirma na bula do lote antes de liberar o tanque."},
    {"principio": "Oxitetraciclina (LA)", "nome_comercial": "Ourotetracina LA",
     "uso_principal": "Antimicrobiano de longa ação.", "concentracao": "200 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 10.0,
     "dose_texto": "1 mL/10 kg PV, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Oxitetraciclina (LA)", "nome_comercial": "Revemycina",
     "uso_principal": "Antimicrobiano de longa ação.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Oxitetraciclina (LA)", "nome_comercial": "Biociclin LA",
     "uso_principal": "Antimicrobiano de longa ação.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    # ── Florfenicol ──────────────────────────────────────────────────────────
    {"principio": "Florfenicol", "nome_comercial": "Nuflor",
     "uso_principal": "Doença Respiratória Bovina (febre do transporte).", "concentracao": "300 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 15.0,
     "dose_texto": "IM: 1 mL/15 kg PV (20 mg/kg), repetir em 48 h", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P,
     "carencia_carne_dias": 38, "status_carencia_carne": _R,
     "proibido_lactacao": True,
     "alerta": "NÃO aplicar em fêmeas produtoras de leite para consumo humano."},
    {"principio": "Florfenicol", "nome_comercial": "Roflin",
     "uso_principal": "Doença respiratória.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},
    {"principio": "Florfenicol", "nome_comercial": "Maxflor",
     "uso_principal": "Doença respiratória.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},
    {"principio": "Florfenicol", "nome_comercial": "Selectan",
     "uso_principal": "Doença respiratória.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},

    # ── Sulfadoxina + Trimetoprima ───────────────────────────────────────────
    {"principio": "Sulfadoxina + Trimetoprima", "nome_comercial": "Borgal",
     "uso_principal": "Diarreia, pneumonia, infecção de casco.", "concentracao": "Sulfadoxina 200 mg/mL + trimetoprima 40 mg/mL",
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": 2, "status_carencia_leite": _R,
     "carencia_carne_dias": 5, "status_carencia_carne": _R,
     "alerta": "48 h de leite (bula) arredondadas para 2 dias (conservador). A bula também traz restrição de "
               "uso em fêmeas produtoras de leite em algumas apresentações — conferir o lote."},
    {"principio": "Sulfadoxina + Trimetoprima", "nome_comercial": "Trissulfin Injetável",
     "uso_principal": "Antibacteriano de amplo espectro.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    # ERRO DE CATÁLOGO (alta) — Doxifin NÃO é sulfa+trimetoprima (ver docstring do módulo).
    {"principio": "Sulfadoxina + Trimetoprima", "nome_comercial": "Doxifin",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": None, "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "ERRO DE CATÁLOGO: Doxifin é DOXICICLINA, não sulfadoxina + trimetoprima. As doses/carências de "
               "sulfa NÃO se aplicam. O princípio correto ('Doxiciclina') ainda não existe no catálogo — "
               "cadastro pendente de decisão do dono."},
    {"principio": "Sulfadoxina + Trimetoprima", "nome_comercial": "Gorban",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: confirmar composição (sulfa associada) antes de manter aqui."},

    # ── Enrofloxacina ────────────────────────────────────────────────────────
    {"principio": "Enrofloxacina", "nome_comercial": "Flotril",
     "uso_principal": "Infecção geniturinária, onfalite, septicemia.", "concentracao": "100 mg/mL (10%)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 40.0,
     "dose_texto": "1 mL/40 kg PV (2,5 mg/kg), IM ou SC, 1×/dia por 3–5 dias",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": 3, "status_carencia_leite": _R,
     "carencia_carne_dias": 7, "status_carencia_carne": _R,
     "alerta": "Fluoroquinolona de uso crítico — reservar para falha das primeiras escolhas."},
    {"principio": "Enrofloxacina", "nome_comercial": "Enrofloxacina 10%",
     "uso_principal": "Antimicrobiano sistêmico.", "concentracao": "100 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 40.0,
     "dose_texto": "1 mL/40 kg PV, IM ou SC", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Enrofloxacina", "nome_comercial": "Kinetomax",
     "uso_principal": "Antimicrobiano sistêmico de dose única.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Subcutânea", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Enrofloxacina", "nome_comercial": "Chemitril",
     "uso_principal": "Antimicrobiano sistêmico.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    # ── Cefalônio (vaca seca) ────────────────────────────────────────────────
    {"principio": "Cefalônio", "nome_comercial": "Cepravin Vaca Seca",
     "uso_principal": "Terapia de vaca seca — mastite subclínica na secagem.",
     "concentracao": "250 mg de cefalônio anidro por seringa de 3 g",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por quarto, após a última ordenha da lactação",
     "via_padrao": "Intramamária", "status_dose": _R,
     "carencia_leite_dias": 4, "status_carencia_leite": _R,
     "carencia_carne_dias": 21, "status_carencia_carne": _R,
     "alerta": "A carência de leite (4 dias) conta A PARTIR DO PARTO e só vale se houver ao menos 51 dias entre "
               "a aplicação e o parto. Secagem curta = descarte maior."},

    # ── Cefoperazona (lactação) ──────────────────────────────────────────────
    {"principio": "Cefoperazona", "nome_comercial": "Pathozone",
     "uso_principal": "Mastite clínica em vaca em lactação.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto afetado, após cada ordenha", "via_padrao": "Intramamária", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Cefoperazona", "nome_comercial": "Mastitrat",
     "uso_principal": "Mastite clínica em vaca em lactação.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto afetado", "via_padrao": "Intramamária", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    # ── Gentamicina (REVISAR) ────────────────────────────────────────────────
    # ERRO DE CATÁLOGO (alta) — registro intramamário no Brasil a confirmar (ver docstring do módulo).
    {"principio": "Gentamicina", "nome_comercial": "Gentocin Mastite",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto afetado", "via_padrao": "Intramamária", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: aminoglicosídeo com resíduo renal muito prolongado; registro intramamário no "
               "Brasil precisa ser confirmado e é vetado em vários mercados de exportação. Não deve nascer "
               "como 1ª escolha de mastite (ver prioridade 3 na indicação Mastite)."},
    {"principio": "Gentamicina", "nome_comercial": "Mastite Clínica",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_teto", "dose_referencia_kg": None,
     "dose_texto": "1 seringa por teto afetado", "via_padrao": "Intramamária", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: confirmar o princípio ativo real deste produto antes de manter sob Gentamicina."},

    # ── AINEs / analgésicos ──────────────────────────────────────────────────
    {"principio": "Flunixina Meglumina", "nome_comercial": "Banamine",
     "uso_principal": "Dor, febre, inflamação; choque endotóxico.", "concentracao": "50 mg/mL",
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 45.0,
     "dose_texto": "2 mL/45 kg PV (2,2 mg/kg), IM ou IV, 1×/dia", "via_padrao": "Intravenosa", "status_dose": _R,
     "carencia_leite_dias": 2, "status_carencia_leite": _R,
     "carencia_carne_dias": 4, "status_carencia_carne": _R,
     "alerta": "Bula: leite 36 h. Arredondado para 2 dias (conservador, protege o tanque)."},
    {"principio": "Flunixina Meglumina", "nome_comercial": "Flunamine",
     "uso_principal": "AINE injetável.", "concentracao": "50 mg/mL",
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 45.0,
     "dose_texto": "2 mL/45 kg PV, IM ou IV", "via_padrao": "Intravenosa", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Flunixina Meglumina", "nome_comercial": "Desflan",
     "uso_principal": "AINE injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Meloxicam", "nome_comercial": "Maxicam 2%",
     "uso_principal": "Inflamação do aparelho locomotor, mastite, analgesia prolongada.", "concentracao": "20 mg/mL",
     "dose_padrao": 2.5, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 100.0,
     "dose_texto": "2,5 mL/100 kg PV (0,5 mg/kg), IM ou IV, 1×/dia — até 2 aplicações",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": 3, "status_carencia_leite": _R,
     "carencia_carne_dias": 8, "status_carencia_carne": _R},
    {"principio": "Meloxicam", "nome_comercial": "Metacam",
     "uso_principal": "AINE de longa duração.", "concentracao": "20 mg/mL",
     "dose_padrao": 2.5, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 100.0,
     "dose_texto": "2,5 mL/100 kg PV (0,5 mg/kg), SC ou IV, dose única", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Meloxicam", "nome_comercial": "Aliv V",
     "uso_principal": "AINE injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Meloxicam", "nome_comercial": "Meloxifin",
     "uso_principal": "AINE injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Cetoprofeno", "nome_comercial": "Ketofen 10%",
     "uso_principal": "Inflamação, dor e febre — mastite, edema de úbere, distocia, cólica.", "concentracao": "100 mg/mL",
     "dose_padrao": 3.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 100.0,
     "dose_texto": "3 mL/100 kg PV (3 mg/kg), IM ou IV, 1×/dia por até 3 dias",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Cetoprofeno", "nome_comercial": "Ketoflex",
     "uso_principal": "AINE injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Cetoprofeno", "nome_comercial": "Ketofarm",
     "uso_principal": "AINE injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Dexametasona", "nome_comercial": "Azium",
     "uso_principal": "Choque, alergia, cetose, indução de parto.", "concentracao": "2 mg/mL",
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True,
     "alerta": "Corticoide — RISCO DE ABORTO em fêmea prenhe e imunossupressão. Dose varia muito por indicação; "
               "não preenchida de propósito."},
    {"principio": "Dexametasona", "nome_comercial": "Cortiflan",
     "uso_principal": "Corticoide injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True},
    {"principio": "Dexametasona", "nome_comercial": "Dexaflex",
     "uso_principal": "Corticoide injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True},

    {"principio": "Dipirona Sódica", "nome_comercial": "D-500",
     "uso_principal": "Febre e dor.", "concentracao": "500 mg/mL",
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intravenosa", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Dipirona Sódica", "nome_comercial": "Finador",
     "uso_principal": "Analgésico/antitérmico.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intravenosa", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    # ── Reprodutivos / hormônios ─────────────────────────────────────────────
    {"principio": "Cloprostenol Sódico / D-Cloprostenol", "nome_comercial": "Ciosin",
     "uso_principal": "Luteólise: sincronização, endometrite, indução de parto.",
     "concentracao": "0,530 mg de cloprostenol sódico / 2 mL",
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "2 mL por animal, IM, dose única", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": 1, "status_carencia_carne": _R,
     "alerta_gestacao": True,
     "alerta": "ABORTIVO — nunca aplicar em fêmea prenhe que se pretende manter. Mulheres grávidas e asmáticos "
               "não devem manipular."},
    {"principio": "Cloprostenol Sódico / D-Cloprostenol", "nome_comercial": "Estrumate",
     "uso_principal": "Luteólise.", "concentracao": "0,250 mg/mL de cloprostenol",
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "2 mL por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True},
    {"principio": "Cloprostenol Sódico / D-Cloprostenol", "nome_comercial": "Sincrocio",
     "uso_principal": "Luteólise (d-cloprostenol).", "concentracao": "0,075 mg/mL de d-cloprostenol",
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "2 mL por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True},
    {"principio": "Cloprostenol Sódico / D-Cloprostenol", "nome_comercial": "Prolise",
     "uso_principal": "Luteólise (d-cloprostenol).", "concentracao": None,
     "dose_padrao": 2.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "2 mL por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True},

    {"principio": "Benzoato de Estradiol", "nome_comercial": "Sincrodiol",
     "uso_principal": "Sincronização da onda folicular (D0 do IATF).", "concentracao": "2 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 mL (2 mg) por animal, IM, no D0", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Benzoato de Estradiol", "nome_comercial": "Gonadiol",
     "uso_principal": "Sincronização da onda folicular.", "concentracao": "2 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 mL (2 mg) por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Benzoato de Estradiol", "nome_comercial": "Estrogin",
     "uso_principal": "Sincronização da onda folicular.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Cipionato de Estradiol", "nome_comercial": "E.C.P.",
     "uso_principal": "Indutor de ovulação (D8/D9 do IATF).", "concentracao": "2 mg/mL",
     "dose_padrao": 0.5, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "0,5 a 1 mL (1 a 2 mg) por animal, IM, na retirada do dispositivo",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Cipionato de Estradiol", "nome_comercial": "SincroCP",
     "uso_principal": "Indutor de ovulação.", "concentracao": None,
     "dose_padrao": 0.5, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "0,5 a 1 mL por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Progesterona", "nome_comercial": "CIDR",
     "uso_principal": "Dispositivo intravaginal de progesterona (IATF, anestro, cisto).",
     "concentracao": "1,9 g de progesterona",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dispositivo intravaginal, permanência de 8 a 9 dias", "via_padrao": "Intravaginal",
     "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     },
    {"principio": "Progesterona", "nome_comercial": "Sincrogest",
     "uso_principal": "Dispositivo intravaginal de progesterona.", "concentracao": "1,0 g de progesterona",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dispositivo intravaginal, 8 a 9 dias", "via_padrao": "Intravaginal", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Progesterona", "nome_comercial": "DIB",
     "uso_principal": "Dispositivo intravaginal de progesterona.", "concentracao": "1,0 g de progesterona",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dispositivo intravaginal, 8 a 9 dias", "via_padrao": "Intravaginal", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Gonadotrofina Coriônica Equina (eCG)", "nome_comercial": "Novormon",
     "uso_principal": "Estímulo folicular em vaca em anestro / escore baixo.", "concentracao": "5.000 UI por frasco",
     "dose_padrao": 400.0, "unidade_dose": "UI", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "300 a 400 UI por animal, IM, na retirada do dispositivo", "via_padrao": "Intramuscular",
     "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "Unidade de dose 'UI' não existe hoje no seletor de unidades."},
    {"principio": "Gonadotrofina Coriônica Equina (eCG)", "nome_comercial": "SincroeCG",
     "uso_principal": "Estímulo folicular.", "concentracao": None,
     "dose_padrao": 400.0, "unidade_dose": "UI", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "300 a 400 UI por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Gonadotrofina Coriônica Equina (eCG)", "nome_comercial": "Folligon",
     "uso_principal": "Estímulo folicular.", "concentracao": None,
     "dose_padrao": 400.0, "unidade_dose": "UI", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "300 a 400 UI por animal, IM", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Ocitocina", "nome_comercial": "Ocitocina Forte UCB",
     "uso_principal": "Descida de leite; auxílio na involução uterina.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "Concentração varia muito entre apresentações (10 UI/mL x 20 UI/mL) — a dose em mL só faz sentido "
               "depois de o produtor informar a concentração do frasco dele."},
    {"principio": "Ocitocina", "nome_comercial": "Placentina",
     "uso_principal": "Retenção de placenta / involução uterina.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    # ERRO DE CATÁLOGO (baixa) — laboratório desatualizado (ver docstring do módulo).
    {"principio": "Ocitocina", "nome_comercial": "Orastina",
     "uso_principal": "Ocitócico.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "REVISAR CATÁLOGO: laboratório cadastrado como 'Bayer' está desatualizado — a linha veterinária "
               "da Bayer foi incorporada pela Elanco. Não corrigido automaticamente (o seed nunca sobrescreve "
               "o campo laboratório de uma marca já existente); confirmar manualmente."},

    # ERRO DE CATÁLOGO (média) — Cystorelin NÃO é buserelina (ver docstring do módulo).
    {"principio": "Buserelina", "nome_comercial": "Cystorelin",
     "uso_principal": "Cisto ovariano; indução de ovulação.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "ERRO DE CATÁLOGO: Cystorelin é GONADORRELINA (GnRH), não buserelina — mesma classe "
               "farmacológica, molécula diferente; a dose pode NÃO ser intercambiável com as demais marcas de "
               "Buserelina. Confirmar com o veterinário antes de usar a dose de buserelina para este produto."},
    {"principio": "Buserelina", "nome_comercial": "Sincrorelin",
     "uso_principal": "Cisto ovariano; indução de ovulação.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Buserelina", "nome_comercial": "Conceptase",
     "uso_principal": "GnRH.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Somatotropina Bovina Recombinante (bST)", "nome_comercial": "Lactotropin",
     "uso_principal": "Persistência de lactação — aplicação a cada 14 dias.", "concentracao": "500 mg por seringa",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 seringa (500 mg) SC na fossa isquiorretal, a cada 14 dias",
     "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": 0, "status_carencia_carne": _R,
     "alerta": "Carência zero na bula brasileira, MAS o uso de bST é PROIBIDO em vários mercados de exportação "
               "e em programas de leite orgânico/premium. Checar o contrato do laticínio."},
    {"principio": "Somatotropina Bovina Recombinante (bST)", "nome_comercial": "Boostin",
     "uso_principal": "Persistência de lactação.", "concentracao": "500 mg por seringa",
     "dose_padrao": 1.0, "unidade_dose": "unidade", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 seringa (500 mg) SC, a cada 14 dias", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": 0, "status_carencia_carne": _R},

    # ── Antiparasitários ─────────────────────────────────────────────────────
    {"principio": "Ivermectina", "nome_comercial": "Ivomec Injetável",
     "uso_principal": "Nematódeos, sarna, piolho e carrapato.", "concentracao": "10 mg/mL (1%)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV (200 mcg/kg), SC", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P,
     "carencia_carne_dias": 35, "status_carencia_carne": _R,
     "proibido_lactacao": True,
     "alerta": "NÃO usar em vacas em lactação produzindo leite para consumo humano."},
    {"principio": "Ivermectina", "nome_comercial": "Ivermina",
     "uso_principal": "Endectocida.", "concentracao": "10 mg/mL (1%)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV, SC", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},
    {"principio": "Ivermectina", "nome_comercial": "Master LP",
     "uso_principal": "Endectocida de longa ação.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Subcutânea", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True,
     "alerta": "Formulação de longa ação — carência de CARNE bem maior que a da ivermectina 1% (pode passar de "
               "70 dias). NUNCA copiar os 35 dias do Ivomec."},

    {"principio": "Doramectina", "nome_comercial": "Dectomax",
     "uso_principal": "Nematódeos, miíase (bicheira), sarna, carrapato.", "concentracao": "10 mg/mL (1%)",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV (200 mcg/kg), IM ou SC", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P,
     "carencia_carne_dias": 35, "status_carencia_carne": _R,
     "proibido_lactacao": True},
    {"principio": "Doramectina", "nome_comercial": "Doramec",
     "uso_principal": "Endectocida.", "concentracao": "10 mg/mL",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 50.0,
     "dose_texto": "1 mL/50 kg PV, IM ou SC", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},

    {"principio": "Fluazuron", "nome_comercial": "Acatak",
     "uso_principal": "Quebra do ciclo do carrapato (inibidor de quitina).", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 20.0,
     "dose_texto": "1 mL/20 kg PV, pour-on ao longo da linha dorsal", "via_padrao": "Tópica", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True,
     "alerta": "PROIBIDO em vaca em lactação. Carência de CARNE muito longa (lipofílico, acumula na gordura) — "
               "não estimar, ler a bula do lote."},
    {"principio": "Fluazuron", "nome_comercial": "Tickless",
     "uso_principal": "Controle de carrapato.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Tópica", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},
    {"principio": "Fluazuron", "nome_comercial": "Ouroatac",
     "uso_principal": "Controle de carrapato.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Tópica", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},

    {"principio": "Fipronil", "nome_comercial": "Topline",
     "uso_principal": "Mosca-do-chifre e carrapato.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 10.0,
     "dose_texto": "1 mL/10 kg PV, pour-on na linha dorsal", "via_padrao": "Tópica", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},
    {"principio": "Fipronil", "nome_comercial": "Fiprotack",
     "uso_principal": "Mosca-do-chifre e carrapato.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Tópica", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},

    {"principio": "Amitraz", "nome_comercial": "Triatox",
     "uso_principal": "Banho de aspersão contra carrapato e sarna.", "concentracao": "125 g/L (12,5%)",
     "dose_padrao": 2.0, "unidade_dose": "mL/L", "dose_base": "por_litro_agua", "dose_referencia_kg": None,
     "dose_texto": "2 mL por litro de água, aspersão até molhar todo o animal", "via_padrao": "Tópica",
     "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "Diluição varia por objetivo (carrapato x sarna) e por concentração do produto — conferir a bula. "
               "Não pulverizar contra o vento; tóxico para equinos."},
    {"principio": "Amitraz", "nome_comercial": "Amitraz 12,5%",
     "uso_principal": "Carrapaticida de aspersão.", "concentracao": "125 g/L",
     "dose_padrao": 2.0, "unidade_dose": "mL/L", "dose_base": "por_litro_agua", "dose_referencia_kg": None,
     "dose_texto": "2 mL por litro de água, aspersão", "via_padrao": "Tópica", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Imidocarb", "nome_comercial": "Imizol",
     "uso_principal": "Babesiose e anaplasmose.", "concentracao": "120 mg/mL (12%)",
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": "2 mg de imidocarb/kg PV, SC", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P,
     "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True,
     "alerta": "Carência de CARNE divergente entre fontes (28 x 241 dias) — deixada em branco de propósito. "
               "É um dos resíduos mais fiscalizados; confirmar na bula. Não vacinar contra "
               "babesiose/anaplasmose nos 28 dias seguintes."},
    {"principio": "Imidocarb", "nome_comercial": "Izoot",
     "uso_principal": "Hemoparasiticida.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Subcutânea", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True},

    {"principio": "Albendazol", "nome_comercial": "Valbazen",
     "uso_principal": "Nematódeos gastrintestinais e pulmonares, cestódeos e Fasciola adulta.",
     "concentracao": "100 mg/mL (10%) + sulfato de cobalto",
     "dose_padrao": 1.0, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": 20.0,
     "dose_texto": "Verminose: 1 mL/20 kg PV, VO. Fasciolose: 2 mL/20 kg PV. Larvas inibidas de Ostertagia: "
                   "1,5 mL/20 kg PV",
     "via_padrao": "Oral", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _P,
     "carencia_carne_dias": 14, "status_carencia_carne": _R,
     "proibido_lactacao": True, "alerta_gestacao": True,
     "alerta": "TERATOGÊNICO — não usar no primeiro terço da gestação. Não usar em fêmeas produzindo leite "
               "para consumo humano."},
    # ERRO DE CATÁLOGO (média) — é injetável, o princípio está como "oral" em litros (ver docstring do módulo).
    {"principio": "Albendazol", "nome_comercial": "Ricobendazol",
     "uso_principal": "Anti-helmíntico injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Subcutânea", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True, "alerta_gestacao": True,
     "alerta": "REVISAR CATÁLOGO: Ricobendazol é o metabólito sulfóxido do albendazol e é INJETÁVEL — o "
               "princípio está cadastrado como 'Endoparasiticida Oral' com unidade-base em litros. Mesma "
               "molécula-mãe, mas confira a via antes de lançar."},
    {"principio": "Albendazol", "nome_comercial": "Biozen",
     "uso_principal": "Anti-helmíntico oral.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_kg_pv", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Oral", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _P, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "proibido_lactacao": True, "alerta_gestacao": True},

    # ── Metabólicos / vitaminas ──────────────────────────────────────────────
    {"principio": "Borogluconato de Cálcio", "nome_comercial": "Calfon",
     "uso_principal": "Hipocalcemia pós-parto (febre do leite).", "concentracao": None,
     "dose_padrao": 500.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "500 mL por vaca adulta, IV LENTA (10 a 20 min) com ausculta cardíaca",
     "via_padrao": "Intravenosa", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "IV rápida causa PARADA CARDÍACA. Exibir este alerta no card e no lançamento."},
    {"principio": "Borogluconato de Cálcio", "nome_comercial": "Cálcio Farmative",
     "uso_principal": "Hipocalcemia.", "concentracao": None,
     "dose_padrao": 500.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "500 mL por vaca adulta, IV lenta", "via_padrao": "Intravenosa", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Borogluconato de Cálcio", "nome_comercial": "Fortemil",
     "uso_principal": "Cálcio associado a fósforo e magnésio.", "concentracao": None,
     "dose_padrao": 500.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "500 mL por vaca adulta, IV lenta", "via_padrao": "Intravenosa", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "É a apresentação com MAGNÉSIO — a indicada para tetania das pastagens."},

    {"principio": "Toldimfós Sódico", "nome_comercial": "Catosal B12",
     "uso_principal": "Estimulante metabólico, fonte de fósforo orgânico + B12.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Toldimfós Sódico", "nome_comercial": "Fosfosan",
     "uso_principal": "Fonte de fósforo, estimulante metabólico.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Toldimfós Sódico", "nome_comercial": "Ourofós",
     "uso_principal": "Fonte de fósforo.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Vitamina A + D3 + E", "nome_comercial": "ADE",
     "uso_principal": "Suporte vitamínico e imunológico (pré-parto, transição).", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Vitamina A + D3 + E", "nome_comercial": "Monovin A",
     "uso_principal": "Vitamina A injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Vitamina A + D3 + E", "nome_comercial": "Adeforte",
     "uso_principal": "Suporte vitamínico.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Cianocobalamina (B12)", "nome_comercial": "Rubra 12",
     "uso_principal": "Estímulo energético e hematopoiético.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Cianocobalamina (B12)", "nome_comercial": "B12",
     "uso_principal": "Vitamina B12 injetável.", "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    # ERRO DE CATÁLOGO (CRÍTICA) — Dexacito contém DEXAMETASONA (ver docstring do módulo).
    # Decisão: NÃO mover para "Dexametasona" nem duplicar — mesmo o princípio
    # "Dexametasona" já existindo no catálogo, mover reclassificaria qualquer
    # Estoque/Sanidade que já referencia esta marca por FK sob "B12", e
    # duplicar quebraria a contagem de marcas do bootstrap (114) sem uma
    # decisão humana de qual das duas cópias é a "oficial". A correção segura
    # e reversível por um seed add-missing é o alerta clínico bem visível.
    {"principio": "Cianocobalamina (B12)", "nome_comercial": "Dexacito",
     "uso_principal": None, "concentracao": None,
     "dose_padrao": None, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": None, "via_padrao": "Intramuscular", "status_dose": _A,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta_gestacao": True,
     "alerta": "ERRO DE CATÁLOGO CRÍTICO: Dexacito é DEXAMETASONA + cianocobalamina, listado só sob 'B12'. Um "
               "operador que escolhe 'suporte metabólico' pode aplicar CORTICOIDE numa vaca prenhe sem nenhum "
               "aviso de aborto. NÃO usar em fêmea prenhe. Cadastro correto (mover para 'Dexametasona' ou "
               "duplicar sob os dois princípios) pendente de decisão do dono — não feito automaticamente."},

    {"principio": "Propilenoglicol", "nome_comercial": "Cetol",
     "uso_principal": "Cetose — precursor gliconeogênico.", "concentracao": None,
     "dose_padrao": 300.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "250 a 300 mL por vaca, VO (drench), 1×/dia por 3 a 5 dias", "via_padrao": "Oral",
     "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Propilenoglicol", "nome_comercial": "Energet",
     "uso_principal": "Suplemento energético oral.", "concentracao": None,
     "dose_padrao": 300.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "250 a 300 mL por vaca, VO", "via_padrao": "Oral", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Propilenoglicol", "nome_comercial": "Propilenoglicol",
     "uso_principal": "Suplemento energético oral (genérico).", "concentracao": None,
     "dose_padrao": 300.0, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "250 a 300 mL por vaca, VO", "via_padrao": "Oral", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    # ── Biológicos ───────────────────────────────────────────────────────────
    {"principio": "Brucelose Bovina (Cepa 19 ou RB51)", "nome_comercial": "Cepa 19",
     "uso_principal": "Vacinação obrigatória de bezerras (PNCEBT).", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose SC — fêmeas de 3 a 8 meses de idade, aplicação única na vida",
     "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A,
     "alerta": "Aplicação e registro EXCLUSIVOS de médico veterinário cadastrado no serviço veterinário oficial. "
               "Zoonose — risco de autoinoculação."},
    {"principio": "Brucelose Bovina (Cepa 19 ou RB51)", "nome_comercial": "RB51",
     "uso_principal": "Vacinação de fêmeas adultas (uso controlado).", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose SC — só com autorização do serviço veterinário oficial",
     "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Clostridioses (Toxoides)", "nome_comercial": "Covexin 9",
     "uso_principal": "Profilaxia de 9 clostridioses.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose SC; primovacinação com reforço em 21 a 30 dias, depois anual",
     "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Clostridioses (Toxoides)", "nome_comercial": "Poli-Star",
     "uso_principal": "Profilaxia de clostridioses.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose SC; reforço em 21 a 30 dias, depois anual", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Clostridioses (Toxoides)", "nome_comercial": "Fortress",
     "uso_principal": "Profilaxia de clostridioses.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose SC; reforço em 21 a 30 dias", "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "nome_comercial": "CattleMaster",
     "uso_principal": "Profilaxia do complexo reprodutivo (IBR, BVD, lepto).", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM ou SC; primovacinação com reforço em 21 a 30 dias, depois semestral/anual",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "nome_comercial": "Supina",
     "uso_principal": "Profilaxia do complexo reprodutivo.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM; reforço em 21 a 30 dias", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Reprodutiva (IBR, BVD, Leptospirose)", "nome_comercial": "Bioabortogen",
     "uso_principal": "Profilaxia de leptospirose/abortos.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM; reforço em 21 a 30 dias", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Pré-parto Neonatal (Rotavírus, Coronavírus, E. coli)", "nome_comercial": "ScourGuard 4KC",
     "uso_principal": "Vacinação pré-parto — imunidade passiva contra diarreia neonatal.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM na vaca seca; 2ª dose 3 a 6 semanas antes do parto",
     "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Pré-parto Neonatal (Rotavírus, Coronavírus, E. coli)", "nome_comercial": "Rotatec",
     "uso_principal": "Vacinação pré-parto.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM na vaca seca, antes do parto", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},
    {"principio": "Pré-parto Neonatal (Rotavírus, Coronavírus, E. coli)", "nome_comercial": "Lactovac",
     "uso_principal": "Vacinação pré-parto.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose IM na vaca seca, antes do parto", "via_padrao": "Intramuscular", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Pasteurelose e Paratifo dos Bezerros (Tifo-Pasteurina)", "nome_comercial": "Tifopasteurina",
     "uso_principal": "Imunidade passiva do bezerro via colostro.", "concentracao": None,
     "dose_padrao": 1.0, "unidade_dose": "dose", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "1 dose na vaca por volta do 8º mês de gestação (≈30 dias antes do parto)",
     "via_padrao": "Subcutânea", "status_dose": _R,
     "carencia_leite_dias": None, "status_carencia_leite": _A, "carencia_carne_dias": None, "status_carencia_carne": _A},

    {"principio": "Tuberculina PPD Bovino", "nome_comercial": "PPD Bovino",
     "uso_principal": "Teste intradérmico de tuberculose (PNCEBT).", "concentracao": None,
     "dose_padrao": 0.1, "unidade_dose": "ml", "dose_base": "por_animal", "dose_referencia_kg": None,
     "dose_texto": "0,1 mL por via intradérmica (prega caudal ou cervical); leitura em 72 h",
     "via_padrao": "Intradérmica", "status_dose": _R,
     "carencia_leite_dias": 0, "status_carencia_leite": _R,
     "carencia_carne_dias": 0, "status_carencia_carne": _R,
     "alerta": "USO EXCLUSIVO de médico veterinário habilitado pelo serviço oficial. "
               "— mapeada para 'Subdérmica' porque VIAS_APLICACAO não tem a opção."},
]
