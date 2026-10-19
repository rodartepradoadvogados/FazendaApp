"""Linha do tempo da Temporada 2 · Ep. 12 (Protocolos — lançar protocolo personalizado; último da T2). Mesma lógica de tl_t2e11.py (LEAD + folga ANTES de cada trecho):
   • a voz (voz_t2e12, 43,57 s) é recortada no meio dos silêncios; 22 trechos, alguns separados por folgas para dar tempo de tocar, digitar e rolar;
   • as âncoras por palavra (A) estão em tempo BRUTO da voz, medidas na fala real (silencedetect −28 dB, 0,04 s); os tempos do plano ficam 0,1–0,6 s adiantados (a frase F3 começa 0,55 s depois do plano).
   python3 tl_t2e12.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala)
F = [("Temporada dois, episódio doze: protocolos.", 0.369, 3.041),
 ("Em Lançar, toque em Protocolos.", 3.801, 5.500),
 ("Aqui ficam os quatro tipos:", 5.835, 7.252),
 ("IATF,", 7.498, 8.016),
 ("Indução de lactação,", 8.290, 9.277),
 ("Sanitário e Personalizado.", 9.559, 11.084),
 ("IATF e Sanitário são as mesmas telas", 12.222, 14.399),
 ("que você já viu nos episódios cinco e dez.", 14.466, 16.795),
 ("Toque em Personalizado.", 17.192, 18.309),
 ("Escolha o protocolo:", 18.654, 19.505),
 ("o app mostra quantos dias ele dura.", 19.911, 21.886),
 ("Em Aplicar em, escolha Animal,", 22.975, 24.942),
 ("para uma vaca,", 25.179, 25.840),
 ("ou Tarefa da fazenda,", 26.168, 27.152),
 ("como uma limpeza ou uma manutenção.", 27.437, 29.339),
 ("Confira a data do primeiro dia", 30.425, 31.977),
 ("e o responsável,", 32.080, 32.916),
 ("e toque em Lançar protocolo.", 33.175, 34.575),
 ("Pronto, lançado.", 35.117, 36.034),
 ("Cada etapa do protocolo vira uma pendência na Agenda.", 36.745, 39.230),
 ("Fim da temporada dois.", 40.498, 41.544),
 ("Obrigado, e bom trabalho!", 41.779, 43.179)]
END = 43.572
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
A = dict(temporada=.45, fita1=2.2, emLancar=3.95, protocolos=4.93, aquiFicam=5.9, quatroTipos=6.6, iatf=7.5, inducao=8.3, sanitario=9.56, personalizado=10.4,
 mesmasTelas=13.5, ep5=15.75, toquePers=17.2, persWord=17.65, escolha=18.66, protocolo=19.05, mostra=19.95, quantos=20.87, dias=21.1,
 aplicarEm=23.05, escolhaAn=23.98, animal=24.5, vaca=25.3, tarefa=26.36, limpeza=28.04, confira=30.43, data=30.95, primeiroDia=31.4, responsavel=32.41, lancarProt=33.54,
 pronto=35.12, lancado=35.66, cada=36.75, etapa=37.07, vira=38.39, agenda=38.95, fim=40.5, temporada2=40.76, obrigado=41.78, fimVoz=43.18)
# folga ANTES de cada trecho: 0 título · 1 Em Lançar (toca em Protocolos ao fim) · 2 Aqui ficam · 3 IATF · 4 Indução · 5 Sanitário e Personalizado · 6 IATF e Sanitário (diagrama) · 7 que você já viu
# · 8 Toque em Personalizado · 9 Escolha o protocolo (abre a lista) · 10 o app mostra quantos dias · 11 Em Aplicar em · 12 para uma vaca (busca 3654) · 13 ou Tarefa da fazenda · 14 como uma limpeza
# · 15 Confira a data · 16 e o responsável · 17 e toque em Lançar · 18 Pronto, lançado (carimbo) · 19 Cada etapa · 20 Fim da temporada · 21 Obrigado
G = [0.0, 0.3, 0.2, 0.0, 0.0, 0.0, 0.3, 0.0, 0.3, 0.4, 0.3, 0.3, 0.4, 0.9, 0.2, 0.3, 0.2, 0.1, 0.3, 0.2, 0.5, 0.4]
TAIL = 2.3
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado."
sobra = (-d["anc"]["lancado"]) % 0.5
G[18] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e12.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
