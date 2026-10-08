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
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import apps
from . import rede
import zipfile
from datetime import date, datetime, timedelta, timezone

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
    "combo": "https://vivo.com.br/para-voce/produtos-e-servicos/combos/vivo-total",
    "prepago": "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/pre-pago/vivo-pre",
}

# A linha de defesa, fora da vitrine principal: preco menor, sem
# aparecer no portfolio anunciado. Ler junto e o que impede o tracker de
# dizer que a Vivo entra a R$ 59 quando ela entra a R$ 45.
LITE = "https://vivo.com.br/para-voce/produtos-e-servicos/planos-lite"

APPS_CATALOGO = {"skeelo", "goread", "nba", "hube", "super comics", "atma",
                 "btfit", "mcafee", "ubook", "forbes", "casa do saber",
                 "vivo home fix", "nfl", "gemini"}
# Servicos de assinatura que a operadora inclui no plano. Nao sao so
# streamings de video: apurado em 07/10/2026 na vitrine, a Vivo inclui
# telemedicina ("Vale Saude Sempre") e educacao ("Vivae") do mesmo jeito
# que inclui Netflix - assinatura paga de terceiro, embutida no preco.
# Tratar essas como "app de catalogo" subestimava o pacote.
STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine",
              # faltavam: o plano "Controle YouTube Premium" caia em nivel 1
              "youtube premium", "deezer",
              # assinaturas de outra natureza, mesmo peso no bolso
              "vale saude", "vivae"}

# TV linear inclusa. "Vivo TV Inicial" e o que vem no Controle
# Entretenimento, e sem esta marca ele era lido como app de catalogo.
TV_INCLUSA = ("tv por assinatura", "canais", "vivo tv")


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


def buscar(op, url, metodo="GET", extras=None, timeout=45, avisos=None):
    def uma():
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
    # soluco de rede nao pode custar o produto do dia (ver coletores/rede.py)
    return rede.insistir(uma, url, avisos=avisos)


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
    if any(m in t for m in TV_INCLUSA):
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


# ------------------------------------------------- regulamento (contrato)

REGULAMENTO = "https://vivo.com.br/bin/vivo-portal/rgc-offer-json-file?anatelCode=%s"

# Cache da rodada: as 20 pracas compartilham os mesmos ~25 codigos, entao
# sem isto seriam 500 downloads de 500 KB para baixar 25 documentos.
_cache_regulamento = {}
_falhas_regulamento = []


def regulamento(op, codigo):
    """Baixa o regulamento da Anatel e devolve o que a vitrine nao mostra.

    E aqui que moram preco de tabela, fidelidade, multa, taxa de instalacao
    e a franquia CONTRATUAL - a que esta no contrato, sem o bonus que expira.
    So a Vivo publica isso em formato estruturado.

    O arquivo vem como ZIP com um JSON dentro, e o encoding varia.
    """
    if codigo in _cache_regulamento:
        return _cache_regulamento[codigo]

    extras = cabecalhos_api("https://vivo.com.br")
    extras["Sec-Fetch-Site"] = "same-origin"
    try:
        req = urllib.request.Request(REGULAMENTO % codigo)
        for k, v in extras.items():
            req.add_header(k, v)
        with op.open(req, timeout=60) as r:
            bruto = r.read()
        z = zipfile.ZipFile(io.BytesIO(bruto))
        cru = z.read(z.namelist()[0])
        dados = None
        for enc in ("utf-8", "latin-1"):
            try:
                dados = json.loads(cru.decode(enc))
                break
            except Exception:
                continue
        oferta = (dados or {}).get("ofertas", [{}])[0] if dados else None
        if oferta is None:
            _falhas_regulamento.append("%s: ZIP sem JSON legivel" % codigo)
    except Exception as e:
        # Engolir a falha aqui foi um erro de projeto: o enriquecimento
        # sumia sem deixar rastro, e a base saia sem fidelidade nem preco
        # de tabela como se a fonte nao tivesse esses campos.
        _falhas_regulamento.append("%s: %s" % (codigo, str(e)[:70]))
        oferta = None

    _cache_regulamento[codigo] = oferta
    return oferta


def _num(x):
    if x in (None, "", "null"):
        return None
    try:
        return float(str(x).replace(".", "").replace(",", "."))
    except Exception:
        return None


def aplicar_regulamento(oferta, reg):
    """Passa para a observacao o que o contrato diz."""
    if not reg:
        return oferta
    fid = reg.get("fidelizacao") or {}
    custo = reg.get("custoInicial") or {}
    smp = reg.get("SMP") or {}
    scm = reg.get("SCM") or {}

    # precoSemDescontos e o preco de tabela oficial - o campo que faltava.
    #
    # So entra se for MAIOR OU IGUAL ao que a vitrine cobra. O regulamento
    # as vezes cobre uma variante mais basica que o card: em "Vivo Familia
    # 2 + TV" ele traz R$ 270 contra R$ 290 do card, e gravado como "preco
    # cheio" isso inventaria um desconto de R$ 20 que nao existe. Quando as
    # duas fontes se contradizem, o campo fica vazio - nada e inventado.
    tabela = _num(reg.get("precoSemDescontos"))
    prom = oferta.get("preco_promocional")
    if tabela is not None and prom is not None and tabela < prom:
        oferta.setdefault("avisos_oferta", []).append(
            "regulamento diz R$ %.2f de tabela, abaixo dos R$ %.2f da vitrine"
            % (tabela, prom))
        tabela = None
    oferta["preco_cheio"] = tabela or oferta.get("preco_cheio")
    oferta["fidelidade_meses"] = int(_num(fid.get("tempoFidelizacao")) or 0) or None
    oferta["multa_fidelidade"] = _num(fid.get("multaFidelizacao"))
    oferta["taxa_instalacao"] = _num(custo.get("instalacao"))
    oferta["taxa_adesao"] = _num(custo.get("adesao"))

    # A franquia do regulamento so vale se nao contradisser o card.
    #
    # Os tres cards do Vivo Pre (5, 15 e 25 GB) dividem UM codigo Anatel:
    # o regulamento declara 20 GB, e carimbar isso nos tres dava ao plano
    # de 5 GB uma franquia contratual de 20 - mais do que ele anuncia.
    # Franquia garantida nao pode ser maior que a anunciada.
    franquia = (smp.get("franquiaDados") or {}).get("franquia")
    if franquia:
        v = int(_num(franquia) or 0) or None
        anunciada = oferta.get("franquia_anunciada_gb")
        if v and anunciada and v > anunciada:
            oferta.setdefault("avisos_oferta", []).append(
                "regulamento declara %s GB para um card de %s GB - codigo "
                "compartilhado entre variantes; franquia contratual nao gravada"
                % (v, anunciada))
        elif v:
            oferta["franquia_contratual_gb"] = v
    velo = (scm.get("velocidade") or {})
    if velo.get("download"):
        oferta["download_mbps"] = int(_num(velo["download"]) or 0) or None
        oferta["upload_mbps"] = int(_num(velo.get("upload")) or 0) or None
    if scm.get("listaTecnologia"):
        oferta["tecnologia"] = scm["listaTecnologia"]
    oferta["nome_regulamento"] = reg.get("nomeOferta")

    # Assinatura da composicao: o conjunto de codigos SVA, ordenado.
    #
    # Nao e preciso saber que app e cada codigo - o cruzamento mostrou que
    # a Vivo nao da para saber (so 1 dos 20 tem nome seguro). O que importa
    # e o CONJUNTO: se o preco nao se move e a assinatura muda, a oferta
    # trocou de conteudo sem trocar de etiqueta, que e o repasse disfarcado
    # da metodologia. Guardado em texto ordenado para comparar com "=".
    #
    # Os dois blocos entram juntos: no combo, movel e fixa declaram SVA
    # cada um, e ler so o primeiro perderia metade da composicao.
    sva = sorted({c for bloco in (smp, scm)
                  for c in (bloco.get("listaSVA") or []) if c})
    if sva:
        oferta["sva"] = sva
        oferta["assinatura_sva"] = "+".join(sva)
    return oferta


# ------------------------------------------------------------------ coleta

def trocar_praca(op, cidade, uf):
    extras = cabecalhos_api("https://vivo.com.br")
    extras["Sec-Fetch-Site"] = "same-origin"
    extras["X-Requested-With"] = "XMLHttpRequest"
    s, corpo = buscar(op, TROCA_PRACA % (urllib.parse.quote(cidade), uf),
                      metodo="POST", extras=extras)
    return s == 200 and '"success":true' in corpo


def _vigente(reg, hoje):
    """A oferta ainda vale hoje?

    A pagina do Lite serve codigo vencido junto com os vigentes - sem
    esta conferencia, o tracker gravaria como preco de hoje uma oferta
    que acabou ha tres meses.
    """
    fim = (reg or {}).get("dataFimOferta")
    if not fim:
        return True          # sem data declarada, vale o que a pagina mostra
    try:
        d, m, a = [int(x) for x in str(fim).split("/")]
    except (ValueError, TypeError):
        return True
    return date(a, m, d) >= hoje


def _produto_do_regulamento(reg):
    """Em que degrau do tracker esta oferta compete.

    A linha Lite e "Pos pago" na modalidade declarada, mas nao compete
    com o pos-pago: ela compete ABAIXO do Controle de entrada - e a
    oferta que segura o cliente sem mexer no portfolio anunciado. Posta
    no balde do pos, um plano de R$ 30 sumiria entre planos de R$ 150 e
    ninguem veria o piso real do mercado. Por isso e produto proprio.

    A de fibra continua em fibra: ali a Lite e so um degrau mais barato
    da mesma escada, com a mesma unidade de comparacao.
    """
    scm = reg.get("SCM") or {}
    if (scm.get("velocidade") or {}).get("download"):
        return "fibra"
    return "btl"


def ler_lite(op, hoje, avisos=None):
    """As ofertas Lite, pelo codigo Anatel que a pagina publica.

    Os cards vem por JavaScript e nao estao no HTML; o codigo Anatel
    esta. Como o regulamento traz preco, franquia, fidelidade e multa,
    ele basta - e e fonte melhor que card, porque e o que a operadora
    registrou na agencia.
    """
    status, html = buscar(op, LITE)
    if status != 200:
        return None, "HTTP %s" % status
    codigos = sorted(set(re.findall(r"VIV\d{12,}", html)))
    if not codigos:
        return None, "nenhum codigo Anatel na pagina - o formato mudou"

    ofertas, vencidos = [], 0
    for cod in codigos:
        reg = regulamento(op, cod)
        if not reg:
            continue
        if not _vigente(reg, hoje):
            vencidos += 1
            continue
        nome = reg.get("nomeOferta") or ""
        # "Vivo Lite + Celular" e o MESMO plano vendido junto com um
        # aparelho em 21x - a vitrine mostra R$ 100 a R$ 330 por mes, mas
        # o regulamento registra so a parte do servico, R$ 30. Gravar
        # assim criaria uma segunda linha de R$ 30 por 30 GB, identica a
        # do Lite Anual, e ainda esconderia o aparelho. O tracker compara
        # preco de SERVICO; pacote com aparelho fica de fora.
        if re.search(r"\+\s*celular|celular\s*\+", nome, re.I):
            continue
        produto = _produto_do_regulamento(reg)
        scm = reg.get("SCM") or {}
        smp = reg.get("SMP") or {}
        vel = (scm.get("velocidade") or {})
        franquia = (smp.get("franquiaDados") or {}).get("franquia")
        preco = _num(reg.get("precoSemDescontos"))
        if preco is None:
            continue
        mbps = None
        if vel.get("download"):
            mbps = int((_num(vel["download"]) or 0)
                       * (1000 if "g" in (vel.get("unidadeDownload") or "").lower() else 1))
        ofertas.append({
            "nome_oferta": reg.get("nomeOferta"),
            "destaque": ("%s Mbps" % mbps) if mbps else
                        ("%s GB" % franquia if franquia else None),
            "produto": produto,
            "degrau_mbps": mbps,
            "franquia_anunciada_gb": int(_num(franquia) or 0) or None,
            "preco_promocional": preco,
            "codigo_anatel": cod,
            # a marca que separa esta linha da vitrine anunciada
            "linha": "lite",
        })
    if vencidos and avisos is not None:
        avisos.append("lite: %d codigo(s) com vigencia encerrada, ignorados" % vencidos)
    if not ofertas:
        return None, "nenhuma oferta Lite vigente"
    return ofertas, None


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

    for produto in ("controle", "movel", "fibra", "combo", "prepago"):
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
                # combo tem velocidade e franquia ao mesmo tempo; pela decisao
                # 16 ele e acompanhado pelo preco de entrada, entao guarda-se
                # o que o card destaca e nao se tenta decompor o pacote
                "degrau_mbps": degrau_mbps(destaque) if produto in ("fibra", "combo") else None,
                "franquia_anunciada_gb": degrau_gb(destaque) if produto not in ("fibra", "combo") else None,
                # preco cheio fica vazio quando a fonte nao informa (decisao 9)
                "preco_cheio": None,
                "preco_promocional": c["preco"],
                "nivel_bundle": nivel_bundle(c["texto"]),
                # QUAIS apps, e nao so quantos: o nome da oferta e onde a
                # Vivo nomeia o app ("Vivo Controle Netflix", "Vivo Pos
                # com Disney+"). O codigo SVA nao distingue - vem igual
                # em todas as ofertas.
                "apps": apps.apps_da_oferta(c["plano"]),
                "apps_rotulo": apps.rotulo(apps.apps_da_oferta(c["plano"])),
                # o texto do card alimenta o cruzamento que deduz quais
                # apps correspondem a quais codigos SVA do regulamento
                "bruto_texto": c["texto"][:600],
                "codigo_anatel": c["codigo_anatel"],
                "campanha": None,
                "id_catalogo": None,
            }
            oferta = enriquecer(oferta, idx.get(c["codigo_anatel"]))
            if c["codigo_anatel"]:
                oferta = aplicar_regulamento(oferta, regulamento(op, c["codigo_anatel"]))
            saida["ofertas"].append(oferta)

        if verbose:
            print("  vitrine %-9s %d ofertas" % (produto, len(cards)))
        time.sleep(PAUSA)

    # A linha Lite, depois da vitrine. Nao entra no laco acima porque a
    # fonte e outra: o regulamento Anatel, e nao o card da pagina.
    lites, err = ler_lite(op, agora.date(), saida["avisos"])
    if err:
        saida["avisos"].append("lite: %s" % err)
        if verbose:
            print("  lite      FALHOU (%s)" % err)
    else:
        for o in lites:
            oferta = {
                "operadora": "Vivo",
                "praca": "%s/%s" % (cidade, uf),
                "capturado_em": agora.isoformat(),
                "preco_cheio": None,
                "nivel_bundle": 0,     # a linha Lite nao traz app incluso
                "campanha": None,
                "id_catalogo": None,
            }
            oferta.update(o)
            oferta = aplicar_regulamento(oferta, regulamento(op, o["codigo_anatel"]))
            saida["ofertas"].append(oferta)
        if verbose:
            print("  lite      %d ofertas" % len(lites))
        time.sleep(PAUSA)

    if _falhas_regulamento:
        saida["avisos"].append(
            "regulamento falhou em %d oferta(s) - fidelidade, multa e preco "
            "de tabela ficam vazios. Primeira: %s"
            % (len(_falhas_regulamento), _falhas_regulamento[0]))
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
