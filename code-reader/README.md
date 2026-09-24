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
python reader.py                      # webcam por defecto (indice 0), muestra ventana de video
python reader.py --camera 1           # usar otra camara
python reader.py --excel salida.xlsx  # elegir el archivo Excel de salida
python reader.py --no-window          # modo headless, sin ventana de video (solo consola)
```

Presiona `q` en la ventana de video (o `Ctrl+C` en modo `--no-window`) para
detener el programa. El Excel se guarda automaticamente en cada codigo nuevo,
asi que se puede cortar el proceso en cualquier momento sin perder lecturas.

Por defecto el Excel se guarda en `code-reader/codigos_leidos.xlsx` con las
columnas `codigo`, `tipo` y `fecha_hora`. Si el archivo ya existe, el script
lo reabre y sigue agregando filas al final (no lo sobreescribe); un mismo
codigo no se vuelve a agregar dos veces.

## Tests

Los tests no requieren camara: generan una imagen de QR en memoria y prueban
la logica de deteccion y sincronizacion con Excel.

```bash
pip install -r requirements.txt pytest qrcode pillow
pytest tests/
```
