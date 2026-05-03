import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy.types import Operator

# ===========================================================================
# Параметри алгоритму
# ===========================================================================
SIMPLE_HOLE_MAX_EDGES    = 4
TUNNEL_THRESHOLD_RATIO   = 0.4   # вузьке місце = менше 40% середнього діаметра
TUNNEL_SEARCH_RANGE      = 4     # ділимо loop на TUNNEL_SEARCH_RANGE частин для пошуку

# ===========================================================================
# Збір boundary loops
# ===========================================================================

def _collect_boundary_loops(bm) -> list[list]:
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


def _collect_selected_loops(bm) -> list[list]:
    all_loops = _collect_boundary_loops(bm)
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


# ===========================================================================
# TUNNEL FILL — допоміжні функції
# ===========================================================================

def _calc_avg_edge_length(verts: list) -> float:
    """Середня довжина ребер boundary loop."""
    n     = len(verts)
    total = 0.0
    for i in range(n):
        total += (verts[(i + 1) % n].co - verts[i].co).length
    return total / n if n > 0 else 0.0


# Поріг кількості вершин після якого використовуємо BVH замість O(n²)
BVH_THRESHOLD = 100


def _find_tunnel_entry(verts: list) -> tuple | None:
    """
    Знаходить вхід у тунель — пару вершин (i, j) з протилежних сторін
    loop де відстань між ними значно менша ніж середній діаметр loop.

    Для малих loops (< BVH_THRESHOLD) — O(n²) прямий перебір.
    Для великих loops (≥ BVH_THRESHOLD) — BVHTree O(log n):
      будуємо дерево з вершин протилежної половини loop і шукаємо
      find_nearest замість повного перебору.
    """
    n = len(verts)

    avg_diameter = sum(
        (verts[i].co - verts[(i + n // 2) % n].co).length
        for i in range(n)
    ) / n

    threshold = avg_diameter * TUNNEL_THRESHOLD_RATIO
    best_dist = float('inf')
    best_pair = None
    positions = [v.co.copy() for v in verts]

    if n < BVH_THRESHOLD:
        # --- Малий loop — класичний O(n²) ---
        for i in range(n):
            range_start = i + n // TUNNEL_SEARCH_RANGE
            range_end   = i + ((TUNNEL_SEARCH_RANGE - 1) * n) // TUNNEL_SEARCH_RANGE

            for k in range(range_start, range_end + 1):
                j    = k % n
                dist = (positions[i] - positions[j]).length
                if dist < threshold and dist < best_dist:
                    best_dist = dist
                    best_pair = (i, j)

    else:
        # --- Великий loop — BVHTree O(log n) ---
        for i in range(n):
            range_start = i + n // TUNNEL_SEARCH_RANGE
            range_end   = i + ((TUNNEL_SEARCH_RANGE - 1) * n) // TUNNEL_SEARCH_RANGE

            candidates = [(k % n, positions[k % n]) for k in range(range_start, range_end + 1)]
            if not candidates:
                continue

            # BVH з вироджених трикутників (точка = tri з нульовою площею)
            bvh_verts = [co for _, co in candidates]
            bvh_polys = [(k, k, k) for k in range(len(candidates))]

            try:
                tree = BVHTree.FromPolygons(bvh_verts, bvh_polys)
                loc, _, idx, dist = tree.find_nearest(positions[i])

                if loc is not None and dist < threshold and dist < best_dist:
                    best_dist = dist
                    best_pair = (i, candidates[idx][0])
            except Exception:
                # Fallback на прямий перебір
                for j, co in candidates:
                    dist = (positions[i] - co).length
                    if dist < threshold and dist < best_dist:
                        best_dist = dist
                        best_pair = (i, j)

    return best_pair


def _fill_tunnel(bm, verts: list, entry: tuple) -> list[list]:
    """
    Заповнює тунельну частину loop quad-гранями.
    Рухається від пари (i,j) одночасно в обидва боки.

    Повертає список залишкових loops після заповнення тунелю.
    Тунель розбиває оригінальний loop на два залишки:
      - Залишок A: вершини від next_left до next_right (права сторона)
      - Залишок B: вершини від next_right до next_left (ліва сторона)
    Кожен залишок — окремий список вершин для подальшої обробки.
    Якщо тунель повністю закрив отвір — повертає порожній список.
    """
    n = len(verts)

    neighbor_normal = None
    for v in verts:
        for f in v.link_faces:
            neighbor_normal = f.normal.copy()
            break
        if neighbor_normal:
            break

    i, j      = entry
    left_idx  = i
    right_idx = j

    for step in range(n):
        next_left  = (left_idx  + 1) % n
        next_right = (right_idx - 1) % n

        closing = (
            next_left  == right_idx or
            next_right == left_idx  or
            next_left  == next_right
        )

        v0 = verts[left_idx]
        v1 = verts[next_left]
        v2 = verts[next_right]
        v3 = verts[right_idx]

        unique_count = len({left_idx, next_left, next_right, right_idx})

        if unique_count == 4:
            _safe_face_add(bm, [v0, v1, v2, v3], neighbor_normal)
        elif unique_count == 3:
            unique = list(dict.fromkeys([left_idx, next_left, next_right, right_idx]))
            _safe_face_add(bm, [verts[unique[0]], verts[unique[1]], verts[unique[2]]], neighbor_normal)
            return []  # тунель повністю закрив отвір

        if closing:
            return []  # тунель повністю закрив отвір

        left_idx  = next_left
        right_idx = next_right

    # --- Тунель зупинився — збираємо два залишки ---
    # Залишок A: від next_left до next_right йдучи вправо по loop
    remainder_a = []
    idx = left_idx
    while idx != right_idx:
        remainder_a.append(verts[idx])
        idx = (idx + 1) % n
        if len(remainder_a) > n:
            break
    remainder_a.append(verts[right_idx])

    # Залишок B: від next_right до next_left йдучи вправо по loop
    remainder_b = []
    idx = right_idx
    while idx != left_idx:
        remainder_b.append(verts[idx])
        idx = (idx + 1) % n
        if len(remainder_b) > n:
            break
    remainder_b.append(verts[left_idx])

    # Фільтруємо залишки — мінімум 3 вершини щоб мало сенс заповнювати
    result = []
    if len(remainder_a) >= 3:
        result.append(remainder_a)
    if len(remainder_b) >= 3:
        result.append(remainder_b)
    return result


# ===========================================================================
# ADVANCING FRONT — поетапне заповнення до центроїда
# ===========================================================================

def _ensure_even_verts(bm, verts: list) -> list:
    """
    Якщо кількість вершин непарна — розбиває найдовше NON-BOUNDARY ребро.
    Це дає парну кількість вершин і гарантує чисті quads.

    Boundary ребра не розбиваємо — bisect_edges на boundary edge
    створює нову вершину яка стає частиною нового boundary loop
    і порушує логіку збору loops при наступному виклику.
    """
    if len(verts) % 2 == 0:
        return verts

    n        = len(verts)
    max_dist = -1.0
    v_pair   = (None, None)

    for i in range(n):
        v1, v2 = verts[i], verts[(i + 1) % n]
        edge   = bm.edges.get((v1, v2))

        # Пропускаємо boundary ребра
        if edge is None or edge.is_boundary:
            continue

        dist = (v1.co - v2.co).length
        if dist > max_dist:
            max_dist = dist
            v_pair   = (v1, v2)

    # Якщо всі ребра boundary — повертаємо без змін
    if v_pair[0] is None:
        return verts

    edge = bm.edges.get((v_pair[0], v_pair[1]))
    if edge:
        res   = bmesh.ops.bisect_edges(bm, edges=[edge], cuts=1)
        new_v = [g for g in res["geom_split"] if isinstance(g, bmesh.types.BMVert)][0]
        idx   = verts.index(v_pair[1])
        verts.insert(idx, new_v)

    return verts


def _calc_centroid(verts: list) -> Vector:
    """Центроїд списку вершин."""
    co = Vector((0.0, 0.0, 0.0))
    for v in verts:
        co += v.co
    return co / len(verts)


def _centroid_is_inside(verts: list, centroid: Vector) -> bool:
    """
    Перевіряє чи центроїд знаходиться всередині boundary loop.

    Використовує 2D ray casting в площині loop:
    проєктуємо всі вершини і центроїд на площину XY нормалі loop,
    потім рахуємо перетини горизонтального променя з ребрами.
    Непарна кількість перетинів = точка всередині полігона.

    Якщо центроїд поза loop — _fill_to_centroid створить
    перевернуті або пересічені грані.
    """
    n = len(verts)
    if n < 3:
        return False

    # Нормаль площини loop — середня нормаль прилеглих граней
    normal = Vector((0.0, 0.0, 0.0))
    for v in verts:
        for f in v.link_faces:
            normal += f.normal
    if normal.length_squared < 1e-8:
        return True  # не можемо визначити — припускаємо що всередині
    normal = normal.normalized()

    # Базис площини: два перпендикулярних вектори
    ref = Vector((1.0, 0.0, 0.0))
    if abs(normal.dot(ref)) > 0.9:
        ref = Vector((0.0, 1.0, 0.0))
    axis_x = normal.cross(ref).normalized()
    axis_y = normal.cross(axis_x).normalized()

    # Проєкція вершин на площину
    def project(co):
        delta = co - verts[0].co
        return (delta.dot(axis_x), delta.dot(axis_y))

    pts  = [project(v.co) for v in verts]
    cx, cy = project(centroid)

    # Ray casting — горизонтальний промінь вправо від центроїда
    inside = False
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > cy) != (y2 > cy)):
            x_intersect = x1 + (cy - y1) * (x2 - x1) / (y2 - y1)
            if cx < x_intersect:
                inside = not inside

    return inside


def _calc_ring_count(verts: list, centroid: Vector) -> int:
    """
    Кількість концентричних кілець = середній радіус / середня довжина ребра.
    Дає приблизно квадратні грані — висота ≈ ширині.
    Мінімум 1 кільце.
    """
    n          = len(verts)
    avg_radius = sum((v.co - centroid).length for v in verts) / n
    avg_edge   = _calc_avg_edge_length(verts)

    if avg_edge < 1e-8:
        return 1

    return max(1, round(avg_radius / avg_edge))


def _fill_to_centroid(bm, verts: list) -> None:
    """
    Поетапне заповнення отвору від периметра до центроїда.

    Алгоритм:
      1. Трикутник (3 вершини) — закриваємо одразу без центроїда
      2. Рахуємо центроїд і кількість кілець
      3. На кожній ітерації будуємо нове внутрішнє кільце вершин
         через lerp між поточним периметром і центроїдом
      4. Між старим і новим кільцем будуємо quad-грані
      5. Нове кільце стає поточним периметром
      6. Коли залишається останнє кільце — закриваємо центральний отвір
    """
    n = len(verts)
    if n < 3:
        return

    # Трикутник — закриваємо одразу, центроїд не потрібен
    if n == 3:
        neighbor_normal = None
        for v in verts:
            for f in v.link_faces:
                neighbor_normal = f.normal.copy()
                break
            if neighbor_normal:
                break
        _safe_face_add(bm, verts, neighbor_normal)
        return

    # Знаходимо нормаль для орієнтації граней
    neighbor_normal = None
    for v in verts:
        for f in v.link_faces:
            neighbor_normal = f.normal.copy()
            break
        if neighbor_normal:
            break

    centroid = _calc_centroid(verts)

    # Перевіряємо чи центроїд всередині loop
    # Якщо ні — S-подібний або увігнутий отвір, просто закриваємо одною гранню
    if not _centroid_is_inside(verts, centroid):
        neighbor_normal = None
        for v in verts:
            for f in v.link_faces:
                neighbor_normal = f.normal.copy()
                break
            if neighbor_normal:
                break
        _safe_face_add(bm, verts, neighbor_normal)
        return

    ring_count = _calc_ring_count(verts, centroid)

    current_ring = list(verts)  # поточний периметр — починаємо з boundary loop

    for ring_idx in range(1, ring_count + 1):

        # Відносна позиція нового кільця між периметром і центром
        t = ring_idx / ring_count  # 0.0 = периметр, 1.0 = центр

        ring_n = len(current_ring)

        if ring_idx == ring_count:
            # --- Останнє кільце — закриваємо центральний отвір ---
            if ring_n % 2 == 0:
                # Парна кількість — закриваємо quad-гранями попарно
                # Кожен quad обʼєднує дві сусідні пари вершин
                center_v = bm.verts.new(centroid)
                bm.verts.ensure_lookup_table()
                for i in range(0, ring_n, 2):
                    v0 = current_ring[i]
                    v1 = current_ring[(i + 1) % ring_n]
                    v2 = current_ring[(i + 2) % ring_n]
                    _safe_face_add(bm, [v0, v1, v2, center_v], neighbor_normal)
            else:
                # Непарна — один трикутник неминучий, решта quads
                center_v = bm.verts.new(centroid)
                bm.verts.ensure_lookup_table()
                # Перший — трикутник
                _safe_face_add(bm, [current_ring[0], current_ring[1], center_v], neighbor_normal)
                # Решта — quads
                for i in range(1, ring_n - 1, 2):
                    v0 = current_ring[i]
                    v1 = current_ring[(i + 1) % ring_n]
                    v2 = current_ring[(i + 2) % ring_n]
                    _safe_face_add(bm, [v0, v1, v2, center_v], neighbor_normal)
            return

        # --- Будуємо нове кільце вершин через lerp ---
        new_ring = []
        for i in range(ring_n):
            new_co = current_ring[i].co.lerp(centroid, t)
            new_v  = bm.verts.new(new_co)
            new_ring.append(new_v)

        # ensure_lookup_table після додавання нових вершин — обовʼязково
        bm.verts.ensure_lookup_table()

        # --- Будуємо quad-грані між поточним і новим кільцем ---
        for i in range(ring_n):
            v0 = current_ring[i]
            v1 = current_ring[(i + 1) % ring_n]
            v2 = new_ring[(i + 1) % ring_n]
            v3 = new_ring[i]

            # Перевіряємо що всі вершини різні
            if len({v0, v1, v2, v3}) < 4:
                continue

            _safe_face_add(bm, [v0, v1, v2, v3], neighbor_normal)

        # Легке згладжування нових вершин для рівномірного розподілу
        bmesh.ops.smooth_vert(
            bm,
            verts=new_ring,
            factor=0.5,
            mirror_clip_x=False,
            mirror_clip_y=False,
            mirror_clip_z=False,
            clip_dist=0.0,
            use_axis_x=True,
            use_axis_y=True,
            use_axis_z=True,
        )

        # Нове кільце стає поточним периметром
        current_ring = new_ring


# ===========================================================================
# Головна логіка заповнення
# ===========================================================================

def _safe_face_add(bm, verts: list, neighbor_normal=None):
    """
    Безпечно створює грань з перевіркою унікальності вершин і орієнтації.
    Централізована заміна розкиданих try/except по всьому коду.
    Повертає нову грань або None якщо створення неможливе.
    """
    if len(set(verts)) < 3:
        return None
    try:
        face = bm.faces.new(verts)
        if neighbor_normal and face.normal.dot(neighbor_normal) < 0:
            face.normal_flip()
        return face
    except ValueError:
        # Грань вже існує
        return None


def _select_loop_edges(bm, verts: list) -> None:
    """Виділяє ребра петлі."""
    for e in bm.edges:
        e.select = False
    n = len(verts)
    for i in range(n):
        v1, v2 = verts[i], verts[(i + 1) % n]
        edge   = bm.edges.get((v1, v2))
        if edge:
            edge.select = True


def _fill_loop(obj, bm, verts: list, depth: int = 0, stats: dict = None) -> bool:
    """
    Рекурсивне заповнення одного loop.

    Ієрархія:
      1. Прості отвори (≤ SIMPLE_HOLE_MAX_EDGES) → bm.faces.new
      2. Є тунельне місце → _fill_tunnel → рекурсія на кожен залишок
      3. Тунелів немає → _ensure_even_verts + _fill_to_centroid

    depth — глибина рекурсії, захист від нескінченного циклу (макс 20).
    stats — словник для збору статистики стратегій заповнення.
    """
    if depth > 20:
        return False

    n = len(verts)
    if n < 3:
        return True

    if stats is None:
        stats = {}

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # --- 1. ПРОСТІ ОТВОРИ ---
    if n <= SIMPLE_HOLE_MAX_EDGES:
        neighbor_normal = None
        for v in verts:
            for f in v.link_faces:
                neighbor_normal = f.normal.copy()
                break
            if neighbor_normal:
                break
        face = _safe_face_add(bm, verts, neighbor_normal)
        if face:
            stats['simple'] = stats.get('simple', 0) + 1
            return True

    # --- 2. ТУНЕЛЬНІ СТРУКТУРИ (рекурсивно) ---
    entry = _find_tunnel_entry(verts)

    if entry is not None:
        remainders = _fill_tunnel(bm, verts, entry)
        stats['tunnel'] = stats.get('tunnel', 0) + 1

        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        for remainder in remainders:
            _fill_loop(obj, bm, remainder, depth + 1, stats)

        return True

    # --- 3. ADVANCING FRONT ДО ЦЕНТРОЇДА ---
    verts = _ensure_even_verts(bm, verts)

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    _fill_to_centroid(bm, verts)
    stats['advancing_front'] = stats.get('advancing_front', 0) + 1
    return True


# ===========================================================================
# Оператори
# ===========================================================================

class RETOPO_OT_find_holes(Operator):
    bl_idname  = "retopo.find_holes"
    bl_label   = "Find Holes"
    bl_description = (
        "Знаходить усі замкнені отвори у сітці та виділяє їх ребра. "
        "Після виконання можна вручну відкоригувати виділення "
        "і натиснути Fill Selected для заповнення"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.active_object

        # Явно перемикаємо в Edge Select Mode незалежно від поточного режиму
        if context.tool_settings.mesh_select_mode != (False, True, False):
            context.tool_settings.mesh_select_mode = (False, True, False)

        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        # Знімаємо все виділення перед пошуком
        for e in bm.edges:
            e.select = False
        for v in bm.verts:
            v.select = False

        loops = _collect_boundary_loops(bm)
        if not loops:
            self.report({"INFO"}, "No closed holes found.")
            return {"CANCELLED"}

        for verts in loops:
            for i in range(len(verts)):
                v1, v2 = verts[i], verts[(i + 1) % len(verts)]
                v1.select = True
                v2.select = True
                edge = bm.edges.get((v1, v2))
                if edge:
                    edge.select = True

        bmesh.update_edit_mesh(obj.data)
        self.report(
            {"INFO"},
            f"Found {len(loops)} closed hole(s). "
            "Adjust selection if needed, then press Fill Selected.",
        )
        return {"FINISHED"}


class RETOPO_OT_fill_selected(Operator):
    bl_idname  = "retopo.fill_selected"
    bl_label   = "Fill Selected"
    bl_description = (
        "Заповнює виділені отвори з пріоритетом quad-полігонів. "
        "Використовує три стратегії залежно від форми отвору: "
        "простий отвір (3-4 ребра) — одна грань; "
        "тунельний отвір — quad-стрічка вздовж звуження; "
        "складний отвір — концентричні кільця до центроїда"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        # Підтримка всіх виділених mesh-обʼєктів в Edit Mode
        # context.objects_in_mode дає всі обʼєкти що зараз в Edit Mode
        objects = [
            obj for obj in context.objects_in_mode
            if obj.type == "MESH"
        ]

        if not objects:
            self.report({"WARNING"}, "No mesh objects in Edit Mode.")
            return {"CANCELLED"}

        all_filled  = 0
        all_total   = 0
        all_skipped = 0
        all_stats   = {"simple": 0, "tunnel": 0, "advancing_front": 0}

        for obj in objects:
            bm = bmesh.from_edit_mesh(obj.data)

            # Очищення кастомних нормалей щоб уникнути чорних граней
            if obj.data.has_custom_normals:
                bpy.ops.mesh.customdata_custom_split_normals_clear()

            loops = _collect_selected_loops(bm)
            if not loops:
                continue

            all_total += len(loops)

            for verts in loops:
                loop_stats = {}
                success = _fill_loop(obj, bm, verts, stats=loop_stats)
                if success:
                    all_filled += 1
                    for key, val in loop_stats.items():
                        all_stats[key] = all_stats.get(key, 0) + val
                else:
                    all_skipped += 1

            # Перераховуємо нормалі і оновлюємо меш для кожного обʼєкта
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.select_flush(False)
            bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
            obj.data.update()

        if all_total == 0:
            self.report({"WARNING"}, "No holes selected. Run Find Holes first.")
            return {"CANCELLED"}

        # Примусово оновлюємо вʼюпорт
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        level = "WARNING" if all_skipped > 0 else "INFO"

        strategy_parts = []
        if all_stats.get("simple",          0): strategy_parts.append(f"simple×{all_stats['simple']}")
        if all_stats.get("tunnel",          0): strategy_parts.append(f"tunnel×{all_stats['tunnel']}")
        if all_stats.get("advancing_front", 0): strategy_parts.append(f"front×{all_stats['advancing_front']}")

        strategy_str = " + ".join(strategy_parts) if strategy_parts else "none"
        msg = f"Filled {all_filled}/{all_total} hole(s) [{strategy_str}]."
        if all_skipped > 0:
            msg += f" {all_skipped} could not be filled."

        self.report({level}, msg)
        return {"FINISHED"}


# ===========================================================================
# Реєстрація
# ===========================================================================

classes = (RETOPO_OT_find_holes, RETOPO_OT_fill_selected)


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


if __name__ == "__main__":
    register()