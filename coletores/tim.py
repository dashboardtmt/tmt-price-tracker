"""Coletor da TIM.

A TIM e a mais simples das seis: o estado esta na URL (/sp/, /rj/) e as
ofertas vem num JSON embutido no HTML, em drupalSettings.ofertas.

MAPA DOS CAMPOS (levantado em 30/09/2026). O Drupal da TIM tem dezenas de
campos e a maioria vem vazia ou reaproveitada de outro produto - o
field_destaque_gigas, por exemplo, traz "500 MEGA" numa pagina de celular.
So estes quatro sao confiaveis:

  field_subtitle           nome comercial   "TIM Controle Light Express"
  field_titulo             franquia         "45GB"
  field_preco_card_oferta  preco limpo      "60,99"
  field_information_text   composicao       "5GB plano + 20GB bonus promo + ..."

E dois que a TIM da de presente e ninguem mais da:

  langcode          a UF da oferta
  field_oferta_ddd  em quais DDDs ela vale - regionalizacao declarada,
                    nao inferida

Uso:  python coletores/tim.py [--praca "Sao Paulo/SP"]
"""

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import apps
from . import rede
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

PAUSA = 4

# A UF vai na URL. Nao ha cookie nem requisicao de troca de praca.
#
# RESOLVIDO em 07/10/2026: o Ultracombo existe, mas mora sob /internet/
# e nao sob /para-voce/ - por isso as cinco variacoes testadas em 01/10
# davam 404. A rota saiu do proprio sitemap.xml da TIM:
#     https://www.tim.com.br/{uf}/internet/tim-ultracombo
PAGINAS = {
    "controle": "https://www.tim.com.br/%s/para-voce/planos/controle",
    "movel": "https://www.tim.com.br/%s/para-voce/planos",
    # O pre vinha de carona na pagina geral, que mostra UM card. A pagina
    # propria tem tres (6GB/R$20, 8GB/R$25, 16GB/R$30).
    "prepago": "https://www.tim.com.br/%s/para-voce/planos/pre-pago",
}

# O combo tem pagina propria, com outro formato - ver ler_combos.
COMBO = "https://www.tim.com.br/%s/internet/tim-ultracombo"

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer"}
APPS_CATALOGO = {"tim mais", "ampli", "babbel", "funcional", "leia", "skeelo",
                 "aya", "exa", "tim games", "tim banca"}


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
    return op


def buscar(op, url, timeout=45, avisos=None):
    def uma():
        try:
            with op.open(urllib.request.Request(url), timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:
            return 0, "ERRO: %s" % e
    return rede.insistir(uma, url, avisos=avisos)


def texto(campo):
    """Le um campo do Drupal, tirando o HTML que vem junto."""
    if not isinstance(campo, list) or not campo or not isinstance(campo[0], dict):
        return None
    v = campo[0].get("value")
    if v is None:
        return None
    limpo = re.sub(r"<[^>]+>", " ", str(v))
    limpo = limpo.replace("&nbsp;", " ").replace("&amp;", "&")
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo or None


def numero(txt):
    if not txt:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?", str(txt))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def mbps(txt):
    if not txt:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps)", str(txt).lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def gb(txt):
    if not txt:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*gb", str(txt).lower())
    return int(float(m.group(1).replace(",", "."))) if m else None


def franquia_contratual(info):
    """'5GB plano + 20GB bonus promo + 20GB bonus especial' -> 5.

    A TIM soma bonus temporario na franquia anunciada. O primeiro numero,
    o que vem antes de 'plano', e o que esta no contrato - o resto expira.
    """
    if not info:
        return None
    m = re.search(r"(\d+)\s*gb\s*(?:d[oa]\s*)?(?:plano|oferta)", info.lower())
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


def classificar(nome, destaque):
    """A pagina geral da TIM mistura tudo: pre, controle, pos e fibra no
    mesmo array. Quem manda e o nome da oferta, nao a pagina onde ela
    apareceu - senao o pre-pago entra na serie do pos e polui a media."""
    n = (nome or "").lower()
    d = (destaque or "").lower()
    if "ultrafibra" in n or "fibra" in n or "mega" in d:
        return "fibra"
    if "controle" in n:
        return "controle"
    # sem \b na regex: o shell ja trocou isso por backspace uma vez,
    # e a regex passou meses casando so pelo ramo do "xip"
    if re.search(r"(^|[^a-z])pr[eé]([^a-z]|$)|xip", n):
        return "prepago"
    if "black" in n or "pos" in n or "pós" in n:
        return "movel"
    return "movel"


def ler_ofertas(op, url, uf):
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    m = re.search(r'<script[^>]*drupal-settings-json[^>]*>(.*?)</script>', h, re.S)
    if not m:
        return None, "drupalSettings ausente - a pagina mudou de formato"
    try:
        cru = json.loads(m.group(1)).get("ofertas", [])
    except Exception as e:
        return None, "JSON invalido: %s" % e

    saida = []
    for o in cru:
        nome = texto(o.get("field_subtitle")) or texto(o.get("field_filtro")) \
            or texto(o.get("field_nome_da_oferta"))
        preco = numero(texto(o.get("field_preco_card_oferta")))
        if not nome or preco is None:
            continue   # card decorativo, sem identidade ou sem preco
        info = texto(o.get("field_information_text"))
        titulo = texto(o.get("field_titulo"))
        contexto = " ".join(filter(None, [
            nome, info, titulo, texto(o.get("field_desc_beneficios_destaque")),
            texto(o.get("field_preco_principal_7_1_3"))]))
        saida.append({
            "nome_oferta": nome,
            "destaque": titulo or (("%dGB" % gb(info)) if gb(info) else None),
            "franquia_anunciada_gb": gb(titulo) or gb(info),
            "franquia_contratual_gb": franquia_contratual(info),
            "preco_promocional": preco,
            "nivel_bundle": nivel_bundle(contexto),
            "uf_declarada": o.get("langcode"),
            "ddds": len(o.get("field_oferta_ddd") or []) or None,
            "nid": (o.get("nid") or [{}])[0].get("value") if isinstance(o.get("nid"), list) else o.get("nid"),
            "composicao": info,
        })
    return saida, None


# O Ultracombo nao cabe no ler_ofertas: o drupalSettings dele traz os
# titulos certos mas o PRECO ERRADO - os tres cards de SP vem todos com
# "R$ 129,99", e o field_destaque_gigas diz "300 MEGA" em cima de ofertas
# de 500MEGA e 1GIGA. Sao restos de uma campanha anterior que ficaram no
# JSON. O preco de verdade esta no HTML renderizado, um por card:
#
#   TIM Ultracombo 7  500MEGA + 65GB  ... (10GB do plano + 50GB promo)
#   Aproveite com seu plano Ultracombo  Por R$89,99/mes
#
# Ler o texto e menos elegante que ler o JSON, mas aqui e o JSON que
# mente. O mesmo trecho ja separa franquia contratual de bonus.
CARD_COMBO = re.compile(
    r"TIM Ultracombo\s+(\d+)\s+"           # o numero do combo (5, 6, 7)
    r"(\d+)\s*(MEGA|GIGA)\s*\+\s*(\d+)\s*GB"   # 500MEGA + 65GB
    r"(.*?)"                                # a composicao, nao gulosa
    r"Por\s*R\$\s?(\d{1,3},\d{2})",         # Por R$89,99/mes
    re.I)


def beneficios_do_json(h):
    """titulo da oferta -> o que vem junto, declarado card a card.

    Os beneficios sao imagens, e o nome do arquivo e o unico lugar onde o
    nome do servico aparece: ".../Paramount%2B%20Icon%20(1).png". Entao a
    leitura e do caminho, com o %XX desfeito.
    """
    m = re.search(r'<script[^>]*drupal-settings-json[^>]*>(.*?)</script>', h, re.S)
    if not m:
        return {}
    try:
        ofs = json.loads(m.group(1)).get("ofertas", [])
    except Exception:
        return {}
    mapa = {}
    for o in ofs:
        titulo = texto(o.get("field_titulo"))
        if not titulo:
            continue
        pedacos = [texto(o.get("field_desc_beneficios_destaque")),
                   texto(o.get("field_desc_outros_beneficios"))]
        for campo in ("field_beneficios_destaque", "field_outros_beneficios",
                      "field_servico_destaque", "field_servicos_adicionais"):
            for item in (o.get(campo) or []):
                if not isinstance(item, dict):
                    continue
                pedacos.append(urllib.parse.unquote(str(item.get("value") or "")))
                for n in (item.get("name") or []):
                    if isinstance(n, dict):
                        pedacos.append(str(n.get("value") or ""))
        mapa[titulo.lower()] = " ".join(p for p in pedacos if p)
    return mapa


def ler_combos(op, url):
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    extras = beneficios_do_json(h)
    t = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)

    saida, vistos = [], set()
    for m in CARD_COMBO.finditer(t):
        n_combo, vel, unid, gigas, meio, preco = m.groups()
        if len(meio) > 400:
            continue          # casou atravessando dois cards
        mbps_ = int(vel) * (1000 if unid.upper() == "GIGA" else 1)
        nome = "TIM Ultracombo %s" % n_combo
        if nome in vistos:
            continue          # a pagina repete os cards no layout mobile
        vistos.add(nome)
        # "(10GB do plano + 50GB promo)": o primeiro numero e o que o
        # contrato garante; o resto e promocao, que pode cair na revisao
        mc = re.search(r"\((\d+)\s*GB do plano", meio, re.I)
        # o texto do card para o preco e a franquia; o JSON para o que
        # vem junto, que no texto so existe numa galeria compartilhada
        chave = ("%s%s + %sGB" % (vel, unid.upper(), gigas)).lower()
        junto = extras.get(chave, "")
        saida.append({
            "nome_oferta": "%s %s%s + %sGB" % (nome, vel, unid.upper(), gigas),
            "destaque": "%s%s + %sGB" % (vel, unid.upper(), gigas),
            "degrau_mbps": mbps_,
            "franquia_anunciada_gb": int(gigas),
            "franquia_contratual_gb": int(mc.group(1)) if mc else None,
            "preco_promocional": numero(preco),
            "nivel_bundle": nivel_bundle(meio + " " + junto),
            "composicao": (meio.strip() + (" | inclui: " + junto if junto else ""))[:400],
        })
    if not saida:
        return None, "nenhum card de combo reconhecido - a pagina mudou"
    return saida, None


def coletar(cidade, uf, verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    op = navegador()
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "TIM", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR TIM  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    for produto, molde in PAGINAS.items():
        url = molde % uf.lower()
        ofertas, err = ler_ofertas(op, url, uf)
        if err:
            saida["avisos"].append("%s: %s" % (produto, err))
            if verbose:
                print("  %-9s FALHOU (%s)" % (produto, err))
            time.sleep(PAUSA)
            continue

        for o in ofertas:
            real = classificar(o["nome_oferta"], o["destaque"])
            o.update({"operadora": "TIM", "produto": real, "praca": praca,
                      "pagina": produto,
                      "capturado_em": agora.isoformat(),
                      "preco_cheio": None,
                      "degrau_mbps": mbps(o["destaque"]) if real == "fibra" else None,
                      "codigo_anatel": None, "campanha": None})
            saida["ofertas"].append(o)
        if verbose:
            print("  %-9s %d ofertas" % (produto, len(ofertas)))
        time.sleep(PAUSA)

    # O combo, da pagina propria. Nao entra no laco acima porque o
    # formato e outro: texto renderizado em vez do array do drupalSettings.
    combos, err = ler_combos(op, COMBO % uf.lower())
    if err:
        saida["avisos"].append("combo: %s" % err)
        if verbose:
            print("  %-9s FALHOU (%s)" % ("combo", err))
    else:
        for o in combos:
            # o "inclui:" da composicao nomeia o que vem junto, e as
            # vezes tambem o tier ("Netflix Padrao")
            o["apps"] = apps.apps_do_texto(o.get("composicao"))
            _fontes = (o.get("composicao"), o.get("nome_oferta"))
            o["apps_rotulo"] = apps.rotulo(o["apps"], *_fontes)
            o["apps_planos"] = apps.planos_dos_apps(o["apps"], *_fontes)
            o.update({"operadora": "TIM", "produto": "combo", "praca": praca,
                      "pagina": "combo",
                      "capturado_em": agora.isoformat(),
                      "preco_cheio": None,
                      "codigo_anatel": None, "campanha": None})
            saida["ofertas"].append(o)
        if verbose:
            print("  %-9s %d ofertas" % ("combo", len(combos)))
    time.sleep(PAUSA)

    # A pagina geral repete ofertas da pagina de controle, com nid diferente
    # para o mesmo produto. Deduplica pelo que o cliente ve - nome, franquia
    # e preco - e nao pelo identificador interno do CMS.
    #
    # O nome precisa ser normalizado antes de comparar: a pagina geral
    # anuncia "TIM Pre XIP Plus - 16GB" e a pagina de pre anuncia o mesmo
    # plano como "TIM Pre XIP Plus". Com o sufixo, as duas passavam, e o
    # pre aparecia com uma oferta a mais do que existe.
    def identidade(o):
        nome = re.sub(r"\s*[-–]\s*\d+\s*GB\s*$", "", o["nome_oferta"] or "",
                      flags=re.I).strip().lower()
        return (nome, o["produto"], o.get("franquia_anunciada_gb"),
                o["preco_promocional"])

    vistos, unicas = set(), []
    for o in saida["ofertas"]:
        assinatura = identidade(o)
        if assinatura in vistos:
            continue
        vistos.add(assinatura)
        unicas.append(o)
    saida["ofertas"] = unicas
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
        for o in sorted(ofs, key=lambda x: x["preco_promocional"]):
            print("  %-34s %-8s R$ %-8g contratual %-5s nivel %s" % (
                o["nome_oferta"][:34], o["destaque"] or "-", o["preco_promocional"],
                o["franquia_contratual_gb"] or "-", o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
