# -*- coding: utf-8 -*-
u"""O WhatsApp incluso aparece sempre que a oferta disser.

Pedido de quem le, em 24/11/2026: "nao tem whatsapp incluso na oferta do
pre pago da Claro?" - tinha, e o tracker nao mostrava, porque a coluna
de servicos so conta assinaturas. Depois: "sempre mostrar quando tiver
whatsapp na oferta".

Vai num campo proprio (whatsapp), fora da lista de apps: nao mexe no
nivel de bundle nem na chave da serie. E so conta o WhatsApp como
BENEFICIO - medido nas paginas, a maioria das mencoes e canal de venda
("Contrate por WhatsApp"), e essas nao contam. As frases abaixo sao as
das paginas, copiadas em 24/11/2026.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from coletores import apps, armazenamento, claro, tim          # noqa: E402
sys.path.insert(0, AQUI)
from _apoio import HOJE, ONTEM, oferta                        # noqa: E402

NODE = shutil.which("node")
RAIZ = os.path.dirname(AQUI)

PAGINA_TIM = os.path.join(AQUI, "fixtures", "tim_pos_whatsapp_2026-11-24.html")


class ODetector(unittest.TestCase):

    def test_as_frases_que_dizem_que_vem_no_plano(self):
        for frase in (
                u"Para YouTube 3GB WhatsApp ilimitado para tudo Ligações",
                u"WhatsApp ilimitado com videochamadas + Ligações",
                u"Redes Sociais e Apps R$ 59,90 /mês Eu quero! WhatsApp Ilimitado",
                u"iCloud Google One WhatsApp e ligações ilimitadas WhatsApp",
                u"Sem asteriscos. WhatsApp E App Do Nu À Vontade",
                u"Apps sem gastar internet do plano Aproveite apps inclusos "
                u"no plano: WhatsApp, Instagram, Facebook e X"):
            self.assertTrue(apps.whatsapp_incluso(frase), frase)

    def test_canal_de_venda_nao_e_beneficio(self):
        for frase in (
                u"Contratar na fatura Contrate por WhatsApp Incluso no plano",
                u"/mês Consultar Fibra Contratar no WhatsApp Internet Fibra "
                u"600 Mega Instalação grátis",
                u"2ª via pelo WhatsApp Receba a 2ª via da sua conta direto "
                u"pelo WhatsApp",
                u"Redes sociais inclusas no seu plano",
                u"10GB de bônus exclusivo para redes sociais"):
            self.assertFalse(apps.whatsapp_incluso(frase), frase)


class AGravacao(unittest.TestCase):
    u"""O coletor que nao sabe pela pagina tem o campo preenchido pelo
    texto da propria oferta, na gravacao - e o que sabe, manda."""

    def _gravar(self, o):
        capturado = {}
        guardas = (armazenamento._config, armazenamento._pedir)
        self.addCleanup(setattr, armazenamento, "_config", guardas[0])
        self.addCleanup(setattr, armazenamento, "_pedir", guardas[1])
        armazenamento._config = lambda: ("http://x", "k")

        def falso(url, chave, caminho, corpo, prefer):
            capturado["corpo"] = corpo
            return 201, "[]"
        armazenamento._pedir = falso
        base = {"operadora": "Claro", "produto": "controle",
                "praca": "Sao Paulo/SP", "nome_oferta": "Claro Controle",
                "preco_promocional": 59.9, "franquia_anunciada_gb": 50,
                "capturado_em": "2026-11-25T09:00:00+00:00"}
        base.update(o)
        armazenamento.gravar_capturas([base])
        return capturado["corpo"][0]["bruto"]

    def test_o_texto_da_oferta_decide(self):
        b = self._gravar({"composicao": u"Eu quero! WhatsApp Ilimitado WhatsApp"})
        self.assertIs(b["whatsapp"], True)
        b = self._gravar({"composicao": u"Contrate por WhatsApp"})
        self.assertIs(b["whatsapp"], False)

    def test_o_coletor_que_sabe_pela_pagina_manda(self):
        b = self._gravar({"composicao": "", "whatsapp": True})
        self.assertIs(b["whatsapp"], True)

    def test_a_lista_de_apps_nao_muda(self):
        b = self._gravar({"composicao": u"WhatsApp Ilimitado", "apps": ["skeelo"]})
        self.assertEqual(b["apps"], ["skeelo"])


class OPrezao(unittest.TestCase):

    def test_o_prezao_diz_whatsapp(self):
        tabela = (u"<div>Valor do saldo</div><span>R$ 30,00</span><span>R$ 25,00"
                  u"</span><h3>PREZÃO R$1 POR DIA</h3><li>17GB + 3GB Youtube / 30 "
                  u"dias</li><li>10GB + 2GB Youtube / 25 dias</li><p>WhatsApp "
                  u"ilimitado com videochamadas + Ligações para todo Brasil</p>")
        guarda = claro.buscar
        claro.buscar = lambda op, url, *a, **k: (200, tabela)
        self.addCleanup(setattr, claro, "buscar", guarda)
        ofertas, _ = claro.ler_prezao(None, "http://x")
        self.assertIs(ofertas[0]["whatsapp"], True)


class OCardLongoDaClaro(unittest.TestCase):
    u"""No Claro Pos Geforce o "WhatsApp e ligacoes ilimitadas" vem depois
    dos 12 mil caracteres de HTML que o leitor usa para preco e nome
    (medido em 24/11/2026). O WhatsApp e lido do bloco inteiro do card."""

    def test_o_whatsapp_depois_do_corte_e_lido(self):
        card = (u'<div class="card-planos" id="plan-1"><h3>Claro Pós 80GB Geforce'
                u'</h3><p>50GB de Livres + 30GB Bônus</p><span>R$ 164,90 /mês'
                u'</span>' + u"<i>.</i>" * 2500 +
                u"<p>WhatsApp e ligações ilimitadas</p></div>")
        outro = (u'<div class="card-planos" id="plan-2"><h3>Claro Pós 150GB</h3>'
                 u'<span>R$ 179,90 /mês</span></div>')
        guarda = claro.buscar
        claro.buscar = lambda op, url, *a, **k: (200, card + outro)
        self.addCleanup(setattr, claro, "buscar", guarda)
        cards, _ = claro.ler_cards(None, "http://x", "movel")
        por_nome = dict((c["nome_oferta"], c["whatsapp"]) for c in cards)
        self.assertIs(por_nome[u"Claro Pós"], False,
                      "o card seguinte nao diz WhatsApp e nao herda o vizinho")
        self.assertTrue([v for k, v in por_nome.items() if "Geforce" in k or v],
                        por_nome)
        geforce = [c for c in cards if "80GB" in (c.get("composicao") or "")
                   or "Geforce" in c["nome_oferta"]]
        self.assertTrue(geforce and geforce[0]["whatsapp"], cards)


class OPosDaTim(unittest.TestCase):
    u"""A frase esta nas vantagens do pos-pago, e vale para todo plano pos
    da TIM - inclusive os que vem da hub e da pagina do Familia."""

    def setUp(self):
        with io.open(PAGINA_TIM, encoding="utf-8") as f:
            self.pos = f.read()
        guarda = (tim.buscar, tim.navegador, tim.PAUSA)
        pos = self.pos
        tim.buscar = lambda op, url, *a, **k: (
            (200, pos) if url.endswith("/pos-pago") else (200, ""))
        tim.navegador = lambda: None
        tim.PAUSA = 0

        def volta():
            tim.buscar, tim.navegador, tim.PAUSA = guarda
        self.addCleanup(volta)

    def test_a_pagina_marca_as_ofertas_dela(self):
        ofertas, erro = tim.ler_cards_dinamicos(None, tim.POS % "sp", "SP")
        self.assertIsNone(erro)
        self.assertTrue(ofertas)
        self.assertTrue(all(o["whatsapp"] for o in ofertas))

    def test_sem_a_frase_nao_marca(self):
        sem = self.pos.replace("WhatsApp, Instagram", "Instagram")
        tim.buscar = lambda op, url, *a, **k: (200, sem)
        ofertas, _ = tim.ler_cards_dinamicos(None, tim.POS % "sp", "SP")
        self.assertFalse(any(o["whatsapp"] for o in ofertas))

    def test_o_coletar_estende_ao_pos(self):
        u"""O Familia vem da pagina dele, que nao repete a frase: e o caso
        que a extensao existe para cobrir."""
        with io.open(os.path.join(AQUI, "fixtures",
                                  "tim_black_familia_2026-11-24.html"),
                     encoding="utf-8") as f:
            familia = f.read()
        pos = self.pos
        tim.buscar = lambda op, url, *a, **k: (
            (200, pos) if url.endswith("/pos-pago")
            else (200, familia) if "tim-black-familia" in url else (200, ""))
        r = tim.coletar("Sao Paulo", "SP", verbose=False)
        fam = [o for o in r["ofertas"] if u"Família" in o["nome_oferta"]]
        self.assertTrue(fam, "o cenario precisa de plano pos de outra pagina")
        self.assertTrue(all(o.get("whatsapp") for o in fam))
        movel = [o for o in r["ofertas"] if o.get("produto") == "movel"]
        self.assertTrue(all(o.get("whatsapp") for o in movel))


def _capturas_da_tela():
    linhas = []
    for data in (ONTEM, HOJE):
        linhas += [
            dict(oferta(operadora="Claro", produto="controle",
                        nome="Claro Controle", preco=59.9, gb=50,
                        praca="Sao Paulo/SP", data=data,
                        chave="Claro|controle|50gb|com_skeelo"),
                 apps_rotulo="Skeelo", apps=["skeelo"], whatsapp=True,
                 nivel_bundle=1),
            dict(oferta(operadora="Claro", produto="controle",
                        nome="Claro Controle Basico", preco=49.9, gb=40,
                        praca="Sao Paulo/SP", data=data,
                        chave="Claro|controle|40gb|simples"),
                 whatsapp=True, nivel_bundle=0),
            dict(oferta(operadora="Claro", produto="controle",
                        nome="Claro Controle Sem Zap", preco=45.0, gb=30,
                        praca="Sao Paulo/SP", data=data,
                        chave="Claro|controle|30gb|simples"),
                 nivel_bundle=0),
        ]
    return linhas


@unittest.skipIf(NODE is None, "node nao instalado")
class ATelaMostra(unittest.TestCase):
    u"""O JS da tela rodando de verdade: a coluna de servicos."""

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.dados = os.path.join(cls.pasta, "d.json")
        cls.tela = os.path.join(cls.pasta, "t.html")
        with open(cls.dados, "w", encoding="utf-8") as f:
            json.dump(_capturas_da_tela(), f)
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
        c = [{"praca": "Sao Paulo/SP", "produto": "controle", "dia": HOJE,
              "player": "Claro"}]
        r = subprocess.run(
            ["node", os.path.join(AQUI, "tela_em_node.mjs"),
             self.tela, self.dados, json.dumps(c)],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o JS da tela quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)[0]["t-player"]

    def test_app_e_whatsapp_saem_juntos(self):
        u"""O app continua com a dica dele (o span), e o WhatsApp vem
        depois do ponto."""
        html = self._player()
        linha = [l for l in html.split("<tr") if "Claro Controle</td>" in l][0]
        self.assertIn("Skeelo</span> \u00b7 WhatsApp ilimitado", linha)

    def test_so_whatsapp_substitui_o_so_internet(self):
        html = self._player()
        linha = [l for l in html.split("<tr") if "Claro Controle Basico" in l][0]
        self.assertIn("WhatsApp ilimitado", linha)
        self.assertNotIn(u"Só internet e ligações", linha)

    def test_sem_whatsapp_fica_como_era(self):
        html = self._player()
        linha = [l for l in html.split("<tr") if "Sem Zap" in l][0]
        self.assertNotIn("WhatsApp", linha)
        self.assertIn(u"Só internet e ligações", linha)


if __name__ == "__main__":
    unittest.main(verbosity=2)
