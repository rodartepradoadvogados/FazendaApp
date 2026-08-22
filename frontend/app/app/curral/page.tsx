"use client";
// Rota /app/curral — Modo Curral (ver components/mobile/ModoCurral.tsx).
// Continua dentro da casca do app (cabeçalho + nav inferior de app/app/layout.tsx),
// só que sem aba própria na navegação de baixo: chega-se por Menu > App >
// "Modo Curral" ou pelo atalho no topo de Lançar.
import { useRouter } from "next/navigation";
import { ModoCurral } from "@/components/mobile/ModoCurral";

export default function Pagina() {
  const router = useRouter();
  return <ModoCurral onVoltar={() => router.push("/app")} />;
}
