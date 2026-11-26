# -*- coding: utf-8 -*-
u"""A tela busca a serie pelo proprio site, como JSON, antes do Storage.

26/11/2026, duas fotos de quem le, num PC de rede corporativa: "Nao consegui
carregar a serie (Failed to fetch). A pagina esta no ar, mas sem dado". Daqui
o mesmo arquivo respondia 200, com CORS aberto.

  - PRIMEIRA FOTO: so havia o Storage (supabase.co). A tela passou a pedir
    /dados.json.gz ao proprio vercel.app, que o vercel.json repassa do
    Storage.
  - SEGUNDA FOTO, horas depois: a mesma falha pelas duas rotas. O vercel.app
    nao estava bloqueado - a pagina abria -; o que as duas rotas tinham em
    comum era o TIPO: um .gz de 2,6 MB servido como application/gzip, que
    filtro corporativo barra como download de arquivo compactado.
    /serie.json entrega os mesmos bytes com Content-Encoding: gzip e
    Content-Type: application/json - a compressao HTTP de qualquer site, que
    o navegador desfaz sozinho.

A ordem fica: /serie.json, /dados.json.gz, Storage. O recado diz a falha de
cada rota, para o proximo diagnostico nao ser adivinhado.

O bloco roda de verdade no node, contra um fetch de mentira: e ali que mora
o comportamento, e conferir texto do bloco nao prova a ordem das rotas.
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
NODE = shutil.which("node")
FONTE = "https://exemplo.supabase.co/storage/v1/object/public/tela/dados.json.gz"


def _texto(caminho):
    with io.open(caminho, encoding="utf-8") as f:
        return f.read()


def _bloco():
    molde = _texto(os.path.join(RAIZ, "gerar_tela.py"))
    ini = molde.index("if (FONTE) {")
    fim = molde.index("} else if (DADOS_GZ) {", ini)
    return molde[ini:fim] + "}\n"


@unittest.skipUnless(NODE, "sem node")
class ASerieChegaPorOutraRota(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp()
        cls.arquivo = os.path.join(cls.pasta, "bloco.js")
        with io.open(cls.arquivo, "w", encoding="utf-8") as f:
            f.write(_bloco())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def rodar(self, protocolo="https:", json_=200, site=200, storage=200):
        r = subprocess.run(
            [NODE, os.path.join(AQUI, "carga_em_node.cjs"), self.arquivo,
             json.dumps({"protocolo": protocolo, "json": json_, "site": site, "storage": storage})],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o bloco de carga quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)

    def test_o_json_do_site_e_a_primeira_rota(self):
        d = self.rodar()
        self.assertEqual(d["pedidos"], ["/serie.json"])
        self.assertEqual((d["iniciado"], d["n"]), (1, 2))
        self.assertEqual(d["recados"][-1], "")

    def test_o_filtro_que_barra_o_gz_ainda_deixa_o_json(self):
        u"""A segunda foto: as duas rotas de .gz bloqueadas."""
        d = self.rodar(site="bloqueado", storage="bloqueado")
        self.assertEqual(d["pedidos"], ["/serie.json"])
        self.assertEqual(d["iniciado"], 1)

    def test_o_json_que_falha_cai_no_gz_do_site(self):
        d = self.rodar(json_=404, site=200)
        self.assertEqual(d["pedidos"], ["/serie.json", "/dados.json.gz"])
        self.assertEqual((d["iniciado"], d["n"]), (1, 2))

    def test_o_site_inteiro_que_falha_cai_no_storage(self):
        d = self.rodar(json_="bloqueado", site="bloqueado", storage=200)
        self.assertEqual(d["pedidos"], ["/serie.json", "/dados.json.gz", FONTE])
        self.assertEqual((d["iniciado"], d["n"]), (1, 2))

    def test_as_tres_que_falham_dizem_cada_uma(self):
        d = self.rodar(json_="bloqueado", site=502, storage="bloqueado")
        self.assertEqual(d["iniciado"], 0)
        self.assertIn("/serie.json: Failed to fetch / /dados.json.gz: HTTP 502 / "
                      "Storage: Failed to fetch", d["recados"][-1])
        self.assertIn(u"nada aqui foi estimado", d["recados"][-1])
        # a versao da pagina, para a foto do recado dizer qual copia roda
        self.assertIn(u"Página de 26/11/2026 17:36.", d["recados"][-1])

    def test_o_arquivo_aberto_do_disco_vai_direto_ao_storage(self):
        d = self.rodar(protocolo="file:")
        self.assertEqual(d["pedidos"], [FONTE])
        self.assertEqual(d["iniciado"], 1)


class OVercelRepassaOStorage(unittest.TestCase):

    def setUp(self):
        self.cfg = json.loads(_texto(os.path.join(RAIZ, "vercel.json")))
        self.destino = dict((r["source"], r["destination"]) for r in self.cfg.get("rewrites") or [])
        self.publicada = re.search(r'const FONTE = "([^"]+)"',
                                   _texto(os.path.join(RAIZ, "site", "index.html"))).group(1)

    def test_as_duas_rotas_do_site_apontam_para_o_arquivo_da_tela(self):
        u"""O destino do vercel.json e a FONTE da tela publicada sao o mesmo
        arquivo: se um mudar sem o outro, o site serve outra coisa."""
        self.assertEqual(self.destino.get("/serie.json"), self.publicada)
        self.assertEqual(self.destino.get("/dados.json.gz"), self.publicada)

    def test_o_json_sai_com_a_compressao_do_http(self):
        cab = {}
        for regra in self.cfg.get("headers") or []:
            if regra["source"] == "/serie.json":
                cab.update((h["key"].lower(), h["value"]) for h in regra["headers"])
        self.assertEqual(cab.get("content-encoding"), "gzip")
        self.assertTrue(cab.get("content-type", "").startswith("application/json"))


if __name__ == "__main__":
    unittest.main()
