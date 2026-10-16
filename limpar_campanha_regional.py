# -*- coding: utf-8 -*-
"""Tira o marcador de regiao do campo campanha nas linhas ja gravadas.

O QUE E. O catalogo da Vivo traz um campo "regional" que diz ONDE a
oferta vale: "nacional", ou o nome da regiao. O coletor despejava isso no
campo campanha. Enquanto campanha nao tinha dono nem saia no export, nao
incomodava ninguem.

Desde 16/10/2026 campanha tem dono: o banner de promocao que a vitrine
cola no card, como o "Claro Day". E o campo passou a sair no export, ou
seja, chega na tela. Com o marcador de regiao junto, o campo diz que a
Vivo roda uma campanha chamada "nacional" todos os dias do ano.

Nao e dado errado - e dado no campo errado. O coletor ja foi corrigido e
grava em "regional". Isto limpa o que ele gravou antes: tira o valor de
campanha nas linhas em que ele e so marcador de regiao, e preserva o
valor em "regional" dentro do bruto, para nao perder a informacao.

O FILTRO E ESTREITO: so linhas da Vivo cujo campanha NAO e campanha de
verdade. Qualquer valor que nao seja marcador de regiao fica onde esta.

MODO PADRAO E CONFERIR. Com --aplicar, grava.
E DESCARTAVEL: depois de rodar, apagar este arquivo e o workflow.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "/rest/v1/"
PAGINA = 500

# O que o catalogo da Vivo poe em "regional". Qualquer outra coisa no
# campo campanha e campanha de verdade e nao se toca.
MARCADORES = {"nacional", "regional", "sudeste", "sul", "nordeste",
              "norte", "centro-oeste", "centro oeste"}


def _config():
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not chave:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SECRET_KEY ausentes.")
    return url, chave


def _ler(url, chave, caminho):
    req = urllib.request.Request(url + API + caminho)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _gravar(url, chave, ident, corpo):
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "%s%scapturas?id=eq.%d" % (url, API, ident), data=dados, method="PATCH")
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:160]


def so_marcador(campanha):
    """O valor e apenas marcador de regiao, sem campanha de verdade?"""
    if not campanha:
        return False
    return all((str(x).strip().lower() in MARCADORES) for x in campanha)


def carregar(url, chave):
    caminho = ("capturas?select=id,operadora,campanha,bruto"
               "&campanha=not.is.null&order=id.asc")
    linhas, inicio = [], 0
    while True:
        lote = _ler(url, chave, "%s&limit=%d&offset=%d" % (caminho, PAGINA, inicio))
        linhas.extend(lote)
        if len(lote) < PAGINA:
            break
        inicio += PAGINA
    return linhas


def main():
    url, chave = _config()
    aplicar = "--aplicar" in sys.argv
    linhas = carregar(url, chave)
    print("linhas com campanha preenchida: %d" % len(linhas))

    por_valor = {}
    for l in linhas:
        k = str(l.get("campanha"))
        por_valor[k] = por_valor.get(k, 0) + 1
    print("valores encontrados:")
    for k, n in sorted(por_valor.items(), key=lambda x: -x[1]):
        marca = "  <- marcador de regiao, vai sair" if so_marcador(
            json.loads(k.replace("'", '"'))) else "  (campanha de verdade, fica)"
        print("   %-24s %5d%s" % (k, n, marca))

    mudar = [l for l in linhas if so_marcador(l.get("campanha"))]
    print("\nlinhas a limpar: %d" % len(mudar))
    if not aplicar:
        print("\nCONFERENCIA: nada foi gravado. Rode com --aplicar para gravar.")
        return 0

    feitas, erros = 0, []
    for l in mudar:
        # o valor nao se perde: fica em "regional" dentro do bruto
        bruto = dict(l.get("bruto") or {})
        bruto["regional"] = l.get("campanha")
        st, msg = _gravar(url, chave, l["id"],
                          {"campanha": None, "bruto": bruto})
        if st in (200, 204):
            feitas += 1
        else:
            erros.append("id=%s HTTP %s %s" % (l["id"], st, msg))
            if len(erros) > 20:
                break
    print("\ngravadas: %d de %d" % (feitas, len(mudar)))
    if erros:
        print("ERROS:")
        for e in erros[:20]:
            print("   " + e)
        return 1

    resta = [l for l in carregar(url, chave) if so_marcador(l.get("campanha"))]
    print("relido: %d linhas ainda com marcador de regiao em campanha" % len(resta))
    return 1 if resta else 0


if __name__ == "__main__":
    sys.exit(main())
