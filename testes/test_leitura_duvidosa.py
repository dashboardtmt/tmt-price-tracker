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


class ACoisaQueOColetorRecusouLerFicaNoRelatorio(unittest.TestCase):
    u"""A falha de leitura NAO vai para a mensagem diaria.

    Decisao do usuario em 26/10/2026: "eu nao quero essas mensagens de
    falha de leitura na msg diaria".

    A medicao explica por que ela se justifica: as ressalvas da Vivo e
    da Claro sao AS MESMAS todo dia - quatro codigos Anatel que a
    operadora repete em cards de precos diferentes, mais o HTTP 422 do
    endpoint da agencia. Aviso que se repete identico todo dia deixa de
    ser aviso: ensina o leitor a pular a secao, e o dia em que aparecer
    uma falha NOVA ele pula tambem.

    Os testes guardam as DUAS metades, porque as duas podem se perder: a
    ressalva voltando para a mensagem, ou desaparecendo tambem do
    relatorio - e a segunda seria pior, porque apagaria o registro do
    buraco.
    """

    def setUp(self):
        sem_declaracao(self)

    # ----------------------------------------- a mensagem nao mostra
    def test_a_mensagem_nao_tem_o_bloco(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertNotIn("nada mudou, mas faltou dado", t)
        self.assertNotIn("leitura com ressalva", t)

    def test_nem_o_rotulo_do_que_ficou_vazio(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertNotIn("sem pre\u00e7o de tabela", t)
        self.assertNotIn("ficou vazio", t)

    def test_nem_a_prosa_do_coletor(self):
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertNotIn("nenhum campo contratual dele foi usado", t)

    def test_o_dia_parado_segue_dizendo_que_esta_parado(self):
        """Sem a ressalva, "nenhuma mudanca" e a mensagem inteira - e
        tem de continuar saindo."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("Nenhuma mudan\u00e7a de pre\u00e7o, composi\u00e7\u00e3o ou nome", t)

    def test_a_mensagem_nao_fica_vazia(self):
        """Sem a ressalva, o dia parado vira tres linhas - e as tres
        tem de continuar saindo, senao o silencio deixa de ser
        alarme."""
        t = montar(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("TMT Price Tracker", t)
        self.assertIn(u"Relatório completo em anexo", t)

    # ----------------------------------------- o levantamento mostra
    def test_o_grupo_continua_no_levantamento(self):
        """O PDF o consome: apagar daqui apagaria o registro do buraco."""
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertTrue(d.get("duvidosa"))
        g = d["duvidosa"][0]
        for campo in ("motivo", "motivos", "curtos", "operadora", "produto",
                      "categoria", "quantas", "onde"):
            self.assertIn(campo, g)

    def test_conta_OFERTA_e_nao_linha(self):
        """A MESMA oferta em tres pracas e UMA oferta."""
        d = dados(com_recusa(ONTEM), com_recusa(HOJE, quantas=3))
        self.assertEqual(d["duvidosa"][0]["quantas"], 1)

    def test_o_texto_longo_continua_guardado(self):
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertIn("nenhum campo contratual",
                      " ".join(d["duvidosa"][0]["motivos"]))

    def test_o_rotulo_curto_continua_guardado(self):
        """Ele nao vai mais na mensagem, mas segue no levantamento: o
        relatorio pode us\u00e1-lo, e tirar a produ\u00e7\u00e3o dele faria o coletor
        declarar para ninguem."""
        d = dados(com_recusa(ONTEM), com_recusa(HOJE))
        self.assertTrue(d["duvidosa"][0]["curtos"])

    def test_motivos_diferentes_na_mesma_operadora_viram_um_grupo(self):
        hoje = com_recusa(HOJE, quantas=2)
        hoje[3]["avisos_oferta"] = [
            {"curto": u"sem franquia garantida",
             "longo": u"o card declara b\u00f4nus e n\u00e3o diz quanto \u00e9 do plano"}]
        d = dados(com_recusa(ONTEM), hoje)
        self.assertEqual(len(d["duvidosa"]), 1)
        self.assertEqual(len(d["duvidosa"][0]["motivos"]), 2)

    def test_operadoras_diferentes_saem_separadas_no_grupo(self):
        hoje = com_recusa(HOJE, quantas=2)
        outra = em_todas(operadora="Claro", produto="fibra",
                         nome="Claro Fibra", preco=99.9, gb=None, mbps=500,
                         data=HOJE)
        outra[0]["avisos_oferta"] = [
            {"curto": u"nomes repetidos na vitrine",
             "longo": u"nomes repetidos com precos diferentes: Claro Fibra"}]
        d = dados(com_recusa(ONTEM) + em_todas(operadora="Claro",
                                               produto="fibra",
                                               nome="Claro Fibra",
                                               preco=99.9, gb=None, mbps=500,
                                               data=ONTEM),
                  hoje + outra)
        self.assertEqual(len(d["duvidosa"]), 2)

    def test_a_string_antiga_continua_valendo(self):
        """O historico nao se reescreve, e a string E o texto longo."""
        d = dados(com_recusa(ONTEM), com_recusa(HOJE, quantas=2,
                                                avisos=[RECUSA]))
        self.assertEqual(d["duvidosa"][0]["quantas"], 1)
        self.assertEqual(d["duvidosa"][0]["motivos"], [RECUSA])


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


class ORiscoLatenteDoLimiteDeApps(unittest.TestCase):
    """O limite nao dispara hoje - e o que aconteceria se disparasse.

    MEDIDO EM 27/10/2026 sobre as 80 ofertas de Sao Paulo da Vivo, da
    Claro e da TIM: o maximo real e DOIS apps numa oferta. A medicao foi
    conferida contra um controle - um texto com nove apps faz a funcao
    devolver a ressalva -, entao o zero e ausencia, e nao falta de
    procura.

    ESTES TESTES FIXAM O COMPORTAMENTO ERRADO DE PROPOSITO, porque o
    erro e latente e vale estar escrito: lista vazia vira nivel 0, e
    nivel 0 na tela e "So internet e ligacoes" - uma AFIRMACAO sobre uma
    oferta cuja leitura foi justamente descartada.

    O conserto seria o nivel virar DESCONHECIDO (None, que a tela ja
    mostra como "—") em vez de zero. Nao foi feito porque mexeria nos
    nove coletores para um caso que hoje nao acontece. Se estes testes
    comecarem a falhar, foi porque alguem consertou - e ai e so apagar
    a classe.
    """

    MUITOS = ("inclui netflix, globoplay, disney+, max, paramount+, "
              "telecine, spotify, deezer e amazon prime video")

    def test_o_texto_largo_dispara_a_ressalva(self):
        """O controle: sem isto os testes de baixo mediriam um texto que
        nunca estourou o limite."""
        aviso = apps.aviso_de_leitura(self.MUITOS)
        self.assertIsNotNone(aviso)
        self.assertIn("acima do limite", aviso["longo"])

    def test_a_leitura_descartada_vira_lista_vazia(self):
        self.assertEqual(apps.apps_do_texto(self.MUITOS), [])

    def test_e_a_lista_vazia_vira_nivel_zero_e_nao_desconhecido(self):
        """AQUI MORA O DEFEITO LATENTE. Zero afirma "nao tem nenhum";
        o certo para uma leitura descartada seria None, que e "nao sei".
        """
        self.assertEqual(apps.nivel_dos_apps([]), 0)
        self.assertEqual(apps.nivel_dos_apps(apps.apps_do_texto(self.MUITOS)),
                         0)

    def test_dois_apps_continuam_sendo_lidos(self):
        """O outro controle: o limite nao pode ter comido o caso normal,
        que e o que acontece em producao."""
        lidos = apps.apps_do_texto("com netflix e globoplay inclusos")
        self.assertEqual(len(lidos), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
