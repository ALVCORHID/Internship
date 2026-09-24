# Lector de codigos -> Excel

Script en Python que abre la webcam, detecta codigos de barras y QR en vivo
(usando OpenCV + pyzbar) y sincroniza cada codigo nuevo a un archivo Excel.

Este proyecto es independiente del pipeline de ML de FlyRank del resto del
repo; no comparte datos ni dependencias con `scripts/` o `notebooks/`.

## Instalacion

```bash
cd code-reader
pip install -r requirements.txt
```

`pyzbar` depende de la libreria nativa `zbar`:

- **Linux**: instalar el paquete del sistema antes de usar pyzbar, por ejemplo
  `sudo apt-get install libzbar0` (Debian/Ubuntu).
- **Windows / macOS**: los wheels de pyzbar ya incluyen la libreria, no hace
  falta instalar nada extra.

## Uso

```bash
python reader.py                                          # webcam local, indice 0, muestra ventana de video
python reader.py --source 1                                # usar otra camara local
python reader.py --excel salida.xlsx                        # elegir el archivo Excel de salida
python reader.py --no-window                                # modo headless, sin ventana de video (solo consola)
python reader.py --source http://192.168.0.10:8080/video   # usar el celular como camara (ver abajo)
```

Presiona `q` en la ventana de video (o `Ctrl+C` en modo `--no-window`) para
detener el programa. El Excel se guarda automaticamente en cada codigo nuevo,
asi que se puede cortar el proceso en cualquier momento sin perder lecturas.

Por defecto el Excel se guarda en `code-reader/codigos_leidos.xlsx` con las
columnas `codigo`, `tipo` y `fecha_hora`. Si el archivo ya existe, el script
lo reabre y sigue agregando filas al final (no lo sobreescribe). Un mismo
codigo nunca se vuelve a agregar dos veces (ni entre corridas ni dentro de la
misma corrida): por consola se ve `Nuevo codigo guardado: ...` la primera vez
y `Codigo duplicado, ya estaba registrado ...` las siguientes.

## Usar el celular como camara (app IP Webcam)

1. En el celular (Android), instala la app **IP Webcam** (Google Play).
2. Conecta el celular a la **misma red wifi** que la computadora donde vas a
   correr `reader.py`.
3. Abri la app, tocá "Start server". Te va a mostrar una URL tipo
   `http://192.168.0.10:8080`.
4. En la computadora, corré:
   ```bash
   python reader.py --source http://192.168.0.10:8080/video
   ```
   (usando la IP que te muestra la app, agregando `/video` al final).

Para iPhone, apps como **DroidCam** o **iVCam** instalan un driver de camara
virtual en la PC: en ese caso el celular aparece como una camara local mas,
y se usa `--source <indice>` (probá `0`, `1`, `2`, ...) en vez de una URL.

## Tests

Los tests no requieren camara: generan una imagen de QR en memoria y prueban
la logica de deteccion y sincronizacion con Excel.

```bash
pip install -r requirements.txt pytest qrcode pillow
pytest tests/
```
