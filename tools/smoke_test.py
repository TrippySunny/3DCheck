from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzer import AnalysisReport, MeshAnalyzer
from app import Application

SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "build" / "smoke"


def collect() -> list[Path]:
    if not SAMPLES.is_dir():
        return []
    return sorted(
        path
        for path in SAMPLES.iterdir()
        if path.is_file() and path.suffix.lower() in MeshAnalyzer.SUPPORTED_EXTENSIONS
    )


def run(app: Application, queue: list[Path]) -> None:
    if not queue:
        app.after(200, app.destroy)
        return
    target = queue.pop(0)

    def on_ready(report: AnalysisReport) -> None:
        app.after(500, lambda: finish(report))

    def finish(report: AnalysisReport) -> None:
        app.viewer.set_wireframe(False)
        shot = app.viewer.save_screenshot(OUTPUT / f"{target.stem}.png")
        app.viewer.set_wireframe(True)
        app.viewer.save_screenshot(OUTPUT / f"{target.stem}_wire.png")
        app.viewer.set_wireframe(False)
        print(f"{target.name}: score={report.score:.1f} markers={len(report.markers)} -> {shot}")
        for check in report.checks:
            print(f"    [{check.severity:8}] {check.title}: {check.summary}")
        run(app, queue)

    app.on_report_ready = on_ready
    app.load(target)


def main() -> int:
    targets = collect()
    if not targets:
        print(f"Положите модели в {SAMPLES} и запустите снова")
        return 1
    app = Application()
    app.geometry("1360x820")
    app.update()
    print(f"иконка окна: {app.icon_path}")
    app.after(600, lambda: run(app, targets))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
