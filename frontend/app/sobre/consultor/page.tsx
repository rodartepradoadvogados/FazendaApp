import { Briefcase, FileSpreadsheet, PieChart, Target, GraduationCap, FileBarChart, Construction } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid } from "@/components/institucional/Destaques";

export default function ConsultorInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={Briefcase}
        eyebrow="Área do consultor"
        titulo="Feita também para quem assessora a fazenda"
        subtitulo="Uma área dedicada para o consultor técnico acompanhar o rebanho sem depender de planilha trocada por e-mail."
        imagem="/images/bg-administracao.webp"
      />
      <SecaoConteudo>
        <div style={{
          display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.9rem 1.1rem", borderRadius: "10px",
          background: "rgba(212,160,23,0.1)", border: "1px solid rgba(212,160,23,0.3)",
        }}>
          <Construction size={18} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text)" }}>
            <strong>Em construção</strong> — esta área ainda está sendo desenvolvida. O que está descrito abaixo é o plano em andamento, não uma funcionalidade já disponível.
          </p>
        </div>
        <DestaquesGrid itens={[
          { icon: FileSpreadsheet, titulo: "Importação simplificada", texto: "O consultor sobe uma planilha enxuta de manejo, sem precisar digitar cada lançamento no sistema." },
          { icon: PieChart, titulo: "Distribuição de DEL por serviço", texto: "Visão de quantas vacas estão em cada faixa de dias em leite na hora de servir." },
          { icon: Target, titulo: "Taxa de serviço, concepção e prenhez", texto: "Os três indicadores reprodutivos lado a lado, prontos para a reunião com o produtor." },
          { icon: GraduationCap, titulo: "Acompanhamento de recria e bezerras", texto: "A evolução das categorias jovens sem precisar abrir o rebanho inteiro." },
          { icon: FileBarChart, titulo: "Relatório personalizado on-line", texto: "O próprio consultor monta o relatório que quer ver, sem depender de pedido para o time da fazenda." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
