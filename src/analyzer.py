from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import KDTree

OK = "ok"
WARNING = "warning"
CRITICAL = "critical"


@dataclass
class CheckResult:
    code: str
    title: str
    severity: str
    penalty: float
    summary: str
    stats: dict[str, Any] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)
    markers: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class AnalysisReport:
    source: Path
    score: float
    grade: str
    checks: list[CheckResult]
    stats: dict[str, Any]
    mesh: trimesh.Trimesh | None = None

    @property
    def problems(self) -> list[CheckResult]:
        return [check for check in self.checks if check.severity != OK]

    @property
    def markers(self) -> dict[str, np.ndarray]:
        merged: dict[str, np.ndarray] = {}
        for check in self.checks:
            merged.update(check.markers)
        return merged


class MeshAnalyzer:
    SUPPORTED_EXTENSIONS: tuple[str, ...] = (
        ".obj",
        ".stl",
        ".ply",
        ".glb",
        ".gltf",
        ".off",
        ".3mf",
        ".dae",
    )
    TOPOLOGY_FORMATS: tuple[str, ...] = (".obj", ".ply", ".off")
    POLYGON_BUDGET: int = 100_000
    FACET_FACE_LIMIT: int = 400_000
    MARK_MIN_EXCESS: int = 2
    HOTSPOT_MIN_VERTICES: int = 6
    GRADES: tuple[tuple[float, str], ...] = (
        (90.0, "Отличная оптимизация"),
        (75.0, "Хорошо, есть мелкие замечания"),
        (55.0, "Средне, модель требует доработки"),
        (35.0, "Плохо, много дефектов геометрии"),
        (0.0, "Критично, модель стоит переделать"),
    )

    def __init__(self, path: str | Path, polygon_budget: int | None = None) -> None:
        self.path: Path = Path(path).expanduser().resolve()
        self.polygon_budget: int = int(polygon_budget or self.POLYGON_BUDGET)
        self.raw: trimesh.Trimesh = self._load()
        self.shaded: trimesh.Trimesh = self.raw.copy()
        self.shaded.merge_vertices()
        self.welded: trimesh.Trimesh = self.raw.copy()
        self.welded.merge_vertices(merge_tex=True, merge_norm=True)
        self.scale: float = float(self.raw.scale) if self.raw.scale > 0 else 1.0
        self.weld_tolerance: float = max(self.scale * 1e-6, 1e-9)
        self.cluster_radius: float = self.scale * 1e-3

    def _load(self) -> trimesh.Trimesh:
        if not self.path.is_file():
            raise FileNotFoundError(f"Файл не найден: {self.path}")
        suffix = self.path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            supported = ", ".join(self.SUPPORTED_EXTENSIONS)
            raise ValueError(f"Формат «{suffix}» не поддерживается. Доступные: {supported}")
        loaded = trimesh.load(self.path, force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            parts = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            loaded = trimesh.util.concatenate(parts) if parts else None
        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise ValueError("В файле не найдено полигональной сетки")
        return loaded

    def analyze(self) -> AnalysisReport:
        checks = [
            self.check_polygons(),
            self.check_normals(),
            self.check_vertices(),
        ]
        score = float(np.clip(100.0 - sum(check.penalty for check in checks), 0.0, 100.0))
        return AnalysisReport(
            source=self.path,
            score=score,
            grade=self._grade(score),
            checks=checks,
            stats=self.summary(),
            mesh=self.raw,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "file": self.path.name,
            "format": self.path.suffix.lower(),
            "size_mb": round(self.path.stat().st_size / 1024 / 1024, 2),
            "faces": int(len(self.raw.faces)),
            "vertices": int(len(self.raw.vertices)),
            "shaded_vertices": int(len(self.shaded.vertices)),
            "welded_vertices": int(len(self.welded.vertices)),
            "bodies": int(self.welded.body_count),
            "dimensions": [round(float(value), 4) for value in self.raw.extents],
            "surface_area": round(float(self.welded.area), 4),
            "watertight": bool(self.welded.is_watertight),
        }

    def check_polygons(self) -> CheckResult:
        mesh = self.welded
        faces = int(len(mesh.faces))
        area_threshold = max(float(mesh.area) * 1e-9, 1e-12)
        degenerate_ids = np.flatnonzero(mesh.area_faces <= area_threshold)
        degenerate = int(degenerate_ids.size)
        redundant, redundant_ids = self._coplanar_redundancy()
        redundant_ratio = redundant / faces if faces else 0.0
        budget_ratio = faces / self.polygon_budget

        penalty = min(25.0, redundant_ratio * 60.0)
        if degenerate:
            penalty += min(15.0, 4.0 + degenerate / faces * 120.0)
        if budget_ratio > 1.0:
            penalty += min(15.0, (budget_ratio - 1.0) * 8.0)

        hints: list[str] = []
        if redundant_ratio > 0.05:
            hints.append(
                f"На плоских участках можно убрать ~{redundant} треугольников "
                f"({redundant_ratio * 100:.1f}% сетки): Blender → Mesh → Limited Dissolve"
            )
        if degenerate:
            hints.append(
                f"Вырожденных полигонов (нулевая площадь): {degenerate}. "
                "Blender → Mesh → Clean Up → Degenerate Dissolve"
            )
        if budget_ratio > 1.0:
            budget_text = f"{self.polygon_budget:,}".replace(",", " ")
            hints.append(
                f"Полигонаж превышает бюджет {budget_text} на "
                f"{(budget_ratio - 1.0) * 100:.0f}% — нужен Decimate или ретопология"
            )

        return CheckResult(
            code="polygons",
            title="Лишние полигоны",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=f"{faces} полигонов, лишних ~{redundant}, вырожденных {degenerate}",
            stats={
                "faces": faces,
                "redundant_faces": redundant,
                "redundant_percent": round(redundant_ratio * 100, 2),
                "degenerate_faces": degenerate,
                "budget": self.polygon_budget,
                "budget_usage_percent": round(budget_ratio * 100, 1),
            },
            hints=hints,
            markers={
                "faces_degenerate": degenerate_ids,
                "faces_redundant": redundant_ids,
            },
        )

    def check_normals(self) -> CheckResult:
        mesh = self.welded
        watertight = bool(mesh.is_watertight)
        winding_consistent = bool(mesh.is_winding_consistent)
        boundary_rows = np.asarray(
            trimesh.grouping.group_rows(mesh.edges_sorted, require_count=1), dtype=np.int64
        )
        boundary_edges = int(boundary_rows.size)
        broken = int(np.count_nonzero(np.linalg.norm(mesh.face_normals, axis=1) < 0.5))

        reference = mesh.copy()
        trimesh.repair.fix_normals(reference, multibody=not watertight)
        dots = np.einsum("ij,ij->i", reference.face_normals, mesh.face_normals)
        flipped_ids = np.flatnonzero(dots < 0.0)
        flipped = int(flipped_ids.size)
        flipped_ratio = flipped / len(mesh.faces) if len(mesh.faces) else 0.0
        inverted = bool(watertight and winding_consistent and float(mesh.volume) < 0.0)

        penalty = min(30.0, flipped_ratio * 70.0)
        if not winding_consistent:
            penalty += 10.0
        if inverted:
            penalty += 12.0
        if not watertight:
            penalty += min(10.0, 3.0 + boundary_edges / max(len(mesh.edges_sorted), 1) * 40.0)
        if broken:
            penalty += 5.0

        hints: list[str] = []
        if flipped:
            hints.append(
                f"Вывернуто наружу/внутрь полигонов: {flipped} ({flipped_ratio * 100:.1f}%). "
                "Blender → Edit Mode → Shift+N (Recalculate Outside)"
            )
        if inverted:
            hints.append("Нормали всей модели смотрят внутрь — объём отрицательный, нужен Flip Normals")
        if not watertight:
            hints.append(
                f"Меш не замкнут: {boundary_edges} граничных рёбер (дыры или несшитые края). "
                "Select → All by Trait → Non Manifold"
            )
        if broken:
            hints.append(f"Полигонов без валидной нормали: {broken} (нулевая площадь или дубли вершин)")

        return CheckResult(
            code="normals",
            title="Неправильные нормали",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=(
                f"watertight={'да' if watertight else 'нет'}, "
                f"вывернутых полигонов {flipped}, граничных рёбер {boundary_edges}"
            ),
            stats={
                "is_watertight": watertight,
                "winding_consistent": winding_consistent,
                "flipped_faces": flipped,
                "flipped_percent": round(flipped_ratio * 100, 2),
                "boundary_edges": boundary_edges,
                "inverted_volume": inverted,
                "broken_normals": broken,
            },
            hints=hints,
            markers={
                "faces_flipped": flipped_ids,
                "edges_boundary": (
                    mesh.vertices[mesh.edges_sorted[boundary_rows]]
                    if boundary_edges
                    else np.empty((0, 2, 3), dtype=np.float64)
                ),
            },
        )

    def check_vertices(self) -> CheckResult:
        vertices = np.asarray(self.raw.vertices, dtype=np.float64)
        total = int(len(vertices))
        distinct = int(len(self.welded.vertices))
        declared = self._declared_vertex_count()
        split_by_format = declared is None
        groups = self._cluster(vertices, self.weld_tolerance, 2)
        duplicated = (
            int(sum(len(group) - 1 for group in groups))
            if declared is None
            else max(declared - distinct, 0)
        )
        duplicate_groups = groups if duplicated else []
        largest_duplicate = int(max((len(group) for group in duplicate_groups), default=0))
        welded_vertices = np.asarray(self.welded.vertices, dtype=np.float64)
        hotspots = self._hotspots(welded_vertices)
        largest_hotspot = int(max((len(group) for group in hotspots), default=0))
        stray_ids = np.setdiff1d(np.arange(total), np.unique(self.raw.faces))
        stray = int(stray_ids.size)
        reference = declared if declared else total
        duplicate_ratio = duplicated / reference if reference else 0.0

        penalty = 0.0
        if not split_by_format:
            penalty += min(20.0, duplicate_ratio * 45.0)
            if largest_duplicate >= 4:
                penalty += min(8.0, largest_duplicate * 0.5)
        if hotspots:
            penalty += min(12.0, 3.0 + len(hotspots) * 0.8)
        if stray:
            penalty += min(6.0, 2.0 + stray / total * 40.0)

        hints: list[str] = []
        if split_by_format and duplicated:
            keeps = ", ".join(self.TOPOLOGY_FORMATS)
            hints.append(
                f"Формат {self.path.suffix.lower()} разрезает вершины по нормалям и UV, поэтому "
                f"{duplicated} совпадений — особенность контейнера, а не дефект модели. "
                f"Чтобы проверить сварку вершин, экспортируйте в {keeps}"
            )
        elif duplicated and not duplicate_groups:
            hints.append(
                f"Merge by Distance убрал бы {duplicated} вершин "
                "(M → By Distance в режиме редактирования)"
            )
        elif duplicated:
            places = len(duplicate_groups)
            hints.append(
                f"Дублирующихся вершин: {duplicated} в {places} "
                f"{'точке' if places == 1 else 'точках'} (максимум {largest_duplicate} в одной). "
                "Blender → Merge by Distance (M → By Distance)"
            )
        if hotspots:
            hints.append(
                f"Скоплений вершин в микрообъёме: {len(hotspots)}, крупнейшее — {largest_hotspot} вершин. "
                "Проверь эти зоны на схлопнутую геометрию"
            )
        if stray:
            hints.append(f"Вершин, не входящих ни в один полигон: {stray} → Clean Up → Delete Loose")

        return CheckResult(
            code="vertices",
            title="Дубли и скопления вершин",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=(
                f"{total} вершин, дублей {duplicated}, скоплений {len(hotspots)}, "
                f"потерянных {stray}"
            ),
            stats={
                "vertices": total,
                "unique_vertices": int(len(self.welded.vertices)),
                "duplicated_vertices": duplicated,
                "duplicate_percent": round(duplicate_ratio * 100, 2),
                "duplicate_points": len(duplicate_groups),
                "largest_duplicate_group": largest_duplicate,
                "hotspots": len(hotspots),
                "largest_hotspot": largest_hotspot,
                "stray_vertices": stray,
                "format_splits_vertices": split_by_format,
            },
            hints=hints,
            markers={
                "points_duplicates": (
                    vertices[[int(group[0]) for group in duplicate_groups]]
                    if duplicate_groups and not split_by_format
                    else np.empty((0, 3), dtype=np.float64)
                ),
                "points_hotspots": (
                    welded_vertices[np.concatenate(hotspots)]
                    if hotspots
                    else np.empty((0, 3), dtype=np.float64)
                ),
                "points_stray": vertices[stray_ids],
            },
        )

    def _coplanar_redundancy(self) -> tuple[int, np.ndarray]:
        mesh = self.welded
        empty = np.empty(0, dtype=np.int64)
        if len(mesh.faces) > self.FACET_FACE_LIMIT:
            return 0, empty
        total = 0
        marked: list[np.ndarray] = []
        for facet, boundary in zip(mesh.facets, mesh.facets_boundary):
            used = int(len(facet))
            minimal = max(self._boundary_corners(boundary) - 2, 1)
            excess = used - minimal
            if excess > 0:
                total += excess
            if excess >= self.MARK_MIN_EXCESS:
                marked.append(np.asarray(facet, dtype=np.int64))
        return total, np.concatenate(marked) if marked else empty

    def _declared_vertex_count(self) -> int | None:
        suffix = self.path.suffix.lower()
        if suffix not in self.TOPOLOGY_FORMATS:
            return None
        try:
            if suffix == ".obj":
                total = 0
                with self.path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line in handle:
                        if line[:2] in ("v ", "v\t"):
                            total += 1
                return total
            if suffix == ".ply":
                with self.path.open("rb") as handle:
                    for chunk in handle:
                        line = chunk.decode("ascii", errors="ignore").strip()
                        if line.startswith("element vertex"):
                            return int(line.split()[2])
                        if line == "end_header":
                            break
                return None
            if suffix == ".off":
                with self.path.open("r", encoding="utf-8", errors="ignore") as handle:
                    first = handle.readline().strip()
                    counts = first[3:].strip() if first.upper().startswith("OFF") else first
                    while not counts:
                        counts = handle.readline().strip()
                    return int(counts.split()[0])
        except (OSError, ValueError, IndexError):
            return None
        return None

    def _boundary_corners(self, boundary: np.ndarray) -> int:
        edges = np.asarray(boundary, dtype=np.int64).reshape(-1, 2)
        if edges.size == 0:
            return 0
        endpoints = edges.reshape(-1)
        partners = edges[:, ::-1].reshape(-1)
        order = np.argsort(endpoints, kind="stable")
        unique, starts, counts = np.unique(
            endpoints[order], return_index=True, return_counts=True
        )
        paired = counts == 2
        if not np.any(paired):
            return int(unique.size)
        sorted_partners = partners[order]
        vertices = self.welded.vertices
        origin = vertices[unique[paired]]
        first = vertices[sorted_partners[starts[paired]]] - origin
        second = vertices[sorted_partners[starts[paired] + 1]] - origin
        first_norm = np.linalg.norm(first, axis=1)
        second_norm = np.linalg.norm(second, axis=1)
        usable = (first_norm > 1e-12) & (second_norm > 1e-12)
        cosine = np.zeros(len(origin))
        cosine[usable] = np.einsum(
            "ij,ij->i",
            first[usable] / first_norm[usable, None],
            second[usable] / second_norm[usable, None],
        )
        collinear = usable & (np.abs(cosine + 1.0) <= 1e-4)
        return int(unique.size - np.count_nonzero(collinear))

    def _cluster(self, points: np.ndarray, radius: float, min_size: int) -> list[np.ndarray]:
        if len(points) < min_size or radius <= 0.0:
            return []
        pairs = KDTree(points).query_pairs(r=radius, output_type="ndarray")
        if len(pairs) == 0:
            return []
        graph = coo_matrix(
            (np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])),
            shape=(len(points), len(points)),
        )
        _, labels = connected_components(graph, directed=False)
        order = np.argsort(labels, kind="stable")
        splits = np.flatnonzero(np.diff(labels[order])) + 1
        return [group for group in np.split(order, splits) if len(group) >= min_size]

    def _hotspots(self, vertices: np.ndarray) -> list[np.ndarray]:
        if len(vertices) < self.HOTSPOT_MIN_VERTICES or self.cluster_radius <= 0.0:
            return []
        tree = KDTree(vertices)
        counts = tree.query_ball_point(vertices, r=self.cluster_radius, return_length=True)
        dense = np.flatnonzero(counts >= self.HOTSPOT_MIN_VERTICES)
        if dense.size < self.HOTSPOT_MIN_VERTICES:
            return []
        subset = vertices[dense]
        groups = self._cluster(subset, self.cluster_radius, self.HOTSPOT_MIN_VERTICES)
        result: list[np.ndarray] = []
        for group in groups:
            points = subset[group]
            extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
            if extent <= self.cluster_radius * 4.0:
                result.append(dense[group])
        return result

    @staticmethod
    def _severity(penalty: float) -> str:
        if penalty >= 15.0:
            return CRITICAL
        if penalty >= 3.0:
            return WARNING
        return OK

    @classmethod
    def _grade(cls, score: float) -> str:
        for threshold, label in cls.GRADES:
            if score >= threshold:
                return label
        return cls.GRADES[-1][1]
