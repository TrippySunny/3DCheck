from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from analyzer import CRITICAL, OK, WARNING, AnalysisReport, CheckResult, MeshAnalyzer
except ModuleNotFoundError:
    from src.analyzer import CRITICAL, OK, WARNING, AnalysisReport, CheckResult, MeshAnalyzer

WIDTH = 74
MARKS = {OK: "[ OK ]", WARNING: "[ !! ]", CRITICAL: "[ XX ]"}
LABELS = {OK: "норма", WARNING: "предупреждение", CRITICAL: "критично"}


def line(char: str = "─") -> str:
    return char * WIDTH


def header() -> None:
    print()
    print(line("═"))
    print("  3DCheck — анализатор оптимизации 3D-моделей".ljust(WIDTH))
    print(line("═"))


def ask_path() -> Path | None:
    if len(sys.argv) > 1:
        return Path(" ".join(sys.argv[1:]).strip().strip('"').strip("'"))
    print("  Поддерживаются: " + ", ".join(MeshAnalyzer.SUPPORTED_EXTENSIONS))
    print("  Перетащи файл в окно консоли или вставь путь (Enter — выход)")
    raw = input("\n  Путь к модели: ").strip().strip('"').strip("'")
    return Path(raw) if raw else None


def score_bar(score: float) -> str:
    filled = int(round(score / 100 * 30))
    return "█" * filled + "░" * (30 - filled)


def print_stats(stats: dict[str, Any]) -> None:
    dimensions = " x ".join(f"{value:g}" for value in stats["dimensions"])
    rows = [
        ("Файл", f"{stats['file']}  ({stats['size_mb']} МБ)"),
        ("Полигонов", f"{stats['faces']}"),
        ("Вершин", f"{stats['vertices']} (уникальных {stats['welded_vertices']})"),
        ("Объектов в сетке", f"{stats['bodies']}"),
        ("Габариты", dimensions),
        ("Площадь поверхности", f"{stats['surface_area']:g}"),
        ("Замкнутый объём", "да" if stats["watertight"] else "нет"),
    ]
    for name, value in rows:
        print(f"  {name + ':':<22}{value}")


def print_check(index: int, check: CheckResult) -> None:
    print()
    print(f"  {MARKS[check.severity]}  {index}. {check.title} — {LABELS[check.severity]}")
    print(f"        {check.summary}")
    print(f"        штраф: -{check.penalty:.1f}")
    for hint in check.hints:
        print(f"        → {hint}")


def print_report(report: AnalysisReport) -> None:
    print()
    print(line())
    print_stats(report.stats)
    print()
    print(line())
    print("  РЕЗУЛЬТАТЫ ПРОВЕРОК")
    print(line())
    for index, check in enumerate(report.checks, start=1):
        print_check(index, check)
    print()
    print(line("═"))
    print(f"  ОЦЕНКА: {report.score:.0f}/100  [{score_bar(report.score)}]")
    print(f"  ВЕРДИКТ: {report.grade}")
    problems = report.problems
    if problems:
        print(f"  Найдено проблем: {len(problems)} — {', '.join(p.title.lower() for p in problems)}")
    else:
        print("  Проблем не обнаружено, модель готова к использованию")
    print(line("═"))
    print()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    header()
    path = ask_path()
    if path is None:
        print("  Файл не выбран, выход\n")
        return 0
    try:
        print(f"\n  Загрузка и анализ: {path.name} ...")
        report = MeshAnalyzer(path).analyze()
    except (FileNotFoundError, ValueError) as error:
        print(f"\n  ОШИБКА: {error}\n")
        return 1
    except Exception as error:
        print(f"\n  Не удалось разобрать файл ({type(error).__name__}): {error}\n")
        return 2
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
