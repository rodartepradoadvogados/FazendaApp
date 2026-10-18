"""Linha do tempo da Temporada 2 · Ep. 5 (Reprodutivo: protocolo de IATF). Mesma lógica de tl_t2e2.py/tl_t2e4.py (LEAD + folgas por frase).
   python3 tl_t2e5.py [pasta_extra_de_saida]"""
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
F = [("Temporada dois, episódio cinco: protocolo de IATF.", 0.299, 3.836),
 ("Em Lançar, toque em Reprodutivo, e depois em Protocolo IATF. A mesma tela abre em Protocolos, IATF.", 4.536, 11.707),
 ("No passo um, escolha quem entra no protocolo. Em Situação, toque em Atrasadas: são as vacas vazias que já passaram do ponto.", 12.503, 20.160),
 ("Toque em Selecionar todas as atrasadas.", 21.100, 23.455),
 ("Vaca que já está em protocolo aparece travada, com o dia da etapa. Ela não entra duas vezes.", 23.916, 29.141),
 ("Toque em Continuar.", 30.087, 30.915),
 ("No passo dois, confira a data do D zero. O app já mostra o protocolo inteiro: D sete, D nove e D onze, com as datas e os hormônios.", 31.453, 39.715),
 ("Atenção: isso só agenda o protocolo. A inseminação do D onze é lançada à parte.", 40.351, 45.560),
 ("Toque em Lançar D zero.", 45.983, 47.527),
 ("Pronto, lançado. As próximas etapas já entram na Agenda.", 48.227, 51.682),
 ("No próximo episódio: controle leiteiro.", 52.382, 54.854)]
A = dict(temporada=.299, protocolo1=2.4, emLancar=4.536, toqueRepro=5.518, reprodutivo=5.902, protocoloIatf=7.566, mesmaTela=9.102, protocolos=10.083,
 iatf2=10.936, passoUm=12.503, quem=14.039, situacao=15.661, atrasadas=16.898, vazias=18.519, ponto=19.799,
 toqueSel=21.1, selecionar=21.697, atrasadas2=22.806, emProtocolo=24.769, travada=25.836, dia=26.689, duasVezes=28.524,
 toqueCont=30.087, continuar=30.471, passoDois=31.453, data=32.946, dZero=33.372, protocoloInteiro=35.122, d7=35.975,
 d9=36.829, d11=37.639, datas=38.663, hormonios=39.218, atencao=40.351, soAgenda=41.588, inseminacao=43.295,
 aParte=45.172, toqueLancar=45.983, lancarD0=46.409, pronto=48.227, lancado=48.654, agenda=51.341, proximo=52.382,
 controleLeiteiro=53.577, fimVoz=54.854)
# folga ANTES de cada frase: F5 (Todas + busca da vaca em protocolo), F7 (a tela do Passo 2 chega), F11 (respiro antes da capa)
G = [0.3, 0.4, 0.2, 0.0, 0.8, 0.0, 0.3, 0.0, 0.0, 0.0, 0.4]
d = tl(F, G, A, 3.4)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto"
sobra = (-d["anc"]["lancado"]) % 0.5
G[9] += sobra
d = tl(F, G, A, 3.4)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e5.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
