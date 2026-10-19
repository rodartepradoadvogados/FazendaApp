"""Linha do tempo da Temporada 2 · Ep. 9 (Sanidade: aplicação de medicamentos). Mesma lógica de tl_t2e7.py (LEAD + folga ANTES de cada trecho):
   • os tempos do plano ficam 0,1–0,5 s adiantados em relação à voz: as âncoras por palavra são REMAPEADAS por frase (P, início/fim medidos na voz com silencedetect −34 dB);
   • a voz é recortada no meio dos silêncios medidos (CORTE); dezessete trechos, alguns partidos numa pausa real para dar tempo de tocar, rolar e voltar.
   python3 tl_t2e9.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala) — medidos em voz_t2e9 (48,14 s)
F = [("Temporada dois, episódio nove: sanidade, aplicação de medicamentos.", 0.345, 4.598),
 ("Em Lançar, toque em Sanidade.", 5.319, 6.882),
 ("Escolha Curativa, para tratar um animal doente, ou Preventiva, para vacinas e vermífugos.", 7.407, 12.887),
 ("Na Curativa, toque em Aplicação de remédio,", 13.557, 15.871),
 ("e busque o animal.", 16.240, 16.923),
 ("Em Filtrar medicamento por, escolha Doença,", 17.982, 20.443),
 ("e depois Mastite: o app mostra só os remédios indicados.", 20.691, 24.135),
 ("Se o remédio estiver em falta, o app avisa,", 25.196, 27.391),
 ("e sugere um substituto disponível no estoque.", 27.630, 29.782),
 ("Informe a dose, a unidade e a via de aplicação,", 30.343, 32.956),
 ("e toque em Salvar.", 33.196, 34.100),
 ("Na Preventiva,", 35.111, 35.826),
 ("toque em Aplicação, e escolha o evento, por exemplo, a vacina.", 36.157, 39.335),
 ("Aplique em um animal,", 40.084, 41.085),
 ("ou no lote inteiro de uma vez.", 41.318, 42.738),
 ("Pronto, lançado.", 43.793, 44.676),
 ("No próximo episódio: protocolo sanitário.", 45.516, 47.788)]
CORTE = []
for i, (t, a, b) in enumerate(F):
    ca = max(a - 0.15, (F[i - 1][2] + a) / 2) if i else max(0.0, a - 0.15)
    cb = min(b + 0.15, (b + F[i + 1][1]) / 2) if i + 1 < len(F) else min(48.14, b + 0.15)
    CORTE.append((t, round(ca, 3), round(cb, 3)))
# frase do plano (início, fim) → fala real (início, fim): remapeia as âncoras do plano
P = [((0.299, 4.561), (0.345, 4.598)), ((5.261, 12.705), (5.319, 12.887)), ((13.405, 16.859), (13.557, 16.923)), ((17.612, 24.078), (17.982, 24.135)),
 ((25.063, 29.718), (25.196, 29.782)), ((30.140, 33.962), (30.343, 34.100)), ((34.564, 39.215), (35.111, 39.335)), ((39.815, 42.531), (40.084, 42.738)),
 ((43.556, 44.665), (43.793, 44.676)), ((45.365, 47.965), (45.516, 47.788))]
def R(t):
    if t < P[0][0][0]: return t + (P[0][1][0] - P[0][0][0])
    for (pa, pb), (ra, rb) in P:
        if pa <= t <= pb: return ra + (t - pa) / (pb - pa) * (rb - ra)
    k = max(i for i, ((pa, pb), _) in enumerate(P) if pb < t)
    return t + (P[k][1][1] - P[k][0][1])
def tl(corte, gaps, anc, tail):
    out = {"frases": [], "anc": {}}; acc = LEAD; starts = []
    for i, (txt, a, b) in enumerate(corte):
        acc += gaps[i]; starts.append(acc); out["frases"].append([txt, round(F[i][1] + acc, 3), round(F[i][2] + acc, 3)])
    def V(raw):
        k = max(i for i, f in enumerate(corte) if f[1] <= raw + 1e-6) if raw >= corte[0][1] else 0
        return round(raw + starts[k], 3)
    out["anc"] = {k: V(R(v)) for k, v in anc.items()}
    out["voz"] = [[starts[i], a, b] for i, (txt, a, b) in enumerate(corte)]
    out["total"] = round(out["frases"][-1][2] + tail, 2)
    return out
A = dict(temporada=.299, fita1=2.2, emLancar=5.261, sanidade=6.37, curativa=7.619, doente=9.454, preventiva=10.35, vacinas=11.545, naCurativa=13.576, aplicRemedio=14.813,
 busque=16.221, filtrar=17.953, doenca=19.873, mastite=21.068, indicados=23.5, falta=25.959, avisa=26.855, substituto=28.093, estoque=29.458, dose=30.695, unidade=31.25,
 via=32.061, salvar=33.554, naPreventiva=35.119, aplicacao=36.356, evento=38.0, vacina=38.874, umAnimal=40.54, loteInteiro=41.6, pronto=43.556, lancado=44.153,
 proximo=45.365, protocolo=46.7, fimVoz=47.965)
# folga ANTES de cada trecho: 0 título · 1 Em Lançar · 2 Escolha Curativa… · 3 Na Curativa (grade) · 4 e busque (digita) · 5 Em Filtrar (seleciona o animal) · 6 e depois Mastite · 7 Se o remédio estiver em falta (o seletor fica aberto)
# · 8 e sugere um substituto · 9 Informe a dose (o Usar troca o produto) · 10 e toque em Salvar (escolhe o responsável) · 11 Na Preventiva (aviso, sobe, dois Voltar) · 12 toque em Aplicação · 13 Aplique em um animal (rola)
# · 14 ou no lote inteiro · 15 Pronto, lançado (o Salvar do lote e o aviso; o carimbo) · 16 próximo episódio
G = [0.0, 0.3, 0.0, 0.3, 0.1, 0.9, 0.3, 0.2, 0.5, 0.7, 0.6, 1.6, 0.2, 0.2, 0.2, 0.5, 0.4]
TAIL = 2.4
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado."
sobra = (-d["anc"]["lancado"]) % 0.5
G[15] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e9.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
