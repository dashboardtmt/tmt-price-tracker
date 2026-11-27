# -*- coding: utf-8 -*-
u"""Sonda de pagina: o que o servidor do GitHub recebe de uma URL.

POR QUE EXISTE. Em 27/11/2026 a coleta das 06:00 nao leu nenhum card das
paginas do TIM Black, do TIM Black Familia e da Ultrafibra nas 20 pracas -
e daqui, minutos depois, as mesmas tres paginas davam 4, 6 e 8 cards. O
ensaio de 26/11 as 17:27 (horario de Brasilia) ainda lia os cards no
GitHub; o das 17:29 ja nao lia, com os dois leitores falhando juntos sobre
a mesma pagina. O aviso so dizia "nenhum card reconhecido", e o que a
pagina trazia no lugar dos cards so o servidor do GitHub via.

O QUE FAZ. Busca cada URL com o navegador e o buscar() do proprio
coletor - os mesmos cabecalhos e o mesmo cookie da coleta -, guarda o
corpo de cada resposta numa pasta e imprime um resumo: status, tamanho,
titulo, as tags de componente mais frequentes e a contagem do padrao
dado. A pasta sobe como artefato do workflow "Sonda de pagina".

Nao grava nada no banco, nao manda mensagem, nao mexe na tela.

Uso:
    python ferramentas/sonda_pagina.py --coletor tim --pasta .sonda URL [URL...]
    python ferramentas/sonda_pagina.py --coletor tim --padrao "<tim-card-pricing-offer" URL
"""
import argparse
import collections
import hashlib
import importlib
import io
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def resumo(url, status, corpo, padrao):
    titulo = re.search(r"<title[^>]*>(.*?)</title>", corpo or "", re.S | re.I)
    tags = collections.Counter(re.findall(r"<([a-z][a-z0-9]*-[\w-]+)", corpo or ""))
    return {
        "url": url,
        "status": status,
        "bytes": len((corpo or "").encode("utf-8")),
        "titulo": re.sub(r"\s+", " ", titulo.group(1)).strip()[:160] if titulo else None,
        "padrao": padrao,
        "ocorrencias_do_padrao": (corpo or "").count(padrao) if padrao else None,
        "tags_de_componente": tags.most_common(25),
        "inicio": re.sub(r"\s+", " ", (corpo or "")[:400]),
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("urls", nargs="+")
    p.add_argument("--coletor", required=True,
                   help="modulo de coletores/ cujo navegador() e buscar() usar")
    p.add_argument("--pasta", default=".sonda")
    p.add_argument("--padrao", default=None,
                   help="trecho de texto a contar em cada corpo")
    a = p.parse_args(argv)

    if not re.match(r"^[a-z_]+$", a.coletor):
        raise SystemExit("coletor invalido: %r" % a.coletor)
    mod = importlib.import_module("coletores." + a.coletor)
    op = mod.navegador()
    os.makedirs(a.pasta, exist_ok=True)
    saida = []
    for url in a.urls:
        status, corpo = mod.buscar(op, url)
        nome = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] + ".html"
        with io.open(os.path.join(a.pasta, nome), "w", encoding="utf-8") as f:
            f.write(corpo or "")
        r = resumo(url, status, corpo, a.padrao)
        r["arquivo"] = nome
        saida.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    with io.open(os.path.join(a.pasta, "resumo.json"), "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
