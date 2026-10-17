"""Linha do tempo da Temporada 2 · Ep. 1 (Movimentar: troca de lotes). Mesma lógica de tl.py (LEAD + folgas por frase),
sem reescrever os arquivos da Temporada 1.   python3 tl_t2e1.py [pasta_extra_de_saida]"""
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
F = [("Temporada dois: os Lançamentos. Episódio um, troca de lotes.", 0.299, 3.968), ("No app, toque em Lançar, aqui embaixo.", 4.668, 6.959),
 ("Depois, em Movimentar.", 7.459, 8.820), ("Primeiro, quem vai mudar de lote. Em Origem, toque em Lotes e escolha o lote de onde as vacas saem.", 9.549, 15.134),
 ("Marque as vacas. Pode ser uma, ou o lote inteiro, de uma vez.", 15.734, 19.267), ("A barra embaixo conta as marcadas. Toque em Continuar.", 19.728, 22.898),
 ("Agora, para onde elas vão. Toque no lote de destino. O app já mostra a conta: trinta e oito vira quarenta e um.", 23.598, 30.071),
 ("O quadro confere quem sai e quem chega. Escolha o motivo e confira a data.", 30.532, 34.985), ("Toque em Movimentar três animais.", 35.898, 37.532),
 ("Pronto, lançado. Os lotes já mudam no sistema.", 38.332, 41.370), ("Sem internet, o lançamento fica guardado e vai sozinho quando o sinal voltar.", 42.210, 46.182),
 ("No próximo episódio: inseminação em lote.", 46.882, 49.526)]
A = dict(temporada=.299, lancamentos=1.365, episodio=2.432, troca=3.328, noApp=4.668, toqueLancar=5.180, lancar=5.649, aqui=6.332, depois=7.459, movimentar=8.184,
 primeiro=9.549, quem=10.274, emOrigem=11.682, toqueLotes=12.493, lotes=12.920, escolha=13.474, saem=14.882, marque=15.734, vacas=16.118, pode=16.955, inteiro=18.278,
 barra=19.941, conta=20.624, toqueCont=21.904, continuar=22.331, agora=23.598, toqueDest=25.391, destino=26.159, conta2=28.100, trinta=28.569, quarenta=29.508,
 quadro=30.703, sai=31.726, chega=32.494, motivo=33.647, data=34.799, toqueMov=35.898, movimentar2=36.325, tres=36.837, pronto=38.332, lancado=38.844,
 lotesMudam=39.826, sistema=40.935, semInternet=42.210, guardado=43.960, sozinho=44.856, proximo=46.882, inseminacao=48.119, fimVoz=49.526)
G = [0.5, 1.0, 0.3, 0.7, 0.5, 0.4, 0.8, 0.6, 0.5, 0.6, 0.8, 0.9]
d = tl(F, G, A, 3.4)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto"
sobra = (-d["anc"]["lancado"]) % 0.5
G[9] += sobra
d = tl(F, G, A, 3.4)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e1.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
