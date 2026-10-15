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
          "apps_planos:bruto->apps_planos")

def exportar(dias):
    desde = (date.today() - timedelta(days=dias)).isoformat()
    # a paginacao mora em armazenamento: o aviso diario precisava da mesma
    # coisa e tinha ficado sem, trazendo so as primeiras mil capturas
    return armazenamento.consultar_tudo(
        "capturas?data_captura=gte.%s&select=%s"
        "&order=data_captura.asc,operadora.asc" % (desde, CAMPOS))


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
