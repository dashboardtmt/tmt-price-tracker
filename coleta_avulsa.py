# -*- coding: utf-8 -*-
u"""Coleta avulsa de UMA operadora, gravando so as ofertas pedidas, no dia
de hoje.

POR QUE EXISTE. Em 25/11/2026 o coletor da Claro passou a ler os cinco
Prezoes tematicos (Kwai, TikTok, Uber, Shopee e Free Fire, R$ 34,99 a
R$ 35), que nunca tinham sido coletados. O conserto entrou depois da
coleta das 6h, e a proxima so rodaria no dia seguinte; quem le pediu para
ver no mesmo dia. O disparo manual da rotina diaria nao serve: recoleta
as nove operadoras e manda a mensagem do dia de novo.

O QUE FAZ: roda o coletor de producao da operadora nas pracas dela, como
a rotina diaria, e grava SO as ofertas do produto pedido cujo nome comeca
por um dos prefixos dados. Nao registra rodada na tabela de coletas (o
dia ja tem a sua, e ja_coletou conta coletores registrados), nao manda
mensagem e nao mexe na tela - o dado publicado so muda na proxima
"Atualizar a tela". Oferta que ja esta gravada hoje com a mesma chave e
ignorada pelo banco, como na rotina.

Sem --gravar, so mostra o que gravaria.

Uso: python coleta_avulsa.py OPERADORA PRODUTO PREFIXO [PREFIXO ...] [--gravar]
"""
import sys

import robo
from coletores import armazenamento


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gravar = "--gravar" in argv
    args = [a for a in argv if a != "--gravar"]
    if len(args) < 3:
        print(__doc__)
        return 2
    nome, produto, prefixos = args[0], args[1], [p.lower() for p in args[2:]]
    modulo = robo.COLETORES[nome]
    pracas = robo.pracas_da_operadora(nome, modulo)
    escolhidas, avisos = [], []
    for p in pracas:
        d, erro = robo._uma_praca(modulo, p)
        rot = robo.rotulo(p)
        if erro or not d:
            avisos.append("%s: erro %s" % (rot, erro))
            continue
        avisos.extend("%s: %s" % (rot, a) for a in d["avisos"])
        achadas = [o for o in d["ofertas"] if o.get("produto") == produto
                   and any((o.get("nome_oferta") or "").lower().startswith(x) for x in prefixos)]
        escolhidas.extend(achadas)
        print("%-22s %d oferta(s) pedida(s)" % (rot, len(achadas)), flush=True)
    for a in avisos[:40]:
        print("   aviso: " + a)
    nomes = sorted(set((o["nome_oferta"], o.get("preco_promocional")) for o in escolhidas))
    for n, pr in nomes:
        print("  %-30s R$ %s" % (n, pr))
    print("total: %d oferta(s) em %d praca(s)" % (
        len(escolhidas), len(set(o["praca"] for o in escolhidas))))
    if not gravar:
        print("so mostrei - para gravar, --gravar")
        return 0
    if not escolhidas:
        print("PAREI: nada a gravar")
        return 1
    n, erro = armazenamento.gravar_capturas(escolhidas)
    if erro:
        print("PAREI: a gravacao falhou: %s" % erro)
        return 1
    print("gravadas: %d (as que ja existiam hoje com a mesma chave o banco ignora)" % n)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
