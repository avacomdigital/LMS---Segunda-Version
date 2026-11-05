// Controlador del rostro de AI Agent. Solo toca el objeto `face_sprite` y su material `material_face_sprite`:
// reutiliza UN material y UNA textura y, en cada cambio de fotograma, solo reescribe la matriz UV de la textura.
import * as THREE from 'three';

const log = (nivel, ...args) => console[nivel]('[AvacomAIAgent/face]', ...args);

/**
 * Calcula, a partir de la propia geometria, la transformacion que lleva las UV de la cara frontal del cubo a las
 * coordenadas (s, t) de un fotograma: s de 0 (izquierda) a 1 (derecha) y t de 0 (arriba) a 1 (abajo), vistas desde
 * fuera de esa cara con `up` hacia arriba. No supone ninguna disposicion de UV (el cubo de Blender trae el desarrollo
 * en cruz: esta cara ocupa solo un cuarto de la textura y girada). Devuelve la inversa: UV -> (s, t).
 */
export function mapaDeLaCaraFrontal(geometry, frontNormal, up) {
  const pos = geometry.getAttribute('position');
  const nor = geometry.getAttribute('normal');
  const uv = geometry.getAttribute('uv');
  if (!pos || !nor || !uv) throw new Error('la geometria de face_sprite no trae position, normal y uv');

  const front = new THREE.Vector3(...frontNormal).normalize();
  const dir = front.clone().negate();                       // hacia donde mira quien ve la cara
  const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(...up)).normalize();
  const arriba = new THREE.Vector3().crossVectors(right, dir).normalize();

  const v = [];
  const p = new THREE.Vector3();
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    n.fromBufferAttribute(nor, i);
    if (n.dot(front) < 0.9) continue;
    p.fromBufferAttribute(pos, i);
    v.push({ a: p.dot(right), b: p.dot(arriba), u: uv.getX(i), v: uv.getY(i) });
  }
  if (v.length < 3) throw new Error(`la cara frontal (normal ${frontNormal}) de face_sprite tiene ${v.length} vertices; se necesitan al menos 3`);

  const minA = Math.min(...v.map((q) => q.a)), maxA = Math.max(...v.map((q) => q.a));
  const minB = Math.min(...v.map((q) => q.b)), maxB = Math.max(...v.map((q) => q.b));
  for (const q of v) { q.s = (q.a - minA) / (maxA - minA); q.t = (maxB - q.b) / (maxB - minB); }

  const cerca = (s, t) => v.reduce((m, q) => (Math.hypot(q.s - s, q.t - t) < Math.hypot(m.s - s, m.t - t) ? q : m));
  const q00 = cerca(0, 0), q10 = cerca(1, 0), q01 = cerca(0, 1);
  // uv = uv00 + s * (uv10 - uv00) + t * (uv01 - uv00)
  const m = [q10.u - q00.u, q01.u - q00.u, q00.u, q10.v - q00.v, q01.v - q00.v, q00.v];
  const det = m[0] * m[4] - m[1] * m[3];
  if (Math.abs(det) < 1e-9) throw new Error('las UV de la cara frontal de face_sprite estan degeneradas');
  const inv = new THREE.Matrix3().set(
    m[4] / det, -m[1] / det, (m[1] * m[5] - m[4] * m[2]) / det,
    -m[3] / det, m[0] / det, (m[3] * m[2] - m[0] * m[5]) / det,
    0, 0, 1);
  const rectUv = { u: [Math.min(...v.map((q) => q.u)), Math.max(...v.map((q) => q.u))], v: [Math.min(...v.map((q) => q.v)), Math.max(...v.map((q) => q.v))] };
  return { inverse: inv, rectUv, aspect: (maxA - minA) / (maxB - minB) };
}

export class FaceAnimator {
  /**
   * @param {object} o
   * @param {THREE.Mesh} o.mesh        face_sprite
   * @param {object} o.config          contenido de config/face-animations.json
   * @param {THREE.Texture} o.texture  atlas ya cargado
   * @param {(n:string)=>void} o.onFrame   se llama al cambiar el fotograma (para pedir un render)
   * @param {(e:object)=>void} [o.onEvent] cambios de estado, para quien escuche (C#)
   */
  constructor({ mesh, config, texture, anisotropy = 4, onFrame, onEvent }) {
    this.mesh = mesh;
    this.config = config;
    this.onFrame = onFrame || (() => {});
    this.onEvent = onEvent || (() => {});
    this.material = mesh.material;
    this.atlas = config.atlas;
    this.cols = this.atlas.columns;
    this.rows = this.atlas.rows;
    this.total = this.cols * this.rows;
    this.fpsOverride = null;
    this.warnings = [];

    this.mapa = mapaDeLaCaraFrontal(mesh.geometry, config.face.frontNormal, config.face.up);
    this._prepararTextura(texture, anisotropy);
    this._prepararMaterial();
    this.states = this._validarEstados();

    this.state = 'idle';
    this._guardado = null;              // lo que un parpadeo interrumpio y debe reanudarse
    this.frame = -1;
    this.playing = false;
    this._seq = null;
    this._acum = 0;
    this._idx = 0;
    this._restanteMs = null;
    this._proxParpadeo = this._sorteaParpadeo();
    this._mostrar(this.states.idle.pose);
  }

  // ---- preparacion (una sola vez) --------------------------------------------------------------------------------

  _prepararTextura(tex, anisotropy) {
    tex.flipY = false;                                  // convencion glTF: v = 0 es el borde superior de la imagen
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = true;
    tex.anisotropy = anisotropy;
    tex.matrixAutoUpdate = false;                       // la matriz la escribimos nosotros, fotograma a fotograma
    tex.needsUpdate = true;
    this.texture = tex;
  }

  _prepararMaterial() {
    const m = this.material;
    const lado = m.color.clone();                       // color original (azul oscuro): lo conservan los cantos del cubo
    const glow = this.config.face.glow ?? 0;
    const frente = new THREE.Vector3(...this.config.face.frontNormal).normalize();
    m.map = this.texture;
    m.color.set(0xffffff);                              // si no, el color base oscuro multiplicaria el rostro hasta apagarlo
    m.polygonOffset = true;                             // por si la pantalla queda a poca distancia del rostro (z-fighting)
    m.polygonOffsetFactor = -1;
    m.polygonOffsetUnits = -1;
    if (this.atlas.alpha) { m.transparent = true; m.alphaTest = 0.01; }
    // El sprite solo se pinta en la cara frontal; los otros cinco lados del cubo conservan el color original.
    m.onBeforeCompile = (shader) => {
      shader.uniforms.uAvSide = { value: new THREE.Vector3(lado.r, lado.g, lado.b) };
      shader.uniforms.uAvGlow = { value: glow };
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying float vAvFront;')
        .replace('#include <beginnormal_vertex>',
          `#include <beginnormal_vertex>\n vAvFront = step(0.5, dot(objectNormal, vec3(${frente.x.toFixed(4)}, ${frente.y.toFixed(4)}, ${frente.z.toFixed(4)})));`);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying float vAvFront;\nuniform vec3 uAvSide;\nuniform float uAvGlow;')
        .replace('#include <map_fragment>',
          `vec4 avSample = texture2D( map, vMapUv );
           diffuseColor.rgb *= mix( uAvSide, avSample.rgb, vAvFront );
           ${this.atlas.alpha ? 'diffuseColor.a *= mix( 1.0, avSample.a, vAvFront );' : ''}`)
        .replace('#include <emissivemap_fragment>', 'totalEmissiveRadiance = avSample.rgb * vAvFront * uAvGlow;');
    };
    m.customProgramCacheKey = () => 'avacom-face-sprite-v1';
    m.needsUpdate = true;
  }

  _validarEstados() {
    const out = {};
    const defs = this.config.states || {};
    const ok = (f) => Number.isInteger(f) && f >= 0 && f < this.total;
    for (const [nombre, d] of Object.entries(defs)) {
      const frames = (d.frames || []).map((x) => (typeof x === 'number' ? { f: x } : x)).filter((x) => {
        if (ok(x.f)) return true;
        this._aviso(`estado '${nombre}': el fotograma ${x.f} no existe (hay ${this.total}); se omite`);
        return false;
      });
      const pose = ok(d.pose) ? d.pose : frames[0]?.f;
      out[nombre] = { ...d, frames, pose, ausente: frames.length === 0 && !ok(pose) };
      if (out[nombre].ausente) this._aviso(`estado '${nombre}': no tiene fotogramas validos`);
    }
    for (const requerido of ['idle', 'blink', 'happy', 'tender', 'talking', 'thinking']) {
      if (!out[requerido]) { out[requerido] = { frames: [], ausente: true }; this._aviso(`estado '${requerido}': no esta definido en la configuracion`); }
    }
    if (out.idle.ausente) throw new Error("el estado 'idle' no tiene fotogramas validos: no se puede mostrar un rostro");
    return out;
  }

  _aviso(texto) { this.warnings.push(texto); log('warn', texto); this.onEvent({ type: 'log', level: 'warn', message: texto }); }

  /** El estado que de verdad se usa: si no existe sus fotogramas, su respaldo (sin ciclos). */
  _resolver(nombre) {
    const visto = new Set();
    let n = nombre;
    while (n && this.states[n]?.ausente && !visto.has(n)) { visto.add(n); n = this.config.fallbacks?.[n]; }
    return n && this.states[n] && !this.states[n].ausente ? n : 'idle';
  }

  // ---- pintado ---------------------------------------------------------------------------------------------------

  _mostrar(frame) {
    if (frame === this.frame) return;
    this.frame = frame;
    const col = frame % this.cols, fila = Math.floor(frame / this.cols);
    const i = this.atlas.inset ?? 0, k = 1 - 2 * i;
    // texU = (col + i + k*s) / cols ; texV = (fila + i + k*t) / rows ; (s, t) = inverso * (u, v, 1)
    const F = new THREE.Matrix3().set(
      k / this.cols, 0, (col + i) / this.cols,
      0, k / this.rows, (fila + i) / this.rows,
      0, 0, 1);
    this.texture.matrix.multiplyMatrices(F, this.mapa.inverse);
    this.onFrame(frame);
  }

  // ---- API ---------------------------------------------------------------------------------------------------------

  /** Reproduce la animacion `nombre`. opciones: {fps, durationMs, loop}. Un parpadeo interrumpe y luego reanuda lo que hubiera. */
  play(nombre, opciones = {}) {
    if (!this.states[nombre]) { this._aviso(`playAnimation('${nombre}'): estado desconocido (${Object.keys(this.states).join(', ')})`); return false; }
    const real = this._resolver(nombre);
    if (real !== nombre) this._aviso(`playAnimation('${nombre}'): sin fotogramas, se usa '${real}'`);
    const d = this.states[real];
    if (nombre === 'blink') {
      // Un parpadeo encima de otro no apila nada: se queda lo que se guardo la primera vez.
      if (this.state !== 'blink') this._guardado = { state: this.state, seq: this._seq, idx: this._idx, acum: this._acum, rest: this._restanteMs, playing: this.playing };
    } else {
      this._guardado = null;
    }
    this.state = nombre;
    this._seq = { nombre: real, frames: d.frames, loop: opciones.loop ?? d.loop ?? false, fps: opciones.fps ?? d.fps ?? this.config.defaultFps ?? 10, returnTo: d.returnTo };
    this._idx = 0;
    this._acum = 0;
    this._restanteMs = opciones.durationMs ?? d.durationMs ?? null;
    this.playing = d.frames.length > 1 || !!this._restanteMs || nombre === 'blink';
    this._mostrar(d.frames[0]?.f ?? d.pose);
    this._emitir();
    return true;
  }

  /** Detiene lo que suene y vuelve al reposo. */
  stop() {
    this._seq = null; this.playing = false; this._restanteMs = null;
    this._guardado = null;
    this.state = 'idle';
    this._mostrar(this.states.idle.pose);
    this._proxParpadeo = this._sorteaParpadeo();
    this._emitir();
  }

  /** Muestra una expresion fija (el fotograma de reposo de ese estado) y cancela cualquier animacion. */
  setExpression(nombre) {
    if (!this.states[nombre]) { this._aviso(`setExpression('${nombre}'): estado desconocido`); return false; }
    const real = this._resolver(nombre);
    if (real !== nombre) this._aviso(`setExpression('${nombre}'): sin fotogramas, se usa '${real}'`);
    this._seq = null; this.playing = false; this._restanteMs = null; this._guardado = null;
    this.state = nombre;
    this._mostrar(this.states[real].pose ?? this.states.idle.pose);
    this._proxParpadeo = this._sorteaParpadeo();
    this._emitir();
    return true;
  }

  setFps(fps) {
    const n = Number(fps);
    if (!Number.isFinite(n) || n <= 0) { this.fpsOverride = null; return this.fpsOverride; }
    this.fpsOverride = Math.min(30, Math.max(1, n));
    return this.fpsOverride;
  }

  getState() {
    return { state: this.state, frame: this.frame, playing: this.playing, fps: this.fpsOverride ?? this._seq?.fps ?? this.config.defaultFps ?? 10, fpsOverride: this.fpsOverride };
  }

  /** true si algo cambia solo con el tiempo (para no renderizar en vano cuando todo esta quieto). */
  get animando() { return this.playing || (this.config.autoBlink?.enabled && this.state === 'idle'); }

  // ---- reloj -------------------------------------------------------------------------------------------------------

  tick(dtMs) {
    if (this._seq && this.playing) {
      if (this._restanteMs != null) {
        this._restanteMs -= dtMs;
        if (this._restanteMs <= 0) { this._terminar(); return; }
      }
      this._acum += dtMs;
      let guarda = 8;
      while (guarda-- > 0) {
        const f = this._seq.frames[this._idx];
        const duracion = f?.ms ?? 1000 / (this.fpsOverride ?? this._seq.fps);
        if (this._acum < duracion) break;
        this._acum -= duracion;
        this._idx++;
        if (this._idx >= this._seq.frames.length) {
          if (!this._seq.loop) { this._terminar(); return; }
          this._idx = 0;
        }
        this._mostrar(this._seq.frames[this._idx].f);
      }
      return;
    }
    // Reposo: un parpadeo de vez en cuando le da vida.
    const ab = this.config.autoBlink;
    if (ab?.enabled && this.state === 'idle' && !this._seq) {
      this._proxParpadeo -= dtMs;
      if (this._proxParpadeo <= 0) { this.play('blink'); this._proxParpadeo = this._sorteaParpadeo(); }
    }
  }

  _terminar() {
    const era = this._seq?.nombre;
    const g = this._guardado;
    this._guardado = null;
    this._proxParpadeo = this._sorteaParpadeo();
    if (era === 'blink' && g) {
      // Reanuda lo que el parpadeo interrumpio: una animacion en su fotograma, o una expresion fija.
      this.state = g.state; this._seq = g.seq; this._idx = g.idx; this._acum = g.acum; this._restanteMs = g.rest; this.playing = g.playing;
      const f = this._seq ? this._seq.frames[this._idx]?.f : this.states[this._resolver(g.state)].pose;
      this._mostrar(f ?? this.states.idle.pose);
      this._emitir();
      return;
    }
    const destino = this._resolver(era === 'blink' ? 'idle' : (this._seq?.returnTo || 'idle'));
    this._seq = null; this.playing = false; this._restanteMs = null;
    this.state = destino;
    this._mostrar(this.states[destino].pose ?? this.states.idle.pose);
    this._emitir();
  }

  _sorteaParpadeo() {
    const { minMs = 2600, maxMs = 5200 } = this.config.autoBlink || {};
    return minMs + Math.random() * (maxMs - minMs);
  }

  _emitir() { this.onEvent({ type: 'state', ...this.getState() }); }

  dispose() {
    this._seq = null; this.playing = false;
    this.texture?.dispose();
    this.material.map = null;
    this.material.onBeforeCompile = () => {};
    this.texture = null;
  }
}
