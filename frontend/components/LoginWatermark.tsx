import { CowDataMark } from "@/components/brand/CowDataMark";

// Marca d'água de fundo da tela de login: o ícone "A Curva" da marca CowData
// no topo + a foto real do freestall/compost barn (vacas na cama comendo)
// preenchendo o resto da tela. Puramente decorativo (aria-hidden,
// pointer-events: none) — fica atrás do card de login, bem apagado, para não
// atrapalhar a leitura do formulário. Curva em uma cor só (sem tile), como
// pede o manual de marca para usos de marca d'água.
export function LoginWatermark() {
  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none", zIndex: 0 }}>
      <div
        style={{
          position: "absolute", top: "-24vh", left: "50%", transform: "translateX(-50%)",
          width: "clamp(1440px, 234vw, 2880px)", opacity: 0.1,
        }}
      >
        <CowDataMark size="100%" variant="mono" color="#ffffff" />
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
