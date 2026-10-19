# -*- coding: utf-8 -*-
"""A coleta de hoje ja aconteceu? Imprime "sim" ou "nao".

POR QUE EXISTE. O agendamento do GitHub nao cumpre horario: medido em
sete dias, o evento chegou entre 3,5 e 9,6 horas atrasado, e numa
segunda-feira a mensagem saiu as 16h45. O atraso esta no GATILHO, nao na
fila de maquinas - o run comeca no mesmo minuto em que e criado.

Como o atraso varia por evento, a rotina passa a ter varios
agendamentos ao longo da madrugada em vez de um. A primeira que o GitHub
disparar faz o trabalho; as outras perguntam aqui, ouvem "sim" e
encerram em segundos.

Isso so e seguro porque a resposta vem do BANCO e nao de um arquivo de
estado: o registro de coleta do dia e a mesma fonte que o aviso diario
usa para dizer se o robo rodou. Duas rodadas simultaneas tambem nao
quebram nada - a gravacao e append-only com indice unico, e o concurrency
do workflow ja impede a sobreposicao.

QUANDO NAO DA PARA SABER, A RESPOSTA E "nao". Banco fora do ar, segredo
ausente, rede caida: nesses casos vale coletar de novo. Pular a coleta
por nao conseguir perguntar seria perder o dia inteiro por causa de uma
consulta.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
API = "/rest/v1/"

# Quantas operadoras precisam ter registro para o dia contar como
# coletado. Abaixo disto a rodada anterior morreu no meio, e a proxima
# tentativa tem o que fazer.
MINIMO = 5


def main():
    hoje = datetime.now(BRT).date().isoformat()
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not chave:
        print("nao")
        sys.stderr.write("sem credencial para perguntar: vale coletar\n")
        return 0

    caminho = ("coletas?data_captura=eq.%s&select=operadora,sucesso" % hoje)
    req = urllib.request.Request(url + API + caminho)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            linhas = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print("nao")
        sys.stderr.write("nao deu para perguntar (%s): vale coletar\n" % e)
        return 0

    ok = {l["operadora"] for l in linhas if l.get("sucesso")}
    sys.stderr.write("%s: %d operadora(s) com coleta ok\n" % (hoje, len(ok)))
    print("sim" if len(ok) >= MINIMO else "nao")
    return 0


if __name__ == "__main__":
    sys.exit(main())
