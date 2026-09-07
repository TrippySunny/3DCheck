from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzer import AnalysisReport
from app import Application

SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "build" / "smoke"
TARGETS = [
    SAMPLES / "broken_sphere.obj",
    SAMPLES / "overtessellated_plane.obj",
    SAMPLES / "clean_sphere.obj",
]


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
    app = Application()
    app.geometry("1360x820")
    app.update()
    app.after(600, lambda: run(app, list(TARGETS)))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
