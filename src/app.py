from __future__ import annotations

import json
import os
import queue
import random
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk
from PIL import Image

try:
    from analyzer import CRITICAL, OK, WARNING, AnalysisReport, AnalyzerError, MeshAnalyzer
    from i18n import FALLBACK, LANGUAGE_NAMES, LANGUAGES, Message, Translator
    from viewer import LAYER_COLORS, LAYER_ORDER, MeshViewer
except ModuleNotFoundError:
    from src.analyzer import CRITICAL, OK, WARNING, AnalysisReport, AnalyzerError, MeshAnalyzer
    from src.i18n import FALLBACK, LANGUAGE_NAMES, LANGUAGES, Message, Translator
    from src.viewer import LAYER_COLORS, LAYER_ORDER, MeshViewer

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
ASSETS = BASE / "assets"
THEME_FILE = ASSETS / "ctk_theme.json"
GREEN = "#3DCC7A"
YELLOW = "#E6B325"
RED = "#FF4545"
BLUE = "#3B7BFF"
BLUE_HOVER = "#5C94FF"
BLUE_SOFT = "#97AAC4"
INK = "#1A1E26"
PAPER = "#FFFFFF"
MUTED = ("#5B6B82", "#97AAC4")
CARD = ("#FFFFFF", "#252A33")
SEVERITY_COLORS = {OK: GREEN, WARNING: YELLOW, CRITICAL: RED}
SEVERITY_CARD = {
    OK: ("#E5F8ED", "#173322"),
    WARNING: ("#FFF6D6", "#332A10"),
    CRITICAL: ("#FFE4E4", "#3A1414"),
}
CANVAS_COLORS = {"dark": "#1A1E26", "light": "#E8EDF3"}
BAR_COLORS = {"dark": "#1A1E26", "light": PAPER}
SIDE_COLORS = {"dark": "#1A1E26", "light": "#E8EDF3"}
THEMES = ("dark", "light")
SECONDARY_BTN = {"fg_color": BLUE, "hover_color": BLUE_HOVER, "text_color": PAPER}


def settings_path() -> Path:
    root = Path(os.environ["APPDATA"]) if os.environ.get("APPDATA") else Path.home() / ".3dcheck"
    return root / "3DCheck" / "settings.json"


def load_settings() -> dict[str, object]:
    path = settings_path()
    data = {"language": FALLBACK, "theme": "dark", "xray": False}
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    language = raw.get("language", FALLBACK)
    theme = raw.get("theme", "dark")
    data["language"] = language if language in LANGUAGES else FALLBACK
    data["theme"] = theme if theme in THEMES else "dark"
    data["xray"] = bool(raw.get("xray", False))
    return data


def save_settings(data: dict[str, object]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def to_hex(color: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{int(round(channel * 255)):02x}" for channel in color)


def score_card_color(score: float) -> str:
    if score >= 75.0:
        return GREEN
    if score >= 45.0:
        return YELLOW
    return RED


def score_track_color(score: float) -> str:
    if score >= 75.0:
        return "#1F7A45"
    if score >= 45.0:
        return "#8A6A12"
    return "#8A1F1F"


def close_splash() -> None:
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass


class Application(ctk.CTk):
    def __init__(self) -> None:
        self.settings = load_settings()
        self.t = Translator(str(self.settings["language"]))
        if THEME_FILE.is_file():
            ctk.set_default_color_theme(str(THEME_FILE))
        ctk.set_appearance_mode(str(self.settings["theme"]))
        super().__init__()
        self.configure(fg_color=(CANVAS_COLORS["light"], CANVAS_COLORS["dark"]))
        self.title(self.t("app.title"))
        self.geometry("1360x820")
        self.minsize(1040, 640)

        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._report: AnalysisReport | None = None
        self._toggles: dict[str, ctk.CTkCheckBox] = {}
        self._icon_image: tk.PhotoImage | None = None
        self._logo_image: ctk.CTkImage | None = None
        self._active_tab: str = "report"
        self._shake_labels: list[ctk.CTkLabel] = []
        self._shake_after: str | None = None
        self.icon_path: Path | None = None
        self.on_report_ready: Callable[[AnalysisReport], None] | None = None
        self._apply_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self.viewer.set_theme(str(self.settings["theme"]))
        self.viewer.set_xray(bool(self.settings["xray"]))
        self.after(80, close_splash)

    def _apply_icon(self) -> None:
        icon = ASSETS / "logo.ico"
        if icon.is_file():
            try:
                self.iconbitmap(default=str(icon))
                self.icon_path = icon
            except tk.TclError:
                pass
        fallback = ASSETS / "logo_256.png"
        if fallback.is_file():
            try:
                picture = Image.open(fallback)
                self._logo_image = ctk.CTkImage(light_image=picture, dark_image=picture, size=(36, 36))
            except OSError:
                self._logo_image = None
        if self.icon_path is None and fallback.is_file():
            try:
                self._icon_image = tk.PhotoImage(file=str(fallback))
                self.iconphoto(True, self._icon_image)
                self.icon_path = fallback
            except tk.TclError:
                pass

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, height=72, fg_color=(BAR_COLORS["light"], BAR_COLORS["dark"]))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)

        if self._logo_image is not None:
            ctk.CTkLabel(bar, text="", image=self._logo_image).grid(
                row=0, column=0, padx=(16, 8), pady=14
            )
        self._btn_open = ctk.CTkButton(
            bar,
            text=self.t("toolbar.open"),
            width=168,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.open_file,
        )
        self._btn_open.grid(row=0, column=1, padx=(6, 10), pady=14)
        self.file_label = ctk.CTkLabel(
            bar, text=self.t("file.none"), anchor="w", text_color=MUTED
        )
        self.file_label.grid(row=0, column=2, sticky="ew", padx=8)

        self.wireframe_switch = ctk.CTkSwitch(
            bar, text=self.t("toolbar.wireframe"), command=self._on_wireframe, width=90
        )
        self.wireframe_switch.grid(row=0, column=3, padx=10)
        self._btn_reset = ctk.CTkButton(
            bar,
            text=self.t("toolbar.reset"),
            width=130,
            height=40,
            command=self._on_reset,
            **SECONDARY_BTN,
        )
        self._btn_reset.grid(row=0, column=4, padx=6)
        self._btn_shot = ctk.CTkButton(
            bar,
            text=self.t("toolbar.screenshot"),
            width=118,
            height=40,
            command=self._on_screenshot,
            **SECONDARY_BTN,
        )
        self._btn_shot.grid(row=0, column=5, padx=6)
        self._btn_settings = ctk.CTkButton(
            bar,
            text=self.t("toolbar.settings"),
            width=128,
            height=40,
            command=self._toggle_app_settings,
            **SECONDARY_BTN,
        )
        self._btn_settings.grid(row=0, column=6, padx=(6, 16))

    def _build_body(self) -> None:
        self._canvas_holder = ctk.CTkFrame(
            self, corner_radius=24, fg_color=CANVAS_COLORS[str(self.settings["theme"])]
        )
        self._canvas_holder.grid(row=1, column=0, sticky="nsew", padx=(10, 8), pady=4)
        self._canvas_holder.grid_rowconfigure(0, weight=1)
        self._canvas_holder.grid_columnconfigure(0, weight=1)

        self.viewer = MeshViewer(
            self._canvas_holder,
            theme=str(self.settings["theme"]),
            width=880,
            height=680,
        )
        self.viewer.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self._build_app_overlay()

        self._side = ctk.CTkFrame(
            self, width=420, corner_radius=0, fg_color=(SIDE_COLORS["light"], SIDE_COLORS["dark"])
        )
        self._side.grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        self._side.grid_propagate(False)
        self._side.grid_columnconfigure(0, weight=1)
        self._side.grid_rowconfigure(1, weight=1)

        self._tab_switch = ctk.CTkSegmentedButton(
            self._side,
            values=[self.t("tab.report"), self.t("tab.params")],
            command=self._on_tab_label,
        )
        self._tab_switch.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self._tab_switch.set(self.t("tab.report"))

        self.sidebar = ctk.CTkScrollableFrame(
            self._side, corner_radius=0, fg_color="transparent"
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)

        self._params_panel = ctk.CTkScrollableFrame(
            self._side, corner_radius=0, fg_color="transparent"
        )
        self._params_panel.grid_columnconfigure(0, weight=1)
        self._build_params()
        self._show_placeholder()

    def _build_statusbar(self) -> None:
        self.status = ctk.CTkLabel(
            self,
            text=self.t("status.controls"),
            anchor="w",
            height=30,
            text_color=MUTED,
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 10))

    def _file_types(self) -> list[tuple[str, str]]:
        return [
            (self.t("dialog.models"), "*.obj *.stl *.ply *.glb *.gltf *.off *.3mf *.dae"),
            (self.t("dialog.all_files"), "*.*"),
        ]

    def _build_params(self) -> None:
        panel = self._params_panel
        for child in panel.winfo_children():
            child.destroy()

        card = ctk.CTkFrame(panel, corner_radius=24, fg_color=CARD)
        card.grid(row=0, column=0, sticky="ew", padx=10, pady=12)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text=self.t("params.title"), font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(card, text=self.t("params.display"), text_color=MUTED).grid(
            row=1, column=0, sticky="w", padx=20, pady=(4, 8)
        )
        self._settings_xray = ctk.CTkSwitch(
            card, text=self.t("settings.xray"), command=self._on_xray_switch
        )
        if self.settings["xray"]:
            self._settings_xray.select()
        else:
            self._settings_xray.deselect()
        self._settings_xray.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            card,
            text=self.t("settings.xray.note"),
            justify="left",
            wraplength=320,
            text_color=MUTED,
        ).grid(row=3, column=0, sticky="w", padx=20, pady=(0, 20))

    def _build_app_overlay(self) -> None:
        self._overlay = ctk.CTkFrame(self._canvas_holder, fg_color=("#1A1E26", "#1A1E26"), corner_radius=24)
        self._overlay_card = ctk.CTkFrame(self._overlay, width=400, corner_radius=28, fg_color=CARD)
        self._overlay_card.place(relx=0.5, rely=0.5, anchor="center")
        self._overlay_card.grid_columnconfigure(0, weight=1)
        self._overlay.bind("<Button-1>", lambda _event: self._hide_app_settings())
        self._fill_app_overlay()

    def _fill_app_overlay(self) -> None:
        card = self._overlay_card
        for child in card.winfo_children():
            child.destroy()

        ctk.CTkLabel(
            card,
            text=self.t("settings.title"),
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=(INK, PAPER),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 14))

        ctk.CTkLabel(card, text=self.t("settings.language")).grid(
            row=1, column=0, sticky="w", padx=24, pady=(4, 4)
        )
        self._settings_language = ctk.CTkOptionMenu(
            card,
            values=[LANGUAGE_NAMES[code] for code in LANGUAGES],
            command=self._on_language,
            width=240,
        )
        self._settings_language.set(LANGUAGE_NAMES[str(self.settings["language"])])
        self._settings_language.grid(row=2, column=0, sticky="w", padx=24)

        ctk.CTkLabel(card, text=self.t("settings.theme")).grid(
            row=3, column=0, sticky="w", padx=24, pady=(16, 4)
        )
        self._settings_theme = ctk.CTkOptionMenu(
            card,
            values=[self.t("settings.theme.dark"), self.t("settings.theme.light")],
            command=self._on_theme_label,
            width=240,
        )
        self._settings_theme.set(self.t(f"settings.theme.{self.settings['theme']}"))
        self._settings_theme.grid(row=4, column=0, sticky="w", padx=24)

        self._overlay_close = ctk.CTkButton(
            card, text=self.t("settings.close"), width=120, command=self._hide_app_settings
        )
        self._overlay_close.grid(row=5, column=0, sticky="e", padx=24, pady=22)

    def _toggle_app_settings(self) -> None:
        if self._overlay.winfo_ismapped():
            self._hide_app_settings()
            return
        self._fill_app_overlay()
        self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay.lift()

    def _hide_app_settings(self) -> None:
        self._overlay.place_forget()

    def _on_tab_label(self, label: str) -> None:
        self._show_tab("params" if label == self.t("tab.params") else "report")

    def _show_tab(self, name: str) -> None:
        self._active_tab = name
        if name == "params":
            self.sidebar.grid_remove()
            self._params_panel.grid(row=1, column=0, sticky="nsew")
            self._tab_switch.set(self.t("tab.params"))
            return
        self._params_panel.grid_remove()
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self._tab_switch.set(self.t("tab.report"))

    def _add_absurd_label(self, card: ctk.CTkFrame, row: int) -> None:
        holder = ctk.CTkFrame(card, fg_color="transparent", height=86)
        holder.grid(row=row, column=0, sticky="ew", padx=8, pady=(10, 6))
        holder.grid_propagate(False)
        label = ctk.CTkLabel(
            holder,
            text=self.t("check.polygons.hint.absurd"),
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#FF0000",
            justify="center",
            wraplength=340,
        )
        label.place(relx=0.5, rely=0.5, anchor="center")
        self._shake_labels.append(label)
        if self._shake_after is None:
            self._tick_shake()

    def _stop_shake(self) -> None:
        if self._shake_after is not None:
            try:
                self.after_cancel(self._shake_after)
            except tk.TclError:
                pass
            self._shake_after = None
        self._shake_labels.clear()

    def _tick_shake(self) -> None:
        alive = [label for label in self._shake_labels if label.winfo_exists()]
        self._shake_labels = alive
        if not alive:
            self._shake_after = None
            return
        for label in alive:
            reach = 10 if random.random() < 0.18 else 5
            label.place(
                relx=0.5,
                rely=0.5,
                x=random.randint(-reach, reach),
                y=random.randint(-reach, reach),
                anchor="center",
            )
        self._shake_after = self.after(28, self._tick_shake)

    def _clear_sidebar(self) -> None:
        self._stop_shake()
        for child in self.sidebar.winfo_children():
            child.destroy()
        self._toggles.clear()

    def _show_placeholder(self) -> None:
        self._clear_sidebar()
        card = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=CARD)
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=12)
        ctk.CTkLabel(
            card,
            text=self.t("sidebar.placeholder"),
            justify="left",
            font=ctk.CTkFont(size=16),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=28)

    def open_file(self) -> None:
        path = filedialog.askopenfilename(title=self.t("dialog.open"), filetypes=self._file_types())
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        self.file_label.configure(text=str(path))
        self.status.configure(text=self.t("status.analyzing", name=path.name))
        self._clear_sidebar()
        card = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=CARD)
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=12)
        ctk.CTkLabel(
            card,
            text=self.t("sidebar.analyzing"),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=BLUE,
        ).grid(row=0, column=0, sticky="w", padx=22, pady=24)
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
        self._show_tab("report")
        self._render_report(payload)
        self.status.configure(
            text=self.t(
                "status.ready",
                score=f"{payload.score:.0f}",
                problems=len(payload.problems),
            )
        )
        if self.on_report_ready is not None:
            self.on_report_ready(payload)

    def _error_text(self, error: object) -> str:
        if isinstance(error, AnalyzerError):
            return self.t(error.message)
        return str(error)

    def _show_error(self, error: object) -> None:
        self.viewer.clear()
        self._clear_sidebar()
        card = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=SEVERITY_CARD[CRITICAL])
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=12)
        ctk.CTkLabel(
            card,
            text=self.t("sidebar.open_failed", error=self._error_text(error)),
            justify="left",
            wraplength=320,
            text_color=PAPER,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=22)
        self.status.configure(text=self.t("status.error"))

    def _render_report(self, report: AnalysisReport) -> None:
        self._clear_sidebar()
        row = 0

        accent = score_card_color(report.score)
        head = ctk.CTkFrame(self.sidebar, corner_radius=26, fg_color=accent)
        head.grid(row=row, column=0, sticky="ew", padx=8, pady=(8, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=f"{report.score:.0f} / 100",
            font=ctk.CTkFont(size=38, weight="bold"),
            text_color=PAPER,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 0))
        badge = ctk.CTkLabel(
            head,
            text=self.t(report.grade),
            anchor="w",
            wraplength=300,
            text_color=PAPER,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        badge.grid(row=1, column=0, sticky="w", padx=20, pady=(4, 6))
        bar = ctk.CTkProgressBar(head, height=8, progress_color=PAPER, fg_color=score_track_color(report.score))
        bar.set(report.score / 100.0)
        bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 18))
        row += 1

        stats = report.stats
        summary = "\n".join(
            (
                self.t("report.faces", value=stats["faces"]),
                self.t(
                    "report.vertices",
                    value=stats["vertices"],
                    unique=stats["welded_vertices"],
                ),
                self.t(
                    "report.bodies",
                    value=stats["bodies"],
                    closed=self.t("yes") if stats["watertight"] else self.t("no"),
                ),
                self.t(
                    "report.dimensions",
                    value=" x ".join(f"{item:g}" for item in stats["dimensions"]),
                ),
            )
        )
        meta = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=CARD)
        meta.grid(row=row, column=0, sticky="ew", padx=8, pady=6)
        ctk.CTkLabel(meta, text=summary, justify="left", anchor="w", text_color=(INK, PAPER)).grid(
            row=0, column=0, sticky="ew", padx=18, pady=16
        )
        row += 1

        for check in report.checks:
            fill = SEVERITY_CARD[check.severity]
            title_color = (INK, PAPER)
            body_color = MUTED
            card = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=fill)
            card.grid(row=row, column=0, sticky="ew", padx=8, pady=6)
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card,
                text=self.t(check.title),
                font=ctk.CTkFont(size=16, weight="bold"),
                anchor="w",
                text_color=title_color,
            ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))
            ctk.CTkLabel(
                card,
                text=f"{self.t(f'severity.{check.severity}')} · −{check.penalty:.1f}",
                text_color=SEVERITY_COLORS[check.severity],
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=1, column=0, sticky="w", padx=16, pady=(2, 0))
            ctk.CTkLabel(
                card,
                text=self.t(check.summary),
                anchor="w",
                justify="left",
                wraplength=320,
                text_color=title_color,
            ).grid(row=2, column=0, sticky="w", padx=16, pady=(6, 0))
            for index, hint in enumerate(check.hints, start=3):
                if isinstance(hint, Message) and hint.key == "check.polygons.hint.absurd":
                    self._add_absurd_label(card, index)
                    continue
                ctk.CTkLabel(
                    card,
                    text=f"• {self.t(hint)}",
                    anchor="w",
                    justify="left",
                    wraplength=320,
                    text_color=body_color,
                ).grid(row=index, column=0, sticky="w", padx=16, pady=(4, 0))
            ctk.CTkLabel(card, text="").grid(row=99, column=0, pady=4)
            row += 1

        layers = ctk.CTkFrame(self.sidebar, corner_radius=24, fg_color=CARD)
        layers.grid(row=row, column=0, sticky="ew", padx=8, pady=(8, 16))
        layers.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            layers, text=self.t("report.layers"), font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        markers = report.markers
        line = 1
        for key in LAYER_ORDER:
            data = markers.get(key)
            count = 0 if data is None else len(data)
            if count == 0:
                continue
            box = ctk.CTkCheckBox(
                layers,
                text=f"{self.t(f'layer.{key}')} ({count})",
                fg_color=to_hex(LAYER_COLORS[key]),
                hover_color=to_hex(LAYER_COLORS[key]),
                command=lambda name=key: self._on_layer(name),
            )
            box.select()
            box.grid(row=line, column=0, sticky="w", padx=16, pady=5)
            self._toggles[key] = box
            line += 1
        if line == 1:
            ctk.CTkLabel(
                layers, text=self.t("report.no_defects"), text_color=MUTED
            ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(layers, text="").grid(row=100, column=0, pady=6)

    def _persist(self) -> None:
        save_settings(self.settings)

    def _on_language(self, name: str) -> None:
        reverse = {title: code for code, title in LANGUAGE_NAMES.items()}
        self.settings["language"] = reverse.get(name, FALLBACK)
        self.t.set_language(str(self.settings["language"]))
        self._persist()
        self._relocalize()

    def _on_theme_label(self, label: str) -> None:
        self._apply_theme("light" if label == self.t("settings.theme.light") else "dark")

    def _apply_theme(self, theme: str) -> None:
        self.settings["theme"] = theme if theme in THEMES else "dark"
        ctk.set_appearance_mode(str(self.settings["theme"]))
        self.configure(fg_color=(CANVAS_COLORS["light"], CANVAS_COLORS["dark"]))
        self._canvas_holder.configure(fg_color=CANVAS_COLORS[str(self.settings["theme"])])
        self.viewer.set_theme(str(self.settings["theme"]))
        self._persist()

    def _on_xray_switch(self) -> None:
        state = bool(self._settings_xray.get())
        self.settings["xray"] = state
        self.viewer.set_xray(state)
        self._persist()

    def _relocalize(self) -> None:
        self.title(self.t("app.title"))
        self._btn_open.configure(text=self.t("toolbar.open"))
        self._btn_reset.configure(text=self.t("toolbar.reset"))
        self._btn_shot.configure(text=self.t("toolbar.screenshot"))
        self._btn_settings.configure(text=self.t("toolbar.settings"))
        self.wireframe_switch.configure(text=self.t("toolbar.wireframe"))
        self._tab_switch.configure(values=[self.t("tab.report"), self.t("tab.params")])
        self._build_params()
        self._fill_app_overlay()
        if self._report is None:
            self.file_label.configure(text=self.t("file.none"))
            self.status.configure(text=self.t("status.controls"))
            self._show_placeholder()
        else:
            self._render_report(self._report)
            self.status.configure(
                text=self.t(
                    "status.ready",
                    score=f"{self._report.score:.0f}",
                    problems=len(self._report.problems),
                )
            )
        self._show_tab(self._active_tab)

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
            self.status.configure(text=self.t("status.pick_first"))
            return
        path = filedialog.asksaveasfilename(
            title=self.t("dialog.save_shot"),
            defaultextension=".png",
            initialfile=f"{self._report.source.stem}_3dcheck.png",
            filetypes=[("PNG", "*.png")],
        )
        if path:
            self.viewer.save_screenshot(path)
            self.status.configure(text=self.t("status.shot_saved", path=path))


def main() -> int:
    app = Application()
    if len(sys.argv) > 1:
        app.after(300, lambda: app.load(Path(" ".join(sys.argv[1:]).strip().strip('"'))))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
