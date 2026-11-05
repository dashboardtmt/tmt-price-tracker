# -*- coding: utf-8 -*-
"""A faixa de numeros que abre o Overview, medida no JS da propria tela.

POR QUE ELA PRECISA DE TESTE PROPRIO. Numero de cabecalho e o que mais
se olha e o que menos se confere: ele fica acima da dobra, e quem o le
nao desce ate a tabela que o sustenta. Se a faixa disser "2 mudancas" e
a matriz logo abaixo mostrar uma seta so, os dois canais da MESMA tela
passam a discordar - que e o defeito que test_tres_canais existe para
impedir entre a mensagem, o PDF e a tela, e que aqui acontece dentro de
uma pagina.

O CASO E O PIOR POSSIVEL DE PROPOSITO: uma operadora deslizando a
escada no mesmo dia em que a outra reajusta. Escada que desliza NAO e
mudanca de preco - o degrau de 45 GB passa a custar o que o de 40
custava, e parear por degrau afirmaria -14% onde o preco nao se mexeu
(decisao 72). A matriz marca losango nesses, seta no reajuste; a faixa
conta so os de seta, porque chama a mesma funcao.
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
class AFaixaDoDiaNaoDiscordaDaMatriz(unittest.TestCase):

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

    def test_a_entrada_e_a_oferta_mais_barata_do_dia(self):
        """E com o nome de quem a vende: "R$ 59,90" sozinho nao diz se o
        mercado tem uma operadora barata ou uma faixa inteira barata."""
        self.assertIn("R$ 59,90", self.painel["kpis"])
        self.assertIn("Claro", self.painel["kpis"])

    def test_a_prateleira_conta_os_planos_do_filtro(self):
        """Dois degraus da Claro e um da Vivo."""
        self.assertIn('<div class="kpi-val">3</div>', self.painel["kpis"])

    def test_a_escada_que_deslizou_nao_entra_como_mudanca_de_preco(self):
        """O NUMERO DA FAIXA E O DA MATRIZ SAO O MESMO FATO. A Claro
        deslizou os dois degraus e a Vivo reajustou: uma mudanca de
        preco, nao tres. Contar os tres e o erro que a decisao 72 mediu
        - 39 pares de preco falsos em 35 dias, todos de dois dias em que
        a escada andou."""
        self.assertIn('<div class="kpi-val">1</div>', self.painel["kpis"],
                      "a faixa tem de contar 1 mudanca de preco")
        # E A TABELA DA MESMA TELA CONCORDA: uma seta e um losango. Sao
        # tres degraus da Claro na janela e so um deles tem par para
        # comparar no ultimo dia - o de 40 GB deixou de existir e o de
        # 50 GB nasceu ali, e degrau sem os dois lados nao vira marca
        # nenhuma, pela mesma regra que vale na mensagem.
        matriz = self.painel["matriz"]
        self.assertEqual(matriz.count("▲") + matriz.count("▼"), 1, matriz)
        self.assertEqual(matriz.count("◆"), 1, matriz)
