# -*- coding: utf-8 -*-
"""A Unifique por rota de cidade, e o acento que escondia uma capital.

DOIS DEFEITOS, UM DENTRO DO OUTRO, achados em 27/10/2026.

O DE FORA: o coletor abria o seletor, digitava a cidade no campo de
busca e clicava no resultado - o trecho mais fragil do projeto, todo
dependente de rotulos de tela. O seletor, na verdade, so NAVEGA: clicar
em "Blumenau - SC" leva a /para-voce/internet-fibra/sc/blumenau, que
responde 200 com os precos e 404 quando a cidade nao e atendida. A
investigacao de 30/09/2026 tinha procurado "?cidade=x", "/cidade/x" e
"/set-cidade/x" - a rota existia pendurada no caminho do PRODUTO.

O DE DENTRO, que e o caro: o casamento do botao era sensivel a acento.
"Florianopolis", como a cesta de pracas guarda, nunca casa com
"Florianopolis - SC" escrito com o "o" acentuado. O coletor respondia "a
Unifique nao atende Florianopolis/SC", e essa frase virou comentario em
pracas.py como FATO DA FONTE - reforcada por uma explicacao plausivel,
que a Unifique seria forte no interior e fraca na capital.

Uma capital ficou um mes fora da serie por causa de um acento, e o
registro do erro parecia uma descoberta. E por isso que os testes abaixo
medem o ACENTO, e nao so a rota.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import unifique                               # noqa: E402
from coletores.pracas import pracas_de                       # noqa: E402


class ARotaSaiDoNomeDaCidade(unittest.TestCase):

    def test_o_caso_simples(self):
        self.assertEqual(
            unifique.rota_da_cidade("Blumenau", "SC"),
            "https://unifique.com.br/para-voce/internet-fibra/sc/blumenau")

    def test_o_acento_cai(self):
        """O endereco e sem acento; foi so por isto que Florianopolis
        passou um mes fora da coleta."""
        self.assertTrue(
            unifique.rota_da_cidade(u"Florianópolis", "SC")
            .endswith("/sc/florianopolis"))

    def test_o_nome_sem_acento_da_na_mesma_rota(self):
        """A cesta guarda sem acento e o site escreve com: as duas
        formas tem de levar ao mesmo lugar."""
        self.assertEqual(unifique.rota_da_cidade(u"Florianópolis", "SC"),
                         unifique.rota_da_cidade("Florianopolis", "sc"))

    def test_o_espaco_vira_hifen(self):
        self.assertTrue(
            unifique.rota_da_cidade("Porto Alegre", "RS").endswith(
                "/rs/porto-alegre"))

    def test_nome_composto_com_acento(self):
        self.assertTrue(
            unifique.rota_da_cidade(u"São José dos Campos", "SP")
            .endswith("/sp/sao-jose-dos-campos"))

    def test_a_uf_desce_para_minuscula(self):
        self.assertIn("/sc/", unifique.rota_da_cidade("Blumenau", "SC"))


class OAcentoNaoDerrubaAConfirmacao(unittest.TestCase):
    u"""A pagina escreve com acento; a cesta guarda sem."""

    def test_as_duas_formas_se_encontram(self):
        pagina = u"Ofertas para Florianópolis - SC"
        self.assertIn(unifique.sem_acento("Florianopolis").lower(),
                      unifique.sem_acento(pagina).lower())

    def test_sem_acento_nao_mexe_no_resto(self):
        self.assertEqual(unifique.sem_acento("Blumenau"), "Blumenau")
        self.assertEqual(unifique.sem_acento(""), "")
        self.assertEqual(unifique.sem_acento(None), "")


class AClaraOEscolhaDaCidadeSaiu(unittest.TestCase):
    u"""A coreografia de cliques nao pode voltar sem ser notada."""

    def test_nao_ha_mais_escolher_cidade(self):
        self.assertFalse(hasattr(unifique, "_escolher_cidade"),
                         "a escolha por clique voltou - ver o cabecalho "
                         "do modulo para o porque de ela ter saido")

    def test_o_coletor_navega_pela_rota(self):
        with open(unifique.__file__, encoding="utf-8") as f:
            fonte = f.read()
        self.assertIn("rota_da_cidade(cidade, uf)", fonte)
        self.assertIn("status == 404", fonte)


class FlorianopolisEstaNaCesta(unittest.TestCase):
    u"""A capital que o acento escondeu."""

    def test_a_unifique_coleta_florianopolis(self):
        cidades = {p["cidade"] for p in pracas_de("Unifique")}
        self.assertIn("Florianopolis", cidades)

    def test_curitiba_continua_fora_e_por_outro_motivo(self):
        """Curitiba foi investigada de verdade: a Unifique atende a
        cidade e nao vende fibra residencial ali. Reconferido em 27/10
        pela rota nova - 200 e sem oferta."""
        cidades = {p["cidade"] for p in pracas_de("Unifique")}
        self.assertNotIn("Curitiba", cidades)

    def test_sao_quatro_pracas(self):
        self.assertEqual(len(pracas_de("Unifique")), 4)


class ONavegadorSaiuEOQueFicouNoLugar(unittest.TestCase):
    u"""A Unifique era a unica das nove lida por navegador.

    O cabecalho do modulo dizia que a rota "responde 200 com os precos
    no HTML servido, sem sessao, sem cookie e sem JavaScript", e que o
    Chromium ficava porque "a leitura roda em cima do texto renderizado,
    e trocar isso por HTML cru mudaria o que se le".

    MEDIDO EM 03/11/2026: nao muda. O HTML cru das quatro pracas,
    passado pela MESMA funcao extrair(), devolve exatamente as ofertas
    que o caminho com navegador publicou no mesmo dia - velocidade e
    preco iguais nas quatro, zero diferenca, e 5,6 s para as quatro.
    """

    def _pagina(self, status, texto):
        guarda = unifique.buscar
        unifique.buscar = lambda url: (status, texto)
        self.addCleanup(lambda: setattr(unifique, "buscar", guarda))

    def test_o_modulo_nao_importa_mais_playwright(self):
        with open(unifique.__file__, encoding="utf-8") as f:
            fonte = f.read()
        self.assertNotIn("sync_playwright", fonte,
                         "o navegador voltou - ver o cabecalho do modulo")
        self.assertNotIn("chromium.launch", fonte)

    def test_le_a_oferta_do_texto_servido(self):
        # a forma que extrair() le: NOME EM MAIUSCULA, N Mega, e o
        # preco ancorado em "/mes" - sem a ancora ele pegaria a taxa de
        # instalacao, que no card vem antes da mensalidade
        self._pagina(200, "Blumenau FIBRA IDEAL 500 Mega com Wi-Fi "
                          "R$ 119,90 /mes")
        s = unifique.coletar("Blumenau", "SC", verbose=False)
        self.assertEqual([(o["degrau_mbps"], o["preco_promocional"])
                          for o in s["ofertas"]], [(500, 119.9)])

    def test_404_segue_sendo_nao_atende_e_nao_falha(self):
        """A rota distingue ausencia de quebra, e era o navegador que
        lia esse status. Sem isto, cidade nao atendida voltaria a
        parecer layout quebrado."""
        self._pagina(404, "")
        s = unifique.coletar("Curitiba", "PR", verbose=False)
        self.assertEqual(s["ofertas"], [])
        self.assertTrue(any("nao atende" in a for a in s["avisos"]))

    def test_outro_erro_de_http_nao_vira_nao_atende(self):
        """500 nao e ausencia: dizer "a Unifique nao atende" sobre um
        erro do servidor e afirmacao positiva de ausencia, que e o pior
        modo de falhar deste projeto."""
        self._pagina(500, "")
        s = unifique.coletar("Blumenau", "SC", verbose=False)
        self.assertFalse(any("nao atende" in a for a in s["avisos"]))
        self.assertTrue(any("HTTP 500" in a for a in s["avisos"]))

    def test_cidade_que_nao_confirma_sai_como_layout_quebrado(self):
        self._pagina(200, "pagina de outra coisa, sem oferta nenhuma")
        s = unifique.coletar("Blumenau", "SC", verbose=False)
        self.assertTrue(any("layout" in a for a in s["avisos"]))

    def test_e_a_cidade_confirmada_sem_oferta_sai_como_ausencia(self):
        self._pagina(200, "Blumenau e atendida, mas nada de fibra aqui")
        s = unifique.coletar("Blumenau", "SC", verbose=False)
        self.assertTrue(s.get("sem_oferta"))
        self.assertTrue(any("nao vende fibra" in a for a in s["avisos"]))

    def test_a_tag_virar_espaco_hoje_nao_muda_o_que_se_le(self):
        """O ESPACO NAO E GUARDA PROVADA, e isto esta medido.

        Escrevi primeiro uma mutacao no provador trocando o espaco por
        vazio, para provar que "500" e "Mega" colariam. ELA NAO PEGOU, e
        medindo o porque: nas paginas reais de Florianopolis e Blumenau,
        com espaco e sem espaco, extrair() devolve as MESMAS quatro
        ofertas e os MESMOS nomes - "FIBRA IDEAL", "FIBRA COMPLETA WI-FI
        EXT", "FIBRA TURBO", "FIBRA ESSENCIAL". O regex de extrair()
        aceita zero espaco entre o numero e "Mega", e e por isso.

        O espaco FICA no codigo, porque converter tag em espaco e o
        certo para um layout em que ele importe. O que nao fica e a
        mutacao: defeito inalcancavel da impressao de cobertura que nao
        existe, como o escape do "&" no relatorio. Se a Unifique passar
        a grudar dois cards sem separador, este teste muda de lado.
        """
        import re as _re
        html = ("<div><h3>FIBRA IDEAL</h3><span>500</span><span>Mega</span>"
                "<p>R$ 119,90</p><small>/mes</small></div>")

        def achatar(troca):
            return _re.sub(r"[ ]+", " ", _re.sub(r"<[^>]+>", troca, html))

        for troca in (" ", ""):
            lido = unifique.extrair(achatar(troca))
            self.assertEqual([(o["degrau_mbps"], o["preco_promocional"])
                              for o in lido], [(500, 119.9)],
                             "troca=%r" % troca)


if __name__ == "__main__":
    unittest.main(verbosity=2)
