from __future__ import annotations

import tkinter as tk
from pathlib import Path

import numpy as np
import trimesh
from OpenGL import GL, GLU
from PIL import Image
from pyopengltk import OpenGLFrame

BACKGROUND = (0.11, 0.12, 0.15, 1.0)
BASE_COLOR = (0.72, 0.74, 0.78)
WIRE_COLOR = (0.20, 0.22, 0.26)

FACE_LAYERS: dict[str, tuple[str, tuple[float, float, float]]] = {
    "faces_redundant": ("Лишние полигоны", (0.96, 0.82, 0.20)),
    "faces_faceted": ("Нехватка полигонов", (0.42, 0.55, 1.00)),
    "faces_degenerate": ("Вырожденные полигоны", (1.00, 0.52, 0.10)),
    "faces_flipped": ("Вывернутые нормали", (0.94, 0.22, 0.24)),
}
POINT_LAYERS: dict[str, tuple[str, tuple[float, float, float]]] = {
    "points_duplicates": ("Дубли вершин", (1.00, 0.24, 0.85)),
    "points_hotspots": ("Скопления вершин", (0.20, 0.95, 0.92)),
    "points_stray": ("Вершины вне полигонов", (1.00, 1.00, 1.00)),
}
LAYER_ORDER: list[str] = [*FACE_LAYERS, *POINT_LAYERS]
LAYER_TITLES: dict[str, str] = {
    key: value[0] for group in (FACE_LAYERS, POINT_LAYERS) for key, value in group.items()
}
LAYER_COLORS: dict[str, tuple[float, float, float]] = {
    key: value[1] for group in (FACE_LAYERS, POINT_LAYERS) for key, value in group.items()
}


class MeshViewer(OpenGLFrame):
    def __init__(self, master: tk.Misc, **kwargs: object) -> None:
        super().__init__(master, **kwargs)
        self.animate = 0
        self.width = 1
        self.height = 1

        self._positions: np.ndarray | None = None
        self._normals: np.ndarray | None = None
        self._colors: np.ndarray | None = None
        self._base_colors: np.ndarray | None = None
        self._faces: np.ndarray | None = None
        self._markers: dict[str, np.ndarray] = {}
        self._points: dict[str, np.ndarray] = {}

        self._center = np.zeros(3, dtype=np.float64)
        self._radius = 1.0
        self._yaw = 30.0
        self._pitch = -20.0
        self._distance = 3.0
        self._pan = np.zeros(2, dtype=np.float64)
        self._drag: tuple[int, int] | None = None
        self._drag_mode = "rotate"

        self.wireframe = False
        self.visible: dict[str, bool] = {key: True for key in LAYER_ORDER}

        self.bind("<ButtonPress-1>", self._on_press_rotate)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<ButtonPress-3>", self._on_press_pan)
        self.bind("<B3-Motion>", self._on_drag)
        self.bind("<ButtonRelease-3>", self._on_release)
        self.bind("<Shift-ButtonPress-1>", self._on_press_pan)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Double-Button-1>", lambda _event: self.reset_view())

    def set_mesh(self, mesh: trimesh.Trimesh, markers: dict[str, np.ndarray] | None = None) -> None:
        faces = np.asarray(mesh.faces, dtype=np.int64)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        self._faces = faces
        self._positions = vertices[faces].reshape(-1, 3).astype(np.float32)
        self._normals = np.repeat(
            np.asarray(mesh.face_normals, dtype=np.float32), 3, axis=0
        ).astype(np.float32)
        self._base_colors = np.tile(
            np.array(BASE_COLOR, dtype=np.float32), (len(self._positions), 1)
        )
        self._markers = dict(markers or {})
        self._points = {
            key: np.asarray(self._markers.get(key, np.empty((0, 3))), dtype=np.float32)
            for key in POINT_LAYERS
        }

        bounds = np.asarray(mesh.bounds, dtype=np.float64)
        self._center = bounds.mean(axis=0)
        self._radius = float(np.linalg.norm(bounds[1] - bounds[0])) * 0.5 or 1.0
        self._rebuild_colors()
        self.reset_view()

    def clear(self) -> None:
        self._positions = None
        self._normals = None
        self._colors = None
        self._points = {}
        self.refresh()

    def reset_view(self) -> None:
        self._yaw = 30.0
        self._pitch = -20.0
        self._distance = self._radius * 2.6
        self._pan[:] = 0.0
        self.refresh()

    def set_view(self, yaw: float, pitch: float) -> None:
        self._yaw = float(yaw)
        self._pitch = float(np.clip(pitch, -89.9, 89.9))
        self.refresh()

    def set_layer(self, key: str, state: bool) -> None:
        self.visible[key] = bool(state)
        if key in FACE_LAYERS:
            self._rebuild_colors()
        self.refresh()

    def set_wireframe(self, state: bool) -> None:
        self.wireframe = bool(state)
        self.refresh()

    def refresh(self) -> None:
        if self.winfo_ismapped():
            self.tkExpose(None)

    def save_screenshot(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.update_idletasks()
        self.tkMakeCurrent()
        self.redraw()
        GL.glFinish()
        GL.glReadBuffer(GL.GL_BACK)
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        raw = GL.glReadPixels(0, 0, self.width, self.height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        pixels = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)
        Image.fromarray(pixels[::-1]).save(target)
        self.tkSwapBuffers()
        return target

    def _rebuild_colors(self) -> None:
        if self._base_colors is None:
            return
        colors = self._base_colors.copy()
        for key, (_, color) in FACE_LAYERS.items():
            if not self.visible.get(key, True):
                continue
            ids = np.asarray(self._markers.get(key, np.empty(0)), dtype=np.int64)
            if ids.size == 0:
                continue
            corners = (ids[:, None] * 3 + np.arange(3)[None, :]).ravel()
            colors[corners] = np.array(color, dtype=np.float32)
        self._colors = colors

    def initgl(self) -> None:
        GL.glClearColor(*BACKGROUND)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_NORMALIZE)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)
        GL.glEnable(GL.GL_LIGHT1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glLightModeli(GL.GL_LIGHT_MODEL_TWO_SIDE, 1)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, (0.4, 0.7, 1.0, 0.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, (0.85, 0.85, 0.85, 1.0))
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, (-0.6, -0.3, -0.8, 0.0))
        GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, (0.35, 0.35, 0.40, 1.0))
        GL.glLightModelfv(GL.GL_LIGHT_MODEL_AMBIENT, (0.25, 0.25, 0.28, 1.0))
        GL.glEnable(GL.GL_POINT_SMOOTH)
        GL.glHint(GL.GL_POINT_SMOOTH_HINT, GL.GL_NICEST)

    def tkResize(self, event: tk.Event) -> None:
        self.width = max(int(event.width), 1)
        self.height = max(int(event.height), 1)
        if self.winfo_ismapped():
            self.tkMakeCurrent()
            GL.glViewport(0, 0, self.width, self.height)

    def redraw(self) -> None:
        GL.glViewport(0, 0, self.width, self.height)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if self._positions is None:
            return

        near = max(self._radius * 0.01, 1e-4)
        far = self._distance + self._radius * 10.0
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GLU.gluPerspective(45.0, self.width / max(self.height, 1), near, far)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glTranslatef(self._pan[0], self._pan[1], -self._distance)
        GL.glRotatef(self._pitch, 1.0, 0.0, 0.0)
        GL.glRotatef(self._yaw, 0.0, 1.0, 0.0)
        GL.glTranslatef(*(-self._center))

        self._draw_surface()
        self._draw_points()

    def _draw_surface(self) -> None:
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_NORMAL_ARRAY)
        GL.glEnableClientState(GL.GL_COLOR_ARRAY)
        GL.glVertexPointer(3, GL.GL_FLOAT, 0, self._positions)
        GL.glNormalPointer(GL.GL_FLOAT, 0, self._normals)
        GL.glColorPointer(3, GL.GL_FLOAT, 0, self._colors)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.0, 1.0)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(self._positions))
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glDisableClientState(GL.GL_COLOR_ARRAY)
        GL.glDisableClientState(GL.GL_NORMAL_ARRAY)

        if self.wireframe:
            GL.glDisable(GL.GL_LIGHTING)
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
            GL.glColor3f(*WIRE_COLOR)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(self._positions))
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_FILL)
            GL.glEnable(GL.GL_LIGHTING)

        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)

    def _draw_points(self) -> None:
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glPointSize(7.0)
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        for key, points in self._points.items():
            if not self.visible.get(key, True) or len(points) == 0:
                continue
            GL.glColor3f(*LAYER_COLORS[key])
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, points)
            GL.glDrawArrays(GL.GL_POINTS, 0, len(points))
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        GL.glPointSize(1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_LIGHTING)

    def _on_press_rotate(self, event: tk.Event) -> None:
        self._drag = (event.x, event.y)
        self._drag_mode = "rotate"

    def _on_press_pan(self, event: tk.Event) -> None:
        self._drag = (event.x, event.y)
        self._drag_mode = "pan"

    def _on_release(self, _event: tk.Event) -> None:
        self._drag = None

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag is None:
            return
        dx = event.x - self._drag[0]
        dy = event.y - self._drag[1]
        self._drag = (event.x, event.y)
        if self._drag_mode == "pan":
            speed = self._distance * 0.0018
            self._pan[0] += dx * speed
            self._pan[1] -= dy * speed
        else:
            self._yaw += dx * 0.5
            self._pitch = float(np.clip(self._pitch + dy * 0.5, -89.9, 89.9))
        self.refresh()

    def _on_wheel(self, event: tk.Event) -> None:
        steps = event.delta / 120.0 if event.delta else 0.0
        self._distance = float(
            np.clip(self._distance * (0.88**steps), self._radius * 0.05, self._radius * 60.0)
        )
        self.refresh()
