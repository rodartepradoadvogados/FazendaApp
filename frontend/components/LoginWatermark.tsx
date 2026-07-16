// Marca d'água de fundo da tela de login: "CWD milk" no topo + uma vaca
// holandesa dentro de um compost barn preenchendo o resto da tela. Puramente
// decorativo (aria-hidden, pointer-events: none) — fica atrás do card de
// login, bem apagado, para não atrapalhar a leitura do formulário.
export function LoginWatermark() {
  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
      <div
        style={{
          position: "absolute", top: "6vh", left: "50%", transform: "translateX(-50%)",
          textAlign: "center", color: "var(--dourado)", opacity: 0.16, whiteSpace: "nowrap",
        }}
      >
        <span style={{ fontSize: "clamp(3.5rem, 12vw, 9rem)", fontWeight: 800, letterSpacing: "0.04em" }}>CWD</span>
        <span
          className="font-script"
          style={{ fontSize: "clamp(1.6rem, 5vw, 3.2rem)", marginLeft: "0.3em", position: "relative", top: "0.6em" }}
        >
          milk
        </span>
      </div>

      <svg
        viewBox="0 0 900 520"
        preserveAspectRatio="xMidYMax meet"
        style={{ position: "absolute", bottom: 0, left: "50%", transform: "translateX(-50%)", width: "min(140vw, 1400px)", height: "auto", opacity: 0.1, color: "var(--vinho)" }}
      >
        {/* Compost barn — cobertura em duas águas, aberto nas laterais, cama de compostagem no chão. */}
        <g stroke="currentColor" fill="none" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round">
          {/* Telhado */}
          <path d="M40 190 L450 60 L860 190" />
          <path d="M80 200 L450 82 L820 200" />
          {/* Estrutura / caibros do telhado */}
          <path d="M150 168 L150 195 M260 138 L260 195 M370 108 L370 195 M530 108 L530 195 M640 138 L640 195 M750 168 L750 195" />
          {/* Pilares */}
          <path d="M90 198 L90 470 M310 198 L310 470 M590 198 L590 470 M810 198 L810 470" />
          {/* Viga de sustentação */}
          <path d="M90 210 L810 210" />
          {/* Cocho / mureta frontal baixa */}
          <path d="M40 470 L860 470" strokeWidth="7" />
          {/* Cama de compostagem — textura ondulada no piso */}
          <path d="M110 445 q30 -14 60 0 q30 14 60 0 q30 -14 60 0 q30 14 60 0 q30 -14 60 0 q30 14 60 0 q30 -14 60 0 q30 14 60 0" strokeWidth="4" />
          <path d="M110 460 q30 -12 60 0 q30 12 60 0 q30 -12 60 0 q30 12 60 0 q30 -12 60 0 q30 12 60 0 q30 -12 60 0 q30 12 60 0" strokeWidth="4" />
        </g>

        {/* Vaca holandesa — perfil, deitada/parada na cama de compostagem.
            Deslocada à esquerda do centro para não ficar toda escondida
            atrás do card de login (que fica sobre o centro da cena). */}
        <g transform="translate(230,300) scale(1.15)">
          {/* Pernas (atrás do corpo) */}
          <g stroke="currentColor" strokeWidth="9" strokeLinecap="round">
            <path d="M-70 110 L-78 175" />
            <path d="M-15 118 L-20 180" />
            <path d="M95 118 L102 180" />
            <path d="M150 108 L160 172" />
          </g>
          {/* Cascos */}
          <g stroke="currentColor" strokeWidth="11" strokeLinecap="round">
            <path d="M-83 178 L-73 178" />
            <path d="M-25 183 L-15 183" />
            <path d="M97 183 L107 183" />
            <path d="M155 175 L165 175" />
          </g>
          {/* Rabo */}
          <path d="M175 40 q40 25 22 95" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
          <ellipse cx="196" cy="140" rx="10" ry="16" fill="currentColor" opacity="0.55" />

          {/* Corpo — barril bovino, largo e arredondado */}
          <path
            d="M-95 75
               C -108 20, -70 -55, 30 -68
               C 120 -80, 190 -55, 205 -5
               C 216 30, 208 70, 178 95
               C 150 118, 40 122, -50 118
               C -78 116, -90 100, -95 75 Z"
            fill="none" stroke="currentColor" strokeWidth="6.5"
          />
          {/* Linha do dorso mais alta perto da cernelha */}
          <path d="M-70 -35 C -20 -60, 70 -68, 150 -50" fill="none" stroke="currentColor" strokeWidth="5" opacity="0.7" />

          {/* Manchas holandesas — mesma cor, mais discretas que o contorno */}
          <g fill="currentColor" opacity="0.5">
            <path d="M-60 -10 q40 -38 78 -8 q10 30 -25 46 q-45 6 -53 -38 Z" />
            <path d="M55 -55 q45 -14 68 18 q2 28 -35 32 q-38 -3 -33 -50 Z" />
            <path d="M110 45 q38 -22 66 6 q6 28 -22 40 q-42 0 -44 -46 Z" />
            <path d="M-45 55 q30 -14 48 8 q2 20 -20 26 q-30 0 -28 -34 Z" />
          </g>

          {/* Úbere */}
          <path d="M20 112 q14 26 55 24 q34 -2 42 -22" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />

          {/* Pescoço + cabeça, abaixada em direção à cama (postura de comendo/cheirando) */}
          <path
            d="M-95 15
               C -140 5, -185 15, -215 45
               C -232 63, -230 88, -212 98
               C -198 106, -180 100, -168 108
               C -158 114, -145 110, -142 96
               C -140 78, -145 55, -140 35
               C -135 20, -115 12, -95 15 Z"
            fill="none" stroke="currentColor" strokeWidth="6"
          />
          {/* Orelha */}
          <path d="M-172 40 q-24 -14 -42 2 q8 20 32 18 q14 -8 10 -20 Z" fill="currentColor" opacity="0.5" />
          {/* Chifres pequenos */}
          <path d="M-158 24 q-6 -18 4 -26 M-138 20 q-2 -18 10 -24" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
          {/* Olho */}
          <circle cx="-160" cy="55" r="5" fill="currentColor" opacity="0.7" />
        </g>
      </svg>
    </div>
  );
}
