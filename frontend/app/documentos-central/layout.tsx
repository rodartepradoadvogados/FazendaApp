import { InsightsLayout } from "@/components/insights/InsightsLayout";

// Casca do portal "Administração" (ver components/insights/
// InsightsLayout.tsx) — esta rota vive dentro dele.
export default function Layout({ children }: { children: React.ReactNode }) {
  return <InsightsLayout>{children}</InsightsLayout>;
}
