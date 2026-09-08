from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LANGUAGES: tuple[str, ...] = ("ru", "en")
LANGUAGE_NAMES: dict[str, str] = {"ru": "Русский", "en": "English"}
FALLBACK: str = "ru"

STRINGS: dict[str, dict[str, str]] = {
    "app.title": {
        "ru": "3DCheck — анализатор дефектов 3D-моделей",
        "en": "3DCheck — 3D model defect analyzer",
    },
    "toolbar.open": {"ru": "Открыть модель", "en": "Open model"},
    "toolbar.wireframe": {"ru": "Сетка", "en": "Wireframe"},
    "toolbar.reset": {"ru": "Сбросить вид", "en": "Reset view"},
    "toolbar.screenshot": {"ru": "Скриншот", "en": "Screenshot"},
    "toolbar.settings": {"ru": "Настройки", "en": "Settings"},
    "tab.report": {"ru": "Отчёт", "en": "Report"},
    "tab.params": {"ru": "Параметры", "en": "Parameters"},
    "params.title": {"ru": "Параметры модели", "en": "Model parameters"},
    "params.display": {"ru": "Отображение", "en": "Display"},
    "file.none": {"ru": "Файл не выбран", "en": "No file selected"},
    "status.controls": {
        "ru": "ЛКМ — вращение · ПКМ или Shift+ЛКМ — сдвиг · колесо — зум · двойной клик — сброс",
        "en": "LMB — rotate · RMB or Shift+LMB — pan · wheel — zoom · double click — reset",
    },
    "status.analyzing": {"ru": "Анализ {name} ...", "en": "Analyzing {name} ..."},
    "status.ready": {
        "ru": "Готово · оценка {score}/100 · проблем: {problems}",
        "en": "Done · score {score}/100 · issues: {problems}",
    },
    "status.error": {"ru": "Ошибка загрузки", "en": "Failed to load"},
    "status.pick_first": {"ru": "Сначала загрузите модель", "en": "Load a model first"},
    "status.shot_saved": {"ru": "Скриншот сохранён: {path}", "en": "Screenshot saved: {path}"},
    "sidebar.placeholder": {
        "ru": "Загрузите 3D-модель,\nчтобы увидеть отчёт",
        "en": "Load a 3D model\nto see the report",
    },
    "sidebar.analyzing": {"ru": "Анализ...", "en": "Analyzing..."},
    "sidebar.open_failed": {
        "ru": "Не удалось открыть файл\n\n{error}",
        "en": "Could not open the file\n\n{error}",
    },
    "dialog.open": {"ru": "Выберите 3D-модель", "en": "Choose a 3D model"},
    "dialog.models": {"ru": "3D-модели", "en": "3D models"},
    "dialog.all_files": {"ru": "Все файлы", "en": "All files"},
    "dialog.save_shot": {"ru": "Сохранить скриншот", "en": "Save screenshot"},
    "report.faces": {"ru": "Полигонов: {value}", "en": "Polygons: {value}"},
    "report.vertices": {
        "ru": "Вершин: {value} (уникальных {unique})",
        "en": "Vertices: {value} (unique {unique})",
    },
    "report.bodies": {
        "ru": "Объектов: {value} · замкнут: {closed}",
        "en": "Objects: {value} · closed: {closed}",
    },
    "report.dimensions": {"ru": "Габариты: {value}", "en": "Size: {value}"},
    "report.layers": {"ru": "Подсветка на модели", "en": "Highlight on model"},
    "report.no_defects": {"ru": "Дефектов не найдено", "en": "No defects found"},
    "yes": {"ru": "да", "en": "yes"},
    "no": {"ru": "нет", "en": "no"},
    "severity.ok": {"ru": "норма", "en": "fine"},
    "severity.warning": {"ru": "предупреждение", "en": "warning"},
    "severity.critical": {"ru": "критично", "en": "critical"},
    "settings.title": {"ru": "Настройки", "en": "Settings"},
    "settings.language": {"ru": "Язык", "en": "Language"},
    "settings.theme": {"ru": "Тема", "en": "Theme"},
    "settings.theme.dark": {"ru": "Тёмная", "en": "Dark"},
    "settings.theme.light": {"ru": "Светлая", "en": "Light"},
    "settings.xray": {"ru": "Показывать дефекты сквозь модель", "en": "Show defects through the model"},
    "settings.xray.note": {
        "ru": "Проблемные полигоны рисуются поверх геометрии, даже если спрятаны внутри модели",
        "en": "Problem polygons are drawn on top of geometry even when hidden inside the model",
    },
    "settings.close": {"ru": "Закрыть", "en": "Close"},
    "layer.faces_overdense": {"ru": "Сомнительные полигоны", "en": "Questionable polygons"},
    "layer.faces_redundant": {"ru": "Лишние полигоны", "en": "Excess polygons"},
    "layer.faces_faceted": {"ru": "Нехватка полигонов", "en": "Missing polygons"},
    "layer.faces_degenerate": {"ru": "Вырожденные полигоны", "en": "Degenerate polygons"},
    "layer.faces_flipped": {"ru": "Вывернутые нормали", "en": "Flipped normals"},
    "layer.points_duplicates": {"ru": "Дубли вершин", "en": "Duplicate vertices"},
    "layer.points_hotspots": {"ru": "Скопления вершин", "en": "Vertex clusters"},
    "layer.points_stray": {"ru": "Вершины вне полигонов", "en": "Loose vertices"},
    "grade.excellent": {"ru": "Отличная оптимизация", "en": "Excellent optimization"},
    "grade.good": {"ru": "Хорошо, есть мелкие замечания", "en": "Good, minor issues"},
    "grade.average": {"ru": "Средне, модель требует доработки", "en": "Average, needs work"},
    "grade.poor": {"ru": "Плохо, много дефектов геометрии", "en": "Poor, many geometry defects"},
    "grade.critical": {"ru": "Критично, модель стоит переделать", "en": "Critical, rebuild the model"},
    "error.not_found": {"ru": "Файл не найден: {path}", "en": "File not found: {path}"},
    "error.format": {
        "ru": "Формат «{suffix}» не поддерживается. Доступные: {supported}",
        "en": "Format \u00ab{suffix}\u00bb is not supported. Available: {supported}",
    },
    "error.no_mesh": {
        "ru": "В файле не найдено полигональной сетки",
        "en": "No polygon mesh found in the file",
    },
    "check.polygons.title": {"ru": "Лишние полигоны", "en": "Excess polygons"},
    "check.polygons.summary": {
        "ru": "{faces} полигонов, лишних ~{redundant}, вырожденных {degenerate}",
        "en": "{faces} polygons, ~{redundant} excess, {degenerate} degenerate",
    },
    "check.polygons.hint.redundant": {
        "ru": "На плоских участках можно убрать ~{count} треугольников ({percent}% сетки): "
        "Blender → Mesh → Limited Dissolve",
        "en": "Flat areas can lose ~{count} triangles ({percent}% of the mesh): "
        "Blender → Mesh → Limited Dissolve",
    },
    "check.polygons.hint.degenerate": {
        "ru": "Вырожденных полигонов (нулевая площадь): {count}. "
        "Blender → Mesh → Clean Up → Degenerate Dissolve",
        "en": "Degenerate polygons (zero area): {count}. "
        "Blender → Mesh → Clean Up → Degenerate Dissolve",
    },
    "check.polygons.hint.budget": {
        "ru": "Полигонаж превышает бюджет {budget} на {percent}% — нужен Decimate или ретопология",
        "en": "Polygon count exceeds the {budget} budget by {percent}% — use Decimate or retopology",
    },
    "check.polygons.hint.absurd": {
        "ru": "ТЫ СОВСЕМ ДУРАК?",
        "en": "ARE YOU COMPLETELY STUPID?",
    },
    "check.density.title": {"ru": "Сомнительные полигоны", "en": "Questionable polygons"},
    "check.density.summary.ok": {
        "ru": "на гладких участках сетка не раздута",
        "en": "smooth areas are not over-tessellated",
    },
    "check.density.summary.bad": {
        "ru": "{regions} гладких зон с избыточной сеткой, {faces} полигонов, можно убрать ~{excess}",
        "en": "{regions} over-tessellated smooth zones, {faces} polygons, ~{excess} can go",
    },
    "check.density.hint": {
        "ru": "Плавная форма набрана слишком мелкой сеткой: средний излом {mean}°. "
        "Ту же гладкость можно получить с меньшим числом полигонов — Decimate "
        "или ретопология, не Limited Dissolve",
        "en": "A smooth shape is built from an overly fine mesh: average crease {mean}°. "
        "The same smoothness needs fewer polygons — use Decimate or retopology, "
        "not Limited Dissolve",
    },
    "check.normals.title": {"ru": "Неправильные нормали", "en": "Wrong normals"},
    "check.normals.summary": {
        "ru": "вывернутых полигонов {flipped}, обход вершин {winding}",
        "en": "{flipped} flipped polygons, winding {winding}",
    },
    "check.normals.winding.ok": {"ru": "согласован", "en": "consistent"},
    "check.normals.winding.bad": {"ru": "не согласован", "en": "inconsistent"},
    "check.normals.hint.flipped": {
        "ru": "Вывернуто наружу/внутрь полигонов: {count} ({percent}%). "
        "Blender → Edit Mode → Shift+N (Recalculate Outside)",
        "en": "Polygons facing the wrong way: {count} ({percent}%). "
        "Blender → Edit Mode → Shift+N (Recalculate Outside)",
    },
    "check.normals.hint.inverted": {
        "ru": "Нормали всей модели смотрят внутрь — объём отрицательный, нужен Flip Normals",
        "en": "Every normal points inwards — volume is negative, use Flip Normals",
    },
    "check.normals.hint.broken": {
        "ru": "Полигонов без валидной нормали: {count} (нулевая площадь или дубли вершин)",
        "en": "Polygons without a valid normal: {count} (zero area or duplicate vertices)",
    },
    "check.vertices.title": {"ru": "Дубли и скопления вершин", "en": "Duplicate and clustered vertices"},
    "check.vertices.summary": {
        "ru": "{total} вершин, дублей {duplicated}, скоплений {hotspots}, потерянных {stray}",
        "en": "{total} vertices, {duplicated} duplicates, {hotspots} clusters, {stray} loose",
    },
    "check.vertices.hint.container": {
        "ru": "Формат {suffix} разрезает вершины по нормалям и UV, поэтому {count} совпадений — "
        "особенность контейнера, а не дефект модели. Чтобы проверить сварку вершин, "
        "экспортируйте в {formats}",
        "en": "The {suffix} format splits vertices by normals and UVs, so {count} matches are a "
        "container trait rather than a model defect. To check welding, export to {formats}",
    },
    "check.vertices.hint.merge": {
        "ru": "Merge by Distance убрал бы {count} вершин (M → By Distance в режиме редактирования)",
        "en": "Merge by Distance would remove {count} vertices (M → By Distance in edit mode)",
    },
    "check.vertices.hint.duplicates": {
        "ru": "Дублирующихся вершин: {count}, точек с дублями: {places}, максимум в одной точке: "
        "{largest}. Blender → Merge by Distance (M → By Distance)",
        "en": "Duplicate vertices: {count}, affected spots: {places}, most in one spot: "
        "{largest}. Blender → Merge by Distance (M → By Distance)",
    },
    "check.vertices.hint.hotspots": {
        "ru": "Скоплений вершин в микрообъёме: {count}, крупнейшее — {largest} вершин. "
        "Проверьте эти зоны на схлопнутую геометрию",
        "en": "Vertex clusters in a tiny volume: {count}, largest holds {largest}. "
        "Check these spots for collapsed geometry",
    },
    "check.vertices.hint.stray": {
        "ru": "Вершин, не входящих ни в один полигон: {count} → Clean Up → Delete Loose",
        "en": "Vertices not used by any polygon: {count} → Clean Up → Delete Loose",
    },
    "check.curvature.title": {"ru": "Нехватка полигонов на изгибах", "en": "Missing polygons on curves"},
    "check.curvature.summary.ok": {
        "ru": "изломов на рёбрах нет",
        "en": "no creases on edges",
    },
    "check.curvature.summary.listed": {
        "ru": "изломы: {angles}",
        "en": "creases: {angles}",
    },
    "check.curvature.summary.bad": {
        "ru": "{regions} угловатых зон, {faces} полигонов, изломы: {angles}",
        "en": "{regions} angular zones, {faces} polygons, creases: {angles}",
    },
    "check.curvature.hint": {
        "ru": "Плавные поверхности собраны из плоских кусков: изломы {angles}. "
        "Задето {percent}% площади. Добавьте рёбер на этих участках "
        "или примените Subdivision Surface",
        "en": "Smooth surfaces are built from flat chunks: creases {angles}. "
        "Covers {percent}% of the area. Add edge loops there "
        "or apply Subdivision Surface",
    },
    "check.curvature.hint.angles": {
        "ru": "Найденные углы излома: {angles}",
        "en": "Crease angles found: {angles}",
    },
    "console.title": {
        "ru": "3DCheck — анализатор оптимизации 3D-моделей",
        "en": "3DCheck — 3D model optimization analyzer",
    },
    "console.supported": {"ru": "Поддерживаются: {list}", "en": "Supported: {list}"},
    "console.drop": {
        "ru": "Перетащи файл в окно консоли или вставь путь (Enter — выход)",
        "en": "Drop a file onto the console window or paste a path (Enter to quit)",
    },
    "console.prompt": {"ru": "Путь к модели: ", "en": "Model path: "},
    "console.cancelled": {"ru": "Файл не выбран, выход", "en": "No file selected, exiting"},
    "console.loading": {"ru": "Загрузка и анализ: {name} ...", "en": "Loading and analyzing: {name} ..."},
    "console.error": {"ru": "ОШИБКА: {error}", "en": "ERROR: {error}"},
    "console.crash": {
        "ru": "Не удалось разобрать файл ({kind}): {error}",
        "en": "Could not parse the file ({kind}): {error}",
    },
    "console.results": {"ru": "РЕЗУЛЬТАТЫ ПРОВЕРОК", "en": "CHECK RESULTS"},
    "console.penalty": {"ru": "штраф: -{value}", "en": "penalty: -{value}"},
    "console.score": {"ru": "ОЦЕНКА: {score}/100", "en": "SCORE: {score}/100"},
    "console.verdict": {"ru": "ВЕРДИКТ: {grade}", "en": "VERDICT: {grade}"},
    "console.problems": {
        "ru": "Найдено проблем: {count} — {list}",
        "en": "Issues found: {count} — {list}",
    },
    "console.clean": {
        "ru": "Проблем не обнаружено, модель готова к использованию",
        "en": "No issues found, the model is ready to use",
    },
    "stat.file": {"ru": "Файл", "en": "File"},
    "stat.faces": {"ru": "Полигонов", "en": "Polygons"},
    "stat.vertices": {"ru": "Вершин", "en": "Vertices"},
    "stat.bodies": {"ru": "Объектов в сетке", "en": "Bodies in mesh"},
    "stat.dimensions": {"ru": "Габариты", "en": "Size"},
    "stat.area": {"ru": "Площадь поверхности", "en": "Surface area"},
    "stat.watertight": {"ru": "Замкнутый объём", "en": "Watertight"},
    "stat.file.value": {"ru": "{name}  ({size} МБ)", "en": "{name}  ({size} MB)"},
    "stat.vertices.value": {
        "ru": "{total} (уникальных {unique})",
        "en": "{total} (unique {unique})",
    },
}


@dataclass(frozen=True)
class Message:
    key: str
    args: dict[str, Any] = field(default_factory=dict)


def msg(key: str, **args: Any) -> Message:
    return Message(key, args)


class Translator:
    def __init__(self, language: str = FALLBACK) -> None:
        self.language: str = language if language in LANGUAGES else FALLBACK

    def set_language(self, language: str) -> None:
        self.language = language if language in LANGUAGES else FALLBACK

    def __call__(self, key: str | Message, **values: Any) -> str:
        if isinstance(key, Message):
            values = {**key.args, **values}
            key = key.key
        table = STRINGS.get(key)
        if table is None:
            return key
        text = table.get(self.language) or table.get(FALLBACK) or key
        if not values:
            return text
        resolved = {
            name: self(value) if isinstance(value, Message) else value
            for name, value in values.items()
        }
        return text.format(**resolved)
