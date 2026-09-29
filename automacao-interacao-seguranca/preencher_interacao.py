"""Preenche e grava o formulário "Registro de Interação" (SAP Fiori ZGEEHS_REG_ABRD).

Os textos de Descrição, Ação Imediata e "Grandes Riscos" vêm de modelos definidos
em modelos.yaml. O script usa a própria API do SAPUI5 (no navegador) para localizar
cada campo pelo rótulo e atribuir o valor, o que é mais robusto que cliques em DOM.

Uso rápido:
    python preencher_interacao.py --login            # 1ª vez: faz login SSO e salva a sessão
    python preencher_interacao.py --listar-opcoes    # mostra as opções dos combos
    python preencher_interacao.py                    # preenche SEM gravar (conferência)
    python preencher_interacao.py --gravar           # preenche e clica em "Gravar"
"""

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

import yaml
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

PASTA = Path(__file__).resolve().parent
URL_PADRAO = (
    "https://sapfiori.arcelormittal.com.br/sap/bc/ui5_ui5/ui2/ushell/shells/abap/"
    "Fiorilaunchpad.html?appState=lean#ZGEEHS_REG_ABRD-display"
)
# O app só está pronto quando este combo recebeu as opções do SAP (chegam alguns
# segundos depois de o formulário aparecer).
ROTULO_ESPERA = "A interação foi feita baseada em algum dos Grandes Riscos"

# Funções executadas dentro da página. Localizam o controle UI5 a partir do texto do
# rótulo (ignorando acentos, "*", ":" e "?") e leem/gravam seu valor.
JS_UTIL = r"""
window.__autoInteracao = (() => {
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[*:?]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();

  const byId = id => (sap.ui.core.Element && sap.ui.core.Element.getElementById)
    ? sap.ui.core.Element.getElementById(id) : sap.ui.getCore().byId(id);

  // Sobe pelos sufixos do id (ex.: "xyz-inner" -> "xyz") até achar um controle.
  const controleDoId = id => {
    while (id) {
      const c = byId(id);
      if (c && typeof c.getMetadata === 'function' && !c.isA('sap.m.Label')) return c;
      const i = id.lastIndexOf('-');
      if (i < 0) return null;
      id = id.substring(0, i);
    }
    return null;
  };

  const rotulos = () => Array.from(document.querySelectorAll('.sapMLabel'))
    .filter(el => el.offsetParent !== null);

  const controlePorRotulo = rotulo => {
    const alvo = norm(rotulo);
    const els = rotulos();
    const el = els.find(e => norm(e.textContent) === alvo)
            || els.find(e => norm(e.textContent).startsWith(alvo));
    if (!el) return null;
    let forId = el.getAttribute('for');
    if (!forId) {
      const lbl = byId(el.id);
      const assoc = lbl && (lbl.getLabelForRendering ? lbl.getLabelForRendering() : lbl.getLabelFor());
      forId = assoc;
    }
    return forId ? controleDoId(forId) : null;
  };

  const textoItem = it => it.getText ? it.getText() : '';

  const acharItem = (ctrl, valor) => {
    const itens = ctrl.getItems();
    const v = norm(valor);
    return itens.find(it => norm(textoItem(it)) === v)
        || itens.find(it => it.getKey && norm(it.getKey()) === v)
        || itens.find(it => norm(textoItem(it)).startsWith(v));
  };

  const definir = (rotulo, valor) => {
    const c = controlePorRotulo(rotulo);
    if (!c) return {ok: false, erro: 'campo não encontrado'};
    const tipo = c.getMetadata().getName();

    if (c.isA('sap.m.MultiComboBox')) {
      const lista = Array.isArray(valor) ? valor : [valor];
      const itens = [];
      for (const v of lista) {
        const it = acharItem(c, v);
        if (!it) return {ok: false, tipo, erro: `opção não encontrada: "${v}"`, opcoes: c.getItems().map(textoItem)};
        itens.push(it);
      }
      c.setSelectedItems(itens);
      c.fireSelectionFinish({selectedItems: itens});
      return {ok: true, tipo, valor: itens.map(textoItem).join('; ')};
    }

    if (typeof c.getItems === 'function' && typeof c.setSelectedItem === 'function') {
      const it = acharItem(c, String(valor));
      if (!it) return {ok: false, tipo, erro: `opção não encontrada: "${valor}"`, opcoes: c.getItems().map(textoItem)};
      c.setSelectedItem(it);
      if (c.fireSelectionChange) c.fireSelectionChange({selectedItem: it});
      c.fireChange({selectedItem: it, value: textoItem(it)});
      return {ok: true, tipo, valor: textoItem(it)};
    }

    if (typeof c.setValue === 'function') {
      c.setValue(String(valor));
      if (c.fireLiveChange) c.fireLiveChange({value: String(valor)});
      c.fireChange({value: String(valor), newValue: String(valor), valid: true});
      return {ok: true, tipo, valor: c.getValue()};
    }
    return {ok: false, tipo, erro: 'tipo de campo não suportado'};
  };

  const listar = () => rotulos().map(el => {
    const texto = el.textContent.replace(/[*:]/g, '').trim();
    const forId = el.getAttribute('for');
    const c = forId ? controleDoId(forId) : null;
    if (!c) return null;
    const r = {rotulo: texto, tipo: c.getMetadata().getName()};
    if (typeof c.getItems === 'function') r.opcoes = c.getItems().map(textoItem);
    if (typeof c.getValue === 'function') r.valor = c.getValue();
    return r;
  }).filter(Boolean);

  const pronto = rotulo => {
    if (!(window.sap && sap.ui && sap.ui.getCore)) return false;
    const c = controlePorRotulo(rotulo);
    return !!c && (typeof c.getItems !== 'function' || c.getItems().some(it => textoItem(it)));
  };

  return {definir, listar, pronto};
})();
"""


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def carregar_config(caminho):
    with open(caminho, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not cfg.get("modelos"):
        sys.exit(f"Nenhum modelo definido em {caminho}")
    return cfg


def escolher_modelo(cfg, nome, arquivo_estado):
    modelos = cfg["modelos"]
    if nome:
        for m in modelos:
            if m.get("nome", "").lower() == nome.lower():
                return m
        sys.exit(f"Modelo '{nome}' não encontrado. Disponíveis: {[m.get('nome') for m in modelos]}")

    if cfg.get("selecao", "rotativo") == "aleatorio":
        return random.choice(modelos)

    estado = {}
    if arquivo_estado.exists():
        estado = json.loads(arquivo_estado.read_text(encoding="utf-8"))
    indice = estado.get("proximo", 0) % len(modelos)
    return modelos[indice]


def avancar_rotacao(cfg, modelo, arquivo_estado):
    indice = cfg["modelos"].index(modelo)
    arquivo_estado.write_text(json.dumps({"proximo": indice + 1}), encoding="utf-8")


def montar_campos(cfg, modelo, data):
    campos = dict(cfg.get("campos_fixos") or {})
    campos.update(modelo.get("campos") or {})
    hoje = data or dt.date.today().strftime("%d/%m/%Y")

    def subst(v):
        if isinstance(v, list):
            return [subst(x) for x in v]
        return str(v).replace("{hoje}", hoje).strip()

    campos = {k: subst(v) for k, v in campos.items()}
    if data:
        campos["Data"] = data
    return campos


def esperar_app(page, timeout_s):
    page.add_init_script(JS_UTIL)
    page.evaluate(JS_UTIL)  # caso a página já esteja carregada
    page.wait_for_function(
        """rotulo => { if (!window.__autoInteracao) { return false; }
                       return window.__autoInteracao.pronto(rotulo); }""",
        arg=ROTULO_ESPERA,
        timeout=timeout_s * 1000,
    )


def preencher(page, campos):
    erros = []
    for rotulo, valor in campos.items():
        r = page.evaluate("([r, v]) => window.__autoInteracao.definir(r, v)", [rotulo, valor])
        if r.get("ok"):
            resumo = r["valor"] if len(r["valor"]) <= 60 else r["valor"][:57] + "..."
            log(f"  OK  {rotulo}: {resumo}")
        else:
            log(f"  ERRO {rotulo}: {r.get('erro')}")
            if r.get("opcoes"):
                log("       opções disponíveis: " + " | ".join(o for o in r["opcoes"] if o))
            erros.append(rotulo)
        page.wait_for_timeout(400)  # combos podem recarregar campos dependentes
    return erros


def gravar(page, pasta_logs, carimbo):
    page.get_by_role("button", name="Gravar").click()
    log("Botão 'Gravar' acionado; aguardando resposta do SAP...")
    mensagem, erro = None, False
    seletor = ".sapMMessageToast, .sapMMessageBox, .sapMDialog[role='alertdialog'], .sapMDialog"
    try:
        page.wait_for_selector(seletor, timeout=30000)
        page.wait_for_timeout(500)
        mensagem = page.locator(seletor).first.inner_text().strip()
        erro = page.locator(".sapMMessageBoxError, .sapMDialogError").count() > 0
    except PlaywrightTimeout:
        pass
    page.screenshot(path=str(pasta_logs / f"{carimbo}_apos_gravar.png"), full_page=True)
    return mensagem, erro


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(PASTA / "modelos.yaml"), help="arquivo de modelos (YAML)")
    ap.add_argument("--modelo", help="nome do modelo a usar (padrão: rotativo/aleatório conforme config)")
    ap.add_argument("--data", help="data da interação dd/mm/aaaa (padrão: mantém a sugerida pelo app)")
    ap.add_argument("--gravar", action="store_true", help="clica em 'Gravar' ao final (sem isso só preenche)")
    ap.add_argument("--login", action="store_true", help="abre o navegador para login manual e salva a sessão")
    ap.add_argument("--listar-opcoes", action="store_true", help="lista campos e opções dos combos e sai")
    ap.add_argument("--headless", action="store_true", help="executa sem abrir janela")
    ap.add_argument("--canal", default=None, help="navegador instalado a usar: msedge ou chrome (padrão: Chromium do Playwright)")
    ap.add_argument("--url", default=URL_PADRAO)
    ap.add_argument("--timeout", type=int, default=120, help="segundos para aguardar o app carregar")
    args = ap.parse_args()

    cfg = carregar_config(args.config)
    perfil = PASTA / "perfil_navegador"
    pasta_logs = PASTA / "logs"
    pasta_logs.mkdir(exist_ok=True)
    arquivo_estado = PASTA / "estado.json"
    carimbo = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(perfil),
            channel=args.canal,
            headless=args.headless and not args.login,
            locale="pt-BR",
            viewport={"width": 1600, "height": 1000},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url)

        if args.login:
            log("Faça o login no navegador. Quando o formulário aparecer, a sessão será salva.")
            esperar_app(page, 600)
            log("Login concluído e sessão salva em perfil_navegador/.")
            ctx.close()
            return 0

        try:
            esperar_app(page, args.timeout)
        except PlaywrightTimeout:
            page.screenshot(path=str(pasta_logs / f"{carimbo}_falha_carregar.png"), full_page=True)
            log("O formulário não carregou. A sessão pode ter expirado: rode com --login.")
            ctx.close()
            return 2

        if args.listar_opcoes:
            for campo in page.evaluate("() => window.__autoInteracao.listar()"):
                log(f"{campo['rotulo']}  [{campo['tipo']}]")
                for o in campo.get("opcoes") or []:
                    if o:
                        print(f"      - {o}")
            ctx.close()
            return 0

        modelo = escolher_modelo(cfg, args.modelo, arquivo_estado)
        campos = montar_campos(cfg, modelo, args.data)
        log(f"Usando modelo: {modelo.get('nome')}")
        erros = preencher(page, campos)
        page.screenshot(path=str(pasta_logs / f"{carimbo}_preenchido.png"), full_page=True)

        if erros:
            log(f"Não foi possível preencher: {', '.join(erros)}. Nada foi gravado.")
            ctx.close()
            return 1

        if not args.gravar:
            log("Modo conferência: formulário preenchido mas NÃO gravado (use --gravar).")
            if not args.headless:
                input("Pressione Enter para fechar o navegador...")
            ctx.close()
            return 0

        mensagem, erro = gravar(page, pasta_logs, carimbo)
        log(f"Resposta do SAP: {mensagem or '(nenhuma mensagem detectada; confira o print em logs/)'}")
        if erro:
            log("O SAP retornou erro; a rotação de modelos não foi avançada.")
            ctx.close()
            return 1
        if not args.modelo:
            avancar_rotacao(cfg, modelo, arquivo_estado)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
