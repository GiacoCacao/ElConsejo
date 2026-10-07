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
  pintarAjustes(await datosAjustes());
}
async function datosAjustes() {
  const [d, p] = await Promise.all([api('/api/ajustes'), api('/api/proveedores')]);
  return { ...d, proveedores: p.proveedores, plantillas: p.plantillas, provDefecto: p.defecto };
}
const modelosProv = {};   // proveedor -> modelos que devolvió «Probar»
function datalistModelos(pid, lista) {
  let dl = document.getElementById('lista-modelos-' + pid);
  if (!dl) { dl = document.createElement('datalist'); dl.id = 'lista-modelos-' + pid; document.body.append(dl); }
  dl.innerHTML = lista.map(m => `<option value="${esc(m)}">`).join('');
}
function pintarProveedores(lista, plantillas, presi) {
  const box = $('#ajProvs'); if (!box) return;
  box.innerHTML = lista.length ? `<table class="tabla"><thead><tr><th>Proveedor</th><th>Modelo por defecto</th><th>Clave</th><th></th></tr></thead><tbody>${lista.map(p => `
      <tr data-id="${p.id}"><td><b>${esc(p.nombre)}</b><small>${esc(p.url)}</small></td><td>${esc(p.modelo || '—')}</td>
      <td>${p.clave_ilegible ? '<span class="aviso-ins">Vuelva a escribirla</span>' : esc(p.clave || 'sin clave')}</td>
      <td class="acc">${presi ? `<button type="button" class="enlace peq" data-probar>${ico('repetir')}<span>Probar</span></button>
        <button type="button" class="enlace peq" data-editar>Editar</button>
        <button type="button" class="icono" data-borrar title="Eliminar">${ico('papelera')}</button>` : ''}</td></tr>
      <tr class="det-prov" hidden><td colspan="4"></td></tr>`).join('')}</tbody></table>`
    : '<p class="ayuda">No hay proveedores adicionales: todos los expertos usan la IA por defecto.</p>';
  box.querySelectorAll('tr[data-id]').forEach(tr => {
    const p = lista.find(x => x.id === tr.dataset.id), det = tr.nextElementSibling;
    const on = (sel, fn) => { const el = tr.querySelector(sel); if (el) el.onclick = fn; };
    on('[data-probar]', async () => {
      det.hidden = false; det.firstElementChild.innerHTML = '<span class="ayuda">Probando la conexión…</span>';
      try {
        const r = await api(`/api/proveedores/${p.id}/probar`, { method: 'POST' });
        modelosProv[p.id] = r.modelos; datalistModelos(p.id, r.modelos);
        det.firstElementChild.innerHTML = `<span class="ok-ins">Conexión correcta · ${r.modelos.length} modelos disponibles</span>
          <div class="modelos">${r.modelos.slice(0, 60).map(m => `<code>${esc(m)}</code>`).join(' ')}</div>`;
      } catch (e) { det.firstElementChild.innerHTML = `<span class="aviso-ins">${esc(e.message)}</span>`; }
    });
    on('[data-editar]', () => formProveedor(p, plantillas));
    on('[data-borrar]', async () => {
      if (!await confirmar(`¿Eliminar el proveedor ${p.nombre}?`, 'Eliminar')) return;
      try { await api(`/api/proveedores/${p.id}`, { method: 'DELETE' }); pintarAjustes(await datosAjustes()); }
      catch (e) { avisar(e.message, true); }
    });
  });
}
function formProveedor(p, plantillas) {
  const box = $('#ajProvs');
  const f = document.createElement('div'); f.className = 'form-prov';
  f.innerHTML = `<div class="sobre">${p ? 'Editar proveedor' : 'Nuevo proveedor'}</div>
    ${p ? '' : `<label class="fld">Plantilla<select data-k="plantilla"><option value="">Elegir…</option>${plantillas.map((t, i) => `<option value="${i}">${esc(t.nombre)}</option>`).join('')}</select></label>`}
    <div class="rejilla3">
      <label class="fld">Nombre<input data-k="nombre" value="${esc(p ? p.nombre : '')}" placeholder="OpenAI"></label>
      <label class="fld">Dirección (base de la API)<input data-k="url" value="${esc(p ? p.url : '')}" placeholder="https://api.openai.com/v1"></label>
      <label class="fld">Modelo por defecto<input data-k="modelo" value="${esc(p ? p.modelo : '')}" placeholder="nombre-del-modelo"></label>
    </div>
    <label class="fld">Clave de la API <small>— ${p ? 'déjela vacía para conservar la actual' : 'se guarda cifrada'}</small><input data-k="clave" type="password" autocomplete="new-password" placeholder="${p ? 'sin cambios' : 'sk-…'}"></label>
    <div class="botones"><span class="grow"></span><button type="button" class="enlace" data-c>Cancelar</button>
      <button type="button" class="dorado" data-g><span class="etq">Guardar proveedor</span></button></div>`;
  box.prepend(f);
  const v = k => f.querySelector(`[data-k=${k}]`);
  if (!p) v('plantilla').onchange = e => { const t = plantillas[e.target.value]; if (t) { v('nombre').value = t.nombre; v('url').value = t.url; } };
  f.querySelector('[data-c]').onclick = () => f.remove();
  f.querySelector('[data-g]').onclick = async () => {
    const cuerpo = { nombre: v('nombre').value, url: v('url').value, modelo: v('modelo').value, clave: v('clave').value };
    try {
      await api(p ? `/api/proveedores/${p.id}` : '/api/proveedores', { method: p ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
      avisar(`Proveedor ${cuerpo.nombre} guardado. Asígnelo a los expertos en Configurar.`); pintarAjustes(await datosAjustes());
    } catch (e) { avisar(e.message, true); }
  };
  v(p ? 'nombre' : 'plantilla').focus();
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
      <h3 class="sub">Proveedores de IA <small class="nota peq" style="margin:0">APIs compatibles con OpenAI; se asignan a cada experto en Configurar</small><span class="grow"></span>
        ${presi ? `<button type="button" class="contorno" id="ajNuevoProv">${ico('mas')}<span>Añadir proveedor</span></button>` : ''}</h3>
      <p class="nota peq" style="margin:0 0 10px">IA por defecto: <b>${esc(d.provDefecto.modelo || '—')}</b> en ${esc(d.provDefecto.url || '—')} (del .env).
        Las claves se guardan cifradas y nunca se muestran completas.</p>
      <div id="ajProvs"></div>
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
  pintarProveedores(d.proveedores, d.plantillas, presi);
  const on = (id, fn) => { const el = $('#' + id); if (el) el.onclick = fn; };
  on('ajNuevoProv', () => formProveedor(null, d.plantillas));
  on('ajGuardarGasto', async () => {
    try {
      await api('/api/ajustes/gasto', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ diario: $('#ajDiario').value.trim(), mensual: $('#ajMensual').value.trim(), modo }) });
      avisoTope = false; avisar('Tope de gasto guardado.'); pintarAjustes(await datosAjustes()); cargarConsumo();
    } catch (e) { avisar(e.message, true); }
  });
  on('ajCopiar', async () => {
    try { const r = await api('/api/copias', { method: 'POST' }); avisar(`Copia ${r.nombre} creada.`); pintarAjustes(await datosAjustes()); }
    catch (e) { avisar(e.message, true); }
  });
  on('ajSalir', async () => { await fetch('/api/acceso', { method: 'DELETE' }); location.href = '/login'; });
}
$('#abrirAjustes').onclick = abrirAjustes;
cargarAcceso();
