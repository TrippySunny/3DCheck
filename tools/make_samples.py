from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

OUTPUT = Path(__file__).resolve().parents[1] / "samples"


def export(mesh: trimesh.Trimesh, name: str) -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / name
    mesh.export(target)
    return target


def clean_sphere() -> list[Path]:
    mesh = trimesh.creation.icosphere(subdivisions=3)
    return [export(mesh, "clean_sphere.obj"), export(mesh, "clean_sphere.stl")]


def overtessellated_plane(resolution: int = 60) -> list[Path]:
    xs, ys = np.meshgrid(
        np.linspace(0.0, 1.0, resolution),
        np.linspace(0.0, 1.0, resolution),
    )
    vertices = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(resolution * resolution)])
    faces = []
    for row in range(resolution - 1):
        for column in range(resolution - 1):
            corner = row * resolution + column
            faces.append([corner, corner + 1, corner + resolution])
            faces.append([corner + 1, corner + resolution + 1, corner + resolution])
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=False)
    return [export(mesh, "overtessellated_plane.obj")]


def broken_sphere() -> list[Path]:
    base = trimesh.creation.icosphere(subdivisions=3)
    vertices = base.vertices.copy()
    faces = base.faces.copy()
    chunks = [vertices]

    duplicated = np.arange(40)
    offset = len(vertices)
    for index, vertex_id in enumerate(duplicated):
        chunks.append(vertices[vertex_id][None, :])
        touched = np.where(faces == vertex_id)[0][:1]
        for face_id in touched:
            faces[face_id][faces[face_id] == vertex_id] = offset + index

    generator = np.random.default_rng(0)
    cluster = np.array([2.0, 0.0, 0.0]) + generator.normal(scale=1e-4, size=(30, 3))
    chunks.append(cluster)
    cluster_start = offset + len(duplicated)
    cluster_faces = [[cluster_start + i, cluster_start + i + 1, cluster_start + i + 2] for i in range(28)]

    chunks.append(np.array([[5.0, 5.0, 5.0], [5.1, 5.0, 5.0], [5.2, 5.0, 5.0]]))

    vertices = np.vstack(chunks)
    faces = np.vstack([faces, np.array(cluster_faces)])
    faces[:120] = faces[:120][:, ::-1]

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    return [export(mesh, "broken_sphere.obj")]


def main() -> int:
    created: list[Path] = []
    created += clean_sphere()
    created += overtessellated_plane()
    created += broken_sphere()
    for path in created:
        print(f"создано: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
