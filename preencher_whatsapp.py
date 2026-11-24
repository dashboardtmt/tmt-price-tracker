# -*- coding: utf-8 -*-
u"""Preenche o WhatsApp incluso nas capturas de 24/11/2026, ja gravadas.

POR QUE EXISTE. O campo whatsapp (decisao 124) nasce na coleta de 25/11.
Quem le pediu para ver ja: "pode colocar agr". As linhas de 24/11 foram
coletadas antes do campo existir; este script grava nelas o que foi
MEDIDO nas paginas nesse mesmo dia, com o detector de producao
(coletores/apps.whatsapp_incluso) rodado contra as paginas de cada
operadora:

  Claro    controle, movel (pos) e prepago (Prezao)  - "WhatsApp ilimitado"
  TIM      movel (pos)        - "apps sem gastar internet do plano: WhatsApp"
  NuCel    controle           - "WhatsApp e App do Nu a vontade"

Vivo, TIM Controle e TIM pre nao citam WhatsApp como beneficio, e nao
recebem nada. So o dia 24/11: os anteriores nao foram medidos, e nao se
grava o que nao se mediu.

SO DENTRO DO BRUTO, so a chave whatsapp, e so onde ela ainda nao existe.
Sem --aplicar, so conta.

Uso: python preencher_whatsapp.py [--aplicar]   (precisa dos segredos)
"""
import json
import sys
import urllib.parse
import urllib.request

from coletores import armazenamento

DIA = "2026-11-24"
MEDIDO = [("Claro", ("controle", "movel", "prepago")),
          ("TIM", ("movel",)),
          ("NuCel", ("controle",))]


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


def linhas(operadora, produtos):
    q = ("capturas?data_captura=eq.%s&operadora=eq.%s&produto=in.(%s)"
         "&select=id,bruto&limit=5000"
         % (DIA, urllib.parse.quote(operadora), ",".join(produtos)))
    return _pedido("GET", q)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    gravar = "--aplicar" in argv
    alvo = []
    for operadora, produtos in MEDIDO:
        ls = [l for l in linhas(operadora, produtos)
              if (l.get("bruto") or {}).get("whatsapp") is None]
        print("%-6s %-26s %4d linha(s) sem o campo"
              % (operadora, ",".join(produtos), len(ls)))
        alvo += ls
    print("total: %d" % len(alvo))
    if not gravar:
        print("so contei - para gravar, --aplicar")
        return 0
    feitas = 0
    for l in alvo:
        bruto = dict(l["bruto"] or {}, whatsapp=True)
        r = _pedido("PATCH", "capturas?id=eq.%d&select=id" % l["id"],
                    {"bruto": bruto})
        if len(r) != 1:
            print("PAREI na linha %s: alterei %d" % (l["id"], len(r)))
            return 1
        feitas += 1
    sobra = sum(len([x for x in linhas(o, p)
                     if (x.get("bruto") or {}).get("whatsapp") is None])
                for o, p in MEDIDO)
    if sobra:
        print("PAREI: ainda ha %d linha(s) sem o campo" % sobra)
        return 1
    print("gravado e conferido: %d linha(s)" % feitas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
