import bpy


class RETOPO_PT_main_panel(bpy.types.Panel):
    bl_label = "Retopo Helper"
    bl_idname = "RETOPO_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Retopo'

    def draw(self, context):
        layout = self.layout
        props  = context.scene.retopo_helper
        stats  = context.scene.retopo_stats

        # -------------------------------------------------------------------------
        # SNAP
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Snap to Surface", icon='SNAP_ON')
        box.prop(props, "snap_target", text="Target")
        box.operator("retopo.snap", text="Snap Selected")

        # -------------------------------------------------------------------------
        # RELAX
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Relax Vertices", icon='MOD_SMOOTH')
        box.prop(props, "relax_strength",   text="Strength")
        box.prop(props, "relax_iterations", text="Iterations")
        box.operator("retopo.relax", text="Relax Selected")

        # -------------------------------------------------------------------------
        # ANALYZE
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Analyze Topology", icon='ZOOM_ALL')

        # Поріг для визначення pole
        box.prop(props, "pole_threshold", text="Pole Threshold")

        # Фільтри виділення в один рядок
        row = box.row(align=True)
        row.prop(props, "show_poles", text="Poles",  toggle=True)
        row.prop(props, "show_tris",  text="Tris",   toggle=True)
        row.prop(props, "show_ngons", text="N-Gons", toggle=True)

        box.operator("retopo.analyze", text="Analyze Mesh", icon='ZOOM_ALL')

        # -------------------------------------------------------------------------
        # STATS — компактний inline-preview після аналізу
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Mesh Stats", icon='INFO')

        if stats.is_valid:
            # Геометрія (одним рядком щоб не займати місце)
            row = box.row()
            row.label(text=f"V: {stats.total_verts}")
            row.label(text=f"E: {stats.total_edges}")
            row.label(text=f"F: {stats.total_faces}")

            # Проблеми
            col = box.column(align=True)
            total_issues = stats.pole_count + stats.tri_count + stats.ngon_count

            if props.show_poles:
                icon = 'ERROR' if stats.pole_count > 0 else 'CHECKMARK'
                col.label(
                    text=f"Poles  : {stats.pole_count}",
                    icon=icon,
                )
            if props.show_tris:
                icon = 'ERROR' if stats.tri_count > 0 else 'CHECKMARK'
                col.label(text=f"Tris   : {stats.tri_count}", icon=icon)

            if props.show_ngons:
                icon = 'ERROR' if stats.ngon_count > 0 else 'CHECKMARK'
                col.label(text=f"N-Gons : {stats.ngon_count}", icon=icon)

            box.separator(factor=0.5)

            # Повний popup
            op_row = box.row()
            op_row.operator("retopo.stats", text="Full Report", icon='ZOOM_ALL')
        else:
            box.label(text="Run Analyze first", icon='INFO')

        # -------------------------------------------------------------------------
        # FILL HOLES
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Fill Holes", icon='MESH_GRID')
        box.operator("retopo.fill_holes", text="Fill Holes")

def register():
    try:
        bpy.utils.register_class(RETOPO_PT_main_panel)
    except RuntimeError:
        pass  # Already registered


def unregister():
    try:
        bpy.utils.unregister_class(RETOPO_PT_main_panel)
    except RuntimeError:
        pass  # Not registered