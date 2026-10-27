// Punto de entrada: arma la escena y el rostro, expone window.AvacomAIAgent y habla con el host (.NET MAUI HybridWebView).
// Funciona igual en un navegador normal (sin host): los mensajes al host simplemente no se envian.
import * as THREE from 'three';
import { AgentScene, AgentError } from './scene.js';
import { FaceAnimator } from './face-animation.js';

const MODELO = 'models/avacom-ai-agent.glb';
const CONFIG = 'config/face-animations.json';
const ESTADOS = ['idle', 'blink', 'happy', 'tender', 'talking', 'thinking'];

const q = new URLSearchParams(location.search);
const opciones = {
  fps: Number(q.get('fps')) || 30,
  maxPixelRatio: Number(q.get('pr')) || 2,
  idleMotion: q.get('motion') !== '0',
};

let estado = 'cargando';                 // cargando | listo | error
let agente = null;                       // AgentScene
let cara = null;                         // FaceAnimator
let errorFinal = null;
const pendientes = [];                   // llamadas hechas antes de estar listo
let resolverListo;
const listo = new Promise((r) => { resolverListo = r; });

const $ = (id) => document.getElementById(id);

// ---- host ----------------------------------------------------------------------------------------------------------

/** Mensaje JSON para C# (HybridWebView.RawMessageReceived). Sin host, no hace nada. */
function aHost(msg) {
  try { window.HybridWebView?.SendRawMessage?.(JSON.stringify(msg)); } catch (e) { console.warn('[AvacomAIAgent] no se pudo avisar al host', e); }
}
const alEvento = (e) => { if (e.type === 'log' || e.type === 'state' || e.type === 'error') aHost(e); };

function mostrarEstado(texto, error = false) {
  const s = $('status');
  if (!s) return;
  s.textContent = texto || '';
  s.dataset.kind = error ? 'error' : 'info';
  s.hidden = !texto;
}

function fallar(e) {
  const code = e instanceof AgentError ? e.code : 'error_inesperado';
  const message = e?.message || String(e);
  errorFinal = { code, message, detail: e?.detail };
  estado = 'error';
  console.error('[AvacomAIAgent]', code, message, e?.detail || '');
  mostrarEstado(message, true);
  aHost({ type: 'error', code, message, detail: e?.detail ? String(e.detail) : undefined });
  resolverListo(false);
}

// ---- arranque ------------------------------------------------------------------------------------------------------

async function iniciar() {
  mostrarEstado('Preparando a AI Agent…');
  try {
    const respuesta = await fetch(CONFIG);
    if (!respuesta.ok) throw new AgentError('config_no_carga', `No se pudo leer la configuracion del rostro (${CONFIG}: ${respuesta.status}).`);
    const config = await respuesta.json();

    agente = new AgentScene($('stage'), { ...opciones, onEvent: alEvento });
    agente.init();
    await agente.cargarModelo(MODELO, config);                     // valida los tres objetos antes de dibujar

    const textura = await new THREE.TextureLoader().loadAsync(config.atlas.src).catch((e) => {
      throw new AgentError('atlas_no_carga', `No se pudo cargar la hoja de rostros (${config.atlas.src}).`, e?.message || e);
    });
    const caraObj = agente.objetos[config.face.object];
    if (!caraObj) throw new AgentError('modelo_incompleto', `El modelo no trae el objeto '${config.face.object}'.`);
    cara = new FaceAnimator({
      mesh: caraObj, config, texture: textura,
      anisotropy: Math.min(8, agente.renderer.capabilities.getMaxAnisotropy()),
      onFrame: () => agente.pedirDibujo(),
      onEvent: alEvento,
    });
    for (const w of cara.warnings) agente.diagnostics.warnings.push(w);
    agente.tickers.push((dt) => cara.tick(dt));
    agente.start();

    estado = 'listo';
    mostrarEstado('');
    document.body.dataset.ready = 'true';
    resolverListo(true);
    for (const [metodo, args] of pendientes.splice(0)) api[metodo](...args);
    aHost({ type: 'ready', diagnostics: diagnostico() });
  } catch (e) {
    fallar(e);
  }
}

function diagnostico() {
  const gl = agente?.renderer?.getContext?.();
  const info = gl?.getExtension?.('WEBGL_debug_renderer_info');
  return {
    status: estado,
    error: errorFinal,
    errors: agente?.diagnostics.errors ?? [],
    warnings: agente?.diagnostics.warnings ?? [],
    pantalla: agente?.diagnostics.pantalla ?? null,
    objetos: agente ? Object.keys(agente.objetos || {}) : [],
    materialesIntactos: agente?.objetos ? agente.materialesIntactos() : null,
    framesDibujados: agente?.frames ?? 0,
    atlas: cara ? { columnas: cara.cols, filas: cara.rows, fotogramas: cara.total, imagen: cara.texture?.image ? [cara.texture.image.width, cara.texture.image.height] : null } : null,
    webgl: gl ? { version: gl instanceof WebGL2RenderingContext ? 2 : 1, renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE) } : null,
    three: THREE.REVISION,
  };
}

// ---- API publica ---------------------------------------------------------------------------------------------------

/** Si todavia no esta listo, la llamada se guarda y se ejecuta al estarlo. */
function cuando(metodo, args, fn) {
  if (estado === 'listo') return fn();
  if (estado === 'cargando') { pendientes.push([metodo, args]); return undefined; }
  console.warn(`[AvacomAIAgent] ${metodo}() ignorado: el renderizador esta en error (${errorFinal?.code})`);
  return false;
}

const api = {
  /** Reproduce una animacion del rostro: idle, blink, happy, tender, talking o thinking. opciones: {fps, durationMs, loop}. */
  playAnimation(name, options) { return cuando('playAnimation', [name, options], () => cara.play(name, options)); },
  /** Detiene la animacion en curso y vuelve a idle. */
  stopAnimation() { return cuando('stopAnimation', [], () => { cara.stop(); return true; }); },
  /** Muestra una expresion fija (sin animar). */
  setExpression(name) { return cuando('setExpression', [name], () => cara.setExpression(name)); },
  /** FPS de las secuencias (1-30). Sin valor, cada animacion usa el suyo. */
  setAnimationFPS(fps) { return cuando('setAnimationFPS', [fps], () => cara.setFps(fps)); },
  getCurrentState() { return estado === 'listo' ? { status: estado, ...cara.getState() } : { status: estado, state: 'idle', frame: -1, playing: false, fps: null }; },
  /** Texto bajo el personaje (aqui llegara lo que diga el agente). Vacio = vuelve la leyenda. */
  setText(text) { setTexto(text); return true; },
  getDiagnostics() { return diagnostico(); },
  /** Libera todo: bucle de dibujo, listeners, geometrias, texturas y el contexto WebGL. */
  dispose() {
    cara?.dispose(); cara = null;
    agente?.dispose(); agente = null;
    pendientes.length = 0;
    removeEventListener('HybridWebViewMessageReceived', alMensajeDelHost);
    estado = 'liberado';
    document.body.dataset.ready = 'false';
  },
  /** Pausa/reanuda el dibujo sin liberar nada (pantalla oculta). */
  pause() { agente?.stop(); },
  resume() { agente?.start(); agente?.pedirDibujo(); },
  states: ESTADOS,
  ready: listo,
};
window.AvacomAIAgent = api;

function setTexto(texto) {
  const t = $('caption-text');
  const c = $('caption');
  if (!t) return;
  const vacio = !texto || !String(texto).trim();
  t.textContent = vacio ? '' : String(texto);
  c.dataset.empty = vacio ? 'true' : 'false';
}

// C# -> JS por mensajes: {"cmd":"play","name":"talking"} / stop / expression / fps / text / pause / resume / dispose
function alMensajeDelHost(e) {
  let m;
  try { m = JSON.parse(e.detail?.message ?? e.detail); } catch { return; }
  switch (m?.cmd) {
    case 'play': api.playAnimation(m.name, m.options); break;
    case 'stop': api.stopAnimation(); break;
    case 'expression': api.setExpression(m.name); break;
    case 'fps': api.setAnimationFPS(m.fps); break;
    case 'text': api.setText(m.text); break;
    case 'pause': api.pause(); break;
    case 'resume': api.resume(); break;
    case 'dispose': api.dispose(); break;
  }
}
addEventListener('HybridWebViewMessageReceived', alMensajeDelHost);

addEventListener('error', (e) => aHost({ type: 'log', level: 'error', message: `JS: ${e.message} (${e.filename}:${e.lineno})` }));
addEventListener('unhandledrejection', (e) => aHost({ type: 'log', level: 'error', message: `JS promesa: ${e.reason?.message || e.reason}` }));
addEventListener('pagehide', () => { if (estado !== 'liberado') api.dispose(); });

setTexto('');
iniciar();
