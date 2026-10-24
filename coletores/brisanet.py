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


# Abaixo disto, numero sem unidade nao da para interpretar: pode ser
# Mbps de um plano que nao existe, ou Giga escrito sem o "G". Nao se
# grava - campo vazio ja e tratado, numero mil vezes errado nao.
PISO_MBPS = 20


def mbps(txt):
    """A velocidade em Mbps, do jeito que a Brisanet publica.

    A API manda plan_speed como NUMERO PURO: "500", "700", "1000". A
    versao anterior exigia unidade no texto e devolvia None em todas -
    119 linhas por dia sem velocidade, sem R$/Mbps, e a chave de
    continuidade caindo para degrau 0, o que juntava 500 e 1000 Mbps na
    mesma serie.
    """
    if not txt:
        return None
    t = str(txt).strip().lower()

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps|gb|mb|m\b|g\b)", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        return int(v * 1000) if m.group(2).startswith("g") else int(v)

    # numero sozinho: e Mbps, que e como a Brisanet manda
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)", t)
    if m:
        v = float(m.group(1).replace(",", "."))
        return int(v) if v >= PISO_MBPS else None
    return None


# Os GB de movel dentro do nome de um combo: "AGO26 500MB + 20GB".
# Exige a unidade GB, para nao confundir com o "500MB" da fibra que vem
# antes na mesma frase.
GB_DO_MOVEL = re.compile(r"(\d{1,4})\s*GB\b", re.I)

# Franquia de movel em combo nao desce disto. Numero menor junto de
# GB e velocidade de fibra escrita em Giga, nao franquia.
PISO_GB_MOVEL = 5


def gb_movel(nome):
    """Os GB de movel anunciados no nome do combo, ou None.

    A Brisanet nao tem campo para isso: poe no nome, depois da
    velocidade. Sem ler daqui, dois combos de 500 Mbps aparecem iguais
    quando um traz 20 GB de movel e o outro nao traz movel nenhum.
    """
    # A ULTIMA ocorrencia, e nao a primeira: em "1GB ESSENCIAL + 20GB" o
    # primeiro GB e a velocidade da fibra em Giga e o segundo e a
    # franquia do movel. No nome da Brisanet o movel vem depois da fibra.
    achados = GB_DO_MOVEL.findall(nome or "")
    if not achados:
        return None
    v = int(achados[-1])
    return v if v >= PISO_GB_MOVEL else None


def numero(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:[,.](\d{1,2}))?", str(x))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def _apps_da_brisanet(oferta, produtos):
    """Os apps da oferta, pelas DUAS leituras do dicionario.

    O modulo separa os padroes em dois: os do NOME da oferta, que podem
    ser frouxos porque o nome e curto e deliberado, e os da PROSA do
    card, que precisam ser rigorosos para "compre na Amazon" nao virar
    app incluso.

    O que a Brisanet manda e nome nos dois casos - o titulo da oferta e
    a lista de produtos da API -, e cada lista pega o que a outra perde:
    o nome sozinho perdia Max, Telecine e Sky; o texto sozinho perdia a
    Amazon. Aqui nao ha prosa, entao valem as duas.
    """
    nome = oferta.get("offer_name") or ""
    tudo = "%s %s" % (nome, " ".join(produtos or ()))
    achados = list(apps.apps_do_texto(tudo))
    # sem operadora: so nome proprio de app. "Brisanet Entretenimento
    # 500MB" nao inclui a TV da Vivo (auditoria 19)
    for a in apps.apps_da_oferta(tudo):
        if a not in achados:
            achados.append(a)
    return achados


def nivel_bundle(texto, produtos):
    # a Brisanet nomeia o que vem junto na lista de produtos contratados,
    # nao so na descricao: as duas coisas sao lidas como um texto so
    tudo = (texto or "") + " " + " ".join(produtos or ())
    if "tv por assinatura" in tudo.lower() or "canais" in tudo.lower():
        return 4
    return apps.nivel_por_apps(tudo, piso=1 if produtos else 0)


# UM DEGRAU DA NOTA: o mes em que o preco muda, e o preco dele, lidos
# JUNTOS. Eram dois re.search independentes - o primeiro mes e o
# primeiro valor -, e numa nota de dois degraus isso casava o mes de um
# com o preco do outro:
#
#   "Do 7o ao 12o mes R$ 89,90. No 13o mes o valor sera R$ 109,90"
#       antes:  6 meses, R$ 89,90   (o degrau do MEIO)
#       agora: 12 meses, R$ 109,90  (o de regime)
#
# O [^.;]{0,40} e o que mantem os dois na mesma oracao: "No 13o mes o
# valor sera R$ 109,90" tem quatorze caracteres entre o "mes" e o "R$".
PASSO_DA_NOTA = re.compile(
    r"(\d{1,2})\s*[\u00ba\u00b0o]?\s*m[e\u00ea]s[^.;]{0,40}?R\$\s*([\d.]+,\d{2})",
    re.I)

MES_DA_NOTA = re.compile(r"(\d{1,2})\s*[\u00ba\u00b0o]?\s*m[e\u00ea]s", re.I)
VALOR_DA_NOTA = re.compile(r"R\$\s*([\d.]+,\d{2})")


def fim_da_promocao(nota):
    """Le o price_note: "No 13o mes o valor sera R$ 109,90".

    A Brisanet declara por quanto tempo o desconto vale e qual sera o
    preco depois - a propria operadora respondendo se o preco de hoje e
    temporario. Nenhuma das outras cinco diz isso de forma direta.

    VALE O ULTIMO DEGRAU, que e o de regime. Nota com mais de um degrau
    ("do 7o ao 12o mes R$ 89,90; no 13o mes R$ 109,90") daria o degrau
    intermediario se valesse o primeiro - seis meses de desconto onde
    sao doze, e o preco do meio como se fosse o definitivo.

    Medido em 24/10/2026: as dez ofertas de Fortaleza tem nota de um
    degrau so, entao isto e guarda e nao conserto de hoje. Com um degrau
    o resultado e o mesmo de antes.
    """
    if not nota:
        return None, None
    nota = str(nota)
    passos = [(int(m.group(1)), numero(m.group(2)))
              for m in PASSO_DA_NOTA.finditer(nota)]
    if passos:
        # "13o mes" quer dizer 12 meses de desconto: o preco novo vale A
        # PARTIR do 13o
        mes, valor = max(passos)
        return mes - 1, valor
    # NOTA QUE NAO PAREIA NAO PERDE O QUE DAVA. Quando ela anuncia o mes
    # e nao diz o preco - ou o contrario -, vale o que estiver escrito.
    mes = MES_DA_NOTA.search(nota)
    valor = VALOR_DA_NOTA.search(nota)
    return ((int(mes.group(1)) - 1) if mes else None,
            numero(valor.group(1)) if valor else None)


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

    # o que ja entrou, para a oferta que aparece nas duas consultas nao
    # ser gravada duas vezes
    vistas = set()
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
            # A ABA MANDA NO PRODUTO, e nao o nome da query.
            #
            # A fetchInternetPage devolve DUAS abas: "Internet", com
            # fibra pura, e "Combos", com fibra mais movel. O coletor
            # rotulava as duas como fibra porque olhava o nome da
            # consulta - e capturava tab_name sem usar.
            #
            # Tres estragos de uma vez. A oferta contava em dobro,
            # porque a consulta de combo traz parte das mesmas. O combo
            # disputava degrau com fibra pura levando um preco que
            # inclui movel, o que empurra o R$/Mbps da fibra para cima.
            # E a copia errada perdia a franquia, porque gb_movel so e
            # lido quando o produto e combo.
            #
            # NAO DA PARA SO DESCARTAR A ABA: medido em Fortaleza, ela
            # tem 10 ofertas e a consulta de combo tem 6 - cinco combos
            # existem so ali, e descartar some com eles. Oferta que some
            # vira "a operadora tirou o produto" no comparador.
            aba = (g.get("tab_name") or "").strip().lower()
            produto_real = "combo" if "combo" in aba else produto
            for o in (g.get("offers") or []):
                preco = o.get("price") or {}
                meses_desc, preco_depois = fim_da_promocao(preco.get("price_note"))
                produtos = [p.get("name") for p in (o.get("included_products") or []) if p.get("name")]
                contexto = " ".join(filter(None, [o.get("offer_name"), o.get("description"),
                                                  o.get("additional_details")]))
                # A MESMA OFERTA NAS DUAS CONSULTAS ENTRA UMA VEZ SO.
                # documentId e a identidade que a propria API da; sem
                # ele, nome e preco.
                ident = (o.get("documentId")
                         or (o.get("offer_name"), (preco or {}).get("price")))
                if ident in vistas:
                    continue
                vistas.add(ident)
                saida["ofertas"].append({
                    "operadora": "Brisanet", "produto": produto_real,
                    "praca": praca,
                    "capturado_em": agora.isoformat(),
                    "nome_oferta": o.get("offer_name"),
                    "destaque": o.get("plan_speed"),
                    "degrau_mbps": mbps(o.get("plan_speed")),
                    # no combo, os GB do movel estao no nome da oferta
                    "franquia_anunciada_gb": (
                        gb_movel(o.get("offer_name"))
                        if produto_real == "combo" else None),
                    "franquia_contratual_gb": None,
                    # a Brisanet entrega os dois separados, sem deducao
                    "preco_cheio": numero(preco.get("original_price")),
                    "preco_promocional": numero(preco.get("discount_price")) or numero(preco.get("original_price")),
                    "nivel_bundle": nivel_bundle(contexto, produtos),
                    # O NOME DA OFERTA E A LISTA DA API, juntos. A lista
                    # sozinha perde a Netflix de "AGO26 600MB + NETFLIX
                    # PCA"; o nome sozinho perde o Prime video que so a
                    # lista traz. E o resultado sai em CHAVES do
                    # dicionario, como nos outros coletores - antes aqui
                    # iam nomes de exibicao, que a tela nao resolve.
                    "apps": _apps_da_brisanet(o, produtos) or None,
                    "apps_rotulo": apps.rotulo(
                        _apps_da_brisanet(o, produtos),
                        o.get("offer_name"), " ".join(produtos or ())),
                    # a lista crua nao se perde: e de onde ela veio
                    "produtos_api": produtos or None,
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
