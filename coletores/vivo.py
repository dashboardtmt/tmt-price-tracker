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

# AS PAGINAS QUE A VITRINE LINKA E A COLETA NAO LIA (auditoria de 26/11/2026).
# Todas no mesmo formato de card (unique-card, com codigo Anatel), entao a
# leitura e a mesma de VITRINE. (produto, endereco, sufixo do nome): o sufixo
# separa a oferta das homonimas da vitrine principal - "Vivo Familia 2" sem
# apps custa R$ 265 e a com apps R$ 270, mesmo nome, mesma franquia; sem o
# sufixo as duas cairiam na mesma serie e o robo leria reajuste todo dia.
#   - fibra com Netflix, Globoplay e Disney+ (600, 700 e 1 Giga, com e sem
#     TV): a pagina de internet mostra so o 600, num carrossel;
#   - o Vivo V 500 GB, do pos;
#   - as paginas "sem apps", que toda pagina da vitrine linka: pos, familia,
#     Vivo Total e controle. Mudam a entrada de alguns produtos (o Vivo Pos
#     sem apps de R$ 145 fica abaixo dos R$ 150 da vitrine), e e por isso
#     que entram: e preco que o cliente contrata.
# Card com o MESMO codigo Anatel de um ja lido nao entra de novo.
PAGINAS_EXTRAS = (
    ("fibra", "https://vivo.com.br/para-voce/produtos-e-servicos/para-casa/internet/internet-netflix", "com Netflix"),
    ("fibra", "https://vivo.com.br/para-voce/produtos-e-servicos/para-casa/internet/internet-globoplay", "com Globoplay"),
    ("fibra", "https://vivo.com.br/para-voce/produtos-e-servicos/para-casa/internet/internet-disney-plus", "com Disney+"),
    ("movel", "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-pos-pago/vivo-v", None),
    ("movel", "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-pos-pago/vivo-pos/sem-apps", "sem apps"),
    ("movel", "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-pos-pago/planos-familia-sem-apps", "sem apps"),
    ("combo", "https://vivo.com.br/para-voce/produtos-e-servicos/combos/vivo-total/vivo-total-sem-apps", "sem apps"),
    ("controle", "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/planos-controle/outros-planos", "sem apps"),
    # O PRE "SEM SERVICO DIGITAL", contratado por SMS: 4 GB por 10 dias (R$ 14),
    # 5 GB por 15 dias (R$ 16) e 10 GB por 30 dias (R$ 29). Era a recarga de
    # 15 dias que faltava na Vivo - o report da XP compara essa faixa, e no
    # tracker so a Claro aparecia nela (pergunta de quem le, 26/11/2026).
    ("prepago", "https://vivo.com.br/para-voce/produtos-e-servicos/para-o-celular/pre-pago/vivo-pre/pre-outras-ofertas", "sem serviço digital"),
)

# O CARD SEM NOME DE PLANO. Os cards do pre "sem servico digital" nao tem
# unique-card__plan - abrem pela franquia ("4 GB de internet 5G") -, e a
# leitura os descartava. Numa pagina extra, o nome e o do produto.
NOME_DO_PRODUTO = {"prepago": "Vivo Pré"}

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


def nivel_bundle(texto, lista=()):
    """O nivel da oferta, pelo texto do card E pela lista de apps dela.

    O NOME DA OFERTA CONTA. O card da Vivo as vezes vem so com
    marcacao - "unique-card__bordered data-settings=..." - e ai o texto
    nao nomeia app nenhum. A lista de apps, que sai do NOME, nomeia:
    "Vivo Pos com Amazon" aparecia com "Amazon Prime" na lista e nivel
    0 no campo ao lado.

    max() porque o nome ACRESCENTA informacao, nunca tira: o texto pode
    citar um streaming que o nome nao cita, e o contrario tambem.
    """
    t = (texto or "").lower()
    if any(m in t for m in TV_INCLUSA):
        return 4
    return max(apps.nivel_por_apps(texto, APPS_CATALOGO),
               apps.nivel_dos_apps(lista))


def apps_da_vitrine(plano, texto):
    """Os apps que a oferta inclui, pelo NOME e pelo TEXTO do card.

    Pelo mesmo argumento de nivel_bundle acima: o nome acrescenta
    informacao e nunca tira, e o texto tambem. A lista saia so do nome,
    e com isso 7 ofertas da vitrine de Sao Paulo em 21/10/2026 chegavam
    na tela sem dizer qual app incluem - as tres "Vivo Total V" com
    "Vivo TV Completo com HBO Max e Telecine" no texto e apps vazio, em
    contradicao aberta com o nivel 4 do campo ao lado.

    O nome vem primeiro porque e a leitura mais confiavel que a Vivo
    oferece: e onde ela batiza a oferta.
    """
    saida = list(apps.apps_da_oferta(plano, "Vivo"))
    for a in apps.apps_do_texto(texto):
        if a not in saida:
            saida.append(a)
    return saida


# ------------------------------------------------- parser da vitrine (HTML)

def _primeiro(padrao, bloco):
    m = re.search(padrao, bloco, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


# O ADICIONAL OPCIONAL NAO E APP INCLUSO (26/11/2026). O card tem
# interruptores de compra a parte - "+ 10 GB ... por R$ 5" no controle, com
# a dica "com Protecao McAfee por R$5"; "Adicione 7 apps por R$ 60/mes" no
# combo - dentro de <fieldset> com unique-card__switch. O texto do card os
# levava junto, e o Vivo Controle de R$ 59 e o de R$ 75 saiam com o McAfee
# incluso. Saem antes do corte. A escolha de TV da fibra e radio, outra
# coisa, e fica.
OPCIONAIS = re.compile(
    r'<fieldset\b[^>]*>(?:(?!</fieldset>).)*?unique-card__switch'
    r'(?:(?!</fieldset>).)*?</fieldset>', re.S)
# O APP DO TOPO DO CARD ("Apple Music Individual" no Controle Musica) mora
# depois do corte de 12 mil caracteres: o titulo co-branded entra junto.
COBRANDED = re.compile(r'unique-card__features-cobranded-title[^>]*>(.*?)<', re.S)


# O PRECO PARTIDO EM DOIS. No Vivo Total V da pagina sem apps o card escreve
# "R$ <span data-original-price="1">1</span> <span>190/mes</span>": o
# atributo traz so o milhar, e o resto vem colado no "/mes". Lido cru, o
# plano de R$ 1.190 entrava a R$ 1.
RESTO_DO_PRECO = re.compile(
    r'data-original-price="(\d{1,2})"[^>]*>[^<]*</span>\s*'
    r'<span[^>]*unique-card__price-new--side[^>]*>\s*(\d{3})\s*/\s*m', re.S)
# A ESCOLHA DE TV DO CARD DE FIBRA + TV (radio): "Vivo TV Avancado" e o padrao
# do preco; "Vivo TV Completo" soma o que o data-value diz, em base64 ("MTI1"
# = 125), e aponta o proprio codigo Anatel (data-rgc-number = posicao na
# lista do card). Conferido no navegador em 26/11: 270 + 125 = 395.
OPCAO_DE_TV = re.compile(r'<input\b[^>]*type="radio"[^>]*>', re.S)


def _opcoes_de_tv(bloco):
    u"""[(rotulo, acrescimo, posicao do codigo)] das opcoes com acrescimo."""
    import base64
    saida = []
    for m in OPCAO_DE_TV.finditer(OPCIONAIS.sub(" ", bloco)):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(0)))
        try:
            extra = float(base64.b64decode(a.get("data-value") or "").decode("ascii"))
        except Exception:
            continue
        rotulo = _html.unescape(a.get("aria-label") or "").strip()
        n = re.match(r"\d+", a.get("data-rgc-number") or "")
        if extra > 0 and rotulo and n:
            saida.append((rotulo, extra, int(n.group(0))))
    return saida


def ler_vitrine(op, produto, url=None, sufixo=None):
    """Le os cards da vitrine da praca atual.

    O corte e por texto, em class="unique-card " - que aparece exatamente
    uma vez por card. Conferido em 30/09/2026: 7 marcacoes para 7 cards,
    um preco em cada bloco.

    Tentei antes um parser por profundidade de <div>. Nao funciona: o HTML
    da Vivo tem aninhamento irregular e a contagem desanda, fazendo um card
    engolir os seguintes (o 700 Mega saiu com o preco do 10 Giga).
    """
    s, doc = buscar(op, url or VITRINE[produto])
    if s != 200:
        return None, "HTTP %s" % s

    cards = []
    for bloco in re.split(r'class="unique-card ', doc)[1:]:
        plano = _primeiro(r'unique-card__plan[^>]*>(.*?)<', bloco)
        destaque = _primeiro(r'header-benefit-text-big[^>]*>(.*?)<', bloco)
        preco = re.search(r'data-original-price="([^"]+)"', bloco)
        codigos = re.findall(r'data-code-rgc="([^"]+)"', bloco)
        if not plano and url and preco:
            plano = NOME_DO_PRODUTO.get(produto)
        if not plano or not preco:
            continue
        valor = so_numero(preco.group(1))
        partido = RESTO_DO_PRECO.search(bloco)
        if partido:
            valor = float(partido.group(1) + partido.group(2))
        # o texto do card para classificar o bundle: so ate o proximo card,
        # sem os adicionais opcionais, e com o titulo do app do topo
        texto = re.sub(r"<[^>]+>", " ", OPCIONAIS.sub(" ", bloco)[:12000])
        topo = " ".join(re.sub(r"\s+", " ", x).strip() for x in COBRANDED.findall(bloco))
        if topo:
            texto += " " + topo
        texto = _html.unescape(re.sub(r"\s+", " ", texto))
        nome = _html.unescape(plano)
        # a pagina do Vivo V repete um "Vivo Total V 1 Giga" com codigo de
        # 2025: e combo, e o card atual dele esta na pagina de combos
        if url and produto == "movel" and nome.lower().startswith("vivo total"):
            continue
        # O PACOTE DE TV NO NOME quando o card e so de um: nas paginas de
        # streaming o mesmo "Vivo Fibra + TV + Netflix 600 Mega" vem a R$ 315
        # (TV Avancado) e a R$ 440 (TV Completo), dois cards com um nome so.
        # Card que oferece as duas (radio) fica com o nome de sempre.
        _t = texto.lower()
        if ("+ tv" in nome.lower() and "vivo tv completo" in _t
                and "vivo tv avan" not in _t):
            nome = "%s (Vivo TV Completo)" % nome
        # o sufixo so quando o nome ainda nao cita o que ele diz ("Vivo
        # Fibra + TV + Netflix" nao vira "... com Netflix")
        if sufixo and sufixo.split()[-1].lower() not in nome.lower():
            nome = "%s %s" % (nome, sufixo)
        cards.append({
            "plano": nome,
            "destaque": _html.unescape(destaque) if destaque else None,
            "preco": valor,
            "codigo_anatel": codigos[0] if codigos else None,
            "codigos_anatel": codigos or None,
            "texto": texto,
        })
        # a TV Completo do mesmo card, com o preco e o codigo dela
        for rotulo, extra, pos in _opcoes_de_tv(bloco):
            if pos - 1 >= len(codigos):
                continue
            cards.append({
                "plano": "%s (%s)" % (nome, rotulo),
                "destaque": _html.unescape(destaque) if destaque else None,
                "preco": valor + extra,
                "codigo_anatel": codigos[pos - 1],
                "codigos_anatel": [codigos[pos - 1]],
                "texto": texto + " " + rotulo,
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


def assinatura_sva(smp, scm):
    """O conjunto de codigos SVA do regulamento, e o texto para comparar.

    NAO E PRECISO SABER QUE APP E CADA CODIGO - o cruzamento mostrou que
    a Vivo nao da para saber (so 1 dos 20 tem nome seguro). O que importa
    e o CONJUNTO: se o preco nao se move e a assinatura muda, a oferta
    trocou de conteudo sem trocar de etiqueta, que e o repasse disfarcado
    da metodologia. Por isso o texto vai ORDENADO - a comparacao entre
    dias e por igualdade, e ordem instavel acusaria troca todo dia.

    OS DOIS BLOCOS ENTRAM JUNTOS: no combo, movel e fixa declaram SVA
    cada um, e ler so o primeiro perderia metade da composicao.

    MORA AQUI PORQUE SAO DOIS CAMINHOS. A vitrine chega por enriquecer();
    o Lite monta a oferta direto do regulamento, sem passar por ela, e
    ficou 80 linhas por dia sem o campo - invisivel para o detector de
    composicao, no produto que o tracker acompanha para ver o piso do
    mercado. Duas montagens da mesma coisa divergiriam na primeira
    correcao, e divergir na ORDEM faria toda oferta do Lite parecer ter
    trocado de conteudo todo dia.
    """
    sva = sorted({c for bloco in (smp or {}, scm or {})
                  for c in (bloco.get("listaSVA") or []) if c})
    return sva, ("+".join(sva) if sva else None)


def enriquecer(oferta, card):
    """Acrescenta o que o catalogo sabe e a vitrine nao mostra."""
    if not card:
        return oferta
    oferta["preco_cheio"] = preco_cheio_valido(card.get("oldPrice"))
    # O "regional" do catalogo diz ONDE a oferta vale - "nacional", ou o
    # nome da regiao. Isso nao e campanha, e escopo. Ia para o campo
    # campanha, que desde 16/10/2026 tem dono: o banner de promocao que
    # a vitrine cola no card ("Claro Day"). Misturar os dois faria o
    # campo dizer que a Vivo roda uma campanha chamada "nacional" todo
    # dia do ano. Vai para chave propria, que o bruto guarda sem precisar
    # de coluna nova.
    oferta["regional"] = [r for r in (card.get("regional") or []) if r] or None
    oferta["id_catalogo"] = card.get("id") or card.get("idOffer")
    detalhes = json.dumps(card, ensure_ascii=False)
    if oferta.get("nivel_bundle") in (None, 0):
        oferta["nivel_bundle"] = nivel_bundle(detalhes, oferta.get("apps"))
    return oferta


# ------------------------------------------------- regulamento (contrato)

REGULAMENTO = "https://vivo.com.br/bin/vivo-portal/rgc-offer-json-file?anatelCode=%s"

# Os GB de movel dentro de um combo. O card escreve a composicao inteira
# numa frase: "Vivo Total Ultra 700 Mega de Vivo Fibra com Wi-Fi 6 100 GB
# de Vivo Pos". Sem isto o combo entrava na tela so com os Mbps da fibra,
# e o movel - que e metade da oferta - nao aparecia em lugar nenhum.
GB_DO_MOVEL = re.compile(r"(\d{1,4})\s*GB\s+de\s+Vivo\s+P[óo]s", re.I)

# O formato de um codigo Anatel da Vivo: VIV e doze digitos ou mais.
#
# A vitrine as vezes publica codigo quebrado - em 14/10/2026 o card de
# "Vivo Pos com Globoplay" trazia "IV202600045258", sem o V inicial.
# Consultar o regulamento com ele devolve HTTP 400, e isso custava 100
# requisicoes perdidas por dia e um aviso enganoso ("regulamento
# falhou") sobre o que e, na verdade, erro de digitacao da fonte.
#
# O codigo e gravado como a Vivo publicou - o V que falta nao e nosso
# para inventar -, mas nao vai ao regulamento.
CODIGO_VALIDO = re.compile(r"^VIV\d{12,}$")

# Cache da rodada: as 20 pracas compartilham os mesmos ~25 codigos, entao
# sem isto seriam 500 downloads de 500 KB para baixar 25 documentos.
_cache_regulamento = {}
_falhas_regulamento = []
# A FALHA NAO VAI DIRETO PARA O CACHE, desde 24/11/2026. Guardar o None
# da primeira falha fazia uma recusa passageira em Sao Paulo valer para as
# 20 pracas: nenhuma perguntava de novo, e as ofertas daquele codigo saiam
# sem fidelidade, multa e preco de tabela o dia inteiro. Os codigos que
# falharam no servidor do robo em 17 e 23/11 abriam normalmente daqui. O
# codigo que falha e tentado de novo nas pracas seguintes - que vem um
# minuto depois, espacadas -, ate TENTATIVAS_REGULAMENTO vezes na rodada.
TENTATIVAS_REGULAMENTO = 3
_tentativas_regulamento = {}
# os codigos desta praca que ficaram sem regulamento, para o aviso contar
# a praca e nao a rodada: a lista de falhas e da rodada inteira, e o aviso
# antigo repetia em toda praca o total acumulado desde a primeira
_sem_regulamento_na_praca = []
# codigo que a vitrine publicou fora do padrao: nao e falha nossa nem
# instabilidade da Vivo, e erro de digitacao deles, e vai dito assim
_codigos_quebrados = []


def codigo_malformado(codigo):
    """O codigo existe mas nao tem o formato que a Anatel usa?"""
    return bool(codigo) and not CODIGO_VALIDO.match(codigo)


def regulamento(op, codigo):
    """Baixa o regulamento da Anatel e devolve o que a vitrine nao mostra.

    E aqui que moram preco de tabela, fidelidade, multa, taxa de instalacao
    e a franquia CONTRATUAL - a que esta no contrato, sem o bonus que expira.
    So a Vivo publica isso em formato estruturado.

    O arquivo vem como ZIP com um JSON dentro, e o encoding varia.
    """
    if codigo in _cache_regulamento:
        if _cache_regulamento[codigo] is None and not codigo_malformado(codigo):
            _sem_regulamento_na_praca.append(codigo)
        return _cache_regulamento[codigo]
    if codigo_malformado(codigo):
        # nao adianta perguntar: o codigo nao existe na agencia
        _cache_regulamento[codigo] = None
        _codigos_quebrados.append(codigo)
        return None

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

    _tentativas_regulamento[codigo] = _tentativas_regulamento.get(codigo, 0) + 1
    if (oferta is not None
            or _tentativas_regulamento[codigo] >= TENTATIVAS_REGULAMENTO):
        _cache_regulamento[codigo] = oferta
    if oferta is None:
        _sem_regulamento_na_praca.append(codigo)
    return oferta


def _reais(v):
    """"1200.0" -> "R$ 1.200,00", como no resto da mensagem.

    MORA AQUI E NAO NO robo.py porque o aviso nasce no coletor, e o
    coletor nao importa o robo - a dependencia e no outro sentido. O
    texto do aviso passou a sair no Telegram quando o canal de leitura
    duvidosa ganhou leitor, e "R$ 1200.00" ao lado de "R$ 1.200,00"
    denuncia que as duas frases foram escritas em epocas diferentes.
    """
    if v is None:
        return "\u2014"
    # o "@" e so um passo intermediario para nao trocar duas vezes o
    # mesmo caractere: 1200.0 -> "1,200.00" -> "1@200.00" -> "1.200,00"
    return "R$ " + ("{:,.2f}".format(v).replace(",", "@")
                    .replace(".", ",").replace("@", "."))


def _num(x):
    """O numero do regulamento, no formato brasileiro.

    NUMERO JA E NUMERO. A troca de "." por "" existe porque no formato
    brasileiro o ponto separa milhar - "1.200,00" vira 1200.0 - e
    aplicada a um float ja pronto ela apaga a casa decimal:
    _num(1200.0) devolvia 12000.0 e _num(299.9) devolvia 2999.0.

    Hoje a Anatel entrega inteiro ou string com virgula, entao nunca
    disparou. Uma mudanca de formato da agencia bastaria para gravar
    preco e multa dez vezes maiores - e a guarda de preco so barra
    valor ABAIXO do da vitrine, nunca inflado, entao nada pegaria.
    """
    if x in (None, "", "null"):
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
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
        # O REGULAMENTO E DE OUTRA OFERTA, E NADA DELE VALE AQUI.
        #
        # Um codigo Anatel e publicado por varios cards: o mesmo
        # VIV202604042336 aparece em "Vivo Total V 1 Giga" (R$ 1.200),
        # "V 2 Giga" (R$ 1.500) e "V 10 Giga" (R$ 3.000). O documento
        # descreve um deles, e o preco de tabela abaixo do preco de
        # vitrine e a prova de que nao e este.
        #
        # Antes so o preco de tabela era barrado, e multa, fidelidade,
        # taxas, franquia contratual, velocidade, nome registrado e a
        # assinatura SVA eram carimbados assim mesmo - numeros de outra
        # oferta apresentados como desta. Dois deles com efeito em
        # cascata: assinatura_sva alimenta o detector de repasse
        # disfarcado, e nome_regulamento alimenta a variante da chave de
        # continuidade, entao a IDENTIDADE desta oferta passava a
        # depender de um documento que e de outra.
        #
        # Escolher um entre varios e publicar como fato e a mesma
        # familia do par indistinguivel. O sinal para recusar ja estava
        # na mao; faltava usa-lo para tudo.
        # APPS.JUNTAR_AVISOS E NAO SETDEFAULT. A chave existe valendo
        # None quando nao ha aviso - ausencia e ausencia, nao lista
        # vazia -, e setdefault nao substitui None: ele devolve None e o
        # .append estoura, derrubando a coleta inteira da Vivo.
        oferta["avisos_oferta"] = apps.juntar_avisos(
            oferta.get("avisos_oferta"),
            apps.ressalva(
            "o contrato n\u00e3o deu para ler: sem pre\u00e7o de tabela, "
            "fidelidade, multa e taxas",
            "o regulamento diz %s de tabela, abaixo dos %s da "
            "vitrine: o documento \u00e9 de outra oferta que divide o mesmo "
            "c\u00f3digo Anatel, e nenhum campo contratual dele foi usado"
            % (_reais(tabela), _reais(prom))))
        return oferta
    # O "DE:" DA VITRINE NA FRENTE (26/11/2026, "o que vale e sempre o site"):
    # a Vivo Total Essencial do Nordeste diz "De: R$ 150" no card, e o
    # tracker gravava os R$ 157,50 do regulamento. O preco de tabela do
    # contrato so entra quando a vitrine nao diz o "De:".
    oferta["preco_cheio"] = oferta.get("preco_cheio") or tabela
    # ZERO DECLARADO NAO E AUSENCIA. "Ausencia e ausencia, nunca
    # zero" e principio do projeto, e o espelho dele vale igual: um
    # regulamento que escreve tempoFidelizacao: 0 esta FALANDO, e
    # dizendo que a oferta nao tem fidelidade - a informacao mais
    # relevante que este campo carrega, porque e a unica que
    # distingue "nao prende o cliente" de "nao consegui ler o
    # contrato". O "or None" do fim apagava os dois no mesmo None, e
    # a linha da multa logo abaixo nunca fez isso: a assimetria
    # entre duas linhas que leem o mesmo bloco era o indicio.
    #
    # NEM TODO "or None" E DEFEITO: franquia de 0 GB e velocidade de
    # 0 Mbps nao existem como produto, e ali o zero e lixo de
    # leitura. Aqui zero e valor valido, e e por isso que esta linha
    # e diferente das vizinhas - nao padronizar as tres.
    #
    # Bloco AUSENTE continua None, e isso nao e descuido: e o
    # "silencio nao e ausencia" da metodologia. Medido em
    # 21/10/2026, o Vivo Lite Mensal nao tem bloco de fidelizacao
    # nenhum, enquanto o Anual declara 12 meses e multa. Inferir
    # zero do silencio afirmaria contratualmente que a operadora
    # nao prende o cliente, o que o documento nao diz.
    meses = _num(fid.get("tempoFidelizacao"))
    oferta["fidelidade_meses"] = None if meses is None else int(meses)
    oferta["multa_fidelidade"] = _num(fid.get("multaFidelizacao"))
    oferta["taxa_instalacao"] = _num(custo.get("instalacao"))
    oferta["taxa_adesao"] = _num(custo.get("adesao"))

    # A FRANQUIA QUE CONTRADIZ O CARD E PROVA DE QUE O DOCUMENTO E DE
    # OUTRA OFERTA - e entao nenhum campo dele vale, nao so este.
    #
    # Os tres cards do Vivo Pre dividem UM codigo Anatel: medido em
    # 20/10/2026, VIV202600042812 cobre 5, 15 e 20 GB e o regulamento
    # declara 25. Franquia garantida nao pode ser maior que a anunciada.
    #
    # Antes so a franquia era recusada, e os tres cards recebiam a mesma
    # multa, a mesma fidelidade e a MESMA assinatura SVA daquele
    # documento. A assinatura e a que mais pesa: ela existe para pegar o
    # repasse disfarcado - composicao muda, etiqueta nao - e com os tres
    # carimbados igual o detector comparava uma composicao que nao e de
    # nenhum deles.
    #
    # Mesma conclusao do preco de tabela acima: provada a origem alheia,
    # o documento sai inteiro.
    franquia = (smp.get("franquiaDados") or {}).get("franquia")
    if franquia:
        v = int(_num(franquia) or 0) or None
        anunciada = oferta.get("franquia_anunciada_gb")
        if v and anunciada and v > anunciada:
            for campo in ("preco_cheio", "fidelidade_meses",
                          "multa_fidelidade", "taxa_instalacao",
                          "taxa_adesao"):
                oferta[campo] = None
            oferta["avisos_oferta"] = apps.juntar_avisos(
                oferta.get("avisos_oferta"),
                apps.ressalva(
                "sem franquia garantida",
                "o regulamento declara %s GB para um card de %s GB: "
                "o documento \u00e9 de outra oferta que divide o mesmo "
                "c\u00f3digo Anatel, e nenhum campo contratual dele foi usado"
                % (v, anunciada)))
            return oferta
        if v:
            oferta["franquia_contratual_gb"] = v
    velo = (scm.get("velocidade") or {})
    if velo.get("download"):
        oferta["download_mbps"] = int(_num(velo["download"]) or 0) or None
        oferta["upload_mbps"] = int(_num(velo.get("upload")) or 0) or None
    if scm.get("listaTecnologia"):
        oferta["tecnologia"] = scm["listaTecnologia"]
    oferta["nome_regulamento"] = reg.get("nomeOferta")

    # O tier do app costuma estar SO no nome registrado na Anatel: a
    # vitrine diz "Vivo Pos com Disney+" e a agencia, "VIVO POS COM
    # DISNEY+ PADRAO". Refaz o rotulo com essa fonte a mais.
    if oferta.get("apps"):
        fontes = (oferta.get("nome_regulamento"), oferta.get("nome_oferta"),
                  oferta.get("bruto_texto"))
        oferta["apps_rotulo"] = apps.rotulo(oferta["apps"], *fontes)
        oferta["apps_planos"] = apps.planos_dos_apps(oferta["apps"], *fontes)

    # Assinatura da composicao: o conjunto de codigos SVA, ordenado.
    #
    sva, texto = assinatura_sva(smp, scm)
    if sva:
        oferta["sva"] = sva
        oferta["assinatura_sva"] = texto
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


DE_DO_CARD = re.compile(r"\bDe:\s*R\$\s*([\d.]+(?:,\d{1,2})?)")
APOS_PROMOCAO = re.compile(
    r"Ap[oó]s\s+(\d{1,2})\s+(anos?|m[eê]s|meses)\s*:?\s*R\$\s*([\d.]+(?:,\d{1,2})?)\s*/\s*m[eê]s",
    re.I)
BONUS_DO_CARD = re.compile(r"(\d{1,3})\s*GB\s*\+\s*(\d{1,3})\s*GB\s*de\s*b[oô]nus", re.I)


def _bonus_do_card(html):
    u"""{codigo Anatel: (GB do contrato, GB de bonus)}, do card que o linka.

    A FRANQUIA ANUNCIADA E A DO CARD (26/11/2026, auditoria contra o site):
    o Lite sai do regulamento, que registra 30 e 40 GB, e o card anuncia 35
    e 45 - "30 GB + 5 GB de bonus 12 meses". O tracker grava a franquia
    anunciada, com bonus, e a do contrato a parte, como nas outras
    operadoras. O card que nao diz bonus nao mexe em nada, e o bonus so
    vale quando a primeira parcela e a franquia do regulamento daquele
    codigo - ver ler_lite.
    """
    saida = {}
    for bloco in html.split('class="unique-card ')[1:]:
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", bloco))
        achados = set(BONUS_DO_CARD.findall(texto))
        if len(achados) != 1:
            continue          # sem bonus, ou dois bonus no mesmo bloco: nao chuta
        base, extra = [int(x) for x in achados.pop()]
        for cod in set(re.findall(r"VIV\d{12,}", bloco)):
            saida.setdefault(cod, (base, extra))
    return saida


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
    bonus = _bonus_do_card(html)
    # O QUE VALE E O SITE (26/11/2026, decisao de quem le). O "Vivo Fibra
    # 500 Mega Lite" e um card na vitrine, com "Baixar condicoes da oferta"
    # e tudo, e o regulamento dele diz que a oferta acabou em 11/07/2026: o
    # cliente ve e compra, e o tracker o descartava - era a fibra mais
    # barata da Vivo (R$ 90). Codigo vencido que o card linka ("Baixar
    # condicoes da oferta", href do proprio codigo) entra; o que so aparece
    # fora de um link de card continua de fora. Pelo link, e nao pela
    # posicao: o ultimo card de um corte por 'unique-card' vai ate o fim
    # da pagina, com script e rodape dentro.
    em_card = set(re.findall(r'href="(VIV\d{12,})"', html))

    ofertas, vencidos, vencidos_no_card = [], 0, 0
    for cod in codigos:
        reg = regulamento(op, cod)
        if not reg:
            continue
        if not _vigente(reg, hoje):
            if cod not in em_card:
                vencidos += 1
                continue
            vencidos_no_card += 1
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
        # A ASSINATURA SVA TAMBEM AQUI. enriquecer() monta este campo
        # para a vitrine, e ler_lite nao passa por ela - monta a oferta
        # direto do regulamento, que e fonte melhor que card. Sem o
        # campo, as 80 linhas do Lite (4 ofertas x 20 pracas) ficavam
        # invisiveis para o detector de composicao: a Vivo podia tirar
        # um servico sem mexer no preco e nada diria nada, no produto
        # que o tracker acompanha para ver o PISO do mercado.
        sva, texto_sva = assinatura_sva(smp, scm)
        contrato = int(_num(franquia) or 0) or None
        anunciada, contratual = contrato, None
        # O BONUS DO CARD, quando o card fala do mesmo contrato: ver
        # _bonus_do_card
        base, extra = bonus.get(cod) or (None, None)
        if contrato and base == contrato and extra:
            anunciada, contratual = contrato + extra, contrato
        ofertas.append({
            # "Vivo Fibra 500 Mega Lite." - o ponto final e do regulamento
            "nome_oferta": (reg.get("nomeOferta") or "").strip().rstrip(".") or None,
            "destaque": ("%s Mbps" % mbps) if mbps else
                        ("%s GB" % anunciada if anunciada else None),
            "produto": produto,
            "degrau_mbps": mbps,
            "franquia_anunciada_gb": anunciada,
            "franquia_contratual_gb": contratual,
            "preco_promocional": preco,
            "codigo_anatel": cod,
            # o nivel de bundle NAO sai da contagem de codigos: eles nao
            # dizem que servico e, e a vitrine tambem nao faz isso - a
            # "Vivo Total Familia 2" tem assinatura cheia e nivel 0
            "sva": sva or None,
            "assinatura_sva": texto_sva,
            # a marca que separa esta linha da vitrine anunciada
            "linha": "lite",
        })
    if vencidos and avisos is not None:
        avisos.append("lite: %d codigo(s) com vigencia encerrada, ignorados" % vencidos)
    if vencidos_no_card and avisos is not None:
        avisos.append("lite: %d codigo(s) com vigencia encerrada na Anatel, gravados "
                      "porque o card esta na vitrine" % vencidos_no_card)
    if not ofertas:
        return None, "nenhuma oferta Lite vigente"
    return ofertas, None


def coletar(cidade, uf, verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    op, _ = navegador()
    saida = {"operadora": "Vivo", "praca": "%s/%s" % (cidade, uf),
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    del _sem_regulamento_na_praca[:]
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

    lidos = set()
    # PAGINA EXTRA QUE FALHA TIRA O PRODUTO INTEIRO DA PRACA, dito: a oferta
    # que so mora nela sairia como saida da vitrine (a regra da Brisanet)
    falhou = set()
    # PAGINA EXTRA SEM CARD NEM SEMPRE E FALHA (26/11/2026, medido antes da
    # primeira coleta com as paginas extras): em Fortaleza e Natal a pagina
    # do Vivo Total sem apps carrega inteira, com o cabecalho e as vantagens,
    # e sem nenhum card - a Vivo nao vende o Total sem apps ali. Tratado como
    # falha, o combo inteiro da Vivo (14 ofertas) sairia da praca toda noite.
    # Sem card numa pagina que respondeu, de um produto cuja vitrine principal
    # leu cards na mesma praca, e ausencia; o erro de rede continua falha.
    principal = set()
    roteiro = ([(p, None, None) for p in ("controle", "movel", "fibra", "combo", "prepago")]
               + list(PAGINAS_EXTRAS))
    for produto, url_extra, sufixo in roteiro:
        cards, err = ler_vitrine(op, produto, url_extra, sufixo)
        if cards:
            if not url_extra:
                principal.add(produto)
            # o mesmo codigo Anatel numa pagina extra e a mesma oferta
            cards = [c for c in cards if not c["codigo_anatel"]
                     or (c["codigo_anatel"], c["preco"]) not in lidos]
            lidos.update((c["codigo_anatel"], c["preco"]) for c in cards if c["codigo_anatel"])
        elif url_extra and not err and produto in principal:
            saida["avisos"].append("vitrine %s: %s sem oferta nesta praca"
                                   % (produto, url_extra.rsplit("/", 1)[-1]))
        elif url_extra:
            # pagina extra que falhou ou que nao trouxe card nenhum
            falhou.add(produto)
            if not err:
                saida["avisos"].append("vitrine %s: nenhum card em %s - a pagina mudou"
                                       % (produto, url_extra.rsplit("/", 1)[-1]))
        if err:
            saida["avisos"].append("vitrine %s: %s" % (produto, err))
            if verbose:
                print("  vitrine %-9s FALHOU (%s)" % (produto, err))
            time.sleep(PAUSA)
            continue

        for c in cards:
            destaque = c["destaque"]
            # UMA LEITURA PARA OS QUATRO CAMPOS de app. Eram quatro
            # chamadas de apps_da_oferta no dicionario abaixo, e o
            # nivel ao lado lia o texto tambem - duas fontes para a
            # mesma pergunta, que e como um campo passou a negar o
            # vizinho.
            _apps_do_card = apps_da_vitrine(c["plano"], c["texto"])
            # a leitura larga sai dita, no mesmo canal
            _aviso_apps = apps.aviso_de_leitura(c["texto"])
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
                # No combo os GB nao estao no destaque (que traz os Mbps
                # da fibra), e sim na frase do card: "700 Mega de Vivo
                # Fibra com Wi-Fi 6 100 GB de Vivo Pos". Sem isto o
                # combo chegava na tela so com a fibra, e o movel - que e
                # metade da oferta - nao aparecia.
                "franquia_anunciada_gb": (
                    degrau_gb(destaque) if produto not in ("fibra", "combo")
                    else (int(_gbm.group(1))
                          if produto == "combo"
                          and (_gbm := GB_DO_MOVEL.search(c["texto"] or ""))
                          else None)),
                # preco cheio fica vazio quando a fonte nao informa (decisao 9)
                "preco_cheio": None,
                "preco_promocional": c["preco"],
                "nivel_bundle": nivel_bundle(c["texto"], _apps_do_card),
                # QUAIS apps, e nao so quantos: o nome da oferta e onde a
                # Vivo nomeia o app ("Vivo Controle Netflix", "Vivo Pos
                # com Disney+"), e o texto do card nomeia o que o nome
                # nao diz ("Vivo TV Completo com HBO Max e Telecine"). O
                # codigo SVA nao distingue - vem igual em todas as
                # ofertas. UMA LEITURA SO para os quatro campos: com
                # duas, um campo dizia o que o vizinho negava.
                "apps": list(_apps_do_card),
                # o tier sai daqui quando a vitrine o escreve; quando
                # nao, o nome registrado na Anatel ainda pode traze-lo, e
                # por isso o rotulo e refeito depois do regulamento
                "apps_rotulo": apps.rotulo(
                    _apps_do_card, c["plano"], c["texto"]),
                "apps_planos": apps.planos_dos_apps(
                    _apps_do_card, c["plano"], c["texto"]),
                # o texto do card alimenta o cruzamento que deduz quais
                # apps correspondem a quais codigos SVA do regulamento
                "bruto_texto": c["texto"][:600],
                "codigo_anatel": c["codigo_anatel"],
                # "Nas recargas de Valor R$ 35 Por 30 dias": so no pre
                "validade_dias": (int(_vd.group(1)) if produto == "prepago"
                                  and (_vd := re.search(r"\bpor\s+(\d{1,3})\s+dias\b",
                                                        c["texto"] or "", re.I))
                                  else None),
                "avisos_oferta": apps.juntar_avisos(None, _aviso_apps),
                "campanha": None,
                "id_catalogo": None,
            }
            # O PRECO DEPOIS DA PROMOCAO, quando o card o escreve (26/11/2026,
            # auditoria): "Vivo Fibra 600 Mega - 1 ano de Disney+ - R$ 100/mes
            # - Apos 1 ano: R$ 120/mes". O tracker gravava o 100 sem dizer que
            # ele acaba em 12 meses.
            _depois = APOS_PROMOCAO.search(c["texto"] or "")
            if _depois:
                _n = int(_depois.group(1))
                oferta["meses_desconto"] = _n * 12 if _depois.group(2).lower().startswith("ano") else _n
                oferta["preco_pos_promocao"] = so_numero(_depois.group(3))
            oferta = enriquecer(oferta, idx.get(c["codigo_anatel"]))
            # O "DE:" DO CARD vence o catalogo e o regulamento: o que vale e o
            # site. A Vivo Total Essencial do Nordeste diz "De: R$ 150" e o
            # tracker gravava os R$ 157,50 do contrato (auditoria de 26/11).
            _de = DE_DO_CARD.search(c["texto"] or "")
            if _de and (so_numero(_de.group(1)) or 0) > (c["preco"] or 0):
                oferta["preco_cheio"] = so_numero(_de.group(1))
            if c["codigo_anatel"]:
                oferta = aplicar_regulamento(oferta, regulamento(op, c["codigo_anatel"]))
            saida["ofertas"].append(oferta)

        if verbose:
            print("  vitrine %-9s %d ofertas" % (produto, len(cards)))
        time.sleep(PAUSA)

    # A linha Lite, depois da vitrine. Nao entra no laco acima porque a
    # fonte e outra: o regulamento Anatel, e nao o card da pagina.
    if falhou:
        antes = len(saida["ofertas"])
        saida["ofertas"] = [o for o in saida["ofertas"] if o["produto"] not in falhou]
        saida["avisos"].append(
            "%s fora da praca hoje: uma das paginas falhou, e o que so ela traz "
            "sairia como saida da vitrine (%d ofertas)"
            % (", ".join(sorted(falhou)), antes - len(saida["ofertas"])))

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

    if _codigos_quebrados:
        saida["avisos"].append(
            "a vitrine publicou %d codigo(s) Anatel fora do padrao (%s) - o "
            "codigo foi gravado como veio, mas sem regulamento nao ha "
            "fidelidade, multa nem preco de tabela nessas ofertas. Erro da "
            "fonte, nao ha o que reprocessar"
            % (len(_codigos_quebrados), ", ".join(_codigos_quebrados[:3])))
    if _sem_regulamento_na_praca:
        # a ultima falha de um codigo DESTA praca, que e a que explica
        codigos = set(_sem_regulamento_na_praca)
        motivo = next((f for f in reversed(_falhas_regulamento)
                       if f.split(":")[0] in codigos), "?")
        saida["avisos"].append(
            "regulamento falhou em %d oferta(s) - fidelidade, multa e preco "
            "de tabela ficam vazios. Primeira: %s"
            % (len(_sem_regulamento_na_praca), motivo))
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
