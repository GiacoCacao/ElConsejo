const $ = s => document.querySelector(s);
let paneles = [], panel = null, msgs = [], sel = null, estado = {}, adjuntos = [], qActual = null;
let progreso = null, ultimoPanel = null;   // progreso = {ronda, hechos, de, turno}
let sesion = null, votaciones = [];        // sesión abierta del panel (sesiones.js)
const ES_DOC = f => /\.(pdf|docx|txt|md|odt|rtf)$/i.test(f.name);
const ROMANO = n => ['', 'I', 'II', 'III', 'IV', 'V'][n] || n;

// ---- iconos (trazo fino) ----
const ICONOS = {
  libros: '<path d="M4 4.5h3.5v15H4zM9.5 4.5H13v15H9.5zM15 5.6l3.3-.9 3.2 14.1-3.3.8z"/>',
  actas: '<path d="M7 3.5h8.5L19 7v13.5H7z"/><path d="M15 3.5V7h4M10 11h6M10 14h6M10 17h4"/>',
  ajustes: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  clip: '<path d="M20 11.5l-7.8 7.8a5 5 0 01-7.1-7.1l8.2-8.2a3.4 3.4 0 014.8 4.8l-8.2 8.2a1.7 1.7 0 01-2.4-2.4l7.6-7.6"/>',
  flecha: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  papelera: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
  doc: '<path d="M6.5 3.5h8L18.5 7.5v13h-12z"/><path d="M14.5 3.5v4h4"/>',
  repetir: '<path d="M19.5 12a7.5 7.5 0 11-2.2-5.3M19.5 4.5v4h-4"/>',
  indice: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  izq: '<path d="M15 5l-7 7 7 7"/>', der: '<path d="M9 5l7 7-7 7"/>',
  mazo: '<path d="M13.5 3.5l7 7M11 6l7 7M12.3 4.7l-6 6 7 7 6-6M9.3 13.7L3.5 19.5M3 21h10"/>',
  balanza: '<path d="M12 3.5v17M7.5 20.5h9M4.5 7h15M4.5 7L2 13.5a2.6 2.6 0 005 0zM19.5 7L17 13.5a2.6 2.6 0 005 0z"/>',
  sello: '<circle cx="12" cy="9" r="5.5"/><path d="M8.6 13.4L7 21l5-2.6 5 2.6-1.6-7.6"/>',
  sesiones: '<rect x="3.5" y="5" width="17" height="15.5" rx="1"/><path d="M3.5 9.5h17M8 3v4M16 3v4M7.5 13h3M7.5 16.5h6"/>',
  imprimir: '<path d="M7 9V3.5h10V9M7 17.5H4.5v-8h15v8H17M7 14h10v6.5H7z"/>',
  descargar: '<path d="M12 4v11M7 10.5l5 5 5-5M4.5 20h15"/>',
  enviar: '<path d="M4 12h12M12 6l6 6-6 6M20 4v16"/>',
  lupa: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5M8.5 10.5h4M10.5 8.5v4"/>',
  persona: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-4 4-6 7-6s6 2 7 6"/>',
  grafico: '<path d="M4 20h16M7 16v-5M12 16V7M17 16v-8"/>',
  deslizadores: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  salir: '<path d="M14 4.5h5.5v15H14M10 8l-4 4 4 4M6 12h10"/>',
  arriba: '<path d="M6 15l6-6 6 6"/>', abajo: '<path d="M6 9l6 6 6-6"/>',
  imagen: '<rect x="3.5" y="5" width="17" height="14" rx="1"/><circle cx="9" cy="10" r="1.6"/><path d="M20.5 16l-5-5-8 8"/>',
};
const ico = n => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONOS[n] || ''}</svg>`;
function hidratar(raiz = document) {
  raiz.querySelectorAll('[data-i]').forEach(el => {
    if (el.dataset.hecho) return; el.dataset.hecho = 1;
    const txt = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
    txt.forEach(n => { const s = document.createElement('span'); s.className = 'etq'; s.textContent = n.textContent.trim(); n.replaceWith(s); });
    el.insertAdjacentHTML('afterbegin', ico(el.dataset.i));
  });
}
const ORNAMENTO = '<svg class="orn" viewBox="0 0 120 14" aria-hidden="true"><path d="M0 7h46M74 7h46" stroke="#c9a96e" stroke-width=".8"/><path d="M60 1l6 6-6 6-6-6z" fill="none" stroke="#c9a96e" stroke-width=".8"/><circle cx="60" cy="7" r="1.4" fill="#c9a96e"/></svg>';

// ---- utilidades ----
// respuesta en flujo (líneas JSON): llama a alTrozo con cada trozo de texto y devuelve el evento final
async function flujo(url, alTrozo, opt = {}) {
  const r = await fetch(url, { method: 'POST', ...opt });
  if (r.status === 401) { location.href = '/login'; throw new Error('Inicie sesión para continuar'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
  const lector = r.body.getReader(), dec = new TextDecoder();
  let buf = '', fin = null;
  for (;;) {
    const { value, done } = await lector.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const linea = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!linea) continue;
      const ev = JSON.parse(linea);
      if (ev.t === 'd') alTrozo(ev.x); else if (ev.t === 'fin') fin = ev;
    }
  }
  if (!fin) throw new Error('La respuesta se cortó antes de terminar');
  return fin;
}
let vivo = {}, rafMesa = 0;   // texto que cada experto está escribiendo ahora mismo
const repintarMesa = () => { if (!rafMesa) rafMesa = requestAnimationFrame(() => { rafMesa = 0; pintarMesa(); }); };

const api = async (url, opt) => {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = '/login'; throw new Error('Inicie sesión para continuar'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
  return r.status === 204 ? null : r.json();
};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function md(t) {  // markdown mínimo, siempre sobre texto escapado
  const lineas = esc(t).split('\n'); let h = '', lista = false;
  const en = x => x.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
  for (const l of lineas) {
    const li = l.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (li) { if (!lista) { h += '<ul>'; lista = true; } h += `<li>${en(li[1])}</li>`; continue; }
    if (lista) { h += '</ul>'; lista = false; }
    if (l.trim()) h += `<p>${en(l.replace(/^#+\s*/, ''))}</p>`;
  }
  return h + (lista ? '</ul>' : '');
}
function monograma(a) {
  const m = (a.emoji || '').trim();
  if (/^[\p{L}]{1,3}$/u.test(m)) return m.toUpperCase();
  const todas = (a.nombre || '?').trim().split(/\s+/), sin = todas.filter(w => !w.endsWith('.'));   // sin «Dr.», «P.»…
  const p = sin.length ? sin : todas;
  return (p.length > 1 ? p[0][0] + p[p.length - 1][0] : p[0][0]).toUpperCase();   // nombre y último apellido
}
function avisar(texto, mal = false) {
  const d = document.createElement('div'); d.className = 'aviso-t' + (mal ? ' mal' : ''); d.textContent = texto;
  $('#avisos').append(d); setTimeout(() => d.remove(), 4200);
}
function confirmar(texto, aceptar = 'Aceptar') {
  const dlg = $('#confirmar'); $('#confirmarTexto').textContent = texto;
  dlg.querySelector('[data-v="1"] .etq').textContent = aceptar;
  dlg.showModal();
  return new Promise(ok => {
    dlg.querySelectorAll('[data-v]').forEach(b => b.onclick = () => { dlg.close(); ok(b.dataset.v === '1'); });
    dlg.oncancel = () => ok(false);
  });
}

// ---- carga ----
async function cargar(id) {
  paneles = await api('/api/paneles');
  panel = paneles.find(p => p.id === id) || paneles.find(p => p.tipo !== 'asamblea') || paneles[0] || null;
  if (panel) localStorage.panel = panel.id;
  const est = panel ? await api(`/api/paneles/${panel.id}/sesion`) : { sesion: null, mensajes: [], votaciones: [] };
  sesion = est.sesion; msgs = est.mensajes; votaciones = est.votaciones;
  sel = null; estado = {}; progreso = null;
  const ult = [...msgs].reverse().find(m => m.rol === 'user');
  qActual = ult ? ult.pregunta_id : null;
  for (const m of msgs) if (m.rol === 'agent' && m.pregunta_id === qActual)
    estado[m.agente_id] = m.error ? 'error' : 'listo';
  if (qActual && panel) sel = (panel.agentes.find(a => estado[a.id]) || {}).id || null;
  destinoInd = null; pintarDestino();
  $('#editar').hidden = !!panel && panel.tipo === 'asamblea';
  document.body.classList.toggle('en-asamblea', !!panel && panel.tipo === 'asamblea');
  if (typeof fijarOradores === 'function') fijarOradores((sesion && sesion.oradores) || []);
  pintarTabs(); pintarArco(); pintarMesa(); pintarRegistro(); cargarConsumo(); pintarSesionBar();
  if (typeof pintarOradores === 'function') pintarOradores();
}
async function refrescarAgentes() {   // recuentos de pools, sin tocar la conversación
  const ps = await api('/api/paneles'); const p = ps.find(x => panel && x.id === panel.id);
  if (p) { panel.agentes = p.agentes; pintarArco(); }
}

function pintarTabs() {
  $('#selNombre').textContent = panel ? panel.nombre : 'Sin paneles';
  const menu = $('#menuPaneles'); menu.innerHTML = '';
  for (const p of paneles) {
    const b = document.createElement('button');
    b.type = 'button'; b.setAttribute('role', 'menuitem');
    b.className = 'item' + (p.tipo === 'asamblea' ? ' asamblea' : '') + (panel && p.id === panel.id ? ' act' : '');
    b.innerHTML = p.tipo === 'asamblea'
      ? `<div class="t">${ico('mazo')} ${esc(p.nombre)}</div><div class="d">Debate entre comités con derecho de palabra parlamentario.${p.agentes.length ? ` Última composición: ${p.agentes.length} delegados.` : ''}</div>`
      : `<div class="t">${esc(p.nombre)}</div><div class="d">${esc(p.descripcion || '')}</div>
      <div class="caras">${p.agentes.slice(0, 7).map(a => `<span style="--c:${a.color}">${esc(monograma(a))}</span>`).join('')}
      <em>${p.agentes.length} expertos</em></div>`;
    b.onclick = () => { abrirMenu(false); cargar(p.id); };
    menu.append(b);
  }
}
function abrirMenu(si) {
  $('#menuPaneles').hidden = !si; $('#selPanel').setAttribute('aria-expanded', si);
  if (si) ($('#menuPaneles .item.act') || $('#menuPaneles .item'))?.focus();
}
$('#selPanel').onclick = e => { e.stopPropagation(); abrirMenu($('#menuPaneles').hidden); };
document.addEventListener('click', e => { if (!e.target.closest('.selector')) abrirMenu(false); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#menuPaneles').hidden) { abrirMenu(false); $('#selPanel').focus(); } });

// ---- hemiciclo ----
function geometria() {
  const arco = $('#arco'), W = arco.clientWidth, H = arco.clientHeight, n = panel ? panel.agentes.length : 0;
  const movil = W < 760, cx = W / 2;
  // pantallas de poca altura (portátiles de 1366×768…): arco bajo y ancho arriba, medallones menores
  const compacto = !movil && H < 720;
  document.body.classList.toggle('compacto', compacto);
  // escritorio: hemiciclo que abraza el atril; móvil: arco compacto arriba y el atril debajo
  // compacto: curva suave arriba (los del centro, altos; los de los extremos, que no chocan con la mesa, algo más abajo)
  const Ry = movil ? Math.min(H * .36, 240) - 62 : compacto ? Math.min(80, H * .14) : Math.max(150, H - 190);
  const cy = movil ? Math.min(H * .36, 240) + 30 : compacto ? 84 + Ry : H - 46;   // móvil: deja sitio a la barra de consumo
  const Rx = movil ? W / 2 - 48 : compacto ? Math.max(150, W / 2 - 100) : Math.max(150, W / 2 - 96);
  const pos = (panel ? panel.agentes : []).map((a, i) => {
    if (compacto && n > 1) {   // misma separación horizontal, siguiendo la curva: nadie se amontona en los extremos
      const dx = -0.92 + 1.84 * i / (n - 1), t = Math.acos(dx);
      return { a, t, x: cx + Rx * dx, y: cy - Ry * Math.sin(t) };
    }
    const t = n === 1 ? Math.PI / 2 : Math.PI * (0.9 - 0.8 * i / (n - 1));
    return { a, t, x: cx + Rx * Math.cos(t), y: cy - Ry * Math.sin(t) };
  });
  const mesaW = Math.min(700, W * (movil ? .94 : .58)); let top = movil ? 60 : 72;   // nunca bajo la barra de consumo
  for (const p of pos) if (Math.abs(p.x - cx) < mesaW / 2 + (compacto ? 40 : 70)) top = Math.max(top, p.y + (movil ? 52 : compacto ? 78 : 118));
  // la respuesta conserva siempre un alto útil, aunque la mesa tape un poco el arco
  const chat = ($('#chat') && $('#chat').offsetHeight) || 118;
  const tope = compacto ? H - chat - 40 - 190 : H - 300;
  return { W, H, cx, cy, Rx, Ry, pos, movil, compacto, mesaTop: Math.max(60, Math.min(top, tope)) };
}

function pintarArco() {
  const arco = $('#arco'); arco.innerHTML = '';
  if (!panel) return;
  const g = geometria(), entrada = ultimoPanel !== panel.id; ultimoPanel = panel.id;
  // con muchos expertos, medallones y rótulos se ajustan a la separación disponible entre vecinos
  const n = panel.agentes.length, sep = n > 1 ? (g.compacto ? g.Rx * 1.84 / (n - 1) : g.Rx * 0.8 * Math.PI / (n - 1) * 0.7) : 999;
  arco.style.setProperty('--ancho-ag', Math.max(70, Math.min(g.compacto ? 160 : 184, sep - 10)) + 'px');
  arco.classList.toggle('apretado', sep < 150);
  arco.classList.toggle('muy-apretado', sep < 95);
  $('#mesa').style.setProperty('--mesa-top', g.mesaTop + 'px');
  pintarDescripcion();
  g.pos.forEach(({ a, x, y }, i) => {
    const d = document.createElement('div');
    d.className = 'agente ' + (estado[a.id] || '') + (sel === a.id ? ' sel' : '') + (entrada ? ' entrada' : '')
      + (progreso && progreso.ronda > 0 && !estado[a.id] ? ' apagado' : '');
    d.tabIndex = 0; d.setAttribute('role', 'button'); d.setAttribute('aria-label', `${a.nombre}, ${a.rol}`);
    d.style.cssText = `left:${x}px;top:${y}px;--c:${a.color};--i:${i}`;
    const turno = sesion && sesion.modo_debate === 'orden' ? sesion.orden.indexOf(a.id) + 1 : 0;
    d.innerHTML = `<div class="medallon"><span class="anillo"></span><span class="ini">${esc(monograma(a))}</span><span class="punto"></span>${turno ? `<span class="turno" title="Turno ${turno} del debate">${turno}</span>` : ''}</div>
      <div class="n">${esc(a.nombre)}</div><div class="r" title="${esc(a.rol)}">${esc(a.rol)}</div>`
      + (a.comite ? `<div class="pool delegacion" title="Delegado del ${esc(a.comite)}">${esc(a.comite.replace(/^(Panel|Consejo)\s+(de\s+|del\s+)?/i, ''))}</div>` :
         a.capitulos ? `<div class="pool" title="${a.docs} documentos · ${a.capitulos} capítulos">${a.docs} doc · ${a.capitulos} cap.</div>` : '');
    d.onclick = () => elegir(a.id);
    d.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); elegir(a.id); } };
    arco.append(d);
  });
  pintarHemiciclo(g);
}

function pintarHemiciclo(g) {
  const s = $('#hemiciclo'), { cx, cy, Rx, Ry, W } = g;
  s.setAttribute('viewBox', `0 0 ${g.W} ${g.H}`);
  const arcoE = (rx, ry) => `M ${cx - rx} ${cy} A ${rx} ${ry} 0 0 1 ${cx + rx} ${cy}`;
  let h = `<defs>
    <linearGradient id="gSuelo" x1="0" x2="1"><stop offset="0" stop-color="#c9a96e" stop-opacity="0"/><stop offset=".5" stop-color="#c9a96e" stop-opacity=".45"/><stop offset="1" stop-color="#c9a96e" stop-opacity="0"/></linearGradient>
    <linearGradient id="gEnlace" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e6d3a8" stop-opacity=".9"/><stop offset="1" stop-color="#c9a96e" stop-opacity=".1"/></linearGradient>
  </defs>
  ${g.movil || g.compacto ? '' : `<path class="arcoS" d="${arcoE(Rx + 64, Ry + 64)}"/>`}
  <path class="arcoP" d="${arcoE(Rx, Ry)}"/>
  <path class="arcoS" d="${arcoE(Math.max(40, Rx - 70), Math.max(40, Ry - 70))}"/>
  ${g.movil || g.compacto ? '' : `<line class="suelo" x1="${W * .08}" y1="${cy}" x2="${W * .92}" y2="${cy}"/>`}`;
  for (const p of g.pos) {   // marcas radiales por fuera de cada escaño
    const ux = Math.cos(p.t), uy = -Math.sin(p.t);
    h += `<line class="marcaA" x1="${cx + (Rx + 56) * ux}" y1="${cy + (Ry + 56) * uy}" x2="${cx + (Rx + 70) * ux}" y2="${cy + (Ry + 70) * uy}"/>`;
  }
  const p = g.pos.find(p => p.a.id === sel);
  if (p && innerWidth >= 760) {
    const y0 = p.y + 46, y1 = g.mesaTop + 30, x1 = cx + Math.max(-260, Math.min(260, (p.x - cx) * .55));
    h += `<path class="enlaceSel" d="M ${p.x} ${y0} C ${p.x} ${(y0 + y1) / 2}, ${x1} ${y0}, ${x1} ${y1}"/>`;
  }
  s.innerHTML = h;
}

function pintarDescripcion() {
  const d = $('#descripcion');
  if (progreso) {
    const tit = progreso.titulo || (progreso.ronda ? `Réplica ${ROMANO(progreso.ronda)}` : 'Deliberando');
    d.className = 'descripcion vivo';
    d.innerHTML = `${tit} · ${progreso.turno ? `en uso de la palabra: ${esc(progreso.turno)}${progreso.de > 1 ? ' · ' : ''}` : ''}${progreso.de > 1 ? `${progreso.hechos} de ${progreso.de}` : ''}<span class="barraP"><i style="width:${100 * progreso.hechos / Math.max(1, progreso.de)}%"></i></span>`;
  } else { d.className = 'descripcion'; d.textContent = panel ? panel.descripcion || '' : ''; }
}

function elegir(id) { sel = id; pintarArco(); pintarMesa(); }
function mover(paso) {
  if (!panel || !panel.agentes.length) return;
  const i = panel.agentes.findIndex(a => a.id === sel);
  elegir(panel.agentes[(i + paso + panel.agentes.length) % panel.agentes.length].id);
}

// ---- atril ----
const retirando = new Set();
function cronometro(id) {   // tiempo de palabra: palabras dichas frente al límite de la sesión
  const n = (vivo[id] || '').trim().split(/\s+/).filter(Boolean).length;
  const lim = sesion && sesion.limite_palabras;
  const pct = lim ? Math.min(100, 100 * n / lim) : 0, pasado = lim && n > lim;
  return `<div class="crono ${pasado ? 'pasado' : ''}"><span class="rot">Tiempo de palabra</span>
    ${lim ? `<span class="medidor"><i style="width:${Math.max(2, pct)}%"></i></span><b>${n} / ${lim}</b>${pasado ? '<em>excedido</em>' : ''}` : `<b>${n} palabras</b>`}
    <span class="grow"></span><button type="button" class="enlace peq" data-retirar ${retirando.has(id) ? 'disabled' : ''}>${ico('x')}<span>${retirando.has(id) ? 'Retirando…' : 'Retirar la palabra'}</span></button></div>`;
}
function gastoAgente(id) {
  const g = consumoDatos && consumoDatos.agentes.find(x => x.id === id);
  if (!g || !g.ultima || !g.ultima.llamadas) return '';
  return `<div class="gasto">${fTok(g.ultima.entrada + g.ultima.salida)} tokens · <b>≈ ${fUSD(g.ultima.coste)}</b>${g.pct != null ? ` · contexto ${nf(g.pct, g.pct < 10 ? 1 : 0)} %` : ''}</div>`;
}
const SUGERENCIAS = ['¿Cuáles son los principales riesgos de esta decisión?', 'Valoren pros y contras de la propuesta adjunta.', '¿Qué harían ustedes en mi lugar?'];
function pintarMesa() {
  const r = $('#respuesta'); r.className = ''; r.style.removeProperty('--c');
  const a = panel && panel.agentes.find(x => x.id === sel);
  if (!a) {
    r.className = 'vacia';
    const hay = panel && panel.agentes.length;
    r.innerHTML = `<div class="vacio">${ORNAMENTO}
      <h2>${qActual ? 'El Consejo ha deliberado' : 'Plantee su consulta al Consejo'}</h2>
      <p>${!hay ? 'Este panel aún no tiene expertos. Configúrelo para empezar.'
        : sesion && !qActual ? `Sesión nº ${sesion.numero} abierta. Asunto: «${esc(sesion.asunto)}». Plantee la primera consulta para abrir el debate.`
        : qActual ? 'Seleccione a un experto del hemiciclo para leer su dictamen.'
        : 'Cada experto responderá desde su especialidad y, si lo desea, deliberará con sus colegas. Puede adjuntar documentos e imágenes.'}</p>
      ${hay && !qActual ? `<div class="sugerencias">${SUGERENCIAS.map(s => `<button type="button">${esc(s)}</button>`).join('')}</div>` : ''}</div>`;
    r.querySelectorAll('.sugerencias button').forEach(b => b.onclick = () => { $('#texto').value = b.textContent; $('#texto').focus(); autoAlto(); });
    return;
  }
  r.style.setProperty('--c', a.color);
  const suyos = msgs.filter(x => x.rol === 'agent' && x.agente_id === a.id && x.pregunta_id === qActual).sort((p, q) => p.ronda - q.ronda);
  let h = `<header class="firma" style="--c2:color-mix(in srgb,${a.color} 45%,#c9a96e)">
      <div class="mini">${esc(monograma(a))}</div>
      <div><div class="quien">${esc(a.nombre)}</div><div class="rol">${esc(a.rol || 'Experto')}</div>${gastoAgente(a.id)}</div>
      <div class="nav">${!document.body.classList.contains('observador') ? `${panel.tipo === 'asamblea' && sesion && qActual
          ? `<button class="contorno peq palabra" data-palabra title="Conceder la palabra a ${esc(a.nombre)}">${ico('mazo')}<span>Conceder la palabra</span></button>` : ''}
        <button class="icono" data-ind title="Consulta individual a ${esc(a.nombre)}">${ico('persona')}</button>` : ''}
        <button class="icono" data-mv="-1" aria-label="Experto anterior">${ico('izq')}</button><button class="icono" data-mv="1" aria-label="Experto siguiente">${ico('der')}</button></div>
    </header><div class="cuerpo">`;
  for (const m of suyos) {
    if (m.modo) h += `<div class="replica">${m.modo === 'alusion' ? 'Por alusiones' : 'En uso de la palabra'}</div>`;
    else if (m.ronda > 0) h += `<div class="replica">Réplica ${ROMANO(m.ronda)}</div>`;
    h += md(m.texto);
    if (m.fuentes.length) h += `<div class="fuentes"><div class="rot">Fuentes consultadas</div>` + m.fuentes.map(f =>
      `<div class="f"><span>${esc(f.doc)}</span><span>Cap. ${f.capitulo} · ${esc(f.titulo)}${f.biblioteca && f.biblioteca !== 'Biblioteca propia' ? ` · <em>${esc(f.biblioteca)}</em>` : ''}</span></div>`).join('') + '</div>';
  }
  if (estado[a.id] === 'hablando' && vivo[a.id] !== undefined && !document.body.classList.contains('observador')) h += cronometro(a.id);
  if (estado[a.id] === 'hablando' && vivo[a.id]) {
    if (vivoModo[a.id]) h += `<div class="replica">${vivoModo[a.id] === 'alusion' ? 'Por alusiones' : 'En uso de la palabra'}</div>`;
    else if (suyos.length) h += `<div class="replica">Réplica ${ROMANO((suyos[suyos.length - 1].ronda || 0) + 1)}</div>`;
    h += `<div class="en-vivo">${md(vivo[a.id])}</div>`;
  }
  else if (estado[a.id] === 'pensando' || estado[a.id] === 'hablando') h += `<div class="pensando-txt">${suyos.length ? 'Preparando su réplica' : 'Estudiando la consulta'}<span class="puntos"><i></i><i></i><i></i></span></div>`;
  else if (!suyos.length) h += '<p class="pensando-txt">Aún no se ha pronunciado.</p>';
  const abajo = r.scrollHeight - r.scrollTop - r.clientHeight < 40;   // seguir el texto si se estaba al final
  r.innerHTML = h + '</div>';
  if (estado[a.id] === 'hablando' && abajo) r.scrollTop = r.scrollHeight;
  r.querySelectorAll('[data-mv]').forEach(b => b.onclick = () => mover(+b.dataset.mv));
  const bi = r.querySelector('[data-ind]'); if (bi) bi.onclick = () => consultaIndividual(a.id);
  const br = r.querySelector('[data-retirar]');
  if (br) br.onclick = async () => {
    br.disabled = true; br.querySelector('span').textContent = 'Retirando…'; retirando.add(a.id);
    await api(`/api/preguntas/${qActual}/agentes/${a.id}/retirar`, { method: 'POST' }).catch(e => avisar(e.message, true));
  };
  const bp = r.querySelector('[data-palabra]'); if (bp) bp.onclick = () => concederPalabra(a.id, 'palabra');
  if (suyos.some(m => m.error)) r.classList.add('error');
}

function pintarRegistro() {
  const box = $('#registro'); box.innerHTML = '';
  if (!panel) return;
  $('#latSobre').textContent = sesion ? `Sesión nº ${sesion.numero} · ${sesion.asunto}` : 'Sin sesión abierta';
  if (!msgs.length) { box.innerHTML = '<div class="acta vacia">Aún no hay intervenciones en esta sesión.</div>'; return; }
  for (const m of msgs) {
    const a = panel.agentes.find(x => x.id === m.agente_id);
    const d = document.createElement('div');
    d.className = 'acta ' + m.rol; if (a) d.style.setProperty('--c', `color-mix(in srgb,${a.color} 40%,#e6d3a8)`);
    const hora = new Date(m.ts * 1000).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
    const dest = m.destinatario && panel.agentes.find(x => x.id === m.destinatario);
    const etq = m.modo ? (m.modo === 'alusion' ? 'por alusiones · ' : 'en uso de la palabra · ') : m.ronda ? 'réplica ' + ROMANO(m.ronda) + ' · ' : '';
    d.innerHTML = `<div class="q"><b>${m.rol === 'user' ? (dest ? 'Consulta individual a ' + esc(dest.nombre) : 'Consulta') : esc(a ? a.nombre : 'Experto')}</b><span>${a && a.comite ? esc(a.comite) + ' · ' : ''}${etq}${hora}</span></div>`
      + (m.rol === 'user' ? `<p>${esc(m.texto)}</p>` : `<div class="cuerpo">${md(m.texto)}</div>`)
      + (m.adjuntos.length ? `<div class="adjuntos-msg">${m.adjuntos.map(x => `<span class="ficha">${ico('doc')}${esc(x.nombre)}</span>`).join('')}</div>` : '')
      + m.imagenes.map(i => `<img src="/img/${i}" alt="">`).join('');
    box.append(d);
  }
  box.scrollTop = box.scrollHeight;
}

// ---- consulta ----
function pintarAdjuntos() {
  const box = $('#adjuntos'); box.innerHTML = '';
  adjuntos.forEach((f, i) => {
    const d = document.createElement('div');
    if (ES_DOC(f)) { d.className = 'ficha'; d.innerHTML = `${ico('doc')}${esc(f.name)}<button type="button" aria-label="Quitar">${ico('x')}</button>`; }
    else { d.className = 'miniatura'; d.innerHTML = `<img src="${URL.createObjectURL(f)}" alt=""><button type="button" aria-label="Quitar">${ico('x')}</button>`; }
    d.querySelector('button').onclick = () => { adjuntos.splice(i, 1); pintarAdjuntos(); };
    box.append(d);
  });
}
const autoAlto = () => { const t = $('#texto'); t.style.height = 'auto'; t.style.height = t.scrollHeight + 'px'; };
$('#archivos').onchange = e => { adjuntos.push(...e.target.files); e.target.value = ''; pintarAdjuntos(); };
$('#chat').addEventListener('paste', e => {
  const fs = [...e.clipboardData.files].filter(f => f.type.startsWith('image/'));
  if (fs.length) { adjuntos.push(...fs); pintarAdjuntos(); }
});
$('#escena').addEventListener('dragover', e => e.preventDefault());
$('#escena').addEventListener('drop', e => { e.preventDefault(); if (e.dataTransfer.files.length) { adjuntos.push(...e.dataTransfer.files); pintarAdjuntos(); } });
$('#texto').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chat').requestSubmit(); } });
$('#texto').addEventListener('input', autoAlto);
document.addEventListener('keydown', e => {
  if (document.activeElement.matches('input,textarea,select') || document.querySelector('dialog[open]') || !$('#menuPaneles').hidden) return;
  if (e.key === 'ArrowRight') mover(1); else if (e.key === 'ArrowLeft') mover(-1);
});

let rondas = +(localStorage.rondas || 1);
function sincDialogo() {
  $('#lrondas').hidden = !$('#dialogo').checked;
  localStorage.dialogo = $('#dialogo').checked ? '1' : '0'; localStorage.rondas = rondas;
  $('#lrondas').querySelectorAll('[data-r]').forEach(b => { b.classList.toggle('act', +b.dataset.r === rondas); b.setAttribute('aria-checked', +b.dataset.r === rondas); });
}
$('#dialogo').checked = localStorage.dialogo === '1';
$('#dialogo').onchange = sincDialogo;
$('#lrondas').querySelectorAll('[data-r]').forEach(b => b.onclick = () => { rondas = +b.dataset.r; sincDialogo(); });
sincDialogo();

function ocupado(si, texto) {
  $('#enviar').disabled = si; $('#enviar .etq').textContent = texto || 'Consultar';
}
// una intervención en tiempo real; devuelve el mensaje guardado (o uno de error)
let vivoModo = {};
async function intervenir(qid, id, { ronda = 0, modo = null, por = null, vigente = () => true } = {}) {
  vivo[id] = ''; vivoModo[id] = modo;
  let m, alus = [];
  try {
    const fin = await flujo(`/api/preguntas/${qid}/agentes/${id}/flujo?ronda=${ronda}${modo ? `&modo=${modo}` : ''}${por ? `&por=${por}` : ''}`, x => {
      if (!vigente()) return;
      const primero = !vivo[id];
      vivo[id] += x;
      if (primero) { estado[id] = 'hablando'; if (!sel) sel = id; pintarArco(); }
      if (sel === id) repintarMesa();
    });
    m = fin.m; alus = fin.alusiones || [];
    if (fin.oradores && typeof fijarOradores === 'function') { fijarOradores(fin.oradores); alus = []; }
    if (fin.retirada) avisar(`La presidencia retiró la palabra a ${(panel.agentes.find(x => x.id === id) || {}).nombre || 'el orador'}.`);
  } catch (err) { m = { rol: 'agent', agente_id: id, pregunta_id: qid, ronda, modo, texto: err.message, error: true, imagenes: [], adjuntos: [], fuentes: [], ts: Date.now() / 1000 }; }
  delete vivo[id]; delete vivoModo[id]; retirando.delete(id);
  if (!vigente()) return null;
  msgs.push(m); estado[id] = m.error ? 'error' : 'listo';
  if (!sel) sel = id;
  pintarArco(); pintarMesa(); pintarRegistro(); pedirConsumo();
  if (alus.length && typeof anotarAlusiones === 'function') anotarAlusiones(id, alus);
  if (typeof pintarOradores === 'function') pintarOradores();
  return m;
}

// consulta individual: la pregunta va solo a un experto y los demás no la oyen
let destinoInd = null;
function pintarDestino() {
  const a = destinoInd && panel && panel.agentes.find(x => x.id === destinoInd);
  if (!a) destinoInd = null;
  const d = $('#destino');
  d.hidden = !a;
  d.innerHTML = a ? `${ico('persona')}<span>Consulta individual a <b>${esc(a.nombre)}</b> · solo este experto la oirá</span>
    <button type="button" aria-label="Volver al pleno">${ico('x')}</button>` : '';
  if (a) d.querySelector('button').onclick = () => { destinoInd = null; pintarDestino(); };
  $('#texto').placeholder = a ? `Consulta individual a ${a.nombre}…` : (innerWidth < 760 ? 'Su consulta…' : 'Plantee su consulta al Consejo…');
}
function consultaIndividual(id) { destinoInd = id; pintarDestino(); $('#texto').focus(); }

$('#chat').onsubmit = async e => {
  e.preventDefault();
  if (!panel || $('#enviar').disabled) return;
  if (!panel.agentes.length) return avisar('Este panel no tiene expertos todavía.', true);
  if (sesion && sesion.receso) return avisar('La sesión está en cuarto intermedio. Reanúdela para continuar.', true);
  const fd = new FormData(); fd.append('texto', $('#texto').value);
  adjuntos.forEach(f => fd.append('imagenes', f));
  const individual = destinoInd;
  if (individual) fd.append('destinatario', individual);
  const nR = $('#dialogo').checked && !individual ? rondas : 0;
  ocupado(true, adjuntos.some(ES_DOC) ? 'Procesando' : 'Enviando');
  try {
    const q = await api(`/api/paneles/${panel.id}/preguntas`, { method: 'POST', body: fd });
    $('#texto').value = ''; autoAlto(); adjuntos = []; pintarAdjuntos(); ocupado(true, individual ? 'Consultando' : 'Deliberando');
    msgs.push(q); qActual = q.pregunta_id; estado = {}; sel = individual;
    if (typeof oradores !== 'undefined') oradores.length = 0;
    const pid = panel.id, vigente = () => panel && panel.id === pid && qActual === q.pregunta_id;
    if (!sesion || sesion.id !== q.sesion_id) await refrescarSesion();   // consultar abre sesión si no la había
    const enOrden = !individual && !!sesion && sesion.modo_debate === 'orden';
    const nombreDe = id => (panel.agentes.find(a => a.id === id) || {}).nombre;
    let activos = individual ? [individual]
      : enOrden ? sesion.orden.filter(id => panel.agentes.some(a => a.id === id)) : panel.agentes.map(a => a.id);
    for (let r = 0; r <= nR && activos.length; r++) {
      progreso = { ronda: r, hechos: 0, de: activos.length, turno: null };
      if (r) estado = {};
      activos.forEach(id => estado[id] = enOrden ? 'espera' : 'pensando');
      pintarArco(); pintarMesa(); pintarRegistro();
      const uno = async id => {
        if (enOrden || individual) { estado[id] = 'pensando'; progreso.turno = nombreDe(id); sel = id; pintarArco(); pintarMesa(); }
        const m = await intervenir(q.pregunta_id, id, { ronda: r, vigente });
        if (m) progreso.hechos++;
        return m;
      };
      let hechos = [];
      if (enOrden) { for (const id of activos) { const m = await uno(id); if (!vigente()) break; hechos.push(m); } }
      else hechos = await Promise.all(activos.map(uno));
      if (!vigente()) break;
      activos = hechos.filter(m => m && !m.error).map(m => m.agente_id);
    }
    if (vigente()) {   // al terminar: «error» solo si ninguna de sus intervenciones salió bien
      const suyas = id => msgs.filter(m => m.rol === 'agent' && m.pregunta_id === qActual && m.agente_id === id);
      for (const a of panel.agentes) { const m = suyas(a.id); if (m.length) estado[a.id] = m.some(x => !x.error) ? 'listo' : 'error'; }
      progreso = null; pintarArco(); pintarMesa();
      const fallos = msgs.filter(m => m.rol === 'agent' && m.pregunta_id === qActual && m.error).length;
      if (fallos) avisar(`${fallos} intervención(es) no se pudieron completar. Lea el detalle en cada experto.`, true);
    }
  } catch (err) { avisar(err.message, true); }
  progreso = null; pintarDescripcion(); ocupado(false); pintarSesionBar();
  if (typeof pintarOradores === 'function') pintarOradores();
};

// ---- actas ----
$('#historial').onclick = () => { $('#lateral').hidden = !$('#lateral').hidden; pintarRegistro(); };
$('#cerrar').onclick = () => $('#lateral').hidden = true;



// ---- consumo de la API ----
let consumoDatos = null, consumoT = null, avisoTope = false;
const nf = (x, d = 0) => Number(x || 0).toLocaleString('es', { minimumFractionDigits: d, maximumFractionDigits: d });
const fTok = n => n < 1000 ? nf(n) : n < 1e6 ? nf(n / 1e3, 1) + ' k' : nf(n / 1e6, n < 1e7 ? 2 : 1) + ' M';
const fUSD = x => x == null ? '—' : x === 0 ? 'US$ 0' : 'US$ ' + nf(x, x < 0.01 ? 4 : x < 1 ? 3 : 2);
async function cargarConsumo() {
  if (!panel) return;
  try { consumoDatos = await api(`/api/paneles/${panel.id}/consumo`); } catch { return; }
  pintarConsumo();
  if (sel) pintarMesa();
  if ($('#dlgConsumo').open) pintarDetalleConsumo();
}
const pedirConsumo = () => { clearTimeout(consumoT); consumoT = setTimeout(cargarConsumo, 350); };
function pintarConsumo() {
  const d = consumoDatos; if (!d) return;
  const s = d.servicio, t = s.tarifa;
  $('#consumo').hidden = false;
  $('#cSvc').innerHTML = `<b>${esc(s.proveedor)}</b> ${esc(s.modelo)}`
    + (t && t.franja ? ` <em class="${s.punta ? 'punta' : ''}" title="${s.punta ? 'Hora punta: tarifa doble' : 'Fuera de hora punta'}">${s.punta ? 'punta' : 'valle'}</em>` : '');
  $('#consumo .led').classList.toggle('off', !t);
  const conPct = d.agentes.filter(a => a.pct != null);
  const max = conPct.sort((a, b) => b.pct - a.pct)[0];
  $('#cCtxBar').style.width = (max ? Math.min(100, Math.max(1.5, max.pct)) : 0) + '%';
  $('#cCtxBar').parentElement.classList.toggle('alto', !!max && max.pct > 75);
  $('#cCtx').textContent = max ? `${nf(max.pct, max.pct < 10 ? 1 : 0)} % · ${fTok(max.contexto_usado)} / ${fTok(max.contexto_max)}` : 'sin uso';
  $('#cTok').textContent = `↑ ${fTok(d.panel.entrada)}  ↓ ${fTok(d.panel.salida)}`;
  const g = d.gasto || {};
  $('#consumo').classList.toggle('tope', !!g.excedido); $('#consumo').classList.toggle('cerca', !!g.cerca);
  $('#consumo').title = g.excedido ? `Tope de gasto ${g.excedido} alcanzado${g.modo === 'bloquear' ? ': las consultas están bloqueadas' : ''} — ver Ajustes`
    : 'Consumo de la API y costes aproximados — pulse para ver el detalle';
  if (g.excedido && !avisoTope) { avisoTope = true; avisar(`Tope de gasto ${g.excedido} alcanzado (hoy US$ ${nf(g.hoy, 3)} · mes US$ ${nf(g.mes, 3)})${g.modo === 'bloquear' ? '. Las consultas están bloqueadas.' : '.'}`, true); }
  $('#cCoste').textContent = innerWidth < 760 ? fUSD(d.panel.coste)
    : d.ultima ? `${fUSD(d.ultima.coste)} última · ${fUSD(d.panel.coste)} panel` : `${fUSD(d.panel.coste)} panel`;
}
function pintarDetalleConsumo() {
  const d = consumoDatos; if (!d) return;
  const tile = (rot, s, extra = '') => `<div class="tile"><div class="rot">${rot}</div><div class="cifra">${s ? fUSD(s.coste) : '—'}</div>
    <div class="det">${s ? `${nf(s.llamadas)} llamadas · ↑ ${fTok(s.entrada)} ↓ ${fTok(s.salida)}${s.cache ? ` · caché ${fTok(s.cache)}` : ''}` : 'Sin consultas'}${extra}</div></div>`;
  const filas = d.agentes.map(a => {
    const ag = panel.agentes.find(x => x.id === a.id) || {};
    return `<tr><td><div class="quien"><span style="--c:${ag.color}">${esc(monograma(ag))}</span><div>${esc(a.nombre)}<small>${esc(a.modelo)}${a.tarifa ? '' : ' · sin tarifa'}</small></div></div></td>
      <td>${a.pct == null ? '—' : `<span class="medidor${a.pct > 75 ? ' alto' : ''}"><i style="width:${Math.min(100, Math.max(1.5, a.pct))}%"></i></span>${nf(a.pct, a.pct < 10 ? 1 : 0)} %`}<small>${a.contexto_usado ? fTok(a.contexto_usado) + ' de ' + fTok(a.contexto_max) : ''}</small></td>
      <td class="opt">${fTok(a.entrada)}</td><td class="opt">${fTok(a.salida)}</td><td>${nf(a.llamadas)}</td>
      <td>${a.ultima && a.ultima.llamadas ? fUSD(a.ultima.coste) : '—'}</td><td>${fUSD(a.coste)}</td></tr>`;
  }).join('');
  const s = d.servicio;
  $('#consumoCuerpo').innerHTML = `
    <div class="tiles">${tile('Última consulta', d.ultima)}${tile('Este panel', d.panel)}${tile('Bibliotecas · resúmenes', d.pools)}${tile('Total general', d.global)}</div>
    <table class="tabla"><thead><tr><th>Experto</th><th>Contexto (última)</th><th class="opt">Entrada</th><th class="opt">Salida</th><th>Llamadas</th><th>Última</th><th>Acumulado</th></tr></thead>
    <tbody>${filas}</tbody><tfoot><tr><td>Panel</td><td></td><td class="opt">${fTok(d.panel.entrada)}</td><td class="opt">${fTok(d.panel.salida)}</td><td>${nf(d.panel.llamadas)}</td><td>${d.ultima ? fUSD(d.ultima.coste) : '—'}</td><td>${fUSD(d.panel.coste)}</td></tr></tfoot></table>
    <p class="nota peq">Costes aproximados en dólares a partir de los tokens que informa la API${d.global.estimado ? ' (algunas llamadas sin datos de uso se han estimado por longitud del texto)' : ''}.
      ${s.tarifa && s.tarifa.franja ? `Servicio en <b>${s.punta ? 'hora punta' : 'franja valle'}</b> ahora mismo: DeepSeek cobra el doble de 01:00 a 04:00 y de 06:00 a 10:00 UTC, de lunes a viernes; cada llamada se valora con su franja.` : ''}
      Fuente de las tarifas de serie: ${esc(s.fuente)}.</p>
    <h3 class="sub">Tarifas por modelo <small class="nota peq" style="margin:0">USD por millón de tokens · editables</small><span class="grow"></span><button type="button" id="nuevaTarifa" class="contorno">${ico('mas')}<span>Añadir modelo</span></button></h3>
    <table class="tabla" id="tablaTarifas"><thead><tr><th>Modelo</th><th>Contexto</th><th>Entrada</th><th>Caché</th><th>Salida</th><th class="opt">Entrada punta</th><th class="opt">Caché punta</th><th class="opt">Salida punta</th><th></th></tr></thead><tbody></tbody></table>`;
  pintarTarifas();
  $('#nuevaTarifa').onclick = () => filaTarifa({ modelo: '', contexto: 128000 }, true);
}
async function pintarTarifas() {
  const r = await api('/api/tarifas');
  $('#tablaTarifas tbody').innerHTML = '';
  r.tarifas.forEach(t => filaTarifa(t, false));
}
function filaTarifa(t, nueva) {
  const tr = document.createElement('tr');
  const n = (k, v) => `<input data-k="${k}" inputmode="decimal" value="${v ?? ''}" placeholder="—">`;
  tr.innerHTML = `<td>${nueva ? '<input class="mod" data-k="modelo" placeholder="nombre-del-modelo">' : `${esc(t.modelo)}<small>${esc(t.proveedor || '')}</small>`}</td>
    <td>${n('contexto', t.contexto)}</td><td>${n('entrada', t.entrada)}</td><td>${n('cache', t.cache)}</td><td>${n('salida', t.salida)}</td>
    <td class="opt">${n('entrada_punta', t.entrada_punta)}</td><td class="opt">${n('cache_punta', t.cache_punta)}</td><td class="opt">${n('salida_punta', t.salida_punta)}</td>
    <td><button type="button" class="icono" title="Eliminar tarifa">${ico('papelera')}</button></td>`;
  const guardar = async () => {
    const modelo = nueva ? tr.querySelector('[data-k=modelo]').value.trim() : t.modelo;
    if (!modelo) return;
    const cuerpo = { proveedor: t.proveedor || (nueva ? 'Personalizado' : null), franja: t.franja || null };
    tr.querySelectorAll('input[data-k]:not([data-k=modelo])').forEach(i => cuerpo[i.dataset.k] = i.value.replace(',', '.'));
    try { await api(`/api/tarifas/${encodeURIComponent(modelo)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
      if (nueva) { nueva = false; t = { ...cuerpo, modelo }; } avisar(`Tarifa de ${modelo} guardada.`); cargarConsumo(); }
    catch (e) { avisar(e.message, true); }
  };
  tr.querySelectorAll('input').forEach(i => i.addEventListener('change', guardar));
  tr.querySelector('button').onclick = async () => {
    if (nueva) return tr.remove();
    if (!await confirmar(`¿Eliminar la tarifa de ${t.modelo}? Sus llamadas quedarán sin coste calculado.`, 'Eliminar')) return;
    await api(`/api/tarifas/${encodeURIComponent(t.modelo)}`, { method: 'DELETE' }); tr.remove(); cargarConsumo();
  };
  $('#tablaTarifas tbody').append(tr);
}
$('#consumo').onclick = () => { $('#dlgConsumo').showModal(); pintarDetalleConsumo(); };
$('#cerrarConsumo').onclick = () => $('#dlgConsumo').close();

// ---- bibliotecas (pools por agente) ----
let poolAg = null, poolDatos = {}, poolTimer = null, abiertos = new Set();
const VIVO = e => !['listo', 'error'].includes(e);
async function abrirPools() {
  if (!panel) return;
  poolAg = ['_consejo', '_general'].includes(poolAg) || panel.agentes.some(a => a.id === poolAg) ? poolAg : (sel || '_consejo');
  $('#pools').showModal();
  const s = await api('/salud').catch(() => ({}));
  if (!s.fabrica_configurada) { $('#notaPools').classList.add('aviso'); $('#notaPools').textContent = 'Falta CONSEJO_FABRICA_URL en el .env: sin la fábrica no se pueden procesar documentos.'; }
  await cargarPools();
}
async function cargarPools() {
  clearTimeout(poolTimer);
  if (!$('#pools').open || !panel) return;
  poolDatos = await api(`/api/paneles/${panel.id}/pools`).catch(() => poolDatos);
  pintarPools();
  if (Object.values(poolDatos).flat().some(d => VIVO(d.estado))) poolTimer = setTimeout(cargarPools, 2000);
  else { refrescarAgentes(); pedirConsumo(); }
}
function pintarPools() {
  const tabs = $('#poolsTabs'); tabs.innerHTML = '';
  const especiales = [{ id: '_consejo', nombre: 'Común del consejo', ico: 'libros' }, { id: '_general', nombre: 'General', ico: 'sesiones' }];
  for (const e of especiales) {
    const b = document.createElement('button'); b.className = 'especial' + (e.id === poolAg ? ' act' : '');
    b.innerHTML = `<span class="mini">${ico(e.ico)}</span>${e.nombre} <em>${(poolDatos[e.id] || []).length}</em>`;
    b.title = e.id === '_consejo' ? 'La consultan todos los expertos de este consejo' : 'La consultan todos los expertos de todos los consejos';
    b.onclick = () => { poolAg = e.id; pintarPools(); }; tabs.append(b);
  }
  tabs.insertAdjacentHTML('beforeend', '<span class="sep-tabs"></span>');
  for (const a of panel.agentes) {
    const b = document.createElement('button'); b.className = a.id === poolAg ? 'act' : '';
    b.innerHTML = `<span class="mini">${esc(monograma(a))}</span>${esc(a.nombre)} <em>${(poolDatos[a.id] || []).length}</em>`;
    b.onclick = () => { poolAg = a.id; pintarPools(); }; tabs.append(b);
  }
  const cuerpo = $('#poolsCuerpo');
  const a = poolAg === '_consejo' ? { id: '_consejo', nombre: panel.nombre, comun: true }
    : poolAg === '_general' ? { id: '_general', nombre: 'todos los consejos', general: true } : panel.agentes.find(x => x.id === poolAg);
  if (!a) { cuerpo.innerHTML = '<p class="nota">Este panel aún no tiene expertos.</p>'; return; }
  const titulo = a.comun ? `Biblioteca común · ${esc(a.nombre)}` : a.general ? 'Biblioteca general' : `Biblioteca de ${esc(a.nombre)}`;
  const quien = a.comun ? 'la consultarán todos los expertos de este consejo' : a.general ? 'la consultarán todos los expertos de todos los consejos'
    : 'solo los consultará este experto';
  cuerpo.innerHTML = `<div class="zona" id="zona"><div class="t1">${titulo}</div>
    <div class="t2">Arrastre aquí documentos PDF, DOCX, TXT, MD, ODT o RTF — ${quien}</div>
    <button id="subirPool" type="button" class="contorno">${ico('mas')}<span>Añadir documentos</span></button>
    <input id="filePool" type="file" multiple hidden accept=".pdf,.docx,.txt,.md,.odt,.rtf"></div><div id="listaDocs"></div>`;
  const zona = $('#zona');
  $('#subirPool').onclick = () => $('#filePool').click();
  $('#filePool').onchange = e => subirPool(e.target.files);
  zona.ondragover = e => { e.preventDefault(); e.stopPropagation(); zona.classList.add('sobre'); };
  zona.ondragleave = () => zona.classList.remove('sobre');
  zona.ondrop = e => { e.preventDefault(); e.stopPropagation(); zona.classList.remove('sobre'); subirPool(e.dataTransfer.files); };
  const lista = $('#listaDocs');
  for (const d of poolDatos[a.id] || []) {
    const el = document.createElement('div'); el.className = 'doc';
    const cls = d.estado === 'listo' ? 'listo' : d.estado === 'error' ? 'error' : 'vivo';
    const parado = d.estado === 'listo' || d.estado === 'error';
    el.innerHTML = `<div class="t">${ico('doc')}<b>${esc(d.nombre)}</b>
      <span class="estado ${cls}">${esc(d.estado === 'listo' ? d.capitulos + ' capítulos' : d.estado === 'error' ? 'Error' : d.paso || d.estado)}</span>
      ${d.capitulos ? `<button class="icono" data-a="indice" title="Índice de capítulos">${ico('indice')}</button>` : ''}
      ${parado ? `<button class="icono" data-a="re" title="Volver a procesar">${ico('repetir')}</button>` : ''}
      <button class="icono" data-a="del" title="Retirar de la biblioteca">${ico('papelera')}</button></div>
      ${d.error ? `<div class="err">${esc(d.error)}</div>` : ''}<div class="caps" hidden></div>`;
    el.querySelector('[data-a=del]').onclick = async () => {
      if (await confirmar(`¿Retirar «${d.nombre}» de la biblioteca de ${a.nombre}?`, 'Retirar')) { await api(`/api/docs/${d.id}`, { method: 'DELETE' }); cargarPools(); }
    };
    const re = el.querySelector('[data-a=re]');
    if (re) re.onclick = async () => { try { await api(`/api/docs/${d.id}/reprocesar`, { method: 'POST' }); } catch (e) { avisar(e.message, true); } cargarPools(); };
    const ix = el.querySelector('[data-a=indice]'); if (ix) ix.onclick = () => indice(d, el.querySelector('.caps'));
    if (abiertos.has(d.id)) indice(d, el.querySelector('.caps'), true);
    lista.append(el);
  }
  if (!(poolDatos[a.id] || []).length) lista.innerHTML = '<p class="nota" style="text-align:center">La biblioteca está vacía.</p>';
}
async function indice(d, caja, forzar) {
  if (!forzar && !caja.hidden) { caja.hidden = true; abiertos.delete(d.id); return; }
  abiertos.add(d.id); caja.hidden = false;
  const r = await api(`/api/docs/${d.id}/capitulos`);
  caja.innerHTML = r.capitulos.map(c => `<details data-id="${c.id}"><summary><span class="num">${c.orden}</span><span class="tt">${esc(c.titulo)}</span>
      <em>${c.n.toLocaleString('es')} car.${c.simplificado ? '' : ' · extracto'}</em></summary>
    <div class="res">${esc(c.resumen)}${c.claves ? `<i>${esc(c.claves)}</i>` : ''}</div><pre hidden></pre></details>`).join('');
  caja.querySelectorAll('details').forEach(x => x.ontoggle = async () => {
    const pre = x.querySelector('pre'); if (!x.open || pre.textContent) return;
    pre.textContent = (await api(`/api/capitulos/${x.dataset.id}`)).texto; pre.hidden = false;
  });
}
async function subirPool(files) {
  if (!files.length) return;
  const fd = new FormData(); [...files].forEach(f => fd.append('archivos', f));
  try { await api(`/api/paneles/${panel.id}/agentes/${poolAg}/docs`, { method: 'POST', body: fd }); avisar('Documentos recibidos. Procesando en la fábrica…'); }
  catch (e) { avisar(e.message, true); }
  cargarPools();
}
$('#abrirPools').onclick = abrirPools;
$('#cerrarPools').onclick = () => $('#pools').close();
$('#pools').onclose = () => clearTimeout(poolTimer);

// ---- editor de panel ----
const COLORES = ['#c9a96e', '#7f9cc9', '#8fb59a', '#c27c8e', '#a593c9', '#d1a173', '#7fb5b5', '#b5a77f'];
let editando = null;
// proveedores de IA para el editor (se cargan al abrirlo)
let provs = [], provDefecto = {};
async function cargarProveedores() {
  const r = await api('/api/proveedores').catch(() => null);
  if (r) { provs = r.proveedores; provDefecto = r.defecto; }
}
function opcionesProveedor(sel) {
  return `<option value="">IA por defecto${provDefecto.modelo ? ` (${esc(provDefecto.modelo)})` : ''}</option>`
    + provs.map(p => `<option value="${p.id}" ${p.id === sel ? 'selected' : ''}>${esc(p.nombre)}${p.modelo ? ` · ${esc(p.modelo)}` : ''}</option>`).join('');
}
function filaAgente(a = {}) {
  const d = document.createElement('div'); d.className = 'ag'; d.dataset.id = a.id || '';
  if (a.comite) { d.dataset.comite = a.comite; d.dataset.comiteId = a.comite_id || ''; }
  d.dataset.cap = a.capitulos || 0; d.dataset.nom = a.nombre || '';
  const c = a.color || COLORES[$('#listaAgentes').children.length % COLORES.length];
  const mono = /^[\p{L}]{1,3}$/u.test((a.emoji || '').trim()) ? a.emoji.trim() : '';
  d.innerHTML = `
    <div class="vista" style="--c:${c}"></div>
    <label class="fld">Nombre<input class="nombre" value="${esc(a.nombre || '')}" placeholder="Nombre"></label>
    <label class="fld">Especialidad<input class="rol" value="${esc(a.rol || '')}" placeholder="Rol en el consejo"></label>
    <label class="fld">Acento<input class="color" type="color" value="${c}"></label>
    <button type="button" class="icono" title="Retirar experto">${ico('x')}</button>
    <div class="fila2">
      <label class="fld">Monograma<input class="emoji" maxlength="3" value="${esc(mono)}" placeholder="Auto"></label>
      <label class="fld">Proveedor de IA<select class="proveedor">${opcionesProveedor(a.proveedor)}</select></label>
      <label class="fld">Modelo <small>— vacío: el del proveedor; para imágenes, uno con visión</small><input class="modelo" list="lista-modelos-${a.proveedor || 'def'}" value="${esc(a.modelo || '')}" placeholder="Modelo del proveedor"></label>
    </div>
    <label class="fld ancho">Instrucciones <small>— personalidad, especialidad y forma de responder</small><textarea class="instr" rows="2">${esc(a.instrucciones || '')}</textarea></label>`;
  const vista = () => {
    const v = d.querySelector('.vista'); v.style.setProperty('--c', d.querySelector('.color').value);
    v.textContent = monograma({ nombre: d.querySelector('.nombre').value || '?', emoji: d.querySelector('.emoji').value });
  };
  d.querySelectorAll('.nombre,.emoji,.color').forEach(i => i.addEventListener('input', vista)); vista();
  d.querySelector('.proveedor').onchange = e => d.querySelector('.modelo').setAttribute('list', `lista-modelos-${e.target.value || 'def'}`);
  d.querySelector('button').onclick = async () => {
    if (+d.dataset.cap && !await confirmar(`${d.dataset.nom} tiene ${d.dataset.cap} capítulos en su biblioteca; se eliminarán al guardar. ¿Retirarlo?`, 'Retirar')) return;
    d.remove();
  };
  $('#listaAgentes').append(d);
}
async function abrirEditor(p) {
  await cargarProveedores();
  editando = p; const f = $('#formEditor');
  $('#sobreEditor').textContent = p ? 'Configuración' : 'Nuevo';
  $('#tituloEditor').textContent = p ? p.nombre : 'Constituir un panel';
  f.nombre.value = p ? p.nombre : ''; f.descripcion.value = p ? p.descripcion : '';
  f.contexto.value = p ? p.contexto : 'Sois un consejo de expertos. Respondéis en español, de forma breve y desde vuestra especialidad.';
  $('#listaAgentes').innerHTML = '';
  (p ? p.agentes : [{}, {}, {}]).forEach(filaAgente);
  $('#eliminar').style.display = p ? '' : 'none';
  $('#editor').showModal();
}
$('#nuevo').onclick = () => abrirEditor(null);
$('#editar').onclick = () => panel && abrirEditor(panel);
$('#addAgente').onclick = () => { filaAgente(); $('#listaAgentes').lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); };
$('#cancelar').onclick = $('#cerrarEditor').onclick = () => $('#editor').close();
$('#eliminar').onclick = async () => {
  if (!await confirmar(`¿Eliminar «${editando.nombre}», sus actas y las bibliotecas de sus expertos?`, 'Eliminar')) return;
  await api(`/api/paneles/${editando.id}`, { method: 'DELETE' }); $('#editor').close(); cargar(); avisar('Panel eliminado.');
};
$('#formEditor').onsubmit = async e => {
  e.preventDefault(); const f = e.target;
  const agentes = [...$('#listaAgentes').children].map(d => ({
    id: d.dataset.id || undefined, emoji: d.querySelector('.emoji').value, nombre: d.querySelector('.nombre').value,
    rol: d.querySelector('.rol').value, color: d.querySelector('.color').value,
    instrucciones: d.querySelector('.instr').value, modelo: d.querySelector('.modelo').value,
    proveedor: d.querySelector('.proveedor').value, ...(d.dataset.comite ? { comite: d.dataset.comite, comite_id: d.dataset.comiteId } : {}) }));
  const cuerpo = JSON.stringify({ nombre: f.nombre.value, descripcion: f.descripcion.value, contexto: f.contexto.value, agentes });
  const h = { 'Content-Type': 'application/json' };
  try {
    const p = editando ? await api(`/api/paneles/${editando.id}`, { method: 'PUT', headers: h, body: cuerpo })
                       : await api('/api/paneles', { method: 'POST', headers: h, body: cuerpo });
    $('#editor').close(); ultimoPanel = null; await cargar(p.id); avisar(editando ? 'Panel actualizado.' : 'Panel constituido.');
  } catch (err) { avisar(err.message, true); }
};

new ResizeObserver(() => document.documentElement.style.setProperty('--chat-alto', $('#chat').offsetHeight + 'px')).observe($('#chat'));
let rz; window.addEventListener('resize', () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(pintarArco); });
hidratar();
if (innerWidth < 760) $('#texto').placeholder = 'Su consulta…';
cargar(localStorage.panel);
