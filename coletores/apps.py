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
