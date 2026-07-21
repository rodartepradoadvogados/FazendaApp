import { Syringe, CalendarClock, ClipboardList, History, CircleCheck, Baby } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid } from "@/components/institucional/Destaques";

export default function SanidadeInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={Syringe}
        eyebrow="Sanidade"
        titulo="Calendário sanitário que avisa antes de atrasar"
        subtitulo="Protocolos preventivos e curativos, calendário automático e o histórico clínico completo de cada animal do rebanho."
        imagem="/images/bg-insumos-sanidade.webp"
      />
      <SecaoConteudo>
        <DestaquesGrid itens={[
          { icon: CalendarClock, titulo: "Calendário sanitário preventivo", texto: "Vacinas e exames por época ou por evento de vida do animal, com aviso antes de atrasar." },
          { icon: ClipboardList, titulo: "Protocolos de tratamento", texto: "Curativo e preventivo, multi-produto e multi-dia, com baixa automática do estoque a cada aplicação." },
          { icon: History, titulo: "Histórico clínico completo", texto: "Cada aplicação, dose, via e resultado registrado no histórico do animal — nada se perde." },
          { icon: CircleCheck, titulo: "Confirmação de cura", texto: "Taxa de cura calculada a partir da confirmação feita direto na agenda, caso a caso." },
          { icon: Baby, titulo: "Relatório sanitário de bezerras", texto: "Colostragem e exame de sangue acompanhados à parte, no período mais crítico da recria." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
