import sys
from pathlib import Path

import numpy as np
import qrcode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reader import decode_frame, existing_codes, load_or_create_workbook, sync_code


def make_qr_frame(data: str) -> np.ndarray:
    img = qrcode.make(data).convert("RGB")
    return np.array(img)


def test_decode_frame_reads_qr_code():
    frame = make_qr_frame("HELLO-123")
    detections = decode_frame(frame)

    assert len(detections) == 1
    assert detections[0].data.decode("utf-8") == "HELLO-123"


def test_sync_code_skips_duplicates(tmp_path):
    excel_path = tmp_path / "codigos.xlsx"
    wb, ws = load_or_create_workbook(excel_path)
    seen = existing_codes(ws)

    assert sync_code(ws, "ABC123", "QRCODE", seen) is True
    assert sync_code(ws, "ABC123", "QRCODE", seen) is False
    wb.save(excel_path)

    _, ws2 = load_or_create_workbook(excel_path)
    rows = list(ws2.iter_rows(min_row=2, values_only=True))
    assert len(rows) == 1
    assert rows[0][0] == "ABC123"


def test_load_or_create_workbook_reopens_existing_file(tmp_path):
    excel_path = tmp_path / "codigos.xlsx"
    wb, ws = load_or_create_workbook(excel_path)
    sync_code(ws, "X1", "CODE128", existing_codes(ws))
    wb.save(excel_path)

    _, ws2 = load_or_create_workbook(excel_path)
    assert existing_codes(ws2) == {"X1"}
