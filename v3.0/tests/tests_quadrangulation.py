import bpy
import bmesh
import sys
import os

ADDON_DIR = os.path.dirname(__file__)
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

from quadrangulation import QuadrangulationEngine, ScoreWeights, SOLVERS


def _new_mesh(name):
    me = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, me


def _grid_grid(rows, cols):
    h = rows + 1
    w = cols + 1
    verts = {}
    for r in range(h):
        for c in range(w):
            verts[(r, c)] = (c * 1.0, r * 1.0, 0.0)
    return verts, h, w


def _make_mesh(verts_dict, faces_list, name="TestMesh"):
    obj, me = _new_mesh(name)
    bm = bmesh.new()
    verts = {}
    for key, co in verts_dict.items():
        verts[key] = bm.verts.new(co)
    for face_verts in faces_list:
        bm.faces.new([verts[v] for v in face_verts])
    bm.to_mesh(me)
    bm.free()
    return obj, me


def _face_count(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    hist = {}
    for f in bm.faces:
        n = len(f.verts)
        hist[n] = hist.get(n, 0) + 1
    bm.free()
    return hist


def _run_engine(obj, max_loop_length=20, max_branch_offs=2, max_relax=0, max_iterations=500):
    bpy.ops.object.mode_set(mode='OBJECT')
    w = ScoreWeights()
    w.loop_length_weight = 1.0
    w.polygon_bonus_weight = 100.0
    w.adjacent_triangle_penalty_weight = 0.0
    w.quad_perfection_weight = 0.0
    w.hexagon_perfection_weight = 0.0
    engine = QuadrangulationEngine(
        obj, w, max_length=max_loop_length,
        max_branch_offs=max_branch_offs, max_relax=max_relax,
        max_iterations=max_iterations,
    )
    stats = engine.run()
    return stats


def _all_quads(hist):
    return all(n == 4 for n in hist)


def _total_non_quads(hist):
    return sum(c for n, c in hist.items() if n != 4)


def _is_convex(f):
    verts = list(f.verts)
    n = len(verts)
    if n <= 3:
        return True
    normal = f.normal
    sign = None
    for i in range(n):
        vp = verts[(i - 1) % n].co
        vc = verts[i].co
        vn = verts[(i + 1) % n].co
        cross = (vc - vp).cross(vn - vc)
        val = cross.dot(normal)
        if abs(val) < 1e-6:
            continue
        if sign is None:
            sign = val > 0
        elif (val > 0) != sign:
            return False
    return True


# =========================================================================
# Tests
# =========================================================================

_PASSED = 0
_FAILED = 0
_ERRORS = 0


def _log(name):
    print(f"  {name}...", end=" ")
    sys.stdout.flush()


def _ok():
    global _PASSED
    _PASSED += 1
    print("OK")


def _fail(msg):
    global _FAILED
    _FAILED += 1
    print(f"FAIL: {msg}")


def _error(e):
    global _ERRORS
    _ERRORS += 1
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


def _cleanup():
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Test"):
            bpy.data.objects.remove(obj, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.name.startswith("Test"):
            bpy.data.meshes.remove(me)


# -------------------------------------------------------------------------
# G1: Single triangle on boundary edge
#
# 5x5 grid, top row has a triangle at column 2.
# The triangle uses the top edge of cell (0,2) as its boundary base,
# and its two other edges connect to the quads at (0,1) and (0,3).
# -------------------------------------------------------------------------

def test_G1_boundary_triangle():
    _log("G1: Single triangle on boundary edge")
    v, h, w = _grid_grid(5, 6)
    faces = []
    for r in range(5):
        for c in range(6):
            if r == 0 and c == 2:
                # Triangle on the top boundary
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1)])
                # The rest of this cell is absorbed by the boundary
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    obj, me = _make_mesh(v, faces)
    h0 = _face_count(obj)
    stats = _run_engine(obj)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# -------------------------------------------------------------------------
# G2: Triangle at grid corner (0,0)
# -------------------------------------------------------------------------

def test_G2_corner_triangle():
    _log("G2: Triangle at grid corner")
    v, h, w = _grid_grid(5, 6)
    faces = []
    for r in range(5):
        for c in range(6):
            if r == 0 and c == 0:
                # Triangle at top-left corner
                faces.append([(r, c), (r, c + 1), (r + 1, c)])
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    obj, me = _make_mesh(v, faces)
    stats = _run_engine(obj)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# -------------------------------------------------------------------------
# G6: Two triangles aligned with a straight quad strip
# -------------------------------------------------------------------------

def _two_triangles_diamond(rows, cols, pr1, pc1, pr2, pc2):
    v, h, w = _grid_grid(rows, cols)
    tri_cells = {(pr1, pc1), (pr2, pc2)}
    blocked = set()
    for tr, tc in tri_cells:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                r2, c2 = tr + dr, tc + dc
                if 0 <= r2 < rows and 0 <= c2 < cols:
                    blocked.add((r2, c2))
    faces = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) in blocked:
                continue
            faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    for tr, tc in tri_cells:
        a = (tr, tc)
        b = (tr, tc + 1)
        c2 = (tr + 1, tc + 1)
        d = (tr + 1, tc)
        center = (tr + 0.5, tc + 0.5, 0.0)
        v[('center', tr, tc)] = center
        faces.append([a, b, ('center', tr, tc)])
        faces.append([b, c2, ('center', tr, tc)])
        faces.append([c2, d, ('center', tr, tc)])
        faces.append([d, a, ('center', tr, tc)])
    return _make_mesh(v, faces)


def test_G6_two_triangles_straight():
    _log("G6: Two triangles straight")
    obj, me = _two_triangles_diamond(6, 8, 2, 2, 2, 5)
    h0 = _face_count(obj)
    stats = _run_engine(obj)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# -------------------------------------------------------------------------
# G7: Two triangles with L-shaped path (turn required)
# -------------------------------------------------------------------------

def test_G7_two_triangles_L_shape():
    _log("G7: Two triangles L-shape")
    obj, me = _two_triangles_diamond(6, 6, 2, 2, 4, 4)
    h0 = _face_count(obj)
    stats = _run_engine(obj, max_branch_offs=2)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# -------------------------------------------------------------------------
# G9: Triangle near hexagon — must not target the hexagon
# -------------------------------------------------------------------------

def test_G9_triangle_hexagon_not_targeted():
    _log("G9: Triangle near hexagon")
    v, h, w = _grid_grid(6, 6)

    hex_r, hex_c = 3, 3
    hex_verts = [
        (hex_r, hex_c),
        (hex_r, hex_c + 1),
        (hex_r + 1, hex_c + 1),
        (hex_r + 1, hex_c + 2),
        (hex_r + 2, hex_c + 2),
        (hex_r + 2, hex_c + 1),
    ]

    tri_r, tri_c = 1, 3
    skip_cells = {(3, 3), (3, 4), (4, 3), (4, 4), (tri_r, tri_c)}

    faces = []
    for r in range(6):
        for c in range(6):
            if (r, c) in skip_cells:
                continue
            faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])

    faces.append(hex_verts)
    faces.append([(tri_r, tri_c), (tri_r, tri_c + 1), (tri_r + 1, tri_c + 1)])

    obj, me = _make_mesh(v, faces)

    h0 = _face_count(obj)

    stats = _run_engine(obj, max_iterations=100)
    h1 = _face_count(obj)

    if h1.get(7, 0) == 0:
        _ok()
    else:
        _fail(f"7-gon created: {h1}")


# -------------------------------------------------------------------------
# G14: Two adjacent triangles sharing a boundary edge
# -------------------------------------------------------------------------

def test_G14_adjacent_triangles():
    _log("G14: Adjacent triangles on boundary")
    v, h, w = _grid_grid(5, 8)
    faces = []
    for r in range(5):
        for c in range(8):
            if r == 0 and c in (3, 4):
                # Two adjacent boundary cells, each replaced by a triangle
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1)])
            elif r == 0 and c == 5:
                # Skip - the quad would overlap
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    obj, me = _make_mesh(v, faces)
    h0 = _face_count(obj)
    stats = _run_engine(obj)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# -------------------------------------------------------------------------
# G16: max loop length — short limit blocks, 0 resolves
# -------------------------------------------------------------------------

def test_G16_max_loop_length_limit():
    _log("G16: max loop length")
    v, h, w = _grid_grid(10, 10)
    tri_r, tri_c = 0, 5
    faces = []
    for r in range(10):
        for c in range(10):
            if r == 0 and c == tri_c:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1)])
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])

    obj, me = _make_mesh(v, faces)
    stats_lim = _run_engine(obj, max_loop_length=2)
    h1 = _face_count(obj)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(me)

    if _total_non_quads(h1) > 0:
        obj2, me2 = _make_mesh(v, faces)
        stats_unlim = _run_engine(obj2, max_loop_length=0)
        h2 = _face_count(obj2)
        bpy.data.objects.remove(obj2, do_unlink=True)
        bpy.data.meshes.remove(me2)
        if _all_quads(h2):
            _ok()
        else:
            _fail(f"unlimited also failed: {h2}")
    else:
        _ok()


# -------------------------------------------------------------------------
# Branch cut: 1 quad → 3 quads via TopologyApplier.quad_loop
# -------------------------------------------------------------------------

def test_branch_cut_1_to_3():
    _log("Branch cut 1→3 quads")
    from quadrangulation import TopologyApplier
    bm = bmesh.new()
    A = bm.verts.new((0, 0, 0))
    B = bm.verts.new((2, 0, 0))
    C = bm.verts.new((2, 2, 0))
    D = bm.verts.new((0, 2, 0))
    E = bm.verts.new((-2, 0, 0))
    bm.verts.ensure_lookup_table()
    bm.faces.new((A, B, C, D))
    bm.faces.new((E, A, B))
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    eAB = next(e for e in bm.edges if A in e.verts and B in e.verts)
    eBC = next(e for e in bm.edges if B in e.verts and C in e.verts)

    TopologyApplier.quad_loop(bm, [eAB, eBC])

    hist = {}
    for f in bm.faces:
        if f.is_valid:
            n = len(f.verts)
            hist[n] = hist.get(n, 0) + 1

    bm.free()
    if hist.get(4, 0) == 4 and hist.get(3, 0) == 0:
        _ok()
    else:
        _fail(f"expected 4 quads, got {hist}")


def test_branch_cut_1_to_3_AB_DA():
    _log("Branch cut AB→DA 1→3 quads")
    from quadrangulation import TopologyApplier
    bm = bmesh.new()
    A = bm.verts.new((0, 0, 0))
    B = bm.verts.new((2, 0, 0))
    C = bm.verts.new((2, 2, 0))
    D = bm.verts.new((0, 2, 0))
    E = bm.verts.new((0, -2, 0))
    bm.verts.ensure_lookup_table()
    bm.faces.new((A, B, C, D))
    bm.faces.new((E, A, B))
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    eAB = next(e for e in bm.edges if A in e.verts and B in e.verts)
    eDA = next(e for e in bm.edges if D in e.verts and A in e.verts)

    TopologyApplier.quad_loop(bm, [eAB, eDA])

    hist = {}
    for f in bm.faces:
        if f.is_valid:
            n = len(f.verts)
            hist[n] = hist.get(n, 0) + 1

    bm.free()
    if hist.get(4, 0) == 4 and hist.get(3, 0) == 0:
        _ok()
    else:
        _fail(f"expected 4 quads, got {hist}")


# =========================================================================
# Multi-triangle stress test
# -------------------------------------------------------------------------

def test_triangles_10_scattered():
    _log("Extra: 10 scattered triangles")
    v, h, w = _grid_grid(12, 12)
    tri_positions = [
        (1, 1), (1, 4), (1, 7), (1, 10),
        (4, 1), (4, 4), (4, 7), (4, 10),
        (7, 7), (10, 10),
    ]
    tri_set = set(tri_positions)
    faces = []
    for r in range(12):
        for c in range(12):
            if (r, c) in tri_set:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1)])
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    obj, me = _make_mesh(v, faces)
    stats = _run_engine(obj, max_iterations=500)
    h1 = _face_count(obj)
    if _all_quads(h1):
        _ok()
    else:
        _fail(f"remaining {h1} (solved={stats['solved']})")


# =========================================================================
# Convexity check: all final faces must be convex
# -------------------------------------------------------------------------

def test_no_concave_polygons():
    _log("No concave polygons after engine")
    v, h, w = _grid_grid(12, 12)
    tri_positions = [
        (1, 1), (1, 4), (1, 7), (1, 10),
        (4, 1), (4, 4), (4, 7), (4, 10),
        (7, 7), (10, 10),
    ]
    tri_set = set(tri_positions)
    faces = []
    for r in range(12):
        for c in range(12):
            if (r, c) in tri_set:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1)])
            else:
                faces.append([(r, c), (r, c + 1), (r + 1, c + 1), (r + 1, c)])
    obj, me = _make_mesh(v, faces, name="ConcavityTest")
    _run_engine(obj, max_iterations=500)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = []
    for f in bm.faces:
        if not _is_convex(f):
            bad.append(f.index)
    bm.free()
    bpy.data.objects.remove(obj, do_unlink=True)
    if bad:
        _fail(f"{len(bad)} concave face(s): {bad}")
    else:
        _ok()


def test_remaining_stats_match_mesh():
    _log("Report: remaining stats match final mesh")
    coords = [(0, 0), (2, 0), (3, 1.5), (2.5, 3),
              (0.5, 3.5), (-1, 2), (-0.5, 0.5)]
    verts = {i: (x, y, 0.0) for i, (x, y) in enumerate(coords)}
    faces = [[0, 1, 2, 3, 4, 5, 6]]
    obj, me = _make_mesh(verts, faces, name="RemainingStats")
    stats = _run_engine(obj, max_iterations=500)
    actual = {n: c for n, c in _face_count(obj).items() if n != 4}
    if stats['remaining'] == {7: 1} and stats['remaining'] == actual:
        _ok()
    else:
        _fail(f"stats['remaining']={stats['remaining']} != actual {actual}")


# =========================================================================
# Runner
# =========================================================================

TESTS = [
    ("G1", test_G1_boundary_triangle),
    ("G2", test_G2_corner_triangle),
    ("G6", test_G6_two_triangles_straight),
    ("G7", test_G7_two_triangles_L_shape),
    ("G9", test_G9_triangle_hexagon_not_targeted),
    ("G14", test_G14_adjacent_triangles),
    ("G16", test_G16_max_loop_length_limit),
    ("BC1", test_branch_cut_1_to_3),
    ("BC2", test_branch_cut_1_to_3_AB_DA),
    ("X1", test_triangles_10_scattered),
    ("CV1", test_no_concave_polygons),
    ("RV1", test_remaining_stats_match_mesh),
]


def run_tests():
    global _PASSED, _FAILED, _ERRORS
    _PASSED = 0
    _FAILED = 0
    _ERRORS = 0

    for code, func in TESTS:
        _cleanup()
        try:
            func()
        except Exception as e:
            _error(e)
        _cleanup()

    total = _PASSED + _FAILED + _ERRORS
    print(f"\n{'='*40}")
    print(f"Triangle tests: {_PASSED}/{total} passed")
    if _FAILED:
        print(f"FAILURES: {_FAILED}")
    if _ERRORS:
        print(f"ERRORS: {_ERRORS}")
    return _PASSED, _FAILED, _ERRORS


if __name__ == "__main__":
    run_tests()
