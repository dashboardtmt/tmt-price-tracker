"""Monta o dicionario de codigos SVA da Vivo, por cruzamento.

A Vivo lista os apps inclusos por codigo da Anatel ("030039"), sem dizer
o nome. A vitrine, por outro lado, escreve os nomes por extenso
("Assinatura Netflix inclusa"). Cruzando as duas coisas em muitas ofertas,
da para deduzir qual codigo e qual app.

REGRA QUE NAO SE NEGOCIA: o dicionario e DEDUZIDO, nao oficial. Ele nunca
vira fonte unica. O texto da vitrine continua mandando na classificacao
de bundle; o codigo entra como confirmacao e como alarme - quando os dois
discordam, e sinal de que a oferta mudou de composicao sem mudar o texto,
que e justamente o "repasse disfarcado" da metodologia.

Por isso cada entrada carrega a evidencia que a sustenta, e nenhuma
deducao com pouca base vira verdade.

Uso:
  python dicionario_sva.py --pracas 3 --saida sva.json
"""

import argparse
import collections
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coletores import vivo                      # noqa: E402
from coletores.pracas import PRACAS             # noqa: E402

# Nomes que a vitrine escreve por extenso. Procurados no texto do card.
APPS = [
    "Netflix", "Globoplay", "Amazon Prime", "Disney+", "Spotify", "Premiere",
    "Max", "Paramount", "Telecine", "Deezer", "Skeelo", "GoRead", "NBA",
    "Hube", "Super Comics", "Atma", "BTFit", "McAfee", "Ubook", "Forbes",
    "Casa do Saber", "Vivo Home Fix", "NFL", "Gemini", "Cinemark",
    "Google One", "iCloud", "Vivo Travel", "Vivo Sync", "Vivo Cloud",
]

# Quantas ofertas distintas precisam sustentar uma deducao para ela valer.
# Abaixo disso a entrada fica como "fraca" e nao e usada em lugar nenhum.
MINIMO_EVIDENCIAS = 2


def apps_no_texto(texto):
    """Os apps que a vitrine nomeia neste card."""
    t = (texto or "").lower()
    return {a for a in APPS if a.lower() in t}


def coletar_evidencias(n_pracas):
    """Junta, por oferta: os codigos do regulamento e os apps da vitrine.

    Conta cada oferta UMA vez, mesmo aparecendo em varias pracas. O catalogo
    da Vivo e quase igual entre capitais: sem isso, "duas evidencias" seria
    a mesma oferta vista em duas cidades - repeticao passando por confirmacao.
    """
    evidencias = []
    vistas = set()
    for p in PRACAS[:n_pracas]:
        d = vivo.coletar(p["cidade"], p["uf"], verbose=False)
        for o in d["ofertas"]:
            codigo = o.get("codigo_anatel")
            if not codigo:
                continue
            reg = vivo._cache_regulamento.get(codigo)
            if not reg:
                continue
            bloco = reg.get("SMP") or reg.get("SCM") or {}
            sva = [c for c in (bloco.get("listaSVA") or []) if c]
            if not sva:
                continue
            # o nome da oferta tambem carrega o app ("Vivo Controle Amazon"),
            # entao entra no texto procurado junto com o corpo do card
            nomes = apps_no_texto("%s %s" % (o.get("nome_oferta") or "",
                                             o.get("bruto_texto") or ""))
            impressao = (o.get("nome_oferta"), codigo,
                         tuple(sorted(sva)), tuple(sorted(nomes)))
            if impressao in vistas:
                continue
            vistas.add(impressao)
            evidencias.append({
                "codigo_anatel": codigo,
                "oferta": o.get("nome_oferta"),
                "sva": sva,
                "apps_vitrine": sorted(nomes),
            })
    return evidencias


def deduzir(evidencias):
    """Cruza codigo com nome e mede a forca de cada deducao.

    Duas armadilhas medidas nos dados reais, e o que se faz com cada uma:

    1) A vitrine nao lista todos os apps - lista os de marketing. Um card
       que nao escreve "Gemini" nao esta dizendo que Gemini esta fora; esta
       calado. Por isso oferta sem nenhum app nomeado NAO conta como
       contraexemplo: silencio nao e negacao. Tratar silencio como ausencia
       era o que derrubava toda deducao.

    2) Varios codigos aparecem sempre nas MESMAS ofertas (030035, 030039,
       030048, 100060 e 100069 dividem as mesmas 14). Nenhum cruzamento
       separa codigos que nunca se separam: eles formam um bloco e so o
       bloco pode ser nomeado. Atribuir o mesmo app a cada um deles seria
       inventar precisao.

    Para cada par codigo/app ficam duas taxas, e as duas tem de fechar:
      suporte      - das ofertas com o codigo, quantas nomeiam o app
      exclusividade - das ofertas que nomeiam o app, quantas trazem o codigo
    """
    # so ofertas que nomeiam ao menos um app servem de base: as outras
    # nao informam nem presenca nem ausencia
    uteis = [e for e in evidencias if e["apps_vitrine"]]
    ofertas = [(set(e["sva"]), set(e["apps_vitrine"])) for e in uteis]

    # blocos: codigos que ocorrem exatamente no mesmo conjunto de ofertas
    onde = collections.defaultdict(set)
    for i, (svas, _) in enumerate(ofertas):
        for c in svas:
            onde[c].add(i)
    bloco_de = collections.defaultdict(list)
    for c, idx in onde.items():
        bloco_de[frozenset(idx)].append(c)

    com_app = collections.Counter()
    for _, apps in ofertas:
        for a in apps:
            com_app[a] += 1

    dicionario = {}
    for codigo, idx in onde.items():
        n = len(idx)
        irmaos = sorted(x for x in bloco_de[frozenset(idx)] if x != codigo)
        taxas = {}
        for app, total_app in com_app.items():
            juntos = sum(1 for i in idx if app in ofertas[i][1])
            if not juntos:
                continue
            taxas[app] = (juntos / float(n), juntos / float(total_app))

        casam = sorted(a for a, (sup, exc) in taxas.items() if sup == 1.0 and exc == 1.0)
        entrada = {
            "ofertas_com_o_codigo": n,
            "candidatos": casam,
            "indistinguivel_de": irmaos,
            # a medida crua de cada app que ja conviveu com o codigo
            "associacao": {a: {"suporte": round(s, 2), "exclusividade": round(e, 2)}
                           for a, (s, e) in sorted(taxas.items(),
                                                   key=lambda kv: -kv[1][0])},
        }
        if irmaos:
            # empatado com outro codigo: o bloco pode ter nome, o codigo nao
            entrada["confianca"] = "bloco"
        elif len(casam) == 1 and n >= MINIMO_EVIDENCIAS:
            entrada["app"] = casam[0]
            entrada["confianca"] = "alta"
        elif casam:
            entrada["confianca"] = "fraca"     # ambiguo ou pouca base
        else:
            entrada["confianca"] = "indefinida"
        dicionario[codigo] = entrada
    return dicionario, len(evidencias) - len(uteis)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pracas", type=int, default=2)
    ap.add_argument("--saida", default="sva.json")
    a = ap.parse_args()

    print("coletando evidencias em %d praca(s)..." % a.pracas)
    ev = coletar_evidencias(a.pracas)
    print("  %d ofertas com codigo e lista de SVA" % len(ev))
    if not ev:
        print("  nada a cruzar")
        return 1

    dic, calados = deduzir(ev)
    if calados:
        print("  %d sem app nomeado na vitrine - fora do cruzamento (silencio "
              "nao e ausencia)" % calados)

    altas = {k: v for k, v in dic.items() if v.get("confianca") == "alta"}
    print("\n%d codigos vistos | %d deduzidos com confianca alta" % (len(dic), len(altas)))
    for c, v in sorted(altas.items(), key=lambda kv: kv[1]["app"]):
        print("  %-10s -> %-18s (%d ofertas)" % (c, v["app"], v["ofertas_com_o_codigo"]))

    blocos = {}
    for c, v in dic.items():
        if v["confianca"] == "bloco":
            blocos.setdefault(tuple(sorted([c] + v["indistinguivel_de"])), v)
    if blocos:
        print("\n%d codigos sao indistinguiveis entre si (aparecem sempre nas "
              "mesmas ofertas):" % sum(len(k) for k in blocos))
        for grupo, v in sorted(blocos.items()):
            print("  {%s} convive com %s" % (
                ", ".join(grupo), ", ".join(v["candidatos"]) or "nenhum app nomeado"))
        print("  (o bloco pode ter nome; o codigo sozinho nao - nao e usado)")

    fracos = [c for c, v in dic.items() if v["confianca"] in ("fraca", "indefinida")]
    if fracos:
        print("\n%d codigos sem deducao: %s" % (len(fracos), ", ".join(sorted(fracos))))
        print("  (entram no arquivo marcados, e nao sao usados em lugar nenhum)")

    io.open(a.saida, "w", encoding="utf-8").write(
        json.dumps({"deduzido_em": __import__("datetime").date.today().isoformat(),
                    "aviso": "Deduzido por cruzamento, nao oficial. "
                             "Nunca usar como fonte unica: o texto da vitrine manda.",
                    "codigos": dic,
                    # a evidencia crua fica no arquivo: sem ela nao da para
                    # conferir uma deducao nem entender por que outra falhou
                    "evidencias": ev}, ensure_ascii=False, indent=1))
    print("\ngravado: %s" % a.saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
