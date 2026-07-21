import { BarChart3, LayoutGrid, HeartPulse, FileBarChart, SlidersHorizontal, Milk } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid, FaixaNumeros } from "@/components/institucional/Destaques";

export default function IndicadoresInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={BarChart3}
        eyebrow="Indicadores gerenciais"
        titulo="A fazenda inteira, num único painel de decisão"
        subtitulo="Indicadores para decisão rápida — a visão global dos resultados da fazenda, sem precisar abrir uma tela por vez."
        imagem="/images/bg-analise.webp"
      />
      <SecaoConteudo>
        <FaixaNumeros itens={[
          { valor: "8 listas", rotulo: "Listas gerenciais de manejo" },
          { valor: "7 gráficos", rotulo: "Gráficos gerenciais" },
          { valor: "10 filtros", rotulo: "No relatório personalizado" },
          { valor: "5 parâmetros", rotulo: "Cruzáveis no mesmo gráfico" },
        ]} />
        <DestaquesGrid itens={[
          { icon: LayoutGrid, titulo: "Painel único", texto: "Os indicadores gerenciais reunidos numa mesma tela, sem abrir módulo por módulo." },
          { icon: HeartPulse, titulo: "Situação reprodutiva", texto: "Aptas, inseminadas, gestantes e a descartar — tudo num único gráfico, sempre atualizado." },
          { icon: FileBarChart, titulo: "Relatórios gerenciais", texto: "Listas de manejo e gráficos prontos, exportáveis em Excel e PDF a qualquer momento." },
          { icon: SlidersHorizontal, titulo: "Relatório personalizado", texto: "Até 10 filtros e 5 parâmetros cruzados num gráfico só, sem precisar pedir para o time de TI." },
          { icon: Milk, titulo: "Produção e qualidade do leite", texto: "CCS, CPP, projeção de entrega e desvio de equipe residual, tudo no mesmo lugar." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
