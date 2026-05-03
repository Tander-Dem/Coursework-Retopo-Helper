import bpy
from bpy.props import (
    PointerProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
)
from bpy.types import PropertyGroup


class RetopoHelperProperties(PropertyGroup):

    # -------------------------------------------------------------------------
    # Snap
    # -------------------------------------------------------------------------
    snap_target: PointerProperty(
        name="Target Object",
        description="High-poly model to snap vertices onto",
        type=bpy.types.Object,
    )

    snap_max_distance: FloatProperty(
        name="Max Distance",
        description="Maximum ray distance for surface projection",
        default=0.1,
        min=0.001,
        max=10.0,
    )

    # -------------------------------------------------------------------------
    # Relax
    # -------------------------------------------------------------------------
    relax_strength: FloatProperty(
        name="Strength",
        description="Relax strength",
        default=0.5,
        min=0.0,
        max=1.0,
    )

    relax_iterations: IntProperty(
        name="Iterations",
        description="Number of relax iterations",
        default=1,
        min=1,
        max=10,
    )

    relax_mode: EnumProperty(
        name="Mode",
        items=[
            ("UNIFORM",    "Uniform",    "Even vertex distribution"),
            ("CURVATURE",  "Curvature",  "Curvature-aware relaxation"),
        ],
        default="UNIFORM",
    )

    # -------------------------------------------------------------------------
    # Decimate
    # -------------------------------------------------------------------------
    decimate_ratio: FloatProperty(
        name="Ratio",
        description="Fraction of faces to keep",
        default=0.5,
        min=0.1,
        max=1.0,
    )

    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Maximum distance between vertices to merge",
        default=0.001,
        min=0.00001,
        max=1.0,
        precision=4,
    )

    # -------------------------------------------------------------------------
    # Analyze — фільтри виділення
    # -------------------------------------------------------------------------
    show_poles: BoolProperty(
        name="Show Poles",
        description="Highlight pole vertices",
        default=True,
    )

    show_tris: BoolProperty(
        name="Show Triangles",
        description="Highlight triangle faces",
        default=True,
    )

    show_ngons: BoolProperty(
        name="Show N-Gons",
        description="Highlight n-gon faces",
        default=True,
    )

    # Кількість ребер, яка вважається «нормальною» для вершини.
    # 4 — стандарт для квад-сіток; 3 — для трикутних; можна змінити в панелі.
    pole_threshold: IntProperty(
        name="Pole Threshold",
        description=(
            "Edge count considered 'regular' for a vertex. "
            "Vertices with a different count are flagged as poles"
        ),
        default=4,
        min=3,
        max=16,
    )
    

class RetopoStatsProperties(PropertyGroup):
    """Зберігає результати останнього запуску retopo.analyze."""

    is_valid: BoolProperty(
        name="Has Results",
        description="True after at least one successful analysis",
        default=False,
    )

    # Загальна геометрія
    total_verts: IntProperty(name="Vertices", default=0)
    total_edges: IntProperty(name="Edges",    default=0)
    total_faces: IntProperty(name="Faces",    default=0)

    # Проблеми
    pole_count:  IntProperty(name="Poles",     default=0)
    tri_count:   IntProperty(name="Triangles", default=0)
    ngon_count:  IntProperty(name="N-Gons",    default=0)


def register():
    # Очищаємо старі класи якщо залишились в пам'яті
    for cls in (RetopoStatsProperties, RetopoHelperProperties):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    bpy.utils.register_class(RetopoHelperProperties)
    bpy.utils.register_class(RetopoStatsProperties)
    bpy.types.Scene.retopo_helper = PointerProperty(type=RetopoHelperProperties)
    bpy.types.Scene.retopo_stats = PointerProperty(type=RetopoStatsProperties)


def unregister():
    if hasattr(bpy.types.Scene, "retopo_stats"):
        del bpy.types.Scene.retopo_stats
    if hasattr(bpy.types.Scene, "retopo_helper"):
        del bpy.types.Scene.retopo_helper

    for cls in (RetopoStatsProperties, RetopoHelperProperties):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

