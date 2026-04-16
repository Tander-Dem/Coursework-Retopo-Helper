import bpy
from bpy.types import Operator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_decimate(obj, ratio: float) -> dict:
    """
    Додає Decimate modifier (Collapse) на obj, застосовує його і видаляє.

    Повертає:
        {
            "faces_before": int,
            "faces_after":  int,
        }
    """
    faces_before = len(obj.data.polygons)

    mod = obj.modifiers.new(name="RetopoDeci", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio         = ratio
    mod.use_collapse_triangulate = False  # зберігаємо quad де можливо

    bpy.ops.object.modifier_apply(modifier=mod.name)

    faces_after = len(obj.data.polygons)

    return {"faces_before": faces_before, "faces_after": faces_after}


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class RETOPO_OT_decimate(Operator):
    """Спрощує активний меш через Decimate Collapse зі збереженням форми"""

    bl_idname  = "retopo.decimate"
    bl_label   = "Apply Decimation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == "MESH"
            and context.mode == "OBJECT"
        )

    def invoke(self, context, event):
        """Показуємо діалог підтвердження — операція незворотня без Undo."""
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj   = context.active_object
        props = context.scene.retopo_helper
        ratio = props.decimate_ratio

        if ratio >= 1.0:
            self.report({"INFO"}, "Ratio is 1.0 — nothing to decimate.")
            return {"CANCELLED"}

        result = _apply_decimate(obj, ratio)

        faces_before = result["faces_before"]
        faces_after  = result["faces_after"]
        removed      = faces_before - faces_after

        self.report(
            {"INFO"},
            f"Decimated: {faces_before} → {faces_after} faces "
            f"({removed} removed, ratio={ratio:.2f}).",
        )
        return {"FINISHED"}


class RETOPO_OT_merge_by_distance(Operator):
    """Об'єднуємо вершини, розташовані ближче, ніж задана відстань"""

    bl_idname  = "retopo.merge_by_distance"
    bl_label   = "Merge by Distance"
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
        props = context.scene.retopo_helper
        # remove_doubles працює на вибраних вершинах в Edit Mode
        result = bpy.ops.mesh.remove_doubles(
            threshold=props.merge_distance
        )
        # result містить {"FINISHED"} або {"CANCELLED"}
        self.report({"INFO"}, f"Merged vertices closer than {props.merge_distance:.4f}.")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (RETOPO_OT_decimate, RETOPO_OT_merge_by_distance)


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