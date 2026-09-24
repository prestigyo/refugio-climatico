/**
 * Registro de búsquedas del buscador de nochetropical.es
 * ---------------------------------------------------------------------------
 * Despliegue: Extensiones → Apps Script en una hoja de cálculo nueva, pegar
 * esto, Implementar → Nueva implementación → Aplicación web, con acceso
 * "Cualquier usuario". La URL /exec que devuelve va en APPS_SCRIPT_BUSCA_URL
 * dentro de generar_calculadora.py.
 *
 * QUÉ SE GUARDA, y por qué solo esto
 * ---------------------------------------------------------------------------
 * Tres columnas: fecha (día, SIN hora), consulta y número de resultados; más
 * un contador que agrega las repeticiones del mismo término el mismo día.
 *
 * No se guarda —ni llega hasta aquí— IP, cookie, identificador de sesión o de
 * usuario, huella del navegador, user-agent, referer, hora exacta ni
 * ubicación. Sin ninguno de esos campos NO SE PUEDE saber que dos búsquedas
 * vienen de la misma persona, que es justamente el punto: esto mide qué busca
 * la gente, no quién.
 *
 * La agregación por (día, consulta) no es solo para ahorrar filas: al no haber
 * una fila por evento, tampoco queda el orden en que se tecleó nada.
 */

var HOJA = "busquedas";

// Longitudes: por debajo no informa, por encima suele ser un pegote accidental
// (una ruta de fichero, un párrafo copiado) más que una búsqueda.
var MIN_LARGO = 2;
var MAX_LARGO = 80;

// Aunque no guardemos identificadores, la gente teclea cosas en un buscador.
// Lo que huela a dato personal se descarta antes de escribir nada.
var PERSONALES = [
  /[\w.+-]+@[\w-]+\.[\w.]+/,            // correo
  /\b(?:\+?\d[ .-]?){9,}\b/,            // teléfono / número largo
  /\b\d{8}[ -]?[A-Za-z]\b/,             // DNI
  /\b[A-Za-z][ -]?\d{7}[ -]?[A-Za-z]\b/ // NIE
];

function doPost(e) {
  var out;
  try {
    out = registrarBusqueda(JSON.parse(e.postData.contents));
  } catch (err) {
    out = { ok: false, error: String(err) };
  }
  return ContentService.createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

function registrarBusqueda(p) {
  var q = String(p.q == null ? "" : p.q).trim().toLowerCase();
  q = q.replace(/\s+/g, " ");
  if (q.length < MIN_LARGO || q.length > MAX_LARGO) return { ok: false, error: "largo" };
  for (var i = 0; i < PERSONALES.length; i++) {
    if (PERSONALES[i].test(q)) return { ok: false, error: "descartada" };
  }

  var n = parseInt(p.n, 10);
  if (isNaN(n) || n < 0) n = 0;
  // Tres orígenes: el buscador español, su gemelo inglés (/en/search/) y el
  // rescate de la página 404. Cualquier otro valor cae en "buscar", así que
  // una versión antigua de este script sigue funcionando: las búsquedas en
  // inglés se guardarían como "buscar" en vez de perderse.
  var donde = (p.o === "404") ? "404" : (p.o === "en" ? "en" : "buscar");

  // Fecha en día, sin hora: la hora exacta permitiría ordenar eventos y con eso
  // reconstruir sesiones. El día basta para ver tendencias.
  var hoy = Utilities.formatDate(new Date(), "Europe/Madrid", "yyyy-MM-dd");

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);          // dos visitantes a la vez no deben pisarse
  try {
    var hoja = hojaBusquedas_();
    var datos = hoja.getDataRange().getValues();
    for (var f = 1; f < datos.length; f++) {
      if (datos[f][0] === hoy && datos[f][1] === q && datos[f][3] === donde) {
        hoja.getRange(f + 1, 3).setValue(n);              // resultados actuales
        hoja.getRange(f + 1, 5).setValue(datos[f][4] + 1); // veces
        return { ok: true, agregada: true };
      }
    }
    hoja.appendRow([hoy, q, n, donde, 1]);
    return { ok: true, agregada: false };
  } finally {
    lock.releaseLock();
  }
}

function hojaBusquedas_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var hoja = ss.getSheetByName(HOJA);
  if (!hoja) {
    hoja = ss.insertSheet(HOJA);
    hoja.appendRow(["fecha", "consulta", "resultados", "origen", "veces"]);
    hoja.setFrozenRows(1);
  }
  return hoja;
}

/**
 * Menú «Búsquedas» en la hoja, con lo que de verdad se quiere mirar:
 * qué se busca y no se encuentra.
 */
function onOpen() {
  SpreadsheetApp.getUi().createMenu("Búsquedas")
    .addItem("Sin resultados (lo que falta en la web)", "informeSinResultados")
    .addItem("Más buscadas", "informeMasBuscadas")
    .addToUi();
}

function informeSinResultados() { informe_(true); }
function informeMasBuscadas()   { informe_(false); }

function informe_(soloVacias) {
  var datos = hojaBusquedas_().getDataRange().getValues().slice(1);
  var acc = {};
  datos.forEach(function (r) {
    if (soloVacias && r[2] !== 0) return;
    acc[r[1]] = (acc[r[1]] || 0) + (r[4] || 1);
  });
  var filas = Object.keys(acc).map(function (k) { return [k, acc[k]]; })
                    .sort(function (a, b) { return b[1] - a[1]; });
  var nombre = soloVacias ? "sin-resultados" : "mas-buscadas";
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var h = ss.getSheetByName(nombre) || ss.insertSheet(nombre);
  h.clear();
  h.appendRow(["consulta", "veces"]);
  if (filas.length) h.getRange(2, 1, filas.length, 2).setValues(filas);
  h.setFrozenRows(1);
  ss.setActiveSheet(h);
}
