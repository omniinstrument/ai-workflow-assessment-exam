#!/usr/bin/env python3
"""Benchmark visualize.py: micro timings, scaled point counts, sequential-load degradation.

Examples (repo root):
  python3 bench_visualize.py
  python3 bench_visualize.py --repeat 80 --subprocess
  python3 bench_visualize.py --scale 181,2000,10000,50000
  python3 bench_visualize.py --scale-min 500 --scale-max 200000 --scale-mult 2 --scale-stop-ms 250
  python3 bench_visualize.py --degrade-loads 800 --degrade-window 100 --degrade-points 20000
  python3 bench_visualize.py --synth-seed 7 --scale 1000,5000
"""

from __future__ import annotations

import argparse
import os
import pathlib
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence

import generate_data as gd
import visualize as vis


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:8.3f} ms"


def rss_peak_mb() -> float:
    """Peak RSS (platform heuristic: Linux KiB, macOS bytes)."""
    try:
        import resource

        v = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if v > 1e9:
            return v / (1024 * 1024)
        return v / 1024.0
    except Exception:
        return 0.0


def bench(fn: Callable[[], object], *, repeat: int, warmup: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


def percentile(sorted_samples: list[float], p: float) -> float:
    if not sorted_samples:
        return 0.0
    k = (len(sorted_samples) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_samples) - 1)
    if f == c:
        return sorted_samples[f]
    return sorted_samples[f] + (sorted_samples[c] - sorted_samples[f]) * (k - f)


def print_row(label: str, samples: list[float], *, note: str = "") -> None:
    s = sorted(samples)
    med = statistics.median(samples)
    mn, mx = s[0], s[-1]
    mean = statistics.mean(samples)
    sd = statistics.stdev(samples) if len(samples) > 1 else 0.0
    p95 = percentile(s, 95)
    extra = f"  {note}" if note else ""
    print(
        f"{label:32}  n={len(samples):4}  "
        f"min={fmt_ms(mn)}  p50={fmt_ms(med)}  p95={fmt_ms(p95)}  max={fmt_ms(mx)}  "
        f"mean={fmt_ms(mean)}  σ={fmt_ms(sd)}{extra}"
    )


def median_of(fn: Callable[[], object], *, repeats: int, warmup: int) -> float:
    for _ in range(warmup):
        fn()
    times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def write_random_synth_csv(n: int, dest: pathlib.Path, seed: int) -> None:
    """Write *n* random synthetic rows (generate_data rules) via generate_data.write_rows."""
    rng = random.Random(seed)
    rows = gd.generate_rows_for_count(n, rng)
    gd.write_rows(dest, rows)


def remove_bench_csvs(*dirs: pathlib.Path, pid: int | None = None) -> None:
    """Remove temp bench CSVs for this process (best-effort, idempotent)."""
    pid = os.getpid() if pid is None else pid
    patterns = (f".bench_scale_*_{pid}.csv", f".bench_degrade_*_{pid}.csv")
    seen: set[pathlib.Path] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for pattern in patterns:
            for p in d.glob(pattern):
                if p not in seen:
                    seen.add(p)
                    p.unlink(missing_ok=True)


def build_scale_schedule(args: argparse.Namespace) -> list[int] | None:
    if args.scale:
        return sorted({int(x.strip()) for x in args.scale.split(",") if x.strip()})
    if args.scale_min is not None and args.scale_max is not None:
        out: list[int] = []
        cur = max(1, int(args.scale_min))
        mult = float(args.scale_mult)
        mx = int(args.scale_max)
        while cur <= mx:
            out.append(cur)
            nxt = int(cur * mult)
            if nxt <= cur:
                nxt = cur + 1
            cur = nxt
        return sorted(set(out))
    return None


def run_microbench(
    *,
    csv_path: pathlib.Path,
    template: pathlib.Path,
    repeat: int,
    warmup: int,
    write_repeat: int,
    subprocess_standalone: bool,
    root: pathlib.Path,
) -> None:
    points = vis.load_points(csv_path)
    n = len(points)
    print(f"Dataset: {csv_path.name}  ({n} points)  repeat={repeat}  warmup={warmup}\n")

    print_row(
        "load_points(csv)",
        bench(lambda: vis.load_points(csv_path), repeat=repeat, warmup=warmup),
    )
    print_row(
        "compute_stats(points)",
        bench(lambda: vis.compute_stats(points), repeat=repeat, warmup=warmup),
    )
    print_row(
        "_json_for_html_script(points)",
        bench(lambda: vis._json_for_html_script(points), repeat=repeat, warmup=warmup),
    )

    write_n = write_repeat if write_repeat > 0 else min(40, max(5, repeat))

    def write_once() -> None:
        fd, raw = tempfile.mkstemp(suffix=".html")
        os.close(fd)
        p = pathlib.Path(raw)
        try:
            vis.write_standalone_html(
                template_path=template,
                out_path=p,
                csv_label=csv_path.name,
                points=points,
            )
        finally:
            p.unlink(missing_ok=True)

    print_row(
        "write_standalone_html (tmp)",
        bench(write_once, repeat=write_n, warmup=min(2, warmup)),
        note=f"(repeat={write_n} for disk)",
    )

    if subprocess_standalone:
        fd, out = tempfile.mkstemp(suffix=".html", dir=root)
        os.close(fd)
        out_path = pathlib.Path(out)
        try:
            t0 = time.perf_counter()
            r = subprocess.run(
                [sys.executable, str(root / "visualize.py"), "--csv", str(csv_path), "--standalone", str(out_path)],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            elapsed = time.perf_counter() - t0
            status = "ok" if r.returncode == 0 else f"exit {r.returncode}"
            sz = out_path.stat().st_size if out_path.exists() else 0
            print(
                f"{'subprocess visualize --standalone':32}  n=   1  "
                f"wall={fmt_ms(elapsed)}  ({status}, {sz} bytes output)"
            )
            if r.returncode != 0 and r.stderr:
                print(r.stderr[:500], file=sys.stderr)
        finally:
            out_path.unlink(missing_ok=True)


def run_scale_sweep(
    *,
    source_csv: pathlib.Path,
    schedule: Sequence[int],
    template: pathlib.Path,
    median_repeats: int,
    warmup: int,
    scale_stop_ms: float | None,
    synth_seed: int,
) -> None:
    print("\n=== Scale sweep (random synthetic rows per N) ===\n")
    hdr = (
        f"{'points':>10}  {'load_p50':>12}  {'json_p50':>12}  "
        f"{'write_p50':>12}  {'html_MB':>10}  {'rss_MB':>10}  note"
    )
    print(hdr)
    print("-" * len(hdr))
    scratch = source_csv.parent
    pid = os.getpid()
    for n in schedule:
        tmp = scratch / f".bench_scale_{n}_{pid}.csv"
        try:
            try:
                write_random_synth_csv(n, tmp, seed=synth_seed + n)
            except MemoryError:
                print(f"{n:10}  (OOM writing CSV)")
                break

            def load_once() -> None:
                vis.load_points(tmp)

            try:
                t_load = median_of(load_once, repeats=median_repeats, warmup=max(1, warmup // 2))
            except MemoryError:
                print(f"{n:10}  {'OOM':>12}  {'—':>12}  {'—':>12}  {'—':>10}  {'—':>10}  load OOM")
                break

            pts = vis.load_points(tmp)
            rss_mb = rss_peak_mb()

            def json_once() -> None:
                vis._json_for_html_script(pts)

            t_json = median_of(json_once, repeats=max(3, median_repeats // 2), warmup=1)

            fd, html_raw = tempfile.mkstemp(suffix=".html")
            os.close(fd)
            html_path = pathlib.Path(html_raw)
            try:

                def write_once() -> None:
                    vis.write_standalone_html(
                        template_path=template,
                        out_path=html_path,
                        csv_label=f"synth_x{n}.csv",
                        points=pts,
                    )

                t_write = median_of(write_once, repeats=max(3, median_repeats // 3), warmup=1)
                html_bytes = html_path.stat().st_size
            finally:
                html_path.unlink(missing_ok=True)

            mb_html = html_bytes / (1024 * 1024)
            note = ""
            if scale_stop_ms is not None and t_load * 1000 > scale_stop_ms:
                note = f"stop: load_p50 > {scale_stop_ms:g} ms"
            print(
                f"{n:10}  {fmt_ms(t_load)}  {fmt_ms(t_json)}  {fmt_ms(t_write)}  "
                f"{mb_html:10.2f}  {rss_mb:10.1f}  {note}"
            )
            if note:
                break
        finally:
            tmp.unlink(missing_ok=True)


def run_degrade_series(
    *,
    source_csv: pathlib.Path,
    loads: int,
    window: int,
    degrade_points: int,
    root: pathlib.Path,
    synth_seed: int,
) -> None:
    print("\n=== Sequential load degradation ===\n")
    tmp: pathlib.Path | None = None
    path = source_csv
    label = source_csv.name
    if degrade_points > 0:
        tmp = root / f".bench_degrade_{degrade_points}_{os.getpid()}.csv"
        write_random_synth_csv(degrade_points, tmp, seed=synth_seed)
        path = tmp
        label = f"{degrade_points} random synthetic rows (seed={synth_seed})"

    times: list[float] = []
    try:
        for _ in range(loads):
            t0 = time.perf_counter()
            vis.load_points(path)
            times.append(time.perf_counter() - t0)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

    print(f"CSV: {label}  sequential loads={loads}  window={window}\n")
    if window < 5 or loads < window * 2:
        print("(use --degrade-window smaller and enough --degrade-loads)\n")

    w0 = times[:window]
    baseline = statistics.median(w0)
    print(f"First window [0:{window})  p50={fmt_ms(baseline)}  p95={fmt_ms(percentile(sorted(w0), 95))}")
    print(f"{'start':>6}  {'end':>6}  {'p50_ms':>10}  {'p95_ms':>10}  {'vs_1st':>8}  {'mean_ms':>10}")
    print("-" * 60)
    i = 0
    while i + window <= len(times):
        chunk = times[i : i + window]
        s = sorted(chunk)
        p50 = statistics.median(chunk)
        p95 = percentile(s, 95)
        ratio = p50 / baseline if baseline > 0 else 0.0
        mean_t = statistics.mean(chunk)
        print(f"{i:6}  {i + window - 1:6}  {p50 * 1000:10.3f}  {p95 * 1000:10.3f}  {ratio:8.2f}x  {mean_t * 1000:10.3f}")
        i += window
    if i < len(times):
        rest = times[i:]
        s = sorted(rest)
        p50 = statistics.median(rest)
        p95 = percentile(s, 95)
        ratio = p50 / baseline if baseline > 0 else 0.0
        print(f"{i:6}  {len(times) - 1:6}  {p50 * 1000:10.3f}  {p95 * 1000:10.3f}  {ratio:8.2f}x  (partial window)")

    overall = statistics.median(times)
    drift = overall / baseline if baseline > 0 else 0.0
    print(f"\nGlobal median={fmt_ms(overall)}  vs first-window median={drift:.2f}x")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", type=pathlib.Path, default=pathlib.Path("synthetic_points.csv"))
    parser.add_argument("--repeat", type=int, default=100, help="timed iterations (after warmup), microbench")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument(
        "--write-repeat",
        type=int,
        default=0,
        help="override repeat for disk write bench (default: min(40, --repeat))",
    )
    parser.add_argument(
        "--subprocess",
        action="store_true",
        help="microbench: one cold `python visualize.py --standalone`",
    )
    parser.add_argument(
        "--no-micro",
        action="store_true",
        help="skip microbench block (only scale/degrade)",
    )
    parser.add_argument(
        "--scale",
        metavar="N,N,...",
        help="comma-separated point counts (random rows via generate_data.generate_rows_for_count)",
    )
    parser.add_argument("--scale-min", type=int, default=None, metavar="N")
    parser.add_argument("--scale-max", type=int, default=None, metavar="N")
    parser.add_argument("--scale-mult", type=float, default=2.0, help="geometric step for --scale-min/max")
    parser.add_argument(
        "--scale-stop-ms",
        type=float,
        default=None,
        metavar="MS",
        help="stop scale sweep after first row with load_p50 > MS",
    )
    parser.add_argument(
        "--scale-median-repeats",
        type=int,
        default=5,
        help="median-of-N timings per column in scale sweep",
    )
    parser.add_argument(
        "--degrade-loads",
        type=int,
        default=0,
        metavar="K",
        help="run K sequential load_points on CSV; report latency per window",
    )
    parser.add_argument(
        "--degrade-window",
        type=int,
        default=100,
        help="loads per bucket for degrade report",
    )
    parser.add_argument(
        "--degrade-points",
        type=int,
        default=0,
        metavar="N",
        help="generate N random synthetic rows for degrade test (0 = use --csv as-is)",
    )
    parser.add_argument(
        "--synth-seed",
        type=int,
        default=42,
        help="RNG seed for random bench CSVs (scale: seed+N per row count; degrade: this seed)",
    )
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parent
    csv_path = args.csv if args.csv.is_absolute() else root / args.csv
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    template = root / "static" / "index.html"
    if not template.exists():
        raise SystemExit(f"Missing template: {template}")

    schedule = build_scale_schedule(args)
    if schedule is not None and min(schedule) < 1:
        raise SystemExit("scale N must be >= 1")

    if not args.no_micro:
        run_microbench(
            csv_path=csv_path,
            template=template,
            repeat=args.repeat,
            warmup=args.warmup,
            write_repeat=args.write_repeat,
            subprocess_standalone=args.subprocess,
            root=root,
        )

    if schedule:
        run_scale_sweep(
            source_csv=csv_path,
            schedule=schedule,
            template=template,
            median_repeats=args.scale_median_repeats,
            warmup=args.warmup,
            scale_stop_ms=args.scale_stop_ms,
            synth_seed=args.synth_seed,
        )

    if args.degrade_loads > 0:
        run_degrade_series(
            source_csv=csv_path,
            loads=args.degrade_loads,
            window=args.degrade_window,
            degrade_points=args.degrade_points,
            root=root,
            synth_seed=args.synth_seed,
        )

    remove_bench_csvs(root, csv_path.parent)

    print("\nDone.")


if __name__ == "__main__":
    main()
