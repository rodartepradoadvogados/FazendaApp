"use client";
// Só alcançável de dentro do app (ver InicioMobilePainelCowData e
// PainelCowDataShell::appMode em ../layout.tsx) — o Cockpit de desktop
// continua em /painel-cowdata (page.tsx), intacto.
import CockpitMobile from "@/components/painel-cowdata/mobile/CockpitMobile";

export default function CockpitCowDataMobile() {
  return <CockpitMobile />;
}
