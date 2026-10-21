# -*- coding: utf-8 -*-
"""Os achados da auditoria dos coletores.

Os coletores sao a origem de todo o dado e ficaram seis rodadas sem ser
olhados - as rodadas anteriores cobriram o comparador, o relatorio, o
vigia, o portao e a tela. Quando foram, dois auditores em paralelo
acharam oito defeitos graves.

A LICAO QUE SE REPETE: tres dos oito sao a mesma familia que ja tinha
aparecido no comparador - escolher um entre varios e publicar como fato.
O regulamento de uma oferta carimbado em outra que divide o codigo
Anatel; a safra do mes dentro da chave de continuidade; a mesma oferta
gravada duas vezes porque o produto saia do nome da consulta e nao da
aba. A familia atravessa os arquivos; e so a forma que muda.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import armazenamento, claro, starlink, tim, vivo  # noqa: E402


class ORegulamentoDeOutraOfertaNaoVale(unittest.TestCase):
    """Um codigo Anatel e publicado por varios cards da Vivo: o mesmo
    VIV202604042336 cobre "V 1 Giga" (R$ 1.200), "V 2 Giga" (R$ 1.500) e
    "V 10 Giga" (R$ 3.000). O documento descreve um deles.

    O coletor ja sabia - ele escrevia "regulamento diz R$ 1200,00 de
    tabela, abaixo dos R$ 3000,00 da vitrine" -, barrava o preco de
    tabela e carimbava todo o resto: multa, fidelidade, taxas, franquia
    contratual, nome registrado e a assinatura SVA.

    Dois deles com efeito em cascata. assinatura_sva alimenta o detector
    de repasse disfarcado - composicao muda, etiqueta nao -, e com tres
    cards recebendo a mesma assinatura ele comparava uma composicao que
    nao e de nenhum. E nome_regulamento alimenta a variante da chave,
    entao a IDENTIDADE de uma oferta dependia de um documento de outra.
    """

    def _reg(self, tabela=1200, franquia=None):
        r = {"precoSemDescontos": tabela,
             "fidelizacao": {"tempoFidelizacao": 12, "multaFidelizacao": 1400},
             "custoInicial": {"instalacao": 0, "adesao": 0},
             "SMP": {"listaSVA": ["030011", "030012"]},
             "SCM": {}, "nomeOferta": "VIVO TOTAL V 1 GIGA"}
        if franquia:
            r["SMP"]["franquiaDados"] = {"franquia": franquia}
        return r

    def test_preco_de_tabela_abaixo_da_vitrine_tira_tudo(self):
        o = vivo.aplicar_regulamento(
            {"preco_promocional": 3000.0}, self._reg(tabela=1200))
        self.assertIsNone(o.get("multa_fidelidade"))
        self.assertIsNone(o.get("fidelidade_meses"))
        self.assertIsNone(o.get("assinatura_sva"))
        self.assertIsNone(o.get("nome_regulamento"))
        self.assertTrue(any("outra oferta" in a
                            for a in o.get("avisos_oferta") or []))

    def test_franquia_que_contradiz_o_card_tambem(self):
        """O outro sinal, medido no Vivo Pre: um codigo cobre 5, 15 e 20
        GB e o regulamento declara 25. Antes so a franquia era recusada e
        os tres cards recebiam a mesma assinatura SVA."""
        o = vivo.aplicar_regulamento(
            {"preco_promocional": 20.0, "franquia_anunciada_gb": 5},
            self._reg(tabela=None, franquia=25))
        self.assertIsNone(o.get("assinatura_sva"))
        self.assertIsNone(o.get("franquia_contratual_gb"))
        self.assertIsNone(o.get("multa_fidelidade"))

    def test_regulamento_que_e_da_oferta_continua_valendo(self):
        o = vivo.aplicar_regulamento(
            {"preco_promocional": 1200.0, "franquia_anunciada_gb": 50},
            self._reg(tabela=1200, franquia=50))
        self.assertEqual(o["multa_fidelidade"], 1400.0)
        self.assertEqual(o["fidelidade_meses"], 12)
        self.assertEqual(o["assinatura_sva"], "030011+030012")
        self.assertEqual(o["franquia_contratual_gb"], 50)


class AChaveNaoCarregaASafraDoMes(unittest.TestCase):
    """A variante da chave saia do NOME CRU para nivel >= 2, e o re.sub
    so decapitava prefixo da Vivo. A Brisanet carimba o mes no nome:

        AGO26 600MB + NETFLIX PCA
          -> Brisanet|fibra|600mbps|com_ago26_600mb_netflix_pca

    Medido: 19 grupos renomeados em 21 dias, e 14 das 31 ofertas de hoje
    perderiam a identidade em 1o de novembro. O comparador veria a oferta
    morrer e outra nascer, e isso entra na mensagem, no PDF e na tela
    como saida e entrada de portfolio que nao aconteceram.
    """

    def _o(self, nome, apps=None, nivel=2, mbps=600, gb=None):
        return {"operadora": "Brisanet", "produto": "fibra",
                "nome_oferta": nome, "nivel_bundle": nivel,
                "degrau_mbps": mbps, "franquia_anunciada_gb": gb,
                "apps": apps}

    def test_a_virada_do_mes_nao_quebra_a_chave(self):
        ago = armazenamento.chave_continuidade(
            self._o("AGO26 600MB + NETFLIX PCA", ["netflix", "skeelo"]))
        nov = armazenamento.chave_continuidade(
            self._o("NOV26 600MB + NETFLIX PCA", ["netflix", "skeelo"]))
        self.assertEqual(ago, nov)
        self.assertNotIn("ago26", ago)

    def test_e_a_safra_entre_colchetes_tambem_nao(self):
        a = armazenamento.chave_continuidade(
            self._o("[SET] OFT NC PF PROMO 12M 500MB", ["skeelo"]))
        b = armazenamento.chave_continuidade(
            self._o("[OUT] OFT NC PF PROMO 12M 500MB", ["skeelo"]))
        self.assertEqual(a, b)

    def test_apps_diferentes_continuam_sendo_series_diferentes(self):
        """A variante existe para isto: "Pos com Netflix" nao e o mesmo
        produto que "Pos com Amazon", mesmo com a franquia igual."""
        n = armazenamento.chave_continuidade(self._o("X", ["netflix"]))
        a = armazenamento.chave_continuidade(self._o("X", ["amazon"]))
        self.assertNotEqual(n, a)

    def test_nivel_alto_sem_lista_nao_inventa_qual(self):
        k = armazenamento.chave_continuidade(self._o("X", None, nivel=2))
        self.assertIn("com_streaming", k)

    def test_no_combo_as_duas_pernas_identificam(self):
        """A velocidade ganhava e os GB do movel eram descartados: duas
        ofertas de 500 Mbps que diferem pelo movel - R$ 94,80 sem e
        R$ 109,89 com 20 GB - dividiam a mesma serie."""
        sem = armazenamento.chave_continuidade(
            self._o("500MB + SKY", ["sky"], mbps=500, gb=None))
        com = armazenamento.chave_continuidade(
            self._o("500MB + 20GB + sky", ["sky"], mbps=500, gb=20))
        self.assertNotEqual(sem, com)
        self.assertIn("500mbps_20gb", com)


class ProdutoVazioNaoEProdutoInexistente(unittest.TestCase):
    """ler_cards da Claro e ler_ofertas da TIM devolviam ([], None)
    quando nao reconheciam nada - e a rodada era gravada como sucesso,
    com a praca contada em pracas_ok. A base do dia passava a afirmar
    que a operadora nao tem aquele produto.

    E afirmacao de ausencia, o pior defeito da regua. As funcoes irmas
    do mesmo arquivo ja faziam certo: ler_por_texto e ler_prezao
    devolvem erro quando nao reconhecem nada.
    """

    def _pagina(self, modulo, html):
        """Os dois leitores buscam a URL: entra um abridor de mentira."""
        guarda = modulo.buscar
        modulo.buscar = lambda op, url: (200, html)
        self.addCleanup(lambda: setattr(modulo, "buscar", guarda))

    def test_claro_sem_card_reconhecido_devolve_erro(self):
        self._pagina(claro, "<html><body>nada aqui</body></html>")
        cards, erro = claro.ler_cards(None, "http://x", "movel")
        self.assertEqual(cards, [])
        self.assertTrue(erro, "lista vazia sem erro vira afirmacao")
        self.assertIn("leitura falhou", erro)

    def test_claro_com_card_de_verdade_nao_reclama(self):
        html = ('<div class="card-planos"> Claro Pós 50GB '
                'R$ 124,90 /mes </div>')
        self._pagina(claro, html)
        cards, erro = claro.ler_cards(None, "http://x", "movel")
        self.assertIsNone(erro)
        self.assertEqual(len(cards), 1)

    def test_tim_sem_oferta_reconhecida_devolve_erro(self):
        self._pagina(
            tim, '<script data-drupal-selector="drupal-settings-json">'
                 '{"ofertas": []}</script>')
        saida, erro = tim.ler_ofertas(None, "http://x", "SP")
        self.assertEqual(saida, [])
        self.assertTrue(erro)
        self.assertIn("leitura falhou", erro)


class ATimNomeiaOAppQueEncontrou(unittest.TestCase):
    """nivel_bundle(contexto) ja chamava apps.apps_do_texto para decidir
    o degrau - a TIM identificava o app, usava para subir o nivel e
    jogava o nome fora. A captura afirmava "uma assinatura inclusa" sem
    dizer qual, que e exatamente o que o modulo de apps existe para
    impedir. 60 capturas por dia nesse estado."""

    def _com(self, cru):
        import json as _j
        guarda = tim.buscar
        tim.buscar = lambda op, url: (
            200, '<script data-drupal-selector="drupal-settings-json">'
                 + _j.dumps({"ofertas": cru}) + "</script>")
        self.addCleanup(lambda: setattr(tim, "buscar", guarda))

    def test_o_app_do_texto_chega_a_oferta(self):
        cru = [{"field_subtitle": [{"value": "TIM Pré XIP Plus"}],
                "field_preco_card_oferta": [{"value": "R$ 20,00"}],
                "field_information_text": [{"value": "6GB com Max incluso"}]}]
        self._com(cru)
        saida, erro = tim.ler_ofertas(None, "http://x", "SP")
        self.assertIsNone(erro)
        self.assertEqual(len(saida), 1)
        o = saida[0]
        self.assertGreaterEqual(o["nivel_bundle"], 2)
        self.assertIn("max", o.get("apps") or [])
        self.assertIn("Max", o.get("apps_rotulo") or "")

    def test_oferta_sem_app_nao_ganha_rotulo(self):
        cru = [{"field_subtitle": [{"value": "TIM Controle"}],
                "field_preco_card_oferta": [{"value": "R$ 40,00"}],
                "field_information_text": [{"value": "20GB de internet"}]}]
        self._com(cru)
        saida, _e = tim.ler_ofertas(None, "http://x", "SP")
        self.assertIsNone(saida[0].get("apps"))
        self.assertIsNone(saida[0].get("apps_rotulo"))


class AListaDeAppsDaVivoLeONomeEOTexto(unittest.TestCase):
    u"""O nivel lia as duas fontes; a lista lia so o nome.

    O proprio nivel_bundle da Vivo ja dizia por que isso esta errado:
    "max() porque o nome ACRESCENTA informacao, nunca tira: o texto pode
    citar um streaming que o nome nao cita, e o contrario tambem". O
    argumento vale igual para a lista, e a lista nao o seguia.

    MEDIDO NA VITRINE REAL DE SAO PAULO EM 21/10/2026, 7 ofertas de 49:

      Vivo Total V 1/2/10 Giga  texto: "Vivo TV Completo com HBO Max e
                                Telecine"            gravado: apps=[]
      Vivo Controle (x2)        texto nomeia McAfee            apps=[]
      Vivo Pre (x2)             texto nomeia Vale Saude        apps=[]

    Nos tres combos o campo ficava em contradicao aberta com o vizinho:
    nivel_bundle 4 ao lado de apps vazio. A oferta subia na tela sem
    dizer QUAL app inclui - que e a pergunta que o modulo de apps
    existe para responder.
    """

    def test_o_texto_acrescenta_o_que_o_nome_nao_diz(self):
        self.assertEqual(
            vivo.apps_da_vitrine(
                u"Vivo Total V 1 Giga",
                u"1Giga de Vivo Fibra Vivo TV Completo com HBO Max e Telecine"),
            ["max", "telecine"])

    def test_o_nome_acrescenta_o_que_o_texto_nao_diz(self):
        """O card da Vivo as vezes e so marcacao - "unique-card__bordered
        data-settings=..." - e ai quem nomeia o app e o nome."""
        self.assertEqual(
            vivo.apps_da_vitrine(u"Vivo Pós com Amazon",
                                 u'unique-card__bordered data-settings="{}"'),
            ["amazon"])

    def test_o_nome_vem_primeiro_e_ninguem_repete(self):
        """O nome e a leitura mais confiavel que a Vivo oferece: e onde
        ela batiza a oferta. Citado nos dois, o app entra uma vez."""
        self.assertEqual(
            vivo.apps_da_vitrine(u"Vivo Controle Netflix",
                                 u"Netflix e Telecine inclusos"),
            ["netflix", "telecine"])

    def test_sem_app_em_lugar_nenhum_a_lista_fica_vazia(self):
        self.assertEqual(
            vivo.apps_da_vitrine(u"Vivo Fibra", u"700 Mega com Wi-Fi 6"), [])

    def test_os_sufixos_da_vivo_valem_no_nome_dela(self):
        """"Vivo Controle Saude" e telemedicina - o sufixo e dela, e so
        vale porque a operadora e ela (ver DO_NOME_VIVO)."""
        self.assertEqual(
            vivo.apps_da_vitrine(u"Vivo Controle Saúde", u""),
            ["vale_saude"])


class OLiteFicavaForaDoDetectorDeRepasse(unittest.TestCase):
    u"""assinatura_sva existe para pegar repasse disfarcado, e o Lite nao a tinha.

    O comentario da propria montagem diz para que o campo serve: "se o
    preco nao se move e a assinatura muda, a oferta trocou de conteudo
    sem trocar de etiqueta, que e o repasse disfarcado da metodologia".

    ler_lite nao passa por enriquecer - monta a oferta direto do
    regulamento, que e fonte melhor que card - e nao montava o campo.
    Sao 80 linhas por dia (4 ofertas x 20 pracas) invisiveis para o
    detector de composicao, no produto que o tracker acompanha
    justamente para ver o PISO do mercado, onde repasse silencioso e o
    movimento esperado e nao o improvavel.

    O dado sempre esteve no regulamento. Medido em 21/10/2026:

        Vivo Lite Mensal II   R$ 45   030012+030021+030032+040022
        Vivo Lite Mensal III  R$ 55   ... +060016
        Vivo Lite Anual II    R$ 30   030012+030021+030032+040022
        Vivo Lite Anual III   R$ 40   ... +060016
    """

    def test_os_dois_blocos_entram_juntos(self):
        """No combo, movel e fixa declaram SVA cada um: ler so o
        primeiro perderia metade da composicao."""
        self.assertEqual(
            vivo.assinatura_sva({"listaSVA": ["040022"]},
                                {"listaSVA": ["030012"]}),
            (["030012", "040022"], "030012+040022"))

    def test_o_texto_vai_ordenado(self):
        """A comparacao entre dias e por igualdade de texto: ordem
        instavel acusaria troca de conteudo todo dia."""
        a = vivo.assinatura_sva({"listaSVA": ["060016", "030012"]}, {})
        b = vivo.assinatura_sva({"listaSVA": ["030012", "060016"]}, {})
        self.assertEqual(a, b)
        self.assertEqual(a[1], "030012+060016")

    def test_codigo_repetido_nos_dois_blocos_conta_uma_vez(self):
        self.assertEqual(
            vivo.assinatura_sva({"listaSVA": ["030012"]},
                                {"listaSVA": ["030012"]})[1], "030012")

    def test_sem_codigo_o_campo_fica_ausente_e_nao_vazio(self):
        """Ausencia e ausencia, nunca string vazia: "" compararia igual
        a "" entre dias e esconderia a chegada do primeiro servico."""
        self.assertEqual(vivo.assinatura_sva({}, {}), ([], None))
        self.assertEqual(vivo.assinatura_sva(None, None), ([], None))

    def test_bloco_sem_a_lista_nao_quebra(self):
        self.assertEqual(vivo.assinatura_sva({"velocidade": {}}, {})[1], None)

    def test_codigo_vazio_na_lista_nao_entra(self):
        self.assertEqual(
            vivo.assinatura_sva({"listaSVA": ["030012", "", None]}, {})[1],
            "030012")

    # Os codigos reais das quatro ofertas Lite de 21/10/2026, e o que o
    # regulamento declara em cada uma. O III tem um codigo SVA a mais
    # que o II, com R$ 10 de diferenca nas duas periodicidades.
    LITE_REAL = {
        "VIV202600045201": {
            "nomeOferta": "Vivo Lite Mensal II", "precoSemDescontos": 45.0,
            "SMP": {"listaSVA": ["040022", "030012", "030032", "030021"],
                    "franquiaDados": {"franquia": 30}}},
        "VIV202600045202": {
            "nomeOferta": "Vivo Lite Mensal III", "precoSemDescontos": 55.0,
            "SMP": {"listaSVA": ["040022", "030012", "030032", "030021",
                                 "060016"],
                    "franquiaDados": {"franquia": 30}}},
    }

    def _lite_offline(self):
        """ler_lite sem rede: buscar devolve o HTML, regulamento le do cache."""
        from datetime import date

        html = " ".join(self.LITE_REAL)
        guarda_buscar = vivo.buscar
        vivo.buscar = lambda op, url, **kw: (200, html)
        self.addCleanup(setattr, vivo, "buscar", guarda_buscar)
        for cod, reg in self.LITE_REAL.items():
            vivo._cache_regulamento[cod] = reg
            self.addCleanup(vivo._cache_regulamento.pop, cod, None)
        ofertas, erro = vivo.ler_lite(None, date(2026, 10, 21), [])
        self.assertIsNone(erro)
        return {o["nome_oferta"]: o for o in (ofertas or ())}

    def test_ler_lite_grava_a_assinatura(self):
        """A MUTACAO J3 PASSOU VERDE sem este teste. Os outros medem a
        funcao auxiliar; nenhum passava por ler_lite, entao nada notava
        se o Lite parasse de chama-la - que e o defeito consertado."""
        de = self._lite_offline()
        self.assertEqual(de["Vivo Lite Mensal II"]["assinatura_sva"],
                         "030012+030021+030032+040022")
        self.assertEqual(de["Vivo Lite Mensal III"]["assinatura_sva"],
                         "030012+030021+030032+040022+060016")

    def test_e_o_detector_de_composicao_ve_a_diferenca(self):
        """O ponto do campo: comparar o conjunto entre dias por
        igualdade. Se o II e o III saissem com a mesma assinatura, um
        repasse silencioso entre eles passaria batido."""
        de = self._lite_offline()
        self.assertNotEqual(de["Vivo Lite Mensal II"]["assinatura_sva"],
                            de["Vivo Lite Mensal III"]["assinatura_sva"])

    def test_o_nivel_de_bundle_nao_sai_da_contagem_de_codigos(self):
        """Quatro codigos SVA nao dizem QUE servico e, e a vitrine
        tambem nao grava nivel a partir deles - a "Vivo Total Familia 2"
        tem assinatura cheia e nivel 0. Subir o nivel por contagem seria
        inventar conteudo que a fonte nao nomeia."""
        de = self._lite_offline()
        self.assertIsNone(de["Vivo Lite Mensal II"].get("nivel_bundle"))

    def test_a_vitrine_e_o_lite_usam_a_MESMA_montagem(self):
        """Duas montagens da mesma coisa divergem na primeira correcao,
        e divergir na ordem faria o Lite parecer trocar de conteudo todo
        dia. Entao ha uma funcao so, e enriquecer tambem a chama."""
        reg = {"SMP": {"listaSVA": ["060016", "030012"]},
               "SCM": {"listaSVA": ["040022"]}}
        oferta = vivo.aplicar_regulamento(
            {"nome_oferta": "Vivo Pos", "preco_promocional": 119.90}, reg)
        self.assertEqual(oferta["assinatura_sva"],
                         vivo.assinatura_sva(reg["SMP"], reg["SCM"])[1])
        self.assertEqual(oferta["assinatura_sva"], "030012+040022+060016")


class ZeroDeclaradoNaoEAusencia(unittest.TestCase):
    u"""O espelho de "ausencia e ausencia, nunca zero".

    A linha era:

        oferta["fidelidade_meses"] = int(_num(...) or 0) or None

    e o "or None" do fim apagava um zero DECLARADO no mesmo None da
    ausencia. A linha de baixo, a multa, nunca fez isso - a assimetria
    entre duas linhas vizinhas que leem o mesmo bloco era o indicio.

    Um regulamento que escreve tempoFidelizacao: 0 esta FALANDO, e
    dizendo que a oferta nao tem fidelidade. E a informacao mais
    relevante que o campo carrega, porque e a unica que distingue "nao
    prende o cliente" de "nao consegui ler o contrato".

    LATENTE, NAO ATIVO: medido nos regulamentos reais de 21/10/2026,
    nenhum declara zero. O Lite Anual declara 12 meses e multa; o Lite
    Mensal nao tem bloco de fidelizacao nenhum.
    """

    def _fidelidade(self, bloco):
        reg = {} if bloco is None else {"fidelizacao": bloco}
        oferta = vivo.aplicar_regulamento(
            {"nome_oferta": "X", "preco_promocional": 50.0}, reg)
        return oferta.get("fidelidade_meses")

    def test_zero_declarado_fica_zero(self):
        self.assertEqual(self._fidelidade({"tempoFidelizacao": 0}), 0)

    def test_zero_declarado_como_texto_tambem(self):
        """O regulamento entrega numero ou string, conforme o campo."""
        self.assertEqual(self._fidelidade({"tempoFidelizacao": "0"}), 0)

    def test_prazo_normal_segue_igual(self):
        self.assertEqual(self._fidelidade({"tempoFidelizacao": "12"}), 12)

    def test_campo_ausente_no_bloco_fica_sem_resposta(self):
        self.assertIsNone(self._fidelidade({}))

    def test_bloco_calado_fica_sem_resposta(self):
        """SILENCIO NAO E AUSENCIA, e a metodologia decide isso: "um card
        que nao escreve Gemini nao esta dizendo que Gemini ficou fora -
        esta calado".

        Era tentador ler a falta do bloco num contrato PUBLICADO como
        "nao tem fidelidade" - o Vivo Lite Mensal nao tem o bloco e e
        vendido ao lado de um Anual que tem 12 meses e multa, entao o
        desenho do produto e sem compromisso. Mas inferir dali afirmaria
        contratualmente algo que o documento nao diz.
        """
        self.assertIsNone(self._fidelidade(None))

    def test_zero_e_ausencia_deixam_de_ser_a_mesma_coisa(self):
        """O ponto de tudo: os dois eram None e nao se distinguiam."""
        self.assertNotEqual(self._fidelidade({"tempoFidelizacao": 0}),
                            self._fidelidade(None))


class FaixaAbertaNaoEDegrau(unittest.TestCase):
    u"""A Starlink declara faixa no plano Max, e o tracker gravava o piso.

    MEDIDO NA API EM 21/10/2026:

        description     'Residencial - Max'
        longDescription '... * Ate mais de 400 Mbps * Dados ilimitados ...'

    degrau_mbps saia 400. "Ate mais de 400" e faixa aberta: a fonte diz
    que passa de 400 e se recusa a dizer quanto. Gravar 400 inventa
    precisao que a fonte nega, e inventa no PISO - o plano melhor da
    Starlink ia para 400 contra uma fibra de 700 ou 1000 no mesmo
    grafico. Decisao 8: exatas, sem faixas.
    """

    def test_piso_sem_teto_nao_vira_degrau(self):
        self.assertIsNone(starlink.velocidade("Ate mais de 400 Mbps"))
        self.assertIsNone(starlink.velocidade("Velocidades acima de 400 Mbps"))
        self.assertIsNone(starlink.velocidade("A partir de 50 Mbps"))

    def test_teto_do_proprio_numero_continua_valendo(self):
        """"Ate 100 Mbps" NAO e faixa aberta: e teto do mesmo numero que
        o nome do plano declara ("Residencial: 100 Mbps"). O que
        desqualifica e o piso sem teto, nao a palavra "ate"."""
        self.assertEqual(starlink.velocidade("Ate 100 Mbps."), 100)
        self.assertEqual(starlink.velocidade("Residencial: 100 Mbps"), 100)

    def test_gbps_segue_convertendo(self):
        self.assertEqual(starlink.velocidade("Download de 1 Gbps"), 1000)

    def test_sem_numero_nenhum(self):
        self.assertIsNone(starlink.velocidade("Residencial - Max"))
        self.assertIsNone(starlink.velocidade(None))

    def test_a_promessa_da_fonte_nao_se_perde(self):
        """NAO INVENTAR NAO E JOGAR FORA. O plano perde o degrau, mas a
        frase da operadora e a unica informacao que existe sobre a
        velocidade dele - vai gravada como ela escreveu."""
        self.assertEqual(
            starlink.velocidade_declarada(
                "Residencial - Max",
                "Melhor desempenho.\n * Ate mais de 400 Mbps\n * Dados "
                "ilimitados"),
            "Ate mais de 400 Mbps")

    def test_a_declarada_prefere_a_primeira_fonte_que_fala(self):
        self.assertEqual(
            starlink.velocidade_declarada("Residencial: 100 Mbps",
                                          "Ate 100 Mbps. Estavel."),
            "Residencial: 100 Mbps")

    def test_sem_velocidade_em_fonte_nenhuma_fica_vazio(self):
        """Os planos Prioritario descrevem o publico, nao a banda."""
        self.assertIsNone(starlink.velocidade_declarada(
            "Prioritario Local 500 GB",
            "Indicado para pequenas empresas com dois a quatro usuarios"))


class OColetorDaStarlinkMonta(unittest.TestCase):
    u"""O caminho de producao, nao so as funcoes de leitura.

    A MUTACAO K4 PASSOU VERDE sem esta classe: velocidade_declarada()
    tinha teste e nada verificava que coletar() punha o campo na oferta.
    Segunda vez na mesma sessao - J3 foi o Lite da Vivo - e o mesmo
    engano: teste de peca nao prova montagem.

    A carga e a resposta real da API em 21/10/2026, reduzida.
    """

    RESPOSTA = {
        "isAvailable": True,
        "isoCurrencyCode": "BRL",
        "kits": [
            {"description": "Kit Starlink Mini", "adjustedPrice": 99.0},
            {"description": "KIT INTERNET, STARLINK STANDARD",
             "adjustedPrice": 2400.0},
        ],
        "subscriptions": [
            {"description": "Residencial: 100\u00a0Mbps",
             "longDescription": "At\u00e9 100\u00a0Mbps. Servi\u00e7o de internet "
                                "residencial est\u00e1vel. Dados ilimitados.",
             "adjustedPrice": 189.0, "productId": "res-100"},
            {"description": "Residencial - M\u00e1x",
             "longDescription": "Nosso servi\u00e7o com melhor desempenho.\n"
                                " * At\u00e9 mais de 400 Mbps\n * Dados ilimitados",
             "adjustedPrice": 249.0, "productId": "res-max"},
        ],
    }

    def _coletar(self):
        import json

        guarda = starlink._http
        starlink._http = lambda url, **kw: (200, json.dumps(self.RESPOSTA))
        self.addCleanup(setattr, starlink, "_http", guarda)
        guarda_pausa = starlink.PAUSA
        starlink.PAUSA = 0
        self.addCleanup(setattr, starlink, "PAUSA", guarda_pausa)
        r = starlink.coletar("Sao Paulo", "SP", verbose=False)
        # as duas familias devolvem a mesma carga no teste; basta a
        # primeira ocorrencia de cada nome
        de = {}
        for o in r["ofertas"]:
            de.setdefault(o["nome_oferta"], o)
        return de

    def test_o_plano_com_faixa_nao_ganha_degrau(self):
        de = self._coletar()
        max_ = [o for n, o in de.items() if "x" in n[-2:]][0]
        self.assertIsNone(max_["degrau_mbps"],
                          "'Ate mais de 400 Mbps' e faixa, nao degrau")

    def test_e_a_promessa_da_fonte_vai_gravada(self):
        """O ponto: nao inventar nao e jogar fora. Sem o campo, o plano
        melhor da Starlink chegaria sem nenhuma informacao de banda."""
        de = self._coletar()
        max_ = [o for n, o in de.items() if "x" in n[-2:]][0]
        self.assertIn("400", max_["velocidade_declarada"] or "")

    def test_o_plano_que_declara_numero_segue_com_degrau(self):
        de = self._coletar()
        cem = [o for n, o in de.items() if "100" in n][0]
        self.assertEqual(cem["degrau_mbps"], 100)

    def test_o_kit_vem_com_o_nome_ao_lado_do_preco(self):
        """taxa_instalacao gravava so o numero e perdia de qual kit saiu:
        o minimo da familia residencial e o Kit Mini, hardware diferente
        do prato Standard que o plano sugere."""
        de = self._coletar()
        cem = [o for n, o in de.items() if "100" in n][0]
        self.assertEqual(cem["taxa_instalacao"], 99.0)
        self.assertEqual(cem["taxa_instalacao_kit"], "Kit Starlink Mini")


class ONumeroJaNumeroNaoPerdeACasaDecimal(unittest.TestCase):
    """_num tirava o ponto antes de converter, porque no formato
    brasileiro ele separa milhar - e aplicado a um float ja pronto isso
    apaga a casa decimal e multiplica por dez.

    Achado por um teste MEU que tropecou nele: escrevi a fixture do
    regulamento com 1200.0 e a guarda nao disparou, porque 12000 nao e
    menor que 3000. Latente hoje, e a uma mudanca de formato da Anatel
    de gravar preco e multa dez vezes maiores - e a guarda de preco so
    barra valor ABAIXO do da vitrine, nunca inflado.
    """

    def test_float_nao_vira_dez_vezes(self):
        self.assertEqual(vivo._num(1200.0), 1200.0)
        self.assertEqual(vivo._num(299.9), 299.9)

    def test_e_o_formato_brasileiro_continua_valendo(self):
        self.assertEqual(vivo._num("1.200,00"), 1200.0)
        self.assertEqual(vivo._num("299,90"), 299.9)

    def test_ausencia_continua_ausencia(self):
        for v in (None, "", "null", "abc"):
            self.assertIsNone(vivo._num(v))


if __name__ == "__main__":
    unittest.main(verbosity=2)
