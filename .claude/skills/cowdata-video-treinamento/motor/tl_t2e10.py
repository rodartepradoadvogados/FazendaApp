"""Linha do tempo da Temporada 2 · Ep. 10 (Sanidade: protocolo sanitário). Mesma lógica de tl_t2e9.py (LEAD + folga ANTES de cada trecho):
   • a voz (voz_t2e10, 42,81 s) é recortada no meio dos silêncios medidos (silencedetect −34 dB, 0,15 s); vinte trechos, alguns separados por folgas para dar tempo de tocar, digitar e rolar;
   • as âncoras por palavra (A) estão em tempo BRUTO da voz, medidas na fala real (os tempos do plano ficam 0,1–0,6 s adiantados).
   python3 tl_t2e10.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala)
F = [("Temporada dois, episódio dez: protocolo sanitário.", 0.364, 3.558),
 ("Em Lançar, toque em Sanidade,", 4.440, 6.345),
 ("depois em Curativa,", 6.639, 7.658),
 ("e em Protocolo sanitário.", 7.912, 9.138),
 ("A mesma tela abre em Protocolos.", 9.500, 11.393),
 ("Escolha o animal,", 12.617, 13.491),
 ("ou o lote inteiro,", 13.692, 14.623),
 ("e confira a data de início.", 14.903, 16.236),
 ("Em Protocolo sanitário,", 17.361, 18.444),
 ("escolha o tratamento cadastrado pelo veterinário:", 18.764, 20.947),
 ("ele já traz os remédios, as doses e os dias.", 21.191, 23.923),
 ("Protocolo de mastite é lançado um animal por vez,", 24.957, 27.807),
 ("e pede a classificação da mastite.", 28.100, 29.718),
 ("Se precisar,", 30.126, 30.828),
 ("escreva uma observação,", 31.086, 32.333),
 ("e toque em Salvar.", 32.485, 33.567),
 ("Pronto, lançado.", 34.574, 35.585),
 ("O app cria o tratamento com todas as etapas,", 35.901, 38.310),
 ("para acompanhar dia a dia.", 38.595, 39.893),
 ("No próximo episódio: alimentação.", 40.651, 42.520)]
END = 42.81
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
A = dict(temporada=.40, fita1=2.2, emLancar=4.45, sanidade=5.75, curativa=7.1, protSanit=8.25, mesmaTela=9.7, protocolos=10.85, animal=13.0, lote=13.95, data=15.5,
 protocolo=17.65, tratamento=19.2, veterinario=20.3, remedios=21.75, doses=22.6, dias=23.35, mastite=25.5, umPorVez=26.7, classificacao=28.55, observacao=31.65, salvar=33.0,
 pronto=34.6, lancado=35.05, etapas=37.6, diaADia=39.0, proximo=40.65, alimentacao=41.7, fimVoz=42.52)
# folga ANTES de cada trecho: 0 título · 1 Em Lançar · 2 Curativa · 3 Protocolo sanitário · 4 A mesma tela (relance) · 5 Escolha o animal (volta do relance) · 6 ou o lote (digita 2014 e escolhe o animal)
# · 7 confira a data · 8 Em Protocolo sanitário · 9 escolha o tratamento (lista aberta) · 10 ele já traz… (escolhe o protocolo; diagrama) · 11 Protocolo de mastite · 12 e pede a classificação
# · 13 Se precisar (escolhe a classificação) · 14 escreva uma observação · 15 e toque em Salvar (digita; rola) · 16 Pronto, lançado (salva; carimbo) · 17 O app cria · 18 para acompanhar · 19 próximo episódio
G = [0.0, 0.3, 0.35, 0.35, 0.4, 0.5, 1.4, 0.1, 0.5, 0.3, 0.5, 0.5, 0.3, 0.6, 0.2, 1.0, 0.8, 0.2, 0.2, 0.5]
TAIL = 2.3
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado."
sobra = (-d["anc"]["lancado"]) % 0.5
G[16] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e10.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
