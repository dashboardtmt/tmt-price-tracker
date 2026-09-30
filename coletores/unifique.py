"""Coletor da Unifique.

A unica das seis que exige navegador de verdade.

POR QUE: os precos vem no HTML, mas o servidor so os inclui quando a
sessao ja tem uma cidade escolhida - e a escolha mora num cookie que o
JavaScript nao enxerga. Testado e descartado, em 30/09/2026:

  - parametro na URL (?cidade=blumenau)  -> ignorado, devolve a sessao atual
  - rotas /cidade/x, /set-cidade/x       -> 404
  - forjar cookie                        -> o cookie e HttpOnly
  - API por tras                         -> nao existe; nenhuma chamada e feita

Sobra abrir a pagina, clicar no seletor, buscar a cidade e ler. E o que
este modulo faz.

FRAGILIDADE ASSUMIDA: depende do layout do site, nao de um formato de
dado. Quando a Unifique mexer na tela, isto quebra - e por isso avisa em
vez de devolver vazio em silencio.

Uso:  python coletores/unifique.py [--praca "Blumenau/SC"]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

PAGINA = "https://unifique.com.br/para-voce/internet-fibra"
ESPERA = 2000

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer"}


def _num(txt):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", str(txt or ""))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def _mbps(txt):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps)", str(txt or "").lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def nivel_bundle(texto):
    t = (texto or "").lower()
    if "tv por assinatura" in t or "canais" in t:
        return 4
    achados = {s for s in STREAMINGS if s in t}
    if len(achados) > 1:
        return 3
    if len(achados) == 1:
        return 2
    return 0


def extrair(texto):
    """Le as ofertas do texto da pagina.

    A estrutura HTML nao ajuda - os cards nao tem classe propria - entao a
    leitura e pelo texto que o cliente ve: "FIBRA IDEAL 500 Mega ... R$ 119,90".
    """
    ofertas = []
    # O preco mensal e o que vem seguido de "/mes". Sem essa ancora captura-se
    # o primeiro "R$" do card - e no FIBRA ESSENCIAL esse primeiro valor e a
    # taxa de instalacao (R$ 349,90), nao a mensalidade de R$ 89,90.
    padrao = re.compile(
        r"([A-ZÀ-Ú][A-ZÀ-Ú0-9\s\+\-\.]{3,40}?)\s*(\d{3,4})\s*Mega"
        r"(.{0,600}?)R\$\s*\n?\s*(\d{2,4},\d{2})\s*\n?\s*.{0,4}/m",
        re.S)
    for m in padrao.finditer(texto):
        nome, mega, meio, preco = m.groups()
        nome = re.sub(r"\s+", " ", nome).strip(" -+.")
        if not nome or len(nome) < 3:
            nome = "Unifique %s Mega" % mega
        taxa = re.search(r"instala[çc][ãa]o\s*R\$\s*(\d{1,4},\d{2})", meio, re.I)
        gratis = re.search(r"instala[çc][ãa]o\s*gr[áa]tis", meio, re.I)
        ofertas.append({
            "nome_oferta": nome[:60],
            "destaque": "%s Mega" % mega,
            "degrau_mbps": _mbps(mega + " Mega"),
            "preco_promocional": _num(preco),
            # a Unifique escreve a taxa no proprio card; as outras so trazem
            # isso no regulamento, quando trazem
            "taxa_instalacao": _num(taxa.group(1)) if taxa else (0.0 if gratis else None),
            "contexto": re.sub(r"\s+", " ", meio)[:260],
        })
    # tira repetido (a pagina repete o card em versao desktop e mobile)
    vistos, unicas = set(), []
    for o in ofertas:
        k = (o["degrau_mbps"], o["preco_promocional"])
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(o)
    return unicas


def _escolher_cidade(pg, cidade, uf):
    """Abre o seletor (ou o 'mudar', se ja houver cidade) e escolhe."""
    abriu = False
    for rotulo in (r"ver ofertas", r"^mudar$"):
        try:
            pg.get_by_text(re.compile(rotulo, re.I)).first.click(timeout=6000)
            abriu = True
            break
        except Exception:
            continue
    if not abriu:
        return False, "nao encontrei o seletor de cidade"

    pg.wait_for_timeout(1200)
    try:
        pg.locator('input[type="search"]').first.fill(cidade)
    except Exception as e:
        return False, "campo de busca ausente: %s" % str(e)[:60]
    pg.wait_for_timeout(1200)

    alvo = pg.locator("button.select-city",
                      has_text=re.compile(r"%s\s*-\s*%s" % (re.escape(cidade), uf), re.I))
    if alvo.count() == 0:
        return False, "a Unifique nao atende %s/%s" % (cidade, uf)
    try:
        alvo.first.click(timeout=8000)
    except Exception as e:
        return False, "nao consegui selecionar a cidade: %s" % str(e)[:60]
    pg.wait_for_timeout(4000)
    return True, None


def coletar(cidade, uf, verbose=True, pagina=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Unifique", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR UNIFIQUE  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        saida["avisos"].append(
            "playwright nao instalado - a Unifique exige navegador "
            "(pip install playwright && playwright install chromium)")
        return saida

    proprio = pagina is None
    contexto = nav = p = None
    try:
        if proprio:
            p = sync_playwright().start()
            nav = p.chromium.launch(headless=True)
            contexto = nav.new_context(locale="pt-BR")
            pagina = contexto.new_page()

        pagina.goto(PAGINA, wait_until="domcontentloaded", timeout=60000)
        pagina.wait_for_timeout(ESPERA)

        ok, err = _escolher_cidade(pagina, cidade, uf)
        if not ok:
            saida["avisos"].append(err)
            if verbose:
                print("  %s" % err)
            return saida

        texto = pagina.inner_text("body")
        if cidade.lower() not in texto.lower():
            saida["avisos"].append("a pagina nao confirmou a cidade %s" % cidade)

        for o in extrair(texto):
            o.update({
                "operadora": "Unifique", "produto": "fibra", "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_anunciada_gb": None, "franquia_contratual_gb": None,
                "preco_cheio": None,
                "nivel_bundle": nivel_bundle(o.pop("contexto", "")),
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
                "fidelidade_meses": None, "multa_fidelidade": None,
            })
            saida["ofertas"].append(o)

        if not saida["ofertas"]:
            saida["avisos"].append(
                "nenhuma oferta lida - o layout da Unifique provavelmente mudou")
        if verbose:
            print("  fibra  %d ofertas" % len(saida["ofertas"]))
    except Exception as e:
        saida["avisos"].append("navegador: %s" % str(e)[:140])
        if verbose:
            print("  ERRO: %s" % str(e)[:140])
    finally:
        if proprio:
            for fechar in (contexto, nav):
                try:
                    fechar and fechar.close()
                except Exception:
                    pass
            try:
                p and p.stop()
            except Exception:
                pass
    return saida


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--praca", default="Blumenau/SC")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cidade, uf = a.praca.split("/")
    d = coletar(cidade, uf, verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    for o in sorted(d["ofertas"], key=lambda x: x["degrau_mbps"] or 0):
        print("  %-38s %-10s R$ %-8g nivel %s" % (
            o["nome_oferta"][:38], o["destaque"], o["preco_promocional"] or 0,
            o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
