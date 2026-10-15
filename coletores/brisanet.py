"""Coletor da Brisanet.

A fonte mais rica das seis. A Brisanet expoe uma API GraphQL (Strapi) que
filtra ofertas POR CIDADE e - unica junto com a Vivo - devolve preco cheio
e preco com desconto em campos separados, sem precisar deduzir nada:

    price { original_price, discount_price }

O token de acesso vem embutido no JavaScript do proprio site, o mesmo que
qualquer visitante recebe ao abrir a pagina. E lido em tempo de execucao
em vez de fixado no codigo: quando a Brisanet trocar, o coletor acompanha
sozinho em vez de quebrar em silencio.

COBERTURA MEDIDA (30/09/2026): 398 cidades ativas. Das 9 pracas nordestinas
da nossa cesta, a Brisanet atende 7 - Salvador e Sao Luis ficam de fora.
Isso e ausencia esperada, nao falha.

Uso:  python coletores/brisanet.py [--praca "Fortaleza/CE"]
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

from . import rede
from . import apps
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

PAUSA = 3
SITE = "https://www.brisanet.com.br"
API = "https://produtos.brisanet.net.br/api/cmsbrisasite/p1//graphql"

CAMPOS = """
  documentId
  offer_name
  plan_speed
  description
  additional_details
  price { price_note original_price discount_price }
  included_products(filters: { isActive: { eq: true } }) { name }
"""

PAGINAS = {
    "fibra": "fetchInternetPage",
    "combo": "comboPageQuery",
}

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "skyplus", "brisaplay"}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").upper()


def _http(url, dados=None, cabecalhos=None, timeout=45, avisos=None):
    """Devolve o corpo, e levanta se nao conseguir - como antes.

    A retentativa entra por dentro: quem chama continua tratando a falha
    do mesmo jeito, so que ela agora significa "nao respondeu em tres
    tentativas" em vez de "nao respondeu de primeira".
    """
    def uma():
        req = urllib.request.Request(url, data=dados,
                                     method="POST" if dados else "GET")
        req.add_header("User-Agent", UA)
        for k, v in (cabecalhos or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:
            return 0, "ERRO: %s" % e

    status, corpo = rede.insistir(uma, url, avisos=avisos)
    if status == 0 or status >= 400:
        raise RuntimeError("HTTP %s em %s" % (status, url))
    return corpo


def descobrir_token():
    """Le o token publico do bundle do site, em vez de fixar no codigo.

    Token fixo no codigo e bomba-relogio: no dia em que a operadora trocar,
    a coleta volta vazia todo dia ate alguem perceber.
    """
    h = _http(SITE, cabecalhos={"Accept": "text/html", "Accept-Encoding": "identity"})
    for caminho in sorted(set(re.findall(r'/_next/static/chunks/[a-zA-Z0-9._/-]+\.js', h))):
        try:
            js = _http(SITE + caminho, timeout=30)
        except Exception:
            continue
        m = re.search(r'Bearer\s+([A-Za-z0-9_\-\.]{40,})', js)
        if m:
            return m.group(1), None
    return None, "token nao encontrado no site - o bundle mudou de formato"


def gql(token, query, variaveis=None):
    corpo = {"query": query}
    if variaveis:
        corpo["variables"] = variaveis
    try:
        bruto = _http(API, json.dumps(corpo).encode(), {
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Origin": SITE, "Referer": SITE + "/"})
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, str(e)
    d = json.loads(bruto)
    if d.get("errors"):
        return None, json.dumps(d["errors"])[:200]
    return d.get("data"), None


def achar_cidade(token, cidade, uf):
    q = ('query { cities(filters:{active:{eq:true}} sort:"name:asc" '
         'pagination:{pageSize:1000}) { documentId name state { UF } } }')
    d, err = gql(token, q)
    if err:
        return None, "cidades: %s" % err
    alvo = sem_acento(cidade)
    for c in d.get("cities", []):
        if sem_acento(c.get("name")) == alvo and (c.get("state") or {}).get("UF") == uf:
            return c["documentId"], None
    return None, "a Brisanet nao atende %s/%s" % (cidade, uf)


def mbps(txt):
    if not txt:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps|m\b|g\b)", str(txt).lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def numero(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:[,.](\d{1,2}))?", str(x))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def nivel_bundle(texto, produtos):
    # a Brisanet nomeia o que vem junto na lista de produtos contratados,
    # nao so na descricao: as duas coisas sao lidas como um texto so
    tudo = (texto or "") + " " + " ".join(produtos or ())
    if "tv por assinatura" in tudo.lower() or "canais" in tudo.lower():
        return 4
    return apps.nivel_por_apps(tudo, piso=1 if produtos else 0)


def fim_da_promocao(nota):
    """Le o price_note: "No 13o mes o valor sera R$ 109,90".

    A Brisanet declara por quanto tempo o desconto vale e qual sera o
    preco depois - a propria operadora respondendo se o preco de hoje e
    temporario. Nenhuma das outras cinco diz isso de forma direta.
    """
    if not nota:
        return None, None
    mes = re.search(r"(\d{1,2})\s*[ºo°]?\s*m[eê]s", str(nota), re.I)
    valor = re.search(r"R\$\s*([\d.]+,\d{2})", str(nota))
    meses = (int(mes.group(1)) - 1) if mes else None     # "13o mes" = 12 de desconto
    return meses, (numero(valor.group(1)) if valor else None)


def coletar(cidade, uf, verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Brisanet", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR BRISANET  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    token, err = descobrir_token()
    if err:
        saida["avisos"].append(err)
        return saida
    time.sleep(PAUSA)

    city_id, err = achar_cidade(token, cidade, uf)
    if err:
        saida["avisos"].append(err)
        if verbose:
            print("  %s" % err)
        return saida
    if verbose:
        print("  cidade %s -> %s" % (cidade, city_id))
    time.sleep(PAUSA)

    for produto, nome_query in PAGINAS.items():
        raiz = {"fetchInternetPage": "internetPage",
                "comboPageQuery": "comboPage"}[nome_query]
        q = ("query($cityId: ID) { %s { Offers { tab_name offers(filters: { or: ["
             "{ cities: { documentId: { eq: $cityId } } },"
             "{ city_selector: { cities: { documentId: { eq: $cityId } } } } ],"
             "active_offer: { eq: true } }) { %s } } } }" % (raiz, CAMPOS))
        d, err = gql(token, q, {"cityId": city_id})
        if err:
            saida["avisos"].append("%s: %s" % (produto, err))
            if verbose:
                print("  %-6s FALHOU (%s)" % (produto, err[:70]))
            time.sleep(PAUSA)
            continue

        grupos = ((d.get(raiz) or {}).get("Offers") or [])
        n = 0
        for g in grupos:
            for o in (g.get("offers") or []):
                preco = o.get("price") or {}
                meses_desc, preco_depois = fim_da_promocao(preco.get("price_note"))
                produtos = [p.get("name") for p in (o.get("included_products") or []) if p.get("name")]
                contexto = " ".join(filter(None, [o.get("offer_name"), o.get("description"),
                                                  o.get("additional_details")]))
                saida["ofertas"].append({
                    "operadora": "Brisanet", "produto": produto, "praca": praca,
                    "capturado_em": agora.isoformat(),
                    "nome_oferta": o.get("offer_name"),
                    "destaque": o.get("plan_speed"),
                    "degrau_mbps": mbps(o.get("plan_speed")),
                    "franquia_anunciada_gb": None,
                    "franquia_contratual_gb": None,
                    # a Brisanet entrega os dois separados, sem deducao
                    "preco_cheio": numero(preco.get("original_price")),
                    "preco_promocional": numero(preco.get("discount_price")) or numero(preco.get("original_price")),
                    "nivel_bundle": nivel_bundle(contexto, produtos),
                    "apps": produtos or None,
                    # a Brisanet diz quanto o desconto dura e o preco depois
                    "meses_desconto": meses_desc,
                    "preco_pos_promocao": preco_depois,
                    "nota_preco": preco.get("price_note"),
                    "id_catalogo": o.get("documentId"),
                    "aba": g.get("tab_name"),
                    "codigo_anatel": None, "campanha": None,
                })
                n += 1
        if verbose:
            print("  %-6s %d ofertas" % (produto, n))
        time.sleep(PAUSA)

    return saida


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--praca", default="Fortaleza/CE")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cidade, uf = a.praca.split("/")
    d = coletar(cidade, uf, verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    for produto in ("fibra", "combo"):
        ofs = [o for o in d["ofertas"] if o["produto"] == produto]
        if not ofs:
            continue
        print("\n--- %s (%d) ---" % (produto.upper(), len(ofs)))
        for o in sorted(ofs, key=lambda x: x["degrau_mbps"] or 0):
            cheio = "de R$ %g " % o["preco_cheio"] if o["preco_cheio"] else ""
            print("  %-32s %-10s %sR$ %-8g nivel %s" % (
                (o["nome_oferta"] or "?")[:32], o["destaque"] or "-", cheio,
                o["preco_promocional"] or 0, o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
