# -*- coding: utf-8 -*-
u"""Corrige o NOME de oferta que a coleta gravou errado, por tabela declarada.

POR QUE EXISTE. De 19 a 24/11/2026 o coletor da Unifique gravou a faixa
da campanha Black como nome do plano: "PAGAMENTO EM 2027" em quatro
planos e "MAS VOCE CONTINUA ONLINE" nos tres FIBRA + POWER. O coletor foi
consertado em 24/11 (a faixa sai pela classe antes da leitura), mas os
seis dias ja gravados continuavam no site com o nome errado - e o nome
errado escondia noticia: em 24/11 o FIBRA ESSENCIAL saiu da vitrine sem
nenhuma linha, porque "PAGAMENTO EM 2027" continuava existindo nos
outros planos. Escolha de quem le, em 23/11/2026: corrigir a base.

SO O NOME, E SO A COLUNA. Preco, velocidade, chave e o resto ficam. O
"bruto" guarda o que o coletor leu e fica como esta: e a prova do erro,
e a correcao esta escrita aqui e na metodologia.

CADA LINHA DA TABELA E UMA OFERTA, pelo que o erro nao tocou: operadora,
periodo, o nome gravado, velocidade e preco. Nenhuma combinacao casa com
duas ofertas - conferido no dado publicado antes de escrever.

Sem --aplicar, so conta. Com --aplicar, grava e confere: o numero de
linhas alteradas tem de ser o numero contado, e depois nao pode sobrar
nenhuma com o nome errado. Qualquer diferenca para tudo, alto.

Uso: python corrigir_nomes.py [--aplicar]   (precisa dos segredos do Supabase)
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from coletores import armazenamento

# (operadora, primeiro dia, ultimo dia, nome gravado, degrau_mbps, preco, nome certo)
CORRECOES = [
    ("Unifique", "2026-11-19", "2026-11-24", "PAGAMENTO EM 2027", 100, 89.9,
     "FIBRA ESSENCIAL"),
    ("Unifique", "2026-11-19", "2026-11-24", "PAGAMENTO EM 2027", 500, 119.9,
     "FIBRA IDEAL"),
    # A PAGINA CHAMA O PLANO DE "FIBRA COMPLETA". Ate 18/11 ele foi
    # gravado "FIBRA COMPLETA WI-FI EXTRA" - quase certamente outra faixa
    # colada no nome, a de antes da Black. Fica o nome da pagina, que e o
    # que o coletor grava daqui em diante.
    ("Unifique", "2026-11-19", "2026-11-24", "PAGAMENTO EM 2027", 600, 129.9,
     "FIBRA COMPLETA"),
    ("Unifique", "2026-11-19", "2026-11-24", "PAGAMENTO EM 2027", 1000, 159.9,
     "FIBRA TURBO"),
    ("Unifique", "2026-11-20", "2026-11-24", u"MAS VOCÊ CONTINUA ONLINE", 500,
     134.9, "FIBRA + POWER"),
    ("Unifique", "2026-11-20", "2026-11-24", u"MAS VOCÊ CONTINUA ONLINE", 600,
     144.9, "FIBRA + POWER"),
    ("Unifique", "2026-11-20", "2026-11-24", u"MAS VOCÊ CONTINUA ONLINE", 1000,
     174.9, "FIBRA + POWER"),
]


def filtro(c):
    u"""O filtro da linha da tabela. Os seis campos SEMPRE: um PATCH sem
    filtro no PostgREST altera a tabela inteira."""
    operadora, de, ate, errado, mbps, preco, _certo = c
    q = urllib.parse.quote
    return ("operadora=eq.%s&data_captura=gte.%s&data_captura=lte.%s"
            "&nome_oferta=eq.%s&degrau_mbps=eq.%d&preco_promocional=eq.%s"
            % (q(operadora), de, ate, q(errado), mbps, repr(preco)))


def _pedido(metodo, caminho, corpo=None):
    url, chave = armazenamento._config()
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url + armazenamento.API + caminho,
                                 data=dados, method=metodo)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8") or "[]")


def contar(c):
    return len(_pedido("GET", "capturas?%s&select=id&limit=5000" % filtro(c)))


def aplicar(c):
    return len(_pedido("PATCH", "capturas?%s&select=id" % filtro(c),
                       {"nome_oferta": c[6]}))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gravar = "--aplicar" in argv
    contados = [contar(c) for c in CORRECOES]
    for c, n in zip(CORRECOES, contados):
        print("%-9s %s a %s  %-26s %4d Mbps R$ %7.2f -> %-16s %3d linha(s)"
              % (c[0], c[1], c[2], c[3], c[4], c[5], c[6], n))
    print("total: %d linha(s)" % sum(contados))
    if not gravar:
        print("so contei - para gravar, --aplicar")
        return 0
    for c, n in zip(CORRECOES, contados):
        feitas = aplicar(c)
        if feitas != n:
            print("PAREI: %s %d Mbps - contei %d e alterei %d"
                  % (c[3], c[4], n, feitas))
            return 1
    sobrou = sum(contar(c) for c in CORRECOES)
    if sobrou:
        print("PAREI: depois de gravar ainda ha %d linha(s) com o nome errado"
              % sobrou)
        return 1
    print("gravado e conferido: %d linha(s), nenhuma com o nome errado"
          % sum(contados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
