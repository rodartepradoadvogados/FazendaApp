// Marca d'água de fundo da tela de login: monograma "CWD Milk" no topo + a
// foto real do freestall/compost barn (vacas na cama comendo) preenchendo o
// resto da tela. Puramente decorativo (aria-hidden, pointer-events: none) —
// fica atrás do card de login, bem apagado, para não atrapalhar a leitura
// do formulário.
//
// O monograma é um traço único contínuo: a perna de cima do C emenda no
// topo do W, e o topo do fim do W emenda no topo-esquerda do D — sem
// quebra entre as três letras. "Milk" (cursivo, fonte --font-script) fica
// na parte de baixo da barriga do D. Aprovado por simulação antes de entrar
// aqui (ver histórico da conversa).
export function LoginWatermark() {
  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
      <div
        style={{
          position: "absolute", top: "6vh", left: "50%", transform: "translateX(-50%)",
          width: "clamp(300px, 45vw, 640px)", opacity: 0.16,
        }}
      >
        <svg viewBox="0 0 1160 400" width="100%" height="auto">
          <path d="M240,305 A140,140 0 1 1 240,75"
            fill="none" stroke="var(--dourado-fixo)" strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M240,75 L380,305 L520,75 L660,305 L920,75"
            fill="none" stroke="var(--dourado-fixo)" strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M920,75 L920,305 A150,150 0 1,0 920,74.9"
            fill="none" stroke="var(--dourado-fixo)" strokeWidth="36" strokeLinecap="round" strokeLinejoin="round" />
          <text x="1015" y="272" textAnchor="middle" className="font-script" fontSize="60" fill="var(--vinho)">Milk</text>
        </svg>
      </div>

      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/images/login-fundo.webp"
        alt=""
        className="login-watermark-photo"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 60%" }}
      />
    </div>
  );
}
