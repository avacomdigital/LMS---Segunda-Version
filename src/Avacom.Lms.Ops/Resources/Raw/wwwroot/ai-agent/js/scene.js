// Escena de AI Agent: renderer, camara, luces, carga y validacion del GLB y ciclo de dibujo.
// El modelo de Blender es lo unico que se dibuja: no se sustituye ni se completa con primitivas.
import * as THREE from 'three';
import { GLTFLoader } from '../vendor/three/loaders/GLTFLoader.js';
import { aplicarDegradadoDePantalla } from './screen-gradient.js';

const log = (nivel, ...args) => console[nivel]('[AvacomAIAgent/scene]', ...args);

/** Los tres objetos del GLB y el material que cada uno debe traer. */
export const REQUERIDOS = [
  { objeto: 'tablet_cuerpo', material: 'material_tablet_cuerpo' },
  { objeto: 'pantalla_colores', material: 'material_pantalla_colores' },
  { objeto: 'face_sprite', material: 'material_face_sprite' },
];

export class AgentError extends Error {
  constructor(code, message, detail) { super(message); this.code = code; this.detail = detail; }
}

/** Foto de las propiedades que importan de un material, para comprobar luego que no se tocaron. */
function huella(m) {
  return JSON.stringify({
    tipo: m.type, color: m.color?.getHexString(), emissive: m.emissive?.getHexString(), emissiveIntensity: m.emissiveIntensity,
    roughness: m.roughness, metalness: m.metalness, opacity: m.opacity, transparent: m.transparent, doubleSided: m.side,
    map: m.map?.uuid ?? null, emissiveMap: m.emissiveMap?.uuid ?? null, normalMap: m.normalMap?.uuid ?? null, roughnessMap: m.roughnessMap?.uuid ?? null,
    envMap: m.envMap?.uuid ?? null, vertexColors: m.vertexColors, blending: m.blending, depthWrite: m.depthWrite, depthTest: m.depthTest,
  });
}

export class AgentScene {
  /**
   * @param {HTMLElement} host   contenedor del canvas
   * @param {object} o           { modelUrl, maxPixelRatio, fps, idleMotion, onDirty, onEvent }
   */
  constructor(host, o) {
    this.host = host;
    this.o = { maxPixelRatio: 2, fps: 30, idleMotion: true, ...o };
    this.dirty = true;
    this.running = false;
    this.disposed = false;
    this.visible = true;
    this.tickers = [];
    this.diagnostics = { errors: [], warnings: [], notes: [] };
    this._raf = 0;
    this._last = 0;
    this._t0 = 0;
    this._listeners = [];
  }

  // ---- arranque ----------------------------------------------------------------------------------------------------

  init() {
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'default', preserveDrawingBuffer: false });
    } catch (e) {
      throw new AgentError('webgl_no_disponible', 'WebGL no esta disponible en este equipo: no se puede dibujar al agente.', String(e?.message || e));
    }
    if (!renderer.getContext()) throw new AgentError('webgl_no_disponible', 'WebGL no esta disponible en este equipo: no se puede dibujar al agente.');
    this.renderer = renderer;
    renderer.setClearColor(0xffffff, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping;          // los colores del modelo salen tal como se exportaron
    renderer.domElement.setAttribute('aria-label', 'AI Agent');
    this.host.appendChild(renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xffffff);
    this.camera = new THREE.PerspectiveCamera(28, 1, 1, 100);

    // Luz suave de estudio: hemisferica + clave desde arriba a la izquierda + relleno tenue. Sin mapa de entorno.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xd9e0e8, 1.15));
    const clave = new THREE.DirectionalLight(0xffffff, 1.7);
    clave.position.set(6, 7, 5);
    const relleno = new THREE.DirectionalLight(0xdfe9ff, 0.55);
    relleno.position.set(5, -2, -6);
    this.scene.add(clave, relleno);

    const alPerderContexto = (e) => { e.preventDefault(); this._contextoPerdido = true; this.o.onEvent?.({ type: 'error', code: 'webgl_contexto_perdido', message: 'El contexto WebGL se perdio; se intenta recuperar.' }); };
    const alRecuperar = () => { this._contextoPerdido = false; this.dirty = true; this.o.onEvent?.({ type: 'log', level: 'info', message: 'Contexto WebGL recuperado.' }); };
    this._on(renderer.domElement, 'webglcontextlost', alPerderContexto);
    this._on(renderer.domElement, 'webglcontextrestored', alRecuperar);

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.host);
    this._on(window, 'resize', () => this.resize());
    this._on(document, 'visibilitychange', () => this._aplicarVisibilidad());
    if ('IntersectionObserver' in window) {
      this.io = new IntersectionObserver((es) => { this.visible = es.some((x) => x.isIntersecting); this._aplicarVisibilidad(); });
      this.io.observe(this.host);
    }
    this.resize();
  }

  _on(target, tipo, fn) { target.addEventListener(tipo, fn); this._listeners.push([target, tipo, fn]); }

  async cargarModelo(url, config = {}) {
    const gltf = await new Promise((ok, fail) => new GLTFLoader().load(url, ok, undefined, (e) => fail(new AgentError('modelo_no_carga', `No se pudo cargar el modelo 3D (${url}).`, String(e?.message || e)))));
    this.gltf = gltf;
    this.raiz = gltf.scene;
    this.validar(gltf.scene);
    this.scene.add(gltf.scene);
    this.raiz.updateMatrixWorld(true);
    this._encuadrar();
    this._diagnosticarPantalla(config.screen, config.face);
    this._guardarHuellas();                    // despues del degradado: de ahi en adelante nada vuelve a tocar el cuerpo ni la pantalla
    return gltf;
  }

  /** Comprueba que estan los tres objetos con sus materiales ANTES de dibujar nada. */
  validar(raiz) {
    const faltan = [];
    this.objetos = {};
    for (const r of REQUERIDOS) {
      const o = raiz.getObjectByName(r.objeto);
      if (!o) { faltan.push(r.objeto); continue; }
      if (!o.isMesh) { faltan.push(`${r.objeto} (existe pero no es una malla)`); continue; }
      this.objetos[r.objeto] = o;
      const nombre = o.material?.name;
      if (nombre !== r.material) this._aviso(`El objeto '${r.objeto}' trae el material '${nombre}' y se esperaba '${r.material}'.`);
    }
    if (faltan.length) {
      const msg = `El modelo 3D no contiene lo que se necesita: falta ${faltan.map((f) => `'${f}'`).join(', ')}. Objetos encontrados: ${this._nombres(raiz).join(', ') || '(ninguno)'}.`;
      this.diagnostics.errors.push(msg);
      throw new AgentError('modelo_incompleto', msg);
    }
  }

  _nombres(raiz) { const n = []; raiz.traverse((o) => { if (o.name && o !== raiz) n.push(o.name); }); return n; }

  _guardarHuellas() {
    // El cuerpo se conserva como salio de Blender y la pantalla como salio mas su degradado; se anota como quedaron para poder demostrar que no se vuelven a tocar.
    this._huellas = { tablet_cuerpo: huella(this.objetos.tablet_cuerpo.material), pantalla_colores: huella(this.objetos.pantalla_colores.material) };
  }

  /** true si el cuerpo y la pantalla siguen exactamente como quedaron al cargar. */
  materialesIntactos() {
    if (!this._huellas) return false;
    return huella(this.objetos.tablet_cuerpo.material) === this._huellas.tablet_cuerpo && huella(this.objetos.pantalla_colores.material) === this._huellas.pantalla_colores;
  }

  /**
   * El GLB no trae el degradado de la pantalla horneado (sin textura, color base blanco). Si config.screen lo define, se genera con esos colores y se pone en
   * ese material (js/screen-gradient.js). Si el GLB ya trae textura, no se toca. Sin ninguno de los dos, se avisa.
   */
  _diagnosticarPantalla(screen, face) {
    const mesh = this.objetos.pantalla_colores;
    const m = mesh.material;
    const traiaTextura = !!(m.map || m.emissiveMap);
    const color = m.color ? `#${m.color.getHexString()}` : 'sin color';
    const resumen = { texturaEnElGlb: traiaTextura, colorBase: color, emisivo: m.emissive ? `#${m.emissive.getHexString()}` : null, degradado: null };
    this.diagnostics.pantalla = resumen;
    try {
      resumen.degradado = aplicarDegradadoDePantalla(mesh, screen, face?.frontNormal, face?.up);
    } catch (e) {
      resumen.degradado = { aplicado: false, motivo: String(e?.message || e) };
      this._aviso(`No se pudo aplicar el degradado a material_pantalla_colores: ${resumen.degradado.motivo}`);
    }
    if (!traiaTextura && !resumen.degradado.aplicado && m.color?.getHex() === 0xffffff) {
      this._aviso('material_pantalla_colores no trae textura, su color base es blanco y no hay degradado configurado (config.screen): se muestra blanco.');
    }
  }

  _aviso(texto) { this.diagnostics.warnings.push(texto); log('warn', texto); this.o.onEvent?.({ type: 'log', level: 'warn', message: texto }); }

  // ---- encuadre ----------------------------------------------------------------------------------------------------

  _encuadrar() {
    const caja = new THREE.Box3();
    for (const o of Object.values(this.objetos)) caja.expandByObject(o);
    this.caja = caja;
    this.centro = caja.getCenter(new THREE.Vector3());
    this.tamano = caja.getSize(new THREE.Vector3());
    // La pantalla mira hacia +X: la camara se coloca en ese eje y mira al centro del modelo.
    this.camera.up.set(0, 1, 0);
    this._ajustarCamara();
  }

  _ajustarCamara() {
    if (!this.caja) return;
    const { x: profundo, y: alto, z: ancho } = this.tamano;
    const aspecto = this.camera.aspect;
    const tanV = Math.tan(THREE.MathUtils.degToRad(this.camera.fov / 2));
    const tanH = tanV * aspecto;
    const margen = 1.12;                                      // aire alrededor del modelo (incluye el vaiven)
    const distV = (alto / 2) * margen / tanV;
    const distH = (ancho / 2) * margen / tanH;
    const dist = Math.max(distV, distH) + profundo / 2;
    this.camera.position.set(this.centro.x + dist, this.centro.y, this.centro.z);
    this.camera.near = Math.max(0.5, dist - this.tamano.length());
    this.camera.far = dist + this.tamano.length() * 2;
    this.camera.lookAt(this.centro);
    this.camera.updateProjectionMatrix();
  }

  resize() {
    if (!this.renderer || this.disposed) return;
    const w = Math.max(1, this.host.clientWidth), h = Math.max(1, this.host.clientHeight);
    const pr = Math.min(window.devicePixelRatio || 1, this.o.maxPixelRatio);
    this.renderer.setPixelRatio(pr);
    this.renderer.setSize(w, h, false);
    const c = this.renderer.domElement;
    c.style.width = '100%'; c.style.height = '100%';
    this.camera.aspect = w / h;
    this._ajustarCamara();
    this.dirty = true;
  }

  // ---- ciclo -------------------------------------------------------------------------------------------------------

  pedirDibujo() { this.dirty = true; }

  start() {
    if (this.running || this.disposed) return;
    this.running = true;
    this._last = performance.now();
    this._t0 = this._last;
    const paso = (now) => {
      if (!this.running) return;
      this._raf = requestAnimationFrame(paso);
      const intervalo = 1000 / this.o.fps;
      if (now - this._last < intervalo - 2) return;
      const dt = Math.min(now - this._last, 250);
      this._last = now;
      for (const t of this.tickers) t(dt);
      if (this.o.idleMotion && !this._reducirMovimiento()) { this._movimientoSuave((now - this._t0) / 1000); this.dirty = true; }
      if (this.dirty && !this._contextoPerdido && this._debeDibujar()) {
        this.dirty = false;
        this.renderer.render(this.scene, this.camera);
        this.frames = (this.frames || 0) + 1;
      }
    };
    this._raf = requestAnimationFrame(paso);
  }

  stop() { this.running = false; if (this._raf) cancelAnimationFrame(this._raf); this._raf = 0; }

  _debeDibujar() { return this.visible && !document.hidden; }
  _aplicarVisibilidad() { this.dirty = true; if (this._debeDibujar()) this._last = performance.now(); }
  _reducirMovimiento() { return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches; }

  /** Un vaiven muy ligero (flotar y girar un poco): se aplica a la raiz del GLB sin tocar su jerarquia ni sus materiales. */
  _movimientoSuave(t) {
    if (!this.raiz) return;
    const escala = this.tamano.length();
    const yaw = Math.sin(t * 0.7) * 0.06, cabeceo = Math.sin(t * 0.5 + 1) * 0.015;
    this.raiz.quaternion.setFromEuler(new THREE.Euler(0, yaw, cabeceo, 'YXZ'));
    // Gira alrededor del centro del modelo, no del origen del archivo.
    const c = this.centro.clone().applyQuaternion(this.raiz.quaternion);
    this.raiz.position.copy(this.centro).sub(c);
    this.raiz.position.y += Math.sin(t * 1.3) * escala * 0.006;
  }

  // ---- limpieza ----------------------------------------------------------------------------------------------------

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.stop();
    this.ro?.disconnect();
    this.io?.disconnect();
    for (const [t, tipo, fn] of this._listeners) t.removeEventListener(tipo, fn);
    this._listeners.length = 0;
    this.tickers.length = 0;
    this.scene?.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      const ms = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
      for (const m of ms) {
        for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();
        m.dispose();
      }
    });
    this.scene?.clear();
    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.forceContextLoss?.();
      this.renderer.domElement.remove();
    }
    this.renderer = this.scene = this.camera = this.raiz = this.gltf = null;
  }
}
