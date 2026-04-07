bl_info = {
    "name": "Retopo Helper",
    "author": "Tander",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Retopo",
    "description": "Helper tools for manual retopology",
    "category": "Mesh",
}

import bpy
import importlib
from . import ui
from . import operators
from . import properties
from .operators import snap, relax, analyze, fill_holes
from .ui import panel

modules = (
    properties,
    snap,
    relax,
    analyze,
    fill_holes,
    panel,
)

def reload_modules():
    for mod in modules:
        importlib.reload(mod)

if "bpy" in dir():
    reload_modules()

def register():
    properties.register()
    snap.register()
    relax.register()
    analyze.register()
    fill_holes.register()
    panel.register()


def unregister():
    panel.unregister()
    fill_holes.unregister()
    analyze.unregister()
    relax.unregister()
    snap.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()