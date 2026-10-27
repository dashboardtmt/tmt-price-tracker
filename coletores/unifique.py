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

O NAVEGADOR CONTINUA AQUI, de proposito. Ele nao e mais necessario para
ESCOLHER a cidade - a URL faz isso -, mas a leitura roda em cima do
texto renderizado, e trocar isso por HTML cru mudaria o que se le. O que
saiu foi a coreografia: abrir o seletor, achar o campo de busca, digitar
e clicar no resultado certo. Era o trecho mais fragil do projeto.

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
from . import apps
from datetime import datetime, timedelta, timezone

PAGINA = "https://unifique.com.br/para-voce/internet-fibra"
ESPERA = 2000

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
        gratis = re.search(r"instala[çc][ãa]o\s*gr[áa]tis", meio, re.I)
        ofertas.append({
            "nome_oferta": nome[:60],
            "destaque": "%s Mega" % mega,
            "degrau_mbps": _mbps(mega + " Mega"),
            "preco_promocional": _num(preco),
            # a Unifique escreve a taxa no proprio card; as outras so trazem
            # isso no regulamento, quando trazem
            "taxa_instalacao": _num(taxa.group(1)) if taxa else (0.0 if gratis else None),
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


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def rota_da_cidade(cidade, uf):
    """A URL propria da cidade, que e para onde o seletor navega.

    O endereco e sem acento e com hifen: "Sao Jose dos Campos" vira
    "sao-jose-dos-campos". Foi so por causa do acento que Florianopolis
    passou um mes fora da coleta.
    """
    pedaco = re.sub(r"[^a-z0-9]+", "-", sem_acento(cidade).lower()).strip("-")
    return "%s/%s/%s" % (PAGINA, uf.lower(), pedaco)


def coletar(cidade, uf, verbose=True, pagina=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Unifique", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR UNIFIQUE  |  %s  |  %s" % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        saida["avisos"].append(
            "playwright nao instalado - a Unifique exige navegador "
            "(pip install playwright && playwright install chromium)")
        return saida

    proprio = pagina is None
    contexto = nav = p = None
    try:
        if proprio:
            p = sync_playwright().start()
            nav = p.chromium.launch(headless=True)
            contexto = nav.new_context(locale="pt-BR")
            pagina = contexto.new_page()

        # A ROTA DA CIDADE responde 404 quando a Unifique nao atende, e
        # isso e melhor sinal do que "nao achei o botao": separa
        # ausencia real de layout quebrado, sem depender de nada na tela.
        resposta = pagina.goto(rota_da_cidade(cidade, uf),
                               wait_until="domcontentloaded", timeout=60000)
        if resposta is not None and resposta.status == 404:
            err = "a Unifique nao atende %s/%s" % (cidade, uf)
            saida["avisos"].append(err)
            if verbose:
                print("  %s" % err)
            return saida
        pagina.wait_for_timeout(ESPERA)

        texto = pagina.inner_text("body")
        # SEM ACENTO DOS DOIS LADOS. A cesta guarda "Florianopolis" e a
        # pagina escreve "Florianopolis" com acento: comparar cru faz a
        # confirmacao falhar justamente nas cidades acentuadas.
        if sem_acento(cidade).lower() not in sem_acento(texto).lower():
            saida["avisos"].append("a pagina nao confirmou a cidade %s" % cidade)

        for o in extrair(texto):
            o.update({
                "operadora": "Unifique", "produto": "fibra", "praca": praca,
                "capturado_em": agora.isoformat(),
                "franquia_anunciada_gb": None, "franquia_contratual_gb": None,
                "preco_cheio": None,
                "nivel_bundle": nivel_bundle(o.pop("contexto", "")),
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
                "fidelidade_meses": None, "multa_fidelidade": None,
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
    except Exception as e:
        saida["avisos"].append("navegador: %s" % str(e)[:140])
        if verbose:
            print("  ERRO: %s" % str(e)[:140])
    finally:
        if proprio:
            for fechar in (contexto, nav):
                try:
                    fechar and fechar.close()
                except Exception:
                    pass
            try:
                p and p.stop()
            except Exception:
                pass
    return saida


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
