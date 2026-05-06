import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator

from ..utils.mesh_utils import get_move_constraint, calc_vert_normal


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _laplacian_relax(bm: bmesh.types.BMesh, strength: float, iterations: int) -> int:
    """
    Лапласіанське згладжування вибраних вершин з підтримкою sharp edges.

    Кожна вибрана вершина зміщується до центроїда сусідів.
    Обмеження руху залежно від позиції вершини:
      - Вільна вершина        → повний рух до центроїда
      - На прямому sharp краї → рух тільки вздовж краю
      - Кутова / кінець краю  → повністю заблокована

    Jacobi-step: всі цільові позиції рахуються до оновлення координат.
    Повертає кількість оброблених вершин.
    """
    selected = [v for v in bm.verts if v.select and not v.hide]

    if not selected:
        return 0

    constraints = {v: get_move_constraint(v) for v in selected}

    for _ in range(iterations):
        targets = []

        for vert in selected:
            constraint = constraints[vert]

            if constraint == 'blocked':
                continue

            neighbors = [e.other_vert(vert) for e in vert.link_edges]
            if not neighbors:
                continue

            centroid = Vector((0.0, 0.0, 0.0))
            for nb in neighbors:
                centroid += nb.co
            centroid /= len(neighbors)

            delta = centroid - vert.co

            if constraint is None:
                new_co = vert.co + delta * strength
            else:
                edge_dir    = constraint
                delta_along = edge_dir * delta.dot(edge_dir)
                new_co      = vert.co + delta_along * strength

            targets.append((vert, new_co))

        for vert, new_co in targets:
            vert.co = new_co

    return len(selected)


# ---------------------------------------------------------------------------
# Curvature Relax
# ---------------------------------------------------------------------------

def _curvature_relax(bm: bmesh.types.BMesh, strength: float, iterations: int) -> int:
    """
    Curvature-aware Лапласіанське згладжування.

    Відрізняється від звичайного Лапласіана тим що зміщення
    проєктується на дотичну площину поверхні — вершина рухається
    ВЗДОВЖ поверхні а не крізь неї.

    Алгоритм для кожної вершини:
      1. Рахуємо нормаль поверхні в точці (усереднена по прилеглих гранях)
      2. Рахуємо цільову позицію — центроїд сусідів (як у Лапласіані)
      3. Вектор зміщення delta = centroid - vert.co
      4. Проєктуємо delta на дотичну площину:
             delta_tangent = delta - normal * delta.dot(normal)
         Це прибирає компоненту вздовж нормалі — зміщення йде по поверхні
      5. Вершини на sharp edges або seams — заблоковані (не рухаються)
      6. Jacobi-step: всі цілі рахуються до оновлення координат

    Повертає кількість оброблених вершин.
    """
    selected = [v for v in bm.verts if v.select and not v.hide]

    if not selected:
        return 0

    constraints = {v: get_move_constraint(v) for v in selected}

    for _ in range(iterations):
        targets = []

        for vert in selected:
            constraint = constraints[vert]

            if constraint == 'blocked':
                continue

            neighbors = [e.other_vert(vert) for e in vert.link_edges]
            if not neighbors:
                continue

            centroid = Vector((0.0, 0.0, 0.0))
            for nb in neighbors:
                centroid += nb.co
            centroid /= len(neighbors)

            normal = calc_vert_normal(vert)
            delta  = centroid - vert.co

            if constraint is None:
                delta_tangent = delta - normal * delta.dot(normal)
            else:
                edge_dir      = constraint
                delta_along   = edge_dir * delta.dot(edge_dir)
                delta_tangent = delta_along - normal * delta_along.dot(normal)

            targets.append((vert, delta_tangent))

        for vert, delta_tangent in targets:
            vert.co += delta_tangent * strength

    return len(selected)


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class RETOPO_OT_relax(Operator):
    bl_description = (
        "Вирівнює вибрані вершини з двома режимами. "
        "Uniform — Лапласіанське згладжування до центроїда сусідів. "
        "Curvature — зміщення вздовж поверхні через проєкцію на дотичну площину, "
        "вершини на sharp edges та seams заблоковані"
    )

    bl_idname  = "retopo.relax"
    bl_label   = "Relax Vertices"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == "MESH"
            and context.mode == "EDIT_MESH"
        )

    def execute(self, context):
        obj   = context.active_object
        props = context.scene.retopo_helper

        strength   = props.relax_strength
        iterations = props.relax_iterations
        mode       = props.relax_mode

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()

        if mode == 'CURVATURE':
            bm.faces.ensure_lookup_table()
            for f in bm.faces:
                f.normal_update()

        if mode == 'UNIFORM':
            processed = _laplacian_relax(bm, strength, iterations)
        else:
            processed = _curvature_relax(bm, strength, iterations)

        if processed == 0:
            self.report({"WARNING"}, "No vertices selected.")
            return {"CANCELLED"}

        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        self.report(
            {"INFO"},
            f"Relaxed {processed} vert(s) — "
            f"mode={mode.lower()}, strength={strength:.2f}, iterations={iterations}.",
        )
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (RETOPO_OT_relax,)


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            pass


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass