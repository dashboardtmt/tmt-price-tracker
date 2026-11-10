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
    ainda e cedo demais?        -> espere N (dorme os N minutos que
                                   faltam e coleta as 6h; ou "nao", se
                                   faltar mais do que o job aguenta
                                   dormir)
    passou da hora limite?      -> sim, de qualquer jeito
    senao                       -> sim

Assim a coleta acontece AS 6H, e nao na hora em que o gatilho calhou de
chegar. Quem chega depois da rodada fechada encerra em segundos.

NAO E UMA JANELA, E UMA HORA - E QUEM CHEGA CEDO ESPERA. Recusar o
gatilho da madrugada era jogar fora a unica chegada do dia que cai perto
da hora certa. Medido de 02 a 09/11/2026, nas chegadas de oito dias: o
GitHub entrega OITO GATILHOS POR DIA, nao importa quantos crons existam
- oito com oito crons, e oito depois que a faixa densa subiu para 29.
Declarar mais gatilho nao compra mais chegada, compra outro HORARIO de
chegada. E entre a chegada que a guarda recusava as 2h da manha e a
seguinte corriam seis horas: a mensagem de 08/11 saiu as 9h12 e a de
09/11 as 11h33.

Dai a terceira resposta. O gatilho que chega cedo DORME os minutos que
faltam, aqui dentro do job, e coleta as 6h em ponto - e nao precisa de
gatilho externo nenhum para isso. Minuto de Actions nao e cobrado (o
repositorio e publico) e o job do Actions e morto em 6 horas, que e de
onde sai ESPERA_MAXIMA.

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

# QUANTO VALE A PENA DORMIR ESPERANDO A JANELA ABRIR. O job do Actions e
# morto em 6 horas, e morrer dormindo e pior do que passar a vez: a
# rodada se perde e o alerta do dia perdido so fala as 10h29.
#
# ERA 320, E A PRIMEIRA RODADA DE VERDADE MOSTROU QUE ERA POUCO. Com 320
# o limite cai as 00h40, e eu justifiquei esse numero medindo 21 dias em
# que a primeira chegada do dia ficou entre 01h59 e 06h03 - folga de
# mais de uma hora. Em 10/11/2026, no primeiro dia em que a espera
# valeu, a chegada veio as 00h58: dentro do limite por DEZOITO MINUTOS,
# e fora da faixa inteira que eu tinha medido. A faixa de 21 dias
# descrevia o passado, nao o alcance do gatilho.
#
# Com 345 o limite vai para 00h15. O teto segue sendo o job: 345 de sono
# mais um minuto de folga mais o checkout e os testes cabem nos 355 de
# timeout-minutes, e os 360 do Actions continuam acima disso.
ESPERA_MAXIMA = 345

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


def _falta_para_abrir(agora):
    """Minutos daqui ate a abertura de hoje, arredondando PARA CIMA.

    Para cima porque quem dorme 30 segundos de menos acorda antes das 6h
    e ouve "espere 1" de novo - e o job que acorda cedo nao coleta.
    """
    abertura = agora.replace(hour=ABERTURA.hour, minute=ABERTURA.minute,
                             second=0, microsecond=0)
    return int(((abertura - agora).total_seconds() + 59) // 60)


def decidir(agora, feito):
    """A resposta da guarda: ("sim" | "nao" | "espere N", o porque).

    PURA DE PROPOSITO. A decisao e so hora e estado, e e a parte que
    precisa ser medida em todos os horarios do dia - sem banco, sem rede
    e sem esperar o relogio chegar la.

    A ORDEM DOS RAMOS E A REGRA. "Ja coletou" vem antes de tudo, senao a
    rodada da madrugada dormiria quatro horas para descobrir que o dia
    estava fechado. E o LIMITE vem antes da ABERTURA: as 23h de um dia
    que nao coletou, o que falta para as 6h e a madrugada inteira, e
    dormir ali trocaria "dia sem dado" por "dia coletado amanha".
    """
    if feito:
        return "nao", "o dia ja foi coletado"

    if agora.time() >= LIMITE:
        return "sim", ("passou das %s: coleta de qualquer jeito"
                       % LIMITE.strftime("%H:%M"))

    if agora.time() < ABERTURA:
        falta = _falta_para_abrir(agora)
        if falta > ESPERA_MAXIMA:
            return "nao", (
                "sao %s e faltam %d min para as %s - mais do que o job "
                "aguenta dormir (%d); a vez fica para quem chegar mais perto"
                % (agora.strftime("%H:%M"), falta,
                   ABERTURA.strftime("%H:%M"), ESPERA_MAXIMA))
        return "espere %d" % falta, (
            "sao %s: durmo os %d min que faltam e coleto as %s"
            % (agora.strftime("%H:%M"), falta, ABERTURA.strftime("%H:%M")))

    return "sim", "dentro da janela e sem coleta hoje: vai coletar"


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
    resposta, porque = decidir(agora, feito)
    print(resposta)
    sys.stderr.write(porque + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
