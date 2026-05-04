#!/usr/bin/env python3

"""Generate synthetic point/orientation CSV data for the workspace."""

from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path


SEED = 42
SQUARE_GRID_SIZE = 10
SQUARE_SIDE = 10.0
CIRCLE_DIAMETER = 10.0
CIRCLE_Z = 3.0
SQUARE_Z = 0.0
TARGET_A = 50.0
NORMAL_A_MAX_DELTA = 4.0
ERROR_A_MIN_DELTA = 5.5
ERROR_A_MAX_DELTA = 10.0
MAX_NORMAL_TILT_DEG = 4.0
MIN_ERROR_TILT_DEG = 6.0
MAX_ERROR_TILT_DEG = 12.0
ROLL_ERROR_DEG = 3.0
TARGET_ERROR_RATIO = 0.20
MIN_ERROR_RATIO = 0.10


def frange(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 6))
        current += step
    return values


def normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    return tuple(component / norm for component in vector)


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def rodrigues_rotate(
    vector: tuple[float, float, float],
    axis: tuple[float, float, float],
    angle_rad: float,
) -> tuple[float, float, float]:
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    axis_dot = dot(axis, vector)
    axis_cross = cross(axis, vector)
    return (
        vector[0] * cos_a + axis_cross[0] * sin_a + axis[0] * axis_dot * (1.0 - cos_a),
        vector[1] * cos_a + axis_cross[1] * sin_a + axis[1] * axis_dot * (1.0 - cos_a),
        vector[2] * cos_a + axis_cross[2] * sin_a + axis[2] * axis_dot * (1.0 - cos_a),
    )


def euler_zyx_from_forward(
    forward: tuple[float, float, float],
    roll_noise_deg: float,
) -> tuple[float, float, float]:
    # Treat the local +z axis as the viewing direction and generate a
    # right-handed basis that looks approximately toward world -z.
    reference_x = (1.0, 0.0, 0.0)
    projected_x = tuple(
        reference_x[i] - dot(reference_x, forward) * forward[i] for i in range(3)
    )
    if math.sqrt(dot(projected_x, projected_x)) < 1e-8:
        reference_x = (0.0, 1.0, 0.0)
        projected_x = tuple(
            reference_x[i] - dot(reference_x, forward) * forward[i] for i in range(3)
        )

    local_x = normalize(projected_x)
    local_y = normalize(cross(forward, local_x))

    roll_rad = math.radians(roll_noise_deg)
    local_x = normalize(rodrigues_rotate(local_x, forward, roll_rad))
    local_y = normalize(rodrigues_rotate(local_y, forward, roll_rad))

    rotation = (
        (local_x[0], local_y[0], forward[0]),
        (local_x[1], local_y[1], forward[1]),
        (local_x[2], local_y[2], forward[2]),
    )

    pitch = math.asin(max(-1.0, min(1.0, -rotation[2][0])))
    roll = math.atan2(rotation[2][1], rotation[2][2])
    yaw = math.atan2(rotation[1][0], rotation[0][0])

    return (
        round(math.degrees(roll), 6),
        round(math.degrees(pitch), 6),
        round(math.degrees(yaw), 6),
    )


def build_forward(tilt_deg: float, azimuth_deg: float) -> tuple[float, float, float]:
    tilt_rad = math.radians(tilt_deg)
    azimuth_rad = math.radians(azimuth_deg)
    return (
        math.sin(tilt_rad) * math.cos(azimuth_rad),
        math.sin(tilt_rad) * math.sin(azimuth_rad),
        -math.cos(tilt_rad),
    )


def build_a_value(rng: random.Random, is_error: bool) -> float:
    if is_error:
        delta = rng.uniform(ERROR_A_MIN_DELTA, ERROR_A_MAX_DELTA)
        delta *= rng.choice((-1.0, 1.0))
    else:
        delta = rng.uniform(-NORMAL_A_MAX_DELTA, NORMAL_A_MAX_DELTA)
    return round(TARGET_A + delta, 6)


def build_pose(
    rng: random.Random,
    is_orientation_error: bool,
) -> tuple[float, float, float]:
    if is_orientation_error:
        tilt_deg = rng.uniform(MIN_ERROR_TILT_DEG, MAX_ERROR_TILT_DEG)
    else:
        tilt_deg = rng.uniform(0.0, MAX_NORMAL_TILT_DEG)
    azimuth_deg = rng.uniform(-180.0, 180.0)
    forward = build_forward(tilt_deg, azimuth_deg)
    roll_noise_deg = rng.uniform(-ROLL_ERROR_DEG, ROLL_ERROR_DEG)
    return euler_zyx_from_forward(forward, roll_noise_deg)


def generate_square_points() -> list[tuple[float, float, float]]:
    step = SQUARE_SIDE / (SQUARE_GRID_SIZE - 1)
    coords = [round((-SQUARE_SIDE / 2.0) + index * step, 6) for index in range(SQUARE_GRID_SIZE)]
    points: list[tuple[float, float, float]] = []
    for x in coords:
        for y in coords:
            points.append((round(x, 6), round(y, 6), SQUARE_Z))
    return points


def generate_circle_points() -> list[tuple[float, float, float]]:
    radius = CIRCLE_DIAMETER / 2.0
    candidates = frange(-radius, radius, 1.0)
    points: list[tuple[float, float, float]] = []
    for x in candidates:
        for y in candidates:
            if x * x + y * y > radius * radius + 1e-9:
                continue
            points.append((round(x, 6), round(y, 6), CIRCLE_Z))
    return points


def assign_error_modes(
    count: int,
    rng: random.Random,
) -> tuple[set[int], set[int]]:
    min_error_count = math.ceil(count * MIN_ERROR_RATIO)
    target_error_count = max(math.ceil(count * TARGET_ERROR_RATIO), min_error_count)
    indices = list(range(count))
    rng.shuffle(indices)

    orientation_error_count = target_error_count // 3
    a_error_count = target_error_count // 3
    both_error_count = target_error_count - orientation_error_count - a_error_count

    both_indices = set(indices[:both_error_count])
    orientation_only_indices = set(
        indices[both_error_count : both_error_count + orientation_error_count]
    )
    a_only_indices = set(
        indices[
            both_error_count
            + orientation_error_count : both_error_count
            + orientation_error_count
            + a_error_count
        ]
    )

    orientation_error_indices = both_indices | orientation_only_indices
    a_error_indices = both_indices | a_only_indices
    return orientation_error_indices, a_error_indices


def generate_rows(rng: random.Random) -> list[dict[str, float]]:
    points = generate_square_points() + generate_circle_points()
    orientation_error_indices, a_error_indices = assign_error_modes(len(points), rng)

    rows: list[dict[str, float]] = []
    for index, (x, y, z) in enumerate(points):
        roll_deg, pitch_deg, yaw_deg = build_pose(
            rng,
            is_orientation_error=index in orientation_error_indices,
        )
        rows.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "A": build_a_value(rng, is_error=index in a_error_indices),
                "roll_deg": roll_deg,
                "pitch_deg": pitch_deg,
                "yaw_deg": yaw_deg,
            }
        )
    return rows


def generate_rows_for_count(count: int, rng: random.Random) -> list[dict[str, float]]:
    """Build *count* rows with the same error/A/pose rules as the fixed grid, random (x,y,z) in workspace."""
    half = SQUARE_SIDE / 2.0
    radius = CIRCLE_DIAMETER / 2.0
    orientation_error_indices, a_error_indices = assign_error_modes(count, rng)
    rows: list[dict[str, float]] = []
    for index in range(count):
        use_circle_z = rng.random() < 0.45
        if use_circle_z:
            z = CIRCLE_Z
            for _ in range(120):
                x = round(rng.uniform(-radius, radius), 6)
                y = round(rng.uniform(-radius, radius), 6)
                if x * x + y * y <= radius * radius + 1e-9:
                    break
            else:
                x, y = 0.0, 0.0
        else:
            z = SQUARE_Z
            x = round(rng.uniform(-half, half), 6)
            y = round(rng.uniform(-half, half), 6)
        roll_deg, pitch_deg, yaw_deg = build_pose(
            rng,
            is_orientation_error=index in orientation_error_indices,
        )
        rows.append(
            {
                "x": x,
                "y": y,
                "z": z,
                "A": build_a_value(rng, is_error=index in a_error_indices),
                "roll_deg": roll_deg,
                "pitch_deg": pitch_deg,
                "yaw_deg": yaw_deg,
            }
        )
    return rows


def rotation_matrix_from_euler_zyx(
    roll_deg: float,
    pitch_deg: float,
    yaw_deg: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    yaw = math.radians(yaw_deg)

    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def forward_from_euler_zyx(
    roll_deg: float,
    pitch_deg: float,
    yaw_deg: float,
) -> tuple[float, float, float]:
    rotation = rotation_matrix_from_euler_zyx(roll_deg, pitch_deg, yaw_deg)
    return (rotation[0][2], rotation[1][2], rotation[2][2])


def angle_from_negative_z_deg(forward: tuple[float, float, float]) -> float:
    negative_z = (0.0, 0.0, -1.0)
    cosine = max(-1.0, min(1.0, dot(normalize(forward), negative_z)))
    return math.degrees(math.acos(cosine))


def count_error_rows(rows: list[dict[str, float]]) -> int:
    error_count = 0
    for row in rows:
        forward = forward_from_euler_zyx(
            row["roll_deg"],
            row["pitch_deg"],
            row["yaw_deg"],
        )
        is_orientation_error = angle_from_negative_z_deg(forward) > 5.0
        is_a_error = abs(row["A"] - TARGET_A) > 5.0
        if is_orientation_error or is_a_error:
            error_count += 1
    return error_count


def write_rows(output_path: Path, rows: list[dict[str, float]]) -> None:
    fieldnames = ["x", "y", "z", "A", "roll_deg", "pitch_deg", "yaw_deg"]
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="synthetic_points.csv",
        help="Path to the CSV file to create.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(SEED)
    rows = generate_rows(rng)
    output_path = Path(args.output)
    write_rows(output_path, rows)
    error_count = count_error_rows(rows)
    error_ratio = error_count / len(rows)
    print(
        f"Wrote {len(rows)} rows to {output_path} "
        f"with {error_count} error rows ({error_ratio:.1%})"
    )


if __name__ == "__main__":
    main()
