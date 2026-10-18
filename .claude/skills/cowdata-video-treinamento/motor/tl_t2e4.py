"""Linha do tempo da Temporada 2 · Ep. 4 (Reprodutivo: parto). Mesma lógica de tl_t2e2.py/tl_t2e3.py (LEAD + folgas por frase).
   python3 tl_t2e4.py [pasta_extra_de_saida]"""
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
F = [("Temporada dois, episódio quatro: parto.", 0.256, 2.859), ("Em Lançar, toque em Reprodutivo, e depois em Parto.", 3.559, 6.507),
 ("Busque a matriz pelo número ou pelo nome, e confira a data do parto.", 7.207, 10.796),
 ("Em Tipo de parto, escolha Normal. Se houve retenção de placenta, marque: o app cria um item na Agenda.", 11.217, 17.784),
 ("Toque no sexo da cria, e digite o número dela. Se ficar sem número, a cria é baixada automaticamente.", 18.384, 24.405),
 ("Tem os dados do colostro? Abra Colostragem e IgG. O app já classifica: ouro, prata ou bronze.", 24.981, 31.869), ("Toque em Salvar.", 32.804, 33.619),
 ("O app pergunta se quer mover a mãe de lote. Confira, e toque em Confirmar.", 34.319, 38.831), ("Depois, sugere o lote da cria: a bezerra vai para o lote de bezerras.", 39.506, 43.820),
 ("Pronto, lançado. Nasceram gêmeos? Marque Parto gemelar, e preencha a segunda cria.", 44.520, 49.863), ("No próximo episódio: protocolo de IATF.", 50.722, 54.185)]
A = dict(temporada=.256, parto1=2.25, emLancar=3.559, toqueRepro=4.455, reprodutivo=4.839, parto=6.204, busque=7.207, matriz=7.719, numero=8.274, nome=9.127, data=10.151,
 tipoParto=11.729, normal=13.009, retencao=14.374, placenta=14.887, marque=15.569, agenda=17.404, sexo=18.811, digite=19.878, numeroCria=20.347, semNumero=21.739,
 baixada=23.018, colostro=25.707, abra=26.56, colostragem=26.901, classifica=29.333, ouro=30.016, prata=30.656, bronze=31.424, toqueSalvar=32.804, salvar=33.231,
 pergunta=34.745, mae=35.94, lote=36.238, confira=36.878, confirmar=38.158, depois=39.506, loteCria=40.957, bezerra=42.023, bezerras=43.346, pronto=44.52,
 lancado=44.989, gemeos=46.397, gemelar=47.933, segunda=49.213, proximo=50.722, iatf=52.984, fimVoz=54.185)
# folga ANTES de cada frase: F6 (tempo de abrir e preencher a colostragem), F10 (tempo do mini-quadro dos lotes antes do carimbo)
G = [0.3, 0.4, 0.2, 0.0, 0.0, 0.5, 0.0, 0.0, 0.2, 1.2, 0.4]
d = tl(F, G, A, 3.4)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto"
sobra = (-d["anc"]["lancado"]) % 0.5
G[9] += sobra
d = tl(F, G, A, 3.4)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e4.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
