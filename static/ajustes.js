// El Consejo — ajustes: acceso (roles), tope de gasto y copias de seguridad.
let rol = 'presidencia';
async function cargarAcceso() {
  const a = await api('/api/acceso').catch(() => null);
  if (!a) return;
  rol = a.rol || 'presidencia';
  document.body.classList.toggle('observador', rol === 'observador');
}
const kb = n => n < 1048576 ? nf(n / 1024, 0) + ' KB' : nf(n / 1048576, 1) + ' MB';
async function abrirAjustes() {
  $('#dlgAjustes').showModal();
  $('#ajustesCuerpo').innerHTML = '<div class="v-espera"><span class="puntos"><i></i><i></i><i></i></span>Cargando…</div>';
  pintarAjustes(await api('/api/ajustes'));
}
function pintarAjustes(d) {
  const g = d.gasto, presi = d.rol === 'presidencia';
  const pct = (v, l) => l ? Math.min(100, 100 * v / l) : 0;
  const medidor = (v, l) => l ? `<span class="medidor ${v >= l ? 'alto' : ''}" style="width:100%"><i style="width:${Math.max(1.5, pct(v, l))}%"></i></span>` : '';
  $('#ajustesCuerpo').innerHTML = `
    <section class="aj">
      <h3 class="sub">Acceso</h3>
      ${d.protegido
        ? `<p class="nota peq" style="margin:0 0 12px">Ha entrado como <b>${d.rol === 'presidencia' ? 'presidencia' : 'observador (solo lectura)'}</b>. La sesión dura 30 días en este navegador.
            ${d.observador ? 'Hay una clave de observador configurada.' : 'No hay clave de observador: puede añadirla en el .env (CONSEJO_CLAVE_OBSERVADOR).'}</p>
           <button type="button" class="contorno" id="ajSalir">${ico('salir')}<span>Cerrar sesión</span></button>`
        : `<p class="nota aviso" style="margin:0">El acceso está abierto a toda la red. Para protegerlo, defina CONSEJO_CLAVE_PRESIDENCIA en el .env del despliegue y reinicie.</p>`}
    </section>
    <section class="aj">
      <h3 class="sub">Tope de gasto <small class="nota peq" style="margin:0">en dólares, según las tarifas de Consumo</small></h3>
      <div class="tiles dos">
        <div class="tile"><div class="rot">Hoy</div><div class="cifra">${fUSD(g.hoy)}</div>${medidor(g.hoy, g.diario)}<div class="det">${g.diario != null ? `de un tope de ${fUSD(g.diario)}` : 'Sin tope diario'}</div></div>
        <div class="tile"><div class="rot">Este mes</div><div class="cifra">${fUSD(g.mes)}</div>${medidor(g.mes, g.mensual)}<div class="det">${g.mensual != null ? `de un tope de ${fUSD(g.mensual)}` : 'Sin tope mensual'}</div></div>
      </div>
      ${g.excedido ? `<p class="nota aviso">Se ha alcanzado el tope ${g.excedido}${g.modo === 'bloquear' ? ': las consultas están bloqueadas hasta que lo suba o cambie de periodo.' : '.'}</p>` : ''}
      <div class="rejilla3">
        <label class="fld">Tope diario (US$)<input id="ajDiario" inputmode="decimal" placeholder="Sin tope" value="${g.diario ?? ''}" ${presi ? '' : 'disabled'}></label>
        <label class="fld">Tope mensual (US$)<input id="ajMensual" inputmode="decimal" placeholder="Sin tope" value="${g.mensual ?? ''}" ${presi ? '' : 'disabled'}></label>
        <div class="fld">Al alcanzarlo
          <div class="segmentos grande" id="ajModo"><button type="button" data-m="avisar">Avisar</button><button type="button" data-m="bloquear">Bloquear consultas</button></div></div>
      </div>
      ${presi ? `<button type="button" class="dorado" id="ajGuardarGasto"><span class="etq">Guardar tope</span></button>` : ''}
    </section>
    <section class="aj">
      <h3 class="sub">Copias de seguridad <small class="nota peq" style="margin:0">una al día, se guardan las ${d.copias_guardar} más recientes</small><span class="grow"></span>
        ${presi ? `<button type="button" class="contorno" id="ajCopiar">${ico('descargar')}<span>Hacer copia ahora</span></button>` : ''}</h3>
      <p class="nota peq" style="margin:0 0 10px">Incluyen paneles, sesiones, actas, votaciones, bibliotecas (capítulos) y consumo. Los documentos originales los custodia la fábrica.</p>
      ${d.copias.length ? `<table class="tabla"><thead><tr><th>Copia</th><th>Fecha</th><th>Tamaño</th><th></th></tr></thead><tbody>${d.copias.map(c => `
        <tr><td>${esc(c.nombre)}</td><td>${fechaHora(c.ts)}</td><td>${kb(c.tamano)}</td>
        <td>${presi ? `<a class="enlace peq" href="/api/copias/${encodeURIComponent(c.nombre)}" download>${ico('descargar')}<span>Descargar</span></a>` : ''}</td></tr>`).join('')}</tbody></table>`
        : '<p class="ayuda">Aún no hay copias. La primera se hace al arrancar el servicio.</p>'}
    </section>`;
  let modo = g.modo || 'avisar';
  const pintaModo = () => $('#ajModo').querySelectorAll('[data-m]').forEach(b => b.classList.toggle('act', b.dataset.m === modo));
  pintaModo();
  if (presi) $('#ajModo').querySelectorAll('[data-m]').forEach(b => b.onclick = () => { modo = b.dataset.m; pintaModo(); });
  const on = (id, fn) => { const el = $('#' + id); if (el) el.onclick = fn; };
  on('ajGuardarGasto', async () => {
    try {
      await api('/api/ajustes/gasto', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ diario: $('#ajDiario').value.trim(), mensual: $('#ajMensual').value.trim(), modo }) });
      avisoTope = false; avisar('Tope de gasto guardado.'); pintarAjustes(await api('/api/ajustes')); cargarConsumo();
    } catch (e) { avisar(e.message, true); }
  });
  on('ajCopiar', async () => {
    try { const r = await api('/api/copias', { method: 'POST' }); avisar(`Copia ${r.nombre} creada.`); pintarAjustes(await api('/api/ajustes')); }
    catch (e) { avisar(e.message, true); }
  });
  on('ajSalir', async () => { await fetch('/api/acceso', { method: 'DELETE' }); location.href = '/login'; });
}
$('#abrirAjustes').onclick = abrirAjustes;
cargarAcceso();
