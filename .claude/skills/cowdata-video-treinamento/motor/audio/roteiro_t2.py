"""Monta o roteiro da trilha (camadas, efeitos, voz) a partir de tl_<ep>.json + beats.json (extraído da página por dump_t2.mjs).
   python3 roteiro_t2.py tl.json beats.json voz_tratada.wav saida.json
   Música 6 dB abaixo do padrão da Temporada 1 (ganho 0,13 → 0,065). Cada segmento de voz = [início no vídeo, início bruto, fim bruto]."""
import json, sys
tl, beats, voz, saida = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3], sys.argv[4]
R = {"total": tl["total"], "camadas": beats["camadas"], "fx": [[t, tipo, 0] for t, tipo in beats["sfx"]], "ganho_musica": 0.065,
     "voz": {"arquivo": voz, "segmentos": [[round(v[0] + v[1], 3), v[1], v[2]] for v in tl["voz"]]}}
json.dump(R, open(saida, "w"), ensure_ascii=False)
print("roteiro", saida, len(R["fx"]), "fx")
