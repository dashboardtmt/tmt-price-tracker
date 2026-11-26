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

from . import apps
from . import rede
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

# OS PREZOES TEMATICOS, desde 26/11/2026. A pagina do Prezao tem duas abas,
# e ate 25/11 so a primeira (o Prezao R$ 1 por dia) era lida. A segunda,
# "Outras ofertas Pre", aponta para esta pagina, com cinco Prezoes de 30
# dias - Kwai, TikTok, Uber, Shopee e Free Fire - de R$ 34,99 a R$ 35.
# Estavam no site desde antes do primeiro dia do tracker (Web Archive,
# 02/09 e 04/10). Quem viu foi quem le, no site: "parece um erro grave".
PREZAO_TEMATICOS = "https://www.claro.com.br/celular/planos-pre/ofertas-pre"

# Montadas em Storyblok, sem os cards do movel. Ate 26/11/2026 eram lidas
# pelas frases de acessibilidade (ler_por_texto); desde 27/11, pelo mesmo
# catalogo que monta os cards (ler_catalogo).
POR_TEXTO = {"fibra", "combo"}

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


def buscar(op, url, metodo="GET", dados=None, extras=None, timeout=45,
           avisos=None):
    def uma():
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
    # foi a Claro que mostrou a necessidade disto, em 07/10
    return rede.insistir(uma, url, avisos=avisos)


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
    return apps.nivel_por_apps(txt, APPS_CATALOGO)


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
    sem_preco_real = 0
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
        valor, tinha = preco_do_card(txt)
        if valor is None:
            # tinha preco, mas so dentro da frase do beneficio: a oferta
            # fica de fora em vez de entrar com o preco errado
            if tinha:
                sem_preco_real += 1
            continue
        if txt.startswith("data-") or not re.match(r"[A-Za-z]", txt):
            continue   # bloco sem identidade legivel
        # o nome vem antes do primeiro numero de franquia/velocidade
        nome = re.split(r"\d+\s*(?:GB|MEGA|Mega|Giga)", txt)[0].strip(' ">-')
        nome, campanha = _sem_campanha(nome)
        # o que vem DEPOIS da franquia tambem e nome, quando distingue
        qual = _qualificador_do_card(txt)
        if qual and qual.lower() not in nome.lower():
            nome = ("%s %s" % (nome, qual)).strip()
        # campanha e text[] no esquema: vai lista, nao string
        campanha = [campanha] if campanha else None
        destaque = re.search(r"(\d+\s*(?:GB|MEGA|Mega|Giga|Mbps))", txt)
        cards.append({
            "id_catalogo": ident.group(1) if ident else None,
            "campanha": campanha,
            "nome_oferta": (nome or "Claro")[:70],
            "destaque": destaque.group(1) if destaque else None,
            "preco_promocional": numero(valor),
            "composicao": txt[:400],
            # PELO BLOCO INTEIRO DO CARD, que vai so ate o card seguinte - e
            # nao pela composicao (400 caracteres) nem pelo txt (12 mil de
            # HTML): no Claro Pos Geforce o "WhatsApp e ligacoes
            # ilimitadas" vem depois dos dois cortes (medido em 24/11/2026).
            "whatsapp": apps.whatsapp_incluso(re.sub(r"<[^>]+>", " ", bloco)),
            # OS APPS TAMBEM PELO CARD INTEIRO (26/11/2026). Saiam da
            # composicao, os primeiros 400 caracteres de um texto ja cortado
            # em 12 mil de HTML, e o "Apps exclusivos para voce: Skeelo" do
            # pos e do Controle Geforce fica depois dos dois cortes - o
            # Skeelo faltava nos cinco planos de pos. Medido no hub de Sao
            # Paulo: o card inteiro tem de 400 a 2.000 caracteres de texto e
            # nomeia de um a tres apps.
            "texto_apps": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", bloco)).strip(),
        })
    if sem_preco_real and cards:
        cards[0]["avisos_oferta"] = apps.juntar_avisos(
            cards[0].get("avisos_oferta"),
            apps.ressalva(
                "%d card(s) ficaram de fora: o pre\u00e7o s\u00f3 aparecia "
                "em frase de degusta\u00e7\u00e3o" % sem_preco_real,
                "%d card(s) tinham preco so dentro de frase de degustacao e "
                "ficaram de fora - e preco do beneficio, nao do plano"
                % sem_preco_real))
    # PRODUTO VAZIO SEM ERRO E AFIRMACAO DE AUSENCIA. Devolvendo
    # ([], None) a rodada era gravada como sucesso, com a praca contada
    # em pracas_ok, e a base do dia passava a dizer que a Claro nao tem
    # este produto naquela praca.
    #
    # Tres entradas chegam aqui: pagina cujos cards todos carregam
    # data-product-name (o filtro de aparelho e um marcador largo do
    # Hybris), pagina sem a classe card-planos, e drupalSettings sem a
    # chave de ofertas. Nos tres a leitura falhou - ela nao mediu que
    # nao ha oferta.
    #
    # As funcoes irmas deste arquivo ja fazem assim: ler_por_texto e
    # ler_prezao devolvem erro quando nao reconhecem nada.
    if not cards:
        return [], ("nenhum card de plano reconhecido na pagina - "
                    "a leitura falhou, e nao ha como afirmar que o "
                    "produto nao existe nesta praca")
    return cards, None


# O que separa duas ofertas de mesma franquia dentro de um card. Fica
# entre os GB e o texto estrutural, que sempre abre em "Ate N linhas":
#
#     "Claro Pos 50GB Geforce Ate 2 linhas ..."   -> Geforce
#     "Claro Pos 50GB Ate 2 linhas ..."           -> nada
#
# Sem isto as duas viravam "Claro Pos 50GB", com R$ 124,90 e R$ 164,90,
# e a serie do 50 GB pulava de um preco para o outro conforme qual
# aparecesse primeiro na pagina.
QUALIFICADOR = re.compile(
    r"\d+\s*(?:GB|MEGA|Mega|Giga)\s+"
    r"((?:[A-ZÀ-Ý][\wÀ-ÿ+]{2,14}\s*){1,2}?)"
    r"(?=\s*(?:At[ée]\b|Linhas\b|Valor\b|R\$|\d))")


PRECO = re.compile(r"R\$\s?([\d.]+,\d{2})")


def preco_do_card(txt):
    """O preco do PLANO anunciado num card. Devolve (valor, tinha_algum).

    O PRECO NAO PODE SAIR DE UMA FRASE DE DEGUSTACAO. Em 07/10/2026 tres
    cards de Controle em Porto Alegre vieram com R$ 24,60 - o preco
    avulso do Disney+, citado em "Disney+: 3 meses por conta da Claro.
    Apos, R$24,60 por mes" - no lugar dos R$ 99,90 do plano, porque a
    leitura pega o primeiro "R$" e naquele dia a frase do beneficio veio
    antes no markup. A serie mostrava o preco certo nos outros quinze
    dias.

    O segundo item da resposta diz se HAVIA preco no card: card cujo
    unico "R$" estava dentro da frase do beneficio fica de fora, e isso
    e contado como aviso da rodada em vez de entrar com o preco errado.

    E UMA FUNCAO COM NOME, e nao quatro linhas no meio do laco, porque o
    teste precisa chamar exatamente isto. Enquanto a leitura morava no
    laco, o teste reimplementava os mesmos dois passos - e quebrar a
    linha de producao deixava a suite verde.
    """
    achado = PRECO.search(apps.sem_degustacao(txt) or "")
    if achado:
        return achado.group(1), True
    return None, bool(PRECO.search(txt or ""))


def _qualificador_do_card(txt):
    """O que distingue esta oferta de outra com a mesma franquia."""
    m = QUALIFICADOR.search(txt or "")
    if not m:
        return None
    q = " ".join(m.group(1).split())
    # palavra estrutural que escapou do lookahead nao e qualificador
    if q.lower() in ("ate", "até", "linhas", "valor", "total", "eu", "por",
                     "plano", "mes", "mês"):
        return None
    return q or None


def _sem_campanha(nome):
    """Separa o banner de campanha do nome da oferta.

    De 06 a 12/10/2026 a Claro rodou o "Claro Day" e o banner colou na
    frente do card: a leitura do nome, que pega o comeco do texto,
    devolvia "Claro Day Claro Pos". A oferta e a mesma, mas com outro
    nome ela vira outra identidade - a serie morria no dia 06 e
    ressuscitava no dia 12, e a mesma oferta aparecia duas vezes na
    tabela. Foram 834 linhas em sete dias.

    NAO DA PARA LISTAR AS CAMPANHAS que a operadora vai inventar, e nem
    e preciso: o que marca o comeco do nome e a marca seguida de um
    PRODUTO que a Claro vende, e esses o coletor ja conhece. O que vier
    antes de "Claro <produto>" e banner. Nome que ja comeca na marca nao
    tem nada antes e nunca vira campanha.

    Devolve (nome limpo, campanha ou None).
    """
    m = None
    for m in re.finditer(r"\bClaro\s+(?:P[óo]s|Controle|Multi|Fibra|"
                         r"Pr[ée]|Prez[ãa]o|Flex)\b", nome or "", re.I):
        pass                     # fica com a ULTIMA: o nome comeca nela
    if not m or m.start() == 0:
        return nome, None        # nada antes da marca: nao ha banner
    campanha = nome[:m.start()].strip(" -|") or None
    return nome[m.start():].strip() or nome, campanha


# Os textos de acessibilidade da pagina: cada um descreve uma oferta
# inteira, com velocidade e preco na mesma frase. Ler assim evita o erro
# de parear por proximidade no markup.
FRASE = re.compile(
    r'(?:accessText|access_text|title|aria-label)"?\s*[:=]\s*"([^"]{15,260})"',
    re.I)

# Preco que so vale para quem ja e cliente nao entra (decisao 9).
CONDICIONADO = re.compile(
    r"cliente\s+claro|j[a\u00e1]\s+(?:e|\u00e9)\s+cliente|para\s+clientes",
    re.I)

# Frase que vende fibra e movel junta, dentro da pagina de fibra: e
# combo, e combo tem pagina propria.
TEM_MOVEL = re.compile(r"claro\s+p[o\u00f3]s|\d+\s*gb\b", re.I)

# Os GB de movel dentro de um combo: "Oferta de 500 Mega + Pos 60GB por
# apenas R$129,90". Sem isto o combo chegava na tela so com os Mbps da
# fibra, e o movel - que e metade da oferta - nao aparecia em lugar
# nenhum: duas ofertas de 600 Mega pareciam iguais quando uma traz
# 60 GB de movel e a outra nao traz movel nenhum.
GB_DO_MOVEL = re.compile(
    r"p[oó]s\s*(\d{1,4})\s*GB|(\d{1,4})\s*GB\s*(?:de\s*)?p[oó]s", re.I)


def _qualificador(frase, velocidade):
    """O que distingue esta oferta das outras da mesma velocidade."""
    f = frase.lower()
    if "rel\u00e2mpago" in f or "relampago" in f:
        return "Rel\u00e2mpago"
    if "mesh" in f:
        return "Mesh"
    if "especial" in f:
        return "Especial"
    if "a partir de" in f:
        return ""          # a oferta base, sem qualificador
    return ""


def ler_por_texto(op, url, produto):
    """Uma frase de acessibilidade, uma oferta.

    A versao anterior varria "N mega ... R$ X,XX" numa janela de 40
    caracteres do HTML e chamava tudo de "Claro Fibra N Mega". Tres
    ofertas de 750 Mega viravam um nome so, o banco guardava uma
    arbitrariamente, e a troca de qual sobrevivia virava mudanca de preco
    no tracker - aconteceu em 05/10.
    """
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s

    unidade = r"gb" if produto == "prepago" else r"mega|giga"
    achados, vistos = [], set()
    for m in FRASE.finditer(h):
        frase = re.sub(r"\s+", " ", m.group(1)).strip()
        mv = re.search(r"(\d{1,4})\s*(%s)" % unidade, frase, re.I)
        mp = re.search(r"R\$\s?(\d{1,3}(?:\.\d{3})?,\d{2})", frase)
        if not mv or not mp:
            continue
        if CONDICIONADO.search(frase):
            continue
        velocidade = int(mv.group(1))
        if mv.group(2).lower() == "giga":
            velocidade *= 1000
        # na pagina de fibra, frase que tambem vende movel e combo
        if produto == "fibra" and TEM_MOVEL.search(frase):
            continue

        qual = _qualificador(frase, velocidade)
        rotulo = {"fibra": "Fibra", "combo": "Multi", "prepago": "Pre"}[produto]
        sufixo = "Mega" if produto != "prepago" else "GB"
        nome = "Claro %s %s %s%s" % (rotulo, mv.group(1), sufixo,
                                     (" " + qual) if qual else "")
        preco = numero(mp.group(1))
        if (nome, preco) in vistos:
            continue
        vistos.add((nome, preco))
        ident = re.findall(r"internetId=([\d,]+)", h[m.start():m.start() + 900])
        # no combo, os GB do movel estao na mesma frase que a velocidade
        gb_movel = None
        if produto == "combo":
            mg = GB_DO_MOVEL.search(frase)
            if mg:
                gb_movel = int(mg.group(1) or mg.group(2))
        achados.append({
            "id_catalogo": ident[0][:40] if ident else None,
            "nome_oferta": nome,
            "destaque": "%s %s" % (mv.group(1), sufixo),
            "franquia_anunciada_gb": gb_movel,
            "preco_promocional": preco,
            # a frase inteira, que e a fonte do dado e explica a oferta
            "composicao": frase[:400],
        })

    # Mesmo nome com dois precos ainda seria indistinguivel no banco:
    # fica o menor, que e o criterio do tracker para o degrau, e o caso
    # vira aviso em vez de sumir calado.
    por_nome = {}
    repetidos = []
    for a in achados:
        antes = por_nome.get(a["nome_oferta"])
        if antes is None:
            por_nome[a["nome_oferta"]] = a
        else:
            repetidos.append(a["nome_oferta"])
            if a["preco_promocional"] < antes["preco_promocional"]:
                por_nome[a["nome_oferta"]] = a

    if not por_nome:
        return None, "nenhuma frase com velocidade e preco juntos - a pagina mudou"
    saida = list(por_nome.values())
    if repetidos:
        saida[0]["avisos_oferta"] = apps.juntar_avisos(
            saida[0].get("avisos_oferta"),
            apps.ressalva(
                "nomes repetidos na vitrine, com pre\u00e7os diferentes",
                "nomes repetidos com precos diferentes: %s"
                % ", ".join(sorted(set(repetidos)))))
    return saida, None
# O Prezao NAO pode usar a leitura por frase de acessibilidade.
#
# A pagina tem uma pergunta frequente sobre bonus de recarga: "ao
# recarregar R$20,00 ganhe 1GB de bonus, R$25,00 ganhe 2GB de bonus,
# R$30,00 ganhe 3GB de bonus". Qualquer varredura generica casa com ela
# e emparelha o bonus de um degrau com o preco do degrau SEGUINTE -
# foi assim que nasceram "Claro Pre 1 GB por R$ 25" e "Claro Pre 2 GB
# por R$ 30", dois planos que nunca existiram.
#
# A oferta de verdade esta numa tabela de quatro degraus, onde os precos
# e as franquias aparecem em listas paralelas, da maior para a menor:
#
#   Valor do saldo  R$ 30,00  R$ 25,00  R$ 20,00  R$ 15,00
#   PREZAO R$1 POR DIA  17GB + 3GB Youtube / 30 dias
#                       10GB + 2GB Youtube / 25 dias
#                       8GB + 2GB Youtube / 20 dias
#                       5GB / 15 dias
#
# OS QUATRO DEGRAUS ENTRAM, cada um com a validade, desde 25/11/2026.
# Ate ali so o de 30 dias entrava ("o tracker compara preco mensal"),
# enquanto Vivo e TIM gravavam todas as recargas - a entrada delas parecia
# R$ 20 contra R$ 30 da Claro. Escolha de quem le: todas, com a validade
# a vista, e a comparacao mensal fica com o leitor.
FAIXA_PREZAO = re.compile(
    r"Valor do saldo\s*((?:R\$\s?\d{1,3},\d{2}\s*){2,6})"
    r"(.{0,80}?)"
    r"((?:\d{1,3}\s*GB[^/]{0,40}?/\s*\d{1,3}\s*dias\s*){2,6})", re.I)


def ler_prezao(op, url):
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    t = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)

    m = FAIXA_PREZAO.search(t)
    if not m:
        return None, "a escada do Prezao nao foi reconhecida - a pagina mudou"
    precos = re.findall(r"R\$\s?(\d{1,3},\d{2})", m.group(1))
    degraus = re.findall(r"(\d{1,3})\s*GB(.{0,40}?)/\s*(\d{1,3})\s*dias", m.group(3), re.I)
    if len(precos) != len(degraus):
        return None, ("escada desalinhada: %d precos para %d degraus"
                      % (len(precos), len(degraus)))

    escada = "; ".join("R$ %s = %sGB%s/%s dias" % (p, g, extra.strip(), d)
                       for p, (g, extra, d) in zip(precos, degraus))
    # O SKEELO DAS VANTAGENS DO PRE, desde 25/11/2026. A pagina o oferece
    # "para clientes Claro Pre" - um best-seller por mes -, fora do card da
    # recarga, como a TIM poe o WhatsApp nas vantagens do pos. Vai NA
    # FRENTE da composicao, que tem teto de 400 caracteres.
    junto = ""
    if re.search(r"skeelo.{0,200}?clientes claro pr[eé]", t, re.I):
        junto = "Inclui Skeelo (um best-seller por mes para clientes Claro Pre). "
    saida = []
    for preco, (gigas, extra, dias) in zip(precos, degraus):
        # "17GB + 3GB Youtube" E 20 GB, E NAO 17. Ate 24/11/2026 a leitura
        # tomava 17 como o total e 3 como parte dele, e gravava 17 GB
        # anunciados e 14 de uso livre. O card da propria Claro desfaz a
        # duvida: "Melhor opcao 20GB R$30/30 dias - Para uso livre 17GB,
        # Para YouTube 3GB"; e o de R$ 25 diz "12GB" sobre "10GB + 2GB". O
        # anunciado e a soma; o de uso livre e o primeiro numero.
        app = re.search(r"\+\s*(\d{1,3})\s*GB", extra)
        livre = int(gigas)
        total = livre + (int(app.group(1)) if app else 0)
        saida.append({
            "id_catalogo": None,
            "nome_oferta": "Claro Prezao %sGB" % total,
            "destaque": "%s GB" % total,
            "franquia_anunciada_gb": total,
            "franquia_contratual_gb": livre if app else None,
            # "WhatsApp ilimitado com videochamadas", na tabela do Prezao
            "whatsapp": apps.whatsapp_incluso(t),
            "preco_promocional": numero(preco),
            "validade_dias": int(dias),
            "composicao": (junto + "Prezao R$1 por dia, renovacao a cada %s "
                           "dias. Escada completa: %s" % (dias, escada))[:400],
        })
    if not saida:
        return None, "a escada do Prezao veio vazia"
    return saida, None


# O CARD DE CONTRATAR de cada Prezao tematico, como a pagina o mostra:
#
#   Que tal levar o Prezao Kwai agora? 22GB 17GB uso livre + 5GB para
#   Kwai WhatsApp ilimitado para tudo. Ligacoes ilimitadas para qualquer
#   operadora do Brasil. Por apenas R$ 35 , 00 /mes Contratar
#
# O CARD, E NAO A TABELA DE RENOVACAO do pe da pagina: a tabela poe o Free
# Fire na coluna de R$ 35,00, e o card - o que o cliente contrata - diz
# R$ 34,99. O total e o primeiro numero (22 GB), o de uso livre o segundo
# (17), como no Prezao: "17GB + 3GB Youtube" sao 20 GB.
CARD_TEMATICO = re.compile(
    r"(\d{1,3})\s*GB\s+(\d{1,3})\s*GB\s+uso livre\s*\+\s*(\d{1,3})\s*GB\s+para\s+"
    r"([^\W\d][\w ]{1,20}?)\s+(WhatsApp ilimitado.{0,260}?)"
    r"Por apenas\s*R\$\s*(\d{1,3})\s*,\s*(\d{2})\s*/\s*(m[e\u00ea]s|\d{1,3}\s*dias)", re.I | re.S)
# a validade, na tabela de renovacao: "Prezao KWAI | 17GB + 5GB Kwai/30 dias"
VALIDADE_TEMATICO = re.compile(
    r"Prez[a\u00e3]o\s+([A-Za-z][A-Za-z ]{1,15}?)\s+\d{1,3}\s*GB\s*\+\s*\d{1,3}\s*GB\s*"
    r"[A-Za-z ]{1,15}?/\s*(\d{1,3})\s*dias", re.I)


def _so_letras(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def ler_prezao_tematico(op, url):
    u"""Os Prezoes tematicos: uma oferta por card de contratar."""
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    t = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)
    dias_por_tema = dict((_so_letras(m.group(1)), int(m.group(2)))
                         for m in VALIDADE_TEMATICO.finditer(t))
    saida, vistos = [], set()
    for m in CARD_TEMATICO.finditer(t):
        total, livre, extra_gb = int(m.group(1)), int(m.group(2)), int(m.group(3))
        tema = m.group(4).strip()
        if _so_letras(tema) in vistos:
            continue
        vistos.add(_so_letras(tema))
        corpo = m.group(5)
        preco = float("%s.%s" % (m.group(6), m.group(7)))
        periodo = m.group(8).lower()
        # "/mes" no card; a tabela de renovacao da os dias. Sem a tabela,
        # o mes do card vale 30 dias, como no Prezao
        dias = (int(re.sub(r"\D", "", periodo)) if "dia" in periodo
                else dias_por_tema.get(_so_letras(tema), 30))
        # o que vem alem dos gigas: voucher, cupom, diamantes
        brinde = re.sub(r"\s+", " ", re.split(r"Liga\S*es ilimitadas para qualquer operadora do Brasil\.?",
                                           corpo)[-1]).strip(" .")
        saida.append({
            "id_catalogo": None,
            "nome_oferta": "Claro Prezao %s %sGB" % (tema, total),
            "destaque": "%s GB" % total,
            "franquia_anunciada_gb": total,
            "franquia_contratual_gb": livre,
            "whatsapp": apps.whatsapp_incluso(corpo),
            "preco_promocional": preco,
            "validade_dias": dias,
            # A VARIANTE E O TEMA. Kwai e TikTok entregam os mesmos 22 GB,
            # e Uber, Shopee e Free Fire os mesmos 17: sem isto as cinco
            # dividiriam duas chaves, e a serie alternaria entre elas
            "variante": "prezao_" + _so_letras(tema),
            "composicao": ("Prezao %s: %sGB de uso livre + %sGB para %s, renovacao a cada %s dias."
                           "%s" % (tema, livre, extra_gb, tema, dias,
                                   (" " + brinde + ".") if brinde else ""))[:400],
        })
    if not saida:
        return None, "nenhum Prezao tematico reconhecido - a pagina mudou"
    return saida, None


# A FIBRA E O MULTI PELO CATALOGO, desde 27/11/2026.
#
# Ate 26/11 os dois eram lidos pelas FRASES DE ACESSIBILIDADE do HTML cru
# (ler_por_texto, que fica para quem quiser reler o passado), e nao pelos
# cards que o cliente ve: os cards sao montados pelo JavaScript a partir de
# /api/catalog. Medido em Sao Paulo em 17/11 e de novo em 26/11/2026:
#   - os planos de gigabit (1, 5 e 10 Giga, a R$ 179,90, 499,90 e
#     1.999,90) nunca entraram: a frase deles nao tem preco;
#   - o 350 Mega saia a 79,90 com o card a 89,90, e o 500 Mega a 109,90
#     com o card a 119,90;
#   - nenhum app entrava (a frase nao nomeia), com o card mostrando
#     Globoplay, Skeelo e McAfee;
#   - o Multi saia com tres ofertas que nao estao na vitrine (500 Mega a
#     119,90, 600 Mega + 60 GB a 159,90 e um "750 Mega Especial" a 99,90)
#     no lugar das que estao (750 Mega + Pos 100GB a 159,90, 1 Giga + Pos
#     100GB a 179,90 e os dois com TV).
#
# A FONTE E A MESMA CHAMADA QUE A PAGINA FAZ. A pagina traz os cards
# (componente card_360) no __NEXT_DATA__, cada um com um _uid; o catalogo
# responde, para a UF e a cidade pedidas, o produto, o preco e o texto de
# cada card. Publica, sem login. A cidade vai no endereco - nao depende do
# cookie da praca, que e de outro site (planoscelular).
#
# TRES REGRAS DA PAGINA QUE O CATALOGO NAO APLICA, e que a leitura aplica no
# lugar dela - sem elas entraria oferta que o cliente nao ve:
#   1. a JANELA DO CARD (scheduling): card com data so aparece dentro dela.
#      Em 26/11 o 600 Mega a 99,90 da pagina de fibra tinha janela de 15/11
#      e o catalogo ainda o resolvia;
#   2. a CIDADE EXCLUIDA (segments): o 1 Giga + Pos 100GB exclui 314
#      cidades, Blumenau entre elas, e o catalogo o devolve para Blumenau a
#      169,90;
#   3. o card que o catalogo NAO ACHA na cidade (notFound) nao aparece.
# Conferido no navegador em 26/11, Sao Paulo: as tres regras deixam
# exatamente os cards que a pagina mostra, nas tres abas do Multi.
#
# O MULTI E FIBRA + CELULAR. A aba "Quero streamings e internet pra casa"
# vende internet + TV, sem linha movel - nao e o combo que o tracker compara
# nas outras operadoras, e fica fora. A de familia (internet, celular e TV)
# entra, como os "+ TV" da Vivo.
CATALOGO = "https://www.claro.com.br/api/catalog"
NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
DE_POR = re.compile(r"de:?\s*~?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", re.I)
APOS = re.compile(r"ap[oó]s,?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", re.I)
MESES = re.compile(r"(\d+)\s*mes", re.I)
# O TETO DE APPS DO CARD DO CATALOGO. O de apps.py (6) existe porque o texto
# de uma PAGINA traz o portfolio inteiro em menu e rodape; o texto do
# catalogo e o do proprio card, produto por produto, e o Multi com TV nomeia
# 9 de verdade (Globoplay, Amazon Prime, Netflix, Disney+, HBO Max, Apple TV,
# Skeelo, McAfee...). Com o teto de 6 a lista saia vazia e o aviso dizia
# "a leitura pegou a vitrine junto com o card" - falso. O teto continua,
# mais alto, contra o dia em que o catalogo trouxer a pagina inteira.
LIMITE_DE_APPS_DO_CARD = 12
# QUANTOS CARDS POR CHAMADA. Medido em 26/11/2026: com 21 _uids o catalogo
# responde; com 22 ou mais devolve TODOS como notFound, com HTTP 200 e sem
# erro nenhum - o Multi tem 23 cards na pagina. A pagina pede por aba (no
# maximo 10), e a leitura pede em lotes do mesmo tamanho.
LOTE_DO_CATALOGO = 10
# "50GB + 50GB bonus": a primeira parcela e a contratual, a outra e bonus
BONUS_MOVEL = re.compile(r"(\d+)\s*GB\s*\+\s*(\d+)\s*GB\s*b[oô]nus", re.I)


def _cards_360(no):
    """Os itens de cada componente card_360 publico da pagina, em ordem."""
    if isinstance(no, dict):
        if no.get("component") == "card_360":
            dados = no.get("data") or {}
            if dados.get("environment") == "public":
                for it in dados.get("data") or ():
                    if isinstance(it, dict) and it.get("_uid"):
                        yield it
            return
        for v in no.values():
            yield from _cards_360(v)
    elif isinstance(no, list):
        for v in no:
            yield from _cards_360(v)


def _data_do_card(txt, fuso):
    try:
        return datetime.strptime(txt.strip(), "%d/%m/%Y %H:%M").replace(tzinfo=fuso)
    except (ValueError, AttributeError):
        return None


def no_ar(item, agora):
    """O card esta dentro da janela dele? Sem janela, sempre."""
    s = item.get("scheduling") or {}
    ini = _data_do_card(s.get("datetimeStart") or "", agora.tzinfo)
    fim = _data_do_card(s.get("datetimeEnd") or "", agora.tzinfo)
    if ini and agora < ini:
        return False
    if fim and agora > fim:
        return False
    return True


def _nome_de_lugar(x):
    if isinstance(x, dict):
        x = x.get("name") or x.get("uf") or x.get("value") or ""
    return sem_acento(str(x or "")).strip().lower()


def na_cidade(item, cidade, uf):
    """O segmento do card deixa a cidade ver? Sem segmento, deixa.

    Basta um segmento que inclua: UF listada (ou nenhuma), cidade listada
    (ou nenhuma) e a cidade fora da lista de exclusao. Segmento por DDD ou
    por rede nao se resolve daqui: o card entra, e a ressalva sai dita.
    Devolve (deixa, ressalva)."""
    segs = ((item.get("segments") or {}).get("data")) or []
    if not segs:
        return True, None
    alvo, uf = _nome_de_lugar(cidade), (uf or "").upper()
    for s in segs:
        if not isinstance(s, dict):
            continue
        ufs = [_nome_de_lugar(u).upper() for u in s.get("ufs") or ()]
        cidades = [_nome_de_lugar(c) for c in s.get("cities") or ()]
        fora = {((c.get("uf") or "").upper(), _nome_de_lugar(c))
                for c in s.get("cities_exclusion") or () if isinstance(c, dict)}
        if ufs and uf not in ufs:
            continue
        if cidades and alvo not in cidades:
            continue
        if (uf, alvo) in fora:
            continue
        if s.get("ddds") or s.get("networkType") or s.get("networkName"):
            return True, "segmento por DDD ou rede, que a leitura nao resolve"
        return True, None
    return False, None


def preco_do_catalogo(item):
    """(preco, preco_cheio, meses, preco_depois) como o card mostra.

    O preco e o texto do card, e nao a soma dos produtos: no Multi o
    catalogo da 99,90 pela fibra e 124,90 pelo Pos, e o card cobra 159,90.
    O "De:" riscado e o preco cheio. O "2 meses" do periodo sozinho nao e
    promocao - o card diz "Valor mensal"; so o "Apos, R$ X" do sufixo e."""
    acoes = item.get("actions") or [{}]
    p = (acoes[0] if isinstance(acoes[0], dict) else {}).get("price") or {}
    preco = numero(p.get("price"))
    m = DE_POR.search(p.get("prefix") or "")
    cheio = numero(m.group(1)) if m else None
    if cheio is not None and (preco is None or cheio <= preco):
        cheio = None
    suf = p.get("suffix") or ""
    m = APOS.search(suf)
    depois = numero(m.group(1)) if m else None
    meses = None
    if depois is not None:
        mm = MESES.search("%s %s" % (p.get("period") or "", suf))
        meses = int(mm.group(1)) if mm else None
    return preco, cheio, meses, depois


def _texto_do_card(item, produtos):
    """O que o card escreve, na ordem dele, e o que cada produto inclui.

    A fibra traz os itens soltos ({label}); o Multi, um bloco por produto
    ({title, description, detail}). O logo de marca (brandGroup) entra
    entre parenteses: "Streaming incluso" so diz qual com ele."""
    def item_de(d):
        rot = re.sub(r"\s+", " ", d.get("label") or "").strip()
        marcas = [b.get("alt") for b in ((d.get("group") or {}).get("brandGroup") or ())
                  if isinstance(b, dict) and b.get("alt")]
        marcas = [m for m in marcas if m.lower() not in rot.lower()]
        return ("%s (%s)" % (rot, ", ".join(marcas))) if marcas else rot

    blocos, soltos = [], []
    for d in item.get("detail") or ():
        if not isinstance(d, dict):
            continue
        if isinstance(d.get("detail"), list):
            cab = ", ".join(x.strip() for x in (d.get("title") or "", d.get("description") or "")
                            if x and x.strip())
            itens = [item_de(x) for x in d["detail"] if isinstance(x, dict)]
            blocos.append("%s: %s" % (cab, "; ".join(i for i in itens if i)) if cab else
                          "; ".join(i for i in itens if i))
        else:
            soltos.append(item_de(d))
    partes = []
    titulo = ((item.get("heading") or {}).get("children") or "").strip()
    if soltos:
        partes.append(("%s: " % titulo if titulo and "{{" not in titulo else "") +
                      "; ".join(s for s in soltos if s))
    partes.extend(b for b in blocos if b)
    inclui = []
    for prod in produtos:
        for r in (prod.get("recursos") or {}).values():
            if isinstance(r, dict):
                t = (r.get("descricao") or r.get("nome") or "").strip()
                if t and t not in inclui:
                    inclui.append(t)
    if inclui:
        partes.append("Inclui: " + ", ".join(inclui))
    return ". ".join(partes)


def _cidade_do_catalogo(cidade):
    """'Sao Paulo' -> 'sao_paulo', como a pagina pede."""
    return re.sub(r"\s+", "_", sem_acento(cidade).strip().lower())


def ler_catalogo(op, url, produto, cidade, uf, agora):
    u"""A fibra ou o Multi como o card mostra. Ver o cabecalho do bloco.

    Falha alto em vez de devolver vazio: pagina sem card, catalogo que nao
    responde e catalogo que nao resolve NENHUM card da cidade (cidade que o
    catalogo nao reconhece devolve tudo notFound - medido com uma cidade
    inventada em 26/11) sao erro, para nao virarem saida de oferta."""
    s, h = buscar(op, url)
    if s != 200:
        return None, "HTTP %s" % s
    m = NEXT_DATA.search(h)
    if not m:
        return None, "a pagina nao trouxe o __NEXT_DATA__ - a pagina mudou"
    try:
        itens = list(_cards_360(json.loads(m.group(1))))
    except ValueError as e:
        return None, "o __NEXT_DATA__ nao abriu (%s)" % str(e)[:80]
    if not itens:
        return None, "nenhum card do catalogo na pagina - a pagina mudou"
    hoje = [it for it in itens if no_ar(it, agora)]
    if not hoje:
        return None, "nenhum card da pagina dentro da janela de hoje"
    resp = {}
    for i in range(0, len(hoje), LOTE_DO_CATALOGO):
        q = urllib.parse.urlencode([
            ("state", uf.upper()), ("city", _cidade_do_catalogo(cidade)),
            ("environment", "public"), ("component", "card_360"),
            ("uuids", ",".join(it["_uid"] for it in hoje[i:i + LOTE_DO_CATALOGO])),
            ("editMode", "false")], safe=",")
        s, t = buscar(op, CATALOGO + "?" + q, extras={"Accept": "application/json"})
        if s != 200:
            return None, "catalogo HTTP %s" % s
        try:
            resp.update({x.get("_uid"): x for x in (json.loads(t).get("data") or ())
                         if isinstance(x, dict)})
        except (ValueError, AttributeError) as e:
            return None, "o catalogo nao abriu (%s)" % str(e)[:80]

    achados, resolvidos, ressalvas = [], 0, []
    for it in hoje:
        x = resp.get(it["_uid"])
        cat = (x or {}).get("catalog") or {}
        if not x or cat.get("notFound"):
            continue
        resolvidos += 1
        deixa, ressalva = na_cidade(x if x.get("segments") else it, cidade, uf)
        if not deixa:
            continue
        internet = cat.get("internet") or {}
        celular = cat.get("celular") or {}
        tv = cat.get("tv") or {}
        if not internet.get("nome"):
            continue
        # a pagina de fibra so vende fibra; no Multi, sem celular nao e combo
        if produto == "fibra" and (celular or tv):
            continue
        if produto == "combo" and not celular:
            continue
        preco, cheio, meses, depois = preco_do_catalogo(x)
        if preco is None:
            ressalvas.append("card sem preco: %s" % internet.get("nome"))
            continue
        nome_int = re.sub(r"\s+", " ", internet["nome"]).strip()
        produtos = [p for p in (internet, celular, tv) if p]
        texto = _texto_do_card(x, produtos)
        if produto == "fibra":
            nome = "Claro Fibra %s" % nome_int
            gb_movel = contratual = None
            ident = str(internet.get("id") or "") or None
            codigo = internet.get("rgc") or None
        else:
            movel = re.sub(r"\s+", " ", celular.get("nomeAutomatico")
                           or celular.get("nome") or "").strip()
            nome = "Claro Multi %s + %s" % (nome_int, movel)
            if tv:
                nome += " + TV %s" % ("Soundbox" if "soundbox" in
                                      (tv.get("nome") or "").lower() else "Box")
            gb_movel = gb(movel)
            mb = BONUS_MOVEL.search(texto)
            contratual = int(mb.group(1)) if mb else None
            ident = "%s+%s" % (internet.get("id"), celular.get("id"))
            codigo = None
        if ressalva:
            ressalvas.append("%s: %s" % (nome, ressalva))
        achados.append({
            "id_catalogo": ident,
            "nome_oferta": nome,
            "destaque": nome_int,
            "franquia_anunciada_gb": gb_movel,
            "franquia_contratual_gb": contratual,
            "preco_promocional": preco,
            "preco_cheio": cheio,
            "meses_desconto": meses,
            "preco_pos_promocao": depois,
            "codigo_anatel": codigo,
            # o texto inteiro do card: e dele que saem os apps, e o Multi
            # com TV passa de 700 caracteres com a lista do pacote
            "composicao": texto[:1500],
            "limite_apps": LIMITE_DE_APPS_DO_CARD,
        })
    if not resolvidos:
        return None, ("o catalogo nao resolveu nenhum card em %s/%s - "
                      "a cidade nao foi reconhecida" % (cidade, uf))
    if not achados:
        return None, ("nenhum card de %s visivel em %s/%s depois das regras "
                      "da pagina" % (produto, cidade, uf))

    # Mesmo nome com dois precos seria indistinguivel no banco: fica o
    # menor e o caso vira aviso, como na leitura por frase.
    por_nome, repetidos = {}, []
    for a in achados:
        antes = por_nome.get(a["nome_oferta"])
        if antes is None:
            por_nome[a["nome_oferta"]] = a
        elif a["preco_promocional"] != antes["preco_promocional"]:
            repetidos.append(a["nome_oferta"])
            if a["preco_promocional"] < antes["preco_promocional"]:
                por_nome[a["nome_oferta"]] = a
    saida = list(por_nome.values())
    if repetidos:
        saida[0]["avisos_oferta"] = apps.juntar_avisos(
            saida[0].get("avisos_oferta"),
            apps.ressalva(
                "nomes repetidos na vitrine, com preços diferentes",
                "nomes repetidos com precos diferentes: %s"
                % ", ".join(sorted(set(repetidos)))))
    if ressalvas:
        saida[0]["avisos_oferta"] = apps.juntar_avisos(
            saida[0].get("avisos_oferta"),
            apps.ressalva("leitura do catalogo com ressalva",
                          "; ".join(ressalvas)[:300]))
    return saida, None


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
        if produto == "prepago":
            cards, erro = ler_prezao(op, url)
            # os tematicos vem de outra pagina: uma falha la nao derruba o
            # Prezao, e a do Prezao nao derruba os tematicos - cada uma
            # sai dita nos avisos
            time.sleep(PAUSA)
            temas, erro_t = ler_prezao_tematico(op, PREZAO_TEMATICOS)
            if erro_t:
                saida["avisos"].append("prepago tematicos: %s" % erro_t)
                if verbose:
                    print("  %-7s FALHOU nos tematicos (%s)" % (produto, erro_t))
            elif erro:
                saida["avisos"].append("%s: %s" % (produto, erro))
                cards, erro = [], None
            if temas:
                cards = (cards or []) + temas
        elif produto in POR_TEXTO:
            cards, erro = ler_catalogo(op, url, produto, cidade, uf, agora)
        else:
            cards, erro = ler_cards(op, url, produto)
        if erro:
            saida["avisos"].append("%s: %s" % (produto, erro))
            if verbose:
                print("  %-7s FALHOU (%s)" % (produto, erro))
            time.sleep(PAUSA)
            continue
        for c in cards:
            nome = c["nome_oferta"]
            # so o catalogo traz o teto proprio; os outros usam o de apps.py
            lim = c.pop("limite_apps", None)
            # o texto de onde saem os apps: o card inteiro, quando o leitor
            # o tem (ler_cards); senao a composicao
            fonte_apps = c.pop("texto_apps", None) or c.get("composicao")
            if produto == "prepago":
                real = "prepago"
            elif produto in POR_TEXTO:
                real = produto          # a pagina ja define o produto
            elif "controle" in nome.lower():
                real = "controle"
            else:
                real = "movel"
            c.update({
                "operadora": "Claro", "produto": real, "praca": praca,
                "capturado_em": agora.isoformat(),
                # o Prezao ja chega com as duas franquias resolvidas
                "franquia_anunciada_gb": c.get("franquia_anunciada_gb") if real in ("prepago", "combo")
                    else (gb(c["destaque"]) if real not in ("fibra", "combo") else None),
                "franquia_contratual_gb": c.get("franquia_contratual_gb")
                    if real in ("prepago", "combo")
                    else franquia_contratual(c["composicao"]),
                "degrau_mbps": mbps(c["destaque"]) if real in ("fibra", "combo") else None,
                "nivel_bundle": nivel_bundle(fonte_apps),
                # a frase da vitrine nomeia o que acompanha a oferta, e
                # as vezes tambem o tier ("Netflix Padrao")
                "apps": apps.apps_do_texto(fonte_apps, limite=lim),
                "apps_rotulo": apps.rotulo(
                    apps.apps_do_texto(fonte_apps, limite=lim),
                    fonte_apps, c.get("nome_oferta")),
                "apps_planos": apps.planos_dos_apps(
                    apps.apps_do_texto(fonte_apps, limite=lim),
                    fonte_apps, c.get("nome_oferta")),
                # A LEITURA LARGA SAI DITA. Acima do limite de apps a
                # lista vira vazia, e vazio quer dizer "nenhum app
                # nomeado" - nivel 0, "sem assinatura inclusa" na
                # tela. O aviso vai para avisos_oferta, que a
                # mensagem e o relatorio leem.
                "avisos_oferta": apps.juntar_avisos(
                    c.get("avisos_oferta"),
                    apps.aviso_de_leitura(fonte_apps, limite=lim)),
                # so o catalogo (fibra e Multi) preenche os dois; os
                # outros leitores nao os tem e continuam None
                "preco_cheio": c.get("preco_cheio"),
                "codigo_anatel": c.get("codigo_anatel"),
                # a campanha, quando houve, veio do card e nao pode ser
                # zerada aqui: e ela que explica por que o nome da oferta
                # mudou naquele dia
                "campanha": c.get("campanha"),
                "ibge": ibge,
            })
            saida["ofertas"].append(c)
        if verbose:
            print("  %-7s %d ofertas" % (produto, len(cards)))
        time.sleep(PAUSA)

    # OS PLANOS SEM FIDELIDADE, da loja - ver ler_sem_fidelidade. Se a loja
    # nao responde, o pos e o controle saem da praca hoje, como a pagina
    # extra da Vivo: o que so ela traz nao pode virar "saida da vitrine".
    sem_fid, erro = ler_sem_fidelidade(op)
    if erro:
        antes = len(saida["ofertas"])
        saida["ofertas"] = [o for o in saida["ofertas"]
                            if o["produto"] not in ("movel", "controle")]
        saida["avisos"].append(
            "movel, controle fora da praca hoje: a loja sem fidelidade falhou "
            "(%s), e o que so ela traz nao pode sair como saida - %d ofertas "
            "deixadas de fora" % (erro, antes - len(saida["ofertas"])))
    else:
        for o in sem_fid:
            saida["ofertas"].append(dict(o, praca=praca, capturado_em=agora.isoformat(),
                                         ibge=ibge))
        if verbose:
            print("  %-7s %d ofertas" % ("sem fidelidade", len(sem_fid)))
    return saida


# OS PLANOS SEM FIDELIDADE DA LOJA (27/11/2026). Escolha de quem le em
# 26/11, "incluir, como a Vivo sem apps": a loja vende o Controle de 15 e
# 20 GB e o Pos de 50 a 200 GB sem fidelidade, em duas familias cada - com
# os apps exclusivos (Skeelo, Truecaller, Claro Banca) e sem eles -, e a
# vitrine principal so linka a loja. Os precos estao no __NEXT_DATA__ da
# pagina: "price" e o preco do plano; o "paymentComboPrices" mais baixo e o
# do debito automatico, condicionado, e fica de fora. A loja nao muda com a
# praca (medido na auditoria de 26/11) e e lida uma vez por rodada.
LOJA_SEM_FIDELIDADE = "https://loja.claro.com.br/c/planos-de-celular/sem-fidelidade"
_cache_sem_fidelidade = {}


def ler_sem_fidelidade(op):
    if "ofertas" in _cache_sem_fidelidade:
        return [dict(o) for o in _cache_sem_fidelidade["ofertas"]], None
    s, h = buscar(op, LOJA_SEM_FIDELIDADE)
    if s != 200:
        return None, "HTTP %s" % s
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    try:
        pagina = json.loads(m.group(1))["props"]["pageProps"]
    except Exception:
        return None, "a loja sem fidelidade mudou de formato (sem __NEXT_DATA__)"
    saida, vistos = [], set()
    for chave, produto, rotulo in (("productsPos", "movel", u"Claro Pós"),
                                   ("productsControle", "controle", u"Claro Controle")):
        for p in pagina.get(chave) or ():
            preco = (p.get("price") or {}).get("value")
            g = re.match(r"\s*(\d{1,4})", p.get("identifier") or p.get("name") or "")
            if preco is None or not g:
                continue
            nomes = [i.get("title") for i in ((p.get("exclusiveApps") or {}).get("items") or ())
                     if i.get("title")]
            # os icones de cada grupo tambem nomeiam app: o Controle lista so
            # a Claro Banca em exclusiveApps e o Skeelo so no grupo
            # "SVSkeeloBanca". O grupo que e escolha ("Google One ou
            # iCloud+") vai so pela frase, para o "ou" continuar valendo.
            partes = []
            for x in (p.get("planAppsGroups") or ()):
                desc = x.get("description") or ""
                partes.append(desc + ".")
                if not re.search(r"\sou\s", desc, re.I):
                    for ic in (x.get("icons") or ()):
                        n = ic.get("name") or ic.get("title") or ic.get("alt")
                        if n and n not in nomes:
                            nomes.append(n)
            grupos = " ".join(partes)
            texto = ((u"Apps exclusivos para você: %s. " % ", ".join(nomes)) if nomes else "") + grupos
            lista = apps.apps_do_texto(texto)
            nome = u"%s sem fidelidade%s" % (rotulo, "" if nomes else " sem apps")
            identidade = (nome, int(g.group(1)), float(preco))
            if identidade in vistos:
                continue
            vistos.add(identidade)
            saida.append({
                "operadora": "Claro", "produto": produto,
                "id_catalogo": p.get("code"),
                "nome_oferta": nome,
                "destaque": "%sGB" % g.group(1),
                "franquia_anunciada_gb": int(g.group(1)),
                "franquia_contratual_gb": None,
                "preco_promocional": float(preco),
                "preco_cheio": None,
                "fidelidade_meses": 0,
                "nivel_bundle": apps.nivel_dos_apps(lista),
                "apps": lista,
                "apps_rotulo": apps.rotulo(lista, texto),
                "apps_planos": apps.planos_dos_apps(lista, texto),
                # "estes planos nao possuem WhatsApp ilimitado", e o Controle
                # e "sem redes sociais inclusos"
                "whatsapp": False,
                "composicao": (u"%s %sGB sem fidelidade, na loja. %s" % (rotulo, g.group(1), texto))[:400],
                "codigo_anatel": None, "campanha": None, "validade_dias": None,
                "pagina": "sem fidelidade",
            })
    if not saida:
        return None, "nenhum plano reconhecido na loja sem fidelidade"
    _cache_sem_fidelidade["ofertas"] = saida
    return [dict(o) for o in saida], None


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
