"""Linha do tempo da Temporada 2 · Ep. 11 (Alimentação: consumo e sobra de cocho). Mesma lógica de tl_t2e10.py (LEAD + folga ANTES de cada trecho):
   • a voz (voz_t2e11, 44,67 s) é recortada no meio dos silêncios medidos (silencedetect −34 dB, 0,15 s); 21 trechos, alguns separados por folgas para dar tempo de tocar, digitar e rolar;
   • as âncoras por palavra (A) estão em tempo BRUTO da voz, medidas na fala real (silencedetect −28 dB, 0,04 s); os tempos do plano ficam 0,1–0,6 s adiantados.
   python3 tl_t2e11.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala)
F = [("Temporada dois, episódio onze: alimentação.", 0.342, 3.052),
 ("Em Lançar, toque em Alimentação,", 3.837, 5.601),
 ("em Outros lançamentos frequentes.", 5.779, 7.272),
 ("Escolha o lote.", 8.010, 8.734),
 ("Aparecem só os alimentos da dieta ativa,", 9.266, 11.397),
 ("e o que já foi lançado hoje.", 11.730, 12.921),
 ("Em Como informar a quantidade,", 13.935, 15.790),
 ("escolha Número de animais:", 16.056, 17.731),
 ("digite quantos comeram,", 17.911, 18.982),
 ("e o app calcula os quilos de cada alimento.", 19.313, 21.292),
 ("Se preferir,", 22.467, 23.185),
 ("toque em Kg direto,", 23.413, 24.790),
 ("e digite o peso de cada um.", 25.061, 26.373),
 ("Toque em Lançar consumo.", 26.884, 28.133),
 ("No fim do dia,", 29.224, 29.906),
 ("pese o que sobrou no cocho,", 30.204, 31.358),
 ("e lance o total em Sobra.", 31.657, 32.884),
 ("Relançar no mesmo dia substitui, não soma.", 33.550, 35.803),
 ("O app mostra a porcentagem de sobra, e se está dentro da faixa.", 36.827, 40.112),
 ("Pronto, lançado.", 40.818, 41.684),
 ("No próximo episódio: protocolos.", 42.543, 44.435)]
END = 44.67
CORTE = []
for i, (t, a, b) in enumerate(F):
    ca = max(a - 0.15, (F[i - 1][2] + a) / 2) if i else max(0.0, a - 0.15)
    cb = min(b + 0.15, (b + F[i + 1][1]) / 2) if i + 1 < len(F) else min(END, b + 0.15)
    CORTE.append((t, round(ca, 3), round(cb, 3)))
def tl(corte, gaps, anc, tail):
    out = {"frases": [], "anc": {}}; acc = LEAD; starts = []
    for i, (txt, a, b) in enumerate(corte):
        acc += gaps[i]; starts.append(acc); out["frases"].append([txt, round(F[i][1] + acc, 3), round(F[i][2] + acc, 3)])
    def V(raw):
        k = max(i for i, f in enumerate(corte) if f[1] <= raw + 1e-6) if raw >= corte[0][1] else 0
        return round(raw + starts[k], 3)
    out["anc"] = {k: V(v) for k, v in anc.items()}
    out["voz"] = [[starts[i], a, b] for i, (txt, a, b) in enumerate(corte)]
    out["total"] = round(out["frases"][-1][2] + tail, 2)
    return out
# âncoras (tempo bruto da voz)
A = dict(temporada=.45, fita1=2.1, emLancar=3.95, alimentacao=4.85, outros=5.85, frequentes=6.95,
 lote=8.4, alimentos=9.9, dieta=10.6, jaLancado=12.1, comoInformar=14.5, numAnimais=16.85, digite=18.0, calcula=19.75, quilos=20.05, cadaAlimento=20.5,
 kgDireto=23.95, peso=25.55, cadaUm=25.95, lancarConsumo=27.15, fimDia=29.3, sobrou=30.6, cocho=31.05, sobra=32.4, relancar=33.6, substitui=34.8, naoSoma=35.4,
 porcentagem=37.2, sobraPct=38.2, dentro=39.2, faixa=39.7, pronto=40.83, lancado=41.28, proximo=42.6, protocolos=43.76, fimVoz=44.43)
# folga ANTES de cada trecho: 0 título · 1 Em Lançar · 2 em Outros lançamentos (toca em Alimentação ao fim) · 3 Escolha o lote · 4 Aparecem só… (rola) · 5 já lançado hoje · 6 Em Como informar
# · 7 escolha Nº de animais · 8 digite · 9 e o app calcula · 10 Se preferir · 11 toque em Kg direto · 12 digite o peso · 13 Toque em Lançar consumo · 14 No fim do dia · 15 pese o que sobrou
# · 16 e lance o total em Sobra · 17 Relançar substitui · 18 O app mostra a porcentagem · 19 Pronto, lançado · 20 próximo episódio
G = [0.0, 0.3, 0.0, 0.4, 0.3, 0.0, 0.7, 0.0, 0.0, 0.2, 0.8, 0.0, 0.5, 0.9, 0.7, 0.15, 0.1, 0.5, 1.2, 0.4, 0.6]
TAIL = 2.3
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado."
sobra = (-d["anc"]["lancado"]) % 0.5
G[19] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e11.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
