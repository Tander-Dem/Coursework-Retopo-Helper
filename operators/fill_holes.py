import bpy


class RETOPO_OT_fill_holes(bpy.types.Operator):
    bl_idname = "retopo.fill_holes"
    bl_label = "Fill Holes"
    bl_description = "Fill holes in selected mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Тимчасово — логіку додамо пізніше
        self.report({'INFO'}, "Fill Holes — coming soon")
        return {'FINISHED'}


def register():
    try:
        bpy.utils.register_class(RETOPO_OT_fill_holes)
    except RuntimeError:
        pass


def unregister():
    try:
        bpy.utils.unregister_class(RETOPO_OT_fill_holes)
    except RuntimeError:
        pass
