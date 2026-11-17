"""Exporta o banco para o JSON que a tela consome.

Roda depois da coleta. Le as capturas do Supabase e grava um arquivo que
o gerador da tela usa - assim a tela reflete o que esta gravado, e nao
uma coleta avulsa feita na mao.

Exporta a janela recente em vez da base inteira: a tela mostra evolucao,
nao arqueologia, e um arquivo que cresce para sempre acabaria pesando
mais que o navegador aguenta abrir.

Uso:
  python exportar.py --dias 90 --saida dados.json
"""

import argparse
import io
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coletores import armazenamento   # noqa: E402

CAMPOS = ("operadora,produto,praca,uf,data_captura,capturado_em,nome_oferta,"
          "destaque,chave,codigo_anatel,degrau_mbps,franquia_anunciada_gb,"
          "franquia_contratual_gb,preco_cheio,preco_promocional,"
          "fidelidade_meses,multa_fidelidade,taxa_instalacao,nivel_bundle,"
          "meses_desconto,preco_pos_promocao,"
          # a campanha explica por que o nome ou a franquia da oferta
          # mudou num punhado de dias: sem ela, o leitor ve um degrau na
          # serie e nao tem como saber que houve promocao
          "campanha,"
          # extraidos do jsonb, por nao terem coluna propria
          "assinatura_sva:bruto->>assinatura_sva,"
          # QUAL app vem junto. Sem isto a tela so sabe o NIVEL de bundle
          # e escreve "uma assinatura" em quatro ofertas que se
          # distinguem exatamente pelo app.
          "apps_rotulo:bruto->>apps_rotulo,"
          "apps:bruto->apps,"
          # e QUAL tier de cada app, quando a operadora declarou. O preco
          # avulso pertence ao tier, nao ao app: sem isto a tela mostraria
          # o preco de um plano que a oferta pode nao incluir.
          "apps_planos:bruto->apps_planos,"
          # A FRASE DA FONTE SOBRE VELOCIDADE, quando ela declara faixa e
          # nao degrau. O plano Max da Starlink perde o degrau_mbps de
          # proposito - "Ate mais de 400 Mbps" e faixa, e virava um ponto
          # falso de 400 no grafico -, e com isso ele aparecia na tela
          # sem velocidade NENHUMA. O coletor guardava a frase em bruto
          # desde 26/10/2026 e ninguem a exportava: campo gravado sem
          # leitor, que e o defeito que este projeto mais encontra.
          "velocidade_declarada:bruto->>velocidade_declarada")

PAGINA = 1000   # o PostgREST corta a resposta nesse tamanho


def exportar(dias):
    """As capturas da janela, na ordem (data, operadora, id).

    PAGINA PELA CHAVE, NAO POR OFFSET. Com offset, cada pagina pede ao
    banco a janela inteira ordenada - jsonb aberto em todas as linhas - e
    joga fora o que vem antes do offset: 82 paginas, 82 vezes a tabela. O
    custo cresce com o quadrado da serie. Em 17/11/2026, com ~84 mil
    capturas, uma pagina passou do statement_timeout (HTTP 500, 57014) e
    o painel ficou no dia 16; a mesma consulta levava de 41 a 81 s nos
    dias anteriores, e a janela de 90 dias ainda estava pela metade.

    Pela chave, cada pagina comeca onde a anterior parou (id > ultimo),
    pelo indice da chave primaria, e o banco so abre as mil linhas que
    devolve. A ordem que a tela recebe e refeita aqui, com o id como
    desempate - a mesma ordem total que o banco devolvia.
    """
    desde = (date.today() - timedelta(days=dias)).isoformat()
    tudo, ultimo = [], 0
    while True:
        linhas, erro = armazenamento.consultar(
            "capturas?data_captura=gte.%s&id=gt.%d&select=id,%s"
            "&order=id.asc&limit=%d" % (desde, ultimo, CAMPOS, PAGINA))
        if erro:
            return None, erro
        # so a pagina VAZIA encerra: se o servidor cortar abaixo de
        # PAGINA, "veio menos que o pedido" pararia no meio, calado
        if not linhas:
            break
        if linhas[-1]["id"] <= ultimo:
            return None, "a chave nao avancou depois do id %d" % ultimo
        tudo.extend(linhas)
        ultimo = linhas[-1]["id"]
    tudo.sort(key=lambda l: (l["data_captura"], l["operadora"], l["id"]))
    for l in tudo:
        del l["id"]
    return tudo, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=90)
    ap.add_argument("--saida", default="dados.json")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    linhas, erro = exportar(a.dias)
    if erro:
        print("FALHOU: %s" % erro)
        return 1
    if not linhas:
        print("nenhuma captura nos ultimos %d dias" % a.dias)
        return 1

    io.open(a.saida, "w", encoding="utf-8").write(
        json.dumps(linhas, ensure_ascii=False))

    dias = sorted({l["data_captura"] for l in linhas})
    ops = sorted({l["operadora"] for l in linhas})
    print("exportado: %s" % a.saida)
    print("  %d capturas | %d dia(s) | %d operadoras" % (len(linhas), len(dias), len(ops)))
    print("  periodo: %s a %s" % (dias[0], dias[-1]))
    print("  operadoras: %s" % ", ".join(ops))
    return 0


if __name__ == "__main__":
    sys.exit(main())
