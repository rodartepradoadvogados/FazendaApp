"use client";
import { useState } from "react";
import {
  ClipboardList, Info, Beef, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby,
} from "lucide-react";

/**
 * Tela de Lançamentos — RASCUNHO.
 * Objetivo: desenhar juntos a forma final das entradas manuais. Os campos são
 * um ponto de partida; ainda NÃO gravam nada. Serve para o produtor apontar
 * todas as possibilidades de lançamento de cada tipo.
 */

type Campo = {
  label: string;
  tipo?: "text" | "number" | "date" | "select" | "textarea";
  opcoes?: string[];
  placeholder?: string;
  larg?: "full" | "meia"; // ocupa a linha toda ou metade
};

type Tipo = {
  id: string;
  label: string;
  icon: any;
  desc: string;
  campos: Campo[];
};

const TIPOS: Tipo[] = [
  {
    id: "animal", label: "Animal (ficha)", icon: Beef,
    desc: "Cadastro/atualização de um animal do rebanho.",
    campos: [
      { label: "Número / brinco", tipo: "text", larg: "meia", placeholder: "ex.: 464" },
      { label: "Nome (opcional)", tipo: "text", larg: "meia" },
      { label: "Sexo", tipo: "select", opcoes: ["Fêmea", "Macho"], larg: "meia" },
      { label: "Raça", tipo: "select", opcoes: ["Girolando", "Holandês", "Gir", "Outra"], larg: "meia" },
      { label: "Data de nascimento", tipo: "date", larg: "meia" },
      { label: "Categoria / grupo", tipo: "text", larg: "meia", placeholder: "ex.: Novilha, 01 - NOV. ALTA" },
      { label: "Mãe (nº)", tipo: "text", larg: "meia" },
      { label: "Pai / touro", tipo: "text", larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "servico", label: "Serviço / IA", icon: Heart,
    desc: "Inseminação, IATF ou cobertura de uma matriz.",
    campos: [
      { label: "Matriz (nº)", tipo: "text", larg: "meia" },
      { label: "Data do serviço", tipo: "date", larg: "meia" },
      { label: "Tipo", tipo: "select", opcoes: ["IATF", "IA em cio natural", "Cobertura / monta"], larg: "meia" },
      { label: "Touro / sêmen", tipo: "text", larg: "meia" },
      { label: "Protocolo (se IATF)", tipo: "text", larg: "meia" },
      { label: "Responsável / inseminador", tipo: "text", larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope,
    desc: "Resultado do toque / diagnóstico de prenhez.",
    campos: [
      { label: "Matriz (nº)", tipo: "text", larg: "meia" },
      { label: "Data do diagnóstico", tipo: "date", larg: "meia" },
      { label: "Resultado", tipo: "select", opcoes: ["Positivo", "Negativo", "Reconfirmar"], larg: "meia" },
      { label: "Método", tipo: "select", opcoes: ["Palpação", "Ultrassom"], larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "parto", label: "Parto / nascimento", icon: Baby,
    desc: "Registro de parto e da(s) cria(s).",
    campos: [
      { label: "Matriz (nº)", tipo: "text", larg: "meia" },
      { label: "Data do parto", tipo: "date", larg: "meia" },
      { label: "Situação", tipo: "select", opcoes: ["Normal", "Natimorto", "Aborto", "Parto assistido/puxado"], larg: "meia" },
      { label: "Nº de crias", tipo: "number", larg: "meia" },
      { label: "Nº da cria", tipo: "text", larg: "meia", placeholder: "ex.: 483" },
      { label: "Sexo da cria", tipo: "select", opcoes: ["Fêmea", "Macho"], larg: "meia" },
      { label: "Cria baixada? (não entra no rebanho)", tipo: "select", opcoes: ["Não", "Sim"], larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "producao", label: "Controle leiteiro", icon: Milk,
    desc: "Pesagem de leite de uma vaca.",
    campos: [
      { label: "Vaca (nº)", tipo: "text", larg: "meia" },
      { label: "Data do controle", tipo: "date", larg: "meia" },
      { label: "Produção (kg/dia)", tipo: "number", larg: "meia" },
      { label: "DEL (dias em lactação)", tipo: "number", larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "sanidade", label: "Sanidade", icon: Syringe,
    desc: "Aplicação de medicamento / manejo sanitário.",
    campos: [
      { label: "Animal (nº)", tipo: "text", larg: "meia" },
      { label: "Data", tipo: "date", larg: "meia" },
      { label: "Produto / medicamento", tipo: "text", larg: "meia" },
      { label: "Categoria", tipo: "select", opcoes: ["Vacina", "Antibiótico", "Vermífugo", "Hormônio", "Suplemento/Vitamina", "Outro"], larg: "meia" },
      { label: "Dose", tipo: "text", larg: "meia" },
      { label: "Via", tipo: "select", opcoes: ["Intramuscular", "Subcutânea", "Oral", "Intravenosa", "Tópica"], larg: "meia" },
      { label: "Responsável", tipo: "text", larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "financeiro", label: "Financeiro", icon: Wallet,
    desc: "Lançamento de receita ou despesa.",
    campos: [
      { label: "Data", tipo: "date", larg: "meia" },
      { label: "Tipo", tipo: "select", opcoes: ["Receita", "Despesa"], larg: "meia" },
      { label: "Conta gerencial", tipo: "text", larg: "meia", placeholder: "ex.: Leite indústria" },
      { label: "Valor (R$)", tipo: "number", larg: "meia" },
      { label: "Fornecedor / cliente", tipo: "text", larg: "meia" },
      { label: "Centro de custo", tipo: "text", larg: "meia" },
      { label: "Descrição", tipo: "textarea", larg: "full" },
    ],
  },
  {
    id: "estoque", label: "Estoque", icon: Package,
    desc: "Entrada ou saída de item do estoque.",
    campos: [
      { label: "Item", tipo: "text", larg: "meia" },
      { label: "Movimento", tipo: "select", opcoes: ["Entrada", "Saída"], larg: "meia" },
      { label: "Quantidade", tipo: "number", larg: "meia" },
      { label: "Unidade", tipo: "text", larg: "meia", placeholder: "kg, un, L..." },
      { label: "Data", tipo: "date", larg: "meia" },
      { label: "Observação", tipo: "textarea", larg: "full" },
    ],
  },
];

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};

export default function LancamentosPage() {
  const [sel, setSel] = useState(TIPOS[0].id);
  const tipo = TIPOS.find((t) => t.id === sel)!;

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ClipboardList size={22} style={{ color: "var(--dourado-light)" }} /> Lançamentos
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Entrada de dados direto no sistema — escolha o tipo de lançamento e preencha.
        </p>
      </div>

      {/* Aviso de rascunho */}
      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          <strong style={{ color: "var(--text)" }}>Tela em rascunho.</strong> Os campos abaixo são um ponto de partida para desenharmos juntos
          a forma final de cada lançamento. Por enquanto <strong>nada é gravado</strong> — me diga, para cada tipo, quais campos faltam,
          sobram ou devem mudar, e quais opções de escolha você usa na fazenda.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-4">
        {/* Lista de tipos */}
        <div className="card" style={{ padding: "0.5rem", alignSelf: "start" }}>
          <div className="space-y-1">
            {TIPOS.map((t) => {
              const Icon = t.icon; const ativo = t.id === sel;
              return (
                <button key={t.id} onClick={() => setSel(t.id)}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: "0.6rem",
                    padding: "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
                    border: "1px solid " + (ativo ? "var(--dourado)" : "transparent"),
                    background: ativo ? "rgba(94,26,46,0.4)" : "transparent",
                    color: ativo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.85rem", fontWeight: ativo ? 700 : 500,
                  }}>
                  <Icon size={16} /> {t.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Formulário do tipo selecionado */}
        <div className="card">
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {tipo.campos.map((c, i) => (
              <div key={i} style={{ gridColumn: c.larg === "full" ? "1 / -1" : undefined }}>
                <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>{c.label}</label>
                {c.tipo === "select" ? (
                  <select style={inputStyle} defaultValue="">
                    <option value="" disabled>Selecione…</option>
                    {(c.opcoes || []).map((o) => <option key={o}>{o}</option>)}
                  </select>
                ) : c.tipo === "textarea" ? (
                  <textarea style={{ ...inputStyle, minHeight: "3.5rem", resize: "vertical" }} placeholder={c.placeholder} />
                ) : (
                  <input type={c.tipo || "text"} style={inputStyle} placeholder={c.placeholder} inputMode={c.tipo === "number" ? "decimal" : undefined} />
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3 mt-4" style={{ flexWrap: "wrap" }}>
            <button className="btn-primary" disabled title="Ainda em desenvolvimento"
              style={{ opacity: 0.55, cursor: "not-allowed" }}>
              Salvar (em breve)
            </button>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              O salvamento entra quando ligarmos o banco de dados permanente e o login.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
