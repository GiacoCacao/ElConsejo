# El Consejo

Panel visual de **expertos (agentes IA)**. Cada panel reúne varios agentes colocados en arco, cada
uno con su nombre, rol e instrucciones; una barra de chat en el centro permite preguntarles a
todos a la vez. Se pueden adjuntar imágenes y documentos, activar un **diálogo** para que los
expertos repliquen entre sí y dar a cada agente su propia **biblioteca** (pool) de documentos.

## Qué hace

- **Paneles y agentes** configurables (nombre, rol, icono, color, instrucciones, modelo propio y contexto común).
- **Chat central**: la pregunta llega a todos los agentes en paralelo; se pulsa un agente para leer su respuesta.
- **Diálogo entre expertos** (conmutador, 1–3 réplicas): tras responder, cada agente lee lo que dijeron sus
  colegas y replica con su postura final.
- **Imágenes** (las ven los modelos con visión) y **documentos** (PDF, DOCX, TXT, MD, ODT, RTF) en el chat: el
  texto lo extrae la [fábrica de documentos](#fábrica) (con OCR si está escaneado) y se pasa a los agentes.
- **Pools por agente** (📚 Pools): cada documento subido a la biblioteca de un agente se envía a la fábrica,
  se **divide en capítulos**, se **simplifica** (resumen y palabras clave con IA), se **ordena** y se
  **indexa** (SQLite FTS5 + búsqueda semántica de la fábrica). Al responder, el agente recibe solo los
  capítulos pertinentes y cita de qué documento y capítulo sale cada dato.

## Menú principal y ambientes

Al entrar se abre el **menú principal** con los tres ambientes, cada uno con su sala:

- **Asamblea General** (salón de la Asamblea General de la ONU): debate entre comités.
- **Consulta de panel** (sala del Consejo de Seguridad): un consejo responde, delibera y vota.
- **Consulta individual** (despacho con vistas a Manhattan): a solas con el experto que se elija, de cualquier
  consejo; su sesión va aparte de la del panel.

Además, accesos al Asistente, Sesiones (con las que están en curso), Bibliotecas, Estadísticas y Ajustes.

## Asistente

Asesor interno fuera del hemiciclo (antes «Consultor general»). Conoce cómo funciona El Consejo y el catálogo de
paneles y expertos: explica el funcionamiento, **recomienda** ambiente, panel o expertos para un caso, **ordena el
planteamiento** antes de consultar (planteamiento reformulado, orden del día y recomendación, con un botón «Llevar al
Consejo» que abre el ambiente con todo preparado) y aclara términos seleccionados en cualquier respuesta o acta. Cada recomendación trae una **síntesis del caso** (con lo
hablado en la conversación) y el botón **«Iniciar sesión con esta síntesis»**: abre el ambiente, inicia la sesión con
su asunto y orden del día y plantea el caso, sin volver a escribirlo.

## Asamblea General

Consejo especial donde varios comités (los paneles) debaten un asunto. Al convocarla se eligen los comités
y sus delegados (por defecto, un portavoz), el **tiempo de palabra** y la modalidad de la ronda de posiciones.
Cada delegado conserva su configuración, su biblioteca y su proveedor de IA, y habla en nombre de su comité.

**Derecho de palabra parlamentario**: tras la ronda de posiciones, la presidencia gestiona una **lista de
oradores**: concede la palabra a quien quiera, abre el turno de **solicitudes** («¿quién pide la palabra?»:
cada delegado decide si tiene algo nuevo que aportar) y concede **réplicas por alusiones**, que se detectan
cuando un orador nombra a otro delegado o a su comité («el comité jurídico», «la delegación financiera»).
La votación y el acta funcionan como en cualquier consejo; el acta indica a qué comité representa cada delegado.

## Herramientas parlamentarias

- **Orden del día** con varios puntos (al iniciar la sesión o convocar la Asamblea): cada consulta y cada votación
  pertenecen a un punto; la presidencia pasa de uno a otro y el acta recoge un acuerdo por punto.
- **Lista de oradores persistente** (sobrevive a recargar la página). Las alusiones y las solicitudes se anotan solas.
- **Cuestiones de orden**: en el turno de solicitudes un delegado puede plantearla; pasa delante en la lista y su
  intervención se limita a señalar la infracción del procedimiento.
- **Mociones de procedimiento** que votan los delegados (mayoría simple): cierre del debate (abre la votación del
  acuerdo), pasar al siguiente punto, limitar el tiempo de palabra y cuarto intermedio.
- **Cronómetro de palabra** en vivo (palabras dichas frente al tiempo de palabra) y **retirar la palabra** a mitad
  de intervención. **Cuarto intermedio**: suspende las consultas hasta reanudar.

## Acta con membrete

El acta de cierre se descarga en **PDF** (ReportLab, con las tipografías de la marca incrustadas) y en **Word**
(python-docx): sello o logotipo propio, nombre de la institución y lema, cabecera y pie con «Página x de y», lugar y
fecha, y líneas de firma de la Presidencia y la Secretaría. Nombre, lema, ciudad, papel (carta o A4) y logotipo se
configuran en Ajustes.

## Bibliotecas

Cada experto consulta tres bibliotecas a la vez: la **propia**, la **común de su consejo** y la **general** de todos
los consejos (un delegado de la Asamblea, además, la común de su comité). Las fuentes citadas indican de cuál sale cada dato.

## Estadísticas

Sesiones, consultas, acuerdos adoptados y gasto; gasto por día o por mes; sesiones por consejo; resultado de las
votaciones; expertos con más intervenciones y más disidentes (votos contra el resultado final); gasto por modelo y por
consejo. Filtros por periodo y consejo, detalle al pasar el ratón y vista de tabla en cada gráfico.

## Consultas individuales y proveedores de IA

- **Pregunta directa** (en la sala): desde la ficha de un experto, la pregunta va a él en presencia del resto, que la
  oye y puede opinar después con «Que opine el consejo». La conversación privada es la consulta individual (despacho).
- **Proveedores de IA por experto**: en Ajustes se registran otras APIs compatibles con OpenAI (OpenAI,
  Anthropic, Gemini, Mistral, Groq, OpenRouter, xAI, Ollama…) con su clave, que se guarda cifrada con
  `CONSEJO_SECRETO` y no vuelve al navegador. Cada experto elige proveedor y modelo en Configurar. Si una API
  rechaza un parámetro (`stream_options`, `max_tokens`, `temperature`…), la llamada se adapta sola.

## Tiempo real y consultor general

- **Respuestas en tiempo real**: el texto de cada experto aparece mientras lo escribe (flujo de la API; el
  servidor reenvía los trozos como líneas JSON). Si la conexión se corta a mitad, se conserva lo dicho.
- **Consultor general**: asesor interno fuera del hemiciclo, en un panel lateral. Aclara palabras, conceptos,
  siglas y referencias (definición, sentido en el contexto, ejemplo, términos relacionados) sin opinar sobre el
  asunto. Se puede **seleccionar un término** en una respuesta, la transcripción o un acta y pulsar «Consultar».
  Su historial se guarda en el navegador; su gasto cuenta en el consumo del panel.

## Sesiones, votación y actas

- **Sesión**: cada asunto se trata en una sesión numerada por consejo (botón *Iniciar sesión*; si se consulta sin
  sesión, se abre una con la pregunta como asunto). Se fija el **orden del debate**: *por turnos* (cada experto
  interviene en su turno y oye a quienes hablaron antes) o *simultáneo*.
- **Deliberar acuerdo**: *acuerdo unificado* (la Secretaría —una IA neutral— redacta una propuesta que integra las
  posturas; se aprueba si nadie vota en contra y, si no, se revisa con las objeciones) o *mayoría simple* (la
  Secretaría identifica las alternativas del debate y gana la más votada; un empate lo decide el voto de calidad
  de la presidencia). Pantalla de votación con escaños, recuento y explicación de voto.
- **Acta de cierre**: los datos objetivos (asistentes, orden, consultas, votos, acuerdo literal) los compone el
  código; la IA solo redacta la síntesis del debate y las conclusiones, a partir de la transcripción. Se puede
  imprimir, descargar en Markdown y **llevar a otro consejo**: se anexa a su sesión abierta o abre una sesión
  para deliberarla. Las actas anexas llegan a los expertos como contexto.
- **Registro de sesiones** de todos los consejos, con estado, resultado y acceso al acta.

## Seguridad y administración (Ajustes)

- **Acceso**: con `CONSEJO_CLAVE_PRESIDENCIA` la sala pide clave (control total); `CONSEJO_CLAVE_OBSERVADOR` da acceso
  de solo lectura. Sesión de 30 días, cookie firmada con `CONSEJO_SECRETO`, bloqueo tras 5 intentos fallidos.
- **Tope de gasto** diario y mensual en dólares: *avisar* o *bloquear* las llamadas a la IA al alcanzarlo.
- **Copias de seguridad** diarias de la base de datos (copia en caliente de SQLite) en `datos/copias`, rotativas,
  descargables desde Ajustes.
- Los expertos y la Secretaría conocen la **fecha y hora actuales** y advierten cuando su información puede estar
  desactualizada.

## Consumo y costes

Una barra en la sala muestra el servicio y su franja tarifaria, el contexto usado (máximo de los
expertos en la última consulta), los tokens y el coste aproximado; al pulsarla se ve el detalle por
experto, por panel, por bibliotecas y global. El coste sale de los tokens que informa la API (`usage`)
y de la tabla de tarifas (USD por millón de tokens), que se puede editar y ampliar con otros modelos.
Las de DeepSeek vienen de serie, con su precio doble en hora punta (01–04 y 06–10 UTC, lunes a viernes).

**Base de tarifas actualizada**: al arrancar y cada 3 días se descargan los precios públicos de cientos de modelos
(OpenAI, Anthropic, Google, Mistral, xAI, DeepSeek… vía `openrouter.ai/api/v1/models`) para que cualquier proveedor
tenga coste. Los nombres se emparejan aunque el proveedor los escriba distinto (`claude-sonnet-5-5` =
`anthropic/claude-sonnet-5.5`, sufijos de fecha o `-latest`). Prioridad: tarifa **manual** > **oficial** de serie >
**base**; la actualización nunca pisa las dos primeras. Se puede forzar con «Actualizar tarifas» y buscar cualquier
modelo en el detalle de Consumo, donde cada experto muestra su proveedor y el precio que se le aplica.

## Paneles de serie

Se crean una sola vez al arrancar (`paneles_base.py`); si se borran, no vuelven: **Empresarial**,
**Marketing y Ventas**, **Técnico Moderno**, **Psicológico**, **Financiero**, **Filosófico** (con
materialismo filosófico y teología, entre otras escuelas) **Importaciones a Venezuela**, **Político**, **Militar**, **Internacionalistas y Diplomáticos**,
**Periodistas**, **Diseño Gráfico**, **Infraestructura IT**, **Electrónica**, **Electricidad**, **Jurídico** y **Científico**, con seis
expertos cada uno.

## Puesta en marcha

```bash
cp .env.ejemplo .env && chmod 600 .env     # rellena CONSEJO_IA_CLAVE y CONSEJO_FABRICA_URL
# edita TU_IP en docker-compose.ejemplo.yml
docker compose -f docker-compose.ejemplo.yml up -d --build
curl http://TU_IP:8190/salud
```

| Variable | Para qué |
|---|---|
| `CONSEJO_IA_URL` / `CONSEJO_IA_MODELO` / `CONSEJO_IA_CLAVE` / `CONSEJO_IA_PENSAR` | endpoint compatible con OpenAI. Por defecto `deepseek-flash` (con visión). `CONSEJO_IA_PENSAR=1` activa el razonamiento de DeepSeek |
| `CONSEJO_FABRICA_URL` / `CONSEJO_FABRICA_CLAVE` | fábrica de documentos (obligatoria para PDF/pools) |

## Fábrica

Los documentos se procesan con una *fábrica de documentos* externa que expone `POST /documentos`,
`GET /documentos/{id}`, `GET /documentos/{id}/texto`, `GET /buscar` y `DELETE /documentos/{id}`.
Sin ella, el chat y los pools funcionan con imágenes y texto, pero no con documentos.

## API (resumen)

`GET/POST /api/paneles` · `PUT/DELETE /api/paneles/<id>` · `GET/DELETE /api/paneles/<id>/mensajes` ·
`POST /api/paneles/<id>/preguntas` (multipart: `texto`, `imagenes`) ·
`POST /api/preguntas/<id>/agentes/<agente>?ronda=N` · `GET /api/paneles/<id>/pools` ·
`POST /api/paneles/<id>/agentes/<agente>/docs` · `GET /api/docs/<id>/capitulos` · `DELETE /api/docs/<id>`.

## Desarrollo

Flask + SQLite, interfaz sin build en `static/`. Pruebas con la fábrica y la IA simuladas:

```bash
pip install -r requirements.txt pytest && python -m pytest -q
```

No incluye autenticación: pensado para una red privada (p. ej. Tailscale).

## Créditos

- Asamblea General: *United Nations General Assembly 2024*, foto de
  [Mojnsen](https://commons.wikimedia.org/wiki/File:United_Nations_General_Assembly_2024.jpg),
  licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Adaptada (recortada, virada y oscurecida);
  `static/asamblea.jpg` se distribuye bajo la misma licencia.
- Despacho: composición propia sobre *NYC Dusk*, foto de John Dillenbeck
  ([Wikimedia Commons](https://commons.wikimedia.org/wiki/File:NYC_Dusk.jpg), dominio público).
- Fondo: *United Nations Headquarters — Security Council chamber, straight-on view*, foto de
  [Jdforrester](https://commons.wikimedia.org/wiki/File:United_Nations_Headquarters_-_Security_Council_chamber,_straight-on_view.jpg),
  licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Adaptada: recortada, virada a tonos cálidos y oscurecida.
- Tipografías Cormorant Garamond e Inter, SIL Open Font License 1.1 (`static/fuentes/LICENCIAS.txt`); las versiones
  TTF estáticas de `static/fuentes/ttf` (para el PDF) se derivan de ellas con fontTools.
