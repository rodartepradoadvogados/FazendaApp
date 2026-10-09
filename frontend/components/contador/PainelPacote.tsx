"use client";
// Painel do Contador › Pacote do contador (Fase C5). O mesmo pacote de
// Relatórios › Entrega ao contador (GET /financeiro/pacote-contador, só
// leitura — o vínculo `contador` lê e baixa, não escreve), com o período do
// próprio painel. A lista e os botões são os da tela dos Relatórios
// (ListaPacote); aqui só se traduz o vocabulário de tokens para a paleta do painel.
import { useEffect, useState, type CSSProperties } from "react";
import { fetchPacoteContador, type PacoteResumo } from "@/lib/fechamentoApi";
import { CSS_ENTREGA } from "@/components/financeiro/relatorios/estilosEntrega";
import { ListaPacote } from "@/components/financeiro/relatorios/entregaComum";
import { CORES_CONTADOR as C } from "@/app/contador/layout";

const TOKENS = {
  "--text": C.texto, "--text-muted": C.mudo, "--surface": C.painel, "--surface-2": C.painelAlt,
  "--border": C.borda, "--border-strong": C.bordaClara, "--text-accent": C.cobreClaro,
  "--pill-active-bg": C.cobre, "--pill-active-fg": "#fff", "--pill-active-border": C.cobre,
} as CSSProperties;

const br = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

export function PainelPacote({ inicio, fim }: { inicio: string; fim: string }) {
  const chave = `${inicio}~${fim}`;
  const [res, setRes] = useState<{ chave: string; dados: PacoteResumo | null; erro: string | null } | null>(null);
  useEffect(() => {
    let vivo = true;
    if (!inicio || !fim) return;
    fetchPacoteContador(inicio, fim)
      .then((d) => { if (vivo) setRes({ chave: `${inicio}~${fim}`, dados: d, erro: null }); })
      .catch((e) => { if (vivo) setRes({ chave: `${inicio}~${fim}`, dados: null, erro: (e as Error).message }); });
    return () => { vivo = false; };
  }, [inicio, fim]);
  const atual = res && res.chave === chave ? res : null;
  const dados = atual?.dados ?? null;
  const erro = atual?.erro ?? null;
  return (
    <div style={{ ...TOKENS, background: C.painel, border: `1px solid ${C.borda}`, borderRadius: "var(--r-sm)", padding: "1rem 1.1rem" }}>
      <style>{CSS_ENTREGA}</style>
      <p style={{ margin: "0 0 .8rem", fontSize: ".85rem", color: C.mudo }}>
        Pacote de {br(inicio)} a {br(fim)}: DRE (mês do gasto e dia do pagamento), livro caixa da atividade rural, lançamentos sem
        classificação, pendências do fechamento, patrimônio e depreciação, conciliação e o apoio ao LCDPR — em PDF, Excel e CSV.
      </p>
      {erro && <p role="alert" style={{ color: C.negativo, margin: 0 }}>{erro}</p>}
      {!dados && !erro && <p style={{ color: C.mudo, margin: 0 }} role="status">Montando o pacote…</p>}
      {dados && <ListaPacote itens={dados.itens} inicio={inicio} fim={fim} />}
      {dados && (
        <p style={{ margin: ".8rem 0 0", fontSize: ".76rem", color: C.mudo }}>
          {dados.cabecalho.fazenda}{dados.cabecalho.documento ? ` · ${dados.cabecalho.documento}` : ""} · regras {dados.cabecalho.regras_v2 ? "novas" : "antigas"} dos relatórios ·
          a nota de método vai dentro do pacote (LEIA-ME.txt).
        </p>
      )}
    </div>
  );
}
