"""
mesh_utils.py — Спільні низькорівневі BMesh-утиліти.

Імпортуються з будь-якого модуля плагіна:
    from .mesh_utils import safe_face_add, calc_centroid, ...
"""

import bmesh
from mathutils import Vector


# ---------------------------------------------------------------------------
# Геометрія
# ---------------------------------------------------------------------------

def calc_centroid(verts: list) -> Vector:
    """Центроїд списку BMVert."""
    co = Vector((0.0, 0.0, 0.0))
    for v in verts:
        co += v.co
    return co / len(verts)


def get_neighbor_normal(verts: list):
    """
    Повертає нормаль першої знайденої прилеглої грані або None.
    Використовується для правильної орієнтації нових граней.
    """
    for v in verts:
        for f in v.link_faces:
            return f.normal.copy()
    return None


# ---------------------------------------------------------------------------
# Безпечне створення граней
# ---------------------------------------------------------------------------

def safe_face_add(bm: bmesh.types.BMesh, verts: list, neighbor_normal=None):
    """
    Безпечно створює грань: перевіряє унікальність вершин і орієнтацію.

    Повертає нову BMFace або None якщо:
      - менше 3 унікальних вершин
      - грань вже існує (ValueError)
    """
    if len(set(verts)) < 3:
        return None
    try:
        face = bm.faces.new(verts)
        if neighbor_normal and face.normal.dot(neighbor_normal) < 0:
            face.normal_flip()
        return face
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Виділення елементів
# ---------------------------------------------------------------------------

def select_verts_by_index(
    bm: bmesh.types.BMesh,
    indices: list[int],
    deselect_all: bool = False,
) -> None:
    """Виділяє вершини за індексами. Опційно знімає все попереднє виділення."""
    if deselect_all:
        for v in bm.verts:
            v.select = False
    for idx in indices:
        bm.verts[idx].select = True


def select_faces_by_index(
    bm: bmesh.types.BMesh,
    indices: list[int],
    deselect_all: bool = False,
) -> None:
    """
    Виділяє грані за індексами разом з їхніми вершинами і ребрами
    (потрібно для коректного відображення у вʼюпорті).
    """
    if deselect_all:
        for f in bm.faces:
            f.select = False
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
    for idx in indices:
        face = bm.faces[idx]
        face.select = True
        for v in face.verts:
            v.select = True
        for e in face.edges:
            e.select = True


# ---------------------------------------------------------------------------
# Sharp / Seam — обмеження руху вершин (relax)
# ---------------------------------------------------------------------------

def is_sharp_or_seam(edge) -> bool:
    """True якщо ребро є sharp або seam."""
    return edge.smooth is False or edge.seam


def get_sharp_edges(vert) -> list:
    """Список sharp/seam ребер що виходять з вершини."""
    return [e for e in vert.link_edges if is_sharp_or_seam(e)]


def get_move_constraint(vert):
    """
    Визначає обмеження руху вершини відносно sharp edges / seams.

    Повертає:
      None        — вершина вільна (не на sharp/seam)
      'blocked'   — повністю заблокована:
                      кутова (3+ sharp ребра) або кінець краю (1 sharp ребро)
      Vector      — одиничний вектор вздовж краю:
                      пряма ділянка (рівно 2 sharp ребра)
    """
    sharp_edges = get_sharp_edges(vert)
    n = len(sharp_edges)

    if n == 0:
        return None

    if n == 1 or n >= 3:
        return 'blocked'

    # Рівно 2 sharp ребра — пряма ділянка краю
    v1 = sharp_edges[0].other_vert(vert)
    v2 = sharp_edges[1].other_vert(vert)
    edge_vec = v2.co - v1.co
    length   = edge_vec.length

    if length < 1e-8:
        return 'blocked'

    return edge_vec / length


def calc_vert_normal(vert) -> Vector:
    """
    Усереднена нормаль вершини через прилеглі грані.
    Якщо граней немає — повертає vert.normal як fallback.
    """
    faces = vert.link_faces
    if not faces:
        return vert.normal.copy()

    normal = Vector((0.0, 0.0, 0.0))
    for f in faces:
        normal += f.normal
    normal /= len(faces)

    length = normal.length
    return normal / length if length > 1e-8 else vert.normal.copy()