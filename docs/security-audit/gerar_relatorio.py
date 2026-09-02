#!/usr/bin/env python3
"""
Gera o relatório de auditoria de segurança em PDF a partir de achados.json.

Uso:
    .venv/bin/python gerar_relatorio.py

Lê achados.json (mesma pasta) e escreve relatorio-auditoria-seguranca.pdf.
Regenere depois de editar achados.json.
"""
from __future__ import annotations

import json
import os
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Image, NextPageTemplate, PageBreak, KeepTogether, HRFlowable,
)
from reportlab.pdfgen import canvas as pdfcanvas

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "achados.json")
OUT_PATH = os.path.join(HERE, "relatorio-auditoria-seguranca.pdf")

# ---------------------------------------------------------------------------
# Paleta (pedida pelo usuário)
# ---------------------------------------------------------------------------
COR = {
    "critica": colors.HexColor("#B91C1C"),
    "alta": colors.HexColor("#EA580C"),
    "media": colors.HexColor("#D97706"),
    "baixa": colors.HexColor("#2563EB"),
    "informativa": colors.HexColor("#6B7280"),
    "ponto_forte": colors.HexColor("#059669"),
    "texto": colors.HexColor("#1F2937"),
    "muted": colors.HexColor("#6B7280"),
    "fundo_claro": colors.HexColor("#F3F4F6"),
    "linha": colors.HexColor("#D1D5DB"),
    "faixa": colors.HexColor("#0F172A"),
}
SEVERIDADE_ORDEM = ["critica", "alta", "media", "baixa", "informativa"]
SEVERIDADE_LABEL = {
    "critica": "Crítica", "alta": "Alta", "media": "Média",
    "baixa": "Baixa", "informativa": "Informativa",
}

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Titulo1", fontSize=22, leading=26, textColor=COR["texto"], fontName="Helvetica-Bold", spaceAfter=6))
styles.add(ParagraphStyle(name="Subtitulo", fontSize=12, leading=16, textColor=COR["muted"], fontName="Helvetica"))
styles.add(ParagraphStyle(name="H2", fontSize=15, leading=19, textColor=COR["texto"], fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=8))
styles.add(ParagraphStyle(name="H3", fontSize=11.5, leading=15, textColor=COR["texto"], fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle(name="Corpo", fontSize=9.3, leading=13.2, textColor=COR["texto"], fontName="Helvetica", alignment=TA_LEFT))
styles.add(ParagraphStyle(name="CorpoMuted", fontSize=8.8, leading=12.5, textColor=COR["muted"], fontName="Helvetica"))
styles.add(ParagraphStyle(name="Codigo", fontSize=7.6, leading=10.2, textColor=COR["texto"], fontName="Courier", backColor=COR["fundo_claro"], borderPadding=(4, 6, 4, 6)))
styles.add(ParagraphStyle(name="Celula", fontSize=8.4, leading=11.2, textColor=COR["texto"], fontName="Helvetica"))
styles.add(ParagraphStyle(name="CelulaMono", fontSize=7.8, leading=10.6, textColor=COR["texto"], fontName="Courier"))
styles.add(ParagraphStyle(name="Rodape", fontSize=7.6, textColor=COR["muted"]))
styles.add(ParagraphStyle(name="IssueTitulo", fontSize=10.5, leading=14, textColor=COR["texto"], fontName="Helvetica-Bold"))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def severidade_chip(sev: str) -> Table:
    sev = sev or "informativa"
    cor = COR.get(sev, COR["informativa"])
    t = Table([[SEVERIDADE_LABEL.get(sev, sev.title())]], colWidths=[2.2 * cm], rowHeights=[0.48 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.6),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


# ---------------------------------------------------------------------------
# Cabeçalho / rodapé
# ---------------------------------------------------------------------------
REPORT_NAME = "Relatório de Auditoria de Segurança — FazendaApp"


def _header_footer(cnv: pdfcanvas.Canvas, doc):
    cnv.saveState()
    cnv.setStrokeColor(COR["linha"])
    cnv.setLineWidth(0.6)
    if doc.page > 1:
        cnv.line(MARGIN, PAGE_H - 1.35 * cm, PAGE_W - MARGIN, PAGE_H - 1.35 * cm)
        cnv.setFont("Helvetica", 8)
        cnv.setFillColor(COR["muted"])
        cnv.drawString(MARGIN, PAGE_H - 1.2 * cm, REPORT_NAME)
    cnv.line(MARGIN, 1.35 * cm, PAGE_W - MARGIN, 1.35 * cm)
    cnv.setFont("Helvetica", 8)
    cnv.setFillColor(COR["muted"])
    cnv.drawRightString(PAGE_W - MARGIN, 1.0 * cm, f"Página {doc.page}")
    cnv.drawString(MARGIN, 1.0 * cm, "FazendaApp · Auditoria de Segurança · Confidencial")
    cnv.restoreState()


def _cover_canvas(cnv: pdfcanvas.Canvas, doc):
    cnv.saveState()
    cnv.setFillColor(COR["faixa"])
    cnv.rect(0, PAGE_H - 7.6 * cm, PAGE_W, 7.6 * cm, stroke=0, fill=1)
    cnv.restoreState()


def build(data: dict):
    achados = data["achados"]
    pontos_fortes = data.get("pontos_fortes", [])
    incertos = data.get("incertos", [])
    meta = data["meta"]
    recomendacoes = data.get("recomendacoes", [])
    issues = data.get("issues", [])

    # ---- gráficos ----
    sev_count = Counter(a["severidade"] for a in achados)
    ordered = [s for s in SEVERIDADE_ORDEM if sev_count.get(s)]
    donut_path = os.path.join(HERE, "_chart_donut.png")
    if ordered:
        fig, ax = plt.subplots(figsize=(3.6, 3.6), dpi=200)
        vals = [sev_count[s] for s in ordered]
        cols = [COR[s].hexval()[2:] for s in ordered]
        cols = [f"#{c}" for c in cols]
        wedges, _texts, autotexts = ax.pie(
            vals, colors=cols, startangle=90, counterclock=False,
            wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
            autopct=lambda p: f"{round(p * sum(vals) / 100.0)}", pctdistance=0.79,
        )
        for at in autotexts:
            at.set_color("white")
            at.set_fontsize(11)
            at.set_fontweight("bold")
        ax.legend(wedges, [f"{SEVERIDADE_LABEL[s]} ({sev_count[s]})" for s in ordered],
                   loc="center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False, fontsize=8.5)
        ax.set_title("Achados por severidade", fontsize=11, fontweight="bold", color="#1F2937", pad=10)
        fig.tight_layout()
        fig.savefig(donut_path, transparent=True)
        plt.close(fig)
    else:
        donut_path = None

    cat_count = Counter(a["categoria_label"] for a in achados)
    bar_path = os.path.join(HERE, "_chart_bar.png")
    if cat_count:
        cats = list(cat_count.keys())
        fig, ax = plt.subplots(figsize=(6.0, 3.6), dpi=200)
        y = range(len(cats))
        bar_colors = []
        for c in cats:
            worst = min((a["severidade"] for a in achados if a["categoria_label"] == c),
                        key=lambda s: SEVERIDADE_ORDEM.index(s))
            bar_colors.append(f"#{COR[worst].hexval()[2:]}")
        ax.barh(list(y), [cat_count[c] for c in cats], color=bar_colors, height=0.55)
        ax.set_yticks(list(y))
        ax.set_yticklabels(cats, fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Nº de achados", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
        for i, c in enumerate(cats):
            ax.text(cat_count[c] + 0.05, i, str(cat_count[c]), va="center", fontsize=9, color="#1F2937")
        ax.set_title("Achados por categoria", fontsize=11, fontweight="bold", color="#1F2937", pad=10)
        fig.tight_layout()
        fig.savefig(bar_path, transparent=True)
        plt.close(fig)
    else:
        bar_path = None

    # ---- doc ----
    doc = BaseDocTemplate(OUT_PATH, pagesize=A4,
                           leftMargin=MARGIN, rightMargin=MARGIN,
                           topMargin=2.0 * cm, bottomMargin=1.8 * cm)
    frame_normal = Frame(MARGIN, 1.8 * cm, PAGE_W - 2 * MARGIN, PAGE_H - 2.0 * cm - 1.8 * cm, id="normal")
    frame_cover = Frame(MARGIN, 1.8 * cm, PAGE_W - 2 * MARGIN, PAGE_H - 1.8 * cm - 1.8 * cm, id="cover")
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[frame_cover], onPage=_cover_canvas),
        PageTemplate(id="Normal", frames=[frame_normal], onPage=_header_footer),
    ])

    story = []

    # ---- Capa ----
    story.append(Spacer(1, 1.4 * cm))
    story.append(Paragraph('<font color="white" size="10">RELATÓRIO CONFIDENCIAL</font>', ParagraphStyle("c1", fontName="Helvetica-Bold")))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(f'<font color="white" size="25"><b>Relatório de Auditoria de<br/>Segurança</b></font>', ParagraphStyle("c2", leading=30)))
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph(f'<font color="#93C5FD" size="15">{_esc(meta["projeto"])}</font>', ParagraphStyle("c3")))
    story.append(Spacer(1, 3.6 * cm))
    story.append(Paragraph(f"<b>Data:</b> {_esc(meta['data'])}", styles["Corpo"]))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(f"<b>Escopo:</b> {_esc(meta['escopo'])}", styles["Corpo"]))
    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("<b>Nota metodológica — mapeamento das categorias para esta stack</b>", styles["H3"]))
    for linha in meta["metodologia"]:
        story.append(Paragraph(f"• {_esc(linha)}", styles["Corpo"]))
    story.append(NextPageTemplate("Normal"))
    story.append(PageBreak())

    # ---- Resumo executivo ----
    story.append(Paragraph("Resumo executivo", styles["Titulo1"]))
    total = len(achados)
    resumo_txt = (f"Foram revisados sistematicamente {meta['rotas_revisadas']} handlers de rota, "
                  f"em {meta['arquivos_revisados']} arquivos de backend, mais o frontend e a configuração "
                  f"de segredos/deploy. Este relatório registra {total} achado(s) acionável(is) e "
                  f"{len(pontos_fortes)} pontos fortes verificados (evidência de cobertura da auditoria).")
    story.append(Paragraph(resumo_txt, styles["Corpo"]))
    story.append(Spacer(1, 0.3 * cm))

    resumo_tbl_data = [["Severidade", "Qtd."]]
    for s in SEVERIDADE_ORDEM:
        if sev_count.get(s):
            resumo_tbl_data.append([SEVERIDADE_LABEL[s], str(sev_count[s])])
    resumo_tbl_data.append(["Total", str(total)])
    resumo_tbl = Table(resumo_tbl_data, colWidths=[4.2 * cm, 2 * cm])
    tbl_style = [
        ("BACKGROUND", (0, 0), (-1, 0), COR["faixa"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, COR["linha"]),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, COR["fundo_claro"]]),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    resumo_tbl.setStyle(TableStyle(tbl_style))

    imgs = []
    if donut_path:
        imgs.append(Image(donut_path, width=7.4 * cm, height=7.4 * cm))
    charts_row = []
    if imgs:
        charts_row.append(imgs[0])
    left_col = [resumo_tbl]
    if charts_row:
        two_col = Table([[left_col[0], charts_row[0]]], colWidths=[7 * cm, 8.5 * cm])
        two_col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(two_col)
    else:
        story.append(resumo_tbl)
    story.append(Spacer(1, 0.4 * cm))
    if bar_path:
        story.append(Image(bar_path, width=15.5 * cm, height=9.3 * cm))

    story.append(PageBreak())

    # ---- Pontos fortes / fracos ----
    story.append(Paragraph("Pontos fortes", styles["H2"]))
    story.append(Paragraph(
        "O que foi verificado no código e está corretamente protegido — evidência direta de cobertura da auditoria "
        "(cada item cita onde a proteção foi conferida).", styles["CorpoMuted"]))
    story.append(Spacer(1, 0.2 * cm))
    for pf in pontos_fortes:
        p = Table([[Paragraph(f"<b>{_esc(pf['titulo'])}</b><br/><font color='#6B7280' size='7.6'>{_esc(pf['ref'])}</font><br/>{_esc(pf['descricao'])}", styles["Corpo"])]],
                   colWidths=[16.8 * cm])
        p.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, COR["ponto_forte"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
        ]))
        story.append(p)
        story.append(Spacer(1, 0.16 * cm))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Pontos fracos — riscos centrais", styles["H2"]))
    for linha in meta.get("riscos_centrais", []):
        story.append(Paragraph(f"• {_esc(linha)}", styles["Corpo"]))

    story.append(PageBreak())

    # ---- Achados detalhados por categoria ----
    story.append(Paragraph("Achados detalhados", styles["Titulo1"]))
    categorias = []
    for a in achados:
        if a["categoria_label"] not in categorias:
            categorias.append(a["categoria_label"])
    for cat in categorias:
        story.append(Paragraph(cat, styles["H2"]))
        for a in [x for x in achados if x["categoria_label"] == cat]:
            head = Table([[severidade_chip(a["severidade"]),
                            Paragraph(f"<b>{_esc(a['titulo'])}</b>", styles["Celula"]),
                            Paragraph(f"<font color='#6B7280'>{_esc(a['local'])}</font>", styles["CelulaMono"])]],
                          colWidths=[2.3 * cm, 8.3 * cm, 6.2 * cm])
            head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            block = [head]
            block.append(Paragraph(_esc(a["descricao"]), styles["Corpo"]))
            if a.get("trecho"):
                trecho = _esc(a["trecho"]).replace("\n", "<br/>")
                block.append(Spacer(1, 0.08 * cm))
                block.append(Paragraph(trecho, styles["Codigo"]))
            block.append(Spacer(1, 0.05 * cm))
            block.append(HRFlowable(width="100%", thickness=0.4, color=COR["linha"], spaceBefore=6, spaceAfter=10))
            story.append(KeepTogether(block))

    if incertos:
        story.append(PageBreak())
        story.append(Paragraph("Itens incertos (necessitam confirmação humana)", styles["H2"]))
        for it in incertos:
            story.append(Paragraph(f"<b>{_esc(it['local'])}</b> — {_esc(it['descricao'])}", styles["Corpo"]))
            story.append(Spacer(1, 0.15 * cm))

    story.append(PageBreak())

    # ---- Recomendações ----
    story.append(Paragraph("Recomendações priorizadas", styles["Titulo1"]))
    for bloco in recomendacoes:
        story.append(Paragraph(bloco["prioridade"], styles["H2"]))
        for item in bloco["itens"]:
            story.append(Paragraph(f"• {_esc(item)}", styles["Corpo"]))
        story.append(Spacer(1, 0.15 * cm))

    # ---- Issues para GitHub ----
    story.append(PageBreak())
    story.append(Paragraph("Issues para o GitHub", styles["Titulo1"]))
    story.append(Paragraph(
        "Texto completo em Markdown, pronto para copiar e colar na criação de cada issue.",
        styles["CorpoMuted"]))
    story.append(Spacer(1, 0.3 * cm))
    for i, issue in enumerate(issues, start=1):
        story.append(Paragraph(f"--- ISSUE {i} ---", styles["CorpoMuted"]))
        story.append(Spacer(1, 0.08 * cm))
        md = issue["markdown"]
        # Render as monospace preformatted block, preserving line breaks.
        safe = _esc(md).replace("\n", "<br/>")
        story.append(Paragraph(safe, styles["Codigo"]))
        story.append(Spacer(1, 0.08 * cm))
        story.append(Paragraph(f"--- FIM ISSUE {i} ---", styles["CorpoMuted"]))
        story.append(Spacer(1, 0.35 * cm))

    doc.build(story)
    print(f"OK: {OUT_PATH}")


if __name__ == "__main__":
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    build(data)
