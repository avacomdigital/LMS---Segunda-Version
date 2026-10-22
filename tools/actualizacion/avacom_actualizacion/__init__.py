"""
AVACOM Emisor de Paquetes de Actualización (MOD-017 · Update Manager, P-03).

Herramienta de consola para el personal de AVACOM: arma y firma un paquete `.avupd` (contenedor canónico sin comprimir, manifiesto firmado con Ed25519 y SHA-256 por archivo) con
la llave PRIVADA de publicación, y lo verifica como lo verificaría un nodo. NUNCA viaja en el instalador del colegio ni en el APK, y no abre ninguna conexión de red.

Usa EXACTAMENTE el dominio del nodo (`actualizacion.dominio`: contenedor, firma, manifiesto, paquete) para que lo que se emite y lo que el nodo lee no puedan diferir. Jamás importa
`actualizacion.tests.*` (ahí vive el emisor de PRUEBAS, con llaves de desarrollo): una prueba comprueba que ningún archivo de esta carpeta las contiene.
"""

__version__ = "1.0.0"
