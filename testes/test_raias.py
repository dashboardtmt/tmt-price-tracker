# -*- coding: utf-8 -*-
"""A coleta em raias: paralela por operadora, serial por praca.

POR QUE ESTE ARQUIVO EXISTE. Em 27/10/2026 a cota de minutos do GitHub
Actions acabou no dia 27. A coleta daquele dia rodou e FECHOU - 45m29s,
dado gravado -, e os jobs seguintes, o do aviso e o da tela, nao
chegaram a iniciar: o dia foi coletado e ficou sem mensagem e sem
painel. O alarme que existe para o dia em que a mensagem nao sai tambem
e um job, e tambem nao iniciou.

A causa era o relogio: 46 minutos por dia, vezes 30 dias, mais um minuto
em cada um dos oito gatilhos diarios, contra 2.000 minutos por mes. As
raias trocam a SOMA dos coletores pelo MAIOR deles - 19 minutos da Vivo
em vez de 43 somados.

O QUE SE MEDE AQUI e o caminho de producao, rodar_coleta, com coletores
de mentira. Testar coletar_operadora sozinha nao provaria nada: o
paralelismo, a ordem do resumo e a tranca do log sao todos de
rodar_coleta, e e nela que eles podem se perder.

AS DUAS METADES QUE PODEM SE PERDER:

  1. O PARALELISMO em si - alguem "simplifica" o executor de volta para
     um for, a suite fica verde e a cota estoura de novo em novembro.
  2. O QUE O PARALELISMO NAO PODE QUEBRAR - a ordem do resumo, a
     integridade das linhas do log, e a garantia de que toda operadora
     de COLETORES tem raia. Esta ultima e a mais perigosa: coletor sem
     raia nao coleta, e nao coletar calado numa serie append-only
     significa um buraco que nao volta.
"""
import io
import os
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                    # noqa: E402


# --------------------------------------------------------- coletor de mentira

class ColetorFalso(object):
    """Um modulo de coletor com o minimo que rodar_coleta usa.

    `demora` e por praca, e e o que permite medir se duas raias andaram
    ao mesmo tempo: em serie o relogio soma, em paralelo ele nao soma.
    """

    def __init__(self, nome, demora=0.0, nacional=False, explode=False,
                 ofertas_por_praca=2):
        self.nome = nome
        self.demora = demora
        self.NACIONAL = nacional
        self.explode = explode
        self.ofertas_por_praca = ofertas_por_praca
        self.visitou = []

    def coletar(self, cidade, uf, verbose=True):
        if self.demora:
            time.sleep(self.demora)
        self.visitou.append((cidade, uf))
        if self.explode:
            raise RuntimeError("o coletor %s quebrou" % self.nome)
        return {"ofertas": [{"operadora": self.nome, "praca": cidade,
                             "preco": 10.0 + i}
                            for i in range(self.ofertas_por_praca)],
                "avisos": []}


class BancoDeMentira(object):
    """Conta o que foi gravado, sem rede nenhuma."""

    def __init__(self):
        self.capturas = []
        self.registros = []
        self.tranca = threading.Lock()

    def gravar_capturas(self, ofertas):
        with self.tranca:
            self.capturas.append(list(ofertas))
        return len(ofertas), None

    def registrar_coleta(self, registro):
        with self.tranca:
            self.registros.append(dict(registro))
        return True, None


class ComColetoresFalsos(unittest.TestCase):
    """Troca COLETORES, o banco e as pracas por versoes de mentira."""

    PRACAS = [{"cidade": "Sao Paulo", "uf": "SP", "regiao": "Sudeste",
               "capital": True},
              {"cidade": "Recife", "uf": "PE", "regiao": "Nordeste",
               "capital": True}]

    def montar(self, coletores):
        self.banco = BancoDeMentira()
        self.falsos = coletores
        self._guardado = (robo.COLETORES,
                          robo.armazenamento.gravar_capturas,
                          robo.armazenamento.registrar_coleta,
                          robo.pracas_de)
        robo.COLETORES = coletores
        robo.armazenamento.gravar_capturas = self.banco.gravar_capturas
        robo.armazenamento.registrar_coleta = self.banco.registrar_coleta
        robo.pracas_de = lambda nome: list(self.PRACAS)
        self.addCleanup(self.devolver)

    def devolver(self):
        (robo.COLETORES, robo.armazenamento.gravar_capturas,
         robo.armazenamento.registrar_coleta, robo.pracas_de) = self._guardado

    def rodar(self, raias, uma_praca=None, simular=False):
        """Roda a coleta engolindo o log, e devolve (resumo, falhas, log)."""
        buraco = io.StringIO()
        with redirect_stdout(buraco):
            resumo, falhas = robo.rodar_coleta(uma_praca, simular, raias)
        return resumo, falhas, buraco.getvalue()


# ------------------------------------------- a invariante que mata em silencio

class TodoColetorTemRaia(unittest.TestCase):
    u"""Coletor fora das raias nao coleta, e nao avisa que nao coletou.

    Este e o teste que protege o dado. Os outros protegem o relogio.
    """

    def test_as_raias_cobrem_coletores_exatamente(self):
        nas_raias = [n for raia in robo.RAIAS for n in raia]
        self.assertEqual(sorted(nas_raias), sorted(robo.COLETORES))

    def test_nenhum_coletor_em_duas_raias(self):
        """Repetido, ele coletaria duas vezes - e pagaria duas vezes."""
        nas_raias = [n for raia in robo.RAIAS for n in raia]
        self.assertEqual(len(nas_raias), len(set(nas_raias)))

    def test_a_importacao_recusa_raia_incompleta(self):
        """A guarda esta no modulo, e nao so aqui: quem rodar o robo sem
        rodar a suite tambem tem de bater nela."""
        caminho = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "robo.py")
        with io.open(caminho, encoding="utf-8") as f:
            fonte = f.read()
        self.assertIn("RAIAS e COLETORES nao batem", fonte)
        self.assertIn("raise RuntimeError", fonte)

    def test_a_vivo_esta_sozinha_na_raia_dela(self):
        """Ela e a mais lenta - 19 dos 43 minutos -, entao e ela que
        define o relogio. Dividir a raia dela com qualquer outro soma
        em cima do maior."""
        dela = [raia for raia in robo.RAIAS if "Vivo" in raia]
        self.assertEqual(dela, [("Vivo",)])

    def test_tim_e_tim_fit_na_mesma_raia(self):
        """Mesmo dominio: o FIT sai das etiquetas linkadas na pagina de
        Controle da TIM. Separados, dobram a batida no mesmo host."""
        juntos = [raia for raia in robo.RAIAS
                  if "TIM" in raia and "TIM FIT" in raia]
        self.assertEqual(len(juntos), 1)

    def test_os_tres_de_navegador_na_mesma_raia(self):
        """A API sincrona do Playwright nao foi feita para varias
        instancias concorrentes, e os tres somam 35 segundos: paralelizar
        nao compra nada e paga risco."""
        for raia in robo.RAIAS:
            if "Unifique" in raia:
                self.assertIn("NuCel", raia)
                self.assertIn("Claro Flex", raia)
                return
        self.fail("a Unifique sumiu das raias")


# ----------------------------------------------------------------- o relogio

class AsRaiasAndamJuntas(ComColetoresFalsos):
    u"""O ganho que motivou tudo: o relogio para de somar.

    Se alguem trocar o executor por um for, estes dois testes ficam
    vermelhos. Sem eles a regressao e invisivel - a suite segue verde e
    a conta chega no fim do mes.
    """

    def test_tres_raias_nao_somam_o_relogio(self):
        self.montar({"A": ColetorFalso("A", demora=0.20, nacional=True),
                     "B": ColetorFalso("B", demora=0.20, nacional=True),
                     "C": ColetorFalso("C", demora=0.20, nacional=True)})
        inicio = time.time()
        resumo, _, _ = self.rodar((("A",), ("B",), ("C",)))
        gasto = time.time() - inicio
        self.assertEqual(len(resumo), 3)
        # em serie seriam 0,60s; o limite generoso e so para nao piscar
        # em maquina ocupada - o ponto e que NAO soma
        self.assertLess(gasto, 0.45,
                        "as raias somaram o relogio: rodaram em serie")

    def test_uma_raia_so_soma(self):
        """O controle do teste de cima. Sem ele, um rodar_coleta que nao
        roda nada passaria nos dois."""
        self.montar({"A": ColetorFalso("A", demora=0.20, nacional=True),
                     "B": ColetorFalso("B", demora=0.20, nacional=True),
                     "C": ColetorFalso("C", demora=0.20, nacional=True)})
        inicio = time.time()
        resumo, _, _ = self.rodar((("A", "B", "C"),))
        gasto = time.time() - inicio
        self.assertEqual(len(resumo), 3)
        self.assertGreater(gasto, 0.55, "nao rodou os tres de verdade")

    def test_a_praca_continua_em_serie_dentro_da_operadora(self):
        """E a rajada no mesmo host que derruba. Duas pracas de 0,15s na
        mesma operadora tem de somar."""
        self.montar({"A": ColetorFalso("A", demora=0.15)})
        inicio = time.time()
        self.rodar((("A",),))
        self.assertGreater(time.time() - inicio, 0.25,
                           "as pracas da mesma operadora foram em paralelo")


# ------------------------------------------- o que o paralelismo nao quebra

class OParaleloNaoBagunca(ComColetoresFalsos):
    u"""Tres coisas que o paralelo poderia estragar sem ninguem ver."""

    def test_a_ordem_do_resumo_e_a_de_coletores(self):
        """A mais lenta esta em PRIMEIRO em COLETORES e termina por
        ultimo. Pela ordem de chegada o resumo sairia B, C, A - e a
        tabela "Estado da coleta" dancaria conforme a rede do dia."""
        self.montar({"A": ColetorFalso("A", demora=0.25, nacional=True),
                     "B": ColetorFalso("B", nacional=True),
                     "C": ColetorFalso("C", nacional=True)})
        resumo, _, _ = self.rodar((("A",), ("B",), ("C",)))
        self.assertEqual([r["operadora"] for r in resumo], ["A", "B", "C"])

    def test_a_ordem_nao_depende_da_ordem_das_raias(self):
        self.montar({"A": ColetorFalso("A", demora=0.25, nacional=True),
                     "B": ColetorFalso("B", nacional=True),
                     "C": ColetorFalso("C", nacional=True)})
        resumo, _, _ = self.rodar((("C",), ("B",), ("A",)))
        self.assertEqual([r["operadora"] for r in resumo], ["A", "B", "C"])

    def test_nenhuma_linha_do_log_sai_partida(self):
        """Sem a tranca, duas raias escrevendo juntas partem a linha uma
        da outra - e o log de um job de 20 minutos existe justamente
        para achar onde travou.

        A SAIDA TEM DE CEDER A VEZ, senao este teste nao mede nada. A
        primeira versao dele escrevia num StringIO comum, e passava com
        a tranca REMOVIDA: print() faz duas escritas - o texto e o
        "\\n" -, e num buffer em memoria as duas saem coladas porque
        nada troca de thread no meio. Era medicao sem sinal se passando
        por prova.

        EscritaLenta dorme dentro do write, que e o que um terminal ou
        um arquivo de verdade fazem ao bloquear em E/S: ai a troca de
        thread acontece exatamente entre o texto e o "\\n", que e onde a
        linha se parte.
        """
        class EscritaLenta(io.StringIO):
            def write(self, s):
                time.sleep(0.002)      # cede a vez no meio da linha
                return io.StringIO.write(self, s)

        # NOMES DE TRES LETRAS para o teste poder CONTAR a marca na
        # linha. Conferir so o comeco da linha nao mede nada: duas
        # linhas grudadas - "AAA ...BBB ..." - ainda comecam com uma
        # marca conhecida, e a primeira versao disto passava com a
        # tranca removida por causa exatamente dessa frouxidao.
        marcas = ("AAA", "BBB", "CCC")
        self.montar(dict((m, ColetorFalso(m)) for m in marcas))
        papel = EscritaLenta()
        with redirect_stdout(papel):
            robo.rodar_coleta(None, False, tuple((m,) for m in marcas))

        cabecalho_ou_rodape = ("=", "COLETA", "Incompletas")
        for linha in papel.getvalue().split("\n"):
            if not linha or linha.startswith(cabecalho_ou_rodape):
                continue
            quantas = sum(linha.count(m) for m in marcas)
            # duas marcas = duas linhas grudadas; nenhuma = linha que
            # comecou no meio de outra
            self.assertEqual(quantas, 1, "linha partida no log: %r" % linha)

    def test_cada_operadora_grava_a_sua(self):
        """Uma chamada de gravacao por operadora, com as ofertas dela -
        e nao uma gravacao gigante no fim, que perderia tudo de uma vez."""
        self.montar({"A": ColetorFalso("A"), "B": ColetorFalso("B")})
        self.rodar((("A",), ("B",)))
        self.assertEqual(len(self.banco.capturas), 2)
        donos = sorted(c[0]["operadora"] for c in self.banco.capturas)
        self.assertEqual(donos, ["A", "B"])

    def test_o_diario_de_bordo_sai_um_por_operadora(self):
        self.montar({"A": ColetorFalso("A"), "B": ColetorFalso("B")})
        self.rodar((("A",), ("B",)))
        self.assertEqual(sorted(r["operadora"] for r in self.banco.registros),
                         ["A", "B"])


# ------------------------------------------------------- pracas e falhas

class AsPracasEAsFalhas(ComColetoresFalsos):

    def test_nacional_roda_uma_praca_so(self):
        """Repetir nas 20 pracas gravaria 20 copias do mesmo preco."""
        nac = ColetorFalso("N", nacional=True)
        self.montar({"N": nac})
        resumo, _, _ = self.rodar((("N",),))
        self.assertEqual(resumo[0]["pracas_pedidas"], 1)
        self.assertEqual(nac.visitou, [("Brasil", "BR")])

    def test_o_filtro_de_praca_nao_vale_para_nacional(self):
        """--praca e modo de teste; a nacional nao tem praca para filtrar
        e sumiria da rodada inteira se o filtro valesse para ela."""
        nac = ColetorFalso("N", nacional=True)
        self.montar({"N": nac})
        resumo, _, _ = self.rodar((("N",),), uma_praca="Recife/PE")
        self.assertEqual(resumo[0]["pracas_pedidas"], 1)

    def test_o_filtro_de_praca_vale_para_as_outras(self):
        reg = ColetorFalso("R")
        self.montar({"R": reg})
        resumo, _, _ = self.rodar((("R",),), uma_praca="Recife/PE")
        self.assertEqual(resumo[0]["pracas_pedidas"], 1)
        self.assertEqual(reg.visitou, [("Recife", "PE")])

    def test_simular_nao_grava(self):
        self.montar({"A": ColetorFalso("A")})
        self.rodar((("A",),), simular=True)
        self.assertEqual(self.banco.capturas, [])

    def test_a_praca_que_quebra_nao_derruba_a_operadora(self):
        """Ja era assim em serie, e o paralelo nao pode ter perdido."""
        quebra = ColetorFalso("Q", explode=True)
        self.montar({"Q": quebra})
        resumo, falhas, _ = self.rodar((("Q",),))
        self.assertEqual(falhas, ["Q"])
        self.assertEqual(resumo[0]["pracas_ok"], 0)
        self.assertEqual(len(resumo[0]["avisos"]), 2)   # uma por praca

    def test_a_operadora_incompleta_sai_em_falhas(self):
        """E o que faz o robo sair diferente de zero e o repique rodar."""
        self.montar({"A": ColetorFalso("A"),
                     "Q": ColetorFalso("Q", explode=True)})
        resumo, falhas, _ = self.rodar((("A",), ("Q",)))
        self.assertEqual(falhas, ["Q"])
        self.assertEqual(len(resumo), 2)

    def test_uma_raia_que_quebra_nao_impede_as_outras_de_gravar(self):
        """A excecao continua derrubando a rodada, de proposito - e assim
        que o job falha e o repique roda. Mas o que as outras raias ja
        coletaram tem de estar no banco: dia perdido nao volta."""
        class RaiaQuebrada(ColetorFalso):
            def coletar(self, cidade, uf, verbose=True):
                raise KeyboardInterrupt("isto nao e pego por except Exception")

        self.montar({"A": ColetorFalso("A", demora=0.02),
                     "X": RaiaQuebrada("X", nacional=True)})
        with self.assertRaises(KeyboardInterrupt):
            self.rodar((("A",), ("X",)))
        gravadas = [c[0]["operadora"] for c in self.banco.capturas]
        self.assertIn("A", gravadas,
                      "a raia boa nao gravou: a quebrada levou junto")


if __name__ == "__main__":
    unittest.main(verbosity=2)
