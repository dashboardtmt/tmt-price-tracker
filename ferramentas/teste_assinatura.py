"""Confere a leitura da assinatura de composicao direto do jsonb.

A assinatura dos codigos SVA nao tem coluna propria: ela viaja dentro de
"bruto", a captura crua, e e lida por bruto->>assinatura_sva. Isso evita
um ALTER TABLE na mao a cada campo novo - e passo manual esquecido e dia
de coleta perdida, que nao volta.

O que este teste prova, contra o banco de verdade:
  1. o PostgREST aceita extrair campo de dentro do jsonb
  2. o que sai do jsonb e igual ao que esta na coluna equivalente
  3. mudancas() roda ponta a ponta sem quebrar

So le. Nao grava, nao manda mensagem, nao chama operadora nenhuma.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                  # noqa: E402
from coletores import armazenamento          # noqa: E402


def ultimo_dia():
    linhas, erro = armazenamento.consultar(
        "capturas?select=data_captura&order=data_captura.desc&limit=1")
    if erro or not linhas:
        return None, erro or "banco sem capturas"
    return linhas[0]["data_captura"], None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dia, erro = ultimo_dia()
    if erro:
        print("FALHOU: %s" % erro)
        return 1
    print("ultimo dia no banco: %s" % dia)

    # 1 e 2. Pede o mesmo dado por coluna e por dentro do jsonb. Se os dois
    # baterem, a extracao esta provada com dado real - a assinatura em si so
    # existe nas capturas feitas depois que o coletor passou a le-la.
    campos = ("produto,nome_oferta,operadora,"
              "do_jsonb:bruto->>produto,"
              "assinatura_sva:bruto->>assinatura_sva")
    linhas, erro = armazenamento.consultar_tudo(
        "capturas?data_captura=eq.%s&select=%s" % (dia, campos))
    if erro:
        print("FALHOU ao extrair do jsonb: %s" % erro)
        return 1

    # Quantas capturas o dia tem de verdade. O PostgREST corta em 1000, e
    # uma consulta sem paginacao traz so a primeira pagina sem avisar - era
    # o que a comparacao diaria fazia, pedindo limit=20000 e confiando.
    uma_pagina, _ = armazenamento.consultar(
        "capturas?data_captura=eq.%s&select=produto&limit=20000" % dia)
    print("\n0. capturas do dia: %d paginando, %d numa pagina so"
          % (len(linhas), len(uma_pagina or [])))
    if len(linhas) > len(uma_pagina or []):
        print("   confirmado: sem paginar, %d capturas ficavam invisiveis"
              % (len(linhas) - len(uma_pagina or [])))

    conferem = sum(1 for l in linhas if l["produto"] == l["do_jsonb"])
    print("\n1. extracao do jsonb: %d linhas lidas, sem erro" % len(linhas))
    print("2. coluna x jsonb: %d de %d conferem" % (conferem, len(linhas)))
    if conferem != len(linhas):
        divergente = next(l for l in linhas if l["produto"] != l["do_jsonb"])
        print("   FALHOU - exemplo: coluna=%r jsonb=%r"
              % (divergente["produto"], divergente["do_jsonb"]))
        return 1

    com = [l for l in linhas if l.get("assinatura_sva")]
    print("\n3. assinatura presente em %d de %d capturas de %s"
          % (len(com), len(linhas), dia))
    if com:
        print("   assinaturas distintas: %d" % len({l["assinatura_sva"] for l in com}))
        for l in com[:3]:
            print("   %-9s %-28s %s" % (l["operadora"], (l["nome_oferta"] or "")[:28],
                                        l["assinatura_sva"]))
    else:
        print("   esperado se a coleta deste dia rodou com o codigo anterior:")
        print("   a assinatura entra nas capturas feitas a partir da proxima.")

    # 4. a comparacao diaria inteira, do jeito que o aviso das 8h a usa
    anterior, _ = armazenamento.consultar(
        "capturas?select=data_captura&data_captura=lt.%s"
        "&order=data_captura.desc&limit=1" % dia)
    if anterior:
        ontem = anterior[0]["data_captura"]
        r = robo.mudancas(dia, ontem)
        if r["erro"]:
            print("\n4. mudancas FALHOU: %s" % r["erro"])
            return 1
        print("\n4. mudancas(%s, %s):" % (dia, ontem))
        for chave in ("precos", "composicao", "renomeadas", "grades",
                      "voltaram", "remodeladas"):
            print("   %-12s %d" % (chave, len(r[chave])))
        if r["cego"]:
            print("   ponto cego: %s" % r["cego"]["curto"])
        for m in r["renomeadas"][:4]:
            a, d = m["antes"], m["atual"]
            mudou = ("PRECO MUDOU: %s -> %s" % (a["preco_promocional"],
                                                d["preco_promocional"])
                     if a["preco_promocional"] != d["preco_promocional"]
                     else "mesmo preco (%s)" % d["preco_promocional"])
            print("   %s -> %s | %s | %d praca(s)"
                  % (a["nome_oferta"], d["nome_oferta"], mudou, len(m["pracas"])))
        # Cobertura: zero mudancas pode significar mercado parado ou
        # comparacao cega. A diferenca esta em quantas ofertas de hoje
        # encontram a mesma identidade ontem - sem par, nao ha o que
        # comparar e o silencio nao prova nada.
        # A COBERTURA AGORA SAI DO ROBO. Ela era calculada aqui, a mao,
        # e so quem rodasse esta ferramenta a veria - hoje vem no mesmo
        # levantamento que alimenta a mensagem e o relatorio.
        hj, _e, _c = robo._indexar(dia)
        on, _e, _c = robo._indexar(ontem)
        comuns = set(hj) & set(on)
        cob = r["cobertura"] or {}
        print("   ofertas: %d em %s, %d em %s, %d com par nos dois"
              % (len(hj), dia, len(on), ontem, len(comuns)))
        if cob:
            print("   cobertura da comparacao: %.0f%% das ofertas de hoje"
                  % (100.0 * cob["fracao"]))
            for op, (pares, total) in sorted(cob["por_operadora"].items()):
                if total and pares < total * 0.6:
                    print("      %s: so %d de %d com par" % (op, pares, total))
        # por operadora, para distinguir ausencia esperada (coletor novo,
        # praca que a operadora nao atende) de serie partida de verdade
        import collections
        for titulo, indice, chaves in (("apareceram hoje", hj, set(hj) - comuns),
                                       ("sairam de ontem", on, set(on) - comuns)):
            if not chaves:
                continue
            porop = collections.Counter(indice[k]["operadora"] for k in chaves)
            print("   sem par, %s: %s" % (titulo, ", ".join(
                "%s %d" % (o, n) for o, n in porop.most_common())))
            exemplo = [indice[k]["nome_oferta"] for k in list(chaves)[:2]]
            print("      ex: %s" % " | ".join(str(n)[:34] for n in exemplo))
    else:
        print("\n4. so existe um dia no banco - nada a comparar ainda")

    print("\nok: a assinatura e legivel sem coluna nova e sem ALTER TABLE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
