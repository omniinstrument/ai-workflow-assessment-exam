#!/usr/bin/env python3
"""3D point cloud visualizer for synthetic_points.csv."""

from __future__ import annotations

import argparse
import csv
import math
import pathlib
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# geometry helpers (refs generate_data.py)
def _rotation_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> list[list[float]]:
    r, p, y = math.radians(roll_deg), math.radians(pitch_deg), math.radians(yaw_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def _forward(roll_deg: float, pitch_deg: float, yaw_deg: float) -> tuple[float, float, float]:
    R = _rotation_matrix(roll_deg, pitch_deg, yaw_deg)
    return (R[0][2], R[1][2], R[2][2])


def _tilt_from_neg_z(roll_deg: float, pitch_deg: float, yaw_deg: float) -> float:
    fx, fy, fz = _forward(roll_deg, pitch_deg, yaw_deg)
    norm = math.sqrt(fx * fx + fy * fy + fz * fz)
    cosine = max(-1.0, min(1.0, -fz / norm))
    return math.degrees(math.acos(cosine))


def _local_axes(
    roll_deg: float, pitch_deg: float, yaw_deg: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return (local_x, local_y) as world-space vectors (columns 0 and 1 of R)."""
    R = _rotation_matrix(roll_deg, pitch_deg, yaw_deg)
    lx = (round(R[0][0], 4), round(R[1][0], 4), round(R[2][0], 4))
    ly = (round(R[0][1], 4), round(R[1][1], 4), round(R[2][1], 4))
    return lx, ly

def load_points(csv_path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            x = float(row["x"])
            y = float(row["y"])
            z = float(row["z"])
            A = float(row["A"])
            roll = float(row["roll_deg"])
            pitch = float(row["pitch_deg"])
            yaw = float(row["yaw_deg"])

            tilt = _tilt_from_neg_z(roll, pitch, yaw)
            fx, fy, fz = _forward(roll, pitch, yaw)
            lx, ly = _local_axes(roll, pitch, yaw)

            a_err = abs(A - 50.0) > 5.0
            orient_err = tilt > 5.0
            problematic = a_err or orient_err

            rows.append({
                "id": i,
                "x": x, "y": y, "z": z,
                "A": round(A, 4),
                "roll_deg": round(roll, 4),
                "pitch_deg": round(pitch, 4),
                "yaw_deg": round(yaw, 4),
                "tilt_deg": round(tilt, 4),
                "forward_x": round(fx, 4),
                "forward_y": round(fy, 4),
                "forward_z": round(fz, 4),
                "local_x_x": lx[0], "local_x_y": lx[1], "local_x_z": lx[2],
                "local_y_x": ly[0], "local_y_y": ly[1], "local_y_z": ly[2],
                "a_error": a_err,
                "orient_error": orient_err,
                "problematic": problematic,
                "layer": "circle" if z > 1.0 else "grid",
            })
    return rows

app = FastAPI()
_points: list[dict[str, Any]] = []


@app.get("/api/points")
def get_points() -> JSONResponse:
    return JSONResponse(_points)


@app.get("/api/stats")
def get_stats() -> JSONResponse:
    total = len(_points)
    problematic = sum(1 for p in _points if p["problematic"])
    a_err = sum(1 for p in _points if p["a_error"])
    orient_err = sum(1 for p in _points if p["orient_error"])
    both = sum(1 for p in _points if p["a_error"] and p["orient_error"])
    return JSONResponse({
        "total": total,
        "problematic": problematic,
        "a_error_only": a_err - both,
        "orient_error_only": orient_err - both,
        "both_errors": both,
        "ok": total - problematic,
    })


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="synthetic_points.csv", help="CSV file to visualize")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    csv_path = pathlib.Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    global _points
    _points = load_points(csv_path)

    n_prob = sum(1 for p in _points if p["problematic"])
    print(f"Loaded {len(_points)} points ({n_prob} problematic)")
    print(f"Open http://{args.host}:{args.port}/ in your browser")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
