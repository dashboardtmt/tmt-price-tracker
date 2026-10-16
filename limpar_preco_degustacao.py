# -*- coding: utf-8 -*-
"""Apaga as tres capturas que gravaram o preco do Disney+ como preco do plano.

O QUE SAO. Em 07/10/2026, tres cards de Claro Controle em Porto Alegre
foram gravados a R$ 24,60. A serie dessas ofertas mostra R$ 99,90,
R$ 69,90 e R$ 59,90 em todos os outros quinze dias do historico - so
naquele dia caiu, e no dia seguinte voltou.

R$ 24,60 e o preco avulso do Disney+, que a propria Claro cita no card:
"Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes". A leitura
pegava o primeiro "R$" do texto e naquele dia a frase do beneficio veio
antes do preco do plano no markup.

Nao e desconto nem promocao: e preco de outra coisa. Preco de beneficio
nao e preco de plano, e linha inventada nao fica no historico.

O coletor ja foi corrigido - procura o preco no texto sem as frases de
degustacao. Isto limpa o que ele gravou antes.

O FILTRO E EXATO: data, operadora, produto, praca e o valor. Nenhuma
outra linha pode casar, e o script conta antes e confere depois.

E DESCARTAVEL: depois de rodar, apagar este arquivo e o workflow.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "/rest/v1/"
FILTRO = ("capturas?data_captura=eq.2026-10-07&operadora=eq.Claro"
          "&produto=eq.controle&praca=eq.Porto%20Alegre%2FRS"
          "&preco_promocional=eq.24.60")


def _config():
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not chave:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SECRET_KEY ausentes.")
    return url, chave


def _pedir(url, chave, caminho, metodo="GET"):
    req = urllib.request.Request(url + API + caminho, method=metodo)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    if metodo == "DELETE":
        req.add_header("Prefer", "return=representation")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            corpo = r.read().decode("utf-8", "replace")
            return r.status, json.loads(corpo) if corpo.strip() else []
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]


def main():
    url, chave = _config()
    aplicar = "--aplicar" in sys.argv

    st, linhas = _pedir(url, chave, FILTRO + "&select=id,nome_oferta,"
                                              "destaque,preco_promocional")
    if st not in (200, 206):
        print("FALHOU a leitura: HTTP %s %s" % (st, linhas))
        return 1
    print("linhas que casam o filtro: %d" % len(linhas))
    for l in linhas:
        print("   id=%s  %-26s %-8s R$ %s" % (
            l["id"], (l.get("nome_oferta") or "")[:26], l.get("destaque"),
            l.get("preco_promocional")))

    if len(linhas) > 5:
        print("MAIS LINHAS DO QUE O ESPERADO (3). Nada foi apagado - confira o filtro.")
        return 1
    if not linhas:
        print("nada a apagar: ou ja foi feito, ou o filtro nao casa mais")
        return 0
    if not aplicar:
        print("\nCONFERENCIA: nada foi apagado. Rode com --aplicar para apagar.")
        return 0

    st, apagadas = _pedir(url, chave, FILTRO, metodo="DELETE")
    if st not in (200, 204):
        print("FALHOU o delete: HTTP %s %s" % (st, apagadas))
        return 1
    print("\napagadas: %d" % (len(apagadas) if isinstance(apagadas, list) else 0))

    st, resta = _pedir(url, chave, FILTRO + "&select=id")
    print("releitura: %d linhas ainda casam o filtro" % len(resta))
    return 1 if resta else 0


if __name__ == "__main__":
    sys.exit(main())
