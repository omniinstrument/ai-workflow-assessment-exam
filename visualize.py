#!/usr/bin/env python3
"""3D point cloud visualizer for synthetic_points.csv."""

from __future__ import annotations

import argparse
import csv
import json
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


def compute_stats(points: list[dict[str, Any]]) -> dict[str, int]:
    total = len(points)
    problematic = sum(1 for p in points if p["problematic"])
    a_err = sum(1 for p in points if p["a_error"])
    orient_err = sum(1 for p in points if p["orient_error"])
    both = sum(1 for p in points if p["a_error"] and p["orient_error"])
    return {
        "total": total,
        "problematic": problematic,
        "a_error_only": a_err - both,
        "orient_error_only": orient_err - both,
        "both_errors": both,
        "ok": total - problematic,
    }


def _json_for_html_script(data: Any) -> str:
    """Serialize JSON safe to embed inside <script>...</script> (no raw </)."""
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def write_standalone_html(
    *,
    template_path: pathlib.Path,
    out_path: pathlib.Path,
    csv_label: str,
    points: list[dict[str, Any]],
) -> None:
    stats = compute_stats(points)
    template = template_path.read_text(encoding="utf-8")
    marker_pts = '<script type="application/json" id="pcv-embed-points"></script>'
    marker_st = '<script type="application/json" id="pcv-embed-stats"></script>'
    if marker_pts not in template or marker_st not in template:
        raise SystemExit(
            f"Template {template_path} must contain empty embed markers:\n  {marker_pts}\n  {marker_st}"
        )
    pts_json = _json_for_html_script(points)
    stats_json = _json_for_html_script(stats)
    template = template.replace(
        marker_pts,
        f'<script type="application/json" id="pcv-embed-points">{pts_json}</script>',
        1,
    )
    template = template.replace(
        marker_st,
        f'<script type="application/json" id="pcv-embed-stats">{stats_json}</script>',
        1,
    )
    template = template.replace(
        '<p id="csv-name">synthetic_points.csv</p>',
        f'<p id="csv-name">{csv_label}</p>',
        1,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template, encoding="utf-8")


app = FastAPI()
_points: list[dict[str, Any]] = []


@app.get("/api/points")
def get_points() -> JSONResponse:
    return JSONResponse(_points)


@app.get("/api/stats")
def get_stats() -> JSONResponse:
    return JSONResponse(compute_stats(_points))


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Standalone (no FastAPI): write a single HTML file with data embedded, then serve it "
            "over HTTP (ES modules), e.g.  python -m http.server 8000  and open the file URL."
        ),
    )
    parser.add_argument("--csv", default="synthetic_points.csv", help="CSV file to visualize")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--standalone",
        nargs="?",
        const="standalone.html",
        metavar="OUT.html",
        help=(
            "Write self-contained HTML (embedded points + stats); no API server. "
            "Optional output path (default: standalone.html)."
        ),
    )
    args = parser.parse_args()

    csv_path = pathlib.Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    points = load_points(csv_path)
    n_prob = sum(1 for p in points if p["problematic"])
    print(f"Loaded {len(points)} points ({n_prob} problematic)")

    if args.standalone is not None:
        out_path = pathlib.Path(args.standalone)
        template_path = pathlib.Path(__file__).resolve().parent / "static" / "index.html"
        write_standalone_html(
            template_path=template_path,
            out_path=out_path,
            csv_label=csv_path.name,
            points=points,
        )
        print(f"Wrote {out_path.resolve()}")
        return

    global _points
    _points = points

    print(f"Open http://{args.host}:{args.port}/ in your browser")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
