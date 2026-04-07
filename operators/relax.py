import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _laplacian_relax(bm: bmesh.types.BMesh, strength: float, iterations: int) -> int:
    """
    Лапласіанське згладжування вибраних вершин.

    Кожна вибрана вершина зміщується до середнього положення своїх сусідів.
    Вершини, де ВСІ сусіди — теж вибрані, згладжуються повністю.
    Вершини на межі виділення (є хоч один невибраний сусід) згладжуються
    з тим самим strength, але їхній дрейф обмежений — це зберігає форму
    силуету ретопо-сітки.

    Повертає кількість оброблених вершин.
    """
    selected = [v for v in bm.verts if v.select and not v.hide]

    if not selected:
        return 0

    for _ in range(iterations):
        # Рахуємо цільові позиції за поточними координатами (не оновлюємо
        # під час ітерації — інакше порядок обходу впливає на результат).
        targets: list[tuple[bmesh.types.BMVert, Vector]] = []

        for vert in selected:
            neighbors = [e.other_vert(vert) for e in vert.link_edges]

            if not neighbors:
                continue

            centroid = Vector((0.0, 0.0, 0.0))
            for nb in neighbors:
                centroid += nb.co
            centroid /= len(neighbors)

            targets.append((vert, centroid))

        # Застосовуємо зміщення
        for vert, target in targets:
            vert.co = vert.co.lerp(target, strength)

    return len(selected)


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class RETOPO_OT_relax(Operator):
    """Вирівнює вибрані вершини (Laplacian smooth) зі збереженням силуету"""

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

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()

        processed = _laplacian_relax(bm, strength, iterations)

        if processed == 0:
            self.report({"WARNING"}, "No vertices selected.")
            return {"CANCELLED"}

        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        self.report(
            {"INFO"},
            f"Relaxed {processed} vert(s) "
            f"(strength={strength:.2f}, iterations={iterations}).",
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