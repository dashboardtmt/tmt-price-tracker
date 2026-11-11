# -*- coding: utf-8 -*-
u"""O arquivo da tela, o teto do Storage e o caminho de volta.

O QUE ACONTECEU EM 11/11/2026. A exportacao do dia gerou 51.254 KB e o
Storage recusou o upload - HTTP 400 trazendo "413 Payload too large",
porque o objeto passou dos 50 MB do plano. O job da tela morreu no
passo de publicar, e ate ali tudo que chega ao usuario estava certo: a
mensagem das 6h21 com o dado de hoje, o PDF anexado com o dado de hoje,
o site no ar. So que o site servia o retrato do dia 10, e nada na
pagina dizia isso.

A serie crescia 1,16 MB por dia. O limite nao foi um acidente - foi uma
data no calendario que ninguem tinha calculado.

COMPRIMIDO, O ARQUIVO CABE COM MUITA FOLGA: 48,7 MB viram 1,4 MB,
porque a serie repete a mesma oferta em 20 pracas por 43 dias. O que
este arquivo prende e tudo que, mexido sem perceber, traz o defeito de
volta - e cada um deles volta CALADO, com a pagina no ar:

  1. a pagina buscando o nome antigo, que agora e uma placa e nao uma
     lista: tela sem dado;
  2. a pagina baixando o .gz sem descomprimir: tela sem dado;
  3. a guarda do navegador sem gzip indo embora numa limpeza: tela
     vazia, sem erro, em quem nao tem DecompressionStream;
  4. a compressao deixando de ser deterministica: a conferencia do que
     subiu contra o que esta no ar perde sentido;
  5. o nome antigo voltando a receber o dado: um dia o upload falha e a
     URL serve o dia anterior de novo, que e o defeito inteiro;
  6. o job que avisa que o painel parou saindo do yml: volta o quadrado
     vermelho como unico sinal.
"""
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import publicar_dados                                            # noqa: E402

ROTINA = os.path.join(RAIZ, ".github", "workflows", "diario.yml")
AVULSO = os.path.join(RAIZ, ".github", "workflows", "atualizar-tela.yml")
GERADOR = os.path.join(RAIZ, "gerar_tela.py")


def _texto(caminho):
    with io.open(caminho, encoding="utf-8") as f:
        return f.read()


def _serie(dias=3, pracas=4):
    u"""Uma serie com a forma da de verdade: a mesma oferta repetida."""
    fora = []
    for d in range(dias):
        for p in range(pracas):
            fora.append({"operadora": "Vivo", "produto": "prepago",
                         "praca": "Cidade %d/SP" % p,
                         "data_captura": "2026-11-%02d" % (d + 1),
                         "nome_oferta": u"Vivo Pré", "preco_promocional": 35.0,
                         "assinatura_sva": "030012+030021+060016"})
    return fora


class OCaminhoDeIdaEVolta(unittest.TestCase):

    def test_o_json_volta_inteiro(self):
        serie = _serie()
        bruto = json.dumps(serie, ensure_ascii=False).encode("utf-8")
        self.assertEqual(
            publicar_dados.descompactar(publicar_dados.compactar(bruto)),
            serie)

    def test_e_gzip_de_verdade_e_nao_deflate_cru(self):
        u"""DecompressionStream("gzip") espera o container, com os dois
        bytes de assinatura. Deflate cru decodifica em Python e falha no
        navegador - erro que so apareceria na tela."""
        b = publicar_dados.compactar(b"[]")
        self.assertEqual(b[:2], b"\x1f\x8b")
        self.assertEqual(gzip.decompress(b), b"[]")

    def test_o_cabecalho_nao_carrega_o_relogio(self):
        u"""O campo MTIME do gzip, que sao os bytes 4 a 8 do cabecalho.

        ESTE TESTE JA EXISTIU MEDINDO NADA. Ele comparava compactar()
        com compactar() e afirmava determinismo - mas as duas chamadas
        caem no mesmo segundo, entao a hora era igual mesmo SEM mtime=0,
        e tirar o mtime=0 nao quebrava nada. A mutacao Gz1 mostrou isso:
        a unica forma de a comparacao falhar era o teste rodar na virada
        do segundo, uma vez a cada tantas execucoes.

        E O PADRAO DO gzip.compress MUDOU NO MEIO: ate o 3.12 e o
        relogio, do 3.13 em diante e zero. Quem desenvolve numa versao
        e publica na outra nao pode herdar esse campo - e um teste que
        compara duas chamadas da MESMA versao nunca veria isso.

        Lendo o campo direto, o sinal esta sempre la.
        """
        b = publicar_dados.compactar(json.dumps(_serie()).encode("utf-8"))
        self.assertEqual(b[4:8], b"\x00\x00\x00\x00")
        self.assertEqual(publicar_dados.compactar(b"[]"),
                         publicar_dados.compactar(b"[]"))

    def test_comprimir_vale_a_pena_na_forma_real(self):
        u"""Nao e microotimizacao: a serie e repetitiva por construcao -
        a mesma oferta em cada praca, em cada dia."""
        bruto = json.dumps(_serie(dias=10, pracas=20)).encode("utf-8")
        self.assertLess(len(publicar_dados.compactar(bruto)), len(bruto) / 10.0)


class OTetoDoStorage(unittest.TestCase):

    def test_o_limite_e_o_do_plano(self):
        self.assertEqual(publicar_dados.LIMITE_DO_STORAGE, 50 * 1024 * 1024)

    def test_abaixo_do_limite_passa(self):
        ok, erro = publicar_dados.cabe(b"x" * 1024)
        self.assertTrue(ok)
        self.assertIsNone(erro)

    def test_acima_do_limite_falha_antes_de_subir(self):
        u"""O 413 do servidor chega embrulhado num HTTP 400 e levou uma
        leitura de log para virar "passou de 50 MB". Aqui o numero e o
        limite estao na frase."""
        ok, erro = publicar_dados.cabe(
            b"x" * (publicar_dados.LIMITE_DO_STORAGE + 1))
        self.assertFalse(ok)
        self.assertIn("51200 KB", erro)
        self.assertIn("exportar.py", erro)


class APlacaNoNomeAntigo(unittest.TestCase):

    def test_o_dado_sobe_no_nome_novo(self):
        self.assertTrue(publicar_dados.ARQUIVO.endswith(".gz"))
        self.assertEqual(publicar_dados.ANTIGO, "dados.json")
        self.assertNotEqual(publicar_dados.ARQUIVO, publicar_dados.ANTIGO)

    def test_a_placa_nao_e_uma_lista(self):
        u"""E ISTO QUE FAZ O LEITOR ANTIGO FALHAR ALTO. Todo consumidor
        de dados.json espera um array; recebendo um objeto, ele quebra na
        linha seguinte em vez de desenhar o dia anterior como se fosse
        hoje."""
        corpo = json.loads(publicar_dados.corpo_da_placa().decode("utf-8"))
        self.assertNotIsInstance(corpo, list)
        self.assertEqual(corpo["este_arquivo_mudou_de_lugar"],
                         publicar_dados.ARQUIVO)

    def test_a_url_publica_e_a_do_gz(self):
        self.assertTrue(
            publicar_dados.url_publica("https://x.supabase.co")
            .endswith("/tela/dados.json.gz"))
        self.assertTrue(
            publicar_dados.url_publica("https://x.supabase.co", "dados.json")
            .endswith("/tela/dados.json"))

    def test_o_dado_sobe_como_gzip_e_a_placa_como_json(self):
        u"""O tipo vai no cabecalho do upload, e e o que o navegador le
        para decidir o que fazer com o corpo."""
        vistos = []

        def espiao(url, chave, caminho, metodo="GET", corpo=None,
                   tipo="application/json"):
            vistos.append((caminho, metodo, tipo))
            return 200, ""

        antigo = publicar_dados._pedir
        publicar_dados._pedir = espiao
        try:
            publicar_dados.subir("u", "k", publicar_dados.ARQUIVO,
                                 b"\x1f\x8b", "application/gzip")
            publicar_dados.subir("u", "k", publicar_dados.ANTIGO,
                                 publicar_dados.corpo_da_placa())
        finally:
            publicar_dados._pedir = antigo

        self.assertEqual(vistos[0][0], "/storage/v1/object/tela/dados.json.gz")
        self.assertEqual(vistos[0][2], "application/gzip")
        self.assertEqual(vistos[1][0], "/storage/v1/object/tela/dados.json")
        self.assertEqual(vistos[1][2], "application/json")


class AMontagemEnaoAsPecas(unittest.TestCase):
    u"""main() de ponta a ponta, com o servidor de mentira.

    POR QUE NAO BASTA TESTAR compactar() E corpo_da_placa(). As duas
    podem estar perfeitas e main() subir o JSON cru, ou nunca chamar a
    placa - e e main() que roda as 6h. Esta classe exerce a mesma funcao
    que o yml chama, com _pedir e urlopen trocados.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dados = os.path.join(self.tmp, "dados.json")
        self.serie = _serie()
        with io.open(self.dados, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.serie, ensure_ascii=False))
        self.subidos = []

        def espiao(url, chave, caminho, metodo="GET", corpo=None,
                   tipo="application/json"):
            if caminho.startswith("/storage/v1/bucket"):
                return 200, ""
            self.subidos.append((caminho.rsplit("/", 1)[-1], corpo, tipo))
            return 200, ""

        class Resposta(object):
            # o que o CDN devolve: o proprio arquivo que acabou de subir
            def __init__(self, corpo):
                self.corpo = corpo

            def read(self):
                return self.corpo

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def abrir(req, timeout=None):
            return Resposta(self.subidos[0][1])

        self._pedir, self._urlopen = (publicar_dados._pedir,
                                      publicar_dados.urllib.request.urlopen)
        publicar_dados._pedir = espiao
        publicar_dados.urllib.request.urlopen = abrir
        self._argv, sys.argv = sys.argv, ["publicar_dados.py",
                                          "--dados", self.dados]
        self._env = dict(os.environ)
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_SECRET_KEY"] = "chave"

    def tearDown(self):
        publicar_dados._pedir = self._pedir
        publicar_dados.urllib.request.urlopen = self._urlopen
        sys.argv = self._argv
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rodar(self):
        saida = io.StringIO()
        antigo, sys.stdout = sys.stdout, saida
        try:
            codigo = publicar_dados.main()
        finally:
            sys.stdout = antigo
        return codigo, saida.getvalue()

    def test_sobe_comprimido_e_depois_a_placa(self):
        codigo, _ = self._rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual([n for n, _c, _t in self.subidos],
                         ["dados.json.gz", "dados.json"])
        gz, placa = self.subidos[0][1], self.subidos[1][1]
        self.assertEqual(gz[:2], b"\x1f\x8b")
        self.assertEqual(gzip.decompress(gz).decode("utf-8"),
                         json.dumps(self.serie, ensure_ascii=False))
        self.assertNotIsInstance(json.loads(placa.decode("utf-8")), list)

    def test_a_placa_nao_sobe_se_o_dado_nao_subiu(self):
        u"""Trocar o nome antigo antes de confirmar o novo deixaria a
        tela sem dado nenhum no dia em que o upload falhasse - que e
        justamente o dia em que ela mais precisa seguir no ar."""
        def recusa(url, chave, caminho, metodo="GET", corpo=None,
                   tipo="application/json"):
            if caminho.startswith("/storage/v1/bucket"):
                return 200, ""
            self.subidos.append((caminho.rsplit("/", 1)[-1], corpo, tipo))
            return 400, '{"statusCode":"413","error":"Payload too large"}'

        publicar_dados._pedir = recusa
        codigo, texto = self._rodar()
        self.assertEqual(codigo, 1)
        self.assertEqual([n for n, _c, _t in self.subidos], ["dados.json.gz"])
        self.assertIn("FALHOU ao subir", texto)


class ASerieNoNavegador(unittest.TestCase):
    u"""O bloco de fetch da pagina nao passa pelo DOM de mentira dos
    outros testes: tela_em_node.mjs corta o script em "if (FONTE) {".
    Entao e aqui que o contrato dele fica preso."""

    def setUp(self):
        self.molde = _texto(GERADOR)

    def test_a_pagina_descomprime(self):
        self.assertIn('new DecompressionStream("gzip")', self.molde)
        self.assertIn("pipeThrough", self.molde)

    def test_o_navegador_sem_gzip_nao_fica_com_tela_vazia(self):
        u"""Sem esta guarda, quem nao tem DecompressionStream recebe
        TypeError dentro do then e cai no catch sem frase propria - ou,
        pior numa reescrita, desenha a tela sem serie."""
        self.assertIn("self.DecompressionStream", self.molde)
        self.assertIn("navegador sem gzip", self.molde)

    def test_o_json_sem_gz_continua_funcionando(self):
        u"""A copia local, gerada sem --remoto, nao passa por aqui; mas a
        tela aberta contra um arquivo .json qualquer tem de seguir
        lendo."""
        self.assertIn("if (!/\\.gz$/.test(FONTE)) return r.json();", self.molde)


class ORobotApontaParaOGz(unittest.TestCase):

    def test_os_dois_ymls_buscam_o_gz(self):
        for caminho in (ROTINA, AVULSO):
            t = _texto(caminho)
            self.assertIn("public/tela/dados.json.gz", t,
                          "%s busca o nome antigo" % os.path.basename(caminho))
            self.assertNotIn('tela/dados.json"', t,
                             "%s aponta para a placa"
                             % os.path.basename(caminho))

    def test_o_painel_parado_avisa(self):
        u"""Em 11/11/2026 o unico sinal de que a tela nao atualizou foi o
        quadrado vermelho do Actions - e tudo que chegava ao usuario
        estava certo, o que torna o silencio pior aqui do que nos outros
        passos."""
        t = _texto(ROTINA)
        self.assertIn("tela_falhou:", t)
        self.assertIn("needs.tela.result == 'failure'", t)
        self.assertIn("O PAINEL NAO FOI ATUALIZADO HOJE", t)


if __name__ == "__main__":
    unittest.main()
