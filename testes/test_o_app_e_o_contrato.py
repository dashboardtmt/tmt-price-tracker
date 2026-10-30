# -*- coding: utf-8 -*-
u"""O que mudou DENTRO da oferta, dito com palavras.

TRES PEDIDOS DE QUEM LE, EM 30/10/2026, sobre a mensagem daquela manha:

  "vc escreveu que esta com o mesmo preco e mesma entrega, mas nao
   explicou o que mudou"

A mensagem trazia tres ofertas da TIM com "mesmo preco (99,99) e mesma
entrega (600 Mbps) / e voltou a vitrine como outra versao da oferta". O
que havia mudado era a lista de apps - o Ultracombo 7 deixou de nomear
o Aya Ensinah, o Controle Smart passou a nomear o EXA Seguranca -, e o
dado estava gravado nas duas datas. A frase nomeava o fato sem contar
qual era.

  "vc colocou em 10 de 20: xxxx mas so escreveu o nome de 3 cidades,
   tambem nao entendi"

A lista de pracas saia com tres nomes em ordem alfabetica e nenhuma
marca de corte - e o PDF lia a MESMA frase cortada, entao a lista
inteira nao existia em canal nenhum. O bloco de grade ja declarava o
corte ("e mais 3 movimentos nesta grade, no relatorio"); este nao.

  e, do mesmo dia, a franquia contratual

A anunciada e contrato mais bonus temporario, e e ela que entra na
chave de continuidade. O Controle Smart trocou 5 GB de contrato por 15
nas mesmas 10 pracas, com os 45 GB da vitrine parados: nenhum dos seis
detectores tinha o que reportar.

O QUE ESTE ARQUIVO PRENDE. Os tres sao mudanca de TEXTO sobre dado que
ja existia, e e por isso que eles podem desaparecer num refactor sem
quebrar nada: a frase volta a ser a generica, o corte volta a ser
silencioso, o campo volta a ficar sem leitor. Cada teste aqui mede o
canal que o leitor usa - a mensagem e o PDF -, e nao a funcao que monta
a frase.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import robo                                                   # noqa: E402
from _apoio import (HOJE, ONTEM, dados, montar, oferta,       # noqa: E402
                    sem_declaracao)
from coletores.pracas import PRACAS, rotulo                   # noqa: E402

try:
    import relatorio
except ImportError:                                      # pragma: no cover
    relatorio = None

TODAS = [rotulo(p) for p in PRACAS]


def tim(nome="TIM Controle Smart", preco=58.99, gb=45, data=HOJE,
        pracas=None, apps=None, contratual=None, variante="simples"):
    """A mesma oferta em varias pracas, com a variante na chave.

    A VARIANTE ENTRA NA CHAVE porque e ela que o detector de remodelada
    persegue: chave diferente com o mesmo nome e exatamente o par que
    sobra para ele. Fixture que repetisse a chave cairia no detector de
    composicao e mediria outra coisa.
    """
    return [oferta(operadora="TIM", produto="controle", nome=nome,
                   preco=preco, gb=gb, praca=p, data=data, apps=apps,
                   contratual=contratual,
                   chave="TIM|controle|%dgb|%s" % (gb, variante))
            for p in (pracas if pracas is not None else TODAS)]


class OAppQueAVitrineNomeia(unittest.TestCase):
    """A versao mudou, o nivel de bundle nao: qual app entrou ou saiu."""

    def setUp(self):
        sem_declaracao(self)

    def _dia(self, apps_ontem, apps_hoje):
        return montar(
            tim(data=ONTEM, apps=apps_ontem, variante="com_aya_books"),
            tim(data=HOJE, apps=apps_hoje, variante="com_aya_books_exa"))

    def test_a_mensagem_diz_qual_app_saiu_da_vitrine(self):
        t = self._dia(["aya_books", "aya_ensinah"], ["aya_books"])
        self.assertIn("a vitrine deixou de listar \"Aya Ensinah\"", t)
        self.assertNotIn("voltou à vitrine como outra versão", t,
                         "a frase generica nao pode sobrar quando ha o que "
                         "dizer")

    def test_a_frase_fala_da_vitrine_e_nao_do_plano(self):
        """SILENCIO NAO E AUSENCIA, e a ressalva mora no sujeito e no
        verbo da frase: a VITRINE deixou de LISTAR. Dizer "deixou de
        incluir" seria afirmar sobre a oferta o que a fonte so disse
        sobre o proprio texto - o defeito de 23/10/2026, quando a Claro
        reescreveu a pagina do Flex e cinco apps sumiram de uma vez.

        A oracao explicativa saiu da linha em 30/10/2026: "o que e
        'silencio nao confirma...'? isso nao faz sentido". Ela mudou de
        canal, nao desapareceu - ver o teste do paragrafo do PDF."""
        t = self._dia(["aya_books", "aya_ensinah"], ["aya_books"])
        self.assertIn("a vitrine deixou de listar", t)
        self.assertNotIn("silêncio", t)
        self.assertNotIn("deixou de incluir", t)

    def test_e_qual_app_ela_passou_a_listar(self):
        t = self._dia(["aya_books"], ["aya_books", "exa"])
        self.assertIn("a vitrine passou a listar \"EXA Segurança\"", t)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_a_ressalva_metodologica_esta_no_paragrafo_do_anexo(self):
        """O OUTRO LADO DA MUDANCA DE 30/10/2026. A oracao saiu da linha
        da mensagem; se ela nao estiver aqui, o projeto passou a publicar
        "deixou de listar" sem dizer em canal nenhum que isso e sobre a
        pagina, e nao sobre o plano."""
        import pypdf
        d = dados(tim(data=ONTEM, apps=["aya_books", "aya_ensinah"],
                      variante="com_dois"),
                  tim(data=HOJE, apps=["aya_books"], variante="com_um"))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        # o extrator quebra a linha no meio da frase: o pedaço
        # contíguo é o que se pode medir
        self.assertIn("não constitui evidência de sua", texto)

    def test_os_dois_lados_no_mesmo_dia(self):
        t = self._dia(["aya_books", "deezer"], ["aya_books", "paramount"])
        self.assertIn("Paramount+", t)
        self.assertIn("Deezer", t)

    def test_sem_lista_de_apps_a_frase_generica_fica(self):
        """A vitrine que nao nomeia app nenhum nao da o que dizer, e a
        frase antiga e o que resta - ela nao foi apagada, foi
        substituida quando ha material."""
        t = self._dia(None, None)
        self.assertIn("voltou à vitrine como outra versão da oferta", t)

    def test_o_nivel_de_bundle_segue_dono_do_ramo_dele(self):
        """Quando o NIVEL muda, a frase dele diz mais do que o nome de um
        app - e e a mesma escala que a tela mostra."""
        ontem = [dict(l, nivel_bundle=0, apps=[])
                 for l in tim(data=ONTEM, variante="simples")]
        hoje = [dict(l, nivel_bundle=1, apps=["aya_books"])
                for l in tim(data=HOJE, variante="com_aya_books")]
        t = montar(ontem, hoje)
        self.assertIn("com apps de catálogo", t)

    def test_o_id_cru_do_app_nao_sai(self):
        """"aya_ensinah" e como o coletor guarda; codigo sem dicionario e
        ruido com cara de informacao (decisao 10)."""
        t = self._dia(["aya_books", "aya_ensinah"], ["aya_books"])
        self.assertNotIn("aya_ensinah", t)

    def test_app_sem_catalogo_sai_pelo_id_e_nao_desaparece(self):
        """Nome desconhecido e pior do que id cru? Nao: desaparecer e
        pior. A oferta mudou e o leitor tem de saber."""
        t = self._dia(["aya_books"], ["aya_books", "app_que_nao_existe"])
        self.assertIn("app_que_nao_existe", t)

    def test_o_grupo_nao_junta_ofertas_que_mudaram_de_jeito_diferente(self):
        """O bloco imprime as linhas da PRIMEIRA oferta sob um cabecalho
        que fala de todas. Com dois movimentos diferentes no mesmo grupo,
        a frase de uma sairia afirmada para a outra - o defeito de eleger
        um representante e publicar como fato."""
        ontem = (tim(nome="TIM Controle Smart", apps=["aya_books", "deezer"],
                     data=ONTEM, variante="a")
                 + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                       apps=["aya_books"], data=ONTEM, variante="a"))
        hoje = (tim(nome="TIM Controle Smart", apps=["aya_books"],
                    data=HOJE, variante="b")
                + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                      apps=["aya_books", "exa"], data=HOJE, variante="b"))
        t = montar(ontem, hoje)
        self.assertIn("Deezer", t)
        self.assertIn("EXA Segurança", t)

    def test_o_evento_nao_junta_pracas_que_mudaram_de_jeito_diferente(self):
        """A MESMA OFERTA pode mudar diferente em duas pracas, e ai sao
        dois eventos e nao um.

        A identidade do evento agrupa pracas, e o texto sai de uma delas.
        Sem a lista de apps na identidade, "em 20 pracas a vitrine passou
        a nomear EXA" sairia sobre dez pracas em que ela parou de nomear
        o Deezer - o defeito de eleger um representante e publicar como
        fato, que este projeto ja consertou em "onde" e em
        "outras_leituras".
        """
        ontem = tim(data=ONTEM, apps=["aya_books", "deezer"],
                    variante="com_aya_books_deezer")
        hoje = (tim(data=HOJE, apps=["aya_books", "deezer", "exa"],
                    pracas=TODAS[:10], variante="com_tres")
                + tim(data=HOJE, apps=["aya_books"], pracas=TODAS[10:],
                      variante="com_aya_books"))
        t = montar(ontem, hoje)
        self.assertIn("EXA Segurança", t)
        self.assertIn("Deezer", t)
        self.assertIn("em 10 de 20:", t)

    def test_o_select_do_indice_pede_a_lista_de_apps(self):
        """SEM ISTO O DETECTOR LE None TODO DIA EM PRODUCAO, e o replay
        offline nao pega: ele le o JSON publicado, que traz todas as
        colunas. Foi assim que avisos_oferta ficou sem leitor."""
        import inspect
        self.assertIn("apps:bruto->apps", inspect.getsource(robo._indexar))

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_o_pdf_diz_a_mesma_coisa(self):
        """A coluna Versao dizia "outra versao da oferta" pelo mesmo
        motivo, e o texto vem pronto do robo para os dois canais nao
        poderem divergir."""
        import pypdf
        d = dados(tim(data=ONTEM, apps=["aya_books", "aya_ensinah"],
                      variante="com_aya_books_aya_ensinah"),
                  tim(data=HOJE, apps=["aya_books"],
                      variante="com_aya_books"))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Aya Ensinah", texto)


class OCorteDaListaDePracas(unittest.TestCase):
    """"em 10 de 20" com tres nomes e sem dizer que havia mais sete."""

    def setUp(self):
        sem_declaracao(self)

    def _reajuste_em(self, quantas):
        """Reajuste em N pracas, com a oferta existindo nas 20.

        O REAJUSTE E DE PROPOSITO, e nao uma mudanca de versao: preco
        nunca cai na regra de "minoria das pracas e nossa leitura", e
        aqui o que se mede e a linha da praca, nao a atribuicao.
        """
        ontem = tim(preco=58.99, data=ONTEM)
        hoje = (tim(preco=69.99, data=HOJE, pracas=TODAS[:quantas])
                + tim(preco=58.99, data=HOJE, pracas=TODAS[quantas:]))
        return montar(ontem, hoje)

    def test_quando_quase_todas_mudaram_a_frase_nomeia_a_excecao(self):
        """Pedido de 30/10/2026: "no caso de 19, coloque em 19 das 20
        cidades, ex-Rio de Janeiro". Tres nomes de dezenove nao dizem
        onde o movimento NAO foi, e e essa a pergunta que sobra."""
        t = self._reajuste_em(19)
        de_fora = TODAS[19].split("/")[0]
        self.assertIn("em 19 das 20 cidades, ex-%s" % de_fora, t)
        self.assertNotIn("e mais 16", t)

    def test_com_duas_excecoes_as_duas_saem_costuradas(self):
        t = self._reajuste_em(18)
        a, b = sorted(p.split("/")[0] for p in TODAS[18:])
        self.assertIn("em 18 das 20 cidades, ex-%s e %s" % (a, b), t)

    def test_com_muitas_excecoes_volta_a_lista_do_que_mudou(self):
        """A frase da excecao existe para ser mais curta E dizer mais.
        Com dez de fora ela nao e nenhuma das duas coisas."""
        t = self._reajuste_em(10)
        self.assertNotIn("ex-", t)
        self.assertIn("em 10 de 20:", t)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_o_anexo_diz_a_excecao_com_as_mesmas_palavras(self):
        """A frase da excecao e COMPLETA - dela se deduz a lista inteira
        -, entao aqui ela vale para os dois canais, ao contrario do corte
        em tres nomes."""
        import pypdf
        ontem = tim(preco=58.99, data=ONTEM)
        hoje = (tim(preco=69.99, data=HOJE, pracas=TODAS[:19])
                + tim(preco=58.99, data=HOJE, pracas=TODAS[19:]))
        d = dados(ontem, hoje)
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("19 das 20 cidades", texto)

    def test_a_mensagem_declara_quantas_pracas_faltam(self):
        t = self._reajuste_em(10)
        self.assertIn("em 10 de 20:", t)
        self.assertIn("e mais 7, no relatório", t)

    def test_com_tres_ou_menos_nao_sobra_marca_de_corte(self):
        """A marca so existe onde houve corte: "e mais 0" seria ruido."""
        t = self._reajuste_em(3)
        self.assertIn("em 3 de 20:", t)
        self.assertNotIn("e mais", t)

    def test_todas_as_pracas_segue_saindo_por_extenso(self):
        t = self._reajuste_em(20)
        self.assertIn("em todas as 20 praças", t)
        self.assertNotIn("e mais", t)

    def test_a_conta_fecha_com_o_numero_da_propria_frase(self):
        """3 nomes + "e mais 7" tem de somar os 10 que a frase anuncia:
        quem le soma, e uma frase que nao fecha vale menos que nenhuma."""
        t = self._reajuste_em(10)
        linha = [l for l in t.splitlines() if "em 10 de 20:" in l][0]
        nomes = linha.split(":", 1)[1].split("e mais")[0]
        self.assertEqual(len([x for x in nomes.split(",") if x.strip()]), 3)
        self.assertIn("e mais 7", linha)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_o_relatorio_traz_a_lista_inteira(self):
        """E PARA CA QUE A MENSAGEM MANDA O LEITOR. Enquanto o PDF lia a
        frase cortada, "no relatorio" era uma promessa falsa."""
        import pypdf
        ontem = tim(preco=58.99, data=ONTEM)
        hoje = (tim(preco=69.99, data=HOJE, pracas=TODAS[:10])
                + tim(preco=58.99, data=HOJE, pracas=TODAS[10:]))
        d = dados(ontem, hoje)
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        decima = sorted({p.split("/")[0] for p in TODAS[:10]})[-1]
        self.assertIn(decima, texto,
                      "a decima praca do evento nao esta no anexo")
        self.assertNotIn("no relatório", texto,
                         "o anexo nao manda o leitor para si mesmo")


class AFranquiaDoContrato(unittest.TestCase):
    """A mesma oferta na vitrine e outro numero no contrato."""

    def setUp(self):
        sem_declaracao(self)

    def _so_o_contrato(self, antes=20, agora=15, preco=58.99):
        return (tim(data=ONTEM, contratual=antes),
                tim(data=HOJE, contratual=agora, preco=preco))

    def test_a_mensagem_conta(self):
        t = montar(*self._so_o_contrato())
        self.assertIn("a franquia contratual foi de 20 para 15 GB", t)

    def test_e_mostra_a_anunciada_parada_ao_lado(self):
        """E O CONTRASTE QUE IMPORTA: 45 GB na vitrine com 20 de contrato
        e uma oferta diferente dos mesmos 45 GB com 15."""
        t = montar(*self._so_o_contrato())
        self.assertIn("mesma entrega (45 GB)", t)

    def test_e_conta_como_mudanca_do_dia(self):
        """Fora da contagem, o dia sairia como "nenhuma mudanca" com uma
        mudanca de contrato em 20 pracas."""
        t = montar(*self._so_o_contrato())
        self.assertIn("1 mudança hoje", t)

    def test_um_lado_nao_lido_nao_e_movimento(self):
        """Sete dos nove coletores nao leem contratual. "de None para 15"
        seria movimento inventado sobre campo que nunca foi lido - a
        mesma regra de _parado e de _mesmo_preco."""
        t = montar(*self._so_o_contrato(antes=None))
        self.assertNotIn("contratual", t)

    def test_igual_nos_dois_dias_tambem_nao(self):
        t = montar(*self._so_o_contrato(antes=15, agora=15))
        self.assertNotIn("contratual", t)

    def test_o_preco_que_mexeu_nao_sai_duas_vezes(self):
        """O bloco do preco ja conta o reajuste. Repetir aqui seria a
        mesma noticia duas vezes, que e o defeito que este projeto mais
        persegue - e o contrato continua saindo."""
        t = montar(*self._so_o_contrato(preco=69.99))
        self.assertEqual(t.count("58,99 → 69,99"), 1)
        self.assertIn("a franquia contratual foi de 20 para 15 GB", t)

    def test_e_quando_o_preco_ficou_parado_ele_sai_junto(self):
        """Mesmo preco com menos contrato e o contraste completo."""
        t = montar(*self._so_o_contrato())
        self.assertIn("mesmo preço (58,99)", t)

    def test_a_remodelada_leva_a_linha_do_contrato(self):
        """O OUTRO CAMINHO: quando a chave muda e o nome fica, o par vem
        do detector de remodelada e nao deste - e a contratual tem de
        aparecer ali tambem. Foi o caso real da TIM em 30/10/2026."""
        t = montar(tim(data=ONTEM, contratual=5, apps=["aya_books"],
                       variante="com_aya_books"),
                   tim(data=HOJE, contratual=15,
                       apps=["aya_books", "exa"],
                       variante="com_aya_books_exa"))
        self.assertIn("a vitrine passou a listar \"EXA Segurança\"", t)
        self.assertIn("a franquia contratual foi de 5 para 15 GB", t)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_e_o_contrato_sai_na_tabela_das_remodeladas(self):
        """A FORMA CURTA, na celula de 24 mm, colada na entrega
        anunciada: e contra ela que o numero do contrato se le. A longa
        saiu na mensagem, e as duas vem do robo para nao divergirem."""
        import pypdf
        d = dados(tim(data=ONTEM, contratual=5, apps=["aya_books"],
                      variante="com_aya_books"),
                  tim(data=HOJE, contratual=15,
                      apps=["aya_books", "exa"],
                      variante="com_aya_books_exa"))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        # O PDF QUEBRA A CELULA EM LINHAS, e o extrator devolve a
        # quebra: "mesma entrega (45 GB)" sai em duas. A asserçao mede
        # os pedaços, senao ela falha por formataçao e nao por conteudo.
        self.assertIn("contrato: 5", texto)
        self.assertIn("mesma entrega", texto)

    def test_o_select_do_indice_pede_a_contratual(self):
        import inspect
        self.assertIn("franquia_contratual_gb",
                      inspect.getsource(robo._indexar))

    def test_o_evento_diz_em_que_praca(self):
        d = dados(*self._so_o_contrato())
        for c in d["contratuais"]:
            self.assertTrue(c.get("onde"))

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_o_relatorio_tem_a_secao(self):
        import pypdf
        d = dados(*self._so_o_contrato())
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Alterações de franquia contratual", texto)
        self.assertIn("20 GB", texto)
        self.assertIn("15 GB", texto)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_a_secao_vazia_diz_que_esta_vazia(self):
        """A SECAO NAO DESAPARECE no dia sem movimento: quem le nao tem
        como distinguir "nao houve" de "o relatorio quebrou no meio" -
        mesma regra das outras seis."""
        import pypdf
        d = dados(tim(data=ONTEM), tim(data=HOJE))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Alterações de franquia contratual", texto)
        self.assertIn("Nenhuma alteração de franquia contratual", texto)


class AFraseDaExcecaoSoAfirmaOQueFoiOlhado(unittest.TestCase):
    """"ex-Rio de Janeiro" diz que no Rio a oferta foi olhada e nao se
    mexeu. Medido em 30/10/2026 nos 30 dias publicados: com o
    denominador do PRODUTO, as 9 frases que sairiam eram todas falsas -
    6 nomeavam cidade em que a oferta nem e vendida, 1 nomeava cidade
    sem coleta no dia anterior, 2 nomeavam a cidade em que a MESMA
    mudanca saiu como outro evento.
    """

    def setUp(self):
        sem_declaracao(self)

    def test_cidade_sem_coleta_ontem_nao_entra_como_excecao(self):
        """O caso de 13/10/2026: a coleta de Belo Horizonte falhou em
        12/10, e o reajuste da Claro alcancou BH como as outras 19. A
        frase saia "ex-Belo Horizonte" - afirmando que lá o preco ficou
        parado no dia em que nao houve com que comparar."""
        ontem = tim(preco=58.99, data=ONTEM, pracas=TODAS[:19])
        hoje = (tim(preco=69.99, data=HOJE, pracas=TODAS[:19])
                + tim(preco=69.99, data=HOJE, pracas=TODAS[19:]))
        t = montar(ontem, hoje)
        self.assertNotIn("ex-", t)
        self.assertIn("em 19 de 20:", t)

    def test_cidade_sem_a_oferta_nao_entra_como_excecao(self):
        """Seis das nove frases eram desta forma: "TIM Ultracombo 3" nao
        e vendida em Sao Paulo, e o anexo dizia "ex-Sao Paulo" como se lá
        ela tivesse ficado parada. O denominador era a pegada do
        PRODUTO; a frase fala de uma OFERTA."""
        ontem = (tim(nome="TIM Controle Smart", preco=58.99, data=ONTEM,
                     pracas=TODAS[:5])
                 + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                       data=ONTEM, pracas=TODAS[5:]))
        hoje = (tim(nome="TIM Controle Smart", preco=69.99, data=HOJE,
                    pracas=TODAS[:5])
                + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                      data=HOJE, pracas=TODAS[5:]))
        t = montar(ontem, hoje)
        self.assertNotIn("ex-", t)

    def test_praca_de_outro_evento_da_mesma_oferta_nao_entra(self):
        """O caso de 30/10/2026: em Sao Paulo o preco da oferta e outro,
        entao a perna de lá sai como evento separado - e a mensagem
        dizia "ex-Sao Paulo" na linha de cima e contava a mudanca de Sao
        Paulo tres linhas abaixo. O anexo chegava a dizer "ex-Sao Paulo"
        numa secao e "em 1 de 20: Sao Paulo" na seguinte."""
        ontem = (tim(preco=58.99, data=ONTEM, pracas=TODAS[:19])
                 + tim(preco=48.99, data=ONTEM, pracas=TODAS[19:]))
        hoje = (tim(preco=69.99, data=HOJE, pracas=TODAS[:19])
                + tim(preco=58.99, data=HOJE, pracas=TODAS[19:]))
        t = montar(ontem, hoje)
        self.assertNotIn("ex-", t)
        self.assertIn("58,99 → 69,99", t)
        self.assertIn("48,99 → 58,99", t)

    def test_o_denominador_e_o_que_foi_comparado(self):
        """"19 das 20" quer dizer "das 20 cidades comparadas, 19 se
        mexeram" - e e isso que faz a lista inteira se deduzir da frase.
        Com o universo do produto no lugar, a conta nao fecha com nada
        que o leitor possa verificar."""
        ontem = (tim(nome="TIM Controle Smart", preco=58.99, data=ONTEM,
                     pracas=TODAS[:15])
                 + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                       data=ONTEM, pracas=TODAS[15:]))
        hoje = (tim(nome="TIM Controle Smart", preco=69.99, data=HOJE,
                    pracas=TODAS[:14])
                + tim(nome="TIM Controle Smart", preco=58.99, data=HOJE,
                      pracas=TODAS[14:15])
                + tim(nome="TIM Controle Premium", preco=84.99, gb=55,
                      data=HOJE, pracas=TODAS[15:]))
        t = montar(ontem, hoje)
        de_fora = TODAS[14].split("/")[0]
        self.assertIn("em 14 das 15 cidades, ex-%s" % de_fora, t)
        self.assertNotIn("das 20 cidades", t)

    def test_a_escada_e_o_degrau_que_voltou_nao_usam_a_frase(self):
        """Os dois falam do PORTFOLIO, e nao de uma oferta: "a cidade X
        foi olhada e a oferta nao se mexeu" nao e frase que eles
        autorizem. _serie_do_evento devolve None para quem nao tem nome
        de oferta, e e isso que desliga a frase."""
        self.assertIsNone(robo._serie_do_evento(
            {"operadora": "TIM", "produto": "controle", "pracas": []}))
        self.assertIsNone(robo._serie_do_evento(
            {"operadora": "TIM", "produto": "controle",
             "atual": {"operadora": "TIM", "produto": "controle",
                       "nome_oferta": ""}}))


class OsConsertosDaAuditoria(unittest.TestCase):
    """Cada um destes defeitos passou pela suite de 548 testes verde."""

    def setUp(self):
        sem_declaracao(self)

    def test_dois_degraus_do_mesmo_nome_sao_dois_eventos_de_contrato(self):
        """O ident do contrato nao levava a chave: o degrau de 100 GB
        desaparecia dentro do evento do de 50, e o dia saia com "1
        mudanca" em vez de 2."""
        ontem = (tim(gb=50, preco=58.99, data=ONTEM, contratual=20)
                 + tim(gb=100, preco=98.99, data=ONTEM, contratual=20))
        hoje = (tim(gb=50, preco=58.99, data=HOJE, contratual=15)
                + tim(gb=100, preco=98.99, data=HOJE, contratual=15))
        t = montar(ontem, hoje)
        self.assertIn("2 mudanças hoje", t)
        self.assertIn("mesma entrega (50 GB)", t)
        self.assertIn("mesma entrega (100 GB)", t)

    def test_o_preco_de_uma_praca_nao_vale_para_as_vinte(self):
        """Sem os precos no ident, as vinte pracas colapsavam num evento
        e a linha saia "mesmo preco (69,90)" - o numero de Sao Paulo
        afirmado para todas as outras."""
        ontem = (tim(preco=58.99, data=ONTEM, pracas=TODAS[:19],
                     contratual=20)
                 + tim(preco=48.99, data=ONTEM, pracas=TODAS[19:],
                       contratual=20))
        hoje = (tim(preco=58.99, data=HOJE, pracas=TODAS[:19],
                    contratual=15)
                + tim(preco=48.99, data=HOJE, pracas=TODAS[19:],
                      contratual=15))
        t = montar(ontem, hoje)
        self.assertIn("mesmo preço (58,99)", t)
        self.assertIn("mesmo preço (48,99)", t)
        self.assertNotIn("em todas as 20 praças", t)

    def test_o_mesmo_app_nao_sai_dos_dois_lados_da_frase(self):
        """Medido em 19/10/2026 na Brisanet: a lista passou de ["Skeelo",
        "Reforça"] para ["max", "skeelo"] - o coletor trocou rotulo por
        id. Diffando por id, a frase dizia "passou a listar "Max" e
        "Skeelo", e deixou de listar "Reforça" e "Skeelo""."""
        t = montar(tim(data=ONTEM, apps=["Skeelo", "Reforça"],
                       variante="rotulo"),
                   tim(data=HOJE, apps=["max", "skeelo"], variante="id"))
        self.assertEqual(t.count('"Skeelo"'), 0,
                         "app presente nos dois dias nao mudou de lado")
        self.assertIn('"Max"', t)
        self.assertIn('"Reforça"', t)

    def test_tres_apps_saem_costurados(self):
        t = montar(tim(data=ONTEM, apps=["aya_books"], variante="um"),
                   tim(data=HOJE, apps=["aya_books", "exa", "max",
                                        "paramount"], variante="quatro"))
        self.assertIn('"EXA Segurança", "Max" e "Paramount+"', t)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_a_secao_do_contrato_nao_nega_a_tabela_de_cima(self):
        """Em 23/10 e em 30/10/2026 o PDF imprimia "contrato: 5 -> 15
        GB" na tabela das remodeladas e, trinta linhas abaixo, "Nenhuma
        alteracao de franquia contratual identificada" - 2 dos 4 dias
        com movimento nos 30 publicados."""
        import pypdf
        d = dados(tim(data=ONTEM, contratual=5, apps=["aya_books"],
                      variante="com_um"),
                  tim(data=HOJE, contratual=15,
                      apps=["aya_books", "exa"], variante="com_dois"))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertNotIn("Nenhuma alteração de franquia contratual", texto)
        self.assertIn("Alterações de franquia contratual", texto)

    @unittest.skipIf(relatorio is None, "reportlab nao instalado")
    def test_nome_com_e_comercial_atravessa_o_pdf(self):
        """A celula do PDF e mini-XML, e em 30/10/2026 ela passou a
        receber nome de app vindo da vitrine. A suspeita era de que um
        "&" derrubasse o relatorio do dia; medido, ele atravessa."""
        import pypdf
        d = dados(tim(nome="TIM Controle Sky & Max", preco=58.99,
                      data=ONTEM),
                  tim(nome="TIM Controle Sky & Max", preco=69.99,
                      data=HOJE))
        caminho = os.path.join(tempfile.mkdtemp(), "r.pdf")
        relatorio.gerar(d, {}, caminho)
        texto = "".join(p.extract_text()
                        for p in pypdf.PdfReader(caminho).pages)
        self.assertIn("Sky & Max", texto)


@unittest.skipIf(relatorio is None, "reportlab nao instalado")
class OQueDerrubariaOPdf(unittest.TestCase):
    """O risco latente da celula, escrito com o que o mede.

    ESTE TESTE FIXA O COMPORTAMENTO SEM GUARDA DE PROPOSITO, como
    ORiscoLatenteDoLimiteDeApps faz com o limite de apps: a guarda que
    eu escrevi primeiro escapava o "&", que nao e o que quebra, e nao
    tinha um caso em 49.605 linhas. Salvaguarda morta esconde o risco de
    verdade em vez de cobri-lo.

    SE UM COLETOR COMECAR A TRAZER "<" SEGUIDO DE LETRA, a guarda entra
    em _p e este teste muda de lado - com dado para apontar, e nao com
    suspeita.
    """

    def test_o_que_o_reportlab_recusa_e_tag_aberta(self):
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import Paragraph
        estilo = ParagraphStyle("x")
        for texto in ("Sky & Max", "A < B", "A <b>B</b>"):
            Paragraph(texto, estilo).wrap(200, 100)
        with self.assertRaises(ValueError):
            Paragraph("A & <B", estilo).wrap(200, 100)

    def test_e_a_vitrine_nao_traz_nenhum_dos_tres_sinais(self):
        """A medicao que decide: 49.605 linhas publicadas, zero
        ocorrencias. O teste roda sobre a fixture, que e o que esta a
        mao aqui; o numero da base esta na docstring de _p."""
        linhas = tim(data=HOJE) + tim(data=ONTEM)
        for l in linhas:
            for campo in ("nome_oferta", "destaque"):
                self.assertNotRegex(str(l.get(campo) or ""), r"[<>&]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
