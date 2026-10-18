"""Linha do tempo da Temporada 2 · Ep. 3 (Reprodutivo: diagnóstico de gestação). Mesma lógica de tl_t2e2.py (LEAD + folgas por frase).
   python3 tl_t2e3.py [pasta_extra_de_saida]"""
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
F = [("Temporada dois, episódio três: diagnóstico de gestação.", 0.299, 3.755), ("Em Lançar, toque em Reprodutivo, e depois em Diagnóstico.", 4.455, 8.176),
 ("No passo um, escolha quem vai ser diagnosticada. Em Situação, A tocar mostra as vacas no prazo do toque.", 8.876, 15.796),
 ("Quem ainda não chegou no prazo vem com o selo Ainda não, e só entra marcando uma por uma.", 16.633, 21.454),
 ("Atenção: o resultado vale para todas as marcadas. Então, marque primeiro as que deram positivo.", 22.154, 27.866), ("Toque em Continuar.", 28.404, 29.611),
 ("No passo dois, escolha o resultado: Positivo, para retoque. A vaca volta na agenda para reconfirmar.", 30.311, 36.611), ("Confira a data e o método, e toque em Salvar.", 37.033, 39.593),
 ("Agora as vazias: marque as que deram negativo, e escolha Negativo.", 40.393, 44.249), ("Toque em Salvar e lançar inseminação: o app já abre a inseminação com essas vacas.", 45.155, 49.916),
 ("Pronto, lançado. No retoque, use A reconfirmar, do mesmo jeito.", 50.904, 55.196), ("No próximo episódio: parto.", 55.810, 57.637)]
A = dict(temporada=.299, diagnostico1=2.40, gestacao1=3.05, emLancar=4.455, toqueRepro=5.308, reprodutivo=5.692, diagnostico=7.441, passoUm=9.388, situacao=12.375,
 aTocar=13.1, prazo=15.02, aindaNao=18.895, umaPorUma=20.772, atencao=22.154, resultadoVale=22.965, todas=23.904, marque=26.1, positivo=27.337, toqueCont=28.404,
 continuar=28.873, passoDois=30.397, resultado=31.719, positivo2=32.402, retoque=33.767, agenda=35.583, data=37.46, metodo=38.015, toqueSalvar=38.655, salvar=39.167,
 vazias=40.777, negativo=42.441, escolhaNeg=43.295, negativo2=43.679, toqueSL=45.155, salvarLancar=45.582, abre=48.313, inseminacao=48.697, pronto=50.904,
 lancado=51.416, retoque2=52.44, aReconfirmar=53.421, proximo=55.81, parto=57.048, fimVoz=57.637)
# folga ANTES de cada frase; a de F6 (Continuar) dá tempo para as 5 marcações aparecerem uma a uma sem atropelar a locução
G = [0.3, 0.4, 0.2, 0.0, 0.0, 1.5, 0.0, 0.0, 0.3, 0.0, 0.4, 0.3]
d = tl(F, G, A, 3.4)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto"
sobra = (-d["anc"]["lancado"]) % 0.5
G[10] += sobra
d = tl(F, G, A, 3.4)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e3.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
