"""Coletor da Claro.

A Claro roda em SAP Hybris e entrega os cards prontos no HTML. A praca
troca por cookie, num endpoint proprio (addRegionCookie).

O QUE ELA DA DE PRESENTE: a lista de cidades vem com CODIGO IBGE. E a
mesma chave do dado municipal da Anatel que o Dashboard ja usa, entao as
duas bases amarram sem conversao.

COMPOSICAO DA FRANQUIA: a Claro escreve por extenso -
"15GB de Livres + 20GB de Bonus uso livre + 5GB Bonus para Redes Sociais".
O "de Livres" e a franquia contratual; o resto expira.

Uso:  python coletores/claro.py [--praca "Sao Paulo/SP"]
"""

import argparse
import http.cookiejar
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

PAUSA = 4
BASE = "https://planoscelular.claro.com.br"
CIDADES = BASE + "/claro/pt/checkout/multi/delivery-address/region/BR-%s/cities"
TROCA = BASE + "/view/ClaroCMSRegionComponentController/addRegionCookie"

PAGINAS = {
    "movel": BASE + "/",
    "fibra": "https://www.claro.com.br/internet/banda-larga/fibra-otica",
    "combo": "https://www.claro.com.br/multi",
    "prepago": "https://www.claro.com.br/celular/planos-pre/prezao",
}

# Montadas em Storyblok, sem os cards do movel: a leitura e pelo texto que
# a Claro exibe ao cliente.
POR_TEXTO = {"fibra", "combo", "prepago"}

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer"}
APPS_CATALOGO = {"skeelo", "mcafee", "claro banca", "geforce", "google one",
                 "icloud", "claro musica", "claro video"}


def navegador():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "pt-BR,pt;q=0.9,en;q=0.8"),
        ("Accept-Encoding", "identity"),
        ("Upgrade-Insecure-Requests", "1"),
        ("Sec-Fetch-Site", "none"),
        ("Sec-Fetch-Mode", "navigate"),
        ("Sec-Fetch-Dest", "document"),
        ("Sec-Fetch-User", "?1"),
        ("sec-ch-ua", '"Chromium";v="128", "Not;A=Brand";v="24"'),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"Windows"'),
    ]
    return op, cj


def buscar(op, url, metodo="GET", dados=None, extras=None, timeout=45):
    corpo = urllib.parse.urlencode(dados).encode() if dados else None
    req = urllib.request.Request(url, data=corpo, method=metodo)
    for k, v in (extras or {}).items():
        req.add_header(k, v)
    if dados:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, "ERRO: %s" % e


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def numero(txt):
    if not txt:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", str(txt))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def gb(txt):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*gb", (txt or "").lower())
    return int(float(m.group(1).replace(",", "."))) if m else None


def mbps(txt):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps)", (txt or "").lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def franquia_contratual(txt):
    """'15GB de Livres + 20GB de Bonus...' -> 15. O resto e bonus temporario."""
    m = re.search(r"(\d+)\s*gb\s*de\s*livres", (txt or "").lower())
    return int(m.group(1)) if m else None


def nivel_bundle(txt):
    t = (txt or "").lower()
    if "tv por assinatura" in t or "canais" in t:
        return 4
    achados = {s for s in STREAMINGS if s in t}
    if len(achados) > 1:
        return 3
    if len(achados) == 1:
        return 2
    return 1 if any(a in t for a in APPS_CATALOGO) else 0


def codigo_cidade(op, cidade, uf):
    """Acha o code que a Claro usa para a cidade, e devolve tambem o IBGE."""
    s, corpo = buscar(op, CIDADES % uf, extras={"Accept": "application/json"})
    if s != 200:
        return None, None, "cidades: HTTP %s" % s
    try:
        lista = json.loads(corpo)
    except Exception as e:
        return None, None, "cidades: %s" % e
    alvo = sem_acento(cidade).upper()
    for c in lista:
        if sem_acento(c.get("name", "")).upper() == alvo:
            return c.get("code"), c.get("ibgeCode"), None
    return None, None, "cidade %s nao esta na lista da Claro em %s" % (cidade, uf)


def trocar_praca(op, code):
    s, _ = buscar(op, TROCA, metodo="POST", dados={"regionCode": code},
                  extras={"X-Requested-With": "XMLHttpRequest",
                          "Referer": BASE + "/"})
    return s in (200, 204)


def ler_cards(op, url, produto):
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    cards = []
    for bloco in re.split(r'class="[^"]*card-planos', h)[1:]:
        ident = re.search(r'id="plan-(\d+)"', bloco)
        # 12k porque os cards de pos-pago trazem o seletor de linhas
        # antes do preco; cortar em 4k perdia 6 dos 9 planos
        txt = re.sub(r"<[^>]+>", " ", bloco[:12000])
        txt = re.sub(r"&nbsp;", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip().lstrip('-custom "> ').strip()
        # A Claro mistura aparelhos no mesmo carrossel dos planos. Celular
        # nao e oferta de servico: um iPhone a R$ 12.999 entraria na serie
        # como se fosse plano e estragaria qualquer media.
        if 'data-link-redirect="/celulares/' in bloco[:12000] or "data-product-name=" in bloco[:12000]:
            continue
        preco = re.search(r"R\$\s?([\d.]+,\d{2})", txt)
        if not preco:
            continue
        if txt.startswith("data-") or not re.match(r"[A-Za-z]", txt):
            continue   # bloco sem identidade legivel
        # o nome vem antes do primeiro numero de franquia/velocidade
        nome = re.split(r"\d+\s*(?:GB|MEGA|Mega|Giga)", txt)[0].strip(' ">-')
        destaque = re.search(r"(\d+\s*(?:GB|MEGA|Mega|Giga|Mbps))", txt)
        cards.append({
            "id_catalogo": ident.group(1) if ident else None,
            "nome_oferta": (nome or "Claro")[:70],
            "destaque": destaque.group(1) if destaque else None,
            "preco_promocional": numero(preco.group(1)),
            "composicao": txt[:400],
        })
    return cards, None


def ler_por_texto(op, url, produto):
    """A pagina de fibra nao usa card-planos: ela e montada em Storyblok,
    com os dados em JSON dentro do HTML. O que sobra legivel e o padrao
    "600 mega a partir de R$ 99,90", com o internetId do plano ao lado.

    Menos elegante que os cards do movel, mas estavel: e o texto que a
    propria Claro exibe ao cliente.
    """
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    achados, vistos = [], set()
    unidade = "gb" if produto == "prepago" else "mega"
    for m in re.finditer(r"(\d{1,4})\s*%s[^\"]{0,40}?R\$\s?(\d{1,3},\d{2})" % unidade, h, re.I):
        velocidade, preco = m.group(1), m.group(2)
        if (velocidade, preco) in vistos:
            continue
        vistos.add((velocidade, preco))
        ident = re.findall(r"internetId=([\d,]+)", h[m.start():m.start() + 700])
        contexto = re.sub(r"<[^>]+>", " ", h[max(0, m.start() - 400):m.start() + 400])
        achados.append({
            "id_catalogo": ident[0][:40] if ident else None,
            "nome_oferta": "Claro %s %s %s" % (
                {"fibra": "Fibra", "combo": "Multi", "prepago": "Pre"}[produto],
                velocidade, "GB" if produto == "prepago" else "Mega"),
            "destaque": "%s %s" % (velocidade, "GB" if produto == "prepago" else "Mega"),
            "preco_promocional": numero(preco),
            "composicao": re.sub(r"\s+", " ", contexto)[:400],
        })
    return achados, None


def coletar(cidade, uf, verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    op, _ = navegador()
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Claro", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR CLARO  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    code, ibge, err = codigo_cidade(op, cidade, uf)
    if err:
        saida["avisos"].append(err)
        if verbose:
            print("  AVISO: %s" % err)
    else:
        if verbose:
            print("  cidade %s -> code %s (IBGE %s)" % (cidade, code, ibge))
        if not trocar_praca(op, code):
            saida["avisos"].append("praca nao fixou - dado pode ser do padrao")
            if verbose:
                print("  AVISO: a praca nao fixou")
    time.sleep(PAUSA)

    for produto, url in PAGINAS.items():
        cards, erro = (ler_por_texto(op, url, produto) if produto in POR_TEXTO
                       else ler_cards(op, url, produto))
        if erro:
            saida["avisos"].append("%s: %s" % (produto, erro))
            if verbose:
                print("  %-7s FALHOU (%s)" % (produto, erro))
            time.sleep(PAUSA)
            continue
        for c in cards:
            nome = c["nome_oferta"]
            if produto in POR_TEXTO:
                real = produto          # a pagina ja define o produto
            elif "controle" in nome.lower():
                real = "controle"
            else:
                real = "movel"
            c.update({
                "operadora": "Claro", "produto": real, "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_anunciada_gb": gb(c["destaque"]) if real not in ("fibra", "combo") else None,
                "franquia_contratual_gb": franquia_contratual(c["composicao"]),
                "degrau_mbps": mbps(c["destaque"]) if real in ("fibra", "combo") else None,
                "nivel_bundle": nivel_bundle(c["composicao"]),
                "preco_cheio": None, "codigo_anatel": None, "campanha": None,
                "ibge": ibge,
            })
            saida["ofertas"].append(c)
        if verbose:
            print("  %-7s %d ofertas" % (produto, len(cards)))
        time.sleep(PAUSA)
    return saida


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--praca", default="Sao Paulo/SP")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cidade, uf = a.praca.split("/")
    d = coletar(cidade, uf, verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    for produto in ("controle", "movel", "fibra", "prepago"):
        ofs = [o for o in d["ofertas"] if o["produto"] == produto]
        if not ofs:
            continue
        print("\n--- %s (%d) ---" % (produto.upper(), len(ofs)))
        for o in sorted(ofs, key=lambda x: x["preco_promocional"] or 0):
            print("  %-32s %-9s R$ %-8g contratual %-5s nivel %s" % (
                o["nome_oferta"][:32], o["destaque"] or "-",
                o["preco_promocional"] or 0,
                o["franquia_contratual_gb"] or "-", o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
