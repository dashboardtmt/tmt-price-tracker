// Roda o JavaScript da tela gerada num DOM de mentira, e devolve o texto
// que cada tabela produz.
//
// POR QUE EXISTE. A tela e o terceiro consumidor do mesmo dado - depois
// da mensagem e do PDF - e foi o unico que ficou seis rodadas de
// auditoria sem ser olhado. Quando finalmente foi, tinha dez rotulos
// afirmando coisas que o dado nao sustentava: "R$/Mbps" sobre linhas em
// GB, "o site nao nomeia qual" sobre ofertas com o app no proprio nome,
// e tres paineis mostrando um dia diferente do selecionado.
//
// Nenhum deles aparecia em teste de Python, porque o que erra mora no JS
// da pagina. Isto torna esse JS testavel: nao e navegador, nao mede
// layout, mas o TEXTO e o de verdade - e texto e o que afirma.
//
// Uso:
//   node tela_em_node.mjs <tela.html> <dados.json> '<consultas.json>'
//
// A consulta e uma lista de {praca, produto, dia, quero}. "quero" diz o
// que extrair: "t-player", "mat_t", "bt-gb" ou "t-faixas".
import fs from "node:fs";
import vm from "node:vm";

const [, , caminhoHtml, caminhoDados, consultasJson] = process.argv;
const html = fs.readFileSync(caminhoHtml, "utf8");
const DADOS = JSON.parse(fs.readFileSync(caminhoDados, "utf8"));
const consultas = JSON.parse(consultasJson || "[]");

// o unico script inline e o da tela; o bloco final busca a FONTE por
// fetch e nao interessa aqui
const blocos = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)];
let corpo = blocos.map(x => x[1]).filter(s => s.includes("function derivar(")).join("\n");
if (!corpo) throw new Error("nao achei o script da tela");
corpo = corpo.split("if (FONTE) {")[0];

// ------------------------------------------------------- DOM de mentira
class El {
  constructor(tag, id) {
    this.tagName = (tag || "div").toUpperCase();
    this.id = id || "";
    this.innerHTML = ""; this.textContent = ""; this.value = "";
    this.className = ""; this.hidden = false; this.disabled = false;
    this.style = new Proxy({ setProperty() {} },
      { get: (t, k) => t[k] ?? "", set: (t, k, v) => { t[k] = v; return true; } });
    this.dataset = {}; this.options = []; this.offsetHeight = 40;
    this.offsetWidth = 900; this.offsetParent = this;
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  closest() { return new El("div"); }
  addEventListener() {} removeEventListener() {}
  getBoundingClientRect() {
    return { top: 0, left: 0, width: 900, height: 40, bottom: 40, right: 900 };
  }
  appendChild(x) { return x; } remove() {}
  querySelector() { return null; } querySelectorAll() { return []; }
  get tHead() { return null; }
  insertAdjacentHTML() {}
}
const reg = new Map();
function g(id) { if (!reg.has(id)) reg.set(id, new El("div", id)); return reg.get(id); }
const porT = new Map();
const document = {
  documentElement: new El("html"),
  body: new El("body"),
  getElementById: g,
  querySelector(sel) {
    const dt = /^\[data-t="([^"]+)"\]$/.exec(sel);
    if (dt) { if (!porT.has(dt[1])) porT.set(dt[1], new El("h2")); return porT.get(dt[1]); }
    if (sel === "header" || sel === "nav.abas" || sel === ".controles") return new El("div");
    return null;
  },
  querySelectorAll() { return []; },
  createElement(t) { return new El(t); },
  addEventListener() {},
};
class Chart {
  constructor(c, cfg) {
    this.config = cfg; this.data = cfg.data; this.options = cfg.options;
    this.scales = { x: {}, y: {} }; this.$rotulos = null;
  }
  destroy() {} update() {} getDatasetMeta() { return { data: [] }; }
}
Chart.register = () => {};
Chart.defaults = {
  scales: {
    linear: { ticks: { callback: v => String(v) } },
    category: { ticks: { callback: v => String(v) } },
    logarithmic: { ticks: { callback: v => String(v) } },
  }, font: {}, color: "#000", plugins: {},
};
const sandbox = {
  document, Chart, ChartDataLabels: { id: "datalabels" }, console,
  addEventListener() {}, requestAnimationFrame() {},
  setTimeout() {}, clearTimeout() {}, window: null,
  navigator: { language: "pt-BR" },
  Math, JSON, Number, String, Object, Array, Set, Map, Intl, parseInt, parseFloat,
  isNaN, isFinite, RegExp, Date, Error, Boolean, Symbol, Proxy, Reflect,
  Infinity, NaN, undefined,
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
const ctx = vm.createContext(sandbox);
vm.runInContext(corpo, ctx, { filename: "tela.js" });
vm.runInContext("DADOS = __D__; derivar();", Object.assign(ctx, { __D__: DADOS }));

// ----------------------------------------------------------- as consultas
const saida = [];
for (const c of consultas) {
  g("f-praca").value = c.praca;
  g("f-produto").value = c.produto;
  g("f-data").value = c.dia;
  g("f-player").value = c.player || "";
  vm.runInContext(
    `lang="pt"; escopoAtual="todos"; desligadas = new Set([]);`, ctx);
  // A ABA DECIDE O QUE desenhar() DESENHA, e no DOM de mentira tudo
  // nasce visivel - entao ele saia pelo ramo das pracas e nunca montava
  // a tabela por player. "aba" diz qual das tres pagina fica de pe.
  const pagina = c.aba || "ofertas";
  for (const p of ["panorama", "ofertas", "pracas"]) {
    g("pg-" + p).hidden = (p !== pagina);
  }
  if (c.metrica) vm.runInContext(`metrica(${JSON.stringify(c.metrica)});`, ctx);
  vm.runInContext("desenhar();", ctx);
  const r = { consulta: c };
  r["t-player"] = (reg.get("t-player") || {}).innerHTML || "";
  r["t-faixas"] = (reg.get("t-faixas") || {}).innerHTML || "";
  r["bt-gb"] = (reg.get("bt-gb") || {}).textContent || "";
  r["mat_t"] = (porT.get("mat_t") || {}).textContent || "";
  // OS GRAFICOS TAMBEM AFIRMAM. Tres paineis do Panorama liam o ultimo
  // dia da serie e ignoravam o seletor: com Data=01/10 um mostrava 4
  // ofertas e o de baixo mostrava 7, incluindo uma operadora que nao
  // foi coletada naquele dia. Sem ler os datasets, nenhum teste ve isso.
  r.graficos = vm.runInContext(`(function(){
    const o = {};
    for (const k of Object.keys(graficos || {})) {
      const g = graficos[k];
      if (!g || !g.data) continue;
      o[k] = {
        series: (g.data.datasets || []).map(d => d.label || ""),
        rotulos: g.data.labels || [],
        eixoX: ((((g.options||{}).scales||{}).x||{}).title||{}).text || "",
      };
    }
    return o;
  })()`, ctx);
  saida.push(r);
}
process.stdout.write(JSON.stringify(saida));
