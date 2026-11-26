"""Coletor da Unifique.

CADA CIDADE TEM ROTA PROPRIA, e o seletor do site so NAVEGA para ela.
Medido em 27/10/2026, abrindo o seletor no navegador e olhando para onde
ele foi: clicar em "Blumenau - SC" leva a

    /para-voce/internet-fibra/sc/blumenau

que responde 200 com os precos no HTML servido, sem sessao, sem cookie e
sem JavaScript. Cidade inexistente responde 404 - conferido com dois
nomes inventados -, entao a propria rota distingue "nao atende" de
"quebrou".

A INVESTIGACAO DE 30/09/2026 TINHA PROCURADO A FORMA ERRADA. Ela testou
"?cidade=blumenau", "/cidade/x" e "/set-cidade/x", todas 404 ou
ignoradas, e concluiu que so restava simular o clique. A rota existia o
tempo todo, pendurada no caminho do PRODUTO e nao num caminho de cidade.

O NAVEGADOR SAIU EM 03/11/2026, e a medicao foi esta: o HTML cru das
quatro pracas que a Unifique atende, passado pela MESMA funcao
extrair(), devolve exatamente as ofertas que o caminho com Chromium
publicou no mesmo dia - velocidade e preco iguais nas quatro, zero
diferenca. A versao anterior deste comentario dizia que trocar o texto
renderizado por HTML cru "mudaria o que se le"; nao muda.

Antes dele tinha saido a coreografia - abrir o seletor, achar o campo de
busca, digitar e clicar no resultado certo -, que era o trecho mais
fragil do projeto. Agora sai o navegador inteiro: a coleta da Unifique
deixa de ser a mais lenta das nove e deixa de depender de layout
renderizado.

O PLAYWRIGHT CONTINUA NO WORKFLOW, porque claro_flex e nucel ainda
precisam dele. O que esta coleta ganha e nao abrir browser nenhum.

E ERA TAMBEM O QUE ESCONDIA FLORIANOPOLIS. O casamento do botao era
sensivel a acento - "Florianopolis" nunca casa com "Florianopolis - SC"
escrito com o "o" acentuado -, entao o coletor respondia "a Unifique nao
atende Florianopolis/SC" e isso virou comentario em pracas.py como se
fosse fato da fonte. Era defeito nosso. A rota /sc/florianopolis
responde 200 com tres ofertas.

FRAGILIDADE QUE RESTA: a leitura depende do layout, nao de um formato de
dado. Quando a Unifique mexer na tela, isto quebra - e por isso avisa em
vez de devolver vazio em silencio.

Uso:  python coletores/unifique.py [--praca "Blumenau/SC"]
"""

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from . import apps
from datetime import datetime, timedelta, timezone

PAGINA = "https://unifique.com.br/para-voce/internet-fibra"
# O CELULAR E O COMBO, desde 26/11/2026. O coletor lia so a fibra; quem le
# viu no site os combos e os planos de celular que o tracker nao tinha. As
# duas paginas tem a mesma forma de rota por cidade da fibra.
PAGINA_COMBO = "https://unifique.com.br/para-voce/combos-fibra-movel"
PAGINA_MOVEL = "https://unifique.com.br/para-voce/movel-planos-de-celular"
# O QUE A AUDITORIA DE 26/11/2026 ACHOU FORA DA COLETA, os dois no menu:
#   - o combo celular + fibra + TV, com rota por cidade como os outros;
#   - a fibra "sem SVA" (sem apps), que a pagina de fibra linka ("Caso opte
#     por ofertas sem apps inclusos e/ou fidelidade, veja ofertas"). Ela NAO
#     tem rota por cidade (404): a cidade vai no cookie ckUnifique[location],
#     que o seletor publico grava - a rota em base64 mais um sufixo fixo,
#     medido em 26/11 nas quatro pracas. Se o cookie mudar de formato a
#     pagina deixa de confirmar a cidade, e a leitura falha alto em vez de
#     gravar a fibra de outro lugar.
PAGINA_COMBO_TV = "https://unifique.com.br/para-voce/combos-fibra-movel-tv"
PAGINA_SEM_SVA = "https://unifique.com.br/para-voce/internet-fibra-sem-sva"
SUFIXO_DO_COOKIE = "ck1Un2FQ24"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer"}


def _num(txt):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", str(txt or ""))
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0")) if m else None


def _mbps(txt):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mega|mbps|giga|gbps)", str(txt or "").lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).startswith("g") else int(v)


def nivel_bundle(texto):
    t = (texto or "").lower()
    if "tv por assinatura" in t or "canais" in t:
        return 4
    return apps.nivel_por_apps(texto)


def extrair(texto):
    """Le as ofertas do texto da pagina.

    A estrutura HTML nao ajuda - os cards nao tem classe propria - entao a
    leitura e pelo texto que o cliente ve: "FIBRA IDEAL 500 Mega ... R$ 119,90".
    """
    ofertas = []
    # O preco mensal e o que vem seguido de "/mes". Sem essa ancora captura-se
    # o primeiro "R$" do card - e no FIBRA ESSENCIAL esse primeiro valor e a
    # taxa de instalacao (R$ 349,90), nao a mensalidade de R$ 89,90.
    padrao = re.compile(
        r"([A-ZÀ-Ú][A-ZÀ-Ú0-9\s\+\-\.]{3,40}?)\s*(\d{3,4})\s*Mega"
        r"(.{0,600}?)R\$\s*\n?\s*(\d{2,4},\d{2})\s*\n?\s*.{0,4}/m",
        re.S)
    for m in padrao.finditer(texto):
        nome, mega, meio, preco = m.groups()
        nome = re.sub(r"\s+", " ", nome).strip(" -+.")
        if not nome or len(nome) < 3:
            nome = "Unifique %s Mega" % mega
        taxa = re.search(r"instala[çc][ãa]o\s*R\$\s*(\d{1,4},\d{2})", meio, re.I)
        # O RISCADO, quando o card tem ("R$ 138,00 R$ 129,90 /mes" no FIBRA
        # COMPLETA): o ultimo valor do meio, colado no preco. A taxa de
        # instalacao vem com "a vista" depois, e nao casa aqui.
        riscado = re.search(r"R\$\s*(\d{2,4},\d{2})\s*$", re.sub(r"\s+", " ", meio).strip())
        gratis = re.search(r"instala[çc][ãa]o\s*gr[áa]tis", meio, re.I)
        ofertas.append({
            "nome_oferta": nome[:60],
            "destaque": "%s Mega" % mega,
            "degrau_mbps": _mbps(mega + " Mega"),
            "preco_promocional": _num(preco),
            # a Unifique escreve a taxa no proprio card; as outras so trazem
            # isso no regulamento, quando trazem
            "taxa_instalacao": _num(taxa.group(1)) if taxa else (0.0 if gratis else None),
            "preco_cheio": (_num(riscado.group(1)) if riscado
                            and _num(riscado.group(1)) > (_num(preco) or 0) else None),
            "contexto": re.sub(r"\s+", " ", meio)[:260],
        })
    # tira repetido (a pagina repete o card em versao desktop e mobile)
    vistos, unicas = set(), []
    for o in ofertas:
        k = (o["degrau_mbps"], o["preco_promocional"])
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(o)
    return unicas


# A FAIXA DA CAMPANHA, que fica entre o nome do plano e a velocidade.
#
#   <span ...>FIBRA IDEAL</span>
#   <span class="campaign-plan-badge ...">BLACK UNIFIQUE - 1o PAGAMENTO EM 2027</span>
#   <h3 ...>500 Mega</h3>
#
# extrair() le como nome o trecho em maiusculas colado na velocidade, e
# de 19 a 23/11/2026 esse trecho era a faixa: o "o" sobrescrito de "1o"
# cortava a leitura, e sobrava "PAGAMENTO EM 2027" como nome de quatro
# planos e "MAS VOCE CONTINUA ONLINE" ("FALTOU LUZ, ...") como nome dos
# tres FIBRA + POWER - que entraram em 20/11 e sairam na mensagem como
# UMA oferta, porque tinham o mesmo nome. A faixa sem sobrescrito ia
# inteira para o nome: e quase certamente de onde veio o "WI-FI EXTRA"
# de "FIBRA COMPLETA WI-FI EXTRA", gravado por 50 dias - a pagina chama
# o plano de "FIBRA COMPLETA".
#
# PELA CLASSE, e nao pelo texto: a faixa e tao maiuscula quanto o nome,
# e o texto dela muda a cada campanha.
FAIXA = re.compile(r"<(span|div|p)\b[^>]*campaign-plan-badge[^>]*>.*?</\1>",
                   re.S | re.I)


def sem_faixa(html):
    return FAIXA.sub(" ", html)


def buscar(url, cookie=None):
    """A rota da cidade, em texto. Devolve (status, texto).

    O status importa: 404 e a Unifique NAO ATENDER a cidade, que e
    informacao, e nao falha. Era o navegador que lia isso antes.
    """
    cab = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    if cookie:
        cab["Cookie"] = cookie
    req = urllib.request.Request(url, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)
    # O TEXTO NO LUGAR DO RENDERIZADO. extrair() le texto corrido, e era
    # o inner_text do body que o alimentava; aqui o mesmo texto sai do
    # HTML servido. As tags viram espaco - sem isto "500" e "Mega"
    # colariam em "500Mega" ou grudariam no numero do card vizinho.
    t = re.sub(r"<script.*?</script>", " ", bruto, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = sem_faixa(t)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    return status, re.sub(r"[ \t]+", " ", t)


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def _vitrine(texto):
    u"""So o bloco de cards da cidade, de "Ofertas Exclusivas" ao fim dele.

    A pagina repete o nome e os GB de cada plano nos "Mais Detalhes",
    sem preco; lendo a pagina inteira, o nome de um detalhe colaria no
    preco do card seguinte."""
    i = texto.find("Ofertas Exclusivas")
    if i < 0:
        return ""
    fim = re.search(r"Caso opte por ofertas|Cobertura nacional\s+Consulte|Por que escolher",
                    texto[i:])
    return texto[i:i + fim.start()] if fim else texto[i:]


# "LEVE 10 GB ... Fidelidade 12 meses R$ 39,90 /mes"
CARD_MOVEL = re.compile(
    r"([A-Z\u00c0-\u00da][A-Z\u00c0-\u00da ]{2,20}?)\s+(\d{1,3})\s*GB\s+(.{0,400}?)"
    r"R\$\s*(\d{2,4},\d{2})\s*/\s*m[e\u00ea]s", re.S)


def extrair_movel(texto):
    u"""Os planos de celular: nome, GB, fidelidade e preco do card."""
    saida = []
    for m in CARD_MOVEL.finditer(_vitrine(texto)):
        nome, gb, meio, preco = m.groups()
        nome = re.sub(r"\s+", " ", nome).strip()
        fid = re.search(r"Fidelidade\s+(\d{1,2})\s*meses", meio, re.I)
        saida.append({
            "nome_oferta": "%s %s GB" % (nome, gb),
            "destaque": "%s GB" % gb,
            "degrau_mbps": None,
            "franquia_anunciada_gb": int(gb),
            "preco_promocional": _num(preco),
            "preco_cheio": None,
            "fidelidade_meses": int(fid.group(1)) if fid else None,
            "contexto": re.sub(r"\s+", " ", meio)[:300],
        })
    return saida


# "Celular 30 GB ... Fibra Optica 550 Mega Instalacao Gratis R$ 149,90
#  R$ 119,90 /mes ... R$ 119,90 nos primeiros 12 meses. Apos 12 meses
#  R$ 149,90. Mais Detalhes"
CARD_COMBO = re.compile(
    r"Celular\s+(\d{1,3})\s*GB(.{0,250}?)Fibra\s+\S+\s+(\d{3,4})\s*Mega(.{0,160}?)"
    r"((?:R\$\s*\d{2,4},\d{2}\s*)+)/\s*m[e\u00ea]s(.{0,220}?)Mais Detalhes", re.S)


def extrair_combo(texto):
    u"""Os combos fibra + celular: velocidade, GB, preco e o depois."""
    saida = []
    for m in CARD_COMBO.finditer(_vitrine(texto)):
        gb, movel, mega, fibra, precos, nota = m.groups()
        valores = [_num(x) for x in re.findall(r"\d{2,4},\d{2}", precos)]
        meses = re.search(r"nos\s+(?:(\d{1,2})\s+primeiros|primeiros\s+(\d{1,2}))\s+meses", nota, re.I)
        depois = re.search(r"Ap[o\u00f3]s\s+\d{1,2}\s+meses\s+R\$\s*(\d{2,4},\d{2})", nota, re.I)
        contexto = re.sub(r"\s+", " ", " ".join((movel, fibra, nota))).strip()
        saida.append({
            "nome_oferta": "Combo Fibra %s Mega + Celular %s GB" % (mega, gb),
            "destaque": "%s Mega + %s GB" % (mega, gb),
            "degrau_mbps": _mbps(mega + " Mega"),
            "franquia_anunciada_gb": int(gb),
            # o card riscado ("R$ 149,90 R$ 119,90") traz os dois
            "preco_cheio": valores[0] if len(valores) > 1 else None,
            "preco_promocional": valores[-1],
            "meses_desconto": int(next(g for g in meses.groups() if g)) if meses else None,
            "preco_pos_promocao": _num(depois.group(1)) if depois else None,
            "taxa_instalacao": 0.0 if re.search(r"instala\S*o\s+gr\S*tis", fibra, re.I) else None,
            "fidelidade_meses": None,
            "contexto": contexto[:300],
        })
    return saida


# A FIDELIDADE ESTA NOS "MAIS DETALHES" de cada plano, depois da vitrine:
# "FIBRA IDEAL 500 Mega ... Assine no Site Fidelidade 12 meses". O card nao
# a repete, e ela saia vazia nas 24 linhas de fibra.
DETALHE_COM_FIDELIDADE = re.compile(
    r"([A-ZÀ-Ú][A-ZÀ-Ú0-9\s\+\-\.]{3,40}?)\s*(\d{3,4})\s*Mega"
    r"((?:(?!\bMega\b).){0,500}?)Fidelidade\s+(\d{1,2})\s+meses", re.S)


def fidelidades(texto):
    u"""{(nome, Mbps): meses} dos blocos de detalhe da pagina."""
    saida = {}
    for m in DETALHE_COM_FIDELIDADE.finditer(re.sub(r"\s+", " ", texto or "")):
        nome = re.sub(r"\s+", " ", m.group(1)).strip(" -+.")
        saida.setdefault((nome, int(m.group(2))), int(m.group(4)))
    return saida


# "CELULAR + FIBRA + TV 50 GB ... 650 Mega Instalacao gratis ... TV Completa
#  Ver canais R$ 229,91 /mes ... R$ 229,91 por 12 meses. Apos R$ 259,91."
CARD_COMBO_TV = re.compile(
    r"CELULAR\s*\+\s*FIBRA\s*\+\s*TV\s+(\d{1,3})\s*GB(.{0,160}?)(\d{3,4})\s*Mega(.{0,260}?)"
    r"((?:R\$\s*\d{2,4},\d{2}\s*)+)/\s*m[eê]s(.{0,220}?)Mais Detalhes", re.S | re.I)


def extrair_combo_tv(texto):
    u"""Os combos celular + fibra + TV: velocidade, GB, o pacote de TV e o preco."""
    saida = []
    for m in CARD_COMBO_TV.finditer(_vitrine(texto)):
        gb, movel, mega, meio, precos, nota = m.groups()
        valores = [_num(x) for x in re.findall(r"\d{2,4},\d{2}", precos)]
        pacote = re.search(r"\bTV\s+([A-ZÀ-Ú][\wÀ-ú]+)", meio)
        meses = re.search(r"por\s+(\d{1,2})\s+meses", nota, re.I)
        depois = re.search(r"Ap[oó]s\s+R\$\s*(\d{2,4},\d{2})", nota, re.I)
        tv = ("TV %s" % pacote.group(1)) if pacote else "TV"
        contexto = re.sub(r"\s+", " ", " ".join((movel, meio, nota))).strip()
        saida.append({
            "nome_oferta": "Combo Fibra %s Mega + Celular %s GB + %s" % (mega, gb, tv),
            "destaque": "%s Mega + %s GB + %s" % (mega, gb, tv),
            "degrau_mbps": _mbps(mega + " Mega"),
            "franquia_anunciada_gb": int(gb),
            "preco_cheio": valores[0] if len(valores) > 1 else None,
            "preco_promocional": valores[-1],
            "meses_desconto": int(meses.group(1)) if meses else None,
            "preco_pos_promocao": _num(depois.group(1)) if depois else None,
            "taxa_instalacao": 0.0 if re.search(r"instala\S*o\s+gr\S*tis", meio, re.I) else None,
            "fidelidade_meses": None,
            "contexto": contexto[:300],
        })
    return saida


def cookie_da_cidade(cidade, uf):
    u"""O cookie que o seletor da Unifique grava: a rota em base64 + sufixo."""
    import base64
    rota = rota_da_cidade(cidade, uf).rstrip("/").split("/internet-fibra/")[1]
    return "ckUnifique[location]=%s%s" % (
        urllib.parse.quote(base64.b64encode(rota.encode("ascii")).decode("ascii")),
        SUFIXO_DO_COOKIE)


def rota_da_cidade(cidade, uf, pagina=None):
    """A URL propria da cidade, que e para onde o seletor navega.

    O endereco e sem acento e com hifen: "Sao Jose dos Campos" vira
    "sao-jose-dos-campos". Foi so por causa do acento que Florianopolis
    passou um mes fora da coleta.
    """
    pedaco = re.sub(r"[^a-z0-9]+", "-", sem_acento(cidade).lower()).strip("-")
    return "%s/%s/%s" % (pagina or PAGINA, uf.lower(), pedaco)


def coletar(cidade, uf, verbose=True, pagina=None):
    """As ofertas de fibra da cidade, lidas do HTML servido.

    O parametro "pagina" sobreviveu a saida do navegador e e IGNORADO:
    ele existia para reaproveitar uma aba do playwright entre pracas.
    Fica na assinatura porque main() e quem chama de fora passam por
    nome, e tirar agora quebraria a chamada sem ganho nenhum.
    """
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Unifique", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR UNIFIQUE  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    try:
        # A ROTA DA CIDADE responde 404 quando a Unifique nao atende, e
        # isso e melhor sinal do que "nao achei o botao": separa
        # ausencia real de layout quebrado, sem depender de nada na tela.
        status, texto = buscar(rota_da_cidade(cidade, uf))
        if status == 404:
            err = "a Unifique nao atende %s/%s" % (cidade, uf)
            saida["avisos"].append(err)
            if verbose:
                print("  %s" % err)
            return saida
        if status != 200:
            err = "HTTP %s ao ler %s/%s" % (status, cidade, uf)
            saida["avisos"].append(err)
            if verbose:
                print("  %s" % err)
            _celular_e_combo(cidade, uf, praca, agora, saida, verbose)
            return saida
        # SEM ACENTO DOS DOIS LADOS. A cesta guarda "Florianopolis" e a
        # pagina escreve "Florianopolis" com acento: comparar cru faz a
        # confirmacao falhar justamente nas cidades acentuadas.
        if sem_acento(cidade).lower() not in sem_acento(texto).lower():
            saida["avisos"].append("a pagina nao confirmou a cidade %s" % cidade)

        fid = fidelidades(texto)
        for o in extrair(texto):
            o.update({
                "operadora": "Unifique", "produto": "fibra", "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_anunciada_gb": None, "franquia_contratual_gb": None,
                # o riscado do card, quando tem (o FIBRA COMPLETA 600 Mega)
                "preco_cheio": o.get("preco_cheio"),
                "nivel_bundle": nivel_bundle(o.pop("contexto", "")),
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
                "fidelidade_meses": fid.get((o["nome_oferta"], o["degrau_mbps"])),
                "multa_fidelidade": None,
            })
            saida["ofertas"].append(o)

        if not saida["ofertas"]:
            # Ausencia e falha parecem iguais no resultado e sao coisas
            # opostas. Se a pagina confirmou a cidade e mesmo assim nao ha
            # oferta, a Unifique simplesmente nao vende fibra ali - foi o
            # caso de Curitiba, medido em 01/10/2026. Se nem a cidade
            # confirmou, ai sim algo quebrou.
            if sem_acento(cidade).lower() in sem_acento(texto).lower():
                saida["avisos"].append(
                    "sem oferta de fibra em %s - a Unifique atende a cidade "
                    "mas nao vende fibra residencial ali" % cidade)
                saida["sem_oferta"] = True
            else:
                saida["avisos"].append(
                    "nenhuma oferta lida e a cidade nao confirmou - "
                    "o layout da Unifique provavelmente mudou")
        if verbose:
            print("  fibra  %d ofertas" % len(saida["ofertas"]))
        # A FIBRA SEM APPS FALHA SOZINHA: dentro do try do coletor, um
        # erro dela levava o celular e o combo da praca junto
        try:
            _fibra_sem_apps(cidade, uf, praca, agora, saida, verbose)
        except Exception as e:                          # noqa: BLE001
            saida["avisos"].append("fibra sem apps: %s" % str(e)[:140])
        _celular_e_combo(cidade, uf, praca, agora, saida, verbose)
    except Exception as e:
        saida["avisos"].append("leitura: %s" % str(e)[:140])
        if verbose:
            print("  ERRO: %s" % str(e)[:140])
    return saida


def _fibra_sem_apps(cidade, uf, praca, agora, saida, verbose):
    u"""A fibra sem SVA da cidade, pela pagina que a cidade vai no cookie.

    Os nomes sao os da vitrine comum ("FIBRA IDEAL 500 Mega"), a outro preco:
    entram com "sem apps" no nome. Pagina que nao confirma a cidade e o cookie
    que mudou de formato - aviso, e nada entra."""
    status, texto = buscar(PAGINA_SEM_SVA, cookie=cookie_da_cidade(cidade, uf))
    if status == 404:
        # como nas outras paginas: 404 e a Unifique nao vender, nao falha
        saida["avisos"].append("a Unifique nao vende fibra sem apps em %s/%s" % (cidade, uf))
        return
    if status != 200:
        saida["avisos"].append("fibra sem apps: HTTP %s ao ler %s/%s" % (status, cidade, uf))
        return
    vit = _vitrine(texto)
    if sem_acento(cidade).lower() not in sem_acento(vit).lower():
        saida["avisos"].append("fibra sem apps: a pagina nao confirmou a cidade %s - "
                               "o cookie da praca deve ter mudado de formato" % cidade)
        return
    achadas = extrair(vit)
    for o in achadas:
        o.update({
            "operadora": "Unifique", "produto": "fibra", "praca": praca,
            "capturado_em": agora.isoformat(),
            "nome_oferta": ("%s sem apps" % o["nome_oferta"])[:60],
            "variante": "sem_apps",
            "franquia_anunciada_gb": None, "franquia_contratual_gb": None,
            "preco_cheio": o.get("preco_cheio"),
            "nivel_bundle": 0, "apps": None,
            "composicao": o.pop("contexto", ""),
            "codigo_anatel": None, "campanha": None, "id_catalogo": None,
            "fidelidade_meses": None, "multa_fidelidade": None,
        })
        saida["ofertas"].append(o)
    if verbose:
        print("  fibra sem apps  %d ofertas" % len(achadas))


def _celular_e_combo(cidade, uf, praca, agora, saida, verbose):
    u"""O combo e o celular da cidade, cada um na sua rota.

    404 e a Unifique nao vender o produto ali (informacao, nao falha);
    outro erro sai dito; pagina da cidade sem card e ausencia, e pagina
    que nem confirma a cidade e layout quebrado - a mesma regra da fibra.
    """
    for produto, pagina, ler in (("combo", PAGINA_COMBO, extrair_combo),
                                 ("combo", PAGINA_COMBO_TV, extrair_combo_tv),
                                 ("movel", PAGINA_MOVEL, extrair_movel)):
        status, texto = buscar(rota_da_cidade(cidade, uf, pagina))
        if status == 404:
            saida["avisos"].append("a Unifique nao vende %s em %s/%s" % (produto, cidade, uf))
            continue
        if status != 200:
            saida["avisos"].append("%s: HTTP %s ao ler %s/%s" % (produto, status, cidade, uf))
            continue
        achadas = ler(texto)
        if not achadas:
            if sem_acento(cidade).lower() in sem_acento(texto).lower():
                saida["avisos"].append("sem oferta de %s em %s" % (produto, cidade))
            else:
                saida["avisos"].append("%s: nenhuma oferta lida e a cidade nao confirmou - "
                                       "o layout da Unifique provavelmente mudou" % produto)
            continue
        for o in achadas:
            contexto = o.pop("contexto", "")
            o.update({
                "operadora": "Unifique", "produto": produto, "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_contratual_gb": None,
                "nivel_bundle": nivel_bundle(contexto),
                # "WhatsApp* e Waze ilimitados": o asterisco aponta para
                # "*WhatsApp ilimitado para mensagens, fotos e videos", no
                # pe da pagina - a regua comum nao casa com o "e Waze"
                "whatsapp": (apps.whatsapp_incluso(contexto) or bool(re.search(
                    r"whats\s?app\*?\s+e\s+waze\s+ilimitad", contexto, re.I))),
                # o que o card diz alem do preco: os apps, a portabilidade
                "composicao": contexto,
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
                "multa_fidelidade": None,
            })
            o.setdefault("taxa_instalacao", None)
            saida["ofertas"].append(o)
        if verbose:
            print("  %-6s %d ofertas" % (produto, len(achadas)))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--praca", default="Blumenau/SC")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cidade, uf = a.praca.split("/")
    d = coletar(cidade, uf, verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    for o in sorted(d["ofertas"], key=lambda x: x["degrau_mbps"] or 0):
        print("  %-38s %-10s R$ %-8g nivel %s" % (
            o["nome_oferta"][:38], o["destaque"], o["preco_promocional"] or 0,
            o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
