# -*- coding: utf-8 -*-
u"""Apaga as linhas que a coleta gravou de uma fonte sabidamente errada, por
tabela declarada.

POR QUE EXISTE. Em 27/11/2026 as paginas do TIM Black, do Familia e da
Ultrafibra trocaram de formato para o servidor do GitHub, o coletor nao
leu nenhum card, e o carrossel da pagina de pos-pago - velho, e que o
cliente nem ve - preencheu o buraco: o Familia Plus gravado a R$ 284,99
(a TIM cobra 264,99), o Familia e o VIP sem franquia, o Black a 70GB (a
pagina dele publica 80). 156 linhas nas 20 pracas, e a mensagem do dia
noticiou o Familia Plus como reajuste. O coletor foi consertado no mesmo
dia (o card novo e lido pelo no do JSON, e o carrossel nao tapa mais a
pagina que falha); a coleta avulsa grava a leitura certa do dia. Sobram
as 156 linhas do carrossel, que este script apaga - com o ok de quem le.

CADA LINHA DA TABELA E UM CONJUNTO, pela fonte gravada no bruto: operadora,
dia, a pagina que o coletor anotou no bruto, e QUANTAS se espera - contado
no dado publicado antes de escrever. O "bruto" diz de onde a linha veio, e
e por ele que o filtro separa o carrossel do que a hub e as paginas dos
planos gravaram no mesmo dia.

Sem --apagar, so conta. Com --apagar, apaga e confere: o contado tem de
ser o esperado, o apagado tem de ser o contado, e depois nao pode sobrar
nenhuma. Qualquer diferenca para tudo, alto, antes ou depois.

Uso: python apagar_capturas.py [--apagar]   (precisa dos segredos do Supabase)
"""
import collections
import sys
import urllib.parse

from corrigir_nomes import _pedido

# (operadora, dia, pagina gravada no bruto, quantas se espera)
APAGAR = [
    ("TIM", "2026-11-27", "pos-pago", 156),
]


def filtro(c):
    u"""Os tres campos SEMPRE: um DELETE sem filtro no PostgREST apaga a
    tabela inteira."""
    operadora, dia, pagina, _n = c
    q = urllib.parse.quote
    if not (operadora and dia and pagina):
        raise ValueError("filtro incompleto: %r" % (c,))
    return ("operadora=eq.%s&data_captura=eq.%s&%s=eq.%s"
            % (q(operadora), q(dia), q("bruto->>pagina", safe=""), q(pagina)))


def listar(c):
    return _pedido("GET", "capturas?%s&select=id,nome_oferta,preco_promocional,"
                          "franquia_anunciada_gb,praca&limit=5000" % filtro(c))


def apagar(c):
    return len(_pedido("DELETE", "capturas?%s&select=id" % filtro(c)))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gravar = "--apagar" in argv
    contados = []
    for c in APAGAR:
        linhas = listar(c)
        contados.append(len(linhas))
        print("%s %s pagina=%s: %d linha(s), esperadas %d"
              % (c[0], c[1], c[2], len(linhas), c[3]))
        por_nome = collections.Counter((l["nome_oferta"], l["preco_promocional"],
                                        l["franquia_anunciada_gb"]) for l in linhas)
        for (nome, preco, gb), n in sorted(por_nome.items(), key=str):
            print("   %3d  %-28s R$ %s  %s GB" % (n, nome, preco, gb))
    if any(n != c[3] for c, n in zip(APAGAR, contados)):
        print("PAREI: o contado nao e o esperado - nada foi apagado")
        return 1
    if not gravar:
        print("so contei - para apagar, --apagar")
        return 0
    for c, n in zip(APAGAR, contados):
        feitas = apagar(c)
        if feitas != n:
            print("PAREI: %s %s - contei %d e apaguei %d" % (c[0], c[1], n, feitas))
            return 1
    sobrou = sum(len(listar(c)) for c in APAGAR)
    if sobrou:
        print("PAREI: depois de apagar ainda ha %d linha(s)" % sobrou)
        return 1
    print("apagado e conferido: %d linha(s), nenhuma sobrou" % sum(contados))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
