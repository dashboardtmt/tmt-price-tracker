# -*- coding: utf-8 -*-
"""Tira o banner "Claro Day" do nome das ofertas ja gravadas.

O QUE ACONTECEU. De 06 a 12/10/2026 a Claro rodou o "Claro Day" e colou o
banner na frente do card. O nome da oferta e lido do comeco do texto,
entao 834 capturas foram gravadas como "Claro Day Claro Pos" e "Claro Day
Claro Controle".

A oferta e a mesma. Com outro nome ela vira outra identidade: a serie
morre no dia 06, nasce uma nova, morre no dia 12 e a antiga ressuscita.
Foi a maior fonte de buraco no historico - 420 dias-serie faltando em
Claro movel e 287 em Claro controle, com a coleta funcionando nos dois
casos. Na tabela, a mesma oferta aparecia duas vezes com nomes diferentes.

O coletor ja foi corrigido: o banner sai do nome e vai para o campo
"campanha", que existe no esquema desde o inicio e nunca tinha sido
preenchido. Isto arruma o que ele gravou antes - e a campanha deixa de
ser um estrago para virar dado: da para medir quantos dias por mes cada
operadora roda promocao.

O QUE ELE FAZ E NAO FAZ. Troca nome_oferta e preenche campanha. Nao toca
em preco, franquia, praca nem data. Nao apaga linha. Nao inventa nome: o
nome novo e um pedaco literal do que ja estava gravado.

CONFERIDO ANTES: as 834 trocas nao criam nenhuma colisao no indice unico
do banco (data, operadora, produto, praca, chave, nome, codigo Anatel).
Nos sete dias de campanha os dois nomes nunca coexistem na mesma praca.

MODO PADRAO E CONFERIR. Com --aplicar, grava.
E DESCARTAVEL: depois de rodar, apagar este arquivo e o workflow.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "/rest/v1/"
PAGINA = 500

# O nome de verdade comeca na marca seguida de um produto que a Claro
# vende. O que vier antes disso e banner de campanha. Nome que ja comeca
# na marca nao tem nada antes e nunca vira campanha.
PRODUTO = re.compile(
    r"\bClaro\s+(?:P[óo]s|Controle|Multi|Fibra|Pr[ée]|Prez[ãa]o|Flex)\b", re.I)


def separar(nome):
    """(nome limpo, campanha ou None)."""
    m = None
    for m in PRODUTO.finditer(nome or ""):
        pass                      # fica com a ULTIMA ocorrencia
    if not m or m.start() == 0:
        return nome, None
    return nome[m.start():].strip() or nome, (nome[:m.start()].strip(" -|") or None)


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


def carregar(url, chave):
    caminho = ("capturas?select=id,data_captura,operadora,produto,praca,chave,"
               "nome_oferta,codigo_anatel,campanha"
               "&operadora=eq.Claro&order=id.asc")
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
    print("capturas da Claro: %d" % len(linhas))

    mudar = []
    for l in linhas:
        novo, camp = separar(l.get("nome_oferta"))
        if novo != l.get("nome_oferta") or (camp and camp != l.get("campanha")):
            mudar.append((l, novo, camp))
    print("linhas que mudam: %d" % len(mudar))

    # Colisao no indice unico do banco. Se o nome novo ja existe para a
    # mesma data/praca/chave/codigo, o UPDATE e recusado - e o certo e
    # nao tentar, porque ai sao duas linhas para a mesma coisa.
    indice = set()
    for l in linhas:
        indice.add((l["data_captura"], l["produto"], l["praca"], l["chave"],
                    l["nome_oferta"], l.get("codigo_anatel")))
    colisoes = []
    for l, novo, _c in mudar:
        k = (l["data_captura"], l["produto"], l["praca"], l["chave"], novo,
             l.get("codigo_anatel"))
        if k in indice:
            colisoes.append(k)
    print("colisoes no indice unico: %d" % len(colisoes))
    if colisoes:
        print("NAO VOU GRAVAR: renomear criaria linha duplicada.")
        for k in colisoes[:5]:
            print("   %s" % (k,))
        return 1

    campanhas = {}
    for _l, _n, c in mudar:
        if c:
            campanhas[c] = campanhas.get(c, 0) + 1
    print("campanhas extraidas: %s"
          % ", ".join("%s (%d)" % (k, v) for k, v in sorted(campanhas.items())))
    for l, novo, camp in mudar[:5]:
        print("   %s  %-28s -> %-20s campanha=%s"
              % (l["data_captura"], (l["nome_oferta"] or "")[:28], novo, camp))

    if not aplicar:
        print("\nCONFERENCIA: nada foi gravado. Rode com --aplicar para gravar.")
        return 0

    feitas, erros = 0, []
    for l, novo, camp in mudar:
        corpo = {"nome_oferta": novo}
        if camp:
            corpo["campanha"] = camp
        st, msg = _gravar(url, chave, l["id"], corpo)
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

    resta = [l for l in carregar(url, chave)
             if separar(l.get("nome_oferta"))[0] != l.get("nome_oferta")]
    print("relido: %d linhas ainda com banner no nome" % len(resta))
    return 1 if resta else 0


if __name__ == "__main__":
    sys.exit(main())
