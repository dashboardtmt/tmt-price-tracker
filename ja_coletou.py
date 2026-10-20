# -*- coding: utf-8 -*-
"""Decide se a coleta deve rodar AGORA. Imprime "sim" ou "nao".

O PROBLEMA. O agendamento do GitHub nao cumpre horario: medido em sete
dias, o evento chegou entre 3,5 e 9,6 horas atrasado, e numa
segunda-feira a mensagem do dia saiu as 16h45. O atraso esta no GATILHO,
nao na fila de maquinas - o run comeca no mesmo minuto em que e criado.

NAO DA PARA MANDAR O GITHUB DISPARAR AS 6H. Mas da para decidir quando a
coleta acontece, independente de quando o gatilho chega. A rotina tem
varios agendamentos espalhados pela madrugada e pela manha; cada um
pergunta aqui, e a resposta governa:

    ja coletou hoje?            -> nao (uma coleta por dia, e acabou)
    ainda e cedo demais?        -> nao (o dado da madrugada nao serve:
                                   a mensagem chegaria de madrugada)
    passou da hora limite?      -> sim, de qualquer jeito
    senao                       -> sim

Assim a coleta cai na PRIMEIRA oportunidade a partir da hora desejada, e
a mensagem chega logo depois. Os gatilhos que chegam cedo demais
encerram em segundos; os que chegam tarde pegam o trabalho.

POR QUE UMA JANELA, E NAO UM HORARIO. Horario exato exigiria um gatilho
externo e confiavel, que hoje nao existe - o api/disparar.js esta pronto
para isso e so espera um token. Com o que ha, a janela e o mais proximo
de um compromisso que da para prometer: nao antes das 6h, e no pior caso
ate as 10h.

QUANDO NAO DA PARA SABER, A RESPOSTA E "sim". Banco fora do ar, segredo
ausente, rede caida: nesses casos vale coletar. Pular o dia por nao
conseguir perguntar seria perder o dia inteiro por causa de uma consulta.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, time as hora, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
API = "/rest/v1/"

# A coleta leva cerca de 50 minutos, e o aviso sai logo depois. Comecando
# as 6h, a mensagem chega perto das 7h - que e a hora pedida.
ABERTURA = hora(6, 0)

# Depois disto, coleta de qualquer jeito. Um dia sem dado e pior do que
# um dado que chegou tarde, e as 10h ja nao ha o que esperar.
LIMITE = hora(10, 0)

def _esperadas():
    """Quantos coletores a rodada tem.

    SAI DO ROBO, e nao de um numero copiado aqui: copia envelhece em
    silencio, e esta decide se o dia ja foi coletado. Coletor novo
    entrando no robo passaria a nao contar, e o dia fecharia faltando um.
    """
    from robo import COLETORES
    return len(COLETORES)


def _ja_coletou(hoje):
    """(a rodada de hoje fechou?, quantos coletores registraram).

    O SINAL E "REGISTROU", NAO "DEU CERTO". Cada coletor grava sua linha
    em "coletas" assim que termina, com sucesso ou sem; a rodada que
    chegou ao fim deixa uma linha por coletor. Contar sucesso deixaria o
    dia aberto para sempre quando um coletor falha de forma persistente -
    e ai os oito gatilhos recoletariam todo dia.

    Em caso de duvida devolve False, que manda coletar: perder o dia por
    nao conseguir perguntar seria o pior dos dois erros.
    """
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    chave = os.environ.get("SUPABASE_SECRET_KEY") or ""
    if not url or not chave:
        sys.stderr.write("sem credencial para perguntar\n")
        return False, None

    caminho = "coletas?data_captura=eq.%s&select=operadora,sucesso" % hoje
    req = urllib.request.Request(url + API + caminho)
    req.add_header("apikey", chave)
    req.add_header("Authorization", "Bearer " + chave)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            linhas = json.loads(r.read().decode("utf-8", "replace"))
        esperadas = _esperadas()
    except Exception as e:
        sys.stderr.write("nao deu para perguntar: %s\n" % e)
        return False, None

    registradas = {l["operadora"] for l in linhas}
    ok = {l["operadora"] for l in linhas if l.get("sucesso")}
    sys.stderr.write("%s: %d de %d coletores registraram (%d com sucesso)\n"
                     % (hoje, len(registradas), esperadas, len(ok)))
    return len(registradas) >= esperadas, len(registradas)


def main():
    agora = datetime.now(BRT)
    hoje = agora.date().isoformat()

    # "--fechou DIA" responde SO a pergunta do estado: aquele dia passou
    # por todos os coletores? Sem logica de horario nenhuma.
    #
    # POR QUE SEPARADO. O resto desta funcao responde "preciso coletar
    # agora?", que e outra pergunta - e as duas so coincidem dentro da
    # janela. O job de alerta usava a resposta de coletar como se fosse a
    # de estado, e com um gatilho chegando depois da meia-noite ele
    # perguntava sobre o dia NOVO, ouvia "e cedo demais" e calava: o dia
    # perdido morria em silencio, que e o que aquele job existe para
    # impedir.
    if "--fechou" in sys.argv:
        alvo = sys.argv[sys.argv.index("--fechou") + 1]
        feito, quantas = _ja_coletou(alvo)
        print("sim" if feito else "nao")
        sys.stderr.write("%s: %s coletor(es) registrado(s)\n"
                         % (alvo, "?" if quantas is None else quantas))
        return 0

    feito, _quantas = _ja_coletou(hoje)

    if feito:
        print("nao")
        sys.stderr.write("o dia ja foi coletado\n")
        return 0

    if agora.time() >= LIMITE:
        print("sim")
        sys.stderr.write("passou das %s: coleta de qualquer jeito\n"
                         % LIMITE.strftime("%H:%M"))
        return 0

    if agora.time() < ABERTURA:
        print("nao")
        sys.stderr.write("sao %s, cedo demais - a janela abre as %s\n"
                         % (agora.strftime("%H:%M"), ABERTURA.strftime("%H:%M")))
        return 0

    print("sim")
    sys.stderr.write("dentro da janela e sem coleta hoje: vai coletar\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
