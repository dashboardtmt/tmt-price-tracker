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
          "meses_desconto,preco_pos_promocao")

PAGINA = 1000   # o PostgREST limita a resposta; pagina para nao truncar calado


def exportar(dias):
    desde = (date.today() - timedelta(days=dias)).isoformat()
    campos = CAMPOS
    # campo novo no codigo chega antes do ALTER TABLE: pedi-lo antes da hora
    # derrubaria a exportacao e a tela ficaria congelada no dia anterior
    if armazenamento.tem_coluna("assinatura_sva"):
        campos += ",assinatura_sva"
    tudo, inicio = [], 0
    while True:
        filtro = ("capturas?data_captura=gte.%s&select=%s"
                  "&order=data_captura.asc,operadora.asc"
                  "&limit=%d&offset=%d" % (desde, campos, PAGINA, inicio))
        linhas, erro = armazenamento.consultar(filtro)
        if erro:
            return None, erro
        if not linhas:
            break
        tudo.extend(linhas)
        if len(linhas) < PAGINA:
            break
        inicio += PAGINA
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
