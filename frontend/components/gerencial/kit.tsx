"use client";
// Kit "gerencial" das telas de Lançamentos — a língua do Diagnóstico de gestação (components/lancamentos/FormDiagnostico.tsx)
// em peças reutilizáveis: passos numerados, faixa de números, selos de situação, barra fixa de ação (resumo + retorno do
// último salvamento + botão em ouro). Estilo em app/globals.css (classes .gv-*), só com tokens. Estas peças são só
// apresentação: quem salva, valida e chama a API continua sendo cada formulário (e as props de injeção do app de campo).
import React from "react";
import { X } from "lucide-react";

/** Moldura da gaveta de lançamento, para o corpo de cada tela (na tela real vem de GavetaLancamento). */
export function QuadroGaveta({ titulo, icone: Icone, largura = 860, children }: {
  titulo: string; icone?: React.ComponentType<{ size?: number | string }>; largura?: number | string; children: React.ReactNode;
}) {
  return (
    <div className="gv-quadro" style={{ ["--gv-largura" as string]: typeof largura === "number" ? `${largura}px` : largura }}>
      <div className="gv-quadro-topo">
        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>{Icone && <Icone size={15} />}{titulo}</span>
        <X size={16} aria-hidden="true" />
      </div>
      <div className="gv-corpo">{children}</div>
    </div>
  );
}

export function Passo({ n, id, titulo, direita, children }: { n: number; id: string; titulo: string; direita?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="gv-passo" aria-labelledby={id}>
      <div className="gv-passo-topo">
        <div id={id} className="gv-rotulo"><span className="gv-n" aria-hidden="true">{n}</span>{titulo}</div>
        {direita}
      </div>
      {children}
    </section>
  );
}

export type ItemFaixa = { rotulo: string; valor: React.ReactNode; tom?: "ok" | "atencao" | "alerta" };
/** Faixa de números no topo da tela: o "estado do mundo" antes de lançar (gerencial: o número antes do formulário). */
export function Faixa({ itens }: { itens: ItemFaixa[] }) {
  return (
    <div className="gv-faixa" role="group" aria-label="Resumo">
      {itens.map((i) => (
        <div key={i.rotulo} className="gv-faixa-item" data-tom={i.tom}>
          <span className="gv-faixa-valor">{i.valor}</span><span className="gv-faixa-rotulo">{i.rotulo}</span>
        </div>
      ))}
    </div>
  );
}

/** Grupo de pílulas (uma escolha ou várias) com contagem opcional — mesmo `.ft-pilula` do Diagnóstico. */
export function Pilulas<T extends string>({ rotulo, opcoes, valor, onChange }: {
  rotulo: string; opcoes: { id: T; nome: string; n?: number; titulo?: string }[]; valor: T | readonly T[]; onChange?: (id: T) => void;
}) {
  const ativo = (id: T) => (Array.isArray(valor) ? (valor as readonly T[]).includes(id) : valor === id);
  return (
    <div className="gv-linha" role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" className="ft-pilula" aria-pressed={ativo(o.id)} title={o.titulo} onClick={() => onChange?.(o.id)}>
          {o.nome}{o.n != null && <b>{o.n}</b>}
        </button>
      ))}
    </div>
  );
}

export function Selo({ tom = "neutro", children, titulo }: { tom?: "ok" | "atencao" | "bloqueio" | "info" | "neutro"; children: React.ReactNode; titulo?: string }) {
  return <span className="gv-selo" data-tom={tom} title={titulo}>{children}</span>;
}

export function Campo({ rotulo, id, children }: { rotulo: string; id: string; children: React.ReactElement<{ id?: string }> }) {
  return (
    <div className="gv-campo">
      <label htmlFor={id}>{rotulo}</label>
      {React.cloneElement(children, { id })}
    </div>
  );
}

export function Aviso({ tom, children }: { tom?: "erro"; children: React.ReactNode }) {
  return <div className="gv-aviso" role={tom === "erro" ? "alert" : "status"} data-tom={tom}>{children}</div>;
}

export function Ajuda({ children }: { children: React.ReactNode }) {
  return <p className="gv-ajuda">{children}</p>;
}

/** Barra fixa do pé: o que vai ser salvo (resumo), o retorno do último salvamento e o botão em ouro (ouro = ação). */
export function BarraAcao({ resumo, detalhe, retorno, acao, secundaria }: {
  resumo: React.ReactNode; detalhe?: React.ReactNode; retorno?: React.ReactNode; acao: React.ReactNode; secundaria?: React.ReactNode;
}) {
  return (
    <div className="gv-barra">
      {retorno && <div className="gv-barra-retorno" aria-live="polite">{retorno}</div>}
      <div className="gv-barra-miolo">
        <div className="gv-barra-resumo" aria-live="polite"><b>{resumo}</b>{detalhe && <span>{detalhe}</span>}</div>
        <span className="gv-espaco" />
        {secundaria}
        {acao}
      </div>
    </div>
  );
}

export function BotaoOuro({ children, desabilitado, ...resto }: React.ButtonHTMLAttributes<HTMLButtonElement> & { desabilitado?: boolean }) {
  return <button type="button" className="btn-primary-gold" disabled={desabilitado} {...resto}>{children}</button>;
}

/** Moldura de captura das propostas (só nas rotas de prévia): fundo da página e largura da área, para a imagem sair idêntica ao app. */
export function Captura({ largura = 1320, children }: { largura?: number; children: React.ReactNode }) {
  return (
    <div id="captura" style={{ background: "var(--bg)", padding: 24, width: largura + 48, boxSizing: "border-box", color: "var(--text)" }}>
      {children}
    </div>
  );
}
