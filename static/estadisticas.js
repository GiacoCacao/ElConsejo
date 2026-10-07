// El Consejo — estadísticas: cifras clave, gasto en el tiempo y rankings (una serie por gráfico).
const COLOR_DATO = '#b98a2e';   // dorado de datos: pasa luminosidad, croma y contraste sobre el fondo oscuro
let estDias = 90, estDatos = null;
const usd = x => x == null ? '—' : fUSD(x);
const usdEje = x => x === 0 ? '0' : x < 0.01 ? x.toFixed(4) : x < 1 ? x.toFixed(2) : nf(x, 0);

async function abrirEstadisticas() {
  $('#estPanel').innerHTML = '<option value="">Todos los consejos</option>' + paneles.map(p => `<option value="${p.id}">${esc(p.nombre)}</option>`).join('');
  $('#dlgEstadisticas').showModal();
  cargarEstadisticas();
}
async function cargarEstadisticas() {
  $('#estPeriodo').querySelectorAll('[data-d]').forEach(b => b.classList.toggle('act', +b.dataset.d === estDias));
  $('#estCuerpo').innerHTML = '<div class="v-espera"><span class="puntos"><i></i><i></i><i></i></span>Calculando…</div>';
  try { estDatos = await api(`/api/estadisticas?dias=${estDias}${$('#estPanel').value ? `&panel=${$('#estPanel').value}` : ''}`); }
  catch (e) { $('#estCuerpo').innerHTML = `<p class="nota aviso">${esc(e.message)}</p>`; return; }
  pintarEstadisticas(estDatos);
}
$('#estPeriodo').querySelectorAll('[data-d]').forEach(b => b.onclick = () => { estDias = +b.dataset.d; cargarEstadisticas(); });
$('#estPanel').onchange = cargarEstadisticas;
$('#abrirEstadisticas').onclick = abrirEstadisticas;

function tile(rot, valor, det) {
  return `<div class="tile est"><div class="rot">${rot}</div><div class="cifra-sans">${valor}</div><div class="det">${det}</div></div>`;
}
function tarjeta(id, titulo, sub, grafico, tabla) {
  return `<section class="carta" id="${id}"><header><div><h4>${titulo}</h4>${sub ? `<p>${sub}</p>` : ''}</div>
    <button type="button" class="enlace peq" data-tabla="${id}">Tabla</button></header>
    <div class="vista-grafico">${grafico}</div><div class="vista-tabla" hidden>${tabla}</div></section>`;
}
function tablaHTML(cols, filas) {
  return filas.length ? `<table class="tabla"><thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${filas.map(f => `<tr>${f.map(x => `<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`
    : '<p class="ayuda">Sin datos en este periodo.</p>';
}
// barras horizontales de una serie: etiqueta · barra (≤ 24 px, extremo redondeado) · valor en la punta
function barras(datos, fmt, extra = () => '') {
  if (!datos.length) return '<p class="ayuda vacio-g">Sin datos en este periodo.</p>';
  const max = Math.max(...datos.map(d => d.valor)) || 1;
  return `<div class="barras">${datos.map(d => `<div class="fila-b" data-tip="${esc(d.nombre)}: ${esc(fmt(d.valor))}${esc(extra(d) ? ' · ' + extra(d) : '')}">
      <span class="et" title="${esc(d.nombre)}">${esc(d.nombre)}${extra(d) ? `<small>${esc(extra(d))}</small>` : ''}</span>
      <span class="pista"><i style="width:${Math.max(1.5, 100 * d.valor / max)}%;background:${COLOR_DATO}"></i></span>
      <b>${esc(fmt(d.valor))}</b></div>`).join('')}</div>`;
}
// columnas en el tiempo: eje Y con valores redondos, rejilla fina, etiqueta solo en el máximo
function columnas(serie) {
  const W = 760, H = 220, I = 44, D = 10, A = 14, B = 26;
  const max = Math.max(...serie.map(s => s.valor), 0);
  if (!max) return '<p class="ayuda vacio-g">Sin gasto registrado en este periodo.</p>';
  const paso = (() => { const bruto = max / 3, e = Math.pow(10, Math.floor(Math.log10(bruto))); return [1, 2, 2.5, 5, 10].map(m => m * e).find(m => m >= bruto); })();
  const tope = paso * Math.ceil(max / paso), y = v => A + (H - A - B) * (1 - v / tope);
  const banda = (W - I - D) / serie.length, ancho = Math.min(24, banda * 0.62);
  const cadaN = Math.ceil(serie.length / 10);
  let svg = '';
  for (let v = 0; v <= tope + 1e-12; v += paso)
    svg += `<line x1="${I}" x2="${W - D}" y1="${y(v)}" y2="${y(v)}" class="rej"/><text x="${I - 8}" y="${y(v) + 3.5}" class="eje" text-anchor="end">${usdEje(v)}</text>`;
  const imax = serie.findIndex(s => s.valor === max);
  serie.forEach((s, i) => {
    const x = I + banda * i + (banda - ancho) / 2, top = y(s.valor), base = y(0), r = Math.min(4, (base - top) / 2, ancho / 2);
    if (s.valor > 0) svg += `<path d="M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + ancho - r} Q${x + ancho},${top} ${x + ancho},${top + r} V${base} Z" fill="${COLOR_DATO}"/>`;
    svg += `<rect x="${I + banda * i}" y="${A}" width="${banda}" height="${H - A - B}" fill="transparent" class="zona-tip" data-tip="${esc(s.etiqueta)}: ${esc(usd(s.valor))}"/>`;
    if (i % cadaN === 0 || i === serie.length - 1) svg += `<text x="${x + ancho / 2}" y="${H - 8}" class="eje" text-anchor="middle">${esc(s.etiqueta)}</text>`;
    if (i === imax) svg += `<text x="${x + ancho / 2}" y="${top - 6}" class="valor" text-anchor="middle">${esc(usd(s.valor))}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" class="columnas" role="img" aria-label="Gasto por periodo">${svg}</svg>`;
}

function pintarEstadisticas(d) {
  const t = d.tiles;
  const periodo = d.periodo.dias ? (d.periodo.dias === 365 ? 'últimos 12 meses' : `últimos ${d.periodo.dias} días`) : 'desde el principio';
  $('#estCuerpo').innerHTML = `
    <div class="tiles est">
      ${tile('Sesiones', nf(t.sesiones), `${nf(t.cerradas)} cerradas · ${nf(t.abiertas)} abiertas`)}
      ${tile('Consultas', nf(t.consultas), `${nf(t.intervenciones)} intervenciones de expertos`)}
      ${tile('Acuerdos adoptados', t.votaciones ? `${nf(t.aprobadas)} de ${nf(t.votaciones)}` : '—', t.pct_acuerdo != null ? `${t.pct_acuerdo} % de las votaciones` : 'Sin votaciones')}
      ${tile('Gasto en IA', usd(t.gasto), t.gasto_por_sesion != null ? `${usd(t.gasto_por_sesion)} por sesión` : periodo)}
    </div>
    <p class="nota peq est-nota">Periodo: ${periodo}. ${t.cuestiones_orden ? `${nf(t.cuestiones_orden)} cuestiones de orden · ` : ''}${t.mociones ? `${nf(t.mociones)} mociones (${nf(t.mociones_aprobadas)} aprobadas) · ` : ''}Costes aproximados según las tarifas de Consumo.</p>
    <div class="rejilla-est">
      ${tarjeta('cGasto', `Gasto por ${d.periodo.por_dia ? 'día' : 'mes'}`, 'US$, según los tokens que informa la API', columnas(d.gasto_serie),
        tablaHTML(['Periodo', 'Gasto'], d.gasto_serie.map(s => [esc(s.etiqueta), usd(s.valor)])))}
      ${tarjeta('cSesiones', 'Sesiones por consejo', '', barras(d.sesiones_por_consejo, v => nf(v)),
        tablaHTML(['Consejo', 'Sesiones'], d.sesiones_por_consejo.map(x => [esc(x.nombre), nf(x.valor)])))}
      ${tarjeta('cResultados', 'Resultado de las votaciones', '', barras(d.resultados, v => nf(v)),
        tablaHTML(['Resultado', 'Votaciones'], d.resultados.map(x => [esc(x.nombre), nf(x.valor)])))}
      ${tarjeta('cActivos', 'Expertos con más intervenciones', '', barras(d.activos, v => nf(v), x => x.consejo),
        tablaHTML(['Experto', 'Consejo', 'Intervenciones'], d.activos.map(x => [esc(x.nombre), esc(x.consejo), nf(x.valor)])))}
      ${tarjeta('cDisidentes', 'Expertos más disidentes', '% de votos contra el resultado final (mínimo 3 votos)',
        barras(d.disidentes.map(x => ({ ...x, valor: x.pct })), v => `${nf(v, v % 1 ? 1 : 0)} %`, x => `${x.en_contra} de ${x.votos} votos`),
        tablaHTML(['Experto', 'Consejo', 'Votos', 'En contra', '%'], d.disidentes.map(x => [esc(x.nombre), esc(x.consejo), nf(x.votos), nf(x.en_contra), nf(x.pct, 1) + ' %'])))}
      ${tarjeta('cModelos', 'Gasto por modelo', '', barras(d.gasto_por_modelo, usd, x => `${fTok(x.tokens)} tokens`),
        tablaHTML(['Modelo', 'Tokens', 'Gasto'], d.gasto_por_modelo.map(x => [esc(x.nombre), fTok(x.tokens), usd(x.valor)])))}
      ${$('#estPanel').value ? '' : tarjeta('cConsejos', 'Gasto por consejo', '', barras(d.gasto_por_consejo, usd),
        tablaHTML(['Consejo', 'Gasto'], d.gasto_por_consejo.map(x => [esc(x.nombre), usd(x.valor)])))}
    </div>`;
  $('#estCuerpo').querySelectorAll('[data-tabla]').forEach(b => b.onclick = () => {
    const c = $('#' + b.dataset.tabla), g = c.querySelector('.vista-grafico'), tb = c.querySelector('.vista-tabla');
    const aTabla = tb.hidden; tb.hidden = !aTabla; g.hidden = aTabla; b.textContent = aTabla ? 'Gráfico' : 'Tabla';
  });
}
// detalle al pasar el ratón (barras y columnas)
const tipEst = $('#estTip');
$('#dlgEstadisticas').addEventListener('mousemove', e => {
  const z = e.target.closest('[data-tip]');
  if (!z) { tipEst.hidden = true; return; }
  tipEst.textContent = z.dataset.tip; tipEst.hidden = false;
  const r = $('#dlgEstadisticas').getBoundingClientRect();
  tipEst.style.left = Math.min(r.width - 230, e.clientX - r.left + 14) + 'px'; tipEst.style.top = (e.clientY - r.top + 14) + 'px';
});
$('#dlgEstadisticas').addEventListener('mouseleave', () => { tipEst.hidden = true; });
