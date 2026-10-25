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

    O "+" SAI DO FIM. "Disney+" e "Paramount+" entravam com o sinal, e
    parede com sinal nunca casa: a busca e por fronteira de palavra, e
    nao existe fronteira entre "+" e o espaco que vem depois. Resultado
    medido: "Netflix e Disney+ Padrao" devolvia Padrao para o NETFLIX.

    E O PISO CAIU DE 4 PARA 3 LETRAS, que deixava Max e Sky de fora -
    os dois apps de tres letras do dicionario, e os dois citados em
    oferta de TV. "Netflix e Max Premium" dava Premium ao Netflix.
    Tres letras com fronteira dos dois lados nao casa dentro de outra
    palavra, e e a fronteira que faz o trabalho, nao o tamanho.
    """
    fora = []
    for chave, e in APPS.items():
        if chave == app:
            continue
        primeira = _sem_acento((e.get("nome") or chave).lower()).split()[0]
        primeira = primeira.strip("+")
        if len(primeira) >= 3:
            fora.append(primeira)
    return sorted(set(fora))


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
            # A JANELA ACABA NA PRIMEIRA PARADA, inclusive quando ela
            # esta na posicao zero. O "> 0" de antes ignorava justamente
            # o caso em que a frase termina colada no nome do app:
            # "Vivo Pos com Netflix. Premium por R$ 55 a parte" devolvia
            # Premium, que e o tier da frase SEGUINTE e de uma oferta
            # que nao e esta. Tier nao declarado tem de voltar None.
            paradas = [janela.find("."), janela.find(";")]
            for m in alheias:
                achou = re.search(r"\b%s\b" % re.escape(m), janela)
                paradas.append(achou.start() if achou else -1)
            corte = min([p for p in paradas if p >= 0], default=None)
            if corte is not None:
                janela = janela[:corte]
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


# NOME PROPRIO DE APP, no nome da oferta. Vale em qualquer operadora,
# porque Netflix e Netflix em todas elas.
#
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
)

# OS SUFIXOS DA VIVO, E SO DELA. Nenhuma destas palavras e nome de app:
# sao os nomes com que a Vivo batiza a oferta - "Vivo Controle Saude" e
# telemedicina, "Vivo Controle Entretenimento" e a TV dela. Soltas,
# casam com o nome de qualquer operadora: "Brisanet Entretenimento
# 500MB" virava uma oferta com Vivo TV Inicial inclusa, que e servico da
# concorrente numa oferta que nao o tem.
#
# DO_TEXTO ja tomava este cuidado, e o comentario dele ja dizia por que.
# O cuidado existia num lado e faltava no outro.
DO_NOME_VIVO = (
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
    # "\bhbo" sem fronteira no fim, para pegar "hbomax" colado. O
    # "\bmax\b" mantem as duas: "max" solto casaria em "climax" e
    # "maxi", e nao precisa - o \bhbo ja cobre a forma colada.
    (r"\bmax\b|\bhbo", "max"),
    # "SKY" PEGA O SUFIXO COLADO. Isto era r"\bsky\b", e o comentario
    # justificava a fronteira final dizendo que sem ela "casa dentro de
    # Skeelo, que comeca igual e e outro app". E falso: "Skeelo" e
    # s-k-e e "sky" e s-k-y, e \bsky nao casa em "Skeelo" (conferido).
    # A fronteira era desnecessaria e custava "SkyPlus", que devolvia
    # lista vazia.
    (r"\bsky", "sky"),
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

# DE QUEM E A DEGUSTACAO, quando a propria frase diz. "12 meses gratis
# DE Gemini" declara o sujeito logo depois da marca; "3 meses por conta
# da Claro" nao declara produto nenhum, e ai vale a proximidade.
#
# Duas palavras no maximo: nome de app nao passa disso ("Amazon Prime",
# "YouTube Premium", "Vale Saude"), e tres ja atravessa a frase.
SUJEITO_DECLARADO = re.compile(
    r"^\W{0,3}(?:de|do|da|dos|das)\s+"
    r"([a-z\u00e0-\u00ff][\w+\u00e0-\u00ff]*(?:\s+[a-z\u00e0-\u00ff][\w+\u00e0-\u00ff]*)?)",
    re.I)

# QUAIS MARCAS TOMAM COMPLEMENTO DE PRODUTO. "Gratis de X", "cortesia de
# X" e "degustacao de X" nomeiam o produto. "Por conta de X" nomeia quem
# PAGA - "3 meses por conta da Claro" - e ler a Claro como sujeito fazia
# a regra concluir "a cortesia e de outro produto" e contar o Disney+
# como incluso em 8 ofertas reais da Claro, que e o caso que originou o
# corte de degustacao.
MARCA_COM_SUJEITO = re.compile(
    r"(?:gr[\u00e1a]tis|cortesia|degusta[\u00e7c][\u00e3a]o|experimente)\W{0,3}$",
    re.I)


def _degustacao_de_outro(texto, pos_ini, pos_fim, app):
    """A marca de degustacao declara um sujeito, e ele nao e este app?

    Devolve True so quando a frase diz de quem e a cortesia E esse
    alguem e outro produto. Marca sem sujeito declarado devolve False, e
    segue valendo pela proximidade, como antes.
    """
    if not MARCA_COM_SUJEITO.search(texto[pos_ini:pos_fim]):
        return False
    m = SUJEITO_DECLARADO.match(texto[pos_fim:pos_fim + 48])
    if not m:
        return False
    sujeito = _sem_acento(m.group(1).lower())
    nome = _sem_acento((APPS.get(app, {}).get("nome") or app).lower())
    marca = nome.split()[0].strip("+")
    # o sujeito e este app quando as marcas se encontram em qualquer um
    # dos sentidos: "gratis de Netflix" para netflix, "gratis de Amazon"
    # para "Amazon Prime", "gratis de HBO Max" para max
    if marca and marca in sujeito:
        return False
    if sujeito.split()[0] in nome:
        return False
    return True


# Quais apps contam como STREAMING para o nivel de bundle. O resto do
# dicionario - telemedicina, educacao, seguranca, leitura - e app de
# catalogo, e nao faz uma oferta subir de degrau.
STREAMING = {"netflix", "disney", "globoplay", "amazon", "spotify",
             "premiere", "max", "paramount", "telecine", "deezer",
             "youtube", "vivo_tv",
             # A MUSICA DA PROPRIA OPERADORA E STREAMING, como a TV
             # dela. Estes dois ficavam de fora enquanto deezer e
             # spotify entravam e vivo_tv - a TV da propria Vivo -
             # tambem: a assimetria dentro da mesma familia era o
             # indicio. O que a entrada de APPS diz ("servico da
             # propria Claro; nao ha preco avulso") e sobre PRECO, nao
             # sobre categoria. Mede 20 ofertas em 23/10/2026: a Vivo
             # Controle Musica sai de nivel 1 para 2.
             "claro_musica", "vivo_musica"}
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
    nivel = nivel_dos_apps(apps_do_texto(texto))
    if nivel:
        return nivel
    t = (sem_degustacao(texto) or "").lower()
    if any(e in t for e in extras_catalogo):
        return 1
    return piso


def nivel_dos_apps(lista, piso=0):
    """O nivel que uma lista de apps JA IDENTIFICADA implica.

    Contraparte de nivel_por_apps, que parte do texto. Existe porque a
    oferta as vezes nomeia o app no NOME e nao no texto do card - "Vivo
    Pos com Amazon", cujo card e so marcacao - e ai o nivel tem de sair
    da lista final, senao os dois campos da mesma oferta se
    contradizem. Medido ao vivo em 20/10/2026: apps_rotulo "Amazon
    Prime" ao lado de nivel 0, que na tela e "so internet e ligacoes".

    E a mesma escada da decisao 10, com os mesmos cortes: a conta de
    streamings e de apps nao pode morar em dois lugares.
    """
    # APP QUE O ROTULO NAO SABE NOMEAR NAO CONTA. nivel_dos_apps
    # (["inexistente"]) devolvia 1 e rotulo(["inexistente"]) devolvia
    # "": nivel "com apps de catalogo" ao lado de rotulo vazio, os dois
    # campos da mesma oferta se contradizendo. E a mesma regra dos
    # codigos SVA, que o projeto ja aplica - "codigo sem dicionario e
    # ruido com cara de informacao".
    conhecidos = [a for a in (lista or ()) if a in APPS]
    streamings = [a for a in conhecidos if a in STREAMING]
    if len(streamings) > 1:
        return 3
    if len(streamings) == 1:
        return 2
    if conhecidos:
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
    for padrao, _app in DO_TEXTO + DO_NOME + DO_NOME_VIVO:
        for m in re.finditer(padrao, t, re.I):
            nomes.append(m.start())
    nomes.sort()

    cortes = []
    for m in DEGUSTACAO.finditer(t):
        # O ULTIMO nome de app antes da marca, se houver um perto - e a
        # lista esta em ordem crescente, entao o ultimo e o primeiro de
        # tras para frente. Varrendo para a frente, o corte comecava no
        # app MAIS DISTANTE e levava o vizinho embora: em "Netflix
        # incluso. Disney+: 3 meses por conta da Claro" quem estava em
        # degustacao era o Disney, e o Netflix desaparecia junto.
        ini = m.start()
        for pos in reversed(nomes):
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


# Quantos apps um texto de oferta pode nomear antes de a leitura virar
# suspeita. Pagina de operadora lista o portfolio inteiro em rodape e
# menu, e um texto que "contem" oito streamings quase nunca e uma oferta
# com oito.
LIMITE_DE_APPS = 6


def aviso_de_leitura(texto, limite=None):
    """Por que a leitura de apps deste texto nao e de confiar, ou None.

    E A PORTA DO CANAL DE LEITURA DUVIDOSA, do lado do coletor. O
    descarte por limite devolve [], e [] quer dizer "nenhum app
    nomeado" - nivel 0, que na tela e "sem assinatura inclusa". Sem esta
    frase, uma leitura larga virava afirmacao de ausencia, calada.

    O coletor grava o retorno em avisos_oferta, e dali a mensagem e o
    relatorio o leem. O descarte em si nao muda: eleger seis dos oito
    seria o sorteio que o projeto recusa em todo lugar.
    """
    quantos = len(_citados(texto))
    limite = LIMITE_DE_APPS if limite is None else limite
    if quantos > limite:
        return ("o texto da oferta nomeia %d aplicativos, acima do limite "
                "de %d: a leitura pegou a vitrine junto com o card, e a "
                "lista de apps ficou vazia em vez de adivinhada"
                % (quantos, limite))
    return None


def juntar_avisos(existentes, novo):
    """Soma um aviso aos que a oferta ja tinha, sem apagar nenhum.

    A Claro e a Vivo gravam avisos_oferta por outros motivos - regulamento
    de outra oferta, card sem composicao reconhecida - e sobrescrever
    trocaria uma ressalva por outra. Devolve None quando nao ha nenhuma,
    porque ausencia e ausencia e nao lista vazia: "[]" compararia igual a
    "[]" entre dias e esconderia a chegada da primeira ressalva.
    """
    if isinstance(existentes, str):
        existentes = [existentes]
    saida = [a for a in (existentes or ()) if a]
    if novo and novo not in saida:
        saida.append(novo)
    return saida or None


def _citados(texto):
    """Os apps que o texto nomeia, antes do corte de degustacao e limite.

    Serve a aviso_de_leitura, que precisa do TAMANHO da leitura crua -
    e nao do resultado dela, que por definicao e vazio quando o limite
    dispara.
    """
    t = (texto or "").lower()
    return sorted({app for padrao, app in DO_TEXTO if re.search(padrao, t)})


def apps_do_texto(texto, limite=None):
    """Os apps nomeados num texto de oferta, fora os em degustacao.

    O limite existe porque pagina de operadora lista o portfolio inteiro
    em rodape e menu: um texto que "contem" oito streamings quase nunca
    e uma oferta com oito streamings, e sim um trecho que pegou a
    vitrine junto. Acima do limite, a leitura e descartada.

    O DESCARTE NAO E SILENCIOSO desde 25/10/2026: aviso_de_leitura()
    devolve o motivo, o coletor o grava em avisos_oferta, e a mensagem e
    o relatorio o leem. A lista continua vazia - eleger seis dos oito
    seria sorteio -, mas o buraco passa a ser anunciado.
    """
    limite = LIMITE_DE_APPS if limite is None else limite
    t = (texto or "").lower()

    # A PRIMEIRA MENCAO DO APP E A QUE VALE, e isto nao e descuido.
    #
    # Troquei por re.finditer para que a segunda mencao pudesse salvar o
    # app, pensando em "Disney+ em degustacao por 3 meses. No plano
    # anual, Disney+ incluso para sempre". O texto REAL da Claro Pos
    # reprovou a ideia:
    #
    #   ... Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes.
    #   DisneyPlus WhatsApp ilimitado
    #
    # A primeira mencao e a degustacao declarada; a segunda,
    # "DisneyPlus", e resto de marcacao - nome de marca solto, sem
    # nenhuma afirmacao de inclusao em volta. Com finditer a janela dela
    # sai limpa e o Disney entra numa oferta que so tem trial, que e o
    # defeito que o corte de degustacao existe para impedir.
    #
    # Meu caso a favor era inventado e o contraexemplo e medido. Entre
    # deixar um app de fora e anunciar como incluso um app que e trial,
    # a metodologia escolhe o primeiro.
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
        # A MARCA QUE DIZ DE QUEM E NAO DESQUALIFICA O VIZINHO. Sem
        # isto, o Telecine caia das tres ofertas "Vivo Total V" de
        # 21/10/2026: a janela dele varria "12 meses gratis de Gemini",
        # que e cortesia de outro produto, e a oferta com dois
        # streamings aparecia com um.
        # os dois lados sao medidos SEPARADAMENTE: concatenados, eles
        # nao formam um pedaco contiguo do texto - o nome do app fica
        # fora - e a posicao da marca no meio sairia deslocada
        # A JANELA DE TRAS PARA NO FIM DA FRASE ANTERIOR, como a da
        # frente ja fazia. Sem isso os 24 caracteres pulavam o ponto e
        # "Promocao de degustacao encerrada. Netflix incluso no plano"
        # devolvia lista vazia: uma degustacao que ACABOU derrubava o
        # app da frase seguinte, e o resultado dependia da distancia.
        atras = max(0, ini - 24)
        for p in (".", ";"):
            k = t.rfind(p, atras, ini)
            if k >= 0:
                atras = max(atras, k + 1)
        marcas = [(atras + m.start(), atras + m.end())
                  for m in DEGUSTACAO.finditer(t[atras:ini])]
        marcas += [(fim + m.start(), fim + m.end())
                   for m in DEGUSTACAO.finditer(trecho)]
        if any(not _degustacao_de_outro(t, a, b, app) for a, b in marcas):
            continue
        achados.append(app)
    return [] if len(achados) > limite else achados


def apps_da_oferta(nome, operadora=None):
    """As chaves dos apps que o NOME da oferta anuncia.

    Os sufixos da Vivo entram so quando a operadora e ela - ver
    DO_NOME_VIVO. O padrao e NAO incluir: quem chamar sem dizer de quem
    e a oferta recebe apenas nome proprio de app, que e o que vale em
    qualquer vitrine. Assim um coletor novo nao herda o defeito calado.
    """
    t = (nome or "").lower()
    regras = DO_NOME
    if operadora and "vivo" in str(operadora).lower():
        regras = DO_NOME + DO_NOME_VIVO
    achados = []
    for padrao, app in regras:
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
