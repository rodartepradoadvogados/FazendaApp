"use client";
// Sub-tela: Agenda do Veterinário (só leitura, dentro do app).
// Abre APENAS as listas da classificação do rebanho fêmea — cada lista é uma
// seção recolhível (<details>) com nome amigável + contagem; dentro, os
// animais, clicáveis — abrem a ficha do animal aqui mesmo (estado local),
// com seta de voltar para esta mesma tela. Cada lista também traz exportação
// Excel/PDF e cada animal um botão para enviar o último DG por e-mail (#488/#489).
import { useState } from "react";
import { ChevronRight, Mail, Check, X } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchAgendaVeterinario, enviarDiagnosticoEmail, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, NumAnimal } from "@/components/mobile/menu/comum";
import { FichaDetalhe } from "@/components/mobile/rebanho/Ficha";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";

// Campos ordenáveis das listas da Agenda — nem toda lista preenche todos
// (ex.: só as "inseminadas" têm dias_inseminada), mas useOrdenacao já joga os
// valores nulos para o fim, então não há problema em oferecer o conjunto todo.
const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "numero_matriz", rotulo: "Matriz" },
  { chave: "dias_inseminada", rotulo: "Dias inseminada" },
  { chave: "dias_para_parto", rotulo: "Dias p/ parto" },
  { chave: "peso", rotulo: "Peso" },
  { chave: "data_servico", rotulo: "Data do serviço" },
];

type Animal = {
  numero_matriz: string;
  categoria?: string;
  peso?: number | null;
  dias_inseminada?: number | null;
  data_servico?: string | null;
  tocada?: boolean;
  reconfirmada?: boolean;
  atrasada?: boolean;
  dias_para_parto?: number | null;
  motivo?: string | null;
};
type Resposta = { data_referencia: string; listas: Record<string, Animal[]>; totais: Record<string, number> };

// Ordem e rótulos amigáveis das 10 listas (ver fazenda/rules/agenda_veterinario.py).
const LISTAS: { chave: string; rotulo: string }[] = [
  { chave: "inseminadas_1_29", rotulo: "Inseminadas 1–29 dias (aguardar toque)" },
  { chave: "inseminadas_30_59", rotulo: "Inseminadas 30–59 dias (tocar)" },
  { chave: "inseminadas_60_mais", rotulo: "Inseminadas 60+ dias (reconfirmar)" },
  { chave: "novilhas_aptas_vazias", rotulo: "Novilhas aptas e vazias (inseminar)" },
  { chave: "novilhas_gestantes", rotulo: "Novilhas gestantes" },
  { chave: "verificar_pre_parto", rotulo: "Pré-parto (verificar)" },
  { chave: "vacas_gestantes", rotulo: "Vacas gestantes" },
  { chave: "vazias_por_diagnostico", rotulo: "Vazias por diagnóstico (novo serviço)" },
  { chave: "pendentes_classificacao", rotulo: "Pendentes de classificação" },
  // Só aparece quando o parâmetro "usa_adesivo_deteccao_cio" está ativo.
  { chave: "observacao_cio", rotulo: "Observação de cio — adesivo de repasse" },
];

function detalhe(chave: string, a: Animal): string {
  if (a.motivo) return a.motivo;
  const partes: string[] = [];
  if (a.dias_para_parto != null) partes.push(`parto em ${a.dias_para_parto} dias`);
  if (a.dias_inseminada != null) partes.push(`${a.dias_inseminada} dias inseminada`);
  if (a.atrasada) partes.push("atrasada");
  if (!partes.length && a.data_servico) partes.push(`serviço ${formatDate(a.data_servico)}`);
  return partes.join(" · ");
}

function EnviarDgForm({ numero, onFeito, onCancelar }: { numero: string; onFeito: (msg: string) => void; onCancelar: () => void }) {
  const [email, setEmail] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const inputStyle: React.CSSProperties = { flex: 1, background: "var(--mob-surface-2)", color: "var(--mob-text)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };

  async function enviar() {
    if (!email.trim()) { setErro("Informe o e-mail."); return; }
    setEnviando(true); setErro(null);
    try {
      await enviarDiagnosticoEmail(numero, email.trim());
      onFeito(`Diagnóstico enviado (matriz ${numero}).`);
    } catch (e: any) { setErro(e.message); } finally { setEnviando(false); }
  }

  return (
    <div style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--mob-border)" }}>
      <div className="flex items-center gap-2">
        <input type="email" placeholder="e-mail do destinatário" style={inputStyle} value={email} onChange={(e) => setEmail(e.target.value)} />
        <button onClick={enviar} disabled={enviando} style={{ border: "none", background: "var(--mob-dourado-2)", color: "var(--mob-acao-fg)", borderRadius: "var(--r-app)", padding: "0.4rem 0.6rem" }}>
          <Check size={15} />
        </button>
        <button onClick={onCancelar} style={{ border: "1px solid var(--mob-border)", background: "transparent", color: "var(--mob-muted)", borderRadius: "var(--r-app)", padding: "0.4rem 0.6rem" }}>
          <X size={15} />
        </button>
      </div>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.3rem" }}>{erro}</p>}
    </div>
  );
}

function ListaSecao({ chave, rotulo, animais, enviandoDg, setEnviandoDg, onFichaAberta, onDgFeito }: {
  chave: string; rotulo: string; animais: Animal[];
  enviandoDg: string | null; setEnviandoDg: (n: string | null) => void;
  onFichaAberta: (numero: string) => void; onDgFeito: (msg: string) => void;
}) {
  const ord = useOrdenacao(animais);
  const colunasExport = [
    { header: "Matriz", key: "numero_matriz" }, { header: "Categoria", key: "categoria" },
    { header: "Peso (kg)", key: "peso" }, { header: "Dias insem.", key: "dias_inseminada" },
    { header: "Data serviço", key: "data_servico_fmt" }, { header: "Detalhe", key: "detalhe_fmt" },
  ];
  const linhasExport = ord.linhasOrdenadas.map((a) => ({
    ...a, data_servico_fmt: a.data_servico ? formatDate(a.data_servico) : "—", detalhe_fmt: detalhe(chave, a),
  }));

  return (
    <details className="mob-card mob-card-vet" style={{ padding: "0.4rem 0.9rem", marginBottom: "0.6rem" }}>
      <summary style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", cursor: "pointer", padding: "0.55rem 0", fontWeight: 700, fontSize: "0.95rem", listStyle: "none" }}>
        <span style={{ flex: 1, minWidth: 0 }}>{rotulo}</span>
        <span style={{ fontSize: "0.78rem", fontWeight: 800, padding: "0.2rem 0.6rem", borderRadius: 999, background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", color: "var(--mob-muted)", flexShrink: 0 }}>
          {animais.length}
        </span>
      </summary>
      <div style={{ borderTop: "1px solid var(--mob-border)", paddingTop: "0.4rem" }}>
        <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
        <div className="flex items-center justify-end mb-2">
          <ExportarBotoes titulo={`Agenda Reprodutiva — ${rotulo}`} colunas={colunasExport} linhas={linhasExport} nomeArquivoBase={`agenda_veterinario_${chave}`} />
        </div>
        {ord.linhasOrdenadas.map((a) => (
          <div key={a.numero_matriz}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", padding: "0.5rem 0", borderBottom: enviandoDg === a.numero_matriz ? "none" : "1px solid var(--mob-border)" }}>
              <button onClick={() => onFichaAberta(a.numero_matriz)}
                style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0, background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", textAlign: "left", font: "inherit" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <NumAnimal>Nº {a.numero_matriz}</NumAnimal>
                  <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{detalhe(chave, a)}</div>
                </div>
                <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
              </button>
              <button onClick={() => setEnviandoDg(enviandoDg === a.numero_matriz ? null : a.numero_matriz)}
                title="Enviar último diagnóstico de gestação por e-mail"
                style={{ border: "1px solid var(--mob-border)", background: "transparent", color: "var(--mob-muted)", borderRadius: "var(--r-app)", padding: "0.35rem", flexShrink: 0 }}>
                <Mail size={16} />
              </button>
            </div>
            {enviandoDg === a.numero_matriz && (
              <EnviarDgForm numero={a.numero_matriz} onFeito={(msg) => { setEnviandoDg(null); onDgFeito(msg); }} onCancelar={() => setEnviandoDg(null)} />
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

export default function AgendaVet({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_agenda_vet", fetchAgendaVeterinario);
  const [fichaAberta, setFichaAberta] = useState<string | null>(null);
  const [enviandoDg, setEnviandoDg] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const total = dados ? Object.values(dados.totais || {}).reduce((s, n) => s + n, 0) : 0;

  if (fichaAberta) return <FichaDetalhe numero={fichaAberta} onVoltar={() => setFichaAberta(null)} />;

  return (
    <div>
      <MobVoltar titulo="Agenda Reprodutiva" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_agenda_vet" mostrar={doCache} />
      {sucesso && (
        <div className="mb-2" style={{ background: "color-mix(in srgb, var(--green-light) 15%, transparent)", border: "1px solid var(--green-light)", borderRadius: "var(--r-app)", padding: "0.5rem 0.8rem", color: "var(--green-light)", fontSize: "0.82rem" }}>
          {sucesso}
        </div>
      )}

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : total === 0 ? (
        <Vazio>Nenhum animal a acompanhar no momento 🎉</Vazio>
      ) : (
        LISTAS.map(({ chave, rotulo }) => {
          const animais = dados.listas[chave] || [];
          if (!animais.length) return null;
          return (
            <ListaSecao key={chave} chave={chave} rotulo={rotulo} animais={animais}
              enviandoDg={enviandoDg} setEnviandoDg={setEnviandoDg}
              onFichaAberta={setFichaAberta} onDgFeito={setSucesso} />
          );
        })
      )}
    </div>
  );
}
