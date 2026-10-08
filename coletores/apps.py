"""Qual app cada oferta inclui, pelo nome da oferta.

POR QUE EXISTE. O tracker sabia que uma oferta tem bundle (nivel 0 a 4),
mas nao QUAL app. Na tela isso virava "Uma assinatura (Netflix, YouTube,
Vale Saude...)" - uma lista de exemplos, nao o conteudo da oferta. Duas
ofertas de R$ 85 apareciam identicas quando uma traz Netflix e a outra,
telemedicina.

DE ONDE SAI. Do nome da oferta, que e onde a Vivo nomeia o app: "Vivo
Controle Netflix", "Vivo Pos com Disney+", "Vivo Controle Saude". E a
leitura mais confiavel que ela oferece - os codigos SVA do regulamento
vem todos no mesmo bloco e nao distinguem uma oferta da outra, e foi por
isso que o dicionario_sva.py so conseguiu associar 1 de 20 codigos.

QUAL PLANO, quando se sabe. A vitrine declara: "Assinatura Netflix Padrao
inclusa", "Assinatura YouTube Premium Lite inclusa", "Assinatura Spotify
Premium inclusa". Onde ela nao declara - "Assinatura Globoplay inclusa" -
o plano fica sem nome, porque Globoplay tem dois com precos diferentes.

O QUE ESTE MODULO NAO FAZ: subtrair o preco do app do preco do plano.
O preco de varejo esta aqui como referencia do que o assinante receberia,
com fonte e data, e nunca entra numa conta que mude o preco da oferta.
"""

import re

# app -> o que se sabe dele. O preco e REFERENCIA, nunca parcela de
# conta: serve para dizer "este plano inclui Netflix Padrao, que avulso
# custa R$ 44,90", e so.
APPS = {
    "netflix": {
        "nome": "Netflix", "plano": "Padrão", "preco_avulso": 44.90,
        "fonte": "https://help.netflix.com/pt/node/24926",
        "conferido_em": "2026-10-08",
        "evidencia": "Padrão : R$ 44,90/mês",
    },
    "disney": {
        "nome": "Disney+", "plano": "Padrão", "preco_avulso": 49.90,
        "fonte": "https://www.disneyplus.com/pt-br",
        "conferido_em": "2026-10-08",
        "evidencia": "colunas Premium / Padrão / Padrão com anúncios "
                     "sobre R$ 69,90 / R$ 49,90 / R$ 29,90",
    },
    "spotify": {
        "nome": "Spotify", "plano": "Premium Individual", "preco_avulso": 23.90,
        "fonte": "https://www.spotify.com/br-pt/premium/",
        "conferido_em": "2026-10-08",
        "evidencia": "Premium Individual. R$ 0 por 1 mês, depois R$ 23,90 por mês",
    },
    "youtube": {
        "nome": "YouTube Premium", "plano": "Lite", "preco_avulso": 16.90,
        "fonte": "https://www.youtube.com/premium",
        "conferido_em": "2026-10-08",
        "evidencia": "Premium Lite ... Monthly R$16.90/month",
    },
    "globoplay": {
        "nome": "Globoplay", "plano": None, "preco_avulso": None,
        "fonte": "https://globoplay.globo.com/assine/",
        "conferido_em": "2026-10-08",
        "evidencia": "a Vivo nao diz qual plano inclui, e Globoplay tem "
                     "Padrao com anuncios e Premium com precos diferentes",
    },
    "amazon": {
        "nome": "Amazon Prime", "plano": None, "preco_avulso": None,
        "fonte": "https://www.amazon.com.br/amazonprime",
        "conferido_em": "2026-10-08",
        "evidencia": "a pagina responde 503 a leitura automatica",
    },
    "premiere": {"nome": "Premiere", "plano": None, "preco_avulso": None,
                 "fonte": None, "conferido_em": None,
                 "evidencia": "ainda nao conferido"},
    "vale_saude": {"nome": "Vale Saúde Sempre", "plano": None,
                   "preco_avulso": None, "fonte": None, "conferido_em": None,
                   "evidencia": "telemedicina, nao streaming"},
    "vivae": {"nome": "Vivae", "plano": None, "preco_avulso": None,
              "fonte": None, "conferido_em": None,
              "evidencia": "educacao, nao streaming"},
    "vivo_tv": {"nome": "Vivo TV Inicial", "plano": None, "preco_avulso": None,
                "fonte": None, "conferido_em": None,
                "evidencia": "servico da propria Vivo; nao ha preco avulso"},
    "vivo_travel": {"nome": "Vivo Travel", "plano": None, "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "roaming, nao e app de assinatura"},
    "vivo_musica": {"nome": "Vivo Música", "plano": None, "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "servico da propria Vivo; nao ha preco avulso"},

    # --- apps de catalogo: aparecem no TEXTO da oferta, nao no nome.
    # Sao o conteudo tipico do nivel 1, e o leitor merece saber quais
    # sao em vez de ler "apps menores".
    "paramount": {"nome": "Paramount+", "plano": None, "preco_avulso": None,
                  "fonte": None, "conferido_em": None,
                  "evidencia": "ainda nao conferido"},
    "max": {"nome": "Max", "plano": None, "preco_avulso": None,
            "fonte": None, "conferido_em": None,
            "evidencia": "ainda nao conferido"},
    "telecine": {"nome": "Telecine", "plano": None, "preco_avulso": None,
                 "fonte": None, "conferido_em": None,
                 "evidencia": "ainda nao conferido"},
    "deezer": {"nome": "Deezer", "plano": None, "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "ainda nao conferido"},
    "skeelo": {"nome": "Skeelo", "plano": None, "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo, sem preco avulso relevante"},
    "mcafee": {"nome": "McAfee", "plano": None, "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo, sem preco avulso relevante"},
    "aya_books": {"nome": "Aya Books", "plano": None, "preco_avulso": None,
                  "fonte": None, "conferido_em": None,
                  "evidencia": "app de catalogo da TIM"},
    "aya_ensinah": {"nome": "Aya Ensinah", "plano": None, "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "app de catalogo da TIM"},
    "exa": {"nome": "EXA Segurança", "plano": None, "preco_avulso": None,
            "fonte": None, "conferido_em": None,
            "evidencia": "app de catalogo da TIM"},
    "goread": {"nome": "GoRead", "plano": None, "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo"},
    "claro_musica": {"nome": "Claro Música", "plano": None,
                     "preco_avulso": None, "fonte": None, "conferido_em": None,
                     "evidencia": "servico da propria Claro"},
}

# A ordem importa: "YouTube Premium" tem de ser testado antes de
# qualquer regra mais curta que pudesse casar dentro dele.
DO_NOME = (
    (r"youtube\s*premium", "youtube"),
    (r"\bnetflix\b", "netflix"),
    (r"\bdisney", "disney"),
    (r"\bspotify\b", "spotify"),
    (r"\bgloboplay\b", "globoplay"),
    (r"\bamazon\b", "amazon"),
    (r"\bpremiere\b", "premiere"),
    (r"\bsa[úu]de\b", "vale_saude"),
    (r"\beduca[çc][ãa]o\b", "vivae"),
    (r"\bentretenimento\b", "vivo_tv"),
    (r"\btravel\b", "vivo_travel"),
    (r"\bm[úu]sica\b", "vivo_musica"),
)


# Os mesmos apps, procurados num TEXTO livre - a descricao da oferta.
# Claro e TIM nao nomeiam o app no nome da oferta, mas descrevem no
# texto. Aqui a regra tem de ser mais exigente que no nome: texto de
# pagina mistura o que a oferta tem com o que a operadora vende ao lado.
# Nao herda DO_NOME: "Musica", "Saude", "Educacao", "Entretenimento" e
# "Travel" sao sufixos com que a VIVO batiza a oferta, e nao nomes de
# app. Soltos num texto livre casam com qualquer coisa - "Claro Musica e
# Skeelo inclusos" virava "Vivo Musica + Skeelo + Claro Musica". Aqui so
# entra nome proprio de app.
DO_TEXTO = (
    (r"youtube\s*premium", "youtube"),
    (r"\bnetflix\b", "netflix"),
    (r"\bdisney", "disney"),
    (r"\bspotify\b", "spotify"),
    (r"\bgloboplay\b", "globoplay"),
    (r"amazon\s*prime", "amazon"),
    (r"\bpremiere\b", "premiere"),
    (r"vale\s*sa[úu]de", "vale_saude"),
    (r"\bvivae\b", "vivae"),
    (r"\bparamount\b", "paramount"),
    (r"\bmax\b", "max"),
    (r"\btelecine\b", "telecine"),
    (r"\bdeezer\b", "deezer"),
    (r"\bskeelo\b", "skeelo"),
    (r"\bmcafee\b", "mcafee"),
    (r"aya\s*books", "aya_books"),
    (r"aya\s*ensinah", "aya_ensinah"),
    (r"\bexa\b", "exa"),
    (r"\bgoread\b", "goread"),
    (r"claro\s*m[úu]sica", "claro_musica"),
)


# Marcas de que o app e DEGUSTACAO, e nao assinatura inclusa. A Claro
# escreve "Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes" no
# meio da descricao do plano; lido como incluso, o plano parecia muito
# melhor do que e. Beneficio que acaba e desconto condicionado ao tempo,
# e a decisao 9 ja o exclui.
DEGUSTACAO = re.compile(
    r"por conta d[ao]|ap[óo]s,?\s*r\$|gr[áa]tis por|"
    r"\d+\s*(?:m[êe]s|meses)\s*(?:gr[áa]tis|de cortesia|por conta)|"
    r"cortesia|degusta[çc][ãa]o|experimente|primeiros?\s+\d+\s*(?:m[êe]s|meses)",
    re.I)

# Quanto texto em volta do app conta para decidir se e degustacao. Uma
# frase de vitrine cabe nisso; dois paragrafos, nao - e ai a janela
# comecaria a pegar oferta vizinha.
JANELA = 110


def apps_do_texto(texto, limite=6):
    """Os apps nomeados num texto de oferta, fora os em degustacao.

    O limite existe porque pagina de operadora lista o portfolio inteiro
    em rodape e menu: um texto que "contem" oito streamings quase nunca
    e uma oferta com oito streamings, e sim um trecho que pegou a
    vitrine junto. Acima do limite, a leitura e descartada.
    """
    t = (texto or "").lower()

    # onde cada app e citado, para uma janela nao invadir a do vizinho
    posicoes = []
    for padrao, app in DO_TEXTO:
        m = re.search(padrao, t)
        if m:
            posicoes.append((m.start(), m.end(), app))
    posicoes.sort()

    achados = []
    for i, (ini, fim, app) in enumerate(posicoes):
        if app in achados:
            continue
        # a janela vai do nome ate o que vier primeiro: o proximo app,
        # um ponto, um ponto-e-virgula, ou o limite de caracteres
        corte = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(t)
        trecho = t[fim:min(corte, fim + JANELA)]
        for p in (".", ";"):
            k = trecho.find(p)
            if k >= 0:
                trecho = trecho[:k]
        if DEGUSTACAO.search(t[max(0, ini - 24):ini] + trecho):
            continue
        achados.append(app)
    return [] if len(achados) > limite else achados


def apps_da_oferta(nome):
    """As chaves dos apps que o nome da oferta anuncia."""
    t = (nome or "").lower()
    achados = []
    for padrao, app in DO_NOME:
        if re.search(padrao, t) and app not in achados:
            achados.append(app)
    return achados


def rotulo(apps):
    """"Netflix (Padrão)" ou "Netflix + Spotify". Vazio se nao houver."""
    nomes = []
    for a in apps or ():
        e = APPS.get(a)
        if not e:
            continue
        nomes.append("%s (%s)" % (e["nome"], e["plano"]) if e.get("plano")
                     else e["nome"])
    return " + ".join(nomes)
