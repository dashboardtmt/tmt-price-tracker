"""Sobe o JSON da tela para o Supabase Storage, num bucket publico.

POR QUE ISTO EXISTE. A tela no Vercel tinha os dados embutidos no HTML,
entao cada coleta exigia um deploy novo - e deploy automatico exigiria um
token de API do Vercel, que o proprio Vercel se recusa a criar a partir
da sessao do CLI ("Cannot create tokens for this app"), e que portanto so
o usuario conseguiria gerar na mao.

Com o JSON no Storage, a pagina publicada busca o dado em tempo de
execucao. O site passa a refletir a coleta do dia sozinho, sem deploy,
sem token e sem passo manual - usando apenas as credenciais que o robo
ja tem.

O bucket e publico de leitura, o que e aceitavel pela mesma razao que a
tabela tem leitura liberada: preco de vitrine e informacao publica e nao
ha dado pessoal aqui. A gravacao continua exigindo a chave secreta.

Uso:
  python publicar_dados.py --dados dados.json
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

BUCKET = "tela"
ARQUIVO = "dados.json"


def _config():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not chave:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SECRET_KEY ausentes.")
    return url, chave


def _pedir(url, chave, caminho, metodo="GET", corpo=None, tipo="application/json"):
    req = urllib.request.Request(url + caminho, data=corpo, method=metodo)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    if corpo is not None:
        req.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def garantir_bucket(url, chave):
    """Cria o bucket se nao existir. Seguro de repetir todo dia."""
    status, corpo = _pedir(url, chave, "/storage/v1/bucket/" + BUCKET)
    if status == 200:
        return True, None
    status, corpo = _pedir(
        url, chave, "/storage/v1/bucket", "POST",
        json.dumps({"id": BUCKET, "name": BUCKET, "public": True}).encode())
    if status in (200, 201):
        return True, None
    # "already exists" em corrida com outra execucao nao e erro
    if "already exist" in corpo.lower():
        return True, None
    return False, "criar bucket: HTTP %s: %s" % (status, corpo[:200])


def subir(url, chave, dados_bytes):
    """Sobe por cima do arquivo anterior.

    Aqui sobrescrever e certo, ao contrario da tabela: este arquivo e uma
    copia derivada do banco, descartavel e regeravel. O append-only
    protege a captura, nao o seu retrato.
    """
    caminho = "/storage/v1/object/%s/%s" % (BUCKET, ARQUIVO)
    status, corpo = _pedir(url, chave, caminho, "POST", dados_bytes,
                           "application/json")
    if status in (200, 201):
        return True, None
    if status == 400 and "already exists" in corpo.lower():
        status, corpo = _pedir(url, chave, caminho, "PUT", dados_bytes,
                               "application/json")
        if status in (200, 201):
            return True, None
    return False, "HTTP %s: %s" % (status, corpo[:200])


def url_publica(url):
    return "%s/storage/v1/object/public/%s/%s" % (url, BUCKET, ARQUIVO)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="dados.json")
    a = ap.parse_args()

    url, chave = _config()
    bruto = io.open(a.dados, "rb").read()
    linhas = json.loads(bruto.decode("utf-8"))
    print("%s: %d ofertas, %d KB" % (a.dados, len(linhas), len(bruto) // 1024))

    ok, erro = garantir_bucket(url, chave)
    if not ok:
        print("FALHOU: %s" % erro)
        return 1

    ok, erro = subir(url, chave, bruto)
    if not ok:
        print("FALHOU ao subir: %s" % erro)
        return 1

    publica = url_publica(url)
    print("publicado em: %s" % publica)

    # Conferir que esta mesmo legivel sem credencial nenhuma, que e o
    # ponto de todo este arquivo existir.
    #
    # COM CACHE FURADO E COM REPETICAO. Em 13/10/2026 esta conferencia
    # devolveu 19.607 linhas logo apos subir 21.234 - era a copia da
    # vespera ainda no CDN, e a diferenca batia exatamente com as 1.627
    # capturas daquele dia. O arquivo estava certo; a leitura e que
    # chegou velha, e o job morreu depois de publicar.
    ultimo = None
    for tentativa in range(1, 4):
        if tentativa > 1:
            time.sleep(4 * (tentativa - 1))
        # parametro que muda a cada chamada: o CDN nao tem copia dessa URL
        req = urllib.request.Request(
            "%s?conferencia=%d" % (publica, int(time.time() * 1000)))
        req.add_header("Cache-Control", "no-cache")
        req.add_header("Pragma", "no-cache")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                devolta = json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            ultimo = "erro ao ler: %s" % e
            print("tentativa %d: %s" % (tentativa, ultimo))
            continue
        if len(devolta) == len(linhas):
            print("lido de volta sem credencial: %d ofertas%s"
                  % (len(devolta), "" if tentativa == 1
                     else " (na tentativa %d)" % tentativa))
            return 0
        ultimo = "subiu %d e voltou %d" % (len(linhas), len(devolta))
        print("tentativa %d: %s - pode ser cache, repetindo" % (tentativa, ultimo))

    print("FALHOU a conferencia depois de 3 tentativas: %s" % ultimo)
    print("  O arquivo PODE estar correto no Storage - confira antes de "
          "reprocessar, porque a publicacao em si deu certo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
