"""E2E (Playwright/Chromium) da janela TRAVADA do Financeiro — gaveta "Dar baixa".

Prova, em navegador de verdade:
  1. a gaveta abre com ~1120 px a 1440 px de tela (o dobro dos 560 px do painel antigo);
  2. clicar no fundo escurecido (scrim) NÃO fecha;
  3. Esc NÃO fecha;
  4. com um campo já alterado, o X pede confirmação (cancelar mantém aberta, confirmar fecha);
  5. o X fecha (formulário limpo, sem pergunta);
  6. a 390 px a gaveta ocupa a tela toda, sem rolagem horizontal;
  7. o mesmo vale para um Modal travado (Patrimônio › Baixar do ativo, ~1120 px): Esc não
     fecha, o X fecha;
  8. Esc aninhado: um Modal aberto dentro de uma gaveta (Lançamentos › Sanitário ›
     Protocolo sanitário › abrir lançamento › "Novo") fecha sozinho no 1º Esc, e a gaveta só
     fecha no 2º; e o seletor de animais do Protocolo IATF (overlay próprio) idem.

Como rodar (banco descartável, nunca o real):
  backend:  DATABASE_URL=sqlite:////tmp/fin.db ALLOWED_ORIGINS=http://localhost:3110 \\
            python -m uvicorn main:app --port 8110        (em backend/, banco semeado com
            um lançamento a pagar em aberto e o usuário teste_local)
  frontend: NEXT_PUBLIC_API_URL=http://localhost:8110 npx next dev --webpack -p 3110   (em frontend/)
  teste:    python3 e2e/janela_travada.py
Variáveis opcionais: E2E_FRONT, E2E_API, E2E_USER, E2E_SENHA.
"""
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

FRONT = os.environ.get("E2E_FRONT", "http://localhost:3110")
API = os.environ.get("E2E_API", "http://localhost:8110")
USUARIO = os.environ.get("E2E_USER", "teste_local")
SENHA = os.environ.get("E2E_SENHA", "")
if not SENHA:
    sys.exit("defina E2E_SENHA (senha do usuário do banco descartável)")

DIALOGO_BAIXA = '[role=dialog][aria-label^="Dar baixa"]'
falhas = []


def confere(ok, msg):
    print(("OK    " if ok else "FALHA ") + msg)
    if not ok:
        falhas.append(msg)


def login():
    req = urllib.request.Request(
        API + "/auth/login",
        data=json.dumps({"username": USUARIO, "senha": SENHA}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))


def criar_patrimonio():
    """Item de patrimônio para ter o que "baixar" (API do banco descartável)."""
    d = login()
    req = urllib.request.Request(
        API + "/financeiro/patrimonio",
        data=json.dumps({"nome": "Ordenhadeira E2E", "tipo": "Máquinas e equipamentos", "data_imobilizacao": "2026-01-10",
                         "quantidade": 1, "valor_total": 5000, "depreciavel": False}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + d["token"]},
    )
    urllib.request.urlopen(req).read()


def contexto(browser, largura, altura):
    d = login()
    c = browser.new_context(viewport={"width": largura, "height": altura})
    c.add_init_script(f"""localStorage.setItem('token', {json.dumps(d['token'])});
      localStorage.setItem('usuario', {json.dumps(json.dumps(d['usuario']))});
      localStorage.setItem('fazenda_atual', {json.dumps(json.dumps(d['fazenda_atual']))});
      localStorage.setItem('conta_ativa','1'); localStorage.setItem('tema','claro'); localStorage.setItem('paleta','vinho');""")
    return c


def abrir_baixa(pg):
    pg.goto(FRONT + "/financeiro?ir=a_pagar", timeout=240000)
    pg.wait_for_selector("text=Dar baixa", timeout=120000)
    pg.wait_for_timeout(800)
    botao = pg.get_by_role("button", name="Dar baixa").first
    botao.scroll_into_view_if_needed()
    botao.click()
    pg.wait_for_selector(DIALOGO_BAIXA, timeout=10000)
    pg.wait_for_timeout(600)  # fim da animação de entrada


POLITICA = {"acao": "dismiss"}
PERGUNTAS = []


def ao_dialogo(d):
    """window.confirm da página: registra a pergunta e responde conforme POLITICA."""
    PERGUNTAS.append(d.message)
    d.accept() if POLITICA["acao"] == "accept" else d.dismiss()


def aberta(pg):
    return pg.locator(DIALOGO_BAIXA).count() > 0


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ── desktop 1440 ────────────────────────────────────────────────────
    pg = contexto(browser, 1440, 900).new_page()
    pg.on("dialog", ao_dialogo)
    abrir_baixa(pg)
    caixa = pg.locator(DIALOGO_BAIXA).bounding_box()
    confere(abs(caixa["width"] - 1120) <= 2, f"largura a 1440 px = {round(caixa['width'])} (esperado ~1120)")
    confere(pg.locator(DIALOGO_BAIXA).get_attribute("aria-modal") == "true", "role=dialog com aria-modal")
    confere(pg.evaluate("document.activeElement && document.activeElement.closest('[role=dialog]') !== null"),
            "foco foi para dentro da gaveta ao abrir")

    pg.mouse.click(120, 600)  # sobre o scrim (a esquerda da gaveta)
    pg.wait_for_timeout(500)
    confere(aberta(pg), "clique no scrim NÃO fecha")

    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)
    confere(aberta(pg), "Esc NÃO fecha")

    # Tab não escapa da gaveta
    for _ in range(40):
        pg.keyboard.press("Tab")
    confere(pg.evaluate("document.activeElement.closest('[role=dialog]') !== null"), "foco preso: 40 Tabs não saem da gaveta")

    # formulário sujo: o X pergunta
    pg.locator(f"{DIALOGO_BAIXA} input[type=text]").first.fill("12345")
    PERGUNTAS.clear(); POLITICA["acao"] = "dismiss"
    pg.locator(f'{DIALOGO_BAIXA} button[aria-label="Fechar"]').click()
    pg.wait_for_timeout(500)
    confere(len(PERGUNTAS) == 1 and aberta(pg), "X com campo alterado pergunta; 'cancelar' mantém aberta")
    POLITICA["acao"] = "accept"
    pg.locator(f'{DIALOGO_BAIXA} button[aria-label="Fechar"]').click()
    pg.wait_for_timeout(700)
    confere(len(PERGUNTAS) == 2 and not aberta(pg), "X com campo alterado + 'ok' fecha")

    # formulário limpo: X fecha direto
    PERGUNTAS.clear()
    pg.locator("button", has_text="Dar baixa").first.click()
    pg.wait_for_selector(DIALOGO_BAIXA, timeout=10000)
    pg.wait_for_timeout(600)
    pg.locator(f'{DIALOGO_BAIXA} button[aria-label="Fechar"]').click()
    pg.wait_for_timeout(700)
    confere(not aberta(pg) and not PERGUNTAS, "X com formulário limpo fecha sem perguntar")

    # ── Modal travado: Patrimônio › Baixar do ativo ─────────────────────
    criar_patrimonio()
    pg.goto(FRONT + "/financeiro?ir=patrimonio", timeout=240000)
    pg.locator('button[title^="Baixar do ativo"]').first.click()
    modal = pg.locator('div.popup-caixa[role=dialog][aria-label^="Baixar do ativo"]')
    modal.wait_for(timeout=15000)
    pg.wait_for_timeout(600)
    confere(abs(modal.bounding_box()["width"] - 1120) <= 2, f"Modal 'Baixar do ativo' a 1440 px = {round(modal.bounding_box()['width'])} (era 560)")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)
    confere(modal.count() == 1, "Modal travado: Esc NÃO fecha")
    modal.locator('button[aria-label="Fechar"]').click()
    pg.wait_for_timeout(700)
    confere(modal.count() == 0, "Modal travado: X fecha")

    # ── Esc aninhado: Modal dentro da gaveta de Lançamentos ─────────────
    def abrir_gaveta_lancamentos(aba, sub=None):
        pg.goto(FRONT + "/lancamentos", timeout=240000)
        pg.wait_for_selector("text=Abrir lançamento", timeout=120000)
        pg.locator("button", has_text=re.compile(f"^\\s*{aba}\\s*$", re.I)).first.click()
        if sub:
            pg.locator("button", has_text=re.compile(f"^\\s*{sub}\\s*$", re.I)).first.click()
        pg.wait_for_timeout(500)
        pg.get_by_role("button", name="Abrir lançamento").click()
        g = pg.locator('aside[role=dialog][aria-hidden="false"]')
        g.wait_for(timeout=10000)
        pg.wait_for_timeout(500)
        return g

    gaveta = abrir_gaveta_lancamentos("sanitário", "protocolo sanitário")
    pg.get_by_role("button", name="Novo").first.click()
    modais = pg.locator("div.popup-caixa[role=dialog]")
    modais.first.wait_for(timeout=10000)
    pg.wait_for_timeout(400)
    confere(modais.count() == 1 and gaveta.count() == 1, "Modal aberto dentro da gaveta")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(700)
    confere(modais.count() == 0 and gaveta.count() == 1, "1º Esc fecha só o Modal (a gaveta fica)")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(700)
    confere(gaveta.count() == 0, "2º Esc fecha a gaveta (Esc ligado nela)")

    # Seletor de animais do Protocolo IATF (overlay próprio) dentro da gaveta
    gaveta = abrir_gaveta_lancamentos("reprodutivo")
    gaveta.get_by_text("Em lote (vários animais)").click()
    gaveta.get_by_role("button", name="Selecionar animais…").click()
    seletor = pg.locator('[role=dialog][aria-label^="Escolher animais"]')
    seletor.wait_for(timeout=10000)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)
    confere(seletor.count() == 0 and gaveta.count() == 1, "1º Esc fecha só o seletor de animais (a gaveta fica)")
    POLITICA["acao"] = "accept"  # formulário alterado: Lançamentos pergunta antes de sair
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(700)
    confere(gaveta.count() == 0, "2º Esc fecha a gaveta")

    # ── celular 390 ─────────────────────────────────────────────────────
    pm = contexto(browser, 390, 844).new_page()
    abrir_baixa(pm)
    caixa = pm.locator(DIALOGO_BAIXA).bounding_box()
    confere(round(caixa["width"]) == 390 and round(caixa["x"]) == 0, f"390 px: gaveta ocupa a tela toda ({round(caixa['width'])} px)")
    confere(pm.evaluate("document.documentElement.scrollWidth") <= 390, "390 px: sem rolagem horizontal da página")
    confere(pm.evaluate("document.querySelector('[role=dialog][aria-label^=\"Dar baixa\"]').scrollWidth") <= 391,
            "390 px: sem rolagem horizontal dentro da gaveta")
    browser.close()

if falhas:
    print(f"\n{len(falhas)} falha(s)")
    sys.exit(1)
print("\ntudo certo")
