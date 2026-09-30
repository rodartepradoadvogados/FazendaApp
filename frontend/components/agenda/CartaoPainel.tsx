"use client";

import React from "react";
import { ChevronRight } from "lucide-react";

/**
 * Cartão compacto do Painel (mockup fluxo-completo: ~72 px, 6 por linha no
 * desktop, 2 no celular). Título completo, sem cortar (quebra de linha), valor
 * grande e uma linha de detalhe. Clicável quando recebe `onClick` ou `href`.
 * A cor da categoria vem da faixa lateral (--cat-*), nunca só da cor: o ícone e
 * o texto dizem do que se trata.
 */
export function CartaoPainel({
  titulo, valor, detalhe, cor = "var(--dourado)", icon: Icon, onClick, href, aberto, alerta, desligado, titleAttr, id,
}: {
  titulo: string;
  valor: React.ReactNode;
  detalhe?: React.ReactNode;
  cor?: string;
  icon?: any;
  onClick?: () => void;
  href?: string;
  /** Lista associada aberta (aria-expanded). */
  aberto?: boolean;
  alerta?: boolean;
  /** Regra desligada: valor em texto, cartão em tom neutro. */
  desligado?: boolean;
  titleAttr?: string;
  id?: string;
}) {
  const conteudo = (
    <>
      <span className="ag2-cartao-topo">
        {Icon && <Icon size={15} aria-hidden="true" style={{ color: cor, flexShrink: 0 }} />}
        <span className="ag2-cartao-titulo">{titulo}</span>
      </span>
      <span className={"ag2-valor" + (desligado ? " ag2-valor-neutro" : "") + (alerta ? " ag2-valor-alerta" : "")}>{valor}</span>
      {detalhe != null && <span className="ag2-cartao-detalhe">{detalhe}</span>}
      {(onClick || href) && <ChevronRight size={14} aria-hidden="true" className="ag2-cartao-seta" />}
    </>
  );
  const estilo = { ["--ag2-cat" as any]: cor } as React.CSSProperties;
  if (href) return <a id={id} href={href} className="ag2-cartao" style={estilo} title={titleAttr}>{conteudo}</a>;
  if (onClick) return <button id={id} type="button" className="ag2-cartao" style={estilo} onClick={onClick} aria-expanded={aberto} title={titleAttr}>{conteudo}</button>;
  return <div id={id} className="ag2-cartao ag2-cartao-estatico" style={estilo} title={titleAttr}>{conteudo}</div>;
}

export function GrupoPainel({ titulo, cor, children }: { titulo: string; cor: string; children: React.ReactNode }) {
  return (
    <section className="ag2-grupo" aria-label={titulo}>
      <h2 className="ag2-grupo-titulo"><span className="ag2-grupo-marca" style={{ background: cor }} aria-hidden="true" />{titulo}</h2>
      <div className="ag2-grade-cartoes">{children}</div>
    </section>
  );
}
