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

QUAL PLANO - E SO QUANDO A FONTE DIZ. Medido em 15/10/2026, a Vivo
declara o tier em tres lugares e cada um conta: o nome na vitrine
("Vivo Controle YouTube Premium"), o nome registrado na Anatel dentro do
regulamento ("VIVO POS COM DISNEY+ PADRAO", "VIVO POS COM SPOTIFY
PREMIUM") e o texto do card. Onde nenhum dos tres declara, o tier fica
vazio - e com ele o preco de referencia, porque o preco pertence ao
tier, nao ao app.

Netflix e o caso que obrigou esta regra. A oferta se chama "Vivo Pos com
Netflix", o nome na Anatel e "VIVO POS COM NETFLIX" e o regulamento
inteiro - 1.928 caracteres - nao tem a palavra Padrao, Premium nem
anuncio em lugar nenhum. O tracker vinha escrevendo "Netflix (Padrao)" e
R$ 44,90 por conta de um padrao no dicionario. Era palpite com cara de
dado: a Vivo pode estar dando qualquer um dos tres planos.

O QUE ESTE MODULO NAO FAZ: subtrair o preco do app do preco do plano.
O preco de varejo esta aqui como referencia do que o assinante receberia,
com fonte e data, e nunca entra numa conta que mude o preco da oferta.
"""

import re

# app -> o que se sabe dele. O preco e REFERENCIA, nunca parcela de
# conta: serve para dizer "este plano inclui Netflix Padrao, que avulso
# custa R$ 44,90", e so.
#
# "preco_avulso" aqui no nivel do app vale para quem tem UM plano so.
# Quem tem varios guarda preco em TIERS, por tier, e nao recebe preco
# nenhum quando a fonte nao diz qual deles e.
APPS = {
    "netflix": {
        "nome": "Netflix", "preco_avulso": None,
        "fonte": "https://help.netflix.com/pt/node/24926",
        "conferido_em": "2026-10-08",
        "evidencia": "tres planos com precos diferentes; o preco so vale "
                     "com o tier declarado pela operadora, e nenhuma "
                     "declara. Padrão: R$ 44,90/mês",
    },
    "disney": {
        "nome": "Disney+", "preco_avulso": None,
        "fonte": "https://www.disneyplus.com/pt-br",
        "conferido_em": "2026-10-08",
        "evidencia": "colunas Premium / Padrão / Padrão com anúncios "
                     "sobre R$ 69,90 / R$ 49,90 / R$ 29,90",
    },
    "spotify": {
        "nome": "Spotify", "preco_avulso": None,
        "fonte": "https://www.spotify.com/br-pt/premium/",
        "conferido_em": "2026-10-08",
        "evidencia": "Premium Individual. R$ 0 por 1 mês, depois R$ 23,90 por mês",
    },
    "youtube": {
        "nome": "YouTube Premium", "preco_avulso": None,
        "fonte": "https://www.youtube.com/premium",
        "conferido_em": "2026-10-08",
        "evidencia": "Premium Lite ... Monthly R$16.90/month",
    },
    "globoplay": {
        "nome": "Globoplay", "preco_avulso": None,
        "fonte": "https://globoplay.globo.com/assine/",
        "conferido_em": "2026-10-15",
        "evidencia": "mensal: Padrão com anúncios R$ 22,90, Premium "
                     "R$ 39,90. A Vivo nao diz qual inclui, entao nenhum "
                     "dos dois precos vale para a oferta dela",
    },
    "amazon": {
        "nome": "Amazon Prime", "preco_avulso": None,
        "fonte": "https://www.amazon.com.br/amazonprime",
        "conferido_em": "2026-10-08",
        "evidencia": "a pagina responde 503 a leitura automatica",
    },
    "premiere": {"nome": "Premiere", "preco_avulso": None,
                 "fonte": None, "conferido_em": None,
                 "evidencia": "ainda nao conferido"},
    "vale_saude": {"nome": "Vale Saúde Sempre", "preco_avulso": None,
                   "fonte": None, "conferido_em": None,
                   "evidencia": "telemedicina, nao streaming"},
    "vivae": {"nome": "Vivae", "preco_avulso": None,
              "fonte": None, "conferido_em": None,
              "evidencia": "educacao, nao streaming"},
    "vivo_tv": {"nome": "Vivo TV Inicial", "preco_avulso": None,
                "fonte": None, "conferido_em": None,
                "evidencia": "servico da propria Vivo; nao ha preco avulso"},
    "vivo_travel": {"nome": "Vivo Travel", "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "roaming, nao e app de assinatura"},
    "vivo_musica": {"nome": "Vivo Música", "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "servico da propria Vivo; nao ha preco avulso"},

    # --- apps de catalogo: aparecem no TEXTO da oferta, nao no nome.
    # Sao o conteudo tipico do nivel 1, e o leitor merece saber quais
    # sao em vez de ler "apps menores".
    "paramount": {"nome": "Paramount+", "preco_avulso": None,
                  "fonte": None, "conferido_em": None,
                  "evidencia": "ainda nao conferido"},
    "max": {"nome": "Max", "preco_avulso": None,
            "fonte": None, "conferido_em": None,
            "evidencia": "ainda nao conferido"},
    "sky": {"nome": "Sky", "preco_avulso": None,
            "fonte": None, "conferido_em": None,
            "evidencia": "TV por assinatura; a operadora vende o pacote, "
                         "nao ha avulso comparavel"},
    "telecine": {"nome": "Telecine", "preco_avulso": None,
                 "fonte": None, "conferido_em": None,
                 "evidencia": "ainda nao conferido"},
    "deezer": {"nome": "Deezer", "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "ainda nao conferido"},
    "skeelo": {"nome": "Skeelo", "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo, sem preco avulso relevante"},
    "mcafee": {"nome": "McAfee", "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo, sem preco avulso relevante"},
    "aya_books": {"nome": "Aya Books", "preco_avulso": None,
                  "fonte": None, "conferido_em": None,
                  "evidencia": "app de catalogo da TIM"},
    "aya_ensinah": {"nome": "Aya Ensinah", "preco_avulso": None,
                    "fonte": None, "conferido_em": None,
                    "evidencia": "app de catalogo da TIM"},
    "exa": {"nome": "EXA Segurança", "preco_avulso": None,
            "fonte": None, "conferido_em": None,
            "evidencia": "app de catalogo da TIM"},
    "goread": {"nome": "GoRead", "preco_avulso": None,
               "fonte": None, "conferido_em": None,
               "evidencia": "app de catalogo"},
    "claro_musica": {"nome": "Claro Música", "preco_avulso": None, "fonte": None, "conferido_em": None,
                     "evidencia": "servico da propria Claro"},
}

# O tier de cada app, e o preco avulso DAQUELE tier quando conferido.
#
# A ordem importa: "Padrão com anúncios" tem de ser testado antes de
# "Padrão", senao o mais curto casa primeiro e o tier sai errado.
#
# Preco None quer dizer tier que existe mas cujo preco eu nao conferi na
# fonte - entao a oferta mostra o tier e nao mostra preco. App que nao
# esta aqui tem um plano so, e usa o preco_avulso do dicionario acima.
TIERS = {
    "netflix": (
        ("Padrão com anúncios", None),
        ("Premium", None),
        ("Padrão", 44.90),
    ),
    "disney": (
        ("Padrão com anúncios", 29.90),
        ("Premium", 69.90),
        ("Padrão", 49.90),
    ),
    "globoplay": (
        ("Padrão com anúncios", 22.90),
        ("Premium", 39.90),
    ),
    "youtube": (
        ("Lite", 16.90),
        ("Premium", None),
    ),
    # A Vivo registra "SPOTIFY PREMIUM" na Anatel. O Premium tem quatro
    # assinaturas (Individual, Duo, Familia, Universitario) e um plano de
    # celular da uma conta, que e a Individual - o preco abaixo e dela, e
    # isso esta dito na evidencia para quem quiser conferir a leitura.
    "spotify": (
        ("Premium", 23.90),
    ),
}

# Janela a partir do nome do app: "DISNEY+ PADRAO" tem o tier colado, e
# "Controle YouTube Premium Lite" tem uma palavra no meio. Mais longe do
# que isso ja e outra frase, e tier de outra coisa.
JANELA_TIER = 34


def _sem_acento(t):
    for de, para in (("ã", "a"), ("á", "a"), ("â", "a"), ("é", "e"),
                     ("ê", "e"), ("í", "i"), ("ó", "o"), ("ô", "o"),
                     ("õ", "o"), ("ú", "u"), ("ç", "c")):
        t = t.replace(de, para)
    return t


def _marcas_alheias(app):
    """A primeira palavra do nome de cada OUTRO app conhecido.

    Serve de parede: "Netflix e Spotify Premium" nao pode dar tier
    Premium para o Netflix, porque o Premium esta do outro lado do nome
    do Spotify.
    """
    fora = []
    for chave, e in APPS.items():
        if chave == app:
            continue
        primeira = _sem_acento((e.get("nome") or chave).lower()).split()[0]
        if len(primeira) >= 4:
            fora.append(primeira)
    return fora


def tier_do_texto(app, *fontes):
    """O tier que a FONTE declara para este app, ou None.

    Nunca devolve um tier por padrao. Se a operadora nao escreveu qual
    plano do app a oferta inclui, a resposta e None - e sem tier nao ha
    preco de referencia, porque o preco pertence ao tier.
    """
    tiers = TIERS.get(app)
    if not tiers:
        return None
    nome = _sem_acento((APPS.get(app, {}).get("nome") or app).lower())
    marca = nome.split()[0]          # "YouTube Premium" -> "youtube"
    alheias = _marcas_alheias(app)
    for fonte in fontes:
        if not fonte:
            continue
        t = _sem_acento(str(fonte).lower())
        inicio = 0
        while True:
            i = t.find(marca, inicio)
            if i < 0:
                break
            # A janela comeca DEPOIS do nome do app, com nome completo
            # quando ele esta ali: "YouTube Premium" e nome, nao tier, e
            # so o que vem depois dele pode ser lido como tier.
            fim_do_nome = i + (len(nome) if t[i:i + len(nome)] == nome
                               else len(marca))
            janela = t[fim_do_nome:fim_do_nome + JANELA_TIER]
            # a janela acaba na frase seguinte ou no proximo app
            for parada in [janela.find("."), janela.find(";")] + \
                          [janela.find(m) for m in alheias]:
                if parada > 0:
                    janela = janela[:parada]
            for nome_tier, _preco in tiers:
                if _sem_acento(nome_tier.lower()) in janela:
                    return nome_tier
            inicio = i + len(marca)
    return None

def planos_dos_apps(lista, *fontes):
    """{app: tier} para os apps cujo tier a fonte declara."""
    saida = {}
    for a in lista or ():
        t = tier_do_texto(a, *fontes)
        if t:
            saida[a] = t
    return saida or None


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
    # "Prime video" e como a API da Brisanet chama o Amazon Prime
    (r"amazon\s*prime|prime\s*video", "amazon"),
    (r"\bpremiere\b", "premiere"),
    (r"vale\s*sa[úu]de", "vale_saude"),
    (r"\bvivae\b", "vivae"),
    (r"\bparamount\b", "paramount"),
    (r"\bmax\b|\bhbo\b", "max"),
    # "sky" com fronteira dos dois lados: sem isso casa dentro de
    # "Skeelo", que comeca igual e e outro app
    (r"\bsky\b", "sky"),
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


# Quais apps contam como STREAMING para o nivel de bundle. O resto do
# dicionario - telemedicina, educacao, seguranca, leitura - e app de
# catalogo, e nao faz uma oferta subir de degrau.
STREAMING = {"netflix", "disney", "globoplay", "amazon", "spotify",
             "premiere", "max", "paramount", "telecine", "deezer",
             "youtube", "vivo_tv"}
# A Sky fica de fora de proposito: e TV por assinatura, e quem decide
# nivel 4 e a regra de "tv por assinatura" de cada coletor, nao a
# presenca do nome dela numa lista de apps.


def nivel_por_apps(texto, extras_catalogo=(), piso=0):
    """A escada de bundle (decisao 10) lida pelos apps que o texto inclui.

    O nivel sai da MESMA leitura que a lista de apps da tela. Antes cada
    coletor varria o texto cru atras de nome de streaming, sem a regra de
    degustacao, e os dois campos da mesma oferta se contradiziam.

    extras_catalogo sao nomes que valem nivel 1 e nao estao no dicionario
    de apps - Google One, iCloud, Claro Banca. piso e o nivel 1 que o
    coletor ja sabe por outro caminho (a Brisanet tem a lista de produtos
    contratados).
    """
    achados = apps_do_texto(texto)
    streamings = [a for a in achados if a in STREAMING]
    if len(streamings) > 1:
        return 3
    if len(streamings) == 1:
        return 2
    if achados:
        return 1
    t = (sem_degustacao(texto) or "").lower()
    if any(e in t for e in extras_catalogo):
        return 1
    return piso


def sem_degustacao(texto):
    """O texto sem as frases de degustacao, para quem conta bundle.

    POR QUE PRECISA EXISTIR. Cada coletor tem seu nivel_bundle, e cada um
    varria o texto cru procurando nome de streaming. O card da Claro diz
    "Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes", e isso
    virava nivel 2 - "uma assinatura inclusa" - numa oferta que nao
    inclui assinatura nenhuma. A decisao 38 ja dizia que degustacao nao
    conta; so o modulo de apps a aplicava.

    Apaga a frase inteira em que a marca de degustacao aparece, do ponto
    anterior ao proximo. Se o app estiver nessa frase, ele some junto - e
    e esse o ponto.
    """
    if not texto:
        return texto
    t = str(texto)
    if not DEGUSTACAO.search(t):
        return t

    # onde cada app e nomeado: o corte comeca no app que a degustacao
    # esta oferecendo, e nao na frase inteira - senao leva o vizinho
    nomes = []
    for padrao, _app in DO_TEXTO + DO_NOME:
        for m in re.finditer(padrao, t, re.I):
            nomes.append(m.start())
    nomes.sort()

    cortes = []
    for m in DEGUSTACAO.finditer(t):
        # o ultimo nome de app antes da marca, se houver um perto
        ini = m.start()
        for pos in nomes:
            if pos < m.start() and m.start() - pos <= JANELA:
                ini = min(ini, pos)
                break
        # e a pontuacao anterior, quando ela esta mais perto que o app
        ponto = max(t.rfind(".", 0, m.start()), t.rfind(";", 0, m.start()))
        if ponto >= 0:
            ini = max(ini, ponto + 1)
        fim = len(t)
        for p in (".", ";"):
            j = t.find(p, m.end())
            if j >= 0:
                fim = min(fim, j + 1)
        cortes.append((ini, fim))
    # junta os trechos e remonta o que sobrou
    cortes.sort()
    saida, cursor = [], 0
    for ini, fim in cortes:
        if ini > cursor:
            saida.append(t[cursor:ini])
        cursor = max(cursor, fim)
    saida.append(t[cursor:])
    return " ".join(x.strip() for x in saida if x.strip())


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


def rotulo(apps, *fontes):
    """"Disney+ (Padrão)" ou "Netflix + Spotify". Vazio se nao houver.

    O tier entre parenteses so aparece quando alguma das fontes passadas
    o declara - nome da oferta, nome registrado na Anatel ou texto do
    card. Sem declaracao, sai o nome do app sozinho, que e o que a
    operadora de fato disse.
    """
    nomes = []
    for a in apps or ():
        e = APPS.get(a)
        if not e:
            continue
        tier = tier_do_texto(a, *fontes)
        # "YouTube Premium" + tier "Premium" nao vira "YouTube Premium
        # (Premium)": o nome do app ja terminou no tier
        if tier and not e["nome"].lower().endswith(tier.lower()):
            nomes.append("%s (%s)" % (e["nome"], tier))
        else:
            nomes.append(e["nome"])
    return " + ".join(nomes)
