"""
Los límites y los tiempos de la cola de medios. Salen de `settings` (variables `AVACOM_COLA_*`, ver `settings.py`); aquí sólo viven con sus valores por
defecto para que la aplicación no dependa del framework.

Dos reglas guían los tiempos:
  · Nada de lo que hace la cola puede hacer que un medio falle donde antes funcionaba. Si el recurso no está listo a tiempo, la petición se sirve en paso a
    través desde la fuente, como siempre, y la preparación sigue en segundo plano.
  · Los clientes tienen paciencia corta: el audio se rinde a los 10-12 s sin datos y la imagen a los 10 s. Por eso `espera_inicio_seg` es menor que eso.
"""
from __future__ import annotations

from dataclasses import dataclass

MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class Config:
    activa: bool = True                           # False: todo en paso a través, como antes de la cola
    carpeta: str = ""                             # dónde viven los bytes
    max_bytes: int = 4 * GIB                      # tope de la caché en disco
    libre_min_bytes: int = 1 * GIB                # espacio que debe quedar libre en el disco
    hilos: int = 3                                # descargas simultáneas desde la fuente; 0 = se hacen en la propia petición (pruebas)
    transferencias: int = 24                      # transferencias simultáneas hacia las tabletas
    ancho_entrada_bps: int = 0                    # tope global fuente → nodo (bytes por segundo); 0 = sin tope
    ancho_salida_bps: int = 0                     # tope global nodo → tabletas (bytes por segundo); 0 = sin tope
    revalidar_seg: int = 60                       # cada cuánto se le pregunta a la biblioteca si el curso sigue y en qué versión
    espera_inicio_seg: float = 6.0                # lo que espera una petición a que el recurso empiece a llegar antes de servirse en paso a través
    espera_paquete_seg: float = 120.0             # lo que espera la preparación de un paquete de estudio a que termine un recurso
    espera_cupo_seg: float = 20.0                 # lo que espera una transferencia a que haya un cupo libre antes de enviarse igual
    estancado_seg: float = 30.0                   # una lectura sin avance durante este tiempo se corta
    adelanto_max_bytes: int = 32 * MIB            # un salto más lejos que esto de lo ya descargado se sirve en paso a través
    reintentos: int = 3
    pausa_reintento_seg: float = 1.0              # la espera entre intentos crece al doble cada vez (1, 2, 4… hasta 8 s)
    pequeno_bytes: int = 256 * 1024               # lo que cabe en memoria (LocMemCache) además del disco
    proteger_seg: int = 300                       # lo usado hace menos que esto no se expulsa
    reintentar_fallido_seg: int = 60
    reintentar_sin_espacio_seg: int = 600
    servir_sin_biblioteca: bool = False           # True: con Contenido cerrado se sirve lo que ya está en la caché
    max_preparar: int = 60                        # recursos por llamada de preparación
    vigencia_proyeccion_seg: int = 1800
    memoria_seg: int = 600                        # cuánto vive un recurso en LocMemCache
    # Fuentes que entregan los bytes ya hechos en memoria (el manifiesto de ejemplo, sólo para pruebas y desarrollo) en vez de un flujo: se responden en una
    # pieza, con su cuerpo, igual que antes de la cola. La biblioteca de verdad (AVACOM Contenido) siempre se responde por flujo.
    fuentes_en_una_pieza: tuple[str, ...] = ("ejemplo",)
