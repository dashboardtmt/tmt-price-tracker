"""Coletor da Starlink.

A melhor fonte das sete, de longe. A Starlink expoe uma API publica e
estruturada, sem anti-bot e sem navegador:

    /api/webagg/v1/public/marketing/availability
        ?invitationTypeCode=N&isoCountryCode=BR

Ela devolve preco, promocao e duracao em campos separados - o que na Vivo
exige ler o regulamento da Anatel e nas outras nao existe.

NAO E COMPARAVEL COM AS OUTRAS SEIS, e por isso entra como produto
proprio ("satelite") em vez de disputar degrau com a fibra:

  - a tecnologia e satelite, e a secao 6 da metodologia exclui de FTTH
    justamente o que nao e fibra. Misturar faria a Starlink parecer cara
    por Mbps contra uma fibra que ela nao substitui
  - a velocidade nao e contratada e sim "ate", variando com a celula de
    cobertura e o horario
  - o custo de entrada e outra ordem de grandeza: o kit padrao custa
    R$ 2.400, contra instalacao gratis ou quase na fibra. Comparar so a
    mensalidade esconde o que pesa na decisao de quem contrata
  - nao ha praca: o preco e nacional, declarado por pais

As duas familias vendidas no Brasil tem codigos distintos na API, achados
por varredura: 1 e residencial e 6 e o Priority, de uso profissional.

Uso:  python coletores/starlink.py
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

from . import rede
from datetime import datetime, timedelta, timezone

API = ("https://www.starlink.com/api/webagg/v1/public/marketing/availability"
       "?invitationTypeCode=%d&isoCountryCode=BR")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

PAUSA = 3

# Nacional: o endpoint recebe pais, nao cidade. Uma captura por dia basta,
# como na NuCel - repetir nas 20 pracas gravaria 20 copias do mesmo preco.
NACIONAL = True

# invitationTypeCode -> a familia que ele devolve. Os outros codigos
# testados (2, 3 e 5) voltam vazios ou com 422; ficam de fora ate a
# Starlink passar a vender algo neles.
FAMILIAS = {
    1: "residencial",
    6: "priority",
}


# O CABECALHO DE LINGUA E CARGA, nao enfeite. Medido em 27/10/2026, na
# API de verdade: sem "Accept-Language: pt-BR" a Starlink responde em
# INGLES, e 33 campos mudam. Dois deles importam.
#
#   O NOME DA OFERTA MUDA. "Residencial: 100 Mbps" vira "Residential -
#   100 Mbps", e "Residencial - Max" vira "Residential - Max". O nome
#   entra na identidade da oferta: trocar a lingua faria TODAS as
#   ofertas da Starlink parecerem novas no mesmo dia, e a continuidade
#   da serie se partiria sem nada ter mudado no produto.
#
#   A VELOCIDADE DECLARADA SOME. Em portugues o Max traz "Ate mais de
#   400 Mbps"; em ingles, "Up to 400+ Mbps". A frase em ingles nao casa
#   com a leitura - o "+" fica entre o numero e a unidade -, entao
#   velocidade_declarada volta None e o unico dado que existe sobre a
#   velocidade daquele plano se perde calado.
#
# Nenhum dos dois quebra: os dois ficam ERRADOS EM SILENCIO, que e pior.
# Medido tambem que o Referer e o Accept nao mudam nada - a lingua e a
# unica carga aqui.
def _http(url, timeout=45, avisos=None):
    def uma():
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "application/json")
        req.add_header("Accept-Language", "pt-BR,pt;q=0.9")
        req.add_header("Referer", "https://www.starlink.com/br")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:300]
        except Exception as e:
            return 0, str(e)
    return rede.insistir(uma, url, avisos=avisos)


# FAIXA ABERTA NAO E DEGRAU. A Starlink descreve o plano Max como "Ate
# mais de 400 Mbps": ela diz que passa de 400 e se recusa a dizer
# quanto. Ler 400 dali inventa precisao que a fonte nega, e inventa no
# PISO da faixa - o plano melhor dela ia para 400 contra uma fibra de
# 700 ou 1000 no mesmo grafico de degraus (decisao 8: exatas, sem
# faixas).
#
# "Ate 100 Mbps" NAO cai aqui, e nao deve: e teto do mesmo numero que o
# nome do plano declara ("Residencial: 100 Mbps"). O que desqualifica e
# o piso sem teto.
PISO_SEM_TETO = re.compile(
    r"(?:mais\s+de|acima\s+de|superior\s+a|a\s+partir\s+de|\bat[\u00e9e]\s+mais)"
    r"[^.;\n]{0,24}$", re.I)


def velocidade(texto):
    """"Residential - 100 Mbps" -> 100. "Max" nao declara velocidade.

    Devolve None tambem quando o numero vem atras de um piso sem teto -
    "Ate mais de 400 Mbps" -, porque ali a fonte declarou uma faixa e
    nao um degrau.
    """
    t = str(texto or "")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(Mbps|Gbps)", t, re.I)
    if not m:
        return None
    if PISO_SEM_TETO.search(t[:m.start()]):
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1000) if m.group(2).lower().startswith("g") else int(v)


def velocidade_declarada(*fontes):
    """A frase da fonte sobre velocidade, como ela escreveu.

    NAO INVENTAR NAO E JOGAR FORA. O plano Max perde o degrau porque
    "Ate mais de 400 Mbps" e faixa, mas a promessa da operadora continua
    sendo informacao - e a unica que existe sobre a velocidade dele.
    Guardada em texto, ela chega a quem olha a oferta sem virar um ponto
    falso no grafico.
    """
    for fonte in fontes:
        for linha in re.split(r"[.;\n*]", str(fonte or "")):
            if re.search(r"\d\s*(?:Mbps|Gbps)", linha, re.I):
                return " ".join(linha.split())
    return None


def franquia(texto):
    """"Local Priority 500 GB" -> 500. "1 TB" -> 1024."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(GB|TB)", str(texto or ""), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return int(v * 1024) if m.group(2).upper() == "TB" else int(v)


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coletar(cidade="Brasil", uf="BR", verbose=True):
    agora = datetime.now(timezone(timedelta(hours=-3)))
    praca = "%s/%s" % (cidade, uf)
    saida = {"operadora": "Starlink", "praca": praca,
             "capturado_em": agora.isoformat(), "ofertas": [], "avisos": []}

    if verbose:
        print("=" * 70)
        print("COLETOR STARLINK  |  %s  |  %s"
              % (praca, agora.strftime("%d/%m/%Y %H:%M")))
        print("=" * 70)

    for codigo, familia in FAMILIAS.items():
        status, corpo = _http(API % codigo)
        if status != 200:
            saida["avisos"].append("%s: HTTP %s" % (familia, status))
            if verbose:
                print("  %-12s FALHOU (HTTP %s)" % (familia, status))
            time.sleep(PAUSA)
            continue
        try:
            d = json.loads(corpo)
        except ValueError as e:
            saida["avisos"].append("%s: resposta ilegivel (%s)" % (familia, e))
            time.sleep(PAUSA)
            continue

        if not d.get("isAvailable"):
            # ausencia declarada pela fonte nao e falha: a Starlink pode
            # simplesmente nao vender esta familia no Brasil hoje
            saida["avisos"].append("%s: a Starlink declara indisponivel" % familia)
            if verbose:
                print("  %-12s indisponivel (declarado pela fonte)" % familia)
            time.sleep(PAUSA)
            continue

        # O kit e custo de entrada, nao mensalidade. Vale o mais barato da
        # familia, que e o que o site anuncia como "a partir de".
        kits = [(_num(k.get("adjustedPrice") or k.get("price")),
                 k.get("description") or k.get("name"))
                for k in (d.get("kits") or [])]
        kits = [(p, n) for p, n in kits if p is not None]
        # O NOME DO KIT JUNTO COM O PRECO. O campo gravava so o numero e
        # perdia de qual kit ele saiu: na familia residencial o minimo e
        # o Kit Mini a R$ 99, hardware diferente do prato Standard de
        # R$ 2.400 que o plano sugere. O numero continua o "a partir de"
        # que o site anuncia; agora da para conferir de onde veio.
        kit_min, kit_min_nome = min(kits) if kits else (None, None)

        assinaturas = d.get("subscriptions") or []
        for s in assinaturas:
            nome = s.get("description") or s.get("englishDescription") or ""
            preco = _num(s.get("adjustedPrice"))
            if preco is None:
                continue
            saida["ofertas"].append({
                "operadora": "Starlink",
                # produto proprio: satelite nao disputa degrau com fibra
                "produto": "satelite",
                "praca": praca,
                "capturado_em": agora.isoformat(),
                "nome_oferta": nome,
                "destaque": nome,
                "degrau_mbps": (velocidade(nome)
                                or velocidade(s.get("longDescription"))),
                # a promessa da fonte quando ela declara faixa e nao
                # degrau: "Ate mais de 400 Mbps" no plano Max
                "velocidade_declarada": velocidade_declarada(
                    nome, s.get("longDescription")),
                "franquia_anunciada_gb": franquia(nome),
                "franquia_contratual_gb": None,
                # a Starlink nao publica preco de tabela separado: o
                # adjustedPrice e o preco anunciado (decisao 9)
                "preco_cheio": None,
                "preco_promocional": preco,
                # o kit nao e instalacao, mas e o custo de entrada que o
                # campo representa nas outras operadoras
                "taxa_instalacao": kit_min,
                "taxa_instalacao_kit": kit_min_nome,
                "fidelidade_meses": None,
                "multa_fidelidade": None,
                # a propria API declara quanto dura a promocao, o que so a
                # Brisanet tambem faz
                "meses_desconto": s.get("durationInMonths"),
                "preco_pos_promocao": None,
                "promocao_ate": s.get("promoEndDate"),
                "nivel_bundle": 0,          # conectividade pura, sem apps
                "familia": familia,
                "id_catalogo": s.get("productId"),
                "codigo_anatel": None,
                "campanha": None,
                "tecnologia": ["satelite"],
                "kits": [{"preco": p, "nome": n} for p, n in sorted(kits)],
                "moeda": d.get("isoCurrencyCode"),
            })

        if verbose:
            print("  %-12s %d oferta(s) | kit a partir de %s"
                  % (familia, len(assinaturas),
                     ("R$ %.2f" % kit_min) if kit_min is not None else "-"))
        time.sleep(PAUSA)

    if not saida["ofertas"] and not saida["avisos"]:
        saida["avisos"].append("nenhuma oferta e nenhum aviso - a API mudou de formato")
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
        entrega = ("%d Mbps" % o["degrau_mbps"]) if o["degrau_mbps"] else (
            ("%d GB" % o["franquia_anunciada_gb"]) if o["franquia_anunciada_gb"] else "-")
        print("  %-11s %-26s %-10s R$ %8.2f  kit R$ %s"
              % (o["familia"], (o["nome_oferta"] or "")[:26], entrega,
                 o["preco_promocional"],
                 ("%.2f" % o["taxa_instalacao"]) if o["taxa_instalacao"] else "-"))
    if d["avisos"]:
        print("\n--- AVISOS ---")
        for av in d["avisos"]:
            print("  " + av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
