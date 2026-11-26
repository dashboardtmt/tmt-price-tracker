// Roda SO o bloco que baixa a serie, tirado do gerador, contra um fetch de
// mentira. Uso: node carga_em_node.cjs <bloco.js> '<cenario json>'
//
// O cenario diz o protocolo da pagina e o que cada rota responde:
//   {"protocolo": "https:", "site": "bloqueado" | 200 | 404, "storage": ...}
// "bloqueado" e o que a rede corporativa faz: o fetch rejeita com
// TypeError("Failed to fetch") sem resposta nenhuma.
const fs = require("fs");
const zlib = require("zlib");

const bloco = fs.readFileSync(process.argv[2], "utf8");
const CENARIO = JSON.parse(process.argv[3]);
const corpo = zlib.gzipSync(Buffer.from(JSON.stringify([{operadora: "Claro"}, {operadora: "Vivo"}])));
const pedidos = [];

globalThis.self = globalThis;
globalThis.fetch = async (url) => {
  pedidos.push(url);
  const r = CENARIO[url.startsWith("/") ? "site" : "storage"];
  if (r === "bloqueado") throw new TypeError("Failed to fetch");
  if (r === 200) return new Response(corpo, {status: 200});
  return new Response("", {status: r});
};

const rodar = new Function("location", "estado", `
  const FONTE = "https://exemplo.supabase.co/storage/v1/object/public/tela/dados.json.gz";
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
