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
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

BUCKET = "tela"

# O ARQUIVO SOBE COMPRIMIDO, e isso nao e otimizacao: e o que faz ele
# caber. Ver compactar().
ARQUIVO = "dados.json.gz"

# O NOME ANTIGO, que agora recebe a placa. Ver corpo_da_placa().
ANTIGO = "dados.json"

# O TETO DO STORAGE no plano gratuito. Nao e nosso: o servidor devolve
# HTTP 400 com "413 Payload too large" acima disso, e foi assim que o
# dia 11/11/2026 descobriu o limite - depois de a mensagem e o PDF
# terem saido certos.
LIMITE_DO_STORAGE = 50 * 1024 * 1024


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


def compactar(bruto):
    """O MESMO JSON, EM GZIP - e a razao de ele nao ser mais o arquivo.

    Em 11/11/2026 o dado do dia chegou a 51.254 KB e o Storage recusou o
    upload: HTTP 400 com "413 Payload too large", porque o objeto passou
    dos 50 MB do plano. O job morreu DEPOIS de a mensagem e o PDF do dia
    terem saido certos, com o dado de hoje - entao o unico sintoma era a
    tela mostrando o retrato da vespera, sem nada na pagina dizendo
    isso. A serie crescia 1,16 MB por dia e um dia ia passar; o dia foi
    esse.

    COMPRIME 35 VEZES, e nao e sorte: a serie repete a mesma oferta em
    20 pracas por 43 dias. Medido no arquivo publicado de 10/11: 48,7 MB
    viraram 1,4 MB. Com isso o teto deixa de ser uma data no calendario
    - 33 KB por dia em vez de 1,16 MB.

    E E TAMBEM O QUE A PAGINA BAIXA. Antes o celular puxava os 48 MB
    inteiros a cada abertura, o que nenhuma linha de codigo dizia e
    ninguem tinha medido.
    """
    # mtime=0 ESCRITO, e nao herdado: o cabecalho do gzip tem um campo
    # de hora, e o padrao dele MUDOU DE VERSAO - ate o Python 3.12 e o
    # relogio da rodada, do 3.13 em diante e zero. O runner e 3.12 e a
    # maquina onde isto se desenvolve e 3.14: sem escrever, os dois
    # produziriam arquivos diferentes do mesmo dado, e o defeito so
    # apareceria no servidor.
    #
    # COM A HORA DENTRO, dois dias de dado IDENTICO sobem bytes
    # diferentes, e o ETag do objeto passa a responder "o relogio
    # andou" em vez de "o dado mudou". Foi pelo ETag e pelo
    # Last-Modified que se viu, em 11/11/2026, que a publicacao
    # daquele dia nunca tinha acontecido.
    return gzip.compress(bruto, 6, mtime=0)


def descompactar(dados_bytes):
    """O caminho de volta, usado pela conferencia sem credencial."""
    return json.loads(gzip.decompress(dados_bytes).decode("utf-8", "replace"))


def cabe(dados_bytes):
    """Falha ANTES de subir, com o numero e o limite escritos.

    O 413 do servidor chega como "HTTP 400: {...}" e levou uma leitura de
    log para virar "o arquivo passou de 50 MB". Comprimido, chegar aqui
    quer dizer que a serie cresceu de verdade - e ai a resposta e cortar
    a janela do exportar, nao comprimir mais.
    """
    if len(dados_bytes) <= LIMITE_DO_STORAGE:
        return True, None
    return False, ("%d KB passa do limite de %d KB do Storage. Comprimido "
                   "ja, o caminho agora e reduzir a janela em exportar.py "
                   "(--dias)." % (len(dados_bytes) // 1024,
                                  LIMITE_DO_STORAGE // 1024))


def corpo_da_placa():
    """O QUE PASSA A MORAR NO NOME ANTIGO, e por que nao e o dado.

    dados.json continuou respondendo depois que o upload falhou, servindo
    o retrato do dia anterior - uma URL viva com dado velho e a forma
    mais caseira de mentir que este projeto conhece. Apagar o objeto
    resolveria, mas 404 nao diz o que aconteceu.

    ENTAO O LUGAR DIZ QUE MUDOU DE LUGAR. E de proposito que isto NAO e
    uma lista: todo leitor daqui espera um array e vai falhar na linha
    seguinte, em vez de mostrar um dia velho como se fosse hoje.
    """
    return json.dumps({
        "este_arquivo_mudou_de_lugar": ARQUIVO,
        "desde": "2026-11-11",
        "motivo": "sem compressao a serie passou dos 50 MB do Storage",
    }, ensure_ascii=False).encode("utf-8")


def subir(url, chave, nome, dados_bytes, tipo="application/json"):
    """Sobe por cima do arquivo anterior.

    Aqui sobrescrever e certo, ao contrario da tabela: este arquivo e uma
    copia derivada do banco, descartavel e regeravel. O append-only
    protege a captura, nao o seu retrato.
    """
    caminho = "/storage/v1/object/%s/%s" % (BUCKET, nome)
    status, corpo = _pedir(url, chave, caminho, "POST", dados_bytes, tipo)
    if status in (200, 201):
        return True, None
    if status == 400 and "already exists" in corpo.lower():
        status, corpo = _pedir(url, chave, caminho, "PUT", dados_bytes, tipo)
        if status in (200, 201):
            return True, None
    return False, "HTTP %s: %s" % (status, corpo[:200])


def url_publica(url, nome=None):
    return "%s/storage/v1/object/public/%s/%s" % (url, BUCKET, nome or ARQUIVO)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default="dados.json")
    a = ap.parse_args()

    url, chave = _config()
    with io.open(a.dados, "rb") as f:
        bruto = f.read()
    linhas = json.loads(bruto.decode("utf-8"))
    comprimido = compactar(bruto)
    print("%s: %d ofertas, %d KB -> %d KB comprimido"
          % (a.dados, len(linhas), len(bruto) // 1024,
             len(comprimido) // 1024))

    ok, erro = cabe(comprimido)
    if not ok:
        print("FALHOU antes de subir: %s" % erro)
        return 1

    ok, erro = garantir_bucket(url, chave)
    if not ok:
        print("FALHOU: %s" % erro)
        return 1

    ok, erro = subir(url, chave, ARQUIVO, comprimido, "application/gzip")
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
                devolta = descompactar(r.read())
        except Exception as e:
            ultimo = "erro ao ler: %s" % e
            print("tentativa %d: %s" % (tentativa, ultimo))
            continue
        if len(devolta) == len(linhas):
            print("lido de volta sem credencial: %d ofertas%s"
                  % (len(devolta), "" if tentativa == 1
                     else " (na tentativa %d)" % tentativa))
            # SO DEPOIS DE O NOVO ESTAR CONFIRMADO. Trocar o antigo pela
            # placa antes disso deixaria a tela sem dado nenhum se o
            # upload de cima tivesse falhado.
            ok, erro = subir(url, chave, ANTIGO, corpo_da_placa())
            print("placa em %s: %s" % (ANTIGO, "ok" if ok else erro))
            return 0
        ultimo = "subiu %d e voltou %d" % (len(linhas), len(devolta))
        print("tentativa %d: %s - pode ser cache, repetindo" % (tentativa, ultimo))

    print("FALHOU a conferencia depois de 3 tentativas: %s" % ultimo)
    print("  O arquivo PODE estar correto no Storage - confira antes de "
          "reprocessar, porque a publicacao em si deu certo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
