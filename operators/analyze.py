import bpy
import bmesh
from bpy.types import Operator

from ..utils.topology_utils import collect_topology
from ..utils.mesh_utils import select_verts_by_index, select_faces_by_index


# ---------------------------------------------------------------------------
# RETOPO_OT_analyze
# ---------------------------------------------------------------------------

class RETOPO_OT_analyze(Operator):
    """Аналізує топологію: виділяє poles, трикутники та n-gони"""
    bl_idname = "retopo.analyze"
    bl_label = "Analyze Mesh"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    def execute(self, context):
        obj   = context.active_object
        props = context.scene.retopo_helper
        stats = context.scene.retopo_stats

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        poles, tris, ngons = collect_topology(bm, props.pole_threshold)

        # --- Знімаємо все виділення перед новим ---
        for v in bm.verts: v.select = False
        for e in bm.edges: e.select = False
        for f in bm.faces: f.select = False

        # --- Виділяємо відповідно до прапорців ---
        if props.show_poles:
            select_verts_by_index(bm, poles)

        if props.show_tris:
            select_faces_by_index(bm, tris)

        if props.show_ngons:
            select_faces_by_index(bm, ngons)

        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        # --- Зберігаємо статистику ---
        stats.pole_count  = len(poles)
        stats.tri_count   = len(tris)
        stats.ngon_count  = len(ngons)
        stats.total_verts = len(bm.verts)
        stats.total_edges = len(bm.edges)
        stats.total_faces = len(bm.faces)
        stats.is_valid    = True

        total_issues = len(poles) + len(tris) + len(ngons)

        if total_issues == 0:
            self.report({'INFO'}, "Topology is clean — no issues found.")
        else:
            parts = []
            if poles: parts.append(f"{len(poles)} pole(s)")
            if tris:  parts.append(f"{len(tris)} tri(s)")
            if ngons: parts.append(f"{len(ngons)} n-gon(s)")
            self.report({'WARNING'}, "Found: " + ", ".join(parts))

        return {'FINISHED'}


# ---------------------------------------------------------------------------
# RETOPO_OT_stats  (відображення останнього аналізу у popup)
# ---------------------------------------------------------------------------

class RETOPO_OT_stats(Operator):
    """Показує результати останнього аналізу топології"""
    bl_idname = "retopo.stats"
    bl_label = "Mesh Statistics"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.scene.retopo_stats.is_valid

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=260)

    def draw(self, context):
        layout = self.layout
        stats  = context.scene.retopo_stats
        props  = context.scene.retopo_helper

        layout.label(text="Last Analysis Results", icon='ZOOM_ALL')
        layout.separator()

        # --- Геометрія ---
        box = layout.box()
        box.label(text="Geometry", icon='MESH_DATA')
        col = box.column(align=True)
        col.label(text=f"Vertices : {stats.total_verts}")
        col.label(text=f"Edges    : {stats.total_edges}")
        col.label(text=f"Faces    : {stats.total_faces}")

        layout.separator()

        # --- Проблеми ---
        box = layout.box()
        box.label(text="Issues", icon='ERROR')
        col = box.column(align=True)

        if props.show_poles:
            icon = 'LAYER_ACTIVE' if stats.pole_count > 0 else 'CHECKMARK'
            col.label(
                text=f"Poles (≠{props.pole_threshold} edges) : {stats.pole_count}",
                icon=icon,
            )
        if props.show_tris:
            icon = 'LAYER_ACTIVE' if stats.tri_count > 0 else 'CHECKMARK'
            col.label(text=f"Triangles  : {stats.tri_count}", icon=icon)

        if props.show_ngons:
            icon = 'LAYER_ACTIVE' if stats.ngon_count > 0 else 'CHECKMARK'
            col.label(text=f"N-Gons     : {stats.ngon_count}", icon=icon)

        total = stats.pole_count + stats.tri_count + stats.ngon_count
        layout.separator()
        if total == 0:
            layout.label(text="Mesh is clean ✓", icon='CHECKMARK')
        else:
            layout.label(text=f"Total issues: {total}", icon='ERROR')

    def execute(self, context):
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    RETOPO_OT_analyze,
    RETOPO_OT_stats,
)


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