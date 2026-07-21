import { Smartphone, WifiOff, CalendarCheck, Zap, User, PawPrint } from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { InstitucionalHero } from "@/components/institucional/InstitucionalHero";
import { SecaoConteudo, DestaquesGrid } from "@/components/institucional/Destaques";

export default function AppCampoInstitucional() {
  return (
    <PublicPage>
      <InstitucionalHero
        icon={Smartphone}
        eyebrow="App de campo"
        titulo="O sistema também vai pro curral, offline"
        subtitulo="Um aplicativo enxuto para o dia a dia de campo — lançamentos rápidos que funcionam mesmo sem internet."
        imagem="/images/bg-ciclo-diario.webp"
      />
      <SecaoConteudo>
        <DestaquesGrid itens={[
          { icon: WifiOff, titulo: "Funciona sem internet", texto: "Os lançamentos ficam guardados no celular e são enviados sozinhos quando a conexão voltar." },
          { icon: CalendarCheck, titulo: "Agenda do dia", texto: "As tarefas do dia com botão de concluir, direto na tela inicial do aplicativo." },
          { icon: Zap, titulo: "Lançar rápido", texto: "Reprodutivo, leite, sanidade, alimentação e estoque em poucos toques, sem passar pelo site." },
          { icon: PawPrint, titulo: "Ficha do animal no bolso", texto: "Histórico, lote e movimentação do animal, tudo disponível no celular do funcionário." },
          { icon: User, titulo: "Um usuário por pessoa", texto: "Cada funcionário usa o próprio usuário — os lançamentos ficam registrados em nome de quem fez." },
        ]} />
      </SecaoConteudo>
    </PublicPage>
  );
}
