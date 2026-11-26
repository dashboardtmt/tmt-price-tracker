# -*- coding: utf-8 -*-
u"""A tela busca a serie pelo endereco do proprio site antes do Storage.

26/11/2026, foto de quem le, num PC de outra rede: "Nao consegui carregar a
serie (Failed to fetch). A pagina esta no ar, mas sem dado". No mesmo minuto
o mesmo arquivo respondia 200 daqui, com CORS aberto. Failed to fetch sem
resposta e a rede bloqueando o endereco do Storage (supabase.co), comum em
rede corporativa - e a tela publicada mora justamente no PC de trabalho.

O vercel.json repassa /dados.json.gz do Storage: o navegador so fala com o
vercel.app, e o dado continua o da coleta de hoje (nao um retrato do deploy).
O Storage direto fica de segunda rota.

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

    def rodar(self, protocolo="https:", site=200, storage=200):
        r = subprocess.run(
            [NODE, os.path.join(AQUI, "carga_em_node.cjs"), self.arquivo,
             json.dumps({"protocolo": protocolo, "site": site, "storage": storage})],
            capture_output=True, text=True, encoding="utf-8", cwd=AQUI)
        if r.returncode:
            self.fail("o bloco de carga quebrou: %s" % r.stderr[-600:])
        return json.loads(r.stdout)

    def test_a_rede_que_bloqueia_o_storage_ainda_ve_o_dado(self):
        u"""A foto de 26/11: o Storage bloqueado, o site no ar."""
        d = self.rodar(site=200, storage="bloqueado")
        self.assertEqual(d["pedidos"], ["/dados.json.gz"])
        self.assertEqual((d["iniciado"], d["n"]), (1, 2))
        self.assertEqual(d["recados"][-1], "")

    def test_o_site_que_falha_cai_no_storage(self):
        d = self.rodar(site="bloqueado", storage=200)
        self.assertEqual(d["pedidos"], ["/dados.json.gz", FONTE])
        self.assertEqual((d["iniciado"], d["n"]), (1, 2))

    def test_as_duas_que_falham_dizem_as_duas(self):
        d = self.rodar(site=502, storage="bloqueado")
        self.assertEqual(d["iniciado"], 0)
        self.assertIn("HTTP 502 / Failed to fetch", d["recados"][-1])
        self.assertIn(u"nada aqui foi estimado", d["recados"][-1])

    def test_o_arquivo_aberto_do_disco_vai_direto_ao_storage(self):
        d = self.rodar(protocolo="file:", site=200, storage=200)
        self.assertEqual(d["pedidos"], [FONTE])
        self.assertEqual(d["iniciado"], 1)


class OVercelRepassaOStorage(unittest.TestCase):

    def test_a_rota_do_site_aponta_para_o_arquivo_que_a_tela_busca(self):
        u"""O destino do vercel.json e a FONTE da tela publicada sao o mesmo
        arquivo: se um mudar sem o outro, o site serve outra coisa."""
        regras = json.loads(_texto(os.path.join(RAIZ, "vercel.json"))).get("rewrites") or []
        destino = dict((r["source"], r["destination"]) for r in regras).get("/dados.json.gz")
        self.assertTrue(destino, "o vercel.json nao repassa /dados.json.gz")
        publicada = re.search(r'const FONTE = "([^"]+)"', _texto(os.path.join(RAIZ, "site", "index.html")))
        self.assertTrue(publicada)
        self.assertEqual(destino, publicada.group(1))


if __name__ == "__main__":
    unittest.main()
