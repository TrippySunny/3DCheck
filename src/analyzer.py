from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import KDTree

try:
    from i18n import FALLBACK, Message, Translator, msg
except ModuleNotFoundError:
    from src.i18n import FALLBACK, Message, Translator, msg

OK = "ok"
WARNING = "warning"
CRITICAL = "critical"


class AnalyzerError(Exception):
    def __init__(self, message: Message) -> None:
        super().__init__(Translator(FALLBACK)(message))
        self.message = message


@dataclass
class CheckResult:
    code: str
    severity: str
    penalty: float
    summary: Message
    stats: dict[str, Any] = field(default_factory=dict)
    hints: list[Message] = field(default_factory=list)
    markers: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def title(self) -> Message:
        return msg(f"check.{self.code}.title")


@dataclass
class AnalysisReport:
    source: Path
    score: float
    grade: Message
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
    ABSURD_FACE_MIN: int = 1_000_000
    ABSURD_SMOOTH_FACES: int = 150_000
    OVERDENSE_SMOOTH_MAX: float = 12.0
    OVERDENSE_ANGLE: float = 8.0
    OVERDENSE_TARGET: float = 10.0
    OVERDENSE_REGION_MIN: int = 64
    FACET_FACE_LIMIT: int = 400_000
    FACET_ANGLE_MIN: float = 38.0
    FACET_ANGLE_MAX: float = 65.0
    CREASE_LIST_MIN: float = 8.0
    CREASE_LIST_MAX: float = 80.0
    FACET_REGION_MIN: int = 4
    HOTSPOT_MIN_VERTICES: int = 6
    GRADES: tuple[tuple[float, str], ...] = (
        (90.0, "grade.excellent"),
        (75.0, "grade.good"),
        (55.0, "grade.average"),
        (35.0, "grade.poor"),
        (0.0, "grade.critical"),
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
            raise AnalyzerError(msg("error.not_found", path=self.path))
        suffix = self.path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            raise AnalyzerError(
                msg("error.format", suffix=suffix, supported=", ".join(self.SUPPORTED_EXTENSIONS))
            )
        loaded = trimesh.load(self.path, force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            parts = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            loaded = trimesh.util.concatenate(parts) if parts else None
        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise AnalyzerError(msg("error.no_mesh"))
        return loaded

    def analyze(self) -> AnalysisReport:
        checks = [
            self.check_polygons(),
            self.check_density(),
            self.check_normals(),
            self.check_vertices(),
            self.check_curvature(),
        ]
        score = float(np.clip(100.0 - sum(check.penalty for check in checks), 0.0, 100.0))
        return AnalysisReport(
            source=self.path,
            score=score,
            grade=self._grade(score),
            checks=checks,
            stats=self.summary(),
            mesh=self.welded,
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
            penalty += min(55.0, (budget_ratio - 1.0) * 18.0)

        hints: list[Message] = []
        if redundant_ratio > 0.05:
            hints.append(
                msg(
                    "check.polygons.hint.redundant",
                    count=redundant,
                    percent=f"{redundant_ratio * 100:.1f}",
                )
            )
        if degenerate:
            hints.append(msg("check.polygons.hint.degenerate", count=degenerate))
        if budget_ratio > 1.0:
            hints.append(
                msg(
                    "check.polygons.hint.budget",
                    budget=f"{self.polygon_budget:,}".replace(",", " "),
                    percent=f"{(budget_ratio - 1.0) * 100:.0f}",
                )
            )

        return CheckResult(
            code="polygons",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=msg(
                "check.polygons.summary",
                faces=faces,
                redundant=redundant,
                degenerate=degenerate,
            ),
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

    def check_density(self) -> CheckResult:
        mesh = self.welded
        faces = int(len(mesh.faces))
        overdense_ids, regions, excess, average = self._overdense_regions()
        area = float(mesh.area)
        share = (
            float(mesh.area_faces[overdense_ids].sum() / area)
            if overdense_ids.size and area > 0
            else 0.0
        )
        penalty = (
            min(40.0, share * 32.0 + min(18.0, excess / max(faces, 1) * 40.0)) if regions else 0.0
        )
        hints: list[Message] = []
        if regions:
            hints.append(msg("check.density.hint", mean=f"{average:.1f}"))
        if faces >= self.ABSURD_FACE_MIN or overdense_ids.size >= self.ABSURD_SMOOTH_FACES:
            hints.append(msg("check.polygons.hint.absurd"))
            penalty = max(penalty, 40.0)

        return CheckResult(
            code="density",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=(
                msg(
                    "check.density.summary.bad",
                    regions=regions,
                    faces=int(overdense_ids.size),
                    excess=excess,
                )
                if regions
                else msg("check.density.summary.ok")
            ),
            stats={
                "overdense_regions": regions,
                "overdense_faces": int(overdense_ids.size),
                "excess_faces": excess,
                "area_percent": round(share * 100, 1),
                "mean_angle": round(average, 2),
            },
            hints=hints,
            markers={"faces_overdense": overdense_ids},
        )

    def check_normals(self) -> CheckResult:
        mesh = self.welded
        watertight = bool(mesh.is_watertight)
        winding_consistent = bool(mesh.is_winding_consistent)
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
        if broken:
            penalty += 5.0

        hints: list[Message] = []
        if flipped:
            hints.append(
                msg(
                    "check.normals.hint.flipped",
                    count=flipped,
                    percent=f"{flipped_ratio * 100:.1f}",
                )
            )
        if inverted:
            hints.append(msg("check.normals.hint.inverted"))
        if broken:
            hints.append(msg("check.normals.hint.broken", count=broken))

        return CheckResult(
            code="normals",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=msg(
                "check.normals.summary",
                flipped=flipped,
                winding=msg(
                    "check.normals.winding.ok"
                    if winding_consistent
                    else "check.normals.winding.bad"
                ),
            ),
            stats={
                "is_watertight": watertight,
                "winding_consistent": winding_consistent,
                "flipped_faces": flipped,
                "flipped_percent": round(flipped_ratio * 100, 2),
                "inverted_volume": inverted,
                "broken_normals": broken,
            },
            hints=hints,
            markers={"faces_flipped": flipped_ids},
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

        hints: list[Message] = []
        if split_by_format and duplicated:
            hints.append(
                msg(
                    "check.vertices.hint.container",
                    suffix=self.path.suffix.lower(),
                    count=duplicated,
                    formats=", ".join(self.TOPOLOGY_FORMATS),
                )
            )
        elif duplicated and not duplicate_groups:
            hints.append(msg("check.vertices.hint.merge", count=duplicated))
        elif duplicated:
            hints.append(
                msg(
                    "check.vertices.hint.duplicates",
                    count=duplicated,
                    places=len(duplicate_groups),
                    largest=largest_duplicate,
                )
            )
        if hotspots:
            hints.append(
                msg(
                    "check.vertices.hint.hotspots",
                    count=len(hotspots),
                    largest=largest_hotspot,
                )
            )
        if stray:
            hints.append(msg("check.vertices.hint.stray", count=stray))

        return CheckResult(
            code="vertices",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=msg(
                "check.vertices.summary",
                total=total,
                duplicated=duplicated,
                hotspots=len(hotspots),
                stray=stray,
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

    def check_curvature(self) -> CheckResult:
        mesh = self.welded
        empty = np.empty(0, dtype=np.int64)
        faces = int(len(mesh.faces))
        pairs = np.asarray(mesh.face_adjacency, dtype=np.int64).reshape(-1, 2)
        faceted_ids = empty
        regions = 0
        worst = 0.0
        average = 0.0
        creases = np.empty(0, dtype=np.float64)

        if pairs.size and faces:
            angles = np.degrees(np.asarray(mesh.face_adjacency_angles, dtype=np.float64))
            creases = angles[
                (angles >= self.CREASE_LIST_MIN) & (angles <= self.CREASE_LIST_MAX)
            ]
            bends = (angles >= self.FACET_ANGLE_MIN) & (angles <= self.FACET_ANGLE_MAX)
            if np.any(bends):
                touched = np.zeros(faces, dtype=bool)
                touched[pairs[bends].reshape(-1)] = True
                smooth = pairs[angles <= self.FACET_ANGLE_MAX]
                graph = coo_matrix(
                    (np.ones(len(smooth), dtype=np.int8), (smooth[:, 0], smooth[:, 1])),
                    shape=(faces, faces),
                )
                _, labels = connected_components(graph, directed=False)
                counts = np.bincount(labels[touched], minlength=int(labels.max()) + 1)
                wanted = np.flatnonzero(counts >= self.FACET_REGION_MIN)
                if wanted.size:
                    keep = touched & np.isin(labels, wanted)
                    faceted_ids = np.flatnonzero(keep)
                    picked = angles[bends][keep[pairs[bends][:, 0]]]
                    regions = int(wanted.size)
                    worst = float(picked.max())
                    average = float(picked.mean())

        area = float(mesh.area)
        share = (
            float(mesh.area_faces[faceted_ids].sum() / area)
            if faceted_ids.size and area > 0
            else 0.0
        )
        penalty = (
            min(22.0, share * 25.0 + average / self.FACET_ANGLE_MAX * 10.0) if regions else 0.0
        )
        angle_text = self._format_angles(creases)
        hints: list[Message] = []
        if regions:
            hints.append(
                msg(
                    "check.curvature.hint",
                    angles=angle_text or f"{average:.0f}°",
                    percent=f"{share * 100:.0f}",
                )
            )

        if regions:
            summary = msg(
                "check.curvature.summary.bad",
                regions=regions,
                faces=int(faceted_ids.size),
                angles=angle_text or f"{average:.0f}°",
            )
        elif angle_text:
            summary = msg("check.curvature.summary.listed", angles=angle_text)
        else:
            summary = msg("check.curvature.summary.ok")

        return CheckResult(
            code="curvature",
            severity=self._severity(penalty),
            penalty=penalty,
            summary=summary,
            stats={
                "faceted_regions": regions,
                "faceted_faces": int(faceted_ids.size),
                "area_percent": round(share * 100, 1),
                "mean_angle": round(average, 1),
                "max_angle": round(worst, 1),
                "crease_angles": [int(value) for value in np.unique(np.round(creases, 0))]
                if creases.size
                else [],
                "angle_window": [self.FACET_ANGLE_MIN, self.FACET_ANGLE_MAX],
            },
            hints=hints,
            markers={"faces_faceted": faceted_ids},
        )

    @staticmethod
    def _format_angles(degrees: np.ndarray) -> str:
        if degrees.size == 0:
            return ""
        unique = np.unique(np.round(degrees, 0).astype(np.int64))
        return ", ".join(f"{int(value)}°" for value in unique)

    def _overdense_regions(self) -> tuple[np.ndarray, int, int, float]:
        mesh = self.welded
        empty = np.empty(0, dtype=np.int64)
        faces = int(len(mesh.faces))
        pairs = np.asarray(mesh.face_adjacency, dtype=np.int64).reshape(-1, 2)
        if not pairs.size or not faces:
            return empty, 0, 0, 0.0
        angles = np.degrees(np.asarray(mesh.face_adjacency_angles, dtype=np.float64))
        smooth = angles <= self.OVERDENSE_SMOOTH_MAX
        if not np.any(smooth):
            return empty, 0, 0, 0.0
        selected = pairs[smooth]
        graph = coo_matrix(
            (np.ones(len(selected), dtype=np.int8), (selected[:, 0], selected[:, 1])),
            shape=(faces, faces),
        )
        _, labels = connected_components(graph, directed=False)
        counts = np.bincount(labels, minlength=int(labels.max()) + 1)
        left = labels[pairs[:, 0]]
        right = labels[pairs[:, 1]]
        marked: list[np.ndarray] = []
        excess = 0
        regions = 0
        collected: list[float] = []
        for cid in np.flatnonzero(counts >= self.OVERDENSE_REGION_MIN):
            inside = (left == cid) & (right == cid)
            if not np.any(inside):
                continue
            mean_angle = float(angles[inside].mean())
            if mean_angle > self.OVERDENSE_ANGLE:
                continue
            members = np.flatnonzero(labels == cid)
            if self._region_is_planar(members):
                continue
            count = int(members.size)
            target = max(
                self.OVERDENSE_REGION_MIN,
                int(count * (mean_angle / self.OVERDENSE_TARGET) ** 2),
            )
            if count <= target:
                continue
            marked.append(members)
            excess += count - target
            regions += 1
            collected.append(mean_angle)
        ids = np.concatenate(marked) if marked else empty
        average = float(np.mean(collected)) if collected else 0.0
        if ids.size == 0 and faces >= self.ABSURD_SMOOTH_FACES and angles.size:
            mean_all = float(angles.mean())
            if mean_all <= self.OVERDENSE_ANGLE and not self._region_is_planar(np.arange(faces)):
                leftover = max(faces - self.OVERDENSE_REGION_MIN, 0)
                return np.arange(faces, dtype=np.int64), 1, leftover, mean_all
        return ids, regions, excess, average

    def _coplanar_redundancy(self) -> tuple[int, np.ndarray]:
        mesh = self.welded
        empty = np.empty(0, dtype=np.int64)
        if len(mesh.faces) > self.FACET_FACE_LIMIT:
            return 0, empty
        total = 0
        marked: list[np.ndarray] = []
        for facet, boundary in zip(mesh.facets, mesh.facets_boundary):
            used = int(len(facet))
            corners = self._boundary_corners(boundary)
            if corners < 3 or not self._facet_is_planar(facet):
                continue
            minimal = max(corners - 2, 1)
            if used > minimal:
                total += used - minimal
                marked.append(np.asarray(facet, dtype=np.int64))
        return total, np.concatenate(marked) if marked else empty

    def _facet_is_planar(self, facet: np.ndarray) -> bool:
        return self._region_is_planar(np.asarray(facet, dtype=np.int64))

    def _region_is_planar(self, face_ids: np.ndarray) -> bool:
        points = self.welded.vertices[np.unique(self.welded.faces[face_ids])]
        if len(points) < 4:
            return True
        centered = points - points.mean(axis=0)
        singular = np.linalg.svd(centered, compute_uv=False)
        return float(singular[-1] / (singular[0] + 1e-12)) <= 0.02

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
    def _grade(cls, score: float) -> Message:
        for threshold, key in cls.GRADES:
            if score >= threshold:
                return msg(key)
        return msg(cls.GRADES[-1][1])
