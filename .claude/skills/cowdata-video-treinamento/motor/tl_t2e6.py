"""Linha do tempo da Temporada 2 · Ep. 6 (Produção: controle leiteiro). Mesma lógica de tl_t2e5.py (LEAD + folgas por frase).
   A locução é curta (45,8 s): duas frases são partidas numa pausa real da voz (F5 e F8) para dar tempo de digitar e preencher.
   python3 tl_t2e6.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
def tl(frases, gaps, anc, tail):
    out = {"frases": [], "anc": {}}; acc = LEAD; starts = []
    for i, (txt, a, b) in enumerate(frases):
        acc += gaps[i]; starts.append(acc); out["frases"].append([txt, round(a + acc, 3), round(b + acc, 3)])
    def V(raw):
        k = max(i for i, f in enumerate(frases) if f[1] <= raw + 1e-6) if raw >= frases[0][1] else 0
        return round(raw + starts[k], 3)
    out["anc"] = {k: V(v) for k, v in anc.items()}
    out["voz"] = [[starts[i], a, b] for i, (txt, a, b) in enumerate(frases)]
    out["total"] = round(out["frases"][-1][2] + tail, 2)
    return out
# índices: 0 F1 · 1 F2 · 2 F3 · 3 F4 · 4 F5a · 5 F5b · 6 F6 · 7 F7 · 8 F8a · 9 F8b · 10 F9 · 11 F10 · 12 F11
F = [("Temporada dois, episódio seis: controle leiteiro.", 0.256, 3.507),
 ("Em Lançar, toque em Produção, Leite, e depois em Controle leiteiro.", 4.207, 8.009),
 ("Em Lançar por, escolha Vaca ou Lote.", 8.709, 11.106),
 ("Por vaca: busque a vaca. Só aparecem as vacas em lactação.", 11.942, 15.573),
 ("Digite o leite da primeira e da segunda ordenha, em quilos.", 15.995, 19.33),
 ("A terceira é opcional. O app soma o total do dia.", 19.33, 22.686),
 ("Toque em Salvar.", 23.185, 24.009),
 ("Para o lote inteiro, toque em Lote, e escolha o lote.", 24.709, 27.533),
 ("Aparece cada vaca, com o DEL.", 27.994, 30.25),
 ("Preencha as ordenhas de cada uma: o total do lote vai somando.", 30.25, 33.480),
 ("Ordenha em branco não vira zero: fica sem lançamento, e não puxa a média para baixo.", 33.902, 38.401),
 ("Toque em Salvar. Pronto, lançado.", 38.957, 41.663),
 ("No próximo episódio: pesagem corporal e secagem.", 42.200, 45.525)]
A = dict(temporada=.256, controle1=2.2, emLancar=4.207, toqueProd=4.975, producao=5.359, leite=6.084, controle=7.236, lancarPor=8.837, vaca=10.117,
 lote=10.842, porVaca=11.942, busque=12.582, lactacao=14.971, digite=15.995, primeira=16.806, segunda=17.446,
 quilos=18.385, terceira=19.579, opcional=20.219, soma=21.606, total=21.948, toqueSalvar=23.185, salvar=23.569,
 loteInteiro=25.007, toqueLote=25.861, loteBtn=26.245, escolha=26.885, aparece=27.994, delA=29.573, preencha=30.275,
 totalLote=32.195, somando=33.091, branco=34.67, naoVira=34.969, zero=35.609, semLanc=36.121, media=37.657,
 toqueSalvar2=38.957, salvar2=39.853, pronto=40.749, lancado=41.176, proximo=42.2, pesagem=43.565, secagem=44.76,
 fimVoz=45.525)
# folga ANTES de cada frase: F2 (o título chega), F3 (a tela do formulário chega), F5a (a vaca é escolhida), F7 (o aviso de salvo fica na tela),
# F8b (a 1ª vaca do lote é preenchida em silêncio, com o dedo na tela), F9 (a tela do Salvar do lote sai), F11 (o carimbo fica na tela antes da capa)
G = [0.0, 0.4, 0.5, 0.3, 0.7, 0.4, 0.2, 0.5, 0.4, 1.2, 0.6, 0.5, 1.3]
TAIL = 2.6
d = tl(F, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Toque em Salvar. Pronto" (F10)
sobra = (-d["anc"]["lancado"]) % 0.5
G[11] += sobra
d = tl(F, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e6.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
