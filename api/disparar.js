// Dispara a rotina diaria do robo, na hora certa.
//
// POR QUE EXISTE. O evento "schedule" do GitHub nao cumpre horario:
// medido em sete dias, chegou entre 3,5 e 9,6 horas atrasado, e numa
// segunda-feira a mensagem do dia saiu as 16h45. O atraso esta no
// gatilho - o run comeca no mesmo minuto em que e criado.
//
// O "workflow_dispatch" nao tem esse problema: sai no instante da
// chamada. Entao quem marca a hora passa a ser o Vercel, e o GitHub so
// executa.
//
// OS AGENDAMENTOS DO GITHUB CONTINUAM LA, de proposito, como rede de
// seguranca: se esta funcao falhar, se o token expirar ou se o projeto
// sair do ar, o robo ainda entrega - mais tarde, mas entrega. A guarda
// de idempotencia no proprio workflow impede que os dois caminhos
// coletem duas vezes.
//
// QUEM PODE CHAMAR. So o proprio agendador do Vercel, que assina a
// chamada com CRON_SECRET. Sem isso, qualquer um com a URL dispararia a
// coleta a vontade.

const REPO = "dashboardtmt/tmt-price-tracker";
const WORKFLOW = "diario.yml";

export default async function handler(req, res) {
  // O agendador do Vercel manda o segredo no Authorization.
  //
  // FECHA QUANDO NAO SABE. O codigo aqui dizia "em producao ele e
  // obrigatorio" e fazia o contrario: a guarda era "se o segredo
  // existir, confira" - entao CRON_SECRET ausente PULAVA a conferencia
  // e deixava a rota aberta para qualquer um disparar a coleta. O
  // comentario descrevia a intencao; o `esperado &&` descrevia o
  // oposto.
  //
  // Virou defeito de verdade em 27/10/2026, quando o repositorio passou
  // a ser publico: a URL da rota deixou de depender de alguem adivinhar
  // o caminho.
  const esperado = process.env.CRON_SECRET;
  if (!esperado) {
    return res.status(503).json({
      erro: "CRON_SECRET ausente",
      comofazer: "gravar CRON_SECRET nas variaveis de ambiente do Vercel; " +
                 "sem ele a rota nao dispara nada, de proposito",
    });
  }
  if (req.headers.authorization !== `Bearer ${esperado}`) {
    return res.status(401).json({ erro: "nao autorizado" });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    // Sem token a funcao nao faz nada e diz o porque. Nao e erro de
    // execucao: e o estado de quem ainda nao configurou.
    return res.status(503).json({
      erro: "GITHUB_TOKEN ausente",
      comofazer: "criar um token com permissao de Actions no repositorio " +
                 "e grava-lo como variavel de ambiente no Vercel",
    });
  }

  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    });

    // 204 e o sucesso do dispatch: ele nao devolve corpo nenhum
    if (r.status === 204) {
      return res.status(200).json({ ok: true, quando: new Date().toISOString() });
    }
    const detalhe = await r.text();
    return res.status(502).json({
      erro: `GitHub respondeu ${r.status}`,
      detalhe: detalhe.slice(0, 300),
    });
  } catch (e) {
    return res.status(502).json({ erro: String(e).slice(0, 300) });
  }
}
