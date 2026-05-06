"""
topology_utils.py — Утиліти для роботи з топологією меша.

Збір boundary loops та аналіз топологічних проблем.
Імпортуються з будь-якого модуля плагіна:
    from .topology_utils import collect_boundary_loops, collect_selected_loops, collect_topology
"""

import bmesh


# ---------------------------------------------------------------------------
# Boundary loops
# ---------------------------------------------------------------------------

def collect_boundary_loops(bm: bmesh.types.BMesh) -> list[list]:
    """
    Збирає всі замкнені boundary loops меша.

    Обходить boundary edges, групуючи їх у впорядковані ланцюжки вершин.
    Повертає список loops; кожен loop — список BMVert (мінімум 3, замкнений).
    """
    boundary_edges = {e for e in bm.edges if e.is_boundary}
    if not boundary_edges:
        return []

    loops = []
    while boundary_edges:
        start_edge = next(iter(boundary_edges))
        boundary_edges.discard(start_edge)
        verts        = [start_edge.verts[0], start_edge.verts[1]]
        current_vert = start_edge.verts[1]

        while True:
            next_edge = None
            for e in current_vert.link_edges:
                if e in boundary_edges:
                    next_edge = e
                    break
            if next_edge is None:
                break
            boundary_edges.discard(next_edge)
            next_vert = (
                next_edge.verts[1]
                if next_edge.verts[0] == current_vert
                else next_edge.verts[0]
            )
            verts.append(next_vert)
            current_vert = next_vert
            if current_vert == start_edge.verts[0]:
                break

        is_closed = (current_vert == start_edge.verts[0])
        if is_closed and len(verts) >= 3:
            if verts[-1] == verts[0]:
                verts = verts[:-1]
            loops.append(verts)

    return loops


def collect_selected_loops(bm: bmesh.types.BMesh) -> list[list]:
    """
    Повертає тільки ті boundary loops, у яких більше половини ребер виділено.

    Використовується оператором Fill Selected щоб заповнювати лише
    вручну відредаговане виділення після Find Holes.
    """
    all_loops = collect_boundary_loops(bm)
    if not all_loops:
        return []

    selected_loops = []
    for verts in all_loops:
        loop_edges = []
        for i in range(len(verts)):
            v1, v2 = verts[i], verts[(i + 1) % len(verts)]
            edge = bm.edges.get((v1, v2))
            if edge:
                loop_edges.append(edge)
        if not loop_edges:
            continue
        if sum(1 for e in loop_edges if e.select) / len(loop_edges) > 0.5:
            selected_loops.append(verts)

    return selected_loops


# ---------------------------------------------------------------------------
# Топологічний аналіз
# ---------------------------------------------------------------------------

def collect_topology(bm: bmesh.types.BMesh, pole_threshold: int) -> tuple[list, list, list]:
    """
    Аналізує топологію меша і повертає три списки індексів BMesh-елементів:

      poles  — вершини де кількість ребер != pole_threshold
      tris   — грані з 3 вершинами
      ngons  — грані з 5+ вершинами

    Args:
        bm:              Поточний BMesh.
        pole_threshold:  Очікувана кількість ребер на вершину (зазвичай 4).
    """
    poles = [v.index for v in bm.verts if len(v.link_edges) != pole_threshold]
    tris  = [f.index for f in bm.faces if len(f.verts) == 3]
    ngons = [f.index for f in bm.faces if len(f.verts) >= 5]
    return poles, tris, ngons