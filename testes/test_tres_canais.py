# -*- coding: utf-8 -*-
"""Os tres canais tem de dizer a mesma coisa sobre a mesma oferta.

POR QUE ESTE ARQUIVO EXISTE, e ele e a licao mais cara da semana.

O mesmo dado vira tres coisas: a mensagem do Telegram, o PDF anexo e a
tela publicada. Seis rodadas de auditoria acharam 74 defeitos, e a
maioria esmagadora deles estava na FRONTEIRA entre dois desses canais -
nunca dentro de uma funcao. A mensagem passou a dizer "entrega nao lida"
e o PDF seguiu imprimindo "None" na mesma oferta. A mensagem passou a
dizer "nao deu para ler o estado da coleta" e o PDF seguiu listando as
nove operadoras como "Sem registro". A tela, que ficou seis rodadas sem
ser olhada, tinha dez rotulos afirmando o que o dado nao sustentava.

Cada um desses defeitos foi achado por alguem LENDO o codigo. Nenhum
aparecia em teste, porque cada canal, sozinho, estava certo.

Este arquivo testa o que nenhum deles testava: que eles CONCORDAM. E
inclui a tela, que so e testavel porque tela_em_node.mjs roda o
JavaScript dela num DOM de mentira.

AS OFERTAS SAO AS DIFICEIS, de proposito. Satelite, porque e o unico
produto que mistura Mbps e GB na mesma operadora e foi onde a tela
afirmou "R$/Mbps" sobre linhas em GB. Fibra sem velocidade lida, porque
e o estado da Brisanet em 18 dos 21 dias e onde a mensagem afirmou
"mesma entrega (500 Mbps)" sobre uma entrega que ninguem leu.
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

import robo                                                   # noqa: E402
from _apoio import HOJE, ONTEM, banco, oferta                 # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
NODE = shutil.which("node")

try:
    import relatorio
except ImportError:                                      # pragma: no cover
    relatorio = None


def capturas():
    """Um dia pequeno, com as ofertas que ja quebraram cada canal."""
    linhas = []
    for data in (ONTEM, HOJE):
        # satelite: a unica operadora que mistura as duas unidades
        linhas += [
            oferta(operadora="Starlink", produto="satelite",
                   nome="Starlink Residencial", praca="Brasil/BR",
                   preco=189.0, gb=None, mbps=100, data=data,
                   chave="Starlink|satelite|100mbps|simples"),
            oferta(operadora="Starlink", produto="satelite",
                   nome="Starlink Prioritário 50 GB", praca="Brasil/BR",
                   preco=245.0, gb=50, mbps=None, data=data,
                   chave="Starlink|satelite|50gb|simples"),
            # fibra sem velocidade lida: o estado da Brisanet
            oferta(operadora="Brisanet", produto="fibra",
                   nome="Brisanet 500 Mega", praca="Fortaleza/CE",
                   preco=114.80, gb=None, mbps=None, data=data,
                   chave="Brisanet|fibra|None|simples"),
            # movel comum, para o caso facil tambem estar coberto
            oferta(operadora="Vivo", produto="movel", nome="Vivo Pós",
                   preco=119.90, gb=60, data=data,
                   chave="Vivo|movel|60gb|simples"),
        ]
    # UMA OPERADORA QUE EXISTE NUM DIA E NAO NO OUTRO. Sem isso os dois
    # dias tem a mesma lista e o painel que ignora o seletor de data
    # fica indistinguivel do que o respeita. Era o caso real: a Claro
    # nao foi coletada no pre-pago em 01/10.
    linhas.append(oferta(operadora="Claro", produto="movel",
                         nome="Claro Pós", preco=124.90, gb=50,
                         data=ONTEM, chave="Claro|movel|50gb|simples"))
    return linhas


class ANenhumCanalInventaUnidade(unittest.TestCase):
    """A Starlink vende 100 e 400 Mbps ao lado de 50, 500, 1024 e 2048 GB.

    Nenhum rotulo pode nomear uma das duas como se valesse para todas:
    foi assim que a tela afirmou "R$/Mbps" sobre quatro linhas em R$/GB,
    em 300 de 300 combinacoes de praca e dia, e que a mensagem - antes da
    correcao - chamou os Mbps da Starlink de GB.
    """

    def test_a_mensagem_tira_a_unidade_do_campo(self):
        self.assertEqual(
            robo._unidade({"degrau_mbps": 100, "franquia_anunciada_gb": None}),
            "Mbps")
        self.assertEqual(
            robo._unidade({"degrau_mbps": None, "franquia_anunciada_gb": 50}),
            "GB")

    def test_e_satelite_tem_nome_de_categoria(self):
        # sem isto a mensagem imprimia a chave crua do banco
        self.assertEqual(robo._categoria({"produto": "satelite"}), "Satélite")


@unittest.skipIf(NODE is None, "node nao instalado")
class ATelaDizOMesmoQueAMensagem(unittest.TestCase):
    """A tela so e testavel porque tela_em_node.mjs roda o JS dela.

    Antes deste banco de provas, o terceiro consumidor do dado nao tinha
    teste nenhum - e foi onde a auditoria achou cinco defeitos graves de
    primeira, todos de rotulo.
    """

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
            capture_output=True, text=True, cwd=RAIZ)
        if r.returncode:
            raise unittest.SkipTest("gerar_tela falhou: %s" % r.stderr[-300:])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _ver(self, consultas):
        r = subprocess.run(
            [NODE, os.path.join(AQUI, "tela_em_node.mjs"),
             self.tela, self.dados, json.dumps(consultas)],
            capture_output=True, text=True, cwd=AQUI)
        if r.returncode:
            self.fail("o JS da tela quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)

    def test_unidade_misturada_nao_vira_cabecalho(self):
        """O satelite tem Mbps e GB no mesmo produto: o cabecalho nao
        pode nomear uma das duas."""
        v = self._ver([{"praca": "Brasil/BR", "produto": "satelite",
                        "dia": HOJE}])[0]
        html = v["t-player"]
        self.assertIn("R$/un.", html,
                      "com unidades misturadas o cabecalho degrada")
        self.assertNotIn("R$/Mbps", html)
        self.assertNotIn("R$/GB", html)

    def test_unidade_unica_continua_sendo_nomeada(self):
        v = self._ver([{"praca": "Sao Paulo/SP", "produto": "movel",
                        "dia": HOJE}])[0]
        self.assertIn("R$/GB", v["t-player"])

    def test_o_botao_da_metrica_segue_o_produto(self):
        v = self._ver([
            {"praca": "Brasil/BR", "produto": "satelite", "dia": HOJE},
            {"praca": "Sao Paulo/SP", "produto": "movel", "dia": HOJE},
        ])
        self.assertEqual(v[0]["bt-gb"], "R$/un.")
        self.assertEqual(v[1]["bt-gb"], "R$/GB")

    def test_faixa_nao_se_monta_entre_unidades(self):
        """Na faixa a unidade nao decide so o rotulo: decide os CORTES.
        O tercil chamava 100 Mbps e 50 GB de 'entrega baixa'."""
        v = self._ver([{"praca": "Brasil/BR", "produto": "satelite",
                        "dia": HOJE}])[0]
        self.assertIn("mistura ofertas medidas", v["t-faixas"])

    def test_a_tela_nao_imprime_None(self):
        """A Brisanet sem velocidade: a oferta existe, a entrega nao foi
        lida, e isso sai como ausencia - nunca como o token do Python."""
        v = self._ver([{"praca": "Fortaleza/CE", "produto": "fibra",
                        "dia": HOJE}])[0]
        for proibido in ("None", "undefined", "NaN", "null"):
            self.assertNotIn(proibido, v["t-player"],
                             "%s chegou ao HTML" % proibido)

    def test_e_nenhum_painel_mostra_outro_dia(self):
        """Tres paineis liam o ultimo dia da serie e ignoravam o seletor.

        Medido no dado real: com Data=01/10 e pre-pago em Sao Paulo, um
        painel mostrava 4 ofertas e o de baixo mostrava 7, incluindo a
        Claro - num dia em que a Claro nao foi coletada no pre-pago. A
        tela afirmava um R$/GB da Claro num dia sem oferta da Claro.

        O teste le os DATASETS, e nao a tabela: os tres paineis sao
        graficos, e a primeira versao deste teste olhava a tabela da
        outra aba - o provador de mutacoes mostrou que ele nao via nada.
        """
        # ONTEM tem Claro e Vivo; HOJE tem so Vivo
        v = self._ver([{"praca": "Sao Paulo/SP", "produto": "movel",
                        "dia": HOJE, "aba": "panorama"}])[0]
        for painel in ("c-quadrante", "c-dispersao", "c-unitario"):
            g = v["graficos"].get(painel)
            self.assertTrue(g, "o painel %s nao desenhou" % painel)
            quem = set(g["series"]) | set(g["rotulos"])
            self.assertNotIn("Claro", quem,
                             "%s mostra uma operadora que nao foi "
                             "coletada no dia selecionado" % painel)

    def test_e_o_dia_anterior_mostra_as_duas(self):
        """O contrario tambem: selecionando o dia em que a Claro existe,
        os tres paineis tem de mostra-la."""
        v = self._ver([{"praca": "Sao Paulo/SP", "produto": "movel",
                        "dia": ONTEM, "aba": "panorama"}])[0]
        for painel in ("c-dispersao", "c-unitario"):
            g = v["graficos"].get(painel)
            quem = set(g["series"]) | set(g["rotulos"])
            self.assertIn("Claro", quem, painel)

    def test_o_eixo_nao_nomeia_unidade_misturada(self):
        """GB e Mbps no mesmo eixo X, titulado "Mbps", embaixo de uma
        legenda que diz "mais a direita entrega mais"."""
        v = self._ver([{"praca": "Brasil/BR", "produto": "satelite",
                        "dia": HOJE, "aba": "panorama"}])[0]
        for painel in ("c-quadrante", "c-dispersao"):
            g = v["graficos"].get(painel)
            if not g:
                continue
            self.assertNotIn(g["eixoX"], ("Mbps", "GB"),
                             "%s nomeia uma das duas unidades" % painel)


@unittest.skipIf(relatorio is None, "reportlab nao instalado")
class OPdfDizOMesmoQueAMensagem(unittest.TestCase):
    """A frase sobre uma oferta mora no EVENTO, e os dois canais leem.

    Montada em dois lugares, ela divergiu duas vezes: a mensagem dizia
    "entrega nao lida" e o PDF imprimia "None"; a mensagem dizia "nao deu
    para ler o estado da coleta" e o PDF listava nove "Sem registro".
    """

    def test_o_texto_da_oferta_e_o_mesmo_nos_dois(self):
        banco(capturas())
        texto, dados = robo.montar_mensagem(HOJE, ONTEM)
        for grupo in ("remodeladas", "leitura"):
            for e in (dados.get(grupo) or []):
                # o que o PDF imprime e exatamente o que a mensagem diz
                self.assertIn(e["texto_preco"], texto + " ")
                self.assertNotIn("None", e["texto_entrega"])

    def test_e_a_unidade_vem_do_evento_nos_dois(self):
        banco(capturas())
        _t, dados = robo.montar_mensagem(HOJE, ONTEM)
        for grupo in ("grades", "voltaram", "remodeladas"):
            for e in (dados.get(grupo) or []):
                self.assertIn(e.get("unidade"), ("GB", "Mbps", ""),
                              "unidade de %s" % grupo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
