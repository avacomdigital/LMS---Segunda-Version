// Visor del lápiz 3D (Three.js) para la versión web del LMS; lo carga pencil-viewer.html. Equivale al Pencil3DView nativo de MAUI.
// Escena, cámara, luces y modelo; el lápiz gira despacio sobre el eje vertical, inclinado unos grados y flotando
// apenas. Todo es relativo al tamaño del modelo y del área asignada: no hay coordenadas fijas para una resolución.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// Parámetros de la animación. MAUI puede cambiarlos en caliente con window.pencilViewer.configure({ ... }).
const config = {
  modelUrl: 'models/lapiz.glb',
  secondsPerTurn: 12,   // una vuelta completa sobre el eje vertical (10–16 s)
  tiltDegrees: 8,       // inclinación fija sobre un eje secundario (5–12°)
  floatPixels: 3,       // amplitud de la flotación, en píxeles visuales (2–5)
  floatSpeed: 0.7,      // rad/s de la flotación: una oscilación ≈ 9 s
  fillRatio: 0.78,      // fracción del área útil que ocupa el lápiz (0,70–0,85)
  fov: 28,              // perspectiva moderada: sin deformación ni gran angular
};

const canvas = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(config.fov, 1, 0.1, 100);

// Iluminación de estudio: ambiente suave, luz principal arriba a la izquierda y un relleno tenue desde el lado
// opuesto. Sin sombras en tiempo real ni postproceso; los materiales son los del GLB.
scene.add(new THREE.AmbientLight(0xffffff, 1.4));
const principal = new THREE.DirectionalLight(0xffffff, 2.4);
principal.position.set(-3, 5, 4);
scene.add(principal);
const relleno = new THREE.DirectionalLight(0xffffff, 0.8);
relleno.position.set(4, -1, -3);
scene.add(relleno);

// pivote: gira sobre el eje vertical y flota · soporte: inclinación fija · orientado: modelo alineado y centrado.
// El lápiz entero gira como una sola unidad (rotation.y del pivote); ninguna malla gira por su cuenta.
const pivote = new THREE.Group();
const soporte = new THREE.Group();
const orientado = new THREE.Group();
soporte.add(orientado);
pivote.add(soporte);
scene.add(pivote);

const tamano = new THREE.Vector3();  // caja del modelo ya alineado, en unidades del mundo
let unidadesPorPixel = 0;             // unidades del mundo por píxel visual, a la distancia del modelo
let listo = false;

new GLTFLoader().load(
  config.modelUrl,
  (gltf) => {
    const modelo = gltf.scene;
    alinear(modelo);
    orientado.add(modelo);
    centrar();
    soporte.rotation.z = THREE.MathUtils.degToRad(config.tiltDegrees);
    redimensionar();
    listo = true;
    canvas.classList.add('visible');
    arrancar();
    avisar('ready');
  },
  undefined,
  (error) => console.error('No se pudo cargar ' + config.modelUrl, error),
);

// El eje más largo del modelo pasa a ser el vertical y la pieza más pequeña (la punta) queda abajo.
function alinear(modelo) {
  const caja = new THREE.Box3().setFromObject(modelo);
  const lados = caja.getSize(new THREE.Vector3());
  if (lados.x >= lados.y && lados.x >= lados.z) modelo.rotation.z = Math.PI / 2;
  else if (lados.z > lados.y) modelo.rotation.x = -Math.PI / 2;
  modelo.updateMatrixWorld(true);

  let punta = null;
  let menor = Infinity;
  modelo.traverse((objeto) => {
    if (!objeto.isMesh) return;
    const cajaPieza = new THREE.Box3().setFromObject(objeto);
    const l = cajaPieza.getSize(new THREE.Vector3());
    const volumen = l.x * l.y * l.z;
    if (volumen < menor) {
      menor = volumen;
      punta = cajaPieza.getCenter(new THREE.Vector3());
    }
  });
  const centro = new THREE.Box3().setFromObject(modelo).getCenter(new THREE.Vector3());
  if (punta && punta.y > centro.y) orientado.rotation.z = Math.PI;
}

// El centro de la caja del modelo pasa al origen: el lápiz gira y flota alrededor de su propio centro.
function centrar() {
  const caja = new THREE.Box3().setFromObject(orientado);
  caja.getSize(tamano);
  orientado.position.sub(caja.getCenter(new THREE.Vector3()));
}

// Cámara según el tamaño del modelo y del área: el lápiz inclinado, en cualquier fase del giro, ocupa fillRatio
// del alto (o del ancho, si es lo que limita) sin deformarse.
function encuadrar(ancho, alto) {
  if (tamano.y === 0) return;
  const inclinacion = THREE.MathUtils.degToRad(config.tiltDegrees);
  const grosor = Math.max(tamano.x, tamano.z);
  const altoVisible = tamano.y * Math.cos(inclinacion) + grosor * Math.sin(inclinacion);
  const anchoVisible = tamano.y * Math.sin(inclinacion) + grosor;
  const fovVertical = THREE.MathUtils.degToRad(config.fov);
  const fovHorizontal = 2 * Math.atan(Math.tan(fovVertical / 2) * (ancho / alto));
  const distancia = Math.max(
    (altoVisible / config.fillRatio / 2) / Math.tan(fovVertical / 2),
    (anchoVisible / config.fillRatio / 2) / Math.tan(fovHorizontal / 2),
  );
  camera.aspect = ancho / alto;
  camera.near = distancia / 20;
  camera.far = distancia * 20;
  camera.position.set(0, distancia * 0.06, distancia);  // apenas por encima del centro: se intuye la cara superior
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  unidadesPorPixel = (2 * distancia * Math.tan(fovVertical / 2)) / alto;
}

function redimensionar() {
  const ancho = Math.max(1, canvas.clientWidth || window.innerWidth);
  const alto = Math.max(1, canvas.clientHeight || window.innerHeight);
  renderer.setSize(ancho, alto, false);
  encuadrar(ancho, alto);
  if (listo && !corriendo) renderer.render(scene, camera);
}
window.addEventListener('resize', redimensionar);
redimensionar();

// Bucle de render con tiempo delta: la velocidad no depende de los FPS. Tras una pausa, el delta se acota para que
// el lápiz no dé un salto.
const reloj = new THREE.Clock(false);
let corriendo = false;
let cuadro = 0;
let tiempo = 0;

function animar() {
  cuadro = requestAnimationFrame(animar);
  const dt = Math.min(reloj.getDelta(), 0.1);
  tiempo += dt;
  pivote.rotation.y += ((Math.PI * 2) / config.secondsPerTurn) * dt;
  pivote.position.y = Math.sin(tiempo * config.floatSpeed) * config.floatPixels * unidadesPorPixel;
  renderer.render(scene, camera);
}

function arrancar() {
  if (corriendo || !listo) return;
  corriendo = true;
  reloj.start();
  cuadro = requestAnimationFrame(animar);
}

function detener() {
  if (!corriendo) return;
  corriendo = false;
  cancelAnimationFrame(cuadro);
  reloj.stop();
}

// Pausa cuando el documento deja de verse (pestaña, ventana minimizada) y cuando MAUI lo pide (Pencil3DView.Pausar).
document.addEventListener('visibilitychange', () => (document.hidden ? detener() : arrancar()));

window.pencilViewer = {
  pause: detener,
  resume: arrancar,
  configure(opciones) {
    Object.assign(config, opciones || {});
    soporte.rotation.z = THREE.MathUtils.degToRad(config.tiltDegrees);
    redimensionar();
  },
};

// Puente MAUI ↔ WebView: el visor avisa cuando está listo. Windows aloja WebView2 por composición (puente
// chrome.webview); Android usa HybridWebView. Fuera de MAUI (un navegador) no hay puente y no pasa nada.
function avisar(mensaje) {
  try {
    if (window.chrome?.webview?.postMessage) window.chrome.webview.postMessage(mensaje);
    else if (window.HybridWebView?.SendRawMessage) window.HybridWebView.SendRawMessage(mensaje);
  } catch (_) { /* sin puente */ }
}
