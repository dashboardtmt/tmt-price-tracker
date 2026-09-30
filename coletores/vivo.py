"""Coletor da Vivo.

DESENHO (corrigido em 30/09/2026):

  A VITRINE define o universo.  O que a praca exibe e o que existe.
  O CATALOGO enriquece.         Entra so para completar campos.

Por que nesta ordem: o catalogo tem 132 entradas de controle/pos, mas a
maioria nao e plano de vitrine - sao pecas que o site usa internamente
(adicionais, variantes de campanha, configuracoes de checkout). Tratar o
deposito de pecas como prateleira gera preco errado e oferta fantasma.
Isso tambem respeita a decisao 6 da metodologia: o universo e o que a
vitrine publica exibe.

REGRA QUE NAO PODE SER ESQUECIDA: sem cabecalhos de navegador de verdade,
a Vivo responde 403 sem explicar. Medido em 24/09/2026.

Uso:  python coletores/vivo.py [--praca "Sao Paulo/SP"] [--json]
"""

import argparse
import html as _html
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

PAUSA = 4  # a Vivo bloqueia rajada

CATALOGO = "https://plataforma.portal.vivo.com.br/catalog/main/b2c/%s.json"
TROCA_PRACA = ("https://vivo.com.br/bin/vivo-portal/service-layer/"
               "geolocation/locate-by-city?city=%s&state=%s")
VITRINE = {
    "fibra": "https://vivo.com.br/para-voce/produtos-e-servicos/para-casa/internet",
    "movel": "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-pos-pago",
    "controle": "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-controle",
}

APPS_CATALOGO = {"skeelo", "goread", "nba", "hube", "super comics", "atma",
                 "btfit", "mcafee", "ubook", "forbes", "casa do saber",
                 "vivo home fix", "nfl", "gemini"}
STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine"}


# ------------------------------------------------------------------- rede

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


def cabecalhos_api(origem):
    return {"Accept": "*/*", "Origin": origem, "Referer": origem + "/",
            "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty"}


def buscar(op, url, metodo="GET", extras=None, timeout=45):
    req = urllib.request.Request(url, method=metodo)
    for k, v in (extras or {}).items():
        req.add_header(k, v)
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, "ERRO: %s" % e


# ----------------------------------------------------------- normalizacao

def so_numero(txt):
    """'R$ 1.234,56' -> 1234.56. Devolve None quando nao for um preco."""
    if txt is None:
        return None
    if isinstance(txt, (int, float)):
        return float(txt)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", str(txt))
    if not m:
        return None
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0"))


def preco_cheio_valido(texto):
    """Le oldPrice, mas so quando for de fato um preco.

    A Fibra Lite traz oldPrice='12x no cartao de credito'. Ler o 12 como
    preco cheio produziria 'de R$ 12 por R$ 90', que e absurdo. So aceita
    quando o texto tem cifrao e nao fala de parcelamento.
    """
    if not texto:
        return None
    t = str(texto)
    if "R$" not in t:
        return None
    if re.search(r"\d+\s*x\b", t, re.I):   # "12x no cartao"
        return None
    return so_numero(t)


def degrau_mbps(texto):
    if not texto:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps)", str(texto).lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def degrau_gb(texto):
    if not texto:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(gb|giga)", str(texto).lower())
    return int(float(m.group(1).replace(",", "."))) if m else None


def nivel_bundle(texto):
    t = (texto or "").lower()
    if "tv por assinatura" in t or "canais" in t:
        return 4
    achados = {s for s in STREAMINGS if s in t}
    if len(achados) > 1:
        return 3
    if len(achados) == 1:
        return 2
    return 1 if any(a in t for a in APPS_CATALOGO) else 0


# ------------------------------------------------- parser da vitrine (HTML)

def _primeiro(padrao, bloco):
    m = re.search(padrao, bloco, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def ler_vitrine(op, produto):
    """Le os cards da vitrine da praca atual.

    O corte e por texto, em class="unique-card " - que aparece exatamente
    uma vez por card. Conferido em 30/09/2026: 7 marcacoes para 7 cards,
    um preco em cada bloco.

    Tentei antes um parser por profundidade de <div>. Nao funciona: o HTML
    da Vivo tem aninhamento irregular e a contagem desanda, fazendo um card
    engolir os seguintes (o 700 Mega saiu com o preco do 10 Giga).
    """
    s, doc = buscar(op, VITRINE[produto])
    if s != 200:
        return None, "HTTP %s" % s

    cards = []
    for bloco in re.split(r'class="unique-card ', doc)[1:]:
        plano = _primeiro(r'unique-card__plan[^>]*>(.*?)<', bloco)
        destaque = _primeiro(r'header-benefit-text-big[^>]*>(.*?)<', bloco)
        preco = re.search(r'data-original-price="([^"]+)"', bloco)
        codigos = re.findall(r'data-code-rgc="([^"]+)"', bloco)
        if not plano or not preco:
            continue
        # o texto do card para classificar o bundle: so ate o proximo card
        texto = re.sub(r"<[^>]+>", " ", bloco[:12000])
        cards.append({
            "plano": _html.unescape(plano),
            "destaque": _html.unescape(destaque) if destaque else None,
            "preco": so_numero(preco.group(1)),
            "codigo_anatel": codigos[0] if codigos else None,
            "codigos_anatel": codigos or None,
            "texto": _html.unescape(re.sub(r"\s+", " ", texto)),
        })
    return cards, None


# ------------------------------------------------------- catalogo (indice)

def indice_catalogo(op, nomes=("controle", "fibra", "total")):
    """Indexa o catalogo por codigo Anatel, para enriquecer a vitrine.

    Nao vira universo: so entra aqui o que a vitrine ja tiver encontrado.
    """
    idx, avisos = {}, []
    for nome in nomes:
        s, corpo = buscar(op, CATALOGO % nome,
                          extras=cabecalhos_api("https://internet.vivo.com.br"))
        if s != 200:
            avisos.append("catalogo %s: HTTP %s" % (nome, s))
            time.sleep(PAUSA)
            continue
        try:
            cards = json.loads(corpo).get("cards", [])
        except Exception as e:
            avisos.append("catalogo %s: %s" % (nome, e))
            time.sleep(PAUSA)
            continue
        for c in cards:
            for cod in (c.get("anatelCode") or []):
                if cod:
                    idx.setdefault(cod, c)
        time.sleep(PAUSA)
    return idx, avisos


def enriquecer(oferta, card):
    """Acrescenta o que o catalogo sabe e a vitrine nao mostra."""
    if not card:
        return oferta
    oferta["preco_cheio"] = preco_cheio_valido(card.get("oldPrice"))
    oferta["campanha"] = [r for r in (card.get("regional") or []) if r] or None
    oferta["id_catalogo"] = card.get("id") or card.get("idOffer")
    detalhes = json.dumps(card, ensure_ascii=False)
    if oferta.get("nivel_bundle") in (None, 0):
        oferta["nivel_bundle"] = nivel_bundle(detalhes)
    return oferta


# ------------------------------------------------------------------ coleta

def trocar_praca(op, cidade, uf):
    extras = cabecalhos_api("https://vivo.com.br")
    extras["Sec-Fetch-Site"] = "same-origin"
    extras["X-Requested-With"] = "XMLHttpRequest"
    s, corpo = buscar(op, TROCA_PRACA % (urllib.parse.quote(cidade), uf),
                      metodo="POST", extras=extras)
    return s == 200 and '"success":true' in corpo


def coletar(cidade, uf, verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    op, _ = navegador()
    saida = {"operadora": "Vivo", "praca": "%s/%s" % (cidade, uf),
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR VIVO  |  %s/%s  |  %s" % (cidade, uf, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    if not trocar_praca(op, cidade, uf):
        saida["avisos"].append("praca %s/%s nao fixou - dado pode ser de Sao Paulo" % (cidade, uf))
        if verbose:
            print("  AVISO: a praca nao fixou")
    elif verbose:
        print("  praca fixada em %s/%s" % (cidade, uf))
    time.sleep(PAUSA)

    idx, avisos = indice_catalogo(op)
    saida["avisos"].extend(avisos)
    if verbose:
        print("  catalogo indexado: %d ofertas com codigo Anatel" % len(idx))

    for produto in ("controle", "movel", "fibra"):
        cards, err = ler_vitrine(op, produto)
        if err:
            saida["avisos"].append("vitrine %s: %s" % (produto, err))
            if verbose:
                print("  vitrine %-9s FALHOU (%s)" % (produto, err))
            time.sleep(PAUSA)
            continue

        for c in cards:
            destaque = c["destaque"]
            oferta = {
                "operadora": "Vivo",
                "produto": produto,
                "praca": "%s/%s" % (cidade, uf),
                "capturado_em": agora.isoformat(),
                "nome_oferta": c["plano"],
                "destaque": destaque,
                "degrau_mbps": degrau_mbps(destaque) if produto == "fibra" else None,
                "franquia_anunciada_gb": degrau_gb(destaque) if produto != "fibra" else None,
                # preco cheio fica vazio quando a fonte nao informa (decisao 9)
                "preco_cheio": None,
                "preco_promocional": c["preco"],
                "nivel_bundle": nivel_bundle(c["texto"]),
                "codigo_anatel": c["codigo_anatel"],
                "campanha": None,
                "id_catalogo": None,
            }
            saida["ofertas"].append(enriquecer(oferta, idx.get(c["codigo_anatel"])))

        if verbose:
            print("  vitrine %-9s %d ofertas" % (produto, len(cards)))
        time.sleep(PAUSA)

    return saida


def main():
    # o console do Windows usa cp1252 e corrompe acento e JSON;
    # no servidor Linux ja e utf-8, entao isto e inofensivo la
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--praca", default="Sao Paulo/SP")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cidade, uf = a.praca.split("/")
    # com --json a saida precisa ser so o JSON, senao o arquivo nao parseia
    d = coletar(cidade, uf, verbose=not a.json)

    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    for produto, titulo in (("controle", "CONTROLE"), ("movel", "POS-PAGO"), ("fibra", "FIBRA")):
        ofertas = [o for o in d["ofertas"] if o["produto"] == produto]
        if not ofertas:
            continue
        print("\n--- %s (%d ofertas em %s/%s) ---" % (titulo, len(ofertas), cidade, uf))
        chave = (lambda o: o["degrau_mbps"] or 0) if produto == "fibra" \
            else (lambda o: o["preco_promocional"] or 0)
        for o in sorted(ofertas, key=chave):
            cheio = "de R$ %g  " % o["preco_cheio"] if o["preco_cheio"] else ""
            print("  %-34s %-9s %sR$ %-8g nivel %s  %s" % (
                (o["nome_oferta"] or "?")[:34], o["destaque"] or "-", cheio,
                o["preco_promocional"] or 0, o["nivel_bundle"],
                o["codigo_anatel"] or ""))

    entrada = [o for o in d["ofertas"] if o["produto"] == "controle" and o["preco_promocional"]]
    if entrada:
        e = min(entrada, key=lambda o: o["preco_promocional"])
        print("\n  PLANO DE ENTRADA DO CONTROLE: %s, %s, R$ %g" % (
            e["nome_oferta"], e["destaque"], e["preco_promocional"]))

    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
