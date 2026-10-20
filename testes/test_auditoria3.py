# -*- coding: utf-8 -*-
"""Os achados da TERCEIRA auditoria, e o que eu piorei consertando.

A segunda passada achou nove caminhos de erro. Consertei os nove, e a
terceira passada achou QUATRO defeitos graves nas minhas correcoes -
mais um ponto em que eu tornei o sistema pior do que estava.

E o padrao dos quatro e um so, e e humilhante de simples: **eu consertei
a afirmacao falsa num canal e deixei o outro afirmando.** A mensagem
passou a dizer "entrega nao lida" e o PDF seguiu imprimindo "None" na
mesma oferta. A mensagem passou a dizer "nao deu para ler o estado da
coleta" e o PDF seguiu listando as nove operadoras como "Sem registro".

Os dois canais saem do mesmo levantamento exatamente para nao poderem
discordar, e a minha correcao criou a discordancia que a arquitetura
existe para impedir. A licao que fica no codigo: texto que afirma algo
sobre uma oferta mora NO EVENTO, uma vez, e os dois canais leem. Nao em
dois lugares que combinam de dizer a mesma coisa.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
import vigia                                                  # noqa: E402
from _apoio import (COLETA_OK, HOJE, ONTEM, dados, em_todas,   # noqa: E402
                    montar, oferta)
from test_auditoria2 import so_erro                            # noqa: E402


def indexar(linhas):
    return {robo._identidade(l): l for l in linhas}


def ontem_sem(oferta_de_hoje=None):
    """Um indice de ontem com uma oferta qualquer, que nao a de hoje.

    _degraus_que_voltaram so olha um degrau que NAO estava em "o". Passar
    ali a propria oferta de hoje fazia o teste medir o contrario: o
    degrau estava na vitrine, nao havia o que voltar.
    """
    return indexar([oferta(nome="Outra coisa", preco=50.0, gb=10,
                           data=ONTEM, chave="Vivo|movel|10gb|simples")])


# ======================================================== gravidade alta

class OFantasmaVoltouPorOutraPorta(unittest.TestCase):
    """N1. O MESMO -26% falso, agora por _degraus_que_voltaram.

    _indexar tira o grupo indistinguivel de h e de o. Mas
    _degraus_que_voltaram le a tabela crua para a parte historica, e
    pergunta "esta entrega estava na vitrine ontem?" olhando so o indice
    - entao toda oferta do grupo descartado parecia ter faltado ontem.

    Na transicao real de 15 para 16/10, com a correcao de variante
    separando o par, saia:

        Combo - Vivo
          700 Mbps voltou por 290,00   -26% sobre os 390,00 de 15/10

    Nenhum preco mudou, as duas ofertas existiam nos dois dias pelos
    mesmos valores, e o degrau nunca saiu da vitrine. Mesmo sorteio que o
    indice recusou, agora com a palavra "voltou" e uma data.
    """

    def _historico(self, linhas):
        def responder(caminho, pagina=None):
            if caminho.startswith("capturas?operadora="):
                return list(linhas), None
            return [], None
        guarda = robo.armazenamento.consultar_tudo
        robo.armazenamento.consultar_tudo = responder
        self.addCleanup(lambda: setattr(robo.armazenamento,
                                        "consultar_tudo", guarda))

    def test_descartada_de_ontem_nao_e_ausente_de_ontem(self):
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=290.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        # ontem o par colidiu, entao as duas linhas foram descartadas
        par = [oferta(produto="combo", nome="Vivo Família 2 + TV",
                      preco=p, gb=None, mbps=700, data=ONTEM,
                      chave="Vivo|combo|700mbps|familia")
               for p in (290.0, 390.0)]
        # O HISTORICO VAI COM UMA LINHA SO. Com as duas, quem barra o
        # evento e a defesa de ambiguidade e nao a de descartadas - e o
        # teste passaria sem medir o que ele nomeia.
        self._historico([par[1]])
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE,
                                           descartadas_de_ontem=par)
        self.assertEqual(achou, [], "o degrau nao faltou ontem")

    def test_sem_a_defesa_o_fantasma_sai(self):
        """O mesmo cenario sem a lista de descartadas: a prova de que a
        defesa e ela, e nao outra coisa no caminho."""
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=290.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        par = [oferta(produto="combo", nome="Vivo Família 2 + TV",
                      preco=390.0, gb=None, mbps=700, data=ONTEM,
                      chave="Vivo|combo|700mbps|familia")]
        self._historico(par)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(len(achou), 1, "sem a defesa, o fantasma aparece")

    def test_dia_historico_ambiguo_nao_serve_de_referencia(self):
        """A busca de 45 dias le a tabela crua e nao sabe das ofertas
        indistinguiveis: com duas linhas do mesmo dia, mesma praca,
        mesma entrega e mesmo nome a precos diferentes, "a primeira que
        aparecer" e sorteio. Dia ambiguo nao diz por quanto a operadora
        vendia aquele degrau."""
        hoje = indexar([oferta(produto="combo", nome="Vivo Família 2 + TV",
                               preco=250.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|familia")])
        ambiguo = [{"data_captura": "2026-10-15", "praca": "Sao Paulo/SP",
                    "nome_oferta": "Vivo Família 2 + TV",
                    "preco_promocional": p, "franquia_anunciada_gb": None,
                    "degrau_mbps": 700} for p in (290.0, 390.0)]
        self._historico(ambiguo)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(achou, [], "o dia de referencia e ambiguo")

    def test_dia_historico_limpo_continua_servindo(self):
        hoje = indexar([oferta(produto="combo", nome="Vivo Total",
                               preco=250.0, gb=None, mbps=700,
                               chave="Vivo|combo|700mbps|simples")])
        limpo = [{"data_captura": "2026-10-15", "praca": "Sao Paulo/SP",
                  "nome_oferta": "Vivo Total", "preco_promocional": 200.0,
                  "franquia_anunciada_gb": None, "degrau_mbps": 700}]
        self._historico(limpo)
        achou = robo._degraus_que_voltaram(hoje, ontem_sem(), HOJE)
        self.assertEqual(len(achou), 1)
        self.assertEqual(achou[0]["antes"], 200.0)


class OPesoDaRemodeladaNaoEraLido(unittest.TestCase):
    """N2. _por_efeito tinha um ramo morto, e era o das remodeladas.

    Elas carregam "antes" e "atual" como dicionarios, igual as mudancas
    de preco, entao caiam no ramo do par antes/atual e o
    max(preco, entrega) nunca rodava.

    Consequencia medida: a oferta que paga 5% mais e recebe METADE da
    internet pesava 0,05 e era a unica das quatro a ficar fora da
    mensagem - justo o movimento que o modulo chama de "maior efeito
    sobre o cliente". E pior num aspecto: como o relatorio parou de
    reordenar, os dois canais passaram a concordar na ordem errada.
    """

    def _remodelada(self, pa, pd, ea, ed):
        return {"antes_preco": pa, "agora_preco": pd,
                "antes_entrega": ea, "agora_entrega": ed,
                "antes": {"preco_promocional": pa},
                "atual": {"preco_promocional": pd}}

    def test_a_entrega_entra_no_peso(self):
        # 5% no preco, 50% na entrega: o peso e o maior dos dois
        self.assertAlmostEqual(
            robo._por_efeito(self._remodelada(100.0, 105.0, 600, 300)), 0.5)

    def test_so_entrega_tambem_pesa(self):
        self.assertAlmostEqual(
            robo._por_efeito(self._remodelada(100.0, 100.0, 600, 300)), 0.5)

    def test_a_pior_oferta_abre_a_mensagem(self):
        ontem, hoje = [], []
        casos = (("Vivo A", 105.0, 300), ("Vivo B", 140.0, 580),
                 ("Vivo C", 130.0, 590), ("Vivo D", 120.0, 595))
        for nome, _p, _e in casos:
            ontem += em_todas(operadora="Vivo", produto="fibra", nome=nome,
                              preco=100.0, gb=None, mbps=600, data=ONTEM,
                              chave="Vivo|fibra|600mbps|%s" % nome[-1])
        for nome, p, e in casos:
            hoje += em_todas(operadora="Vivo", produto="fibra", nome=nome,
                             preco=p, gb=None, mbps=e, data=HOJE,
                             chave="Vivo|fibra|%dmbps|%s" % (e, nome[-1]))
        t = montar(ontem, hoje)
        # "Vivo A" paga 5% mais e recebe metade: tem de estar na mensagem
        self.assertIn("Vivo A", t)

    def test_composicao_pesa_pelo_que_mudou_dentro(self):
        """O preco e igual por definicao, entao todas pesariam zero - e
        os tres mostrados voltariam a ser os primeiros do indice."""
        muita = {"antes": {"preco_promocional": 100.0, "assinatura_sva": "a+b"},
                 "atual": {"preco_promocional": 100.0, "assinatura_sva": "c+d"}}
        pouca = {"antes": {"preco_promocional": 100.0, "assinatura_sva": "a+b"},
                 "atual": {"preco_promocional": 100.0, "assinatura_sva": "a+b+c"}}
        self.assertGreater(robo._por_efeito(muita), robo._por_efeito(pouca))


class OPdfNaoPodeDiscordarDaMensagem(unittest.TestCase):
    """N3 e N4. Eu consertei a afirmacao falsa na MENSAGEM e deixei o PDF
    afirmando - duas vezes, e sao o mesmo erro de forma.

    Os dois canais saem do mesmo levantamento justamente para nao
    poderem discordar. Texto que afirma algo sobre uma oferta mora no
    EVENTO, uma vez.
    """

    def test_o_texto_da_entrega_viaja_no_evento(self):
        r = dados(em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=None, data=ONTEM,
                           chave="Brisanet|fibra|None|simples"),
                  em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=120.0, gb=None,
                           mbps=None, data=HOJE,
                           chave="Brisanet|fibra|None|com_apps"))
        self.assertTrue(r["remodeladas"], "o cenario tem de produzir evento")
        e = r["remodeladas"][0]
        self.assertEqual(e["texto_entrega"], "entrega não lida")
        self.assertNotIn("None", e["texto_entrega"])

    def test_e_o_do_preco_tambem(self):
        r = dados(em_todas(nome="Vivo Pós", preco=None, gb=20, data=ONTEM,
                           chave="Vivo|movel|20gb|simples"),
                  em_todas(nome="Vivo Pós", preco=35.0, gb=20, data=HOJE,
                           chave="Vivo|movel|20gb|com_apps"))
        self.assertTrue(r["remodeladas"])
        self.assertEqual(r["remodeladas"][0]["texto_preco"],
                         "preço não lido nos dois dias")

    def test_o_erro_da_coleta_chega_ao_pdf(self):
        so_erro("coletas", em_todas(data=ONTEM) + em_todas(data=HOJE))
        _t, d = robo.montar_mensagem(HOJE, ONTEM)
        self.assertTrue(d["erro_coleta"], "o PDF precisa do erro para "
                                          "nao listar nove sem registro")


class IndiceVazioNaoEBancoVazio(unittest.TestCase):
    """N5. "Nenhuma oferta foi capturada hoje" saia de indice vazio, e
    indice vazio inclui o caso em que as capturas existem e TODAS
    colidiram. A frase era falsa e a linha do ponto cego, duas abaixo,
    a desmentia."""

    def _tudo_colidido(self):
        a = oferta(produto="combo", nome="Vivo Família 2 + TV", preco=290.0,
                   gb=None, mbps=700, data=HOJE)
        return [a, dict(a, preco_promocional=390.0)]

    def test_capturas_que_colidiram_nao_sao_capturas_ausentes(self):
        t = montar([], self._tudo_colidido(), coletas=COLETA_OK)
        self.assertNotIn("Nenhuma oferta foi capturada", t)
        self.assertIn("indistinguíveis entre si", t)

    def test_banco_de_fato_vazio_continua_dizendo(self):
        falhou = [dict(c, sucesso=False) for c in COLETA_OK]
        t = montar([], [], coletas=falhou)
        self.assertIn("Nenhuma oferta foi capturada", t)


# ======================================================== gravidade media

class AEscolhaEntreDuasLeituras(unittest.TestCase):
    """N8. A regra estava no codigo e nao no papel: quando a oferta de
    ontem pareia por chave E por nome, _renomeadas rodava primeiro e
    ganhava. A preferencia e defensavel - a chave de continuidade e a
    identidade mais forte - e o que faltava era declara-la e nao esconder
    a leitura descartada."""

    def _dia(self):
        ontem = em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=100.0,
                         gb=None, mbps=600, data=ONTEM,
                         chave="Vivo|fibra|600mbps|simples")
        hoje = em_todas(operadora="Vivo", produto="fibra",
                        nome="Vivo Fibra Pro", preco=130.0, gb=None,
                        mbps=600, data=HOJE,
                        chave="Vivo|fibra|600mbps|simples")
        hoje += em_todas(operadora="Vivo", produto="fibra",
                         nome="Vivo Fibra 600 Mega", preco=160.0, gb=None,
                         mbps=600, data=HOJE,
                         chave="Vivo|fibra|600mbps|com_apps")
        return ontem, hoje

    def test_a_chave_ganha_do_nome(self):
        ontem, hoje = self._dia()
        r = dados(ontem, hoje)
        self.assertEqual(len(r["renomeadas"]), 1)
        self.assertEqual(r["remodeladas"], [])

    def test_e_a_outra_leitura_fica_registrada(self):
        ontem, hoje = self._dia()
        r = dados(ontem, hoje)
        outra = r["renomeadas"][0].get("outra_leitura")
        self.assertTrue(outra, "a leitura descartada nao pode desaparecer")
        self.assertEqual(outra["preco"], 160.0)


class AJanelaEUmaSo(unittest.TestCase):
    """N9 e N10. Uma linha sem hora apagava o aviso inteiro, e havia duas
    definicoes de "janela da manha" em dois arquivos."""

    def _com_hora(self, *horas):
        col = []
        for i, h in enumerate(horas):
            c = dict(COLETA_OK[i])
            c["iniciada_em"] = (HOJE + "T" + h) if h else None
            col.append(c)
        return montar(em_todas(data=ONTEM), em_todas(data=HOJE), coletas=col)

    def test_uma_linha_sem_hora_nao_apaga_o_aviso(self):
        t = self._com_hora(None, "22:40", "22:41")
        self.assertIn("começou às 22:40", t)

    def test_a_janela_e_a_da_guarda(self):
        import ja_coletou
        t = self._com_hora("11:50")
        self.assertIn("começou às 11:50", t)
        self.assertIn(ja_coletou.LIMITE.strftime("%H:%M"), t)

    def test_coleta_na_janela_nao_recebe_ressalva(self):
        self.assertNotIn("fora da janela", self._com_hora("06:30", "06:40"))


class OVigiaDizQuantosSaoGraves(unittest.TestCase):
    """N13. "20 salto(s) acima de 50%, o mais grave em X" deixa o leitor
    entender que os 20 sao graves, e em geral e um so."""

    def _dia(self, n=30):
        return [{"operadora": "Vivo", "produto": "movel", "praca": "P/X",
                 "nome_oferta": "O%d" % i, "preco_promocional": 100.0,
                 "franquia_anunciada_gb": 50, "degrau_mbps": None,
                 "chave": "c%d" % i} for i in range(n)]

    def test_a_contagem_dos_severos_aparece(self):
        ontem = self._dia()
        hoje = self._dia()
        hoje[0]["preco_promocional"] = 24.60      # severo
        for i in range(1, 6):
            hoje[i]["preco_promocional"] = 160.0  # nao severos
        r = vigia.achados(hoje, {"2026-10-%02d" % (10 + i): ontem
                                 for i in range(5)})
        salto = [t for _g, t in r if "salto" in t][0]
        self.assertIn("6 salto(s)", salto)
        self.assertIn("1 deles grande demais", salto)


class EntregaQueMexeuNaoEEntregaParada(unittest.TestCase):
    """N14. A linha da leitura afirma "sem mexer em preco nem entrega", e
    entrega_mudou e False tambem quando um dos lados nao foi lido - a
    entrega mexeu, de desconhecida para 500. Caso real da Brisanet."""

    def test_entrega_que_apareceu_nao_conta_como_parada(self):
        # a variante muda junto, que e o caso real de 10-19: sem isso nao
        # ha evento nenhum, e esta certo - nada identifica a mudanca
        r = dados(em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=None, data=ONTEM,
                           chave="Brisanet|fibra|None|simples"),
                  em_todas(operadora="Brisanet", produto="fibra",
                           nome="Brisanet 500", preco=114.80, gb=None,
                           mbps=500, data=HOJE,
                           chave="Brisanet|fibra|500mbps|com_apps"))
        eventos = r["remodeladas"] + r["leitura"]
        self.assertTrue(eventos)
        self.assertFalse(eventos[0]["versao_apenas"],
                         "a entrega passou de desconhecida para 500")


if __name__ == "__main__":
    unittest.main(verbosity=2)
