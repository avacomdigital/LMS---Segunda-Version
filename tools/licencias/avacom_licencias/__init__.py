"""
AVACOM Emisor de Licencias (el «keygen» interno de MOD-018).

Herramienta de consola para el personal de AVACOM: lee la solicitud (`.avreq`) que genera el computador maestro del colegio, firma una licencia (`.avlic`) con la llave privada de
emisión y la entrega con una hoja de texto. NUNCA viaja en el instalador del colegio ni en el APK, y no abre ninguna conexión de red.

Usa EXACTAMENTE el dominio del nodo (`licenciamiento.dominio`: formato, firma, huella, estado) para que lo que se emite y lo que el nodo lee no puedan diferir. Jamás importa
`licenciamiento.tests.*` (ahí vive el emisor de PRUEBAS, con llaves de desarrollo): una prueba comprueba que ningún archivo de esta carpeta las contiene.
"""

__version__ = "1.0.0"
