import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _project_vertices(retopo_obj, highpoly_obj, context) -> dict:
    """
    Проєктує вибрані вершини retopo_obj на поверхню highpoly_obj через ray_cast.

    Напрямок кидання — трансформована нормаль вершини (world space).
    Якщо прямий кидок не дав результату, пробуємо зворотний (-normal).

    Повертає:
        {
            "projected": int,   # успішно проєктовано
            "missed":    int,   # промах в обох напрямках
            "skipped":   int,   # не вибрані вершини
        }
    """
    depsgraph = context.evaluated_depsgraph_get()

    # Evaluated high-poly враховує всі модифікатори (Subdivision, Multires…)
    hp_eval       = highpoly_obj.evaluated_get(depsgraph)
    hp_mw         = highpoly_obj.matrix_world
    hp_mw_inv     = hp_mw.inverted()
    hp_mw_inv_3x3 = hp_mw_inv.to_3x3()

    retopo_mw     = retopo_obj.matrix_world
    retopo_mw_inv = retopo_mw.inverted()
    retopo_mw_3x3 = retopo_mw.to_3x3()

    bm = bmesh.from_edit_mesh(retopo_obj.data)
    bm.verts.ensure_lookup_table()

    result = {"projected": 0, "missed": 0, "skipped": 0}

    for vert in bm.verts:
        if not vert.select:
            result["skipped"] += 1
            continue

        # --- Позиція та нормаль у world space ---
        co_world     = retopo_mw @ vert.co
        normal_world = (retopo_mw_3x3 @ vert.normal).normalized()

        if normal_world.length_squared < 1e-10:
            result["missed"] += 1
            continue

        # --- Переводимо промінь у локальний простір high-poly ---
        co_local  = hp_mw_inv @ co_world
        dir_local = (hp_mw_inv_3x3 @ normal_world).normalized()

        hit_fwd, loc_fwd, _, _ = hp_eval.ray_cast(co_local,  dir_local)
        hit_bwd, loc_bwd, _, _ = hp_eval.ray_cast(co_local, -dir_local)

        if hit_fwd and hit_bwd:
            # беремо ближче
            dist_fwd = (hp_mw @ loc_fwd - co_world).length
            dist_bwd = (hp_mw @ loc_bwd - co_world).length
            loc_local = loc_fwd if dist_fwd < dist_bwd else loc_bwd
        elif hit_fwd:
            loc_local = loc_fwd
        elif hit_bwd:
            loc_local = loc_bwd
        else:
            result["missed"] += 1
            continue

        # Переводимо точку влучання назад у локальний простір retopo
        loc_world = hp_mw @ loc_local
        vert.co   = retopo_mw_inv @ loc_world
        result["projected"] += 1

    bmesh.update_edit_mesh(retopo_obj.data, loop_triangles=False, destructive=False)

    return result


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class RETOPO_OT_snap(Operator):
    """Проєктує вибрані вершини на поверхню high-poly через ray_cast"""

    bl_idname = "retopo.snap"
    bl_label  = "Snap to Surface"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj   = context.active_object
        props = context.scene.retopo_helper
        return (
            obj is not None
            and obj.type == "MESH"
            and context.mode == "EDIT_MESH"
            and props.snap_target is not None
            and props.snap_target is not obj   # не можна снепати об'єкт сам на себе
        )

    def execute(self, context):
        retopo_obj   = context.active_object
        highpoly_obj = context.scene.retopo_helper.snap_target

        # Перевіряємо, що target — меш
        if highpoly_obj.type != "MESH":
            self.report({"ERROR"}, f'"{highpoly_obj.name}" is not a mesh object.')
            return {"CANCELLED"}

        result = _project_vertices(retopo_obj, highpoly_obj, context)

        projected = result["projected"]
        missed    = result["missed"]

        if projected == 0 and missed == 0:
            self.report({"WARNING"}, "No vertices selected.")
            return {"CANCELLED"}

        if missed:
            self.report(
                {"WARNING"},
                f"Snapped {projected} vert(s). "
                f"{missed} missed (no surface hit in either direction).",
            )
        else:
            self.report({"INFO"}, f"Snapped {projected} vert(s) successfully.")

        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (RETOPO_OT_snap,)


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