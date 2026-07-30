"use client";
import { useEffect, useState } from "react";
import { onPedidoCadastroDeEstoque, onPedidoCadastroDeAlimento } from "@/lib/alimentoEstoqueBridge";
import { Layers, Beef, Truck, Package, ArrowRightLeft, Users, HeartPulse, HeartCrack, Wrench, Trash2, Dna, GitBranch, Wheat, Pill, Scale, Baby, Sprout, ClipboardList } from "lucide-react";
import CadastroLotes from "./CadastroLotes";
import CadastroSafra from "./CadastroSafra";
import CadastroAlimentacao from "./CadastroAlimentacao";
import CadastroPesagem from "./CadastroPesagem";
import CadastroRecria from "./CadastroRecria";
import Farmacia from "./Farmacia";
import CadastroAnimalForm from "./CadastroAnimalForm";
import CadastroFornecedores from "./CadastroFornecedores";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";
import CadastroMotivosMovimentacao from "./CadastroMotivosMovimentacao";
import CadastroMotivosBaixa from "./CadastroMotivosBaixa";
import CadastroRacas from "./CadastroRacas";
import CadastroServicos from "./CadastroServicos";
import CadastroTiposMetodosServico from "./CadastroTiposMetodosServico";
import CadastroPessoas from "./CadastroPessoas";
import CadastroProtocolosCustomizados from "./CadastroProtocolosCustomizados";
import CadastroSanitario, { type AbaCadastroSanitario } from "./CadastroSanitario";
import CentralSemen, { type AbaCentralSemen } from "./CentralSemen";
import { FormExclusao } from "./FormExclusao";
import UsuariosPage from "@/app/usuarios/page";

// Ordem alfabética (pelo rótulo exibido). "usuarios" é restrito a
// administradores — quem monta a árvore de sub-navegação (Configurações >
// page.tsx) filtra essa entrada para não-admins antes de exibi-la.
export const ABAS_CADASTRO = [
  ["alimentacao", "Alimentação", Wheat],
  ["animal", "Animal (ficha)", Beef],
  ["recria", "Categorias", Baby],
  ["central-semen", "Central de Sêmen", Dna],
  ["excluir", "Excluir cadastros", Trash2],
  ["farmacia", "Farmácia", Pill],
  ["fornecedores", "Fornecedores", Truck],
  ["estoque", "Itens de estoque", Package],
  ["lotes", "Lotes", Layers],
  ["motivos-baixa", "Motivos de baixa", HeartCrack],
  ["motivos", "Motivos de movimentação", ArrowRightLeft],
  ["pesagem", "Pesagem do rebanho", Scale],
  ["pessoas", "Pessoas", Users],
  ["protocolos-customizados", "Protocolos personalizados", ClipboardList],
  ["racas", "Raças e grau de sangue", GitBranch],
  ["safra", "Safra", Sprout],
  ["sanitario", "Sanitário", HeartPulse],
  ["servicos", "Serviços", Wrench],
  ["tipos-metodos-servico", "Tipos/Métodos", Wrench],
  ["usuarios", "Usuários", Users],
] as const;
export type AbaCadastro = (typeof ABAS_CADASTRO)[number][0];

// Rendida dentro de Configurações › Cadastro. A aba ativa (e a de Sanitário,
// um nível abaixo) vêm controladas de fora — Configurações é quem registra a
// árvore completa de sub-navegação (Configurações › Cadastro › Sanitário),
// já que só um componente pode ser dono do registro por vez sem risco de um
// sobrescrever o outro na mesma renderização.
export default function Cadastro({
  aba: abaExterna, onAbaChange,
  abaSanitario: abaSanitarioExterna, onAbaSanitarioChange,
  abaCentralSemen: abaCentralSemenExterna, onAbaCentralSemenChange,
}: {
  aba?: AbaCadastro; onAbaChange?: (id: AbaCadastro) => void;
  abaSanitario?: AbaCadastroSanitario; onAbaSanitarioChange?: (id: AbaCadastroSanitario) => void;
  abaCentralSemen?: AbaCentralSemen; onAbaCentralSemenChange?: (id: AbaCentralSemen) => void;
} = {}) {
  const [abaInterna, setAbaInterna] = useState<AbaCadastro>("lotes");
  const [abaSanitarioInterna, setAbaSanitarioInterna] = useState<AbaCadastroSanitario>("principios");
  const [abaCentralSemenInterna, setAbaCentralSemenInterna] = useState<AbaCentralSemen>("estoque-semen");
  const aba = abaExterna ?? abaInterna;
  const setAba = onAbaChange ?? setAbaInterna;
  const abaSanitario = abaSanitarioExterna ?? abaSanitarioInterna;
  const setAbaSanitario = onAbaSanitarioChange ?? setAbaSanitarioInterna;
  const abaCentralSemen = abaCentralSemenExterna ?? abaCentralSemenInterna;
  const setAbaCentralSemen = onAbaCentralSemenChange ?? setAbaCentralSemenInterna;

  // Conversão bidirecional Alimento ↔ Estoque (ver lib/alimentoEstoqueBridge)
  // — quando a tela irmã pede pra "ir pra lá", só troca a aba EXTERNA daqui;
  // quem abre o formulário já preenchido é a própria tela de destino.
  useEffect(() => {
    const off1 = onPedidoCadastroDeEstoque(() => setAba("estoque"));
    const off2 = onPedidoCadastroDeAlimento(() => setAba("alimentacao"));
    return () => { off1(); off2(); };
  }, [setAba]);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Layers size={22} style={{ color: "var(--dourado)" }} /> Cadastro</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Dados mestres do site: lotes, animais, fornecedores/fabricantes/clientes e metadados de itens de estoque.
        </p>
      </div>

      {aba === "lotes" && <CadastroLotesSemMoldura />}
      {aba === "animal" && <CadastroAnimalForm />}
      {aba === "fornecedores" && <CadastroFornecedores />}
      {aba === "estoque" && <CadastroEstoqueMeta />}
      {aba === "central-semen" && <CentralSemen abaControlada={abaCentralSemen} onAbaChange={setAbaCentralSemen} />}
      {aba === "farmacia" && <Farmacia />}
      {aba === "alimentacao" && <CadastroAlimentacao />}
      {aba === "motivos" && <CadastroMotivosMovimentacao />}
      {aba === "motivos-baixa" && <CadastroMotivosBaixa />}
      {aba === "racas" && <CadastroRacas />}
      {aba === "safra" && <div style={{ margin: "-1.5rem" }}><CadastroSafra /></div>}
      {aba === "servicos" && <CadastroServicos />}
      {aba === "tipos-metodos-servico" && <CadastroTiposMetodosServico />}
      {aba === "pessoas" && <CadastroPessoas />}
      {aba === "protocolos-customizados" && <CadastroProtocolosCustomizados />}
      {aba === "sanitario" && <CadastroSanitario abaControlada={abaSanitario} onAbaChange={setAbaSanitario} />}
      {aba === "pesagem" && <CadastroPesagem />}
      {aba === "recria" && <CadastroRecria />}
      {aba === "usuarios" && <UsuariosPage />}
      {aba === "excluir" && (
        <>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Para remover um animal do rebanho, use Rebanho &gt; Baixar animal (registra motivo, gera histórico e,
            em caso de venda, o lançamento financeiro) — não uma exclusão direta da ficha.
          </p>
          <FormExclusao ocultarTipos={["animal"]} />
        </>
      )}
    </div>
  );
}

// CadastroLotes já traz seu próprio título/página (p-6 + h1) por ter existido
// antes desta aba unificada; aqui reaproveitamos o componente todo, só que
// dentro da mesma moldura das outras sub-abas de Cadastro.
function CadastroLotesSemMoldura() {
  return <div style={{ margin: "-1.5rem" }}><CadastroLotes /></div>;
}
