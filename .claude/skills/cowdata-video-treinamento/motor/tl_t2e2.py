"""Linha do tempo da Temporada 2 · Ep. 2 (Reprodutivo: inseminação em lote). Mesma lógica de tl_t2e1.py (LEAD + folgas por frase).
   python3 tl_t2e2.py [pasta_extra_de_saida]"""
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
F = [("Temporada dois, episódio dois: inseminação em lote.", 0.299, 3.337), ("Em Lançar, toque em Reprodutivo, e depois em Inseminação.", 4.037, 7.421),
 ("Primeiro, quem vai ser inseminada. Em Origem, toque em Lotes, e no lote zero um, Alta.", 8.121, 13.625),
 ("Em Situação, fique em Aptas: são as vacas liberadas para inseminar.", 14.225, 18.039), ("Toque em Selecionar todas as aptas, ou marque uma por uma.", 18.952, 22.370),
 ("E vaca prenhe? Em Todas, ela aparece com aviso, e só entra se você confirmar. Na dúvida, deixe de fora.", 23.070, 29.450), ("Toque em Continuar.", 30.050, 30.911),
 ("Agora, o sêmen. Confira a data, a categoria, e escolha o touro.", 31.611, 35.574), ("O app mostra o estoque: doze doses viram oito.", 36.292, 39.070),
 ("Se uma vaca recebeu outro touro, troque só ela, em Touro por vaca.", 39.493, 42.949), ("Toque em Salvar inseminação. O app manda uma por uma, e mostra o andamento.", 43.649, 47.994),
 ("Pronto, lançado. Se alguma falhar, é só tocar em Tentar de novo só essa.", 48.794, 53.426), ("No próximo episódio: diagnóstico de gestação.", 54.413, 57.616)]
A = dict(temporada=.299, inseminacao=2.261, emLancar=4.037, lancar=4.165, toqueRepro=4.891, reprodutivo=5.232, depois=6.128, inseminacao2=6.597, primeiro=8.121, quem=8.846,
 emOrigem=10.169, toqueLotes=10.98, lotes=11.407, zeroUm=12.644, alta=13.241, situacao=14.353, aptas=15.505, liberadas=16.785, toqueSel=18.952, selecionar=19.379,
 umaPorUma=21.725, prenhe=23.455, todas=24.35, aviso=25.545, confirmar=27.038, duvida=28.174, deixe=28.772, toqueCont=30.05, continuar=30.434, agora=31.611,
 semen=32.251, data=33.403, categoria=34.001, touro=35.323, estoque=37.274, doze=37.786, oito=38.81, outroTouro=40.474, troque=41.199, touroPorVaca=42.223,
 toqueSalvar=43.649, salvar=44.119, umaPorUma2=46.364, andamento=47.772, pronto=48.794, lancado=49.306, falhar=50.671, tentar=52.079, proximo=54.413,
 diagnostico=55.736, fimVoz=57.616)
G = [0.3, 0.4, 0.2, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.9, 0.4, 0.3]  # as pausas naturais da locução (~0,6 s) já fazem o ritmo; a folga só acrescenta onde a tela precisa de tempo
d = tl(F, G, A, 3.4)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto"
sobra = (-d["anc"]["lancado"]) % 0.5
G[11] += sobra
d = tl(F, G, A, 3.4)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e2.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
