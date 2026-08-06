/**
 * Buzón del OBSERVATORIO DEL DESCANSO — Google Apps Script.
 *
 * Recibe las noches anónimas enviadas desde
 * https://nochetropical.es/observatorio-del-descanso/ y sirve los agregados
 * por zona y el nacional. A diferencia del Confortómetro (que mide la
 * SENSACIÓN térmica del momento), aquí se mide el DESCANSO: cómo se ha
 * dormido, cómo se ha despertado y cuánta deuda de sueño se arrastra — y se
 * contrasta con el dato de AEMET de la zona y, si el usuario lo aporta, con lo
 * que marcó su pulsera o reloj.
 *
 * CÓMO DESPLEGARLO (5 minutos):
 *  1. Crea una hoja de cálculo de Google nueva (p. ej. "observatorio").
 *  2. Extensiones → Apps Script → borra el contenido y pega este fichero.
 *  3. Cambia SAL por una cadena cualquiera larga (y no la publiques).
 *  4. Desplegar → Nueva implementación → tipo "Aplicación web":
 *       - Ejecutar como: TÚ.
 *       - Quién tiene acceso: CUALQUIER USUARIO.
 *  5. Copia la URL /exec y pégala en APPS_SCRIPT_OBS_URL de
 *     scripts/generar_calculadora.py. Al regenerar la web, el Observatorio
 *     sale del modo demostración y empieza a guardar noches.
 *
 * PRIVACIDAD: aquí NUNCA llegan coordenadas (el navegador ya convirtió la
 * ubicación en zona = indicativo de estación AEMET). El identificador de
 * dispositivo se guarda como hash con sal, no en claro. No se guarda IP ni
 * user-agent (Apps Script ni siquiera los expone). Los datos de pulsera son
 * OPCIONALES y los teclea el propio usuario: no conectamos con ninguna cuenta.
 *
 * NOCHES APARTADAS (columnas "corregida" y "apartada"): quien duerme en la
 * sierra y vota a mediodía desde la ciudad contaría una noche buenísima en el
 * sitio equivocado. La web lo detecta antes de enviar y pregunta por el SITIO,
 * no por el voto: si corrige el pueblo, la noche llega ya re-anclada (mc=1) y
 * es una noche normal; si confirma que durmió donde dice el móvil, llega
 * marcada (q=1) y se guarda APARTE de los agregados. No se borra: si ese
 * pueblo acumula noches apartadas parecidas desde varios dispositivos, deja de
 * ser un despiste y pasa a ser un microclima —una isla— y entra sola en el
 * cálculo. Ver poblacionesRespaldadas_().
 */

var HOJA = "noches";
var SAL = "cambia-esta-sal-por-otra-cualquiera"; // p. ej. un UUID; no la publiques
var TMIN_URL = "https://nochetropical.es/datos/tmin-zonas.json";

// Una noche por dispositivo y ventana (8 h): dormir se vota una vez al día.
var VENTANA_S = 8 * 3600;

// --- Rehabilitación de noches apartadas -------------------------------------
// Una noche apartada vuelve al cálculo cuando su población acumula un patrón,
// no una anécdota. Se miran DÍAS_RESPALDO días (una isla es una propiedad del
// sitio, no de una noche) y se exigen MIN_RESPALDO dispositivos DISTINTOS: una
// persona sola votando cada noche no puede fabricar una isla. Además, sus
// índices tienen que parecerse entre sí (DISPERSION_RESPALDO): si un pueblo
// acumula noches apartadas que se contradicen, eso es ruido, no un refugio.
var DIAS_RESPALDO = 30;
var MIN_RESPALDO = 3;
var DISPERSION_RESPALDO = 2.5;
// Al rehabilitarla, su peso por desvío sería 0,1 y contaría como si no
// estuviera. Se le pone un suelo: ya no es un voto sospechoso.
var PESO_MIN_RESPALDADA = 0.6;

// Apartar también las noches que se desvían muchísimo aunque el navegador no
// las marque (páginas cacheadas de antes de la comprobación). Desactivado por
// defecto: esas noches ya pesan 0,1 por desvío, y activarlo vaciaría el mapa
// justo ahora que arranca. 3,1 puntos = los 6 °C del umbral de la web.
var APARTAR_POR_DESVIO = false;
var UMBRAL_APARTAR = 3.1;

// ---------------------------------------------------------------------------
// Recepción de noches
// ---------------------------------------------------------------------------
function doPost(e) {
  var out;
  try {
    out = registrarNoche(JSON.parse(e.postData.contents));
  } catch (err) {
    out = { ok: false, error: String(err) };
  }
  return salidaJson_(out);
}

function registrarNoche(p) {
  // Payload {z, d, c, r, w, k, u, sd, wh, ws, g, m, mn, mp, mc, q, v}
  var zona = String(p.z || "").trim();
  if (!/^[0-9A-Z]{4,7}$/.test(zona)) return { ok: false, error: "zona" };

  // Las cinco respuestas del flujo, en escala 1-5 (1 = pésimo, 5 = óptimo).
  var dormir = ent1a5_(p.d);        // ¿cómo has dormido?
  var confort = ent1a5_(p.c);       // ¿cómo se está ahora?
  var recurso = ent1a5_(p.r);       // qué has necesitado (nada .. aire acond.)
  var despertar = ent1a5_(p.w);     // ¿cómo te has despertado?
  var repetir = ent1a5_(p.k);       // ¿volverías a dormir aquí?
  if (dormir === "" || despertar === "") return { ok: false, error: "incompleto" };

  // Deuda de sueño declarada: 1 = a cero, 5 = arrastro muchísima.
  var deuda = ent1a5_(p.sd);

  // Datos OPCIONALES de pulsera/reloj (los teclea el usuario). OJO: el campo
  // vacío NO es un cero — Number("") da 0 y colaba ceros que hundían las medias.
  // Solo se guarda lo que venga como número de verdad y con sentido.
  var wh = "";                                            // horas dormidas
  if (p.wh !== "" && p.wh !== null && p.wh !== undefined && isFinite(Number(p.wh))) {
    var whn = Number(p.wh);
    if (whn > 0 && whn <= 16) wh = Math.round(whn * 10) / 10;
  }
  var ws = "";                                            // puntuación de sueño 1-100
  if (p.ws !== "" && p.ws !== null && p.ws !== undefined && isFinite(Number(p.ws))) {
    var wsn = Number(p.ws);
    if (wsn > 0 && wsn <= 100) ws = Math.round(wsn);
  }

  // Índice de descanso 0-10: dormir pesa más que el despertar.
  var indice = ((dormir - 1) / 4 * 10) * 0.6 + ((despertar - 1) / 4 * 10) * 0.4;
  indice = Math.round(indice * 10) / 10;

  // Celda ~1 km, YA redondeada por el navegador a 2 decimales. Si la noche
  // viene re-anclada a mano (corregida), esta celda es donde estaba el MÓVIL al
  // votar, que puede caer a 300 km de la zona: es correcto y no es sospechoso.
  var celda = String(p.g || "").trim();
  if (!/^-?\d{1,2}\.\d{2},-?\d{1,2}\.\d{2}$/.test(celda)) celda = "";

  // POBLACIÓN donde se durmió: la detecta sola el navegador (la más cercana de
  // docs/datos/lugares.json) y es lo que da nombre a la noche — quien duerme en
  // Dénia se guarda como Dénia, aunque su referencia climática sea la estación
  // de Pego. Nunca es texto libre: el id es el slug del propio fichero, así que
  // se valida como tal y el nombre se recorta.
  var munId = String(p.m || "").trim().toLowerCase();
  if (!/^[a-z0-9-]{2,40}$/.test(munId)) munId = "";
  var munNom = munId ? String(p.mn || "").trim().slice(0, 60) : "";
  // Corrección tecleada por quien vota cuando no acertamos la población (o no
  // la detectamos). Se guarda para REVISARLA a mano y, si procede, añadir el
  // lugar a datos/lugares.csv. NO se publica: al ser texto libre no puede
  // entrar sin filtro en un mapa público.
  var munProp = String(p.mp || "").trim().slice(0, 60).replace(/[<>]/g, "");
  // La población venía corregida a mano y la web la reconoció: la zona, el
  // valor esperado y el nombre son ya los del pueblo corregido, no los del GPS.
  var corregida = Number(p.mc) === 1 ? 1 : "";

  // Una noche por dispositivo y ventana de 8 h.
  var uidHash = hash_(String(p.u || "anon"));
  var cache = CacheService.getScriptCache();
  if (cache.get("n_" + uidHash)) return { ok: false, error: "ritmo" };

  // Coherencia con AEMET: el descanso ESPERADO según la mínima de la zona,
  // corregido si durmió con aire acondicionado (rompe el vínculo con el clima).
  var ref = refZona_(zona);
  var esperado = "", desvio = "", peso = 1;
  if (ref !== null) {
    esperado = descansoEsperado_(ref);
    if (recurso === 1) esperado = Math.max(esperado, 7);   // aire acondicionado
    else if (recurso === 3) esperado += 0.5;               // ventilador
    esperado = Math.max(0, Math.min(10, Math.round(esperado * 10) / 10));
    desvio = Math.round(Math.abs(indice - esperado) * 10) / 10;
    peso = desvio <= 2.5 ? 1 : desvio <= 4 ? 0.6 : desvio <= 6 ? 0.3 : 0.1;
    peso = peso * reputacion_(uidHash, desvio);
    peso = Math.round(peso * 1000) / 1000;
  }

  // Noche APARTADA: el navegador preguntó por el sitio y quien vota confirmó
  // que durmió ahí. Se guarda entera, pero fuera de los agregados hasta que
  // otras noches de esa población la respalden.
  var apartada = Number(p.q) === 1 ? 1 : "";
  if (!apartada && APARTAR_POR_DESVIO && desvio !== "" && desvio >= UMBRAL_APARTAR) {
    apartada = 1;
  }

  hoja_().appendRow([new Date(), zona, indice, dormir, confort, recurso,
                     despertar, repetir, deuda, wh, ws, uidHash,
                     ref === null ? "" : ref, esperado, desvio, peso, celda,
                     munId, munNom, munProp, corregida, apartada]);
  cache.put("n_" + uidHash, "1", VENTANA_S);
  return { ok: true, indice: indice, esperado: esperado,
           apartada: apartada === 1 };
}

// ---------------------------------------------------------------------------
// Agregados (GET ?zona=INDICATIVO | ?global=1 | ?global=1&apartadas=1)
// Caché de 5 minutos (30 min la lista de poblaciones respaldadas)
// ---------------------------------------------------------------------------
function doGet(e) {
  var par = e.parameter || {};
  if (par.global !== undefined) {
    if (par.apartadas !== undefined) return salidaJson_(aggApartadas_());
    return salidaJson_(aggGlobal_());
  }
  var zona = String(par.zona || "").trim();
  if (!/^[0-9A-Z]{4,7}$/.test(zona)) return salidaJson_({ ok: false, error: "zona" });

  var cache = CacheService.getScriptCache();
  var hit = cache.get("agg2_" + zona);
  if (hit) return salidaJson_(JSON.parse(hit));

  var resp = poblacionesRespaldadas_();
  var desde = Date.now() - 24 * 3600e3;
  var filas = hoja_().getDataRange().getValues();
  var idx = [], nDeuda = 0, sumDeuda = 0, nRel = 0, sumWs = 0, sumWh = 0, nAp = 0;
  for (var i = 1; i < filas.length; i++) {
    var f = filas[i];
    if (f[1] !== zona || new Date(f[0]).getTime() < desde) continue;
    var pu = pesoUtil_(f, resp);
    if (pu === null) { nAp++; continue; }   // apartada y todavía sin respaldo
    idx.push([Number(f[2]), pu]);
    if (f[8] !== "" && f[8] !== null) { nDeuda++; sumDeuda += Number(f[8]); }
    if (f[10] !== "" && f[10] !== null) { nRel++; sumWs += Number(f[10]); sumWh += Number(f[9]) || 0; }
  }
  var out = { ok: true, zona: zona, n: idx.length, apartadas: nAp };
  if (idx.length >= 5) {
    out.indice = Math.round(medianaPonderada_(idx) * 10) / 10;
    out.deuda_media = nDeuda >= 3 ? Math.round(sumDeuda / nDeuda * 10) / 10 : null;
    // Contraste con wearables: solo se publica con 3+ noches con dato.
    out.reloj_score = nRel >= 3 ? Math.round(sumWs / nRel) : null;
    out.reloj_horas = nRel >= 3 ? Math.round(sumWh / nRel * 10) / 10 : null;
  }
  cache.put("agg2_" + zona, JSON.stringify(out), 300);
  return salidaJson_(out);
}

/** Agregado nacional de las últimas 24 h: total de noches, mejores y peores
 *  zonas con resultado (>=5 noches) y el contraste medio con las pulseras.
 *  Las noches apartadas NO entran, salvo las de poblaciones ya respaldadas. */
function aggGlobal_() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get("agg2_global");
  if (hit) return JSON.parse(hit);

  var resp = poblacionesRespaldadas_();
  var desde = Date.now() - 24 * 3600e3;
  var filas = hoja_().getDataRange().getValues();
  var porZona = {}, porMun = {}, total = 0, nRel = 0, sumWs = 0, nDeuda = 0, sumDeuda = 0;
  var nAp = 0;
  for (var i = 1; i < filas.length; i++) {
    var f = filas[i];
    if (new Date(f[0]).getTime() < desde) continue;
    var v = Number(f[2]);
    if (!(v >= 0 && v <= 10)) continue;
    var peso = pesoUtil_(f, resp);
    if (peso === null) { nAp++; continue; }  // apartada y todavía sin respaldo
    total++;
    (porZona[f[1]] = porZona[f[1]] || []).push([v, peso]);
    // Agregado por MUNICIPIO: es el que da nombre propio a la noche votada
    // (Dénia aparece como Dénia, no como la estación de Pego).
    var mid = String(f[17] || "");
    if (/^[a-z0-9-]{2,40}$/.test(mid)) {
      var mm = porMun[mid] || (porMun[mid] = { n: String(f[18] || ""), z: f[1], v: [] });
      mm.v.push([v, peso]);
      if (!mm.n && f[18]) mm.n = String(f[18]);
    }
    if (f[10] !== "" && f[10] !== null) { nRel++; sumWs += Number(f[10]); }
    if (f[8] !== "" && f[8] !== null) { nDeuda++; sumDeuda += Number(f[8]); }
  }
  // Umbrales de ARRANQUE: el estudio acaba de empezar y con 5 noches por zona
  // el mapa se quedaba mudo (y parecía roto). Se publica desde la primera, pero
  // SIEMPRE acompañada del número de noches que hay detrás, que es lo honesto:
  // quien lo lee sabe si mira 1 voto o 50. Súbelos cuando haya volumen.
  var MIN_ZONA = 1, MIN_MUN = 1;
  var zonas = [];
  for (var z in porZona) {
    if (porZona[z].length >= MIN_ZONA) {
      zonas.push({ z: z, n: porZona[z].length,
                   d: Math.round(medianaPonderada_(porZona[z]) * 10) / 10 });
    }
  }
  zonas.sort(function (a, b) { return b.d - a.d; });
  var muns = [];
  for (var k in porMun) {
    if (porMun[k].v.length >= MIN_MUN) {
      muns.push({ m: k, nom: porMun[k].n, z: porMun[k].z, n: porMun[k].v.length,
                  d: Math.round(medianaPonderada_(porMun[k].v) * 10) / 10,
                  isla: resp[k] ? 1 : 0 });
    }
  }
  muns.sort(function (a, b) { return b.d - a.d; });
  var out = { ok: true, n: total, apartadas: nAp, zonas: zonas, municipios: muns,
              reloj_score: nRel >= 5 ? Math.round(sumWs / nRel) : null,
              deuda_media: nDeuda >= 5 ? Math.round(sumDeuda / nDeuda * 10) / 10 : null };
  cache.put("agg2_global", JSON.stringify(out), 300);
  return out;
}

/** Vista de auditoría (?global=1&apartadas=1): qué hay en el cajón de las
 *  noches apartadas y a cuánto está cada población de entrar en el cálculo.
 *  No la consume la web: es para mirarla tú. */
function aggApartadas_() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get("agg2_apartadas");
  if (hit) return JSON.parse(hit);

  var resp = poblacionesRespaldadas_();
  var desde = Date.now() - DIAS_RESPALDO * 24 * 3600e3;
  var filas = hoja_().getDataRange().getValues();
  var por = {}, total = 0, sinPoblacion = 0;
  for (var i = 1; i < filas.length; i++) {
    var f = filas[i];
    if (Number(f[21]) !== 1 || new Date(f[0]).getTime() < desde) continue;
    var v = Number(f[2]);
    if (!(v >= 0 && v <= 10)) continue;
    total++;
    var mid = String(f[17] || "");
    if (!/^[a-z0-9-]{2,40}$/.test(mid)) { sinPoblacion++; continue; }
    var g = por[mid] || (por[mid] = { nom: String(f[18] || ""), z: f[1], v: [],
                                      disp: {}, corregidas: 0 });
    g.v.push(v);
    g.disp[String(f[11] || "")] = 1;
    if (Number(f[20]) === 1) g.corregidas++;
    if (!g.nom && f[18]) g.nom = String(f[18]);
  }
  var lista = [];
  for (var m in por) {
    var g = por[m], nd = 0;
    for (var d in g.disp) nd++;
    g.v.sort(function (a, b) { return a - b; });
    lista.push({ m: m, nom: g.nom, z: g.z, n: g.v.length, dispositivos: nd,
                 min: g.v[0], max: g.v[g.v.length - 1],
                 mediana: g.v[Math.floor(g.v.length / 2)],
                 dispersion: Math.round((g.v[g.v.length - 1] - g.v[0]) * 10) / 10,
                 corregidas: g.corregidas,
                 respaldada: resp[m] ? 1 : 0,
                 // Qué le falta para entrar: dispositivos distintos, o que las
                 // noches dejen de contradecirse entre sí.
                 falta: resp[m] ? "" :
                        (nd < MIN_RESPALDO ? (MIN_RESPALDO - nd) + " dispositivo(s) más"
                                           : "las noches no concuerdan entre sí") });
  }
  lista.sort(function (a, b) { return b.n - a.n; });
  var out = { ok: true, dias: DIAS_RESPALDO, n: total,
              sin_poblacion: sinPoblacion, poblaciones: lista };
  cache.put("agg2_apartadas", JSON.stringify(out), 300);
  return out;
}

/** Poblaciones cuyas noches apartadas han dejado de ser un despiste. Se exigen
 *  MIN_RESPALDO dispositivos DISTINTOS —una persona sola no puede fabricar una
 *  isla— y que sus índices concuerden entre sí. Devuelve {poblacion_id: true}. */
function poblacionesRespaldadas_() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get("respaldadas");
  if (hit) return JSON.parse(hit);

  var desde = Date.now() - DIAS_RESPALDO * 24 * 3600e3;
  var filas = hoja_().getDataRange().getValues();
  var por = {};
  for (var i = 1; i < filas.length; i++) {
    var f = filas[i];
    if (Number(f[21]) !== 1 || new Date(f[0]).getTime() < desde) continue;
    var mid = String(f[17] || "");
    if (!/^[a-z0-9-]{2,40}$/.test(mid)) continue;
    var v = Number(f[2]);
    if (!(v >= 0 && v <= 10)) continue;
    var g = por[mid] || (por[mid] = { v: [], disp: {} });
    g.v.push(v);
    g.disp[String(f[11] || "")] = 1;
  }
  var ok = {};
  for (var m in por) {
    var g2 = por[m], nd = 0;
    for (var d in g2.disp) nd++;
    if (nd < MIN_RESPALDO) continue;
    var min = Math.min.apply(null, g2.v), max = Math.max.apply(null, g2.v);
    if (max - min > DISPERSION_RESPALDO) continue;
    ok[m] = true;
  }
  cache.put("respaldadas", JSON.stringify(ok), 1800);
  return ok;
}

/** Peso con el que una fila entra en los agregados, o null si no entra.
 *  Una noche apartada solo cuenta si su población ya está respaldada, y
 *  entonces se le quita el castigo por desvío: ya no es un voto sospechoso. */
function pesoUtil_(f, respaldadas) {
  var peso = Number(f[15]) || 1;
  if (Number(f[21]) !== 1) return peso;
  var mid = String(f[17] || "");
  if (!mid || !respaldadas[mid]) return null;
  return Math.max(peso, PESO_MIN_RESPALDADA);
}

// ---------------------------------------------------------------------------
// Auxiliares
// ---------------------------------------------------------------------------
var CABECERA = ["fecha", "zona", "indice", "dormir", "confort", "recurso",
                "despertar", "repetir", "deuda_sueno", "reloj_horas",
                "reloj_score", "dispositivo", "ref_aemet", "esperado",
                "desvio", "peso", "celda", "poblacion_id", "poblacion",
                "poblacion_propuesta", "poblacion_corregida", "apartada"];

function hoja_() {
  var libro = SpreadsheetApp.getActiveSpreadsheet();
  var h = libro.getSheetByName(HOJA);
  // Si la hoja ya existía de una versión anterior, se completa la cabecera con
  // las columnas nuevas (antes solo se escribía al crearla desde cero, así que
  // las columnas añadidas después se quedaban sin título).
  if (h && h.getLastColumn() < CABECERA.length) {
    h.getRange(1, 1, 1, CABECERA.length).setValues([CABECERA]);
  }
  if (!h) {
    h = libro.insertSheet(HOJA);
    h.appendRow(CABECERA);
  }
  return h;
}

function salidaJson_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function ent1a5_(x) {
  var n = Number(x);
  return (n >= 1 && n <= 5) ? n : "";
}

function hash_(texto) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256, SAL + texto, Utilities.Charset.UTF_8);
  return bytes.slice(0, 8).map(function (b) {
    return ("0" + ((b + 256) % 256).toString(16)).slice(-2);
  }).join("");
}

/** Mínima reciente de la zona, del JSON que publica el repo con datos AEMET. */
function refZona_(zona) {
  var cache = CacheService.getScriptCache();
  var raw = cache.get("tmin_json");
  if (!raw) {
    try {
      raw = UrlFetchApp.fetch(TMIN_URL, { muteHttpExceptions: true }).getContentText();
      cache.put("tmin_json", raw, 6 * 3600);
    } catch (e) { return null; }
  }
  try {
    var t = JSON.parse(raw).tmin[zona];
    return (typeof t === "number") ? t : null;
  } catch (e) { return null; }
}

/** Descanso ESPERADO (0-10) según la mínima de la noche. Misma curva que la
 *  semilla de la web (_obs_baseline en generar_calculadora.py): por encima de
 *  20 °C —noche tropical— el sueño profundo se deteriora de forma marcada. */
function descansoEsperado_(tmin) {
  if (tmin <= 12) return 9.5;
  if (tmin >= 28) return 1;
  return Math.round((9.5 - (tmin - 12) * (8.5 / 16)) * 10) / 10;
}

/** Factor 0.3–1 según el desvío medio histórico del dispositivo. */
function reputacion_(uidHash, desvio) {
  var props = PropertiesService.getScriptProperties();
  var clave = "rep_" + uidHash;
  var prev = props.getProperty(clave);
  var media = prev ? Number(prev) : desvio;
  media = 0.7 * media + 0.3 * desvio;
  props.setProperty(clave, String(Math.round(media * 100) / 100));
  if (media <= 3) return 1;
  if (media <= 4.5) return 0.7;
  if (media <= 6) return 0.5;
  return 0.3;
}

function medianaPonderada_(votos) {
  votos.sort(function (a, b) { return a[0] - b[0]; });
  var total = votos.reduce(function (s, v) { return s + v[1]; }, 0);
  var acum = 0;
  for (var i = 0; i < votos.length; i++) {
    acum += votos[i][1];
    if (acum >= total / 2) return votos[i][0];
  }
  return votos[votos.length - 1][0];
}
