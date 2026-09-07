from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

try:
    from analyzer import CRITICAL, OK, WARNING, AnalysisReport, MeshAnalyzer
    from viewer import LAYER_COLORS, LAYER_ORDER, LAYER_TITLES, MeshViewer
except ModuleNotFoundError:
    from src.analyzer import CRITICAL, OK, WARNING, AnalysisReport, MeshAnalyzer
    from src.viewer import LAYER_COLORS, LAYER_ORDER, LAYER_TITLES, MeshViewer

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
ASSETS = BASE / "assets"
SEVERITY_COLORS = {OK: "#41b06e", WARNING: "#e0a112", CRITICAL: "#e0453e"}
SEVERITY_TITLES = {OK: "норма", WARNING: "предупреждение", CRITICAL: "критично"}
FILE_TYPES = [
    ("3D-модели", "*.obj *.stl *.ply *.glb *.gltf *.off *.3mf *.dae"),
    ("Все файлы", "*.*"),
]


def to_hex(color: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{int(round(channel * 255)):02x}" for channel in color)


def score_color(score: float) -> str:
    if score >= 75.0:
        return SEVERITY_COLORS[OK]
    if score >= 45.0:
        return SEVERITY_COLORS[WARNING]
    return SEVERITY_COLORS[CRITICAL]


class Application(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("3DCheck — анализатор дефектов 3D-моделей")
        self.geometry("1360x820")
        self.minsize(1040, 640)

        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._report: AnalysisReport | None = None
        self._toggles: dict[str, ctk.CTkCheckBox] = {}
        self._icon_image: tk.PhotoImage | None = None
        self.icon_path: Path | None = None
        self.on_report_ready: Callable[[AnalysisReport], None] | None = None
        self._apply_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

    def _apply_icon(self) -> None:
        icon = ASSETS / "logo.ico"
        if icon.is_file():
            try:
                self.iconbitmap(default=str(icon))
                self.icon_path = icon
            except tk.TclError:
                pass
        fallback = ASSETS / "logo_256.png"
        if self.icon_path is None and fallback.is_file():
            try:
                self._icon_image = tk.PhotoImage(file=str(fallback))
                self.iconphoto(True, self._icon_image)
                self.icon_path = fallback
            except tk.TclError:
                pass

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, height=58)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(bar, text="Открыть модель", width=160, command=self.open_file).grid(
            row=0, column=0, padx=(14, 10), pady=12
        )
        self.file_label = ctk.CTkLabel(bar, text="Файл не выбран", anchor="w")
        self.file_label.grid(row=0, column=1, sticky="ew", padx=6)

        self.wireframe_switch = ctk.CTkSwitch(
            bar, text="Сетка", command=self._on_wireframe, width=90
        )
        self.wireframe_switch.grid(row=0, column=2, padx=10)
        ctk.CTkButton(bar, text="Сбросить вид", width=130, command=self._on_reset).grid(
            row=0, column=3, padx=6
        )
        ctk.CTkButton(bar, text="Скриншот", width=110, command=self._on_screenshot).grid(
            row=0, column=4, padx=(6, 14)
        )

    def _build_body(self) -> None:
        canvas_holder = ctk.CTkFrame(self, corner_radius=0, fg_color="#1c1d22")
        canvas_holder.grid(row=1, column=0, sticky="nsew")
        canvas_holder.grid_rowconfigure(0, weight=1)
        canvas_holder.grid_columnconfigure(0, weight=1)

        self.viewer = MeshViewer(canvas_holder, width=880, height=680)
        self.viewer.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.sidebar = ctk.CTkScrollableFrame(self, width=400, corner_radius=0)
        self.sidebar.grid(row=1, column=1, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self._show_placeholder()

    def _build_statusbar(self) -> None:
        self.status = ctk.CTkLabel(
            self,
            text="ЛКМ — вращение · ПКМ или Shift+ЛКМ — сдвиг · колесо — зум · двойной клик — сброс",
            anchor="w",
            height=28,
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 6))

    def _clear_sidebar(self) -> None:
        for child in self.sidebar.winfo_children():
            child.destroy()
        self._toggles.clear()

    def _show_placeholder(self) -> None:
        self._clear_sidebar()
        ctk.CTkLabel(
            self.sidebar,
            text="Загрузите 3D-модель,\nчтобы увидеть отчёт",
            justify="left",
            font=ctk.CTkFont(size=15),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=24)

    def open_file(self) -> None:
        path = filedialog.askopenfilename(title="Выберите 3D-модель", filetypes=FILE_TYPES)
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        self.file_label.configure(text=str(path))
        self.status.configure(text=f"Анализ {path.name} ...")
        self._clear_sidebar()
        ctk.CTkLabel(self.sidebar, text="Анализ...", font=ctk.CTkFont(size=15)).grid(
            row=0, column=0, sticky="w", padx=16, pady=24
        )
        threading.Thread(target=self._worker, args=(path,), daemon=True).start()
        self.after(60, self._poll)

    def _worker(self, path: Path) -> None:
        try:
            self._queue.put(("ok", MeshAnalyzer(path).analyze()))
        except Exception as error:
            self._queue.put(("error", error))

    def _poll(self) -> None:
        try:
            kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(60, self._poll)
            return
        if kind == "error":
            self._show_error(payload)
            return
        self._report = payload
        self.viewer.set_mesh(payload.mesh, payload.markers)
        self._render_report(payload)
        problems = len(payload.problems)
        self.status.configure(
            text=f"Готово · оценка {payload.score:.0f}/100 · проблем: {problems}"
        )
        if self.on_report_ready is not None:
            self.on_report_ready(payload)

    def _show_error(self, error: object) -> None:
        self.viewer.clear()
        self._clear_sidebar()
        ctk.CTkLabel(
            self.sidebar,
            text=f"Не удалось открыть файл\n\n{error}",
            justify="left",
            wraplength=340,
            text_color=SEVERITY_COLORS[CRITICAL],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=24)
        self.status.configure(text="Ошибка загрузки")

    def _render_report(self, report: AnalysisReport) -> None:
        self._clear_sidebar()
        row = 0

        head = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", padx=12, pady=(12, 6))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=f"{report.score:.0f} / 100",
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color=score_color(report.score),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text=report.grade, anchor="w", wraplength=340).grid(
            row=1, column=0, sticky="w"
        )
        bar = ctk.CTkProgressBar(head, height=10, progress_color=score_color(report.score))
        bar.set(report.score / 100.0)
        bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        row += 1

        stats = report.stats
        summary = (
            f"Полигонов: {stats['faces']}\n"
            f"Вершин: {stats['vertices']} (уникальных {stats['welded_vertices']})\n"
            f"Объектов: {stats['bodies']} · замкнут: {'да' if stats['watertight'] else 'нет'}\n"
            f"Габариты: {' x '.join(f'{v:g}' for v in stats['dimensions'])}"
        )
        ctk.CTkLabel(self.sidebar, text=summary, justify="left", anchor="w").grid(
            row=row, column=0, sticky="ew", padx=14, pady=(4, 10)
        )
        row += 1

        for check in report.checks:
            card = ctk.CTkFrame(self.sidebar)
            card.grid(row=row, column=0, sticky="ew", padx=12, pady=6)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card,
                text=check.title,
                font=ctk.CTkFont(size=15, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(
                card,
                text=f"{SEVERITY_TITLES[check.severity]} · −{check.penalty:.1f}",
                text_color=SEVERITY_COLORS[check.severity],
                anchor="w",
            ).grid(row=1, column=0, sticky="w", padx=12)
            ctk.CTkLabel(
                card, text=check.summary, anchor="w", justify="left", wraplength=330
            ).grid(row=2, column=0, sticky="w", padx=12, pady=(4, 0))
            for index, hint in enumerate(check.hints, start=3):
                ctk.CTkLabel(
                    card,
                    text=f"• {hint}",
                    anchor="w",
                    justify="left",
                    wraplength=330,
                    text_color="#9aa0aa",
                ).grid(row=index, column=0, sticky="w", padx=12, pady=(4, 0))
            ctk.CTkLabel(card, text="").grid(row=99, column=0, pady=2)
            row += 1

        layers = ctk.CTkFrame(self.sidebar)
        layers.grid(row=row, column=0, sticky="ew", padx=12, pady=(10, 14))
        layers.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            layers, text="Подсветка на модели", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        markers = report.markers
        line = 1
        for key in LAYER_ORDER:
            data = markers.get(key)
            count = 0 if data is None else len(data)
            if count == 0:
                continue
            box = ctk.CTkCheckBox(
                layers,
                text=f"{LAYER_TITLES[key]} ({count})",
                fg_color=to_hex(LAYER_COLORS[key]),
                hover_color=to_hex(LAYER_COLORS[key]),
                command=lambda name=key: self._on_layer(name),
            )
            box.select()
            box.grid(row=line, column=0, sticky="w", padx=12, pady=4)
            self._toggles[key] = box
            line += 1
        if line == 1:
            ctk.CTkLabel(layers, text="Дефектов не найдено", text_color="#9aa0aa").grid(
                row=1, column=0, sticky="w", padx=12, pady=(0, 6)
            )
        ctk.CTkLabel(layers, text="").grid(row=100, column=0, pady=2)

    def _on_layer(self, key: str) -> None:
        box = self._toggles.get(key)
        if box is not None:
            self.viewer.set_layer(key, bool(box.get()))

    def _on_wireframe(self) -> None:
        self.viewer.set_wireframe(bool(self.wireframe_switch.get()))

    def _on_reset(self) -> None:
        self.viewer.reset_view()

    def _on_screenshot(self) -> None:
        if self._report is None:
            self.status.configure(text="Сначала загрузите модель")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить скриншот",
            defaultextension=".png",
            initialfile=f"{self._report.source.stem}_3dcheck.png",
            filetypes=[("PNG", "*.png")],
        )
        if path:
            self.viewer.save_screenshot(path)
            self.status.configure(text=f"Скриншот сохранён: {path}")


def main() -> int:
    app = Application()
    if len(sys.argv) > 1:
        app.after(300, lambda: app.load(Path(" ".join(sys.argv[1:]).strip().strip('"'))))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
