"use client";
import { useState } from "react";
import { HelpCircle, ArrowRight } from "lucide-react";
import { Modal } from "@/components/Modal";

export type DestinoFin = "a_pagar" | "a_receber" | "lote" | "folha" | "faturas_gestao" | "caixa_funcionarios" | "consultas" | "custos" | "recorrentes" | "caixa_real";

const MAPA: { antes: string; agora: string; ir: DestinoFin; dica: string }[] = [
  { antes: "Contas › Pagas", agora: "Consultas › Pagamento", ir: "consultas", dica: "Filtro de movimento = Pagamento, período por Pagamento." },
  { antes: "Contas › Recebidas", agora: "Consultas › Recebimento", ir: "consultas", dica: "Filtro de movimento = Recebimento." },
  { antes: "Contas › Todas / Relatórios › Extrato completo", agora: "Consultas (Ambos) ou a busca por nº de documento", ir: "consultas", dica: "Consultas só mostra o já realizado; o que está em aberto fica em Contas." },
  { antes: "Relatórios › Livro Caixa", agora: "Consultas › Livro caixa", ir: "consultas", dica: "O saldo acumulado aparece quando uma conta bancária está escolhida." },
  { antes: "Ações › Pagamento / Recebimento", agora: "Contas › Contas a pagar / a receber › Dar baixa", ir: "a_pagar", dica: "A baixa abre num painel ao lado da lista." },
  { antes: "Ações › Pagamento/recebimento em lote", agora: "Contas › Pagamento/recebimento em lote", ir: "lote", dica: "Selecione linhas em Contas a pagar e clique em Baixar selecionadas." },
  { antes: "Ações › Fechamento da folha + Contas › Holerites e recibos", agora: "Contas › Folha de pagamento", ir: "folha", dica: "Holerites e recibos é uma aba dentro da folha." },
  { antes: "Contas › Faturas de fornecedor + Ações › Gestão de faturas", agora: "Contas › Gestão de faturas", ir: "faturas_gestao", dica: "Uma tela só." },
  { antes: "Ações › Caixa dos funcionários", agora: "Contas › Caixa dos funcionários", ir: "caixa_funcionarios", dica: "Só para administradores." },
  { antes: "Ações › Lançamentos recorrentes", agora: "Botão Recorrentes em Contas a pagar", ir: "recorrentes", dica: "É ali que nascem as contas a pagar." },
  { antes: "Relatórios › Custo por litro, hectare, vaca/lote e safra", agora: "Relatórios › Custos", ir: "custos", dica: "Uma tela com seletor da base de cálculo." },
];

export default function OndeFoiParar({ onIr }: { onIr: (d: DestinoFin) => void }) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setAberto(true)} title="Mostra para onde foi cada tela da organização antiga">
        <HelpCircle size={14} aria-hidden /> Onde foi parar cada tela?
      </button>
      {aberto && (
        <Modal title="Onde foi parar cada tela?" onClose={() => setAberto(false)} width="760px">
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
            Nada foi perdido: telas que faziam o mesmo trabalho foram juntadas. Links e filtros salvos antigos continuam funcionando.
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.45rem" }}>
            {MAPA.map((m) => (
              <li key={m.antes} style={{ display: "flex", alignItems: "center", gap: "0.7rem", flexWrap: "wrap", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
                <div style={{ flex: "1 1 260px", minWidth: 0 }}>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{m.antes}</div>
                  <div style={{ fontWeight: 700, fontSize: "0.88rem" }}>{m.agora}</div>
                  <div style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{m.dica}</div>
                </div>
                <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => { setAberto(false); onIr(m.ir); }}>Abrir <ArrowRight size={12} aria-hidden /></button>
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </>
  );
}
