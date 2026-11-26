// Roda SO o bloco que baixa a serie, tirado do gerador, contra um fetch de
// mentira. Uso: node carga_em_node.cjs <bloco.js> '<cenario json>'
//
// O cenario diz o protocolo da pagina e o que cada rota responde:
//   {"protocolo": "https:", "json": ..., "site": ..., "storage": ...}
// com cada valor "bloqueado" | 200 | <outro status>. "bloqueado" e o que a
// rede corporativa faz: o fetch rejeita com TypeError("Failed to fetch") sem
// resposta nenhuma.
//
// A rota /serie.json chega descomprimida, como o navegador a entrega (a
// compressao e a do HTTP, Content-Encoding: gzip); as do .gz chegam com os
// bytes do arquivo compactado, que a pagina descomprime.
const fs = require("fs");
const zlib = require("zlib");

const bloco = fs.readFileSync(process.argv[2], "utf8");
const CENARIO = JSON.parse(process.argv[3]);
const linhas = JSON.stringify([{operadora: "Claro"}, {operadora: "Vivo"}]);
const compactado = zlib.gzipSync(Buffer.from(linhas));
const pedidos = [];

globalThis.self = globalThis;
globalThis.fetch = async (url) => {
  pedidos.push(url);
  const rota = url === "/serie.json" ? "json" : (url.startsWith("/") ? "site" : "storage");
  const r = CENARIO[rota];
  if (r === "bloqueado") throw new TypeError("Failed to fetch");
  if (r === 200) return new Response(rota === "json" ? linhas : compactado, {status: 200});
  return new Response("", {status: r});
};

const rodar = new Function("location", "estado", `
  const FONTE = "https://exemplo.supabase.co/storage/v1/object/public/tela/dados.json.gz";
  const GERADO = "26/11/2026 17:36";
  let lang = "pt", DADOS = null;
  function recado(t){ estado.recados.push(t); }
  function iniciar(){ estado.iniciado++; estado.n = DADOS.length; }
  ${bloco}
`);
const estado = {recados: [], iniciado: 0, n: null};
rodar({protocol: CENARIO.protocolo}, estado);
setTimeout(() => {
  console.log(JSON.stringify({pedidos, recados: estado.recados, iniciado: estado.iniciado, n: estado.n}));
}, 300);
