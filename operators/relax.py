import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator


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

    # Рахуємо constraint для кожної вершини один раз перед ітераціями
    constraints = {v: _get_move_constraint(v) for v in selected}

    for _ in range(iterations):
        targets = []

        for vert in selected:
            constraint = constraints[vert]

            # Повністю заблокована — пропускаємо
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
                # Вільна вершина — повний рух
                new_co = vert.co + delta * strength
            else:
                # Вздовж sharp краю — проєктуємо delta на напрямок краю
                edge_dir     = constraint  # Vector вздовж краю
                delta_along  = edge_dir * delta.dot(edge_dir)
                new_co       = vert.co + delta_along * strength

            targets.append((vert, new_co))

        # Jacobi-step
        for vert, new_co in targets:
            vert.co = new_co

    return len(selected)


# ---------------------------------------------------------------------------
# Curvature Relax
# ---------------------------------------------------------------------------

def _is_sharp_or_seam(edge) -> bool:
    """Повертає True якщо ребро є sharp або seam."""
    return edge.smooth is False or edge.seam


def _get_sharp_edges(vert) -> list:
    """Повертає список sharp/seam ребер що виходять з вершини."""
    return [e for e in vert.link_edges if _is_sharp_or_seam(e)]


def _get_move_constraint(vert):
    """
    Визначає обмеження руху вершини відносно sharp edges та seams.

    Повертає одне з трьох:
      None        — вершина вільна (не на sharp/seam)
      'blocked'   — вершина заблокована повністю:
                      - кутова (3+ sharp ребра)
                      - кінець краю (1 sharp ребро)
      Vector      — одиничний вектор вздовж краю:
                      - пряма ділянка (рівно 2 sharp ребра)
                      вершина може рухатись тільки вздовж цього вектора
    """
    sharp_edges = _get_sharp_edges(vert)
    n = len(sharp_edges)

    if n == 0:
        # Вершина не на sharp/seam — вільна
        return None

    if n == 1 or n >= 3:
        # Кінець краю або кутова вершина — повністю заблокована
        return 'blocked'

    # Рівно 2 sharp ребра — пряма ділянка краю
    # Напрямок руху = вздовж краю між двома сусідніми sharp вершинами
    v1 = sharp_edges[0].other_vert(vert)
    v2 = sharp_edges[1].other_vert(vert)

    edge_vec = v2.co - v1.co
    length   = edge_vec.length

    if length < 1e-8:
        return 'blocked'

    return edge_vec / length  # одиничний вектор вздовж краю


def _calc_vert_normal(vert) -> Vector:
    """
    Усереднена нормаль вершини через прилеглі грані.
    Якщо граней немає — повертає vert.normal як fallback.
    """
    faces = vert.link_faces
    if not faces:
        return vert.normal.copy()

    normal = Vector((0.0, 0.0, 0.0))
    for f in faces:
        normal += f.normal
    normal /= len(faces)

    length = normal.length
    return normal / length if length > 1e-8 else vert.normal.copy()


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

    # Рахуємо constraint для кожної вершини один раз перед ітераціями
    constraints = {v: _get_move_constraint(v) for v in selected}

    for _ in range(iterations):
        targets = []

        for vert in selected:
            constraint = constraints[vert]

            # Повністю заблокована — пропускаємо
            if constraint == 'blocked':
                continue

            neighbors = [e.other_vert(vert) for e in vert.link_edges]
            if not neighbors:
                continue

            # Центроїд сусідів
            centroid = Vector((0.0, 0.0, 0.0))
            for nb in neighbors:
                centroid += nb.co
            centroid /= len(neighbors)

            # Нормаль поверхні у вершині
            normal = _calc_vert_normal(vert)

            # Вектор зміщення
            delta = centroid - vert.co

            if constraint is None:
                # Вільна вершина — проєкція на дотичну площину поверхні
                delta_tangent = delta - normal * delta.dot(normal)
            else:
                # Вздовж sharp краю — проєктуємо на напрямок краю
                # і додатково прибираємо компоненту вздовж нормалі
                edge_dir      = constraint
                delta_along   = edge_dir * delta.dot(edge_dir)
                delta_tangent = delta_along - normal * delta_along.dot(normal)

            targets.append((vert, delta_tangent))

        # Jacobi-step
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

        # Оновлюємо нормалі граней перед curvature relax —
        # щоб _calc_vert_normal отримувала актуальні дані
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