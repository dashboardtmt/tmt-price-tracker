# -*- coding: utf-8 -*-
"""O que o tracker pode e nao pode afirmar sobre os apps das ofertas.

CADA TESTE AQUI E UM DEFEITO QUE EXISTIU. Nao sao casos inventados para
encher a suite: sao as coisas que o tracker ja escreveu errado, e que
voltariam a escrever se alguem mexesse no lugar errado.

A regra que todos defendem e uma so: o tracker so afirma o que a fonte
diz. Preco de referencia pertence ao TIER do app, e tier so existe
quando a operadora declara.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coletores import apps                                    # noqa: E402


class TierSaiDaFonte(unittest.TestCase):
    """Ate 15/10/2026 o tracker escrevia "Netflix (Padrao): R$ 44,90".

    Nenhuma operadora declara qual plano da Netflix a oferta inclui. O
    regulamento da Vivo, 1.928 caracteres, nao tem a palavra Padrao,
    Premium nem anuncio. O tier vinha de um valor fixo no dicionario, e
    o preco saia colado nele - palpite com cara de dado.
    """

    def test_netflix_sem_tier_declarado_nao_ganha_tier(self):
        self.assertIsNone(apps.tier_do_texto("netflix", "Vivo Pós com Netflix"))
        self.assertIsNone(apps.tier_do_texto("netflix", "VIVO POS COM NETFLIX"))
        self.assertEqual(apps.rotulo(["netflix"], "Vivo Pós com Netflix"),
                         "Netflix")

    def test_tier_declarado_na_anatel_vale(self):
        self.assertEqual(
            apps.tier_do_texto("disney", "VIVO POS COM DISNEY+ PADRAO"), "Padrão")
        self.assertEqual(
            apps.tier_do_texto("spotify", "VIVO POS COM SPOTIFY PREMIUM"), "Premium")

    def test_tier_declarado_no_nome_da_vitrine_vale(self):
        self.assertEqual(
            apps.tier_do_texto("youtube", "Controle YouTube Premium Lite"), "Lite")
        self.assertEqual(
            apps.tier_do_texto("netflix", "Assinatura Netflix Padrão inclusa"),
            "Padrão")

    def test_o_tier_mais_especifico_ganha(self):
        # "Padrao com anuncios" tem de ser testado antes de "Padrao",
        # senao o mais curto casa primeiro
        self.assertEqual(
            apps.tier_do_texto("netflix", "Netflix Padrão com anúncios"),
            "Padrão com anúncios")

    def test_tier_de_outro_app_nao_vaza(self):
        # "Vivo Pos com Netflix e Spotify Premium" dava tier Premium para
        # o Netflix: o Premium do Spotify estava dentro da janela
        self.assertIsNone(
            apps.tier_do_texto("netflix", "Vivo Pós com Netflix e Spotify Premium"))
        self.assertEqual(
            apps.tier_do_texto("spotify", "Vivo Pós com Netflix e Spotify Premium"),
            "Premium")

    def test_nome_do_app_nao_e_tier_dele(self):
        # "YouTube Premium" e o NOME do app. Sem a janela comecar depois
        # do nome, "Premium" virava tier do YouTube.
        self.assertIsNone(
            apps.tier_do_texto("youtube", "Vivo Controle YouTube Premium"))

    def test_frase_seguinte_nao_conta(self):
        self.assertIsNone(
            apps.tier_do_texto("netflix", "Netflix incluso. Spotify Premium à parte"))


class DegustacaoNaoEIncluso(unittest.TestCase):
    """Decisao 38: beneficio que acaba e desconto condicionado.

    "Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes" nao e
    um app incluso - e uma degustacao. Contar como incluso faz a oferta
    parecer melhor do que e.
    """

    def test_degustacao_nao_entra_na_lista(self):
        self.assertEqual(
            apps.apps_do_texto("Disney+ grátis por 3 meses"), [])
        self.assertEqual(
            apps.apps_do_texto("Disney+: 3 meses por conta da Claro. "
                               "Após, R$24,60 por mês."), [])

    def test_incluso_de_verdade_sobrevive_ao_lado_da_degustacao(self):
        self.assertIn("netflix", apps.apps_do_texto(
            "Netflix incluso. Disney+: 3 meses por conta da Claro."))
        self.assertNotIn("disney", apps.apps_do_texto(
            "Netflix incluso. Disney+: 3 meses por conta da Claro."))

    def test_o_corte_nao_leva_o_vizinho(self):
        # o corte voltava ate o ponto final anterior e, num texto sem
        # pontuacao, apagava o "Google One ou iCloud+" que vinha antes
        limpo = apps.sem_degustacao(
            "Armazenamento na nuvem: Google One ou iCloud+ "
            "Disney+: 3 meses por conta da Claro. Após, R$24,60 por mês.")
        self.assertIn("Google One", limpo)
        self.assertNotIn("3 meses", limpo)


class NivelEListaNaoSeContradizem(unittest.TestCase):
    """O nivel de bundle e a lista de apps leem a MESMA coisa.

    "Claro Pos 50 GB - Uma assinatura (Netflix, YouTube, Vale Saude...)"
    aparecia na tela numa oferta que nao inclui nenhum dos tres: a lista
    aplicava a decisao 38 e devolvia vazio, e o nivel varria o texto cru
    sem a regra.
    """

    CLARO_POS = ("Claro Pós 50GB Até 2 linhas R$ 124,90 /mês Armazenamento "
                 "na nuvem: Google One ou iCloud+ iCloud Google One "
                 "Disney+: 3 meses por conta da Claro. Após, R$24,60 por "
                 "mês. DisneyPlus WhatsApp ilimitado")

    def test_degustacao_nao_sobe_o_nivel(self):
        self.assertEqual(apps.apps_do_texto(self.CLARO_POS), [])
        self.assertEqual(apps.nivel_por_apps(self.CLARO_POS,
                                             ("google one", "icloud")), 1)

    def test_a_escada_dos_niveis(self):
        self.assertEqual(apps.nivel_por_apps("Só internet e ligações"), 0)
        self.assertEqual(apps.nivel_por_apps("Skeelo e McAfee inclusos"), 1)
        self.assertEqual(apps.nivel_por_apps("Netflix incluso no plano"), 2)
        self.assertEqual(apps.nivel_por_apps("Netflix e Max inclusos"), 3)


class NomesQueAsOperadorasUsam(unittest.TestCase):
    """A Brisanet escrevia NETFLIX no nome e a tela dizia que o site nao
    nomeia qual app vem junto."""

    def test_hbo_e_o_max(self):
        self.assertIn("max", apps.apps_do_texto("500MB + HBO PCA"))

    def test_sky_tem_entrada(self):
        self.assertIn("sky", apps.apps_do_texto("SET26 500MB + SKY LIGHT"))

    def test_sky_nao_casa_dentro_de_skeelo(self):
        self.assertNotIn("sky", apps.apps_do_texto("Skeelo incluso"))

    def test_prime_video_e_o_amazon(self):
        self.assertIn("amazon", apps.apps_do_texto("Prime video"))

    def test_amazon_sozinho_so_no_nome_da_oferta(self):
        # na prosa de um card, "Amazon" sozinho pode ser a loja; no nome
        # da oferta, so pode ser o app
        self.assertEqual(apps.apps_do_texto("compre na Amazon"), [])
        self.assertIn("amazon", apps.apps_da_oferta("AGO26 500MB + Amazon"))


class ADegustacaoQueDizDeQuemEla(unittest.TestCase):
    u"""A marca de cortesia que declara o proprio sujeito.

    MEDIDO NO TEXTO REAL DE 21/10/2026, vitrine da Vivo em Sao Paulo,
    tres ofertas "Vivo Total V":

        Vivo TV Completo com HBO Max e Telecine 12 meses gratis de
        Gemini com AI Plus Adicione 6 apps por R$ 50/mes

    apps_do_texto devolvia so ['max']. A janela de degustacao olha 110
    caracteres depois do nome do app, e o Telecine e o ultimo app
    citado - entao a janela dele varria a frase seguinte e achava "12
    meses gratis", cortesia do GEMINI, produto que nem esta no
    dicionario. A oferta com dois streamings aparecia com um, e o nivel
    por apps dava 2 em vez de 3.

    O portugues declara o sujeito depois da marca: "gratis DE Gemini".
    Quando declara, a marca vale para aquele produto e mais nenhum.
    """

    def test_o_vizinho_nao_cai_pela_cortesia_de_outro(self):
        t = (u"Vivo TV Completo com HBO Max e Telecine 12 meses grátis "
             u"de Gemini com AI Plus")
        self.assertEqual(apps.apps_do_texto(t), ["max", "telecine"])

    def test_e_o_nivel_acompanha(self):
        t = (u"Vivo TV Completo com HBO Max e Telecine 12 meses grátis "
             u"de Gemini com AI Plus")
        self.assertEqual(apps.nivel_por_apps(t), 3, "dois streamings")

    def test_a_regra_corta_nos_dois_sentidos(self):
        """Quando o sujeito declarado E o app, ele continua fora - senao
        a regra seria so uma porta de saida para qualquer degustacao.

        A mesma frase da Vivo, com o sujeito trocado: o Max fica e o
        Telecine sai, e e o "de Telecine" que decide.
        """
        t = (u"Vivo TV Completo com HBO Max e Telecine 12 meses grátis "
             u"de Telecine")
        self.assertEqual(apps.apps_do_texto(t), ["max"])

    def test_nome_de_duas_palavras_tambem(self):
        self.assertEqual(
            apps.apps_do_texto(u"12 meses grátis de Amazon Prime"), [])

    def test_por_conta_da_claro_nomeia_quem_paga(self):
        """A REGRESSAO QUE A PRIMEIRA VERSAO CAUSOU, em 8 ofertas reais
        da Claro. "3 meses por conta da Claro" tem um nome depois da
        marca, mas e o do PAGADOR, nao o do produto - e lido como
        sujeito, fazia a regra concluir "a cortesia e de outro" e contar
        o Disney+ como incluso. E o caso que originou o corte de
        degustacao, invertido pela propria correcao."""
        t = u"Disney+: 3 meses por conta da Claro. Após, R$24,60 por mês"
        self.assertEqual(apps.apps_do_texto(t), [])

    def test_so_gratis_cortesia_e_degustacao_tomam_produto(self):
        self.assertTrue(apps.MARCA_COM_SUJEITO.search(u"3 meses grátis"))
        self.assertTrue(apps.MARCA_COM_SUJEITO.search(u"cortesia"))
        self.assertFalse(apps.MARCA_COM_SUJEITO.search(u"3 meses por conta"))

    def test_marca_sem_nome_depois_segue_pela_proximidade(self):
        t = u"Netflix incluso. Disney+ grátis por 3 meses"
        self.assertEqual(apps.apps_do_texto(t), ["netflix"])


class OSufixoColadoNoNomeDoApp(unittest.TestCase):
    u""""SkyPlus" e "hbomax" devolviam lista vazia.

    O comentario do codigo justificava a fronteira final em \\bsky\\b
    assim: "sem isso casa dentro de Skeelo, que comeca igual e e outro
    app". E FALSO - "Skeelo" e s-k-e e "sky" e s-k-y. A fronteira era
    desnecessaria e custava o nome com sufixo colado.
    """

    def test_sky_com_sufixo_colado(self):
        self.assertEqual(apps.apps_do_texto("inclui SkyPlus"), ["sky"])

    def test_sky_com_mais(self):
        self.assertEqual(apps.apps_do_texto("inclui Sky+"), ["sky"])

    def test_e_skeelo_continua_sendo_skeelo(self):
        """A guarda que o comentario antigo dizia proteger. Ela nao
        dependia da fronteira final - depende do "e" no lugar do "y"."""
        self.assertEqual(apps.apps_do_texto("Skeelo incluso"), ["skeelo"])
        self.assertNotIn("sky", apps.apps_do_texto("Skeelo incluso"))

    def test_hbomax_colado(self):
        self.assertEqual(apps.apps_do_texto("inclui hbomax"), ["max"])

    def test_max_mantem_as_duas_fronteiras(self):
        """"max" solto casaria dentro de "climax" e "maxi", e nao precisa
        ser solto: o \\bhbo ja cobre a forma colada."""
        self.assertEqual(apps.apps_do_texto("o climax do plano"), [])
        self.assertEqual(apps.apps_do_texto("plano maxi"), [])
        self.assertEqual(apps.apps_do_texto("inclui Max"), ["max"])


class ADegustacaoDaFraseAnteriorNaoConta(unittest.TestCase):
    u"""A janela de tras atravessava o ponto.

    A degustacao e procurada em 24 caracteres antes do nome do app, e
    esses 24 pulavam o fim da frase anterior. "Promocao de degustacao
    encerrada. Netflix incluso no plano" devolvia lista vazia: uma
    degustacao que ACABOU derrubava o app da frase seguinte, e o
    resultado dependia da distancia entre as duas. A janela da frente ja
    parava no ponto.
    """

    def test_degustacao_encerrada_na_frase_anterior(self):
        t = u"Promo\u00e7\u00e3o de degusta\u00e7\u00e3o encerrada. Netflix incluso no plano."
        self.assertEqual(apps.apps_do_texto(t), ["netflix"])

    def test_e_a_degustacao_da_mesma_frase_continua_valendo(self):
        """O ponto e o limite, nao uma porta de saida: na mesma frase a
        marca segue derrubando o app."""
        t = u"Netflix em degusta\u00e7\u00e3o por 3 meses no plano"
        self.assertEqual(apps.apps_do_texto(t), [])

    def test_ponto_e_virgula_tambem_fecha(self):
        t = u"degusta\u00e7\u00e3o encerrada; Netflix incluso no plano."
        self.assertEqual(apps.apps_do_texto(t), ["netflix"])


class APrimeiraMencaoEhAQueVale(unittest.TestCase):
    u"""E isto NAO e descuido - o contraexemplo e texto real da Claro.

    Troquei re.search por re.finditer para que a segunda mencao pudesse
    salvar o app, pensando em "Disney+ em degustacao por 3 meses. No
    plano anual, Disney+ incluso para sempre". O texto real reprovou:

        ... Disney+: 3 meses por conta da Claro. Apos, R$24,60 por mes.
        DisneyPlus WhatsApp ilimitado

    A segunda mencao, "DisneyPlus", e resto de marcacao - nome de marca
    solto, sem afirmacao de inclusao em volta. Com finditer a janela
    dela sai limpa e o Disney entra numa oferta que so tem trial.

    Entre deixar um app de fora e anunciar como incluso um app que e
    trial, a metodologia escolhe o primeiro.
    """

    def test_nome_de_marca_solto_depois_da_degustacao_nao_salva_o_app(self):
        t = (u"Disney+: 3 meses por conta da Claro. Ap\u00f3s, R$24,60 por "
             u"m\u00eas. DisneyPlus WhatsApp ilimitado")
        self.assertEqual(apps.apps_do_texto(t), [])


class ONivelNaoContaAppQueNaoSabeNomear(unittest.TestCase):
    u"""nivel_dos_apps dizia 1 e rotulo dizia "".

    Nivel "com apps de catalogo" ao lado de rotulo vazio - os dois
    campos da mesma oferta se contradizendo. E a mesma regra dos codigos
    SVA, que o projeto ja aplica: "codigo sem dicionario e ruido com
    cara de informacao".
    """

    def test_chave_fora_do_dicionario_nao_sobe_o_nivel(self):
        self.assertEqual(apps.nivel_dos_apps(["inexistente"]), 0)
        self.assertEqual(apps.rotulo(["inexistente"]), "")

    def test_e_nao_arrasta_a_chave_conhecida_do_lado(self):
        self.assertEqual(apps.nivel_dos_apps(["netflix", "inexistente"]), 2)
        self.assertEqual(apps.rotulo(["netflix", "inexistente"]), "Netflix")

    def test_o_piso_continua_valendo(self):
        self.assertEqual(apps.nivel_dos_apps(["inexistente"], piso=1), 1)


class AMusicaDaOperadoraEhStreaming(unittest.TestCase):
    u"""claro_musica e vivo_musica ficavam fora de STREAMING.

    deezer e spotify estavam dentro, e vivo_tv - a TV da propria Vivo -
    tambem: a assimetria dentro da mesma familia era o indicio. O que a
    entrada de APPS diz ("servico da propria Claro; nao ha preco
    avulso") e sobre PRECO, nao sobre categoria.

    Mede 20 ofertas em 23/10/2026: a Vivo Controle Musica sai de nivel 1
    ("com apps de catalogo") para 2 ("com uma assinatura"). A chave nao
    muda - a variante sai da LISTA de apps, que continua a mesma - entao
    nao ha ruido de "mudou de versao" na mensagem do dia seguinte.
    """

    def test_a_musica_da_operadora_vale_uma_assinatura(self):
        self.assertEqual(apps.nivel_dos_apps(["vivo_musica"]), 2)
        self.assertEqual(apps.nivel_dos_apps(["claro_musica"]), 2)

    def test_igual_as_de_terceiros(self):
        for a in ("deezer", "spotify"):
            self.assertEqual(apps.nivel_dos_apps([a]), 2, a)

    def test_e_com_outra_streaming_sobe_a_dois(self):
        self.assertEqual(apps.nivel_dos_apps(["vivo_musica", "netflix"]), 3)

    def test_a_sky_continua_fora_de_proposito(self):
        """TV por assinatura: quem decide nivel 4 e a regra de "tv por
        assinatura" de cada coletor, nao a presenca do nome numa lista."""
        self.assertNotIn("sky", apps.STREAMING)
        self.assertEqual(apps.nivel_dos_apps(["sky"]), 1)

    def test_app_de_catalogo_segue_em_nivel_1(self):
        for a in ("skeelo", "mcafee", "vale_saude", "vivae"):
            self.assertEqual(apps.nivel_dos_apps([a]), 1, a)


class PrecoPertenceAoTier(unittest.TestCase):
    """O preco avulso nao e do app, e do plano do app."""

    def test_sem_tier_declarado_nao_ha_preco(self):
        self.assertIsNone(apps.TIERS.get("netflix") and
                          dict(apps.TIERS["netflix"]).get(None))

    def test_tiers_do_netflix_tem_mais_de_um(self):
        # se um dia sobrar so um tier, o preco poderia ser atribuido sem
        # declaracao - e esse e o erro que o teste existe para impedir
        self.assertGreater(len(apps.TIERS["netflix"]), 1)

    def test_app_de_plano_unico_pode_ter_preco_sem_tier(self):
        self.assertNotIn("amazon", apps.TIERS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
