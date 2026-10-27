# -*- coding: utf-8 -*-
"""O texto da fonte entrando na tela, que e o canal publico.

TRES DEFEITOS DA MESMA FAMILIA, achados em 27/10/2026, todos na
fronteira entre "texto que a operadora escreveu" e "formato que
interpreta marcacao":

  1. O NOME DA OFERTA IA CRU PARA O HTML, em seis lugares. Um "&" no
     nome ja sai torto, e marcacao no nome executaria na pagina
     publicada. O relatorio em PDF ja tratava disso - _sem_marcacao()
     existe em relatorio.py pelo mesmo motivo - e a tela nao.

  2. UM "</script>" NO NOME QUEBRAVA A TELA INTEIRA. A tela embutida poe
     a serie dentro de um <script>, e json.dumps nao protege contra a
     sequencia que FECHA a tag. Medido: a pagina gerada morreu com
     "Uncaught SyntaxError", sem tabela, sem grafico, sem nada.

  3. A VELOCIDADE DECLARADA NAO CHEGAVA A TELA. O plano Max da Starlink
     perde o degrau de proposito - "Ate mais de 400 Mbps" e faixa, e
     virava um ponto falso de 400 no grafico -, e com isso aparecia sem
     velocidade nenhuma. A frase estava gravada em bruto desde
     26/10/2026 e ninguem a exportava.

O 1 e o 2 sao o mesmo defeito que o projeto ja tinha consertado NO PDF.
Dois canais, a mesma fronteira - que e onde quase todo defeito deste
projeto mora.
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

from _apoio import HOJE, ONTEM, oferta                        # noqa: E402
import gerar_tela                                             # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
NODE = shutil.which("node")

# O nome hostil, com os quatro jeitos de estragar a pagina: a marcacao
# que viraria elemento, o "&" que sai torto, a aspa que fecha atributo e
# a sequencia que fecha a tag <script>.
NOME_HOSTIL = '<b>Oi</b> & "cia" <script>x=1</script>'

FRASE = u"Até mais de 400 Mbps"


def capturas():
    """Satelite, porque e onde os dois casos moram de verdade."""
    linhas = []
    for data in (ONTEM, HOJE):
        linhas += [
            # o Max: sem degrau e sem franquia, com a frase da fonte
            dict(oferta(operadora="Starlink", produto="satelite",
                        nome=u"Residencial - Máx", praca="Brasil/BR",
                        preco=249.0, gb=None, mbps=None, data=data,
                        chave="Starlink|satelite|None|simples"),
                 velocidade_declarada=FRASE),
            # o nome hostil, numa oferta comum
            oferta(operadora="Starlink", produto="satelite",
                   nome=NOME_HOSTIL, praca="Brasil/BR",
                   preco=245.0, gb=50, mbps=None, data=data,
                   chave="Starlink|satelite|50gb|simples"),
            # uma oferta normal, para o caso facil tambem estar coberto
            oferta(operadora="Starlink", produto="satelite",
                   nome="Residencial: 100 Mbps", praca="Brasil/BR",
                   preco=189.0, gb=None, mbps=100, data=data,
                   chave="Starlink|satelite|100mbps|simples"),
        ]
    return linhas


# ------------------------------------------------- o JSON dentro do script

class OJsonNaoFechaATagScript(unittest.TestCase):
    u"""para_script: a funcao pura, sem depender de gerar a tela."""

    def test_a_sequencia_que_fecha_a_tag_sai_escapada(self):
        s = gerar_tela.para_script({"n": "a</script>b"})
        self.assertNotIn("</script>", s)
        self.assertIn("<\\/script>", s)

    def test_continua_sendo_json_valido(self):
        """Escapar demais quebraria a leitura; "\\/" e JSON valido."""
        s = gerar_tela.para_script({"n": "a</script>b", "x": [1, 2]})
        self.assertEqual(json.loads(s), {"n": "a</script>b", "x": [1, 2]})

    def test_qualquer_fecha_tag_e_barrado_e_nao_so_script(self):
        """"</scr" + "ipt>" montado em pedacos tambem fecharia a tag no
        navegador, entao a regra e o "</" e nao a palavra."""
        self.assertNotIn("</", gerar_tela.para_script({"a": "</b>"}))

    def test_as_quebras_de_linha_do_javascript(self):
        """U+2028 e U+2029 sao quebra de linha para o JS e nao para o
        JSON: dentro de string literal elas tambem partem o script."""
        s = gerar_tela.para_script({"a": u"x y z"})
        self.assertNotIn(u" ", s)
        self.assertNotIn(u" ", s)
        self.assertEqual(json.loads(s)["a"], u"x y z")

    def test_o_acento_continua_inteiro(self):
        """ensure_ascii=False e o que mantem a tela legivel; perder isso
        encheria a pagina de \\u00e7."""
        self.assertIn(u"ação", gerar_tela.para_script(["ação"]))


class ATelaGeradaSobrevive(unittest.TestCase):
    u"""O caminho de producao: gerar_tela.py com o nome hostil dentro."""

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
        with open(cls.tela, encoding="utf-8") as f:
            cls.html = f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def test_o_dado_embutido_nao_fecha_a_tag(self):
        """A prova direta: a sequencia hostil nao aparece crua no
        arquivo, e aparece escapada."""
        self.assertNotIn("x=1</script>", self.html)
        self.assertIn("x=1<\\/script>", self.html)

    def test_o_nome_hostil_esta_la_dentro(self):
        """Controle: sem isto os dois testes acima passariam porque o
        nome sumiu, e nao porque foi tratado."""
        self.assertIn("Oi", self.html)
        self.assertIn(FRASE, self.html)


@unittest.skipIf(NODE is None, "node nao instalado")
class ATelaDesenhaOTextoDaFonte(unittest.TestCase):
    u"""O JS da tela rodando de verdade, com o dado hostil."""

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

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _player(self):
        c = [{"praca": "Brasil/BR", "produto": "satelite", "dia": HOJE,
              "player": "Starlink"}]
        # ENCODING EXPLICITO. Com text=True sozinho, o Python decodifica
        # a saida do node pela codificacao do sistema - cp1252 no
        # Windows -, e "Ate mais de 400 Mbps" volta com o acento
        # trocado. O teste falhava afirmando que a frase nao estava na
        # tela quando ela estava: o defeito era do teste.
        r = subprocess.run(
            [NODE, os.path.join(AQUI, "tela_em_node.mjs"),
             self.tela, self.dados, json.dumps(c)],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o JS da tela quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)[0]["t-player"]

    # ------------------------------------------------- o nome escapado
    def test_a_marcacao_do_nome_nao_vira_elemento(self):
        html = self._player()
        self.assertIn("&lt;b&gt;Oi&lt;/b&gt;", html)
        self.assertNotIn("<b>Oi</b>", html)

    def test_o_e_comercial_sai_escapado(self):
        self.assertIn("&amp;", self._player())

    def test_a_aspa_nao_fecha_atributo(self):
        """O nome entra tambem dentro de title=, e ali a aspa crua
        encerraria o atributo."""
        self.assertNotIn('"cia"', self._player())
        self.assertIn("&quot;cia&quot;", self._player())

    # ------------------------------------------- a velocidade declarada
    def test_a_frase_da_fonte_aparece_no_lugar_do_traco(self):
        """Sem isto o Max aparece com a entrega vazia, que e menos
        verdade do que a frase que a operadora escreveu."""
        html = self._player()
        self.assertIn(FRASE, html)
        self.assertIn('class="declarada"', html)

    def test_a_frase_nao_vira_numero(self):
        """Ela NAO passa por entregaDe: nao ordena tabela, nao divide
        R$/Mbps e nao vira ponto de grafico. Era exatamente isso que o
        400 falso fazia antes de ser tirado."""
        html = self._player()
        # a linha do Max tem R$/un. vazio, e nao 249/400
        self.assertNotIn("0,62", html)
        self.assertNotIn(">400<", html)

    def test_sem_frase_continua_saindo_o_traco(self):
        """Quem nao declara nada segue com o traco: a frase e opcional e
        a ausencia dela nao pode virar texto vazio nem "undefined"."""
        self.assertNotIn("undefined", self._player())


if __name__ == "__main__":
    unittest.main(verbosity=2)
