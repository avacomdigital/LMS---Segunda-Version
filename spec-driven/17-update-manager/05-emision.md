# 17 · Update Manager (MOD-017) · Emisión de paquetes `.avupd` (manual del emisor, sin claves)

| Campo | Valor |
|---|---|
| Para quién | Quien en AVACOM firma y entrega paquetes de actualización. **No es para el colegio**: el emisor no viaja en ningún instalador (`Build-Installer.ps1` falla si `tools\actualizacion` o `actualizacion\tests` entran en el paquete). |
| Herramienta | `tools\actualizacion\` (`avacom-actualizacion.bat`, Python del backend, sin red). Modelo: `tools\licencias\` y [spec-driven/15-licenciamiento/05-emision.md](../15-licenciamiento/05-emision.md). |
| Este documento | **No contiene ninguna llave**, ni de pruebas ni de producción. |

## 1 · Reglas que no se rompen

1. **La llave privada de publicación** (`.avkey`, Ed25519, cifrada con una frase de paso de 16 caracteres o más) vive en una memoria USB, nunca en el repositorio, en un correo ni en la nube.
2. Se trabaja en un equipo **sin internet**.
3. **El `kid` de publicación no es el de licencias.** Son otra ceremonia y otras llaves (Q-U8): una llave de licencias no firma paquetes y al revés.
4. La **serie** de cada módulo sólo sube. Un paquete con una serie menor que la instalada se rechaza en el nodo (no se degrada, P-16); igual es `ya_aplicado`.
5. **Toda migración declara su reverso** (otra migración o `zero`, BR-015). El emisor no emite sin él.
6. Un paquete nunca lleva el `Host`, el Python embebido, `backend.env`, las claves de datos ni `backend\biblioteca\`, ni archivos de apps que no declara (D-2). El emisor y el nodo lo rechazan.
7. Hasta la **ceremonia de llaves** `backend\actualizacion\claves\produccion.json` está vacío y **ningún nodo de producción acepta paquetes** (`kid_desconocido`). Es lo previsto.

## 2 · La ceremonia de llaves (pendiente del CTO)

Una vez, en el equipo de emisión sin red:

```text
avacom-actualizacion llaves nueva --kid upd-2026-1 --salida F:\claves
avacom-actualizacion llaves nodo --publica F:\claves\upd-2026-1.pub
```

La primera crea `upd-2026-1.avkey` (privada, cifrada) y `upd-2026-1.pub`. La segunda imprime la **entrada pública** que se pega en `backend\actualizacion\claves\produccion.json`, con al menos **dos** llaves (una vigente y una de relevo). Esa entrada **sí** se commitea y viaja en el instalador; la `.avkey` jamás. Después de la ceremonia hay que reconstruir el instalador: un nodo ya instalado sólo conoce las llaves con las que se instaló.

## 3 · Armar y firmar un paquete

```text
avacom-actualizacion plantilla > paquete.json
avacom-actualizacion emitir --descripcion paquete.json --privada F:\claves\upd-2026-1.avkey --salida reportes-1.4.0.avupd
avacom-actualizacion verificar reportes-1.4.0.avupd --publica F:\claves\upd-2026-1.pub
avacom-actualizacion ver reportes-1.4.0.avupd
```

`paquete.json` (ejemplo completo en `tools\actualizacion\ejemplo\paquete.json`) dice qué módulos cambian: `nombre`, `version`, `version_datos`, `version_contrato`, `serie`, `cambia_contrato`, `requiere` (contrato mínimo de otros módulos), `migraciones` con su reverso y los archivos de `backend\<app>\` que se incluyen. El emisor lee esos archivos de `backend\`, calcula tamaño y SHA-256, escribe el manifiesto, lo firma y empaqueta en el contenedor canónico sin comprimir. **Antes de escribir el archivo lo verifica como lo haría un nodo**: si el nodo lo rechazaría, no lo escribe.

## 4 · Antes de entregar

- [ ] `verificar` con la llave pública correcta responde bien.
- [ ] La serie de cada módulo es **mayor** que la del último paquete entregado.
- [ ] Cada migración nueva declara su reverso y el reverso se probó (migrar hacia atrás sobre una copia de la base).
- [ ] Si el paquete **cambia el contrato de red con Student**, `cambia_contrato` es verdadero, `requisitos.cliente_minimo` lo dice y `installer\version.json` sube (R-13).
- [ ] El paquete se **ensayó** en un nodo de pruebas: importar, aplicar, ver `aplicado`, revertir con una nota, ver `revertido`.
- [ ] Se entrega en una memoria USB: el archivo `.avupd` en la raíz o en `AVACOM\`. El técnico no escribe nada (P-11).

## 5 · Qué hace el nodo con el paquete (para saber qué esperar)

Verifica firma, forma, rutas y SHA-256 sin escribir un byte; comprueba compatibilidad de módulos y contratos y espacio; y recién entonces lo ofrece en OPS. Aplicar exige cero clases y lo hace el `Host` con el servicio parado (ver [04-operacion.md](04-operacion.md)). Los motivos de rechazo son el catálogo cerrado de [02-api.md](02-api.md) §2.

## 6 · Lo que este manual no cubre

- El paquete portátil del emisor (`Build-Emisor.ps1`, como el de licencias): hoy el `.bat` usa el Python del backend del repositorio. Queda pendiente.
- La rotación y revocación de llaves de publicación: un `kid` retirado se quita de `produccion.json` y se reconstruye el instalador. No hay lista de revocación en línea (el aula no tiene internet).
