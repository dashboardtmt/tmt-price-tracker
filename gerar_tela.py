"""Gera a tela do Price Tracker: HTML autocontido, com os dados embutidos.

Autocontido de proposito: assim voce abre com dois cliques, sem servidor.
Quando a tela for para o ar, os dados passam a vir do Storage e este
gerador some - mas ate la, abrir o arquivo tem que ser trivial.

Uso:
  python gerar_tela.py --dados caminho/para/dados.json --saida tela.html
"""

import argparse
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

CORES = {
    "Vivo": "#8258A0",
    "TIM": "#5282D8",
    "Claro": "#FF5000",
    "Brisanet": "#73C6A1",
    "Unifique": "#398478",
    "NuCel": "#809BC4",
}

MOLDE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Price Tracker TMT</title>
<style>
  :root{
    --laranja:#FF5000; --preto:#000512; --cinza:#6E6E6E; --cinza-claro:#CFCFCF;
    --fundo:#F7F7F7; --borda:#DCDCDC; --azul:#1D4080;
  }
  *{box-sizing:border-box}
  body{margin:0;background:#fff;color:var(--preto);
       font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5}
  header{border-bottom:3px solid var(--laranja);padding:20px 26px 14px;
         display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px}
  header h1{margin:0;font-size:22px;letter-spacing:-.3px}
  header .sub{color:var(--cinza);font-size:12px;margin-top:4px}
  .idioma button{border:1px solid var(--borda);background:#fff;padding:5px 12px;
     cursor:pointer;font-size:12px;font-family:inherit}
  .idioma button.on{background:var(--preto);color:#fff;border-color:var(--preto)}
  .filtros{display:flex;gap:18px;flex-wrap:wrap;padding:14px 26px;
           background:var(--fundo);border-bottom:1px solid var(--borda)}
  .filtro label{display:block;font-size:10.5px;text-transform:uppercase;
     letter-spacing:.6px;color:var(--cinza);margin-bottom:3px;font-weight:bold}
  .filtro select{font-family:inherit;font-size:13px;padding:5px 8px;
     border:1px solid var(--borda);background:#fff;min-width:150px}
  .ops{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .op{display:flex;align-items:center;gap:5px;font-size:12.5px;cursor:pointer;
      padding:3px 8px;border:1px solid var(--borda);background:#fff}
  .op.off{opacity:.35}
  .op .bolha{width:10px;height:10px;border-radius:50%}
  main{padding:20px 26px 60px;max-width:1280px}
  .paineis{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:22px}
  .painel{border:1px solid var(--borda);padding:14px 16px}
  .painel h2{margin:0 0 2px;font-size:14.5px}
  .painel .exp{font-size:11.5px;color:var(--cinza);margin:0 0 10px}
  .painel.largo{grid-column:1/-1}
  svg{display:block;width:100%;height:auto;overflow:visible}
  .aviso{background:#EDF1F8;border-left:4px solid var(--azul);padding:9px 13px;
         font-size:12.5px;margin:10px 0}
  table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:6px}
  th{background:var(--cinza);color:#fff;text-align:left;padding:6px 8px;font-weight:bold}
  td{border-bottom:1px solid var(--borda);padding:5px 8px}
  tr:nth-child(even) td{background:var(--fundo)}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  .vazio{color:var(--cinza);font-style:italic;padding:22px 0;text-align:center;font-size:13px}
  .cobertura{font-size:11.5px;color:var(--cinza);margin-top:8px}
  footer{border-top:1px solid var(--borda);padding:14px 26px;font-size:11.5px;color:var(--cinza)}
  @media(max-width:900px){.paineis{grid-template-columns:1fr}}
</style>
</head>
<body>

<header>
  <div>
    <h1 data-t="titulo">Price Tracker TMT</h1>
    <div class="sub" id="sub"></div>
  </div>
  <div class="idioma">
    <button id="bt-pt" class="on" onclick="idioma('pt')">PT</button>
    <button id="bt-en" onclick="idioma('en')">EN</button>
  </div>
</header>

<div class="filtros">
  <div class="filtro">
    <label data-t="f_praca">Praça</label>
    <select id="f-praca" onchange="desenhar()"></select>
  </div>
  <div class="filtro">
    <label data-t="f_produto">Produto</label>
    <select id="f-produto" onchange="desenhar()"></select>
  </div>
  <div class="filtro">
    <label data-t="f_periodo">Período</label>
    <select id="f-periodo" onchange="desenhar()">
      <option value="30">30 dias</option>
      <option value="90">90 dias</option>
      <option value="0" selected data-t="p_tudo">Tudo</option>
    </select>
  </div>
  <div class="filtro" style="flex:1">
    <label data-t="f_operadora">Operadoras</label>
    <div class="ops" id="f-ops"></div>
  </div>
</div>

<main>
  <div class="paineis">
    <div class="painel largo">
      <h2 data-t="g1_t">Evolução do preço no tempo</h2>
      <p class="exp" data-t="g1_x">Linha cheia: preço de tabela. Linha clara: preço praticado na vitrine.</p>
      <div id="g-tempo"></div>
    </div>
    <div class="painel">
      <h2 data-t="g2_t">Preço por velocidade e franquia</h2>
      <p class="exp" data-t="g2_x">Cada ponto é uma oferta. Mais à direita entrega mais; mais acima custa mais.</p>
      <div id="g-dispersao"></div>
    </div>
    <div class="painel">
      <h2 data-t="g3_t">Quanto da franquia é bônus temporário</h2>
      <p class="exp" data-t="g3_x">Barra escura: o que está no contrato. Barra clara: bônus que expira.</p>
      <div id="g-franquia"></div>
    </div>
    <div class="painel largo">
      <h2 data-t="g4_t">Desconto sobre a tabela</h2>
      <p class="exp" data-t="g4_x">Diferença entre o preço cheio e o praticado, por oferta.</p>
      <div id="g-spread"></div>
    </div>
    <div class="painel largo">
      <h2 data-t="tab_t">Ofertas capturadas</h2>
      <p class="exp" id="tab-x"></p>
      <div id="tabela"></div>
    </div>
  </div>
</main>

<footer>
  <span data-t="rodape">Documento de trabalho interno. Dados coletados das vitrines públicas das operadoras.</span>
</footer>

<script>
const DADOS = __DADOS__;
const CORES = __CORES__;
const GERADO = "__GERADO__";

const T = {
  pt:{titulo:"Price Tracker TMT", f_praca:"Praça", f_produto:"Produto", f_periodo:"Período",
      f_operadora:"Operadoras", p_tudo:"Tudo",
      g1_t:"Evolução do preço no tempo",
      g1_x:"Linha cheia: preço de tabela. Linha clara: preço praticado na vitrine.",
      g2_t:"Preço por velocidade e franquia",
      g2_x:"Cada ponto é uma oferta. Mais à direita entrega mais; mais acima custa mais.",
      g3_t:"Quanto da franquia é bônus temporário",
      g3_x:"Barra escura: o que está no contrato. Barra clara: bônus que expira.",
      g4_t:"Desconto sobre a tabela",
      g4_x:"Diferença entre o preço cheio e o praticado, por oferta.",
      tab_t:"Ofertas capturadas",
      rodape:"Documento de trabalho interno. Dados coletados das vitrines públicas das operadoras.",
      serie_jovem:"A série começou em {d}. Com {n} dia(s) de coleta ainda não há evolução para mostrar — o gráfico se forma sozinho conforme os dias passam.",
      sem_dado:"Sem oferta capturada com este filtro.",
      cobertura:"{a} de {b} operadoras nesta praça.",
      col:["Operadora","Oferta","Entrega","Contrato","Cheio","Praticado","Desconto"],
      semdesc:"—"},
  en:{titulo:"TMT Price Tracker", f_praca:"City", f_produto:"Product", f_periodo:"Period",
      f_operadora:"Carriers", p_tudo:"All",
      g1_t:"Price evolution over time",
      g1_x:"Solid line: list price. Light line: price offered on the website.",
      g2_t:"Price by speed and data allowance",
      g2_x:"Each dot is an offer. Further right delivers more; higher up costs more.",
      g3_t:"How much of the allowance is temporary bonus",
      g3_x:"Dark bar: what the contract states. Light bar: bonus that expires.",
      g4_t:"Discount off list price",
      g4_x:"Gap between list price and the price actually offered, per offer.",
      tab_t:"Captured offers",
      rodape:"Internal working document. Data collected from carriers' public websites.",
      serie_jovem:"The series started on {d}. With {n} day(s) of data there is no trend to show yet — the chart builds itself as days go by.",
      sem_dado:"No offer captured with this filter.",
      cobertura:"{a} of {b} carriers in this city.",
      col:["Carrier","Offer","Delivers","Contract","List","Offered","Discount"],
      semdesc:"—"}
};
let lang = "pt";
let desligadas = new Set();

const OPERADORAS = [...new Set(DADOS.map(o=>o.operadora))].sort();
const PRACAS = [...new Set(DADOS.map(o=>o.praca))].sort();
const PRODUTOS = [...new Set(DADOS.map(o=>o.produto))].sort();
const DIAS = [...new Set(DADOS.map(o=>(o.capturado_em||"").slice(0,10)))].filter(Boolean).sort();

function t(k){ return T[lang][k]; }
function num(v){ return v==null?null:Number(v); }
function reais(v){ return v==null?"—":"R$ "+Number(v).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2}); }

function idioma(l){
  lang=l;
  document.getElementById("bt-pt").className = l==="pt"?"on":"";
  document.getElementById("bt-en").className = l==="en"?"on":"";
  document.documentElement.lang = l==="pt"?"pt-BR":"en";
  document.querySelectorAll("[data-t]").forEach(e=>{ const k=e.dataset.t; if(T[l][k]) e.textContent=T[l][k]; });
  desenhar();
}

function montarFiltros(){
  const fp=document.getElementById("f-praca");
  fp.innerHTML = PRACAS.map(p=>`<option value="${p}">${p}</option>`).join("");
  if(PRACAS.includes("Sao Paulo/SP")) fp.value="Sao Paulo/SP";   // decisao 22
  document.getElementById("f-produto").innerHTML =
    PRODUTOS.map(p=>`<option value="${p}">${p}</option>`).join("");
  document.getElementById("f-ops").innerHTML = OPERADORAS.map(o=>
    `<span class="op" id="op-${o}" onclick="alternar('${o}')">
       <span class="bolha" style="background:${CORES[o]||"#999"}"></span>${o}</span>`).join("");
}
function alternar(o){
  desligadas.has(o) ? desligadas.delete(o) : desligadas.add(o);
  document.getElementById("op-"+o).className = "op" + (desligadas.has(o)?" off":"");
  desenhar();
}

function filtrar(){
  const praca=document.getElementById("f-praca").value;
  const produto=document.getElementById("f-produto").value;
  return DADOS.filter(o=>o.praca===praca && o.produto===produto && !desligadas.has(o.operadora));
}

// ------------------------------------------------------------------ SVG

function svg(w,h,conteudo){
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">${conteudo}</svg>`;
}
function eixo(x1,y1,x2,y2){ return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#CFCFCF" stroke-width="1"/>`; }
function rotulo(x,y,txt,anchor,cor,tam){
  return `<text x="${x}" y="${y}" text-anchor="${anchor||"middle"}" fill="${cor||"#6E6E6E"}"
    font-size="${tam||11}" font-family="Arial">${txt}</text>`;
}

function grafEvolucao(ofertas){
  const alvo=document.getElementById("g-tempo");
  if(DIAS.length<2){
    alvo.innerHTML = `<div class="aviso">${t("serie_jovem").replace("{d}",DIAS[0]?DIAS[0].split("-").reverse().join("/"):"—").replace("{n}",DIAS.length)}</div>`
      + tabelaHoje(ofertas);
    return;
  }
  // com serie: uma linha por operadora, curva suave e bolinha nos pontos
  const W=980,H=300,ml=54,mr=16,mt=14,mb=34;
  const precos=ofertas.map(o=>num(o.preco_promocional)).filter(v=>v!=null);
  if(!precos.length){ alvo.innerHTML=`<div class="vazio">${t("sem_dado")}</div>`; return; }
  const max=Math.max(...precos)*1.1, min=0;
  const x=i=>ml+(W-ml-mr)*(DIAS.length<2?0.5:i/(DIAS.length-1));
  const y=v=>H-mb-(H-mt-mb)*((v-min)/(max-min));
  let s=eixo(ml,H-mb,W-mr,H-mb)+eixo(ml,mt,ml,H-mb);
  for(let g=0;g<=4;g++){ const v=min+(max-min)*g/4;
    s+=eixo(ml,y(v),W-mr,y(v))+rotulo(ml-8,y(v)+4,reais(v).replace("R$ ",""),"end"); }
  DIAS.forEach((d,i)=> s+=rotulo(x(i),H-mb+18,d.slice(8,10)+"/"+d.slice(5,7)));
  OPERADORAS.filter(o=>!desligadas.has(o)).forEach(op=>{
    const pts=DIAS.map((d,i)=>{
      const doDia=ofertas.filter(o=>o.operadora===op && (o.capturado_em||"").slice(0,10)===d
                                    && num(o.preco_promocional)!=null);
      if(!doDia.length) return null;
      const v=Math.min(...doDia.map(o=>num(o.preco_promocional)));
      return {x:x(i), y:y(v), v:v};
    }).filter(Boolean);
    if(!pts.length) return;
    const d=pts.map((p,i)=> i?`L${p.x},${p.y}`:`M${p.x},${p.y}`).join(" ");
    s+=`<path d="${d}" fill="none" stroke="${CORES[op]||"#999"}" stroke-width="2.2"
         stroke-linejoin="round" stroke-linecap="round"/>`;
    pts.forEach(p=> s+=`<circle cx="${p.x}" cy="${p.y}" r="3.6" fill="${CORES[op]||"#999"}"/>`);
  });
  alvo.innerHTML=svg(W,H,s);
}

function grafDispersao(ofertas){
  const alvo=document.getElementById("g-dispersao");
  const pts=ofertas.map(o=>({
    op:o.operadora, nome:o.nome_oferta,
    x:num(o.degrau_mbps)||num(o.franquia_anunciada_gb),
    y:num(o.preco_promocional)
  })).filter(p=>p.x&&p.y);
  if(!pts.length){ alvo.innerHTML=`<div class="vazio">${t("sem_dado")}</div>`; return; }
  const W=470,H=290,ml=52,mr=14,mt=12,mb=32;
  const maxX=Math.max(...pts.map(p=>p.x))*1.08, maxY=Math.max(...pts.map(p=>p.y))*1.12;
  const X=v=>ml+(W-ml-mr)*(v/maxX), Y=v=>H-mb-(H-mt-mb)*(v/maxY);
  let s=eixo(ml,H-mb,W-mr,H-mb)+eixo(ml,mt,ml,H-mb);
  for(let g=0;g<=4;g++){ const v=maxY*g/4; s+=eixo(ml,Y(v),W-mr,Y(v))+rotulo(ml-7,Y(v)+4,Math.round(v),"end"); }
  for(let g=0;g<=4;g++){ const v=maxX*g/4; s+=rotulo(X(v),H-mb+17,Math.round(v)); }
  pts.forEach(p=> s+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5.5" fill="${CORES[p.op]||"#999"}"
      fill-opacity="0.78"><title>${p.op} — ${p.nome}\\n${p.x} · ${reais(p.y)}</title></circle>`);
  alvo.innerHTML=svg(W,H,s);
}

function grafFranquia(ofertas){
  const alvo=document.getElementById("g-franquia");
  const itens=ofertas.filter(o=>num(o.franquia_anunciada_gb)&&num(o.franquia_contratual_gb))
    .sort((a,b)=>num(b.franquia_anunciada_gb)-num(a.franquia_anunciada_gb)).slice(0,9);
  if(!itens.length){ alvo.innerHTML=`<div class="vazio">${t("sem_dado")}</div>`; return; }
  const W=470,alt=26,H=itens.length*alt+30,ml=132,mr=42;
  const max=Math.max(...itens.map(o=>num(o.franquia_anunciada_gb)));
  let s="";
  itens.forEach((o,i)=>{
    const y=i*alt+10, anun=num(o.franquia_anunciada_gb), contr=num(o.franquia_contratual_gb);
    const L=v=>(W-ml-mr)*(v/max);
    s+=rotulo(ml-7,y+13,(o.nome_oferta||"").slice(0,20),"end","#000512",11);
    s+=`<rect x="${ml}" y="${y+3}" width="${L(anun)}" height="15" fill="${CORES[o.operadora]||"#999"}" fill-opacity="0.28"/>`;
    s+=`<rect x="${ml}" y="${y+3}" width="${L(contr)}" height="15" fill="${CORES[o.operadora]||"#999"}"/>`;
    s+=rotulo(ml+L(anun)+6,y+14,contr+"/"+anun+" GB","start","#6E6E6E",10.5);
  });
  alvo.innerHTML=svg(W,H,s);
}

function grafSpread(ofertas){
  const alvo=document.getElementById("g-spread");
  const itens=ofertas.filter(o=>num(o.preco_cheio)&&num(o.preco_promocional)
      && num(o.preco_cheio)>num(o.preco_promocional))
    .sort((a,b)=>(num(b.preco_cheio)-num(b.preco_promocional))-(num(a.preco_cheio)-num(a.preco_promocional)))
    .slice(0,10);
  if(!itens.length){
    alvo.innerHTML=`<div class="vazio">${lang==="pt"
      ?"Nenhuma oferta com desconto sobre a tabela neste filtro — o preço praticado é o de tabela."
      :"No offer priced below list here — the offered price equals the list price."}</div>`;
    return;
  }
  const W=980,alt=25,H=itens.length*alt+26,ml=210,mr=90;
  const max=Math.max(...itens.map(o=>num(o.preco_cheio)));
  let s="";
  itens.forEach((o,i)=>{
    const y=i*alt+8, cheio=num(o.preco_cheio), prom=num(o.preco_promocional);
    const L=v=>(W-ml-mr)*(v/max);
    s+=rotulo(ml-8,y+13,(o.operadora+" · "+(o.nome_oferta||"")).slice(0,34),"end","#000512",11);
    s+=`<line x1="${ml+L(prom)}" y1="${y+9}" x2="${ml+L(cheio)}" y2="${y+9}"
         stroke="${CORES[o.operadora]||"#999"}" stroke-width="2" stroke-opacity="0.35"/>`;
    s+=`<circle cx="${ml+L(cheio)}" cy="${y+9}" r="4.5" fill="#fff" stroke="${CORES[o.operadora]||"#999"}" stroke-width="2"/>`;
    s+=`<circle cx="${ml+L(prom)}" cy="${y+9}" r="4.5" fill="${CORES[o.operadora]||"#999"}"/>`;
    s+=rotulo(ml+L(cheio)+10,y+13,"−"+Math.round((1-prom/cheio)*100)+"%","start","#6E6E6E",10.5);
  });
  alvo.innerHTML=svg(W,H,s);
}

function tabelaHoje(ofertas){
  if(!ofertas.length) return `<div class="vazio">${t("sem_dado")}</div>`;
  const c=t("col");
  const linhas=ofertas.slice().sort((a,b)=>(num(a.preco_promocional)||0)-(num(b.preco_promocional)||0))
    .map(o=>{
      const cheio=num(o.preco_cheio), prom=num(o.preco_promocional);
      const desc=(cheio&&prom&&cheio>prom)?("−"+Math.round((1-prom/cheio)*100)+"%"):t("semdesc");
      const entrega=o.degrau_mbps?(o.degrau_mbps+" Mbps"):(o.franquia_anunciada_gb?o.franquia_anunciada_gb+" GB":"—");
      const contr=o.franquia_contratual_gb?o.franquia_contratual_gb+" GB":"—";
      return `<tr><td style="border-left:3px solid ${CORES[o.operadora]||"#999"}">${o.operadora}</td>
        <td>${o.nome_oferta||"—"}</td><td>${entrega}</td><td>${contr}</td>
        <td class="num">${reais(cheio)}</td><td class="num">${reais(prom)}</td>
        <td class="num">${desc}</td></tr>`;
    }).join("");
  return `<table><tr>${c.map(x=>`<th>${x}</th>`).join("")}</tr>${linhas}</table>`;
}

function desenhar(){
  const ofertas=filtrar();
  grafEvolucao(ofertas);
  grafDispersao(ofertas);
  grafFranquia(ofertas);
  grafSpread(ofertas);
  document.getElementById("tabela").innerHTML=tabelaHoje(ofertas);

  const praca=document.getElementById("f-praca").value;
  const naPraca=new Set(DADOS.filter(o=>o.praca===praca).map(o=>o.operadora));
  document.getElementById("tab-x").textContent =
    t("cobertura").replace("{a}",naPraca.size).replace("{b}",OPERADORAS.length);
  document.getElementById("sub").textContent =
    (lang==="pt"?"Coletado em ":"Collected on ")+GERADO+" · "+DADOS.length+
    (lang==="pt"?" ofertas":" offers");
}

montarFiltros();
desenhar();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--saida", default="tela.html")
    a = ap.parse_args()

    dados = json.load(io.open(a.dados, encoding="utf-8"))
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")

    html = (MOLDE
            .replace("__DADOS__", json.dumps(dados, ensure_ascii=False))
            .replace("__CORES__", json.dumps(CORES, ensure_ascii=False))
            .replace("__GERADO__", agora))
    io.open(a.saida, "w", encoding="utf-8").write(html)
    print("tela gerada: %s (%d ofertas, %d KB)"
          % (a.saida, len(dados), len(html) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
