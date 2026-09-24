"""Lector de codigos de barras/QR con sincronizacion a Excel.

Uso:
    python reader.py                      # abre la webcam por defecto (indice 0)
    python reader.py --excel salida.xlsx  # cambia el archivo de salida
    python reader.py --camera 1           # usa otra camara
    python reader.py --no-window          # modo headless (sin ventana de video)

Cada codigo nuevo detectado se agrega como fila al Excel y el archivo se
guarda inmediatamente (sincronizacion en caliente). Un codigo ya visto
(mismo valor) no se vuelve a agregar.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Iterable

import cv2
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from pyzbar import pyzbar
from pyzbar.pyzbar import Decoded

DEFAULT_EXCEL_PATH = Path(__file__).parent / "codigos_leidos.xlsx"
HEADERS = ["codigo", "tipo", "fecha_hora"]


def load_or_create_workbook(excel_path: Path) -> tuple[Workbook, Worksheet]:
    if excel_path.exists():
        wb = load_workbook(excel_path)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Codigos"
        ws.append(HEADERS)
    return wb, ws


def existing_codes(ws: Worksheet) -> set[str]:
    return {row[0] for row in ws.iter_rows(min_row=2, values_only=True) if row and row[0]}


def sync_code(ws: Worksheet, code: str, code_type: str, seen: set[str]) -> bool:
    """Agrega el codigo a la hoja si no se habia visto antes. Devuelve True si lo agrego."""
    if code in seen:
        return False
    ws.append([code, code_type, dt.datetime.now().isoformat(timespec="seconds")])
    seen.add(code)
    return True


def decode_frame(frame) -> list[Decoded]:
    return pyzbar.decode(frame)


def draw_detections(frame, detections: Iterable[Decoded]) -> None:
    for d in detections:
        x, y, w, h = d.rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = d.data.decode("utf-8", errors="replace")
        cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)


def run(excel_path: Path, camera_index: int = 0, show_window: bool = True) -> None:
    wb, ws = load_or_create_workbook(excel_path)
    seen = existing_codes(ws)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir la camara {camera_index}")

    print("Lector de codigos iniciado. Presiona 'q' en la ventana de video para salir (Ctrl+C en modo --no-window).")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            detections = decode_frame(frame)
            for d in detections:
                code = d.data.decode("utf-8", errors="replace")
                if sync_code(ws, code, d.type, seen):
                    wb.save(excel_path)
                    print(f"Nuevo codigo guardado: {code} ({d.type})")

            if show_window:
                draw_detections(frame, detections)
                cv2.imshow("Lector de codigos - 'q' para salir", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()
        wb.save(excel_path)
        print(f"Excel actualizado: {excel_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--excel", type=Path, default=DEFAULT_EXCEL_PATH, help="Ruta al archivo Excel de salida (default: codigos_leidos.xlsx)")
    parser.add_argument("--camera", type=int, default=0, help="Indice de la camara a usar (default: 0)")
    parser.add_argument("--no-window", action="store_true", help="No mostrar la ventana de video (modo headless)")
    args = parser.parse_args()

    run(args.excel, camera_index=args.camera, show_window=not args.no_window)


if __name__ == "__main__":
    main()
