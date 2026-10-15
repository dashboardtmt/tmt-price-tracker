# -*- coding: utf-8 -*-
"""Recalcula o tier do app nas capturas antigas, lendo a fonte gravada.

POR QUE EXISTE. Ate 15/10/2026 o tier do app vinha de um padrao escrito
no dicionario do tracker: Netflix saia sempre como "Netflix (Padrao)" e
Spotify como "Spotify (Premium Individual)". Nenhuma operadora declara
isso. A oferta se chama "Vivo Pos com Netflix", o nome registrado na
Anatel e "VIVO POS COM NETFLIX" e o regulamento inteiro nao tem a palavra
Padrao, Premium nem anuncio - a Vivo pode estar dando qualquer um dos
tres planos, que custam de R$ 20,90 a R$ 59,90 avulsos. Era palpite com
cara de dado, e o preco de referencia na tela saia colado nele.

O coletor ja le o tier da fonte. Isto conserta o que ele gravou antes, e
preenche apps_planos nas linhas onde o tier ESTA declarado - Disney+
PADRAO e Spotify PREMIUM no registro da Anatel, YouTube Premium Lite no
nome da oferta - para a tela continuar mostrando o preco certo.

O QUE ELE FAZ E NAO FAZ. Reescreve dois campos derivados dentro do bruto:
apps_rotulo e apps_planos. Nao toca em preco, franquia, nome de oferta
nem em nada que tenha vindo da operadora. Nao apaga linha. Recalcula a
partir do que ja esta gravado - nenhuma requisicao a vitrine.

MODO PADRAO E CONFERIR. Sem argumento, le tudo, mostra o que mudaria e
escreve zero. Com --aplicar, grava.

E DESCARTAVEL: depois de rodar, apagar este arquivo e o workflow.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coletores import apps                                    # noqa: E402

API = "/rest/v1/"
PAGINA = 500

# De onde o tier pode sair, em ordem de confianca: o nome registrado na
# Anatel e o mais forte (e o que a operadora declarou a agencia), depois
# o nome na vitrine, depois o texto do card.
FONTES = ("nome_regulamento", "nome_oferta", "composicao", "bruto_texto",
          "aplicativos", "plano")


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


def _gravar(url, chave, ident, bruto):
    corpo = json.dumps({"bruto": bruto}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "%s%scapturas?id=eq.%d" % (url, API, ident), data=corpo, method="PATCH")
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:160]
    except Exception as e:
        return 0, str(e)[:160]


def recalcular(bruto, por_codigo=None):
    """(rotulo, planos) relidos da fonte, ou (None, None) se nao da.

    O registro da Anatel esta em metade das linhas, embora seja
    propriedade da OFERTA e nao da linha: a mesma oferta gravada em
    outra praca tem o mesmo registro. O por_codigo traz esse nome pelo
    codigo Anatel, para a linha que nao o guardou ser lida pela mesma
    fonte que as outras - em vez de perder um tier que a agencia
    declara.
    """
    lista = bruto.get("apps")
    if not lista:
        return None, None
    fontes = [bruto.get(k) for k in FONTES]
    if por_codigo and not bruto.get("nome_regulamento"):
        emprestado = por_codigo.get(bruto.get("codigo_anatel"))
        if emprestado:
            fontes.append(emprestado)
    return (apps.rotulo(lista, *fontes),
            apps.planos_dos_apps(lista, *fontes))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aplicar", action="store_true",
                   help="grava. Sem isto, so mostra o que mudaria.")
    args = p.parse_args()
    url, chave = _config()

    # ordem total: sem o id como critario a paginacao repete e perde
    # linhas, que foi o defeito que duplicou 273 linhas no export
    caminho = ("capturas?select=id,operadora,data_captura,bruto"
               "&bruto->>apps_rotulo=not.is.null&order=id.asc")

    linhas, inicio = [], 0
    while True:
        lote = _ler(url, chave, "%s&limit=%d&offset=%d" % (caminho, PAGINA, inicio))
        linhas.extend(lote)
        if len(lote) < PAGINA:
            break
        inicio += PAGINA
    print("linhas com app: %d" % len(linhas))

    # o nome registrado na Anatel, por codigo de oferta: e da oferta, nao
    # da linha, e serve para ler as linhas que nao o guardaram
    por_codigo = {}
    for x in linhas:
        b = x["bruto"] or {}
        cod, nome = b.get("codigo_anatel"), b.get("nome_regulamento")
        if cod and nome:
            por_codigo.setdefault(cod, nome)
    print("registros Anatel conhecidos: %d codigos" % len(por_codigo))

    campos = {}
    sem_apps = 0
    mudar, exemplos = [], {}
    for x in linhas:
        b = x["bruto"] or {}
        for k in FONTES:
            if b.get(k):
                campos[k] = campos.get(k, 0) + 1
        # linha gravada antes do campo "apps" existir: nao ha o que
        # recalcular, e apagar o rotulo dela seria perder dado bom
        if not b.get("apps"):
            sem_apps += 1
            continue
        rot, planos = recalcular(b, por_codigo)
        antes_rot = b.get("apps_rotulo")
        antes_planos = b.get("apps_planos")
        if rot == antes_rot and planos == antes_planos:
            continue
        mudar.append((x["id"], b, rot, planos))
        k = "%s -> %s" % (antes_rot, rot)
        if planos != antes_planos and rot == antes_rot:
            k = "%s (so apps_planos: %s -> %s)" % (rot, antes_planos, planos)
        exemplos[k] = exemplos.get(k, 0) + 1

    print("\nlinhas sem a lista de apps, intocadas: %d" % sem_apps)
    print("\nfontes de tier presentes no bruto:")
    for k in FONTES:
        print("   %-18s %d linhas" % (k, campos.get(k, 0)))

    print("\nmudancas (%d linhas):" % len(mudar))
    for k, n in sorted(exemplos.items(), key=lambda x: -x[1]):
        print("   %5d  %s" % (n, k))

    if not args.aplicar:
        print("\nCONFERENCIA: nada foi gravado. Rode com --aplicar para gravar.")
        return 0

    feitas, erros = 0, []
    for ident, b, rot, planos in mudar:
        novo = dict(b)
        novo["apps_rotulo"] = rot
        if planos:
            novo["apps_planos"] = planos
        else:
            novo.pop("apps_planos", None)
        st, msg = _gravar(url, chave, ident, novo)
        if st in (200, 204):
            feitas += 1
        else:
            erros.append("id=%s HTTP %s %s" % (ident, st, msg))
            if len(erros) > 20:
                break

    print("\ngravadas: %d de %d" % (feitas, len(mudar)))
    if erros:
        print("ERROS (%d primeiros):" % len(erros))
        for e in erros[:20]:
            print("   " + e)
        return 1

    # conferencia: reler e exigir que nada mais precise mudar
    linhas, inicio = [], 0
    while True:
        lote = _ler(url, chave, "%s&limit=%d&offset=%d" % (caminho, PAGINA, inicio))
        linhas.extend(lote)
        if len(lote) < PAGINA:
            break
        inicio += PAGINA
    resta = 0
    for x in linhas:
        b = x["bruto"] or {}
        if not b.get("apps"):
            continue
        rot, planos = recalcular(b, por_codigo)
        if rot != b.get("apps_rotulo") or planos != b.get("apps_planos"):
            resta += 1
    print("relido: %d linhas, %d ainda divergentes" % (len(linhas), resta))
    return 1 if resta else 0


if __name__ == "__main__":
    sys.exit(main())
