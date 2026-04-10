import bpy


class RETOPO_PT_main_panel(bpy.types.Panel):
    bl_label      = "Retopo Helper"
    bl_idname     = "RETOPO_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = 'Retopo'

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
        box.operator("retopo.snap", text="Snap Selected", icon='SNAP_ON')

        # -------------------------------------------------------------------------
        # SMART RELAX
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Smart Relax", icon='MOD_SMOOTH')

        row = box.row(align=True)
        row.prop(props, "relax_mode", expand=True)

        box.prop(props, "relax_strength",   text="Strength")
        box.prop(props, "relax_iterations", text="Iterations")
        box.operator("retopo.relax", text="Relax Selected", icon='MOD_SMOOTH')

        # -------------------------------------------------------------------------
        # ANALYZE & STATS
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Analyze & Stats", icon='ZOOM_ALL')

        # Фільтри + поріг
        row = box.row(align=True)
        row.prop(props, "show_poles", text="Poles",  toggle=True)
        row.prop(props, "show_tris",  text="Tris",   toggle=True)
        row.prop(props, "show_ngons", text="N-Gons", toggle=True)

        box.prop(props, "pole_threshold", text="Pole Threshold")
        box.operator("retopo.analyze", text="Analyze Mesh", icon='ZOOM_ALL')

        box.separator(factor=0.5)

        # Статистика
        col = box.column(align=True)

        if stats.is_valid:
            # Геометрія
            row = col.row()
            row.label(text=f"Vertices: {stats.total_verts}")
            row.label(text=f"Edges: {stats.total_edges}")
            row.label(text=f"Faces: {stats.total_faces}")

            col.separator(factor=0.5)

            # Розбивка полігонів з відсотками
            total_faces = stats.total_faces
            if total_faces > 0:
                quad_count  = total_faces - stats.tri_count - stats.ngon_count
                quad_pct    = quad_count        / total_faces * 100
                tri_pct     = stats.tri_count   / total_faces * 100
                ngon_pct    = stats.ngon_count  / total_faces * 100
            else:
                quad_count = 0
                quad_pct = tri_pct = ngon_pct = 0.0

            # Quads
            row = col.row()
            row.label(text=f"Quads:  {quad_count}", icon='MESH_PLANE')
            row.label(text=f"{quad_pct:.1f}%")

            # Tris
            icon_tri = 'ERROR' if stats.tri_count > 0 else 'CHECKMARK'
            row = col.row()
            row.label(text=f"Tris:   {stats.tri_count}", icon=icon_tri)
            row.label(text=f"{tri_pct:.1f}%")

            # N-Gons
            icon_ng = 'ERROR' if stats.ngon_count > 0 else 'CHECKMARK'
            row = col.row()
            row.label(text=f"N-Gons: {stats.ngon_count}", icon=icon_ng)
            row.label(text=f"{ngon_pct:.1f}%")

            col.separator(factor=0.5)
            col.operator("retopo.stats", text="Full Report", icon='ZOOM_ALL')
        else:
            col.label(text="Vertices: —   Edges: —   Faces: —")
            row = col.row()
            row.label(text="Quads: —%")
            row.label(text="Tris: —%")
            row.label(text="N-Gons: —%")

        # -------------------------------------------------------------------------
        # DECIMATION
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Decimation", icon='MOD_DECIM')

        box.prop(props, "decimate_ratio", text="Ratio")

        # Попередній перегляд кількості граней після спрощення
        obj = context.active_object
        if obj and obj.type == 'MESH':
            current_faces = len(obj.data.polygons)
            preview_faces = int(current_faces * props.decimate_ratio)
            row = box.row()
            row.label(text=f"Result: ~{preview_faces} faces", icon='INFO')

        box.operator("retopo.decimate", text="Apply Decimation", icon='MOD_DECIM')

        # -------------------------------------------------------------------------
        # FILL HOLES
        # -------------------------------------------------------------------------
        box = layout.box()
        box.label(text="Fill Holes", icon='MESH_GRID')
        box.operator("retopo.fill_holes", text="Fill Holes", icon='MESH_GRID')


def register():
    try:
        bpy.utils.register_class(RETOPO_PT_main_panel)
    except RuntimeError:
        pass


def unregister():
    try:
        bpy.utils.unregister_class(RETOPO_PT_main_panel)
    except RuntimeError:
        pass