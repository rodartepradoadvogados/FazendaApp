import { HeartPulse, Syringe, Stethoscope, Target, History, CalendarClock } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid, FaixaNumeros } from "@/components/institucional/Destaques";

export default function ReprodutivoInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={HeartPulse}
        eyebrow="Reprodutivo"
        titulo="Reprodução sob controle, do cio ao diagnóstico"
        subtitulo="Protocolos, inseminação, diagnóstico e o histórico completo de cada matriz — a visão global da situação reprodutiva do rebanho, sempre atualizada."
        imagem="/images/bg-rebanho.webp"
      />
      <SecaoConteudo>
        <FaixaNumeros itens={[
          { valor: "D0–D11", rotulo: "Protocolo IATF completo" },
          { valor: "2 tipos", rotulo: "Sêmen sexado/convencional" },
          { valor: "100%", rotulo: "Histórico por matriz" },
          { valor: "1 painel", rotulo: "Situação reprodutiva" },
        ]} />
        <DestaquesGrid itens={[
          { icon: Syringe, titulo: "Protocolos IATF completos", texto: "D0, D7, D9 e D11 com hormônio por etapa — a agenda avisa cada passo, do início do protocolo ao serviço." },
          { icon: HeartPulse, titulo: "Inseminação e monta natural", texto: "Touro por categoria, sêmen sexado ou convencional, inseminação avulsa ou em lote." },
          { icon: Stethoscope, titulo: "Diagnóstico de gestação", texto: "Toque, reconfirmação e resultado direto na ficha da vaca, com alerta para gestação recente." },
          { icon: Target, titulo: "Acasalamento direcionado", texto: "Sugestão de touro por vaca, com a nota dos critérios usados na indicação." },
          { icon: History, titulo: "Histórico por matriz", texto: "Toda a vida reprodutiva num só lugar: partos, inseminações, secagens, diagnósticos e perdas de prenhez." },
          { icon: CalendarClock, titulo: "Agenda do veterinário", texto: "Visão dedicada para a visita técnica, com exportação em Excel e PDF." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
