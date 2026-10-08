// El Consejo — menú principal y ambientes: consulta de panel, Asamblea General y consulta individual (despacho).
const AMBIENTES = {
  panel: { fondo: 'sala', credito: ['Sala del Consejo de Seguridad de la ONU · Foto: Jdforrester, CC BY 4.0 (adaptada)',
    'https://commons.wikimedia.org/wiki/File:United_Nations_Headquarters_-_Security_Council_chamber,_straight-on_view.jpg'] },
  asamblea: { fondo: 'asamblea', credito: ['Salón de la Asamblea General de la ONU · Foto: Mojnsen, CC BY-SA 4.0 (adaptada)',
    'https://commons.wikimedia.org/wiki/File:United_Nations_General_Assembly_2024.jpg'] },
  individual: { fondo: 'despacho', credito: ['Vista de Manhattan al anochecer · Foto: John Dillenbeck, dominio público (composición propia)',
    'https://commons.wikimedia.org/wiki/File:NYC_Dusk.jpg'] },
};
AMBIENTES.inicio = AMBIENTES.asamblea;

function aplicarAmbiente() {
  for (const k of Object.keys(AMBIENTES)) document.body.classList.toggle('amb-' + k, k === ambiente);
  const [txt, url] = AMBIENTES[ambiente].credito;
  $('#credito').textContent = txt; $('#credito').href = url;
  $('#inicio').hidden = ambiente !== 'inicio';
}

async function irA(amb, opts = {}) {
  ambiente = amb; localStorage.ambiente = amb;
  abrirMenu(false);
  aplicarAmbiente();
  if (amb === 'inicio') { ultimoPanel = null; return pintarInicio(); }
  if (amb === 'individual') {
    if (opts.agente) { expertoInd = { panel: opts.panel, agente: opts.agente }; localStorage.expertoInd = JSON.stringify(expertoInd); }
    if (!expertoInd) { ambiente = 'inicio'; aplicarAmbiente(); pintarInicio(); return abrirSelectorExperto(); }
    ultimoPanel = null;
    return cargar(expertoInd.panel);
  }
  if (amb === 'asamblea') {
    const asam = paneles.find(p => p.tipo === 'asamblea');
    return cargar(asam && asam.id);
  }
  return cargar(opts.panel || localStorage.panel);
}

// ---- menú principal ----
async function pintarInicio() {
  if (!paneles.length) paneles = await api('/api/paneles');
  const abiertas = await api('/api/sesiones?estado=abierta').catch(() => []);
  const hora = new Date().getHours(), saludo = hora < 12 ? 'Buenos días' : hora < 19 ? 'Buenas tardes' : 'Buenas noches';
  const consejos = paneles.filter(p => p.tipo !== 'asamblea'), expertos = consejos.reduce((n, p) => n + p.agentes.length, 0);
  $('#inicio').innerHTML = `<div class="ini-cont">
    <div class="ini-cab">${ORNAMENTO}<div class="sobre">${saludo} · ${new Date().toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
      <h1>¿Cómo desea reunir al Consejo?</h1>
      <p>${consejos.length} consejos y ${expertos} expertos a su disposición.</p></div>
    <div class="ambientes">
      <button type="button" class="amb" data-amb="asamblea" style="--img:url(/static/asamblea.jpg)">
        <span class="sobre">Debate entre comités</span><b>Asamblea General</b>
        <em>Varios consejos debaten un asunto con derecho de palabra parlamentario, mociones y votación.</em></button>
      <button type="button" class="amb" data-amb="panel" style="--img:url(/static/sala.jpg)">
        <span class="sobre">Un consejo en sesión</span><b>Consulta de panel</b>
        <em>Un panel de expertos responde, delibera y vota un acuerdo sobre su consulta.</em></button>
      <button type="button" class="amb" data-amb="individual" style="--img:url(/static/despacho.jpg)">
        <span class="sobre">A solas, en su despacho</span><b>Consulta individual</b>
        <em>Una conversación privada con el experto que usted elija, de cualquier consejo.</em></button>
    </div>
    ${abiertas.length ? `<div class="ini-curso"><div class="sobre">Sesiones en curso</div>${abiertas.slice(0, 6).map(s => `
      <button type="button" class="curso" data-s="${s.id}" data-p="${s.panel_id}" data-i="${s.individual || ''}">
        <b>${esc(s.individual ? `${s.experto} · ${s.panel}` : s.panel)}</b><em>Sesión nº ${s.numero} · ${esc(s.asunto)}</em></button>`).join('')}</div>` : ''}
    <div class="accesos">
      <button type="button" data-a="asistente">${ico('asistente')}<b>Asistente</b><em>Cómo funciona, a quién consultar, ordenar su planteamiento</em></button>
      <button type="button" data-a="sesiones">${ico('sesiones')}<b>Sesiones</b><em>Registro y actas de cierre</em></button>
      <button type="button" data-a="bibliotecas">${ico('libros')}<b>Bibliotecas</b><em>Documentos de cada consejo y generales</em></button>
      <button type="button" data-a="estadisticas">${ico('grafico')}<b>Estadísticas</b><em>Actividad, acuerdos y gasto</em></button>
      <button type="button" data-a="ajustes">${ico('deslizadores')}<b>Ajustes</b><em>Acceso, membrete, proveedores y copias</em></button>
    </div></div>`;
  $('#inicio').querySelectorAll('[data-amb]').forEach(b => b.onclick = () => irA(b.dataset.amb));
  $('#inicio').querySelectorAll('.curso').forEach(b => b.onclick = () => {
    const p = paneles.find(x => x.id === b.dataset.p);
    if (b.dataset.i) irA('individual', { panel: b.dataset.p, agente: b.dataset.i });
    else irA(p && p.tipo === 'asamblea' ? 'asamblea' : 'panel', { panel: b.dataset.p });
  });
  const acc = { asistente: () => consAbrir(), sesiones: () => abrirRegistro(), estadisticas: () => abrirEstadisticas(), ajustes: () => abrirAjustes(),
    bibliotecas: async () => { if (!panel) await cargar(localStorage.panel); abrirPools(); } };
  $('#inicio').querySelectorAll('[data-a]').forEach(b => b.onclick = acc[b.dataset.a]);
}

// ---- selector de experto (consulta individual) ----
function abrirSelectorExperto() {
  $('#buscaExperto').value = ''; pintarExpertos(); $('#dlgExperto').showModal(); $('#buscaExperto').focus();
}
function pintarExpertos() {
  const q = $('#buscaExperto').value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const norm = t => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  $('#listaExpertos').innerHTML = paneles.filter(p => p.tipo !== 'asamblea').map(p => {
    const ags = p.agentes.filter(a => !q || norm(`${a.nombre} ${a.rol} ${p.nombre}`).includes(q));
    if (!ags.length) return '';
    return `<div class="grupo-exp"><div class="sobre">${esc(p.nombre)}</div><div class="exps">${ags.map(a => `
      <button type="button" class="exp" data-p="${p.id}" data-a="${a.id}" style="--c:${a.color}"><span class="mini">${esc(monograma(a))}</span>
        <span class="q"><b>${esc(a.nombre)}</b><em>${esc(a.rol)}</em></span></button>`).join('')}</div></div>`;
  }).join('') || '<p class="ayuda" style="text-align:center;padding:24px 0">Ningún experto coincide con la búsqueda.</p>';
  $('#listaExpertos').querySelectorAll('.exp').forEach(b => b.onclick = () => { $('#dlgExperto').close(); irA('individual', { panel: b.dataset.p, agente: b.dataset.a }); });
}
$('#buscaExperto').oninput = pintarExpertos;
$('#irInicio').onclick = () => irA('inicio');
document.querySelector('.marca').addEventListener('click', e => { e.preventDefault(); irA('inicio'); });

// arranque: el ambiente guardado (o el menú principal)
(async () => {
  paneles = await api('/api/paneles').catch(() => []);
  if (ambiente === 'individual' && !expertoInd) ambiente = 'inicio';
  irA(ambiente);
})();
