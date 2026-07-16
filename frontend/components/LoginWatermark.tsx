// Marca d'água de fundo da tela de login: "CWD milk" no topo + a foto real
// do freestall/compost barn (vacas na cama comendo) preenchendo o resto da
// tela. Puramente decorativo (aria-hidden, pointer-events: none) — fica atrás
// do card de login, bem apagado, para não atrapalhar a leitura do formulário.
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
