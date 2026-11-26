"""Coletor do Claro Flex - a linha below-the-line da Claro.

POR QUE EXISTE SEPARADO. O Flex nao mora em claro.com.br: tem dominio
proprio (flex.claro.com.br) e nao aparece em nenhuma das quatro paginas
que o coletor da Claro le. Por isso o tracker mostrava a Claro entrando
a R$ 59,90 no Controle quando ela entra a R$ 44,90 aqui - a oferta que
segura o cliente sem mexer no portfolio anunciado ficava inteira fora
da base. Mesma historia do Vivo Lite.

POR QUE NAVEGADOR. A pagina e uma SPA em Vue: o HTML servido tem 4 KB e
diz "doesn't work properly without JavaScript enabled". Procurei a API
por tras e nao ha - nenhuma chamada XHR e feita, e nao existe
__INITIAL_STATE__; os planos vem dentro do bundle JavaScript e so
existem depois de ele rodar. Entao e navegador, como na Unifique.

QUAL PRECO VALE. Cada card traz dois: "De: R$ 44,90" e "Por R$ 34,90 no
primeiro mes", este com cupom (VIRAFLEX10). Pela decisao 9 da
metodologia vale o preco cheio, sem desconto condicionado - entao o que
entra e o "De", e o "Por" fica como preco promocional declarado.

NACIONAL. O Flex nao pergunta cidade: o preco e o mesmo no pais todo,
como a NuCel e a Starlink.

Uso:  python coletores/claro_flex.py
"""

import argparse
import json
import re
import sys

from . import apps
from datetime import datetime, timedelta, timezone

PAGINA = "https://flex.claro.com.br/"
ESPERA = 5000

# Nacional: uma captura por dia basta - repetir nas 20 pracas gravaria
# 20 copias do mesmo preco.
NACIONAL = True

STREAMINGS = {"netflix", "globoplay", "amazon prime", "disney", "spotify",
              "premiere", "max", "paramount", "telecine", "deezer",
              "claro musica", "claro música"}
APPS_CATALOGO = {"skeelo", "mcafee", "claro banca", "claro day"}


def _num(txt):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?", str(txt or ""))
    if not m:
        return None
    return float("%s.%s" % (m.group(1).replace(".", ""), m.group(2) or "0"))


def nivel_bundle(texto):
    """Mesma escada dos outros coletores (decisao 10)."""
    t = (texto or "").lower()
    if "tv por assinatura" in t or "canais" in t:
        return 4
    return apps.nivel_por_apps(texto, APPS_CATALOGO)


# Um card do Flex, no texto que a pagina renderiza:
#
#   40GB  30GB do plano + 5GB de bonus redes sociais + 5GB de bonus
#   Claro Day  ...  De: R$ 44,90  Por R$ 34,90 No primeiro mes
#
# O "PASSAPORTE 60GB" nao declara composicao e cai no mesmo molde, com a
# franquia contratual ficando igual a anunciada.
# OS DOIS-PONTOS SAO OPCIONAIS NOS DOIS ROTULOS. Em 06/11/2026 "Por
# R$ 34,90" virou "Por: R$ 34,90" e o coletor voltou vazio nas quatro
# ofertas - um caractere de pontuacao derrubou a leitura do dia
# inteiro, como o "do" de "30GB do plano" em 23/10. Pontuacao de
# rotulo nao e dado: o dado e o numero ao lado dela.
CARD = re.compile(
    r"(\d{1,3})\s*GB"                      # a franquia anunciada
    r"(.{0,260}?)"                         # composicao e beneficios
    r"De:?\s*R\$\s?(\d{1,3},\d{2})"        # preco cheio
    r"\s*Por:?\s*R\$\s?(\d{1,3},\d{2})",    # preco com cupom, 1o mes
    re.I | re.S)


# O WHATSAPP E UM LOGO. O card escreve "App Ilimitado" (no Passaporte, "Apps
# Ilimitados") ao lado do logo do WhatsApp, e o detalhe do plano diz
# "WhatsApp ilimitado pra tudo" - mas o texto da pagina nunca nomeia o app, e
# o WhatsApp das quatro ofertas saia "nao" (auditoria de 26/11/2026). Antes
# de ler o texto, o card que traz o logo passa a dizer o que o logo diz. A
# troca tem quase o mesmo tamanho, porque a janela do CARD e de 260
# caracteres.
MARCA_O_WHATSAPP = r"""() => {
  let n = 0;
  for (const img of document.querySelectorAll('img')) {
    if (!/whats\s?app/i.test(img.alt || '')) continue;
    let el = img.parentElement;
    for (let k = 0; k < 4 && el; k++, el = el.parentElement) {
      const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let achou = false;
      while (w.nextNode()) {
        const v = w.currentNode.nodeValue;
        if (/\bapps?\s+ilimitad/i.test(v)) {
          w.currentNode.nodeValue = v.replace(/\bapps?\s+ilimitad[oa]s?/i, 'WhatsApp ilimitado');
          achou = true; n++;
        }
      }
      if (achou) break;
    }
  }
  return n;
}"""


def extrair(texto):
    t = re.sub(r"\s+", " ", texto or "")
    ofertas, vistos = [], set()
    for m in CARD.finditer(t):
        gb, meio, cheio, promo = m.groups()
        if gb in vistos:
            continue
        vistos.add(gb)
        # "30GB do plano": o que o contrato garante. O resto e bonus de
        # rede social e Claro Day, que e promocional e pode cair.
        #
        # O "do" E OPCIONAL. Em 23/10/2026 a Claro reescreveu o card e
        # "30GB do plano" virou "30GB plano": o numero continua
        # declarado, so a preposicao saiu. O regex exigia o "do", nao
        # achou, e a franquia garantida das quatro ofertas inflou para a
        # anunciada - 10 GB que o contrato nao garante.
        #
        # E O "LIVRES" TAMBEM (26/11/2026): desde 13/11 o card diz "35GB
        # Livres + 5GB de bonus...", a forma do coletor irmao, e o regex so
        # conhecia "plano" - a garantida de tres ofertas ficou vazia.
        mc = re.search(r"(\d{1,3})\s*GB\s*(?:(?:do\s+)?plano|livres?\b)", meio, re.I)
        # CARD QUE DECLARA BONUS TEM PARTE PROMOCIONAL. Se ele fala de
        # bonus e o numero do plano nao foi lido, contratual igual a
        # anunciada e afirmacao falsa - e falha tem de virar buraco, nao
        # numero (o coletor irmao, claro.py, ja devolve None no lugar).
        #
        # O Passaporte nao entra aqui: "60GB livre para voce usar e
        # navegar como quiser" nao separa bonus, entao nao ha o que
        # descontar e contratual igual a anunciada esta certo.
        tem_bonus = re.search(r"b[\u00f4o]nus", meio, re.I)
        passaporte = "passaporte" in meio.lower() or "passaporte" in t[
            max(0, m.start() - 40):m.start()].lower()
        ofertas.append({
            "nome_oferta": ("Claro Flex Passaporte %s GB" if passaporte
                            else "Claro Flex %s GB") % gb,
            "destaque": "%s GB" % gb,
            "franquia_anunciada_gb": int(gb),
            "franquia_contratual_gb": (
                int(mc.group(1)) if mc else (None if tem_bonus else int(gb))),
            # decisao 9: o que entra e o preco sem desconto condicionado
            "preco_promocional": _num(cheio),
            "preco_cheio": _num(cheio),
            "preco_primeiro_mes": _num(promo),
            "nivel_bundle": nivel_bundle(meio),
            "apps": apps.apps_do_texto(meio),
            "apps_rotulo": apps.rotulo(apps.apps_do_texto(meio), meio),
            "apps_planos": apps.planos_dos_apps(
                apps.apps_do_texto(meio), meio),
            # a leitura larga sai dita, no mesmo canal
            "avisos_oferta": apps.juntar_avisos(
                None, apps.aviso_de_leitura(meio)),
            "composicao": meio.strip()[:400],
            # o "App Ilimitado" do card e o WhatsApp - ver MARCA_O_WHATSAPP
            "whatsapp": apps.whatsapp_incluso(meio),
        })
        if not mc and tem_bonus:
            ofertas[-1]["avisos_oferta"] = apps.juntar_avisos(
                ofertas[-1].get("avisos_oferta"),
                apps.ressalva(
                    "franquia garantida ficou vazia",
                    "o card declara b\u00f4nus mas n\u00e3o diz quanto \u00e9 do plano: a "
                    "franquia garantida ficou vazia em vez de igualada \u00e0 "
                    "anunciada"))
    return ofertas


# OS APPS DO FLEX SAO OS DO HUB DA CLARO (27/11/2026). Os dois sites da
# Claro discordam: o hub de planos (planoscelular) mostra "App exclusivo pra
# voce: Skeelo" nos quatro cards do Flex, e Claro Musica no de 55 GB e no
# Passaporte 80 GB; o site do Flex - cards, as oito gavetas de detalhes e o
# cadastro para onde o proprio hub manda - nao cita app nenhum. Escolha de
# quem le, 26/11: "hub da Claro". O resto do card (preco, franquia,
# WhatsApp) continua vindo do site do Flex; do hub vem so a lista de apps,
# casada pela franquia anunciada. O bloco do hub e nacional (medido sem
# praca, em Manaus e em Porto Alegre: o mesmo) e os precos batem com os do
# site.
#
# A LISTA DE APPS E A CHAVE DA SERIE. Hub fora do ar nao pode virar "o Flex
# perdeu o Skeelo": nesse dia o Flex fica fora, dito. Hub que respondeu sem
# o bloco do Flex e outra coisa - a Claro tirou o Flex do hub -, e ai os
# apps sao so os do site, com aviso.
FLEX_NO_HUB = re.compile(r"Claro Flex\s+Plano sem fidelidade", re.I)
CARD_DO_HUB = re.compile(r"(?=Claro Flex\s+\d{2,3}\s*GB)", re.I)


def apps_do_hub(html):
    """{franquia GB: {"preco", "apps", "texto"}} dos cards do Flex no hub.

    Dicionario vazio quando o hub nao mostra o Flex.
    """
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).replace("&#32;", " ")
    ini = FLEX_NO_HUB.search(t)
    if not ini:
        return {}
    fim = t.find("Celulares Ofertas", ini.end())
    bloco = t[ini.end():fim if fim > 0 else ini.end() + 6000]
    saida = {}
    for card in CARD_DO_HUB.split(bloco)[1:]:
        gb = int(re.match(r"Claro Flex\s+(\d+)", card, re.I).group(1))
        preco = re.search(r"Demais meses\s*R\$\s*(\d{1,3},\d{2})", card)
        partes = re.split(r"exclusivos?\s+pra\s+voc\S*", card, maxsplit=1, flags=re.I)
        texto = (u"App exclusivo pra você: %s" % partes[1].strip()) if len(partes) > 1 else ""
        saida.setdefault(gb, {"preco": _num(preco.group(1)) if preco else None,
                              "apps": apps.apps_do_texto(texto) if texto else [],
                              "texto": texto})
    return saida


def ler_hub():
    """(apps do hub por franquia, erro ou None)."""
    from . import claro
    op, _ = claro.navegador()
    s, h = claro.buscar(op, claro.PAGINAS["movel"])
    if s != 200:
        return None, "HTTP %s" % s
    return apps_do_hub(h), None


def com_os_apps_do_hub(ofertas, hub, avisos):
    """Junta a cada oferta do site os apps do card do hub com a mesma franquia."""
    if not hub:
        avisos.append("o hub da Claro nao mostrou o Flex hoje: os apps sao so os do site do Flex")
        return ofertas
    for o in ofertas:
        par = hub.get(o["franquia_anunciada_gb"])
        if par is None:
            avisos.append("o hub da Claro nao tem o Flex de %s GB: os apps dele sao so os do site"
                          % o["franquia_anunciada_gb"])
            continue
        if par["preco"] is not None and par["preco"] != o["preco_cheio"]:
            avisos.append("o Flex de %s GB custa R$ %.2f no hub e R$ %.2f no site do Flex"
                          % (o["franquia_anunciada_gb"], par["preco"], o["preco_cheio"] or 0))
        lista = list(o["apps"] or []) + [a for a in par["apps"] if a not in (o["apps"] or [])]
        fonte = "%s %s" % (o.get("composicao") or "", par["texto"])
        o["apps"] = lista
        o["apps_rotulo"] = apps.rotulo(lista, fonte)
        o["apps_planos"] = apps.planos_dos_apps(lista, fonte)
        o["nivel_bundle"] = max(o.get("nivel_bundle") or 0, nivel_bundle(fonte))
    return ofertas


def coletar(cidade="Brasil", uf="BR", verbose=True, pagina=None):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Claro", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR CLARO FLEX  |  %s  |  %s"
              % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    # O NAVEGADOR SO E IMPORTADO QUANDO E PRECISO ABRI-LO. Com a pagina dada
    # (o teste, que roda onde o playwright nao esta instalado), o import
    # devolvia o aviso abaixo e o Flex saia vazio antes de ler a pagina.
    proprio = pagina is None
    if proprio:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            saida["avisos"].append(
                "playwright nao instalado - o Claro Flex exige navegador "
                "(pip install playwright && playwright install chromium)")
            return saida

    contexto = nav = p = None
    try:
        if proprio:
            p = sync_playwright().start()
            nav = p.chromium.launch(headless=True)
            contexto = nav.new_context(locale="pt-BR")
            pagina = contexto.new_page()

        pagina.goto(PAGINA, wait_until="domcontentloaded", timeout=60000)
        pagina.wait_for_timeout(ESPERA)
        try:
            pagina.evaluate(MARCA_O_WHATSAPP)
        except Exception as e:                          # noqa: BLE001
            saida["avisos"].append("o logo do WhatsApp nao foi lido: %s" % str(e)[:80])
        texto = pagina.inner_text("body")

        if "flex" not in texto.lower():
            saida["avisos"].append("a pagina do Flex nao carregou o conteudo")
            return saida

        ofertas = extrair(texto)
        if not ofertas:
            # vazio em silencio e o pior resultado: avisa
            saida["avisos"].append(
                "nenhum card reconhecido - o layout do Flex mudou")
            return saida

        # os apps vem do hub da Claro - ver com_os_apps_do_hub
        hub, erro_hub = ler_hub()
        if erro_hub:
            saida["avisos"].append(
                "apps do Flex no hub da Claro: %s - o Flex fica fora hoje, para "
                "a falta do app nao sair como troca de oferta" % erro_hub)
            return saida
        ofertas = com_os_apps_do_hub(ofertas, hub, saida["avisos"])

        for o in ofertas:
            o.update({
                "operadora": "Claro",
                # below-the-line e produto proprio: no balde do pos-pago
                # um plano de R$ 45 sumiria entre planos de R$ 150
                "produto": "btl",
                "linha": "flex",
                "praca": praca,
                "capturado_em": agora.isoformat(),
                "degrau_mbps": None,
                # o Flex nao tem fidelidade - e o argumento de venda dele
                "fidelidade_meses": None, "multa_fidelidade": None,
                "codigo_anatel": None, "campanha": None, "id_catalogo": None,
            })
            saida["ofertas"].append(o)

        if verbose:
            print("  %d ofertas" % len(ofertas))
    except Exception as e:
        saida["avisos"].append("navegador falhou: %s" % str(e)[:140])
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
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    d = coletar(verbose=not a.json)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    print("\n--- OFERTAS (%d) ---" % len(d["ofertas"]))
    for o in sorted(d["ofertas"], key=lambda x: x["preco_promocional"]):
        print("  %-28s %3s GB (contr %s) | R$ %6.2f | 1o mes R$ %6.2f | nivel=%s"
              % (o["nome_oferta"][:28], o["franquia_anunciada_gb"],
                 o["franquia_contratual_gb"], o["preco_promocional"],
                 o["preco_primeiro_mes"], o["nivel_bundle"]))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
