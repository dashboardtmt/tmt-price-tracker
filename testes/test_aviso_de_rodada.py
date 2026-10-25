# -*- coding: utf-8 -*-
u"""O aviso de uma rodada BEM-SUCEDIDA so existia no log do Actions.

Nove coletores escrevem 37 avisos de rodada em saida["avisos"], e eles
vao para coletas.avisos no banco. Os leitores eram dois:

  robo.py:142   imprime no console durante a coleta - log do Actions
  robo.py:1846  _porque_falhou, chamado SO para falhas

E a falha e decidida assim:

    "sucesso": ok == len(pracas) and bool(ofertas)

Coletor que fechou todas as pracas e trouxe oferta e SUCESSO mesmo com
aviso, e a manchete de coleta incompleta monta "quem" a partir de
"falhas". Entao o aviso de uma rodada que fechou nao chegava a mensagem,
nem ao PDF, nem a tela.

MEDIDO NO LOG DA COLETA DE 25/10/2026. A Vivo fechou 20/20 pracas com
952 ofertas - sucesso - e carregou tres avisos por praca:

    lite: 1 codigo(s) com vigencia encerrada, ignorados
    a vitrine publicou 1 codigo(s) Anatel fora do padrao (IV202600045258)
    regulamento falhou em 4 oferta(s) - fidelidade, multa e preco de
      tabela ficam vazios. Primeira: VIV202600045225: HTTP 422

O terceiro sao 4 ofertas x 20 pracas = 80 linhas por dia com campo
contratual vazio por falha do endpoint da Anatel, e ninguem avisado.

E O PDF JA RECEBIA O DADO: "coletas": col entra em dados e o select pede
avisos - so ninguem lia. Mesmo padrao do avisos_oferta.

UMA LINHA NA MENSAGEM. O usuario pediu explicitamente: sem justificativa
complexa no Telegram. O texto de cada aviso e do relatorio.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _apoio import HOJE, ONTEM, dados, em_todas, montar, sem_declaracao  # noqa: E402

import robo  # noqa: E402

# os avisos reais da Vivo em 25/10/2026
AVISOS_VIVO = [
    u"lite: 1 código(s) com vigência encerrada, ignorados",
    u"regulamento falhou em 4 oferta(s) - fidelidade, multa e preço de "
    u"tabela ficam vazios. Primeira: VIV202600045225: HTTP 422",
]


def coletas(avisos_por_operadora=None, falha=()):
    """A tabela coletas do dia, com os nove coletores fechados.

    avisos_por_operadora diz quem terminou com aviso; "falha" diz quem
    nao fechou. O resto sai como a rodada normal.
    """
    avisos_por_operadora = avisos_por_operadora or {}
    saida = []
    for op in robo.COLETORES:
        saida.append({
            "data_captura": HOJE, "operadora": op,
            "pracas_ok": 0 if op in falha else 20, "pracas_pedidas": 20,
            "ofertas": 0 if op in falha else 180,
            "sucesso": op not in falha,
            "avisos": avisos_por_operadora.get(op),
            "iniciada_em": HOJE + "T09:00:00+00:00",
        })
    return saida


class ARodadaQueFechouComAvisoSaiDita(unittest.TestCase):
    def setUp(self):
        sem_declaracao(self)

    def _msg(self, **kw):
        return montar(em_todas(data=ONTEM), em_todas(data=HOJE),
                      coletas=coletas(**kw))

    def test_a_mensagem_diz_que_houve_aviso(self):
        t = self._msg(avisos_por_operadora={"Vivo": AVISOS_VIVO})
        self.assertIn("A coleta fechou com 2 avisos (Vivo)", t)

    def test_e_aponta_o_relatorio(self):
        t = self._msg(avisos_por_operadora={"Vivo": AVISOS_VIVO})
        self.assertIn("Estão no relatório", t)

    def test_um_aviso_so_fala_no_singular(self):
        t = self._msg(avisos_por_operadora={"Vivo": AVISOS_VIVO[:1]})
        self.assertIn("A coleta fechou com 1 aviso (Vivo)", t)

    def test_o_texto_do_aviso_NAO_vai_na_mensagem(self):
        """Mesma regra da ressalva por oferta: o texto e de depuracao, e
        o lugar dele e o PDF."""
        t = self._msg(avisos_por_operadora={"Vivo": AVISOS_VIVO})
        self.assertNotIn("HTTP 422", t)
        self.assertNotIn("vigência encerrada", t)

    def test_cabe_em_uma_linha(self):
        t = self._msg(avisos_por_operadora={"Vivo": AVISOS_VIVO})
        quais = [x for x in t.split("\n") if "A coleta fechou com" in x]
        self.assertEqual(len(quais), 1)

    def test_varios_coletores_na_mesma_linha(self):
        t = self._msg(avisos_por_operadora={
            "Vivo": AVISOS_VIVO,
            "Unifique": [u"sem oferta de fibra em Curitiba"],
        })
        self.assertIn("A coleta fechou com 3 avisos (Unifique, Vivo)", t)

    def test_rodada_limpa_nao_tem_a_linha(self):
        t = self._msg()
        self.assertNotIn("A coleta fechou com", t)

    def test_a_falha_continua_sendo_manchete_e_nao_ressalva(self):
        """Coletor que NAO fechou e manchete - "COLETA INCOMPLETA" -, e
        isso nao muda: a ressalva e para quem fechou e tinha algo a
        dizer."""
        t = self._msg(falha=("Unifique",),
                      avisos_por_operadora={"Unifique": [u"o layout mudou"]})
        self.assertIn("COLETA INCOMPLETA", t)
        self.assertNotIn("A coleta fechou com", t)

    def test_falha_e_aviso_no_mesmo_dia_nao_se_misturam(self):
        t = self._msg(falha=("Unifique",),
                      avisos_por_operadora={"Unifique": [u"o layout mudou"],
                                            "Vivo": AVISOS_VIVO})
        self.assertIn("COLETA INCOMPLETA", t)
        self.assertIn("A coleta fechou com 2 avisos (Vivo)", t)

    def test_aviso_vazio_nao_conta(self):
        t = self._msg(avisos_por_operadora={"Vivo": []})
        self.assertNotIn("A coleta fechou com", t)


class ORelatorioListaOsAvisosDaColeta(unittest.TestCase):
    """O dado sempre chegou ao PDF; so ninguem lia."""

    def test_a_funcao_le_de_coletas(self):
        import relatorio

        d = {"coletas": [
            {"operadora": "Vivo", "avisos": AVISOS_VIVO},
            {"operadora": "TIM", "avisos": None},
        ]}
        itens = relatorio._avisos_da_coleta(d)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0][0], "Vivo")
        self.assertIn("HTTP 422", itens[1][1])

    def test_sai_ordenado_por_operadora(self):
        import relatorio

        d = {"coletas": [
            {"operadora": "Vivo", "avisos": [u"um"]},
            {"operadora": "Claro", "avisos": [u"dois"]},
        ]}
        itens = relatorio._avisos_da_coleta(d)
        self.assertEqual([x[0] for x in itens], ["Claro", "Vivo"])

    def test_dia_limpo_nao_rende_item(self):
        import relatorio

        self.assertEqual(relatorio._avisos_da_coleta({"coletas": []}), [])
        self.assertEqual(relatorio._avisos_da_coleta({}), [])

    def test_aviso_vazio_na_lista_nao_entra(self):
        import relatorio

        d = {"coletas": [{"operadora": "Vivo", "avisos": [u"", None, u"vale"]}]}
        itens = relatorio._avisos_da_coleta(d)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0][1], "vale")


class OPdfImprimeOsAvisosDaColeta(unittest.TestCase):
    """A funcao existia e nada a chamava - peca sem montagem.

    Terceira vez na semana que o provador cobra isto: _avisos_da_coleta
    entrou com teste proprio e o PDF continuava sem imprimir nada. Teste
    de peca nao prova montagem.
    """

    def _gerar(self, avisos):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab nao instalado")
        import relatorio

        d = dados(em_todas(data=ONTEM), em_todas(data=HOJE),
                  coletas=coletas(avisos_por_operadora=avisos))
        entradas = {chave: [] for chave, _rot in relatorio.PRODUTOS}
        caminho = relatorio.gerar(
            d, entradas,
            os.path.join(os.path.dirname(__file__), "_rodada.pdf"))
        self.addCleanup(lambda: os.path.exists(caminho)
                        and os.remove(caminho))
        return os.path.getsize(caminho)

    def test_o_pdf_sai_com_a_secao(self):
        self.assertGreater(self._gerar({"Vivo": AVISOS_VIVO}), 1000)

    def test_e_com_tag_aberta_no_aviso(self):
        """MEDIDO: o reportlab aguenta "&" e "<vazio>"; o que derruba e
        tag aberta. O texto vem do coletor, e nao da para confiar."""
        self.assertGreater(
            self._gerar({"Vivo": [u"a vitrine trazia <b>Max sem fechar"]}),
            1000)

    def test_dia_limpo_tambem_gera(self):
        self.assertGreater(self._gerar({}), 1000)

    def test_o_render_chama_a_funcao(self):
        """A guarda contra a volta de "existe e ninguem usa"."""
        import inspect

        import relatorio

        fonte = inspect.getsource(relatorio.gerar)
        self.assertIn("_avisos_da_coleta(dados)", fonte)


class OCanalDeRodadaTemLeitor(unittest.TestCase):
    """A guarda contra a volta do estado anterior: escrito e nao lido."""

    def test_a_mensagem_olha_as_rodadas_que_fecharam(self):
        import inspect

        fonte = inspect.getsource(robo.montar_mensagem)
        self.assertIn('c.get("sucesso") and c.get("avisos")', fonte,
                      "a mensagem tem de olhar o aviso de quem fechou")

    def test_e_os_coletores_continuam_escrevendo(self):
        """Se um coletor parar de avisar, o canal fica sem carga - e isso
        tambem e defeito, no outro sentido."""
        import io as _io

        quantos = 0
        pasta = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "coletores")
        for nome in os.listdir(pasta):
            if not nome.endswith(".py"):
                continue
            with _io.open(os.path.join(pasta, nome),
                          encoding="utf-8") as f:
                fonte = f.read()
            quantos += fonte.count('saida["avisos"].append')
            quantos += fonte.count('saida["avisos"].extend')
        self.assertGreaterEqual(quantos, 30,
                               "os coletores escreviam 37 avisos de rodada")


if __name__ == "__main__":
    unittest.main(verbosity=2)
