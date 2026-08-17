"use client";
import NewsAdmin from "@/components/NewsAdmin";

// Aba de primeiro nível de Administração (17/08/2026, pedido explícito do
// usuário) — antes era sub-aba "News" dentro de Configurações. Rota
// separada da matéria pública "/news" (ver AuthShell.tsx/NewsShell) — este
// componente é só a tela de publicação/aprovação, restrita a quem tem
// pode_publicar_materias_blog (ver ABAS_ADMINISTRACAO em InsightsLayout.tsx).
export default function NewsAdminPage() {
  return <NewsAdmin />;
}
