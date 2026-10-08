"""Coletor do Claro Flex - a linha below-the-line da Claro.

POR QUE EXISTE SEPARADO. O Flex nao mora em claro.com.br: tem dominio
proprio (flex.claro.com.br) e nao aparece em nenhuma das quatro paginas
que o coletor da Claro le. Por isso o tracker mostrava a Claro entrando
a R$ 59,90 no Controle quando ela entra a R$ 44,90 aqui - a oferta que
segura o cliente sem mexer no portfolio anunciado ficava inteira fora
da base. Mesma historia do Vivo Lite.

POR QUE NAVEGADOR. A pagina e uma SPA em Vue: o HTML servido tem 4 KB e
diz "doesn't work properly without JavaScript enabled". Procurei a API
por tras e nao ha - nenhuma chamada XHR e feita, e nao existe
__INITIAL_STATE__; os planos vem dentro do bundle JavaScript e so
existem depois de ele rodar. Entao e navegador, como na Unifique.

QUAL PRECO VALE. Cada card traz dois: "De: R$ 44,90" e "Por R$ 34,90 no
primeiro mes", este com cupom (VIRAFLEX10). Pela decisao 9 da
metodologia vale o preco cheio, sem desconto condicionado - entao o que
entra e o "De", e o "Por" fica como preco promocional declarado.

NACIONAL. O Flex nao pergunta cidade: o preco e o mesmo no pais todo,
como a NuCel e a Starlink.

Uso:  python coletores/claro_flex.py
"""

import argparse
import json
import re
import sys

from . import apps
from datetime import datetime, timedelta, timezone

PAGINA = "https://flex.claro.com.br/"
ESPERA = 5000

# Nacional: uma captura por dia basta - repetir nas 20 pracas gravaria
# 20 copias do mesmo preco.
NACIONAL = True

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer",
              "claro musica", "claro música"}
APPS_CATALOGO = {"skeelo", "mcafee", "claro banca", "claro day"}


def _num(txt):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", str(txt or ""))
    if not m:
        return None
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0"))


def nivel_bundle(texto):
    """Mesma escada dos outros coletores (decisao 10)."""
    t = (texto or "").lower()
    strm = sum(1 for s in STREAMINGS if s in t)
    if "tv por assinatura" in t or "canais" in t:
        return 4
    if strm >= 2:
        return 3
    if strm == 1:
        return 2
    if any(a in t for a in APPS_CATALOGO):
        return 1
    return 0


# Um card do Flex, no texto que a pagina renderiza:
#
#   40GB  30GB do plano + 5GB de bonus redes sociais + 5GB de bonus
#   Claro Day  ...  De: R$ 44,90  Por R$ 34,90 No primeiro mes
#
# O "PASSAPORTE 60GB" nao declara composicao e cai no mesmo molde, com a
# franquia contratual ficando igual a anunciada.
CARD = re.compile(
    r"(\d{1,3})\s*GB"                      # a franquia anunciada
    r"(.{0,260}?)"                         # composicao e beneficios
    r"De:\s*R\$\s?(\d{1,3},\d{2})"         # preco cheio
    r"\s*Por\s*R\$\s?(\d{1,3},\d{2})",     # preco com cupom, 1o mes
    re.I | re.S)


def extrair(texto):
    t = re.sub(r"\s+", " ", texto or "")
    ofertas, vistos = [], set()
    for m in CARD.finditer(t):
        gb, meio, cheio, promo = m.groups()
        if gb in vistos:
            continue
        vistos.add(gb)
        # "30GB do plano": o que o contrato garante. O resto e bonus de
        # rede social e Claro Day, que e promocional e pode cair.
        mc = re.search(r"(\d{1,3})\s*GB do plano", meio, re.I)
        passaporte = "passaporte" in meio.lower() or "passaporte" in t[
            max(0, m.start() - 40):m.start()].lower()
        ofertas.append({
            "nome_oferta": ("Claro Flex Passaporte %s GB" if passaporte
                            else "Claro Flex %s GB") % gb,
            "destaque": "%s GB" % gb,
            "franquia_anunciada_gb": int(gb),
            "franquia_contratual_gb": int(mc.group(1)) if mc else int(gb),
            # decisao 9: o que entra e o preco sem desconto condicionado
            "preco_promocional": _num(cheio),
            "preco_cheio": _num(cheio),
            "preco_primeiro_mes": _num(promo),
            "nivel_bundle": nivel_bundle(meio),
            "apps": apps.apps_do_texto(meio),
            "apps_rotulo": apps.rotulo(apps.apps_do_texto(meio)),
            "composicao": meio.strip()[:400],
        })
    return ofertas


def coletar(cidade="Brasil", uf="BR", verbose=True, pagina=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Claro", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR CLARO FLEX  |  %s  |  %s"
              % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        saida["avisos"].append(
            "playwright nao instalado - o Claro Flex exige navegador "
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
        texto = pagina.inner_text("body")

        if "flex" not in texto.lower():
            saida["avisos"].append("a pagina do Flex nao carregou o conteudo")
            return saida

        ofertas = extrair(texto)
        if not ofertas:
            # vazio em silencio e o pior resultado: avisa
            saida["avisos"].append(
                "nenhum card reconhecido - o layout do Flex mudou")
            return saida

        for o in ofertas:
            o.update({
                "operadora": "Claro",
                # below-the-line e produto proprio: no balde do pos-pago
                # um plano de R$ 45 sumiria entre planos de R$ 150
                "produto": "btl",
                "linha": "flex",
                "praca": praca,
                "capturado_em": agora.isoformat(),
                "degrau_mbps": None,
                # o Flex nao tem fidelidade - e o argumento de venda dele
                "fidelidade_meses": None, "multa_fidelidade": None,
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
            })
            saida["ofertas"].append(o)

        if verbose:
            print("  %d ofertas" % len(ofertas))
    except Exception as e:
        saida["avisos"].append("navegador falhou: %s" % str(e)[:140])
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

    print("\n--- OFERTAS (%d) ---" % len(d["ofertas"]))
    for o in sorted(d["ofertas"], key=lambda x: x["preco_promocional"]):
        print("  %-28s %3s GB (contr %s) | R$ %6.2f | 1o mes R$ %6.2f | nivel=%s"
              % (o["nome_oferta"][:28], o["franquia_anunciada_gb"],
                 o["franquia_contratual_gb"], o["preco_promocional"],
                 o["preco_primeiro_mes"], o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
