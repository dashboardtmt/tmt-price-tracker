# -*- coding: utf-8 -*-
"""A matriz de precos da tela, medida no JS dela mesma.

POR QUE ELA PRECISA DE TESTE PROPRIO. A matriz afirma por MARCA, e as
duas marcas dizem coisas opostas sobre o mesmo par de dias: a seta diz
que a operadora mexeu no preco, o losango diz que o preco e de outra
oferta. Trocar uma pela outra nao quebra a tela nem aparece no console
- sai uma queda de 14% que nunca houve, na pagina publicada.

O CASO E O PIOR POSSIVEL DE PROPOSITO: uma operadora deslizando a
escada no mesmo dia em que a outra reajusta. Escada que desliza NAO e
mudanca de preco - o degrau de 45 GB passa a custar o que o de 40
custava, e parear por degrau afirmaria -14% onde o preco nao se mexeu
(decisao 72). A matriz marca losango nesses e seta no reajuste.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import oferta                                    # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
NODE = shutil.which("node")

DIAS = ["2026-10-19", "2026-10-20", "2026-10-21"]
PRACA = "Sao Paulo/SP"

# A serie longa da outra guarda: 20 dias, mais que o teto de 12 que a
# matriz teve ate 06/11/2026.
LONGA = ["2026-10-%02d" % d for d in range(1, 21)]


def escada(dia, degraus):
    """A escada da Claro num dia: (preco, GB) por degrau."""
    return [oferta(operadora="Claro", produto="movel", nome="Claro Pós",
                   preco=p, gb=gb, praca=PRACA, data=dia,
                   chave="Claro|movel|%dgb|simples" % gb)
            for p, gb in degraus]


def vivo(dia, preco):
    return [oferta(operadora="Vivo", produto="movel", nome="Vivo Pós",
                   preco=preco, gb=100, praca=PRACA, data=dia,
                   chave="Vivo|movel|100gb|simples")]


def capturas():
    linhas = []
    for d in DIAS[:2]:
        linhas += escada(d, [(59.90, 40), (69.90, 45)]) + vivo(d, 89.90)
    # no ultimo dia a escada da Claro desliza inteira - os mesmos dois
    # precos entregando 5 GB a mais - e a Vivo reajusta de verdade
    linhas += escada(DIAS[2], [(59.90, 45), (69.90, 50)]) + vivo(DIAS[2], 94.90)
    return linhas


@unittest.skipIf(NODE is None, "node nao instalado")
class AMatrizNaoMarcaEscadaComoReajuste(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.dados = os.path.join(cls.pasta, "d.json")
        cls.tela = os.path.join(cls.pasta, "t.html")
        with open(cls.dados, "w", encoding="utf-8") as f:
            json.dump(capturas(), f)
        r = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "gerar_tela.py"),
             "--dados", cls.dados, "--saida", cls.tela],
            capture_output=True, text=True, encoding="utf-8", cwd=RAIZ)
        if r.returncode:
            raise unittest.SkipTest("gerar_tela falhou: %s" % r.stderr[-300:])
        cls.painel = cls._ver(cls, [{"praca": PRACA, "produto": "movel",
                                     "dia": DIAS[2], "aba": "panorama"}])[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _ver(self, consultas):
        r = subprocess.run(
            [NODE, os.path.join(AQUI, "tela_em_node.mjs"),
             self.tela, self.dados, json.dumps(consultas)],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o JS da tela quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)

    def test_so_o_reajuste_leva_seta(self):
        """A Claro deslizou os dois degraus e a Vivo reajustou: uma seta,
        nao tres. Contar os tres e o erro que a decisao 72 mediu - 39
        pares de preco falsos em 35 dias, todos de dois dias em que a
        escada andou."""
        matriz = self.painel["matriz"]
        self.assertEqual(matriz.count("▲") + matriz.count("▼"), 1, matriz)

    def test_a_escada_que_deslizou_leva_losango(self):
        """Sao tres degraus da Claro na janela e so um deles tem par para
        comparar no ultimo dia - o de 40 GB deixou de existir e o de 50
        GB nasceu ali, e degrau sem os dois lados nao vira marca
        nenhuma, pela mesma regra que vale na mensagem."""
        matriz = self.painel["matriz"]
        self.assertEqual(matriz.count("◆"), 1, matriz)


def capturas_longas():
    """Vinte dias de uma escada parada: o que se mede aqui e a largura
    da janela, nao a marca da celula."""
    linhas = []
    for d in LONGA:
        linhas += escada(d, [(59.90, 40), (69.90, 45)])
    return linhas


@unittest.skipIf(NODE is None, "node nao instalado")
class AMatrizNaoTemTetoDeDias(unittest.TestCase):
    """A SERIE INTEIRA, UMA COLUNA POR DIA.

    Ate 06/11/2026 a matriz cortava em DIAS.slice(-12) e o seletor de
    Data nao mexia nessa janela: a base tinha 38 dias e os 26 primeiros
    nao tinham como ser alcancados - nem rolando, nem filtrando. O corte
    nao aparece no console nem deixa buraco visivel: a tabela abre cheia,
    encostada no dia mais recente, e o que falta esta fora da tela.

    E um teto que volta sozinho: quem olhar a largura da tabela vai
    querer "limitar a um recorte razoavel". Se for para limitar de novo,
    que seja contra este teste, e nao por engano.
    """

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.dados = os.path.join(cls.pasta, "d.json")
        cls.tela = os.path.join(cls.pasta, "t.html")
        with open(cls.dados, "w", encoding="utf-8") as f:
            json.dump(capturas_longas(), f)
        r = subprocess.run(
            [sys.executable, os.path.join(RAIZ, "gerar_tela.py"),
             "--dados", cls.dados, "--saida", cls.tela],
            capture_output=True, text=True, encoding="utf-8", cwd=RAIZ)
        if r.returncode:
            raise unittest.SkipTest("gerar_tela falhou: %s" % r.stderr[-300:])
        cls.painel = AMatrizNaoMarcaEscadaComoReajuste._ver(
            cls, [{"praca": PRACA, "produto": "movel",
                   "dia": LONGA[-1], "aba": "panorama"}])[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_uma_coluna_por_dia_da_base(self):
        """Vinte dias na base, vinte colunas de data na matriz."""
        matriz = self.painel["matriz"]
        self.assertEqual(matriz.count('<th class="num">'), len(LONGA),
                         matriz[:400])

    def test_o_primeiro_dia_da_base_esta_na_tabela(self):
        """Contar colunas nao basta: um corte que pegasse os 20 ULTIMOS
        de uma base maior passaria. O que a guarda quer e o comeco da
        serie, que e justamente o que o teto escondia."""
        self.assertIn('<th class="num">01/10</th>', self.painel["matriz"])
