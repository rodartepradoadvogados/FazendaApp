import { InsightsLayout } from "@/components/insights/InsightsLayout";

// Casca do portal "Insights e Administração" (ver components/insights/
// InsightsLayout.tsx) — esta rota vive dentro dele, aberta pela Sidebar da
// fazenda numa aba nova de verdade do navegador.
export default function Layout({ children }: { children: React.ReactNode }) {
  return <InsightsLayout>{children}</InsightsLayout>;
}
