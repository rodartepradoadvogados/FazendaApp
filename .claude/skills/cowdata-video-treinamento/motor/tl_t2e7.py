"""Linha do tempo da Temporada 2 · Ep. 7 (Produção: pesagem corporal e secagem). Mesma lógica de tl_t2e6.py (LEAD + folga ANTES de cada trecho).
   Diferenças em relação ao Ep. 6:
   • os tempos do plano ficam ~0,1–0,3 s adiantados em relação à voz (em F8 chegam a 0,5 s): as âncoras por palavra são REMAPEADAS por frase
     (início/fim medidos na voz, envelope a −50 dB) — `R()`; os recortes da voz usam os silêncios medidos, nunca o tempo do plano (que cortaria o fim de "novilhas");
   • cinco frases são partidas numa pausa real da voz (F4, F5, F7, F9 e F10) para dar tempo de digitar, rolar a tabela e preencher.
   python3 tl_t2e7.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala) — medidos em voz_t2e7 (56,56 s)
F = [("Temporada dois, episódio sete: pesagem corporal e secagem.", 0.36, 4.24),
 ("Em Lançar, toque em Produção, Leite, e depois em Pesagem corporal.", 5.05, 9.11),
 ("Em Modalidade, escolha Por animal, Por lote, ou Planilha. Aqui, Por lote: marque o lote das novilhas.", 10.13, 16.75),
 ("Digite o peso novo de cada animal.", 17.31, 18.94),
 ("O app mostra na hora o ganho, e o GMD, o ganho médio por dia.", 19.46, 22.85),
 ("Quem perdeu peso ganha um aviso.", 23.53, 24.96),
 ("Confira, e toque em Salvar.", 25.19, 26.54),
 ("Agora, a secagem. Volte em Produção, e toque em Secagem.", 27.49, 31.63),
 ("No passo um, Até trinta dias mostra as vacas com secagem prevista.", 32.21, 36.01),
 ("Marque as que vão secar.", 36.49, 37.57),
 ("No passo dois, confira a data, e escolha o motivo, que é obrigatório.", 38.61, 42.25),
 ("Se aplicou antibiótico ou selante, acrescente o produto:", 42.66, 45.60),
 ("o app mostra como fica o estoque.", 45.84, 47.62),
 ("Toque em Salvar.", 48.65, 49.48),
 ("O app sugere mover as vacas para o lote das secas.", 49.67, 52.38),
 ("Pronto, lançado.", 52.74, 53.74),
 ("No próximo episódio: BST.", 54.39, 56.29)]
# pontos de recorte da voz: meio do silêncio entre as falas (ou 0,15 s antes/depois da fala, o que for menor)
CORTE = []
for i, (t, a, b) in enumerate(F):
    ca = max(a - 0.15, (F[i - 1][2] + a) / 2) if i else max(0.0, a - 0.15)
    cb = min(b + 0.15, (b + F[i + 1][1]) / 2) if i + 1 < len(F) else min(56.55, b + 0.15)
    CORTE.append((t, round(ca, 3), round(cb, 3)))
# frase do plano (início, fim) → fala real (início, fim): remapeia as âncoras do plano
P = [((0.299, 4.258), (0.36, 4.24)), ((4.958, 9.178), (5.05, 9.11)), ((9.902, 16.473), (10.13, 16.75)), ((17.073, 22.718), (17.31, 22.85)),
 ((23.318, 26.399), (23.53, 26.54)), ((27.199, 31.330), (27.49, 31.63)), ((32.030, 37.395), (32.21, 37.57)), ((38.067, 42.158), (38.61, 42.25)),
 ((42.758, 47.437), (42.66, 47.62)), ((48.462, 52.093), (48.65, 52.38)), ((52.515, 53.582), (52.74, 53.74)), ((54.282, 56.328), (54.39, 56.29))]
def R(t):
    if t < P[0][0][0]: return t + (P[0][1][0] - P[0][0][0])
    for (pa, pb), (ra, rb) in P:
        if pa <= t <= pb: return ra + (t - pa) / (pb - pa) * (rb - ra)
    k = max(i for i, ((pa, pb), _) in enumerate(P) if pb < t)
    return t + (P[k][1][1] - P[k][0][1])
def tl(corte, gaps, anc, tail):
    out = {"frases": [], "anc": {}}; acc = LEAD; starts = []
    for i, (txt, a, b) in enumerate(corte):
        acc += gaps[i]; starts.append(acc); out["frases"].append([txt, round(a + acc, 3), round(b + acc, 3)])
    def V(raw):
        k = max(i for i, f in enumerate(corte) if f[1] <= raw + 1e-6) if raw >= corte[0][1] else 0
        return round(raw + starts[k], 3)
    out["anc"] = {k: V(R(v)) for k, v in anc.items()}
    out["voz"] = [[starts[i], a, b] for i, (txt, a, b) in enumerate(corte)]
    out["total"] = round(out["frases"][-1][2] + tail, 2)
    return out
A = dict(temporada=.299, fita1=2.2, emLancar=4.958, toqueProd=5.854, producao=6.281, leite=6.964, pesagem=8.286, modalidade=10.03, porAnimal=11.438, porLote=12.291,
 planilha=13.145, aqui=13.827, porLote2=14.382, marque=15.235, novilhas=16.046, digite=17.073, pesoNovo=17.585, mostra=19.612, ganho=20.423, gmd=20.977,
 ganhoMedio=21.788, perdeu=23.489, aviso=24.47, confira=24.982, salvar=26.049, agora=27.199, secagem=28.137, volte=29.149, toqueSec=30.344, secagemBtn=30.771,
 passoUm=32.03, ate30=32.798, prevista=35.443, marque2=36.297, secar=37.065, passoDois=38.067, data=39.731, motivo=40.84, obrigatorio=41.48, antibiotico=43.27,
 selante=43.995, acrescente=44.593, estoque=47.067, toqueSalvar2=48.462, salvar2=48.846, sugere=49.87, loteSecas=51.321, pronto=52.515, lancado=53.028,
 proximo=54.282, bst=55.434, fimVoz=56.328)
# folga ANTES de cada trecho, na ordem de F: 0 F1 · 1 F2 (o título chega) · 2 F3 (a tela abre) · 3 F4a (a tabela aparece, a moldura rola até "Peso novo") · 4 F4b (acaba de digitar as 4)
# · 5 F5a · 6 F5b (rola até a barra) · 7 F6 (o retorno do salvar fica na tela) · 8 F7a (a tela da Secagem abre) · 9 F7b (a tabela volta e as vacas são marcadas)
# · 10 F8 (rola até o passo 2) · 11 F9a (rola até o passo 3) · 12 F9b (2º produto) · 13 F10a (rola até a barra) · 14 F10b (o salvar leva ~1 s) · 15 F11 (o mini-quadro)
# · 16 F12 (o carimbo fica na tela antes da capa)
G = [0.0, 0.4, 0.3, 0.4, 0.8, 0.2, 0.3, 0.4, 0.2, 0.6, 0.2, 0.3, 0.9, 0.2, 0.2, 0.8, 1.1]
TAIL = 2.6
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado." (F11)
sobra = (-d["anc"]["lancado"]) % 0.5
G[15] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e7.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
