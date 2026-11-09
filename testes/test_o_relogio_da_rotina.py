# -*- coding: utf-8 -*-
u"""Os gatilhos da rotina diaria - o que decide a hora da mensagem.

O QUE ESTE ARQUIVO PRENDE, E O QUE MUDOU EM 09/11/2026. A tese antiga
estava aqui escrita: "quem governa a hora da mensagem nao e o horario
dos crons, e o ESPACAMENTO entre eles - de 20 em 20 minutos, a primeira
chegada depois das 6h e no maximo 6h20". A medicao desmentiu. De 02 a
09/11/2026, contando todas as rodadas agendadas de oito dias, o GitHub
entrega OITO CHEGADAS POR DIA e nada mais: oito quando havia oito crons,
e oito depois que a faixa densa subiu para 29. As 21 chegadas a mais da
faixa nunca vieram, e a mensagem continuou saindo no meio da manha - as
9h12 em 08/11 e as 11h33 em 09/11.

O QUE FALTAVA ERA DEIXAR DE RECUSAR. A faixa trouxe duas das oito
chegadas para a madrugada (04:59, 05:06 e 05:10 UTC nos tres dias
medidos, a ~4h das 6h BRT) e a guarda recusava justamente essas, por
serem cedo - e ai a vez ia para a chegada seguinte, seis horas depois.
Agora ja_coletou.py responde "espere N" e o job DORME os N minutos
dentro do Actions, coletando as 6h em ponto.

TRES COISAS SE PERDEM SOZINHAS, e cada uma tem classe aqui:

  1. A faixa densa parece decorativa, e qualquer limpeza que tire
     "gatilho repetido" tira a unica chegada que cai perto da janela.
  2. "espere N" vira "diferente de sim" com uma linha de shell - o
     defeito original - e a suite inteira continua verde.
  3. O job "alerta", unico aviso do dia nao coletado, dispara comparando
     github.event.schedule com uma STRING de cron: renomear o cron faz o
     alerta calar para sempre sem quebrar nada visivel.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROTINA = os.path.join(RAIZ, ".github", "workflows", "diario.yml")

import ja_coletou                                             # noqa: E402

# A faixa densa, em minutos desde a meia-noite UTC.
FAIXA_INICIO = 22 * 60          # 22:00 UTC = 19:00 BRT
# A faixa termina NA abertura da janela, e a abertura vem de
# ja_coletou.py: mudar a hora da coleta sem mexer na faixa deixaria a
# faixa parada tres horas antes da nova hora, que era o defeito de antes.
ABERTURA_UTC = (ja_coletou.ABERTURA.hour + 3) * 60 + ja_coletou.ABERTURA.minute
FAIXA_FIM = ABERTURA_UTC
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

    def test_a_faixa_vai_da_noite_ate_a_abertura(self):
        """Da noite anterior as 6h BRT. Encurtar a faixa e apostar que o
        atraso do GitHub nao volta a mudar - e ele mudou 2 horas em dez
        dias."""
        na_faixa = [m - 24 * 60 if m >= FAIXA_INICIO else m
                    for m in disparos()
                    if m >= FAIXA_INICIO or m <= FAIXA_FIM]
        self.assertLessEqual(min(na_faixa), FAIXA_INICIO - 24 * 60 + 5)
        self.assertGreaterEqual(max(na_faixa), FAIXA_FIM - 20)

    def test_a_faixa_termina_na_abertura_e_nao_antes(self):
        """ATE 09/11/2026 ELA PARAVA AS 05:43 UTC, tres horas antes das
        6h BRT: o gatilho que chegasse NA HORA no fim da faixa ainda
        tinha de dormir tres horas, e dormir e o que pode dar errado.
        Terminando na abertura, o ultimo degrau coleta quase na hora."""
        fim = max(m for m in disparos() if m <= FAIXA_FIM)
        self.assertGreaterEqual(
            fim, ABERTURA_UTC - PASSO_MAXIMO,
            "a faixa para %d min antes da abertura" % (ABERTURA_UTC - fim))


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


class AGuardaEsperaEmVezDeRecusar(unittest.TestCase):
    u"""A TERCEIRA RESPOSTA DA GUARDA, medida em todos os ramos.

    O gatilho da madrugada e a unica chegada do dia que cai perto da
    hora certa, e recusa-la era jogar a vez para seis horas depois. Sem
    esta classe, "cedo demais" volta a ser "nao" com uma linha, e a
    mensagem volta para o meio da manha sem quebrar nada.
    """

    def _as(self, h, m=0):
        # um dia qualquer, porque so a hora importa
        return datetime(2026, 11, 10, h, m, tzinfo=ja_coletou.BRT)

    def test_cedo_dentro_do_alcance_manda_esperar(self):
        resposta, _ = ja_coletou.decidir(self._as(2, 10), False)
        self.assertEqual(resposta, "espere 230")

    def test_o_que_se_espera_e_exatamente_o_que_falta(self):
        u"""Dormir demais passa da hora; dormir de menos acorda o job
        antes da janela, e ai a guarda responde "espere" outra vez."""
        for h, m, falta in ((5, 0, 60), (5, 59, 1), (0, 40, 320)):
            resposta, _ = ja_coletou.decidir(self._as(h, m), False)
            self.assertEqual(resposta, "espere %d" % falta,
                             "as %02d:%02d" % (h, m))

    def test_cedo_longe_demais_passa_a_vez(self):
        u"""O job do Actions e morto em 6 horas: dormir alem disso e
        perder a rodada DORMINDO, que e pior do que passar a vez para a
        chegada seguinte."""
        self.assertEqual(ja_coletou.decidir(self._as(0, 39), False)[0], "nao")

    def test_dentro_da_janela_coleta(self):
        self.assertEqual(ja_coletou.decidir(self._as(6, 5), False)[0], "sim")

    def test_dia_coletado_nao_dorme(self):
        u"""A ordem dos ramos: "ja coletou" vem antes de tudo, senao a
        rodada da madrugada dormiria quatro horas para descobrir que o
        dia estava fechado."""
        self.assertEqual(ja_coletou.decidir(self._as(2, 10), True)[0], "nao")

    def test_a_noite_do_dia_que_nao_coletou_nao_dorme(self):
        u"""Depois do limite a coleta roda de qualquer jeito, e esse
        ramo vem ANTES do de dormir: as 23h o que falta para as 6h e a
        madrugada inteira, e dormir ali trocaria "dia sem dado" por
        "dia coletado amanha"."""
        self.assertEqual(ja_coletou.decidir(self._as(23, 10), False)[0], "sim")

    def test_a_espera_cabe_no_teto_do_actions(self):
        u"""Seis horas e o teto de um job. 330 min deixa margem para o
        checkout, os testes e a folga do sleep."""
        self.assertLessEqual(ja_coletou.ESPERA_MAXIMA, 330)


class AGuardaRespondeNoCaminhoDeProducao(unittest.TestCase):
    u"""FUNCAO MEDIDA NAO E CAMINHO MEDIDO. decidir() e pura e esta
    medida acima em todos os horarios, mas quem roda no Actions e
    "python ja_coletou.py" - e um main() que imprimisse a tupla, ou o
    porque, ou nada, passaria por todos os testes de cima.
    """

    def test_a_saida_do_script_e_a_resposta_da_guarda(self):
        env = dict(os.environ)
        # sem credencial ele nao pergunta ao banco, e responde pela hora
        for chave in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"):
            env.pop(chave, None)
        antes = ja_coletou.decidir(datetime.now(ja_coletou.BRT), False)[0]
        r = subprocess.run([sys.executable, "ja_coletou.py"], cwd=RAIZ,
                           env=env, capture_output=True, text=True)
        depois = ja_coletou.decidir(datetime.now(ja_coletou.BRT), False)[0]
        self.assertEqual(r.returncode, 0, r.stderr)
        saida = r.stdout.strip()
        # o relogio anda entre as tres leituras, entao o que se compara e
        # a RESPOSTA, nao o numero de minutos
        self.assertIn(saida.split()[0],
                      (antes.split()[0], depois.split()[0]),
                      "a guarda imprimiu %r" % saida)


class OJobTemDeCaberAEspera(unittest.TestCase):
    u"""DOIS NUMEROS EM ARQUIVOS DIFERENTES. A guarda manda dormir ate
    ESPERA_MAXIMA minutos, e quem dorme e o job "decidir" do Actions:
    com timeout-minutes menor que a espera, o job e morto DORMINDO - a
    rodada se perde sem coletar, e o alerta do dia perdido so fala as
    10h29.
    """

    def _bloco_decidir(self):
        with open(ROTINA, encoding="utf-8") as f:
            texto = f.read()
        return texto[texto.index("  decidir:"):texto.index("  alerta:")]

    def test_o_timeout_cabe_a_espera_maxima(self):
        achado = re.search(r"timeout-minutes: (\d+)", self._bloco_decidir())
        self.assertIsNotNone(achado, "o job decidir ficou sem timeout")
        self.assertGreaterEqual(
            int(achado.group(1)), ja_coletou.ESPERA_MAXIMA + 10,
            "timeout de %s min para dormir %d" % (achado.group(1),
                                                  ja_coletou.ESPERA_MAXIMA))

    def test_o_job_tem_o_ramo_de_esperar(self):
        u"""O ramo e uma linha de shell, e some sem deixar marca: a
        guarda continua respondendo "espere 230" e o job continua
        verde - so que nao coleta, e a mensagem volta para as 11h33."""
        self.assertIn('"espere "*)', self._bloco_decidir())


def _bash():
    return shutil.which("bash")


@unittest.skipIf(_bash() is None, "bash nao encontrado")
class OShellDaGuardaObedece(unittest.TestCase):
    u"""TESTE DE PECA NAO PROVA MONTAGEM. decidir() pode responder
    "espere 230" com toda a razao e o shell do Actions tratar isso como
    "diferente de sim" - que e exatamente o que ele fazia ate 09/11/2026,
    e o que fez a mensagem daquele dia sair as 11h33.

    O que corre aqui e o TRECHO DE VERDADE, recortado do diario.yml, com
    um ja_coletou de mentira respondendo o que cada teste quiser e um
    "sleep" de mentira que anota quanto dormiria em vez de dormir.
    """

    ABRE = 'RESPOSTA="$(python ja_coletou.py)"'
    FECHA = "\n  # O DIA PERDIDO TEM DE FALAR"

    FINGIDO = (u"# -*- coding: utf-8 -*-\n"
               u"import io\n"
               u"with io.open('fila.txt', encoding='utf-8') as f:\n"
               u"    restam = f.read().split('\\n')\n"
               u"print(restam[0])\n"
               u"with io.open('fila.txt', 'w', encoding='utf-8') as f:\n"
               u"    f.write('\\n'.join(restam[1:]))\n")

    def _trecho(self):
        """O passo da guarda, recortado do workflow e sem a indentacao
        do YAML. Comeca onde o shell deixa de ter ${{ }} do GitHub, que
        o bash nao sabe ler."""
        with open(ROTINA, encoding="utf-8") as f:
            texto = f.read()
        i = texto.index(self.ABRE)
        fim = texto.index(self.FECHA, i)
        linhas = [l[10:] if l.startswith(" " * 10) else l
                  for l in texto[i:fim].split("\n")]
        return "\n".join(linhas) + "\n"

    def _rodar(self, respostas):
        """(saida do GITHUB_OUTPUT, o que dormiu, respostas que sobraram)."""
        casa = tempfile.mkdtemp(prefix="guarda")
        try:
            def grava(nome, texto, executavel=False):
                alvo = os.path.join(casa, nome)
                with io.open(alvo, "w", encoding="utf-8", newline="\n") as f:
                    f.write(texto)
                if executavel:
                    os.chmod(alvo, 0o755)
                return alvo

            grava("ja_coletou.py", self.FINGIDO)
            grava("fila.txt", "\n".join(respostas))
            # sleep de mentira: anota os segundos e volta na hora
            grava("sleep", '#!/bin/sh\necho "$1" >> dormiu.txt\n', executavel=True)
            grava("guarda.sh", self._trecho())
            saida = os.path.join(casa, "saida.txt")

            env = dict(os.environ)
            env["PATH"] = casa + os.pathsep + env.get("PATH", "")
            env["GITHUB_OUTPUT"] = saida
            r = subprocess.run([_bash(), "guarda.sh"], cwd=casa, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            def ler(nome):
                alvo = os.path.join(casa, nome)
                if not os.path.exists(alvo):
                    return ""
                with io.open(alvo, encoding="utf-8") as f:
                    return f.read().strip()

            return ler("saida.txt"), ler("dormiu.txt"), ler("fila.txt")
        finally:
            shutil.rmtree(casa, ignore_errors=True)

    def test_espere_dorme_o_que_falta_mais_a_folga(self):
        u"""Dois minutos de espera sao 180 segundos de sono: 120 do que
        falta mais 60 de folga, porque acordar 20 segundos antes das 6h
        faz a guarda responder "espere 1" e o dia nao coletar."""
        saida, dormiu, sobrou = self._rodar(["espere 2", "sim"])
        self.assertEqual(dormiu, "180")
        self.assertEqual(saida, "rodar=true")
        self.assertEqual(sobrou, "", "o shell nao perguntou de novo")

    def test_depois_de_dormir_pergunta_de_novo(self):
        u"""Entre dormir e acordar o dia pode ter sido coletado - por
        disparo na mao, por exemplo -, e ai nao se coleta de novo."""
        saida, dormiu, _ = self._rodar(["espere 2", "nao"])
        self.assertEqual(dormiu, "180")
        self.assertEqual(saida, "rodar=false")

    def test_sim_coleta_sem_dormir(self):
        saida, dormiu, _ = self._rodar(["sim"])
        self.assertEqual(saida, "rodar=true")
        self.assertEqual(dormiu, "")

    def test_nao_nao_coleta(self):
        saida, _, _ = self._rodar(["nao"])
        self.assertEqual(saida, "rodar=false")

    def test_resposta_que_ele_nao_entende_nao_coleta(self):
        u"""Coletar por nao entender a resposta faria a coleta rodar as
        2h da manha no dia em que a guarda imprimisse outra coisa."""
        saida, _, _ = self._rodar(["talvez"])
        self.assertEqual(saida, "rodar=false")

if __name__ == "__main__":
    unittest.main()
