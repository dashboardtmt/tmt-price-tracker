"""Teste de geolocalizacao: o robo enxerga as pracas brasileiras de um servidor?

Responde duas perguntas, sem escrever nada em lugar nenhum:

  1. ACESSO      - o servidor consegue abrir o site, ou leva 403?
  2. REGIAO      - trocar de praca funciona, ou vem sempre Sao Paulo?

Gabarito medido do Brasil em 02/09/2026 (IP residencial, Sao Paulo):

  Vivo  Sao Paulo  -> vitrine de fibra COM 2 Giga e 10 Giga
  Vivo  Manaus     -> vitrine de fibra SEM 2 Giga e SEM 10 Giga
  TIM   /sp/       -> tem plano de R$ 79,99, nao tem R$ 99,99
  TIM   /rj/       -> tem plano de R$ 99,99, nao tem R$ 79,99

Se o servidor reproduzir essas diferencas, a coleta pode rodar nele.
Se vier tudo igual a Sao Paulo, o robo precisa de saida no Brasil.

Uso:  python testes/teste_geoip.py
"""

import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Cabecalhos completos, como um navegador de verdade manda.
# Medido em 24/09/2026: o catalogo da Vivo devolve 403 para requisicao "pelada"
# (so User-Agent) e 200 com o conjunto abaixo. O bloqueio e de cabecalho, nao
# de geografia.
CABECALHOS = [
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

# Para chamadas de API (XHR), o navegador troca os Sec-Fetch e manda origem.
def cabecalhos_api(origem):
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Origin": origem,
        "Referer": origem + "/",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

PAUSA = 4  # segundos entre requisicoes: o site da Vivo bloqueia rajada


def sessao():
    """Abre uma sessao que guarda cookies, como um navegador faria."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = list(CABECALHOS)
    return op, cj


def buscar(op, url, metodo="GET", timeout=45, extras=None):
    """Devolve (status, corpo). Nao levanta excecao em erro HTTP."""
    req = urllib.request.Request(url, method=metodo)
    for k, v in (extras or {}).items():
        req.add_header(k, v)
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        corpo = ""
        try:
            corpo = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, corpo
    except Exception as e:
        return 0, "ERRO DE REDE: %s" % e


def onde_estou():
    op, _ = sessao()
    s, corpo = buscar(op, "http://ip-api.com/json/?fields=country,city,isp,query")
    if s == 200:
        try:
            d = json.loads(corpo)
            return "%s / %s (%s) IP %s" % (d.get("country"), d.get("city"),
                                           d.get("isp"), d.get("query"))
        except Exception:
            pass
    return "nao identificado"


# ---------------------------------------------------------------- Vivo

VIVO_FIBRA = "https://vivo.com.br/para-voce/produtos-e-servicos/para-casa/internet"
VIVO_TROCA = ("https://vivo.com.br/bin/vivo-portal/service-layer/"
              "geolocation/locate-by-city?city=%s&state=%s")


def vivo_vitrine(html):
    """Extrai a vitrine de fibra: precos e velocidades dos cards."""
    precos = re.findall(r'data-original-price="([^"]+)"', html)
    velos = [re.sub(r"\s+", " ", v).strip()
             for v in re.findall(r'header-benefit-text-big">(.*?)</', html, re.S)]
    return precos, velos


def testa_vivo():
    print("\n" + "=" * 68)
    print("VIVO")
    print("=" * 68)
    op, cj = sessao()
    resultado = {"acesso": None, "sp": None, "manaus": None, "trocou": None}

    s, html = buscar(op, VIVO_FIBRA)
    print("  1. abrir a vitrine .................. HTTP %s (%d KB)" % (s, len(html) // 1024))
    if s != 200:
        print("     BLOQUEADO. O servidor nao consegue nem abrir a pagina.")
        resultado["acesso"] = False
        return resultado
    resultado["acesso"] = True

    pr_sp, ve_sp = vivo_vitrine(html)
    print("     cards encontrados: %d -> %s" % (len(pr_sp), ve_sp or pr_sp))
    resultado["sp"] = {"precos": pr_sp, "velocidades": ve_sp}
    if not pr_sp:
        print("     ATENCAO: pagina abriu mas nao tem cards. Pode ser")
        print("     desafio anti-bot ('Just a moment...') disfarcado de 200.")

    time.sleep(PAUSA)

    url = VIVO_TROCA % (urllib.parse.quote("Manaus"), "AM")
    extras = cabecalhos_api("https://vivo.com.br")
    extras["X-Requested-With"] = "XMLHttpRequest"
    extras["Sec-Fetch-Site"] = "same-origin"
    s2, corpo2 = buscar(op, url, metodo="POST", extras=extras)
    print("  2. pedir a praca de Manaus .......... HTTP %s -> %s" % (s2, corpo2[:60]))
    cookies = {c.name: c.value for c in cj}
    print("     cookies de regiao recebidos: %s" %
          {k: v for k, v in cookies.items() if "reg" in k or "city" in k or k == "regional"})

    time.sleep(PAUSA)

    s3, html3 = buscar(op, VIVO_FIBRA)
    print("  3. reabrir a vitrine ................ HTTP %s (%d KB)" % (s3, len(html3) // 1024))
    pr_mao, ve_mao = vivo_vitrine(html3)
    print("     cards encontrados: %d -> %s" % (len(pr_mao), ve_mao or pr_mao))
    resultado["manaus"] = {"precos": pr_mao, "velocidades": ve_mao}

    # o teste de verdade: 2 Giga e 10 Giga existem em SP e nao existem em Manaus
    tem_ultra_sp = any("2 Giga" in v or "10 Giga" in v for v in ve_sp)
    tem_ultra_ma = any("2 Giga" in v or "10 Giga" in v for v in ve_mao)
    if not ve_sp or not ve_mao:
        print("\n  VEREDITO: INCONCLUSIVO - nao deu para ler a vitrine.")
        resultado["trocou"] = None
    elif tem_ultra_sp and not tem_ultra_ma:
        print("\n  VEREDITO: FUNCIONA. A praca mudou (ultravelocidade sumiu em Manaus),")
        print("            igual ao gabarito medido do Brasil.")
        resultado["trocou"] = True
    elif tem_ultra_sp and tem_ultra_ma:
        print("\n  VEREDITO: NAO FUNCIONA. Pedimos Manaus e continuou vindo Sao Paulo.")
        print("            Um robo aqui coletaria a praca errada sem dar erro.")
        resultado["trocou"] = False
    else:
        print("\n  VEREDITO: INESPERADO - nem Sao Paulo veio como esperado.")
        resultado["trocou"] = None
    return resultado


# ----------------------------------------------------------------- TIM

TIM_PLANOS = "https://www.tim.com.br/%s/para-voce/planos"


def testa_tim():
    print("\n" + "=" * 68)
    print("TIM  (estado na URL - o mecanismo mais simples)")
    print("=" * 68)
    resultado = {}
    conjuntos = {}
    for uf in ("sp", "rj"):
        op, _ = sessao()
        s, html = buscar(op, TIM_PLANOS % uf)
        precos = set(re.findall(r"R\$\s?(\d{1,4}(?:[.,]\d{2})?)", html))
        print("  /%s/ ... HTTP %s (%d KB) | %d precos distintos" %
              (uf, s, len(html) // 1024, len(precos)))
        conjuntos[uf] = precos
        resultado[uf] = {"status": s, "kb": len(html) // 1024, "precos": sorted(precos)}
        time.sleep(PAUSA)

    if resultado["sp"]["status"] != 200 or resultado["rj"]["status"] != 200:
        print("\n  VEREDITO: BLOQUEADO.")
        return resultado

    so_sp = conjuntos["sp"] - conjuntos["rj"]
    so_rj = conjuntos["rj"] - conjuntos["sp"]
    print("  so em SP: %s" % (sorted(so_sp)[:8] or "nenhum"))
    print("  so em RJ: %s" % (sorted(so_rj)[:8] or "nenhum"))
    if so_sp or so_rj:
        print("\n  VEREDITO: FUNCIONA. Os estados trazem precos diferentes.")
        resultado["difere"] = True
    else:
        print("\n  VEREDITO: SUSPEITO. Os dois estados vieram identicos,")
        print("            quando do Brasil eles diferem.")
        resultado["difere"] = False
    return resultado


# ------------------------------------------------------ catalogo JSON da Vivo

def testa_catalogo():
    print("\n" + "=" * 68)
    print("CATALOGO JSON DA VIVO  (a fonte preferida: dado puro)")
    print("=" * 68)
    op, _ = sessao()
    url = "https://plataforma.portal.vivo.com.br/catalog/main/b2c/fibra.json"
    s, corpo = buscar(op, url, extras=cabecalhos_api("https://internet.vivo.com.br"))
    print("  HTTP %s (%d KB)" % (s, len(corpo) // 1024))
    if s == 200:
        try:
            d = json.loads(corpo)
            n = len(d.get("cards", []))
            print("  VEREDITO: ACESSIVEL - %d ofertas no catalogo." % n)
            return {"status": s, "ofertas": n}
        except Exception:
            print("  VEREDITO: abriu mas nao e JSON valido.")
    else:
        print("  VEREDITO: BLOQUEADO deste servidor.")
        print("  (do navegador, no Brasil, este endereco responde normalmente)")
    return {"status": s, "ofertas": None}


def main():
    print("=" * 68)
    print("TESTE DE GEOLOCALIZACAO - o robo enxerga as pracas brasileiras?")
    print("=" * 68)
    print("Rodando de: %s" % onde_estou())
    print("Pausa entre requisicoes: %ds" % PAUSA)

    r = {"origem": onde_estou()}
    r["vivo"] = testa_vivo()
    time.sleep(PAUSA)
    r["tim"] = testa_tim()
    time.sleep(PAUSA)
    r["catalogo"] = testa_catalogo()

    print("\n" + "=" * 68)
    print("RESUMO")
    print("=" * 68)
    vivo_ok = r["vivo"].get("trocou")
    tim_ok = r["tim"].get("difere")
    cat_ok = r["catalogo"].get("status") == 200
    print("  Vivo - troca de praca ....... %s" %
          {True: "FUNCIONA", False: "NAO FUNCIONA", None: "INCONCLUSIVO"}[vivo_ok])
    print("  TIM  - estado na URL ........ %s" %
          {True: "FUNCIONA", False: "NAO FUNCIONA", None: "INCONCLUSIVO"}.get(tim_ok, "INCONCLUSIVO"))
    print("  Vivo - catalogo JSON ........ %s" % ("ACESSIVEL" if cat_ok else "BLOQUEADO"))
    print()
    if vivo_ok and tim_ok:
        print("  >> Este servidor SERVE para a coleta.")
    elif vivo_ok is False:
        print("  >> Este servidor NAO SERVE: coletaria a praca errada em silencio.")
        print("     Sera preciso saida no Brasil (nuvem em Sao Paulo ou proxy).")
    else:
        print("  >> Inconclusivo. Ver o detalhe acima antes de decidir.")

    print("\n--- JSON ---")
    print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
