import { InsightsLayout } from "@/components/insights/InsightsLayout";

// Casca do portal "Administração" (ver components/insights/
// InsightsLayout.tsx) — esta rota vive dentro dele, aberta pela Sidebar da
// fazenda numa aba nova de verdade do navegador. Rota separada de "/news"
// (a matéria pública do blog — ver AuthShell.tsx/NewsShell) — aqui é só a
// tela de publicação/aprovação, restrita a quem tem pode_publicar_materias_blog.
export default function Layout({ children }: { children: React.ReactNode }) {
  return <InsightsLayout>{children}</InsightsLayout>;
}
