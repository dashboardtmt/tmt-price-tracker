# -*- coding: utf-8 -*-
u"""O canal da leitura duvidosa, do coletor ate o leitor.

ELE EXISTIA ABERTO DE UM LADO SO. avisos_oferta e escrito por quatro
coletores, em sete lugares:

  claro.py       o preco do beneficio entrou no lugar do preco do plano
  claro.py       nomes repetidos com precos diferentes
  claro_flex.py  o card declara bonus e nao diz quanto e do plano
  tim_fit.py     o total anual da etiqueta nao fecha com preco x meses
  vivo.py        o regulamento e de outra oferta que divide o codigo
  vivo.py        a franquia do regulamento contradiz a do card

O campo ia para o bruto, que o Postgres guarda. E NINGUEM NUNCA O LEU -
nao estava no select de _indexar, nem no exportar, nem na mensagem, nem
no relatorio, nem na tela. Grep no projeto em 25/10/2026: sete escritas,
zero leituras.

Ou seja: houve dias em que a Vivo publicou o mesmo codigo Anatel em
varias ofertas, o coletor percebeu, recusou os campos contratuais com
todas as palavras - e a unica consequencia foi um campo vazio na tela,
sem ninguem saber por que. "Falha vira buraco, nao vira numero" estava
cumprido pela metade: o numero nao saiu errado, e o buraco nao foi
anunciado.

MEDIDO AO VIVO NO DIA EM QUE O CANAL FECHOU: 9 das 49 ofertas da Vivo em
Sao Paulo, e 1 das 18 da Claro. Vezes as 20 pracas, sao cerca de 180
linhas por dia de campo contratual recusado em silencio.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import HOJE, ONTEM, dados, em_todas, montar, oferta  # noqa: E402
from _apoio import sem_declaracao  # noqa: E402

from coletores import apps  # noqa: E402
import robo  # noqa: E402

RECUSA = (u"regulamento diz R$ 270,00 de tabela, abaixo dos R$ 290,00 da "
          u"vitrine: o documento é de outra oferta que divide o mesmo "
          u"código Anatel, e nenhum campo contratual dele foi usado")


def com_recusa(data, quantas=3, avisos=None, **kw):
    """Ofertas da Vivo, as primeiras com a recusa do coletor no bruto."""
    linhas = em_todas(operadora="Vivo", produto="combo", nome="Vivo Família 2",
                      preco=290.0, gb=None, mbps=700, data=data, **kw)
    for l in linhas[:quantas]:
        l["avisos_oferta"] = [RECUSA] if avisos is None else avisos
    return linhas


class ACoisaQueOColetorRecusouLerSaiDita(unittest.TestCase):
    def setUp(self):
        sem_declaracao(self)

    def test_a_mensagem_diz_o_motivo(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("leitura com ressalva", t)
        self.assertIn("nenhum campo contratual dele foi usado", t)

    def test_e_diz_a_operadora_e_o_produto(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("Combo · Vivo · leitura com ressalva", t)

    def test_e_diz_em_quantas_pracas(self):
        """A ressalva segue a regra de toda linha da mensagem."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE, quantas=3))
        # com poucas pracas, _onde nomeia as cidades em vez de so
        # contar - e a informacao que o usuario pediu
        self.assertIn("em 3 de 20:", t)
        self.assertIn("Sao Paulo", t)

    def test_dia_sem_recusa_nao_tem_a_linha(self):
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE))
        self.assertNotIn("ressalva", t)

    def test_nao_entra_na_contagem_de_mudancas(self):
        """Nada mudou na vitrine: foi a nossa leitura que disse "nao
        sei". Contar como mudanca faria a mensagem anunciar movimento
        de mercado onde nao houve."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("Nenhuma mudança de preço, composição ou nome", t)

    def test_o_mesmo_motivo_em_varias_ofertas_sai_uma_vez(self):
        t = montar(com_recusa(ONTEM, quantas=5), com_recusa(HOJE, quantas=5))
        self.assertEqual(t.count("leitura com ressalva"), 1)

    def test_motivos_diferentes_na_mesma_operadora_viram_um_grupo(self):
        """O grupo e (operadora, produto), e os motivos distintos viajam
        numa lista.

        Agrupar pelo TEXTO do motivo nao agrupava nada: ele embute os
        valores da oferta ("declara 25 GB para um card de 15 GB"), e
        medido na coleta real de 25/10/2026 dez ofertas renderam dez
        grupos - parede de quase-repeticoes escondendo que eram dois
        problemas.
        """
        hoje = com_recusa(HOJE, quantas=2)
        hoje[3]["avisos_oferta"] = [u"o card não declarou composição"]
        d = dados(com_recusa(ONTEM), hoje)
        self.assertEqual(len(d["duvidosa"]), 1)
        self.assertEqual(len(d["duvidosa"][0]["motivos"]), 2)
        self.assertEqual(d["duvidosa"][0]["quantas"], 3, "tres ofertas")

    def test_operadoras_diferentes_saem_separadas(self):
        hoje = com_recusa(HOJE, quantas=2)
        outra = em_todas(operadora="Claro", produto="fibra",
                         nome="Claro Fibra", preco=99.9, gb=None, mbps=500,
                         data=HOJE)
        outra[0]["avisos_oferta"] = [u"nomes repetidos com preços diferentes"]
        d = dados(com_recusa(ONTEM) + em_todas(operadora="Claro",
                                               produto="fibra",
                                               nome="Claro Fibra",
                                               preco=99.9, gb=None, mbps=500,
                                               data=ONTEM),
                  hoje + outra)
        self.assertEqual(len(d["duvidosa"]), 2)

    def test_a_mensagem_diz_quantos_outros_motivos_ha(self):
        hoje = com_recusa(HOJE, quantas=2)
        hoje[3]["avisos_oferta"] = [u"o card não declarou composição"]
        t = montar(com_recusa(ONTEM), hoje)
        self.assertIn("e mais 1 motivo nesta operadora", t)

    def test_uma_oferta_com_dois_avisos_conta_uma_vez(self):
        """Contar aviso em vez de oferta inflaria o tamanho do buraco."""
        hoje = com_recusa(HOJE, quantas=1)
        hoje[0]["avisos_oferta"] = [RECUSA, u"e outra coisa também"]
        d = dados(com_recusa(ONTEM, quantas=0), hoje)
        self.assertEqual(d["duvidosa"][0]["quantas"], 1)
        self.assertEqual(len(d["duvidosa"][0]["motivos"]), 2)

    def test_a_contagem_por_motivo_esta_certa(self):
        d = dados(com_recusa(ONTEM), com_recusa(HOJE, quantas=4))
        self.assertEqual(d["duvidosa"][0]["quantas"], 4)

    def test_aviso_em_texto_e_nao_em_lista_tambem_vale(self):
        """O bruto pode devolver string quando o coletor grava um
        aviso so."""
        d = dados(com_recusa(ONTEM), com_recusa(HOJE, quantas=2,
                                                avisos=RECUSA))
        self.assertEqual(d["duvidosa"][0]["quantas"], 2)

    def test_o_grupo_viaja_para_o_relatorio(self):
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertTrue(d.get("duvidosa"))
        g = d["duvidosa"][0]
        for campo in ("motivo", "operadora", "produto", "categoria",
                      "quantas", "onde"):
            self.assertIn(campo, g)


class OPdfNaoCaiComOTextoDoColetor(unittest.TestCase):
    """reportlab le o Paragraph como mini-HTML.

    O texto do aviso vem do coletor, e um "&" nele derrubaria a geracao
    do PDF inteira - e o anexo que falha e problema, mas o aviso que nao
    sai e maior. Este teste existe porque a secao nova entrou no
    relatorio chamando _escapar e CATEGORIA, que nao existem la, e a
    suite ficou VERDE: nenhum teste gerava o PDF com ressalva.
    """

    def _gerar(self, motivo):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab nao instalado")
        import relatorio

        hoje = com_recusa(HOJE, quantas=2, avisos=[motivo])
        d = dados(com_recusa(ONTEM, quantas=0), hoje)
        entradas = {chave: [] for chave, _rot in relatorio.PRODUTOS}
        caminho = relatorio.gerar(d, entradas,
                                  os.path.join(os.path.dirname(__file__),
                                               "_ressalva.pdf"))
        self.assertTrue(caminho and os.path.exists(caminho))
        self.addCleanup(lambda: os.path.exists(caminho)
                        and os.remove(caminho))
        return os.path.getsize(caminho)

    def test_o_pdf_sai_com_a_secao_da_ressalva(self):
        self.assertGreater(self._gerar(RECUSA), 1000)

    def test_e_sai_com_e_comercial_no_motivo(self):
        self.assertGreater(
            self._gerar(u"o card diz \"TV & apps\" e não diz o preço"), 1000)

    def test_e_com_tag_aberta_no_motivo(self):
        """MEDIDO: o reportlab aguenta "&", "<vazio>" e
        "a & b < c > d" sem reclamar - ele estoura em TAG ABERTA,
        como "um <b>negrito". Era este o caractere a testar; os dois
        testes anteriores mediam o caminho e nao o escape, e por
        isso a mutacao Q7 passava verde.
        """
        self.assertGreater(
            self._gerar(u"o card trazia <b>Max sem fechar a marcação"),
            1000)


class ORegulamentoSomaOAvisoSemEstourar(unittest.TestCase):
    u"""setdefault numa chave que vale None derruba a coleta inteira.

    O DEFEITO QUE EU INTRODUZI nesta sessao. Ao ligar o canal, passei a
    gravar "avisos_oferta" no dicionario da oferta da Vivo, e o valor e
    None quando nao ha aviso - ausencia e ausencia, nao lista vazia. Os
    dois trechos do regulamento usavam

        oferta.setdefault("avisos_oferta", []).append(...)

    e setdefault NAO substitui None: encontra a chave, devolve None, e o
    .append estoura. A coleta da Vivo morria com "'NoneType' object has
    no attribute 'append'".

    A suite ficou VERDE com isso - nenhum teste chamava
    aplicar_regulamento numa oferta que ja tivesse a chave. Rodar o
    coletor de verdade e o que pegou, e e isso que este teste substitui.
    """

    def _reg(self, oferta):
        from coletores import vivo

        # O CAMPO E precoSemDescontos, nao "precoTabela". Montei o
        # regulamento pelo nome errado e o aviso nunca disparava: o
        # teste media um caminho que nao era exercitado.
        reg = {"precoSemDescontos": "100,00"}
        return vivo.aplicar_regulamento(oferta, reg)

    def test_chave_presente_valendo_none_nao_estoura(self):
        o = self._reg({"nome_oferta": "X", "preco_promocional": 290.0,
                       "avisos_oferta": None})
        self.assertTrue(o["avisos_oferta"], "o aviso tem de entrar")

    def test_e_nao_apaga_o_aviso_que_ja_havia(self):
        o = self._reg({"nome_oferta": "X", "preco_promocional": 290.0,
                       "avisos_oferta": ["um aviso anterior"]})
        self.assertIn("um aviso anterior", o["avisos_oferta"])
        self.assertGreater(len(o["avisos_oferta"]), 1)

    def test_chave_ausente_tambem_funciona(self):
        o = self._reg({"nome_oferta": "X", "preco_promocional": 290.0})
        self.assertTrue(o["avisos_oferta"])

    def test_o_valor_sai_em_reais_e_com_acento(self):
        """O texto passou a sair no Telegram quando o canal ganhou
        leitor: "R$ 1200.00" ao lado de "R$ 1.200,00" denuncia que as
        duas frases foram escritas em epocas diferentes."""
        o = self._reg({"nome_oferta": "X", "preco_promocional": 1500.0,
                       "avisos_oferta": None})
        junto = " ".join(o["avisos_oferta"])
        self.assertIn("R$ 1.500,00", junto)
        self.assertIn("código", junto)


class OAvisoDaLeituraLargaDeApps(unittest.TestCase):
    u"""O descarte por limite deixa de ser lista vazia calada.

    apps_do_texto descarta a leitura quando acha mais apps que o limite,
    e a decisao esta certa - "um texto que contem oito streamings quase
    nunca e uma oferta com oito". O jeito de contar nao estava: devolvia
    [], e [] quer dizer "nenhum app nomeado", que e nivel 0, que na tela
    e "sem assinatura inclusa".
    """

    SETE = (u"Netflix, Disney+, Spotify, Globoplay, Paramount+, Max e "
            u"Telecine inclusos")

    def test_acima_do_limite_o_motivo_sai(self):
        aviso = apps.aviso_de_leitura(self.SETE)
        self.assertTrue(aviso)
        self.assertIn("7 aplicativos", aviso)
        self.assertIn("acima do limite", aviso)

    def test_e_a_lista_continua_vazia(self):
        """Eleger seis dos oito seria o sorteio que o projeto recusa."""
        self.assertEqual(apps.apps_do_texto(self.SETE), [])

    def test_no_limite_nao_ha_aviso(self):
        seis = self.SETE.replace(u"Max e Telecine", u"Max")
        self.assertIsNone(apps.aviso_de_leitura(seis))
        self.assertEqual(len(apps.apps_do_texto(seis)), 6)

    def test_texto_comum_nao_rende_aviso(self):
        self.assertIsNone(apps.aviso_de_leitura(u"Netflix incluso"))
        self.assertIsNone(apps.aviso_de_leitura(""))
        self.assertIsNone(apps.aviso_de_leitura(None))


class AJuntadaNaoApagaOQueJaHavia(unittest.TestCase):
    """A Claro e a Vivo gravam avisos por outros motivos no mesmo campo."""

    def test_soma_sem_apagar(self):
        self.assertEqual(apps.juntar_avisos(["um"], "dois"), ["um", "dois"])

    def test_aceita_texto_no_lugar_de_lista(self):
        self.assertEqual(apps.juntar_avisos("um", "dois"), ["um", "dois"])

    def test_nao_repete_o_mesmo_aviso(self):
        self.assertEqual(apps.juntar_avisos(["um"], "um"), ["um"])

    def test_sem_nada_devolve_ausencia_e_nao_lista_vazia(self):
        """"[]" compararia igual a "[]" entre dias e esconderia a
        chegada da primeira ressalva."""
        self.assertIsNone(apps.juntar_avisos(None, None))
        self.assertIsNone(apps.juntar_avisos([], None))

    def test_so_o_novo(self):
        self.assertEqual(apps.juntar_avisos(None, "dois"), ["dois"])

    def test_so_o_velho(self):
        self.assertEqual(apps.juntar_avisos(["um"], None), ["um"])


class OIndiceTrazOCampoDoBruto(unittest.TestCase):
    """Sem isto o canal continuaria sem leitor, por mais que o coletor
    escrevesse."""

    def test_o_select_pede_avisos_oferta(self):
        import inspect

        fonte = inspect.getsource(robo._indexar)
        self.assertIn("avisos_oferta:bruto->avisos_oferta", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
