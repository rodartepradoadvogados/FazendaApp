"""Trilha original + efeitos + locução, sintetizados e mixados em numpy (determinístico, sem acaso).

    python trilha.py roteiro.json saida.wav

120 BPM (batida 0,5 s, compasso 2 s). Harmonia em ciclos de 4 compassos:
F(add9) | C/E | Dm7 | B♭(add9)→C ; fecho: F(add9) | C/E | B♭(add9) | F(add9).
Camadas entram por cena (como na v2 aprovada do carrossel vivo). Efeitos (impacto, whoosh, clique) vêm da MESMA
grade de tempos do roteiro que move a imagem. A música abaixa sob a voz (ducking).
"""
import json, sys, wave
import numpy as np

SR = 48000
R = json.load(open(sys.argv[1], encoding="utf-8"))
_C = R["camadas"]
SAIDA = sys.argv[2]
TOTAL = R["total"]
N = int(SR * (TOTAL + 1.0))
BAT = 0.5
rng = np.random.default_rng(20261014)  # semente fixa: ruídos idênticos a cada render


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


F, C, D, Bb = 53, 48, 50, 46
ACORDES = {
    "Dm9": ([62, 65, 69, 76], 38), "Bbmaj7": ([62, 65, 69, 70], 46), "F/A": ([65, 69, 72, 77], 45), "Csus4": ([65, 67, 72, 74], 48), "Fmaj": ([65, 69, 72, 79], 41),  # notas (MIDI) do piano, região média/aguda; baixo à parte
    "Fadd9": ([65, 69, 72, 79], 41), "C/E": ([64, 67, 72, 76], 40), "Dm7": ([62, 65, 69, 72], 38),
    "Bbadd9": ([62, 65, 70, 72], 46), "C": ([64, 67, 72, 74], 48), "Bbadd9/F": ([62, 65, 70, 72], 41),
}
n_comp = int(round(TOTAL / 2))
prog = []
for b in range(n_comp):
    if b >= n_comp - 4:
        prog.append([("Bbmaj7", 0, 4), ("C", 0, 4), ("Dm9", 0, 4), ("Fmaj", 0, 4)][b - (n_comp - 4)])
    else:
        prog.append([("Dm9", 0, 4), ("Bbmaj7", 0, 4), ("F/A", 0, 4), ("Csus4", 0, 2)][b % 4])
        if b % 4 == 3:
            prog.append(("C", 2, 2))
# expande para eventos (compasso, início em batidas, duração em batidas, acorde)
ev = []
b = 0
for item in prog:
    nome, ini, dur = item
    if ini == 0 and ev and ev[-1][1] != 0 and False:
        pass
    ev.append((nome, ini, dur))
eventos = []
comp = -1
for nome, ini, dur in ev:
    if ini == 0:
        comp += 1
    eventos.append((comp, ini, dur, nome))

# camadas por compasso a partir das cenas do roteiro
def camadas_em(t):
    v = _C[0][1]
    for t0, lay in _C:
        if t >= t0:
            v = lay
    return set(v)


out = np.zeros(N)
musica = np.zeros(N)


def add(buf, sig, t0, g=1.0):
    i = int(round(t0 * SR))
    if i >= N:
        return
    j = min(N, i + len(sig))
    buf[i:j] += g * sig[: j - i]


def env(n, ataque, decai):
    t = np.arange(n) / SR
    e = np.exp(-t / decai)
    a = int(ataque * SR)
    if a > 0:
        e[:a] *= np.linspace(0, 1, a)
    return e


def piano(nota, dur=0.9, vel=1.0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f0 = midi(nota)
    s = np.zeros(n)
    for k, a in [(1, 1.0), (2, 0.45), (3, 0.22), (4, 0.12), (5, 0.06)]:
        s += a * np.sin(2 * np.pi * f0 * k * (1 + 0.0004 * k * k) * t) * np.exp(-t * (2.2 + 1.1 * k))
    martelo = rng.standard_normal(n) * np.exp(-t / 0.004) * 0.08
    return vel * (s + martelo) * env(n, 0.003, 10)


def baixo(nota, dur=0.24):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f0 = midi(nota)
    s = np.sin(2 * np.pi * f0 * t) + 0.3 * np.sin(4 * np.pi * f0 * t)
    return s * np.exp(-t / 0.18) * env(n, 0.004, 10)


def bumbo():
    n = int(SR * 0.28)
    t = np.arange(n) / SR
    f = 50 + 70 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11)


def passa_faixa(x, lo, hi):
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    X[(fr < lo) | (fr > hi)] = 0
    return np.fft.irfft(X, len(x))


def palma():
    n = int(SR * 0.16)
    t = np.arange(n) / SR
    s = passa_faixa(rng.standard_normal(n), 900, 2600)
    return s * np.exp(-t / 0.035) / (np.abs(s).max() + 1e-9)


def shaker():
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    s = passa_faixa(rng.standard_normal(n), 5000, 11000)
    return s * np.exp(-t / 0.012) / (np.abs(s).max() + 1e-9)


def sino(nota, dur=1.4):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f0 = midi(nota)
    s = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.7) + 0.35 * np.sin(2 * np.pi * f0 * 2.76 * t) * np.exp(-t / 0.25)
    return s * env(n, 0.002, 10)


def pad(notas, dur):
    n = int(SR * dur)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for nt in notas:
        for dt in (-0.004, 0.004):
            f = midi(nt - 12) * (1 + dt)
            s += 2 * ((f * t) % 1) - 1
    s = passa_faixa(s, 60, 1200)
    a = min(int(0.25 * SR), n // 2)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[-a:] = np.linspace(1, 0, a)
    return s * e / (len(notas) * 2)


MELODIA = [74, 77, 79, 81, 79, 77, 74, 72]  # frase de sino (pentatônica de Fá), fixa
PIANO_PADRAO = [0, 3, 6]  # colcheias sincopadas no compasso (0..7)
for comp, ini, dur, nome in eventos:
    notas, raiz = ACORDES[nome]
    t0 = comp * 2 + ini * BAT
    lay = camadas_em(t0 + 0.01)
    fecho = comp >= n_comp - 4
    # piano: hits sincopados dentro do trecho do acorde
    for e8 in range(int(dur * 2)):
        pos = ini * 2 + e8
        if pos % 8 in PIANO_PADRAO or (pos % 8 == 4 and "piano_cheio" in lay):
            for k, nt in enumerate(notas):
                add(musica, piano(nt, 1.1, 0.16 if pos % 8 == 0 else 0.11), t0 + e8 * 0.25 + k * 0.006)
    if "pad" in lay:
        add(musica, pad(notas, dur * BAT + 0.2), t0, 0.10)
    if "baixo" in lay:
        for e8 in range(int(dur * 2)):
            add(musica, baixo(raiz + (12 if e8 % 2 else 0)), t0 + e8 * 0.25, 0.30 if e8 % 2 == 0 else 0.18)
    if fecho and comp == n_comp - 1 and ini == 0:
        for k, nt in enumerate(notas + [77]):
            add(musica, piano(nt, 3.0, 0.14), t0 + 0.5 + k * 0.03)  # acorde final que soa até o fim
for comp in range(n_comp):
    t0 = comp * 2
    lay = camadas_em(t0 + 0.01)
    for bt in range(4):
        tb = t0 + bt * BAT
        if "bumbo" in lay and bt in (0, 2):
            add(musica, bumbo(), tb, 0.55 if "bumbo_leve" not in lay else 0.32)
        if "palma" in lay and bt in (1, 3):
            add(musica, palma(), tb, 0.10)
    if "shaker" in lay:
        passo = 0.125 if "shaker16" in lay else 0.25
        for k in range(int(2 / passo)):
            add(musica, shaker(), t0 + k * passo, 0.05 if k % 2 == 0 else 0.03)
    if "sino" in lay and comp % 2 == 0:
        for k in range(2):
            add(musica, sino(MELODIA[(comp + k * 3) % len(MELODIA)]), t0 + k * 1.0 + 0.25, 0.09)

# reverberação curta (convolução com cauda de ruído decrescente, semente fixa)
ir_n = int(0.45 * SR)
ir = rng.standard_normal(ir_n) * np.exp(-np.arange(ir_n) / SR / 0.12)
ir /= np.sqrt((ir ** 2).sum())
L = 1 << int(np.ceil(np.log2(N + ir_n)))
rev = np.fft.irfft(np.fft.rfft(musica, L) * np.fft.rfft(ir, L), L)[:N]
musica = musica + 0.12 * rev

# locução: segmentos da gravação do HeyGen colocados nos tempos do roteiro
with wave.open(R["voz"]["arquivo"]) as w:
    vsr, vch, vsw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32768
if vch > 1:
    raw = raw.reshape(-1, vch).mean(1)
xs = np.arange(int(len(raw) * SR / vsr)) / SR
voz_full = np.interp(xs, np.arange(len(raw)) / vsr, raw)
voz = np.zeros(N)
for t0, a, b in R["voz"]["segmentos"]:
    a0, b0 = int(max(0, a - 0.06) * SR), int((b + 0.15) * SR)
    seg = voz_full[a0:b0].copy()
    f = int(0.012 * SR)
    seg[:f] *= np.linspace(0, 1, f)
    seg[-f:] *= np.linspace(1, 0, f)
    add(voz, seg, t0 - 0.06)
voz /= np.abs(voz).max() + 1e-9

# ducking: envelope da voz (ataque 40 ms, soltura 350 ms) abaixa a música ~9 dB
blk = int(0.01 * SR)
nb = N // blk
rms = np.sqrt((voz[: nb * blk].reshape(nb, blk) ** 2).mean(1))
ativo = (rms > 0.02).astype(float)
envd = np.zeros(nb)
for i in range(nb):
    alvo = ativo[i]
    k = 0.22 if alvo > envd[i - 1 if i else 0] else 0.028
    envd[i] = (envd[i - 1] if i else 0) + k * (alvo - (envd[i - 1] if i else 0))
ganho = np.repeat(1 - 0.65 * envd, blk)
ganho = np.concatenate([ganho, np.full(N - len(ganho), ganho[-1])])
musica *= ganho

# efeitos (impacto, whoosh, clique) da grade do roteiro
def impacto():
    n = int(SR * 0.32)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 68 * t) * np.exp(-t / 0.09) + 0.4 * passa_faixa(rng.standard_normal(n), 40, 400) * np.exp(-t / 0.05)
    return s / np.abs(s).max()


def whoosh(d=0.45):
    n = int(SR * d)
    t = np.arange(n) / SR
    s = passa_faixa(rng.standard_normal(n), 600, 5000)
    e = (t / d) ** 2 * np.exp(-(t / d - 1) ** 2 * 0)  # sobe até a batida
    e[-int(0.04 * SR):] *= np.linspace(1, 0, int(0.04 * SR))
    return s * e / (np.abs(s).max() + 1e-9)


def clique():
    n = int(SR * 0.03)
    t = np.arange(n) / SR
    s = passa_faixa(rng.standard_normal(n), 2500, 9000) * np.exp(-t / 0.003) + 0.5 * np.sin(2 * np.pi * 2200 * t) * np.exp(-t / 0.006)
    return s / np.abs(s).max()


fx = np.zeros(N)
FXG = {"impacto": 0.55, "whoosh": 0.16, "clique": 0.30}
for tg, tipo, db in R["fx"]:
    g = FXG[tipo] * 10 ** (db / 20)
    if tipo == "whoosh":
        add(fx, whoosh(), tg - 0.45, g)
    elif tipo == "impacto":
        add(fx, impacto(), tg, g)
    else:
        add(fx, clique(), tg, g)

mix = 0.13 * musica / (np.abs(musica).max() + 1e-9) + 1.0 * voz + 0.55 * fx
# fade final curto e corte no total
fim = int(TOTAL * SR)
mix = mix[:fim]
f = int(0.6 * SR)
mix[-f:] *= np.linspace(1, 0, f) ** 2
mix /= np.abs(mix).max() + 1e-9
mix *= 0.7
pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
with wave.open(SAIDA, "w") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("trilha", SAIDA, "%.2f s" % (len(pcm) / SR))
