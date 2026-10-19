"""Linha do tempo da Temporada 2 · Ep. 8 (Produção: BST). Mesma lógica de tl_t2e7.py (LEAD + folga ANTES de cada trecho), mas SEM remapear: as âncoras abaixo já
   foram medidas na voz real (voz_t2e8, 43,62 s: silencedetect a −34 dB / 0,045 s). A voz é recortada no meio de cada silêncio entre as falas.
   A locução é curta; as folgas dão tempo para rolar a página, arrastar a tabela, desmarcar uma vaca, digitar a dose e ler os retornos.
   python3 tl_t2e8.py [pasta_extra_de_saida]"""
import json, sys
LEAD = 0.6
# (texto, início real da fala, fim real da fala) — medidos em voz_t2e8
F = [("Temporada dois, episódio oito: BST.", 0.365, 3.100),
 ("Em Lançar, toque em Produção, Leite, e depois em BST.", 3.672, 7.419),
 ("No topo, o app mostra a data da próxima aplicação,", 8.697, 11.482),
 ("e separa as vacas em três grupos: Aptas, Incluir no próximo BST, e Inaptas.", 11.688, 16.916),
 ("Em Aptas, toque em Marcar todas as aptas.", 17.868, 20.588),
 ("O DEL projetado é o DEL que a vaca vai ter no dia da aplicação.", 21.197, 24.591),
 ("Confira o produto e a dose:", 25.675, 27.021),
 ("o app mostra como fica o estoque.", 27.209, 28.972),
 ("Toque em Aplicar BST, e confirme.", 29.486, 31.695),
 ("Vaca que não deve receber?", 32.141, 33.315),
 ("Marque,", 33.812, 34.06),
 ("e toque em Marcar inapta:", 34.36, 35.48),
 ("ela sai da lista,", 35.84, 36.56),
 ("sem mexer no estoque.", 36.966, 37.864),
 ("Pronto, lançado.", 38.349, 39.110),
 ("No próximo episódio: sanidade, aplicação de medicamentos.", 39.929, 43.31)]
CORTE = []
for i, (t, a, b) in enumerate(F):
    ca = max(a - 0.15, (F[i - 1][2] + a) / 2) if i else max(0.0, a - 0.15)
    cb = min(b + 0.15, (b + F[i + 1][1]) / 2) if i + 1 < len(F) else min(43.6, b + 0.15)
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
A = dict(temporada=.365, fita1=2.2, emLancar=3.68, toqueProd=4.53, producao=5.0, leite=5.68, bst=6.9, topo=8.71, proximaAplic=10.62, tresGrupos=12.78, aptas=13.67, incluir=14.36,
 inaptas=16.3, emAptas=17.88, toqueMarcar=18.77, marcarTodas=19.1, delProj=21.45, diaAplic=23.3, produto=26.17, dose=26.65, comoFica=27.5, estoque=28.1, aplicar=29.99, confirme=31.0,
 naoDeve=32.15, marque=33.81, marcarInapta=34.85, saiLista=35.84, semEstoque=36.97, pronto=38.35, lancado=38.71, proximo=39.94, sanidade=41.16, fimVoz=43.31)
# folga ANTES de cada trecho: 0 F1 · 1 F2 · 2 topo · 3 três grupos · 4 Em Aptas (rola até a tabela) · 5 DEL projetado (arrasta a tabela de lado) · 6 Confira (desmarca 1, rola até a barra)
# · 7 estoque · 8 Aplicar · 9 Vaca que não deve (o retorno fica na tela, rola para a tabela) · 10 Marque · 11 e toque (rola até a barra) · 12 ela sai da lista · 13 sem mexer no estoque
# · 14 Pronto, lançado (o carimbo) · 15 próximo episódio
G = [0.0, 0.4, 0.2, 0.2, 0.3, 0.8, 1.4, 0.3, 0.4, 1.0, 0.2, 0.7, 0.3, 0.6, 0.6, 1.1]
TAIL = 2.6
d = tl(CORTE, G, A, TAIL)
# carimbo ("lançado") numa batida de 120 BPM (múltiplo de 0,5 s): acrescenta a menor folga antes de "Pronto, lançado."
sobra = (-d["anc"]["lancado"]) % 0.5
G[14] += sobra
d = tl(CORTE, G, A, TAIL)
if __name__ == "__main__":
    for pasta in ["audio"] + sys.argv[1:]:
        json.dump(d, open(f"{pasta}/tl_t2e8.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("total", d["total"], "lancado", d["anc"]["lancado"], "folga extra", round(sobra, 3))
