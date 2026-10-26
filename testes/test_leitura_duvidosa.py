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


# A FORMA QUE O COLETOR GRAVA desde 25/10/2026: o rotulo curto, que diz
# O QUE ficou vazio e vai na mensagem, e o texto longo, que explica POR
# QUE e vai no relatorio.
CURTO = (u"o contrato não deu para ler: sem preço de tabela, "
         u"fidelidade, multa e taxas")
AVISO = {"curto": CURTO, "longo": RECUSA}


def com_recusa(data, quantas=3, avisos=None, **kw):
    """Ofertas da Vivo, as primeiras com a recusa do coletor no bruto."""
    linhas = em_todas(operadora="Vivo", produto="combo", nome="Vivo Família 2",
                      preco=290.0, gb=None, mbps=700, data=data, **kw)
    for l in linhas[:quantas]:
        l["avisos_oferta"] = [dict(AVISO)] if avisos is None else avisos
    return linhas


class ACoisaQueOColetorRecusouLerSaiDita(unittest.TestCase):
    u"""A mensagem traz os DETALHES, sem a prosa tecnica do coletor.

    Errei para os dois lados antes de chegar aqui:

      1. despejei o texto longo - quinze linhas de justificativa tecnica
         no Telegram, e o usuario reclamou;
      2. cortei para uma linha so e perdi produto, pracas e o que ficou
         vazio - que era justamente o que ele queria.

    O certo e o meio. Cada ressalva nasce no coletor com duas formas: o
    rotulo CURTO, que diz O QUE ficou vazio e vai na mensagem, e o texto
    LONGO, que explica POR QUE e vai no relatorio.
    """

    def setUp(self):
        sem_declaracao(self)

    def test_abre_com_o_produto_e_a_operadora(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("Combo \u00b7 Vivo \u00b7 nada mudou, mas faltou dado", t)

    def test_conta_OFERTA_e_nao_linha(self):
        """A MESMA oferta em tres pracas e UMA oferta.

        Todos os outros blocos dizem "2 mudancas" para duas ofertas
        e poem a praca em separado. Este dizia "100 ofertas, em
        todas as 20 pracas", e 100 era 5 vezes 20 - a praca contada
        duas vezes na mesma linha, o que fazia a ressalva parecer
        enorme. Sao 5.
        """
        t = montar(com_recusa(ONTEM), com_recusa(HOJE, quantas=3))
        self.assertIn("1 oferta, em 3 de 20", t)
        self.assertNotIn("3 ofertas,", t)

    def test_diz_o_que_ficou_vazio(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("sem pre\u00e7o de tabela, fidelidade, multa e "
                      "taxas", t)

    def test_e_NAO_diz_por_que(self):
        """O "por que" e prosa de depuracao, e o lugar dele e o PDF."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertNotIn("nenhum campo contratual dele foi usado", t)
        self.assertNotIn("divide o mesmo", t)

    def test_uma_oferta_so_fala_no_singular(self):
        t = montar(com_recusa(ONTEM, quantas=0), com_recusa(HOJE, quantas=1))
        self.assertIn("1 oferta,", t)

    def test_dia_sem_recusa_nao_tem_o_bloco(self):
        t = montar(em_todas(data=ONTEM), em_todas(data=HOJE))
        self.assertNotIn("nada mudou, mas faltou dado", t)

    def test_nao_entra_na_contagem_de_mudancas(self):
        """Nada mudou na vitrine: foi a nossa leitura que disse "nao
        sei". Contar como mudanca faria a mensagem anunciar movimento de
        mercado onde nao houve."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("Nenhuma mudan\u00e7a de pre\u00e7o, composi\u00e7\u00e3o ou nome", t)

    def test_rotulos_diferentes_na_mesma_operadora_saem_juntos(self):
        hoje = com_recusa(HOJE, quantas=2)
        hoje[3]["avisos_oferta"] = [
            {"curto": u"franquia garantida ficou vazia",
             "longo": u"o card declara b\u00f4nus e n\u00e3o diz quanto \u00e9 do plano"}]
        t = montar(com_recusa(ONTEM), hoje)
        # a ordem e alfabetica, de proposito: ordem instavel mudaria a
        # mensagem de um dia para o outro sem nada ter mudado
        self.assertIn("franquia garantida ficou vazia; o contrato", t)
        self.assertIn("sem preço de tabela", t)

    def test_operadoras_diferentes_saem_em_blocos_separados(self):
        hoje = com_recusa(HOJE, quantas=2)
        outra = em_todas(operadora="Claro", produto="fibra",
                         nome="Claro Fibra", preco=99.9, gb=None, mbps=500,
                         data=HOJE)
        outra[0]["avisos_oferta"] = [
            {"curto": u"nomes repetidos com pre\u00e7os diferentes",
             "longo": u"nomes repetidos com precos diferentes: Claro Fibra"}]
        ontem = (com_recusa(ONTEM)
                 + em_todas(operadora="Claro", produto="fibra",
                            nome="Claro Fibra", preco=99.9, gb=None,
                            mbps=500, data=ONTEM))
        t = montar(ontem, hoje + outra)
        self.assertIn("Combo \u00b7 Vivo \u00b7 nada mudou, mas faltou dado", t)
        self.assertIn("Fibra \u00b7 Claro \u00b7 nada mudou, mas faltou dado", t)

    def test_acima_de_tres_blocos_o_resto_vai_para_o_relatorio(self):
        """O mesmo corte que todos os outros blocos da mensagem usam."""
        linhas, ontem = [], []
        for i, (op, prod) in enumerate((("Vivo", "combo"), ("Vivo", "movel"),
                                        ("Claro", "fibra"),
                                        ("TIM", "controle"))):
            base = dict(operadora=op, produto=prod, nome="%s %d" % (op, i),
                        preco=100.0 + i, gb=50, mbps=None)
            ontem += em_todas(data=ONTEM, **base)
            novas = em_todas(data=HOJE, **base)
            novas[0]["avisos_oferta"] = [
                {"curto": u"um campo ficou vazio", "longo": u"por isso e aquilo"}]
            linhas += novas
        t = montar(ontem, linhas)
        self.assertIn("e mais 1 oferta com ressalva de leitura, no "
                      "relat\u00f3rio", t)

    def test_a_string_antiga_continua_valendo(self):
        """O historico nao se reescreve, e a string E o texto longo.

        Ela vale como motivo (relatorio) e rende o rotulo GENERICO na
        mensagem - nunca a prosa. A regra "a mensagem nao imprime o
        texto longo" vale sem excecao, inclusive para os dias
        anteriores.
        """
        d = dados(com_recusa(ONTEM), com_recusa(HOJE, quantas=2,
                                                avisos=[RECUSA]))
        # duas PRACAS da mesma oferta sao UMA oferta
        self.assertEqual(d["duvidosa"][0]["quantas"], 1)
        self.assertEqual(d["duvidosa"][0]["motivos"], [RECUSA])
        self.assertEqual(d["duvidosa"][0]["curtos"],
                         [u"um campo do contrato não deu para ler"])

    def test_a_prosa_nunca_chega_na_mensagem_nem_sem_rotulo(self):
        """O ROTULO QUE FALTA DEGRADA PARA O GENERICO, nao para a prosa.

        A mutacao S4 - coletor que para de declarar o rotulo - passava
        verde porque _duas_formas caia de volta no texto longo. Era
        defensivo e tinha o pior efeito possivel: a justificativa
        tecnica voltava para o Telegram em silencio.
        """
        t = montar(com_recusa(ONTEM),
                   com_recusa(HOJE, quantas=2,
                              avisos=[{"curto": "", "longo": RECUSA}]))
        self.assertIn(u"um campo do contrato não deu para ler", t)
        self.assertNotIn("nenhum campo contratual dele foi usado", t)

    def test_o_longo_vai_para_o_relatorio(self):
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        g = d["duvidosa"][0]
        self.assertIn("nenhum campo contratual", " ".join(g["motivos"]))
        self.assertNotIn("nenhum campo contratual", " ".join(g["curtos"]))

    def test_uma_oferta_com_dois_avisos_conta_uma_vez(self):
        """Contar aviso em vez de oferta inflaria o tamanho do buraco."""
        hoje = com_recusa(HOJE, quantas=1)
        hoje[0]["avisos_oferta"] = [
            {"curto": u"um", "longo": u"um por que"},
            {"curto": u"dois", "longo": u"dois por que"}]
        d = dados(com_recusa(ONTEM, quantas=0), hoje)
        self.assertEqual(d["duvidosa"][0]["quantas"], 1)
        self.assertEqual(len(d["duvidosa"][0]["curtos"]), 2)

    def test_o_grupo_viaja_com_tudo(self):
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        g = d["duvidosa"][0]
        for campo in ("motivo", "motivos", "curtos", "operadora", "produto",
                      "categoria", "quantas", "onde"):
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

    def test_o_coletor_declara_O_QUE_ficou_vazio(self):
        """O ROTULO DA VIVO, medido no proprio coletor.

        A mutacao S4 - o coletor para de declarar o rotulo - passava
        verde porque nenhum teste olhava o que vivo.py escreve: os
        testes do rotulo curto usam o fixture, que tem rotulo proprio.
        Peca sem montagem, no sentido do dado.
        """
        from coletores import apps as _apps

        o = self._reg({"nome_oferta": "X", "preco_promocional": 290.0,
                       "avisos_oferta": None})
        curtos = [_apps._duas_formas(a)[0] for a in o["avisos_oferta"]]
        self.assertIn(
            u"o contrato n\u00e3o deu para ler: sem pre\u00e7o de tabela, "
            u"fidelidade, multa e taxas", curtos)
        self.assertNotIn(_apps.SEM_ROTULO, curtos,
                         "o coletor tem de declarar, nao cair no generico")

    def test_o_valor_sai_em_reais_e_com_acento(self):
        """O texto passou a sair no Telegram quando o canal ganhou
        leitor: "R$ 1200.00" ao lado de "R$ 1.200,00" denuncia que as
        duas frases foram escritas em epocas diferentes."""
        o = self._reg({"nome_oferta": "X", "preco_promocional": 1500.0,
                       "avisos_oferta": None})
        from coletores import apps as _apps

        junto = " ".join(_apps._duas_formas(a)[1]
                         for a in o["avisos_oferta"])
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
        curto, longo = apps._duas_formas(aviso)
        self.assertEqual(curto, "sem a lista de apps")
        self.assertIn("7 aplicativos", longo)
        self.assertIn("acima do limite", longo)

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
