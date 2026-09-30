"""Coletor da NuCel.

Como a Unifique, exige navegador: o HTML servido traz so dois precos
soltos, e os planos aparecem depois que o JavaScript monta a pagina.

Diferente da Unifique em duas coisas que facilitam:
  - e nacional, sem variacao por praca: uma captura por dia basta
  - nao tem seletor de cidade, entao nao ha fluxo de cliques

CONDICAO DE ELEGIBILIDADE: parte das ofertas da NuCel depende de ser
cliente Nubank em certo nivel (Nu+ ou Croma). Isso e registrado no campo
`elegibilidade`, porque comparar um preco que nem todo mundo consegue
contratar com um preco aberto seria comparacao torta.

Uso:  python coletores/nucel.py
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

PAGINA = "https://nubank.com.br/nu/nucel"

# Nacional: uma captura por dia basta. Repetir nas 20 pracas gravaria
# 20 copias do mesmo preco e inflaria a base sem acrescentar nada.
NACIONAL = True


def _num(txt):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", str(txt or ""))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def extrair(texto):
    """Le os planos do texto da pagina: franquia em GB e preco mensal."""
    ofertas = []
    # "25 GB ... R$ 45" - a franquia vem antes do preco, no mesmo bloco
    for m in re.finditer(r"(\d{1,3})\s*GB(.{0,300}?)R\$\s*\n?\s*(\d{1,3}(?:,\d{2})?)", texto, re.S):
        gb, meio, preco = m.groups()
        valor = _num(preco)
        if not valor or valor > 400:      # acima disso nao e mensalidade de MVNO
            continue
        contexto = re.sub(r"\s+", " ", meio)
        eleg = None
        if re.search(r"\bcroma\b", contexto, re.I):
            eleg = "Nubank Croma"
        elif re.search(r"\bnu\s*\+|\bultravioleta\b", contexto, re.I):
            eleg = "Nu+ / Ultravioleta"
        ofertas.append({
            "nome_oferta": "NuCel %s GB" % gb,
            "destaque": "%s GB" % gb,
            "franquia_anunciada_gb": int(gb),
            "preco_promocional": valor,
            "elegibilidade": eleg,
            "contexto": contexto[:220],
        })
    vistos, unicas = set(), []
    for o in ofertas:
        k = (o["franquia_anunciada_gb"], o["preco_promocional"])
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(o)
    return unicas


def coletar(cidade="Brasil", uf="BR", verbose=True, pagina=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "NuCel", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR NUCEL  |  nacional  |  %s" % agora.strftime("%d/%m/%Y %H:%M"))
        print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        saida["avisos"].append("playwright nao instalado - a NuCel exige navegador")
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
        pagina.wait_for_timeout(4000)
        texto = pagina.inner_text("body")

        for o in extrair(texto):
            o.update({
                "operadora": "NuCel", "produto": "movel", "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_contratual_gb": None, "degrau_mbps": None,
                "preco_cheio": None, "nivel_bundle": 0,
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
                "fidelidade_meses": None, "multa_fidelidade": None,
                "taxa_instalacao": None,
            })
            o.pop("contexto", None)
            saida["ofertas"].append(o)

        if not saida["ofertas"]:
            saida["avisos"].append(
                "nenhuma oferta lida - o layout da NuCel provavelmente mudou")
        if verbose:
            print("  movel  %d ofertas" % len(saida["ofertas"]))
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
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    d = coletar(verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    for o in sorted(d["ofertas"], key=lambda x: x["preco_promocional"] or 0):
        print("  %-18s %-8s R$ %-8g %s" % (
            o["nome_oferta"], o["destaque"], o["preco_promocional"],
            o.get("elegibilidade") or ""))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
