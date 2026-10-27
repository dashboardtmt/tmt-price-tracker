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


if __name__ == "__main__":
    unittest.main(verbosity=2)
