// Degradado de `material_pantalla_colores`. El GLB no trae el degradado horneado (el material sale sin textura y con color base blanco), asi que se genera
// aqui, con los colores de config/face-animations.json (`screen`), y se pone como textura base de ESE material y solo de ese. El resto del material
// (rugosidad 0, metalico 0, doble cara...) queda como lo exporto Blender.
import * as THREE from 'three';
import { mapaDeLaCaraFrontal } from './face-animation.js';

/** Dibuja el degradado lineal en un canvas. angleDeg al estilo CSS: 0 = hacia arriba, 90 = hacia la derecha, 180 = hacia abajo. */
function dibujar(gradient, size) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const a = THREE.MathUtils.degToRad(gradient.angleDeg ?? 180);
  const dx = Math.sin(a), dy = -Math.cos(a);
  const largo = Math.abs(size * dx) + Math.abs(size * dy);       // largo de la linea de un degradado CSS en un cuadrado
  const c = size / 2;
  const g = ctx.createLinearGradient(c - (dx * largo) / 2, c - (dy * largo) / 2, c + (dx * largo) / 2, c + (dy * largo) / 2);
  const stops = gradient.stops;
  stops.forEach((s, i) => g.addColorStop(typeof s === 'string' ? i / (stops.length - 1) : s.pos, typeof s === 'string' ? s : s.color));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return canvas;
}

/**
 * Pone el degradado en el material de la pantalla. Devuelve un resumen para el diagnostico.
 * Si el GLB algun dia trae el degradado horneado (el material ya tiene textura), no se toca nada.
 */
export function aplicarDegradadoDePantalla(mesh, cfg, frontNormal = [1, 0, 0], up = [0, 1, 0]) {
  const m = mesh.material;
  if (!cfg?.gradient?.stops?.length) return { aplicado: false, motivo: 'sin degradado configurado' };
  if (m.map || m.emissiveMap) return { aplicado: false, motivo: 'el GLB ya trae textura en el material' };

  const mapa = mapaDeLaCaraFrontal(mesh.geometry, frontNormal, up);
  const tex = new THREE.CanvasTexture(dibujar(cfg.gradient, cfg.gradient.size ?? 512));
  tex.flipY = false;                                  // convencion glTF: la fila 0 del canvas es el borde superior (t = 0)
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;   // los cantos del cubo (UV fuera de la cara frontal) toman el color del borde
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  tex.matrixAutoUpdate = false;
  tex.matrix.copy(mapa.inverse);                      // UV del cubo -> (s, t) de la cara frontal, vista de frente
  tex.needsUpdate = true;
  m.map = tex;                                        // color base blanco (1,1,1) x degradado = el degradado
  m.needsUpdate = true;
  return { aplicado: true, colores: cfg.gradient.stops.map((s) => (typeof s === 'string' ? s : s.color)), anguloGrados: cfg.gradient.angleDeg ?? 180 };
}
