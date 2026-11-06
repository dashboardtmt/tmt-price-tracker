# -*- coding: utf-8 -*-
u"""Os gatilhos da rotina diaria - o que decide a hora da mensagem.

O QUE ESTE ARQUIVO PRENDE. A coleta comeca na PRIMEIRA chegada depois
das 6h, e o gatilho do GitHub chega horas atrasado: medido nos oito
gatilhos de cada dia, de 27/10 a 05/11/2026, o atraso medio subiu de
5,5h para 7,6h. Com isso o primeiro gatilho do dia passou a chegar as
5h24 - a guarda recusa, e cedo - e o segundo so as 9h12. A mensagem de
05/11 saiu as 9h35 sem nada estar quebrado.

Ou seja: quem governa a hora da mensagem nao e o horario escrito nos
crons, e o ESPACAMENTO entre eles. Espacados de 1h30 a 2h30, a janela
das 6h caia entre dois gatilhos. De 20 em 20 minutos, a primeira
chegada depois das 6h e no maximo 6h20.

E E UM AJUSTE QUE SE PERDE FACIL: a lista de crons parece decorativa, e
qualquer limpeza que tire "gatilho repetido" devolve a mensagem para as
9h30 sem quebrar teste nenhum - e sem ninguem notar por dias, porque a
mensagem continua chegando.

O SEGUNDO FATO QUE SE PERDE: o job "alerta" - o unico aviso do dia que
nao foi coletado - dispara comparando github.event.schedule com uma
STRING de cron. Renomear o cron sem mexer no alerta nao quebra nada
visivel: o alerta simplesmente nunca mais fala, e o dia perdido volta a
morrer calado.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROTINA = os.path.join(RAIZ, ".github", "workflows", "diario.yml")

# A faixa densa, em minutos desde a meia-noite UTC.
FAIXA_INICIO = 22 * 60          # 22:00 UTC = 19:00 BRT
FAIXA_FIM = 6 * 60              # 06:00 UTC = 03:00 BRT (do dia seguinte)
PASSO_MAXIMO = 25               # minutos entre uma chegada e a proxima


def _campo(txt, teto):
    """Um campo de cron - "3,23,43", "22-23", "7" - em numeros."""
    fora = []
    for parte in txt.split(","):
        if "-" in parte:
            a, b = parte.split("-")
            fora.extend(range(int(a), int(b) + 1))
        else:
            fora.append(int(parte))
    assert all(0 <= v < teto for v in fora), txt
    return sorted(fora)


def crons():
    """As linhas de cron do arquivo, como strings."""
    with open(ROTINA, encoding="utf-8") as f:
        return re.findall(r"- cron: '([^']+)'", f.read())


def disparos():
    """Todo horario em que a rotina dispara, em minutos UTC."""
    fora = set()
    for linha in crons():
        minuto, hora = linha.split()[:2]
        for h in _campo(hora, 24):
            for m in _campo(minuto, 60):
                fora.add(h * 60 + m)
    return sorted(fora)


class AFaixaDensaNaoPodeRarear(unittest.TestCase):

    def test_nenhum_buraco_maior_que_vinte_e_cinco_minutos(self):
        """Dentro da faixa, de 22:00 as 06:00 UTC. O buraco e o que
        empurra a mensagem: entre o gatilho que chega as 5h59 e o
        proximo correm os minutos que a mensagem atrasa."""
        # a faixa cruza a meia-noite: desdobra em uma reta so
        na_faixa = sorted(
            (m - 24 * 60 if m >= FAIXA_INICIO else m)
            for m in disparos()
            if m >= FAIXA_INICIO or m <= FAIXA_FIM)
        self.assertTrue(na_faixa, "a faixa densa sumiu da lista de crons")
        for antes, depois in zip(na_faixa, na_faixa[1:]):
            self.assertLessEqual(
                depois - antes, PASSO_MAXIMO,
                "buraco de %d min entre dois gatilhos da faixa densa"
                % (depois - antes))

    def test_a_faixa_cobre_as_oito_horas(self):
        """Oito horas de faixa cobrem atraso de ~3h30 a ~11h. Encurtar
        a faixa e apostar que o atraso do GitHub nao volta a mudar - e
        ele mudou 2 horas em dez dias."""
        na_faixa = [m - 24 * 60 if m >= FAIXA_INICIO else m
                    for m in disparos()
                    if m >= FAIXA_INICIO or m <= FAIXA_FIM]
        self.assertLessEqual(min(na_faixa), FAIXA_INICIO - 24 * 60 + 5)
        self.assertGreaterEqual(max(na_faixa), FAIXA_FIM - 20)


class OAlertaPrecisaDoUltimoGatilho(unittest.TestCase):

    def _condicao(self):
        with open(ROTINA, encoding="utf-8") as f:
            texto = f.read()
        bloco = texto[texto.index("  alerta:"):texto.index("  coleta:")]
        achado = re.search(r"github\.event\.schedule == '([^']+)'", bloco)
        self.assertIsNotNone(achado, "o alerta deixou de olhar o cron")
        return achado.group(1)

    def test_o_cron_do_alerta_existe(self):
        """String que nao casa com cron nenhum faz o alerta nunca
        disparar - e o dia perdido volta a morrer calado."""
        self.assertIn(self._condicao(), crons())

    def test_nada_dispara_depois_do_alerta(self):
        """O alerta fala no ULTIMO gatilho do dia porque e a ultima
        chance de o dia ser coletado. Um cron novo entre ele e a faixa
        densa faria o alerta falar com a rodada ainda em pe."""
        minuto, hora = self._condicao().split()[:2]
        alerta = _campo(hora, 24)[0] * 60 + _campo(minuto, 60)[0]
        depois = [m for m in disparos() if alerta < m < FAIXA_INICIO]
        self.assertEqual(depois, [], "gatilho depois do alerta: %s" % depois)


if __name__ == "__main__":
    unittest.main()
