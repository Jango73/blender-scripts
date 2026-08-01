# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Quadrangulation",
    "author": "Jango73",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "description": "Convert every non-quad face of a mesh into quads",
    "category": "Mesh",
}

import bpy
import bmesh
import math
import random
import heapq
from mathutils import Vector

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

POLYGON_REACHED_BONUS = 100.0
# Bonus (in loop-length units) for a loop that terminates by reaching another
# polygon or the mesh boundary. Kept small so loop length stays meaningful:
# previously POLYGON_REACHED_BONUS × polygon_bonus_weight (5000) vs a loop
# cost of 1/edge made long loops look as good as short ones.
LOOP_TERMINATION_BONUS = 10.0
# A tri_quad_merge is scored like a loop of this many edges: it resolves one
# triangle locally but consumes (destroys) one neighbor quad. Giving it a cost
# above a typical short loop keeps merges as a fallback instead of letting them
# out-rank short loops, which would eat up quads other triangles need.
MERGE_LOOP_LENGTH = 3.0
CENTER_LAYER_NAME = "center_count"

# Default weight values
DEFAULT_LOOP_LENGTH_WEIGHT = 1.0
DEFAULT_POLYGON_BONUS_WEIGHT = 50.0
DEFAULT_ADJACENT_TRIANGLE_PENALTY_WEIGHT = 20.0
DEFAULT_BRANCH_PENALTY_WEIGHT = 0.0
DEFAULT_SHORT_EDGE_PENALTY_WEIGHT = 5.0
DEFAULT_CENTER_SUBS_PENALTY_WEIGHT = 5.0
DEFAULT_AREA_PENALTY_WEIGHT = 50.0
# Per-original-quad penalty applied when an operation destroys an original
# input quad (e.g. tri_quad_merge consuming a neighbor quad). Linear, not a
# veto: the solver may still destroy original quads when it is worthwhile.
# Kept well below the per-non-quad cost (POLYGON_REACHED_BONUS ×
# polygon_bonus_weight = 5000) so quadrangulation stays the top priority.
DEFAULT_ORIGINAL_QUAD_PENALTY_WEIGHT = 1000.0
DEFAULT_QUAD_PERFECTION_WEIGHT = 20.0
DEFAULT_HEXAGON_PERFECTION_WEIGHT = 0.5

# UI master sliders: each multiplies its family of weights (1.0 = defaults)
DEFAULT_TOPOLOGY_STRENGTH = 0.5
DEFAULT_SHAPE_STRENGTH = 0.5

# Default limit/relax values
DEFAULT_MAX_LOOP_LENGTH = 20
DEFAULT_MAX_BRANCH_OFFS = 2
DEFAULT_MAX_RELAX_ITERATIONS = 10
DEFAULT_RELAX_MAX_EDGE_COUNT = 5
DEFAULT_RELAX_COLLINEAR_ANGLE = 175.0
DEFAULT_RELAX_PUSH_FACTOR = 0.15
DEFAULT_RELAX_REFLEX_LERP = 0.5
DEFAULT_MIN_AREA = 0.00005
DEFAULT_SEED = 0

# -----------------------------------------------------------------------------
# SolutionCandidate
# -----------------------------------------------------------------------------

class SolutionCandidate:
    __slots__ = ('operations', 'score', 'sub_scores')

    def __init__(self, operations, score=0.0, sub_scores=None):
        self.operations = operations
        self.score = score
        self.sub_scores = sub_scores or {}

# -----------------------------------------------------------------------------
# Mesh Utilities
# -----------------------------------------------------------------------------

class MeshUtils:
    @staticmethod
    def centroid(verts):
        c = Vector((0, 0, 0))
        for v in verts:
            c += v.co
        return c / len(verts) if verts else Vector((0, 0, 0))

    @staticmethod
    def angle90_deviation(face):
        normal = face.normal
        deviation = 0.0
        for loop in face.loops:
            v = loop.vert.co
            prev = loop.link_loop_prev.vert.co
            nxt = loop.link_loop_next.vert.co
            d1 = (prev - v)
            d2 = (nxt - v)
            l1 = d1.length
            l2 = d2.length
            if l1 < MeshUtils.EPSILON_LENGTH or l2 < MeshUtils.EPSILON_LENGTH:
                continue
            dot = max(-1.0, min(1.0, d1.dot(d2) / (l1 * l2)))
            angle = math.degrees(math.acos(dot))
            if d1.cross(d2).dot(normal) > MeshUtils.EPSILON_NORMAL:
                angle = 360.0 - angle
            deviation += abs(angle - 90)
        return deviation

    @staticmethod
    def quad_dev_coords(coords):
        n = len(coords)
        if n < 4:
            return 0.0
        nrm = (coords[1] - coords[0]).cross(coords[2] - coords[1])
        if nrm.length < MeshUtils.EPSILON_NORMAL:
            return float('inf')
        nrm.normalize()
        dev = 0.0
        for i in range(n):
            v = coords[i]
            prev = coords[(i - 1) % n]
            nxt = coords[(i + 1) % n]
            d1 = (prev - v)
            d2 = (nxt - v)
            l1 = d1.length
            l2 = d2.length
            if l1 < MeshUtils.EPSILON_LENGTH or l2 < MeshUtils.EPSILON_LENGTH:
                continue
            dot = max(-1.0, min(1.0, d1.dot(d2) / (l1 * l2)))
            angle = math.degrees(math.acos(dot))
            if d1.cross(d2).dot(nrm) > MeshUtils.EPSILON_NORMAL:
                angle = 360.0 - angle
            dev += abs(angle - 90)
        return dev

    @staticmethod
    def is_convex(face):
        verts = list(face.verts)
        n = len(verts)
        if n < 3:
            return True
        normal = face.normal
        for i in range(n):
            v0 = verts[i].co
            v1 = verts[(i + 1) % n].co
            v2 = verts[(i + 2) % n].co
            cross = (v1 - v0).cross(v2 - v1)
            if cross.dot(normal) < -MeshUtils.EPSILON_NORMAL:
                return False
        return True

    @staticmethod
    def _quad_convex_at(quad, v, co):
        verts = list(quad.verts)
        n = len(verts)
        if n != 4:
            return True
        coords = [co if vt == v else vt.co for vt in verts]
        nrm = (coords[1] - coords[0]).cross(coords[2] - coords[1])
        if nrm.length_squared < 1e-12:
            return False
        for i in range(n):
            v0 = coords[i]
            v1 = coords[(i + 1) % n]
            v2 = coords[(i + 2) % n]
            cross = (v1 - v0).cross(v2 - v1)
            if cross.dot(nrm) < -MeshUtils.EPSILON_NORMAL:
                return False
        return True

    @staticmethod
    def is_convex_robust(face):
        verts = list(face.verts)
        n = len(verts)
        if n < 3:
            return True
        coords = [v.co for v in verts]
        nrm = (coords[1] - coords[0]).cross(coords[2] - coords[1])
        if nrm.length_squared < 1e-12:
            return False
        for i in range(n):
            v0 = coords[i]
            v1 = coords[(i + 1) % n]
            v2 = coords[(i + 2) % n]
            cross = (v1 - v0).cross(v2 - v1)
            if cross.dot(nrm) < -MeshUtils.EPSILON_NORMAL:
                return False
        return True

    @staticmethod
    def _move_would_create_concave(v, new_co):
        for nf in v.link_faces:
            if not nf.is_valid or len(nf.verts) != 4:
                continue
            before = MeshUtils._quad_convex_at(nf, v, v.co)
            after = MeshUtils._quad_convex_at(nf, v, new_co)
            if before and not after:
                return True
        return False

    EPSILON_LENGTH = 1e-10
    EPSILON_NORMAL = 1e-6

    @staticmethod
    def relax_faces(bm, faces, max_iter=10,
                    collinear_angle=175, push_factor=0.15,
                    reflex_lerp=0.5, max_edge_count=5):
        valid = [f for f in faces
                 if hasattr(f, 'verts') and f.is_valid and len(f.verts) >= 3]
        valid_set = set(valid)

        guard_verts = set()
        for f in valid:
            for v in f.verts:
                guard_verts.add(v)
            for e in f.edges:
                for nf in e.link_faces:
                    if nf.is_valid and nf not in valid_set:
                        for v in nf.verts:
                            guard_verts.add(v)
        saved = {v: v.co.copy() for v in guard_verts}

        edge_count_cache = {}

        def _edge_count(v):
            idx = v.index
            if idx not in edge_count_cache:
                edge_count_cache[idx] = len(v.link_edges)
            return edge_count_cache[idx]

        for _ in range(max_iter):
            done = True
            for f in valid:
                for loop in f.loops:
                    v = loop.vert
                    if max_edge_count > 0 and _edge_count(v) > max_edge_count:
                        continue
                    p = loop.link_loop_prev.vert.co
                    c = v.co
                    n_x = loop.link_loop_next.vert.co

                    d1 = (p - c)
                    d2 = (n_x - c)
                    l1 = d1.length
                    l2 = d2.length
                    if l1 < MeshUtils.EPSILON_LENGTH or l2 < MeshUtils.EPSILON_LENGTH:
                        continue

                    d1 /= l1
                    d2 /= l2
                    dot = max(-1.0, min(1.0, d1.dot(d2)))
                    angle = math.acos(dot)

                    if angle > math.radians(collinear_angle):
                        edge_dir = (n_x - p).normalized()
                        perp = edge_dir.cross(f.normal).normalized()
                        push = min(l1, l2) * push_factor
                        new_co = v.co + perp * push
                        if MeshUtils._move_would_create_concave(v, new_co):
                            continue
                        v.co = new_co
                        done = False
                        continue

                    cross = d1.cross(d2)
                    if cross.dot(f.normal) > 0:
                        verts = list(f.verts)
                        n = len(verts)
                        centroid = sum((vt.co for vt in verts), Vector()) / n
                        new_co = v.co.lerp(centroid, reflex_lerp)
                        if MeshUtils._move_would_create_concave(v, new_co):
                            continue
                        v.co = new_co
                        done = False
            if done:
                break

        # Undo any relaxation that left a quad concave. Individual moves are
        # guarded, but moves can accumulate; without this the end-of-pass
        # fix would triangulate engine-created quads into unsolvable tris.
        if saved:
            moved = [v for v in saved if (v.co - saved[v]).length > 1e-12]
            bad = set()
            for v in moved:
                for nf in v.link_faces:
                    if (nf.is_valid and len(nf.verts) == 4
                            and not MeshUtils.is_convex(nf)):
                        bad.add(nf)
            for f in bad:
                for v in f.verts:
                    if v in saved:
                        v.co = saved[v]
        bm.verts.index_update()

    @staticmethod
    def fix_concave_quads(bm, max_straighten=3, straighten_lerp=0.5):
        """Guarantee zero concave quads in the mesh.

        Reflex vertices are first pulled toward their quad centroid; any quad
        that is still concave afterwards is triangulated, which always yields
        convex faces.
        """
        for _ in range(max_straighten):
            fixed = False
            for f in list(bm.faces):
                if not f.is_valid or len(f.verts) != 4:
                    continue
                if MeshUtils.is_convex(f):
                    continue
                reflex = None
                for loop in f.loops:
                    d1 = loop.link_loop_prev.vert.co - loop.vert.co
                    d2 = loop.link_loop_next.vert.co - loop.vert.co
                    if d1.cross(d2).dot(f.normal) > MeshUtils.EPSILON_NORMAL:
                        reflex = loop.vert
                        break
                if reflex is None:
                    continue
                centroid = sum((v.co for v in f.verts), Vector()) / 4
                reflex.co = reflex.co.lerp(centroid, straighten_lerp)
                fixed = True
            if not fixed:
                break
        for f in list(bm.faces):
            if f.is_valid and len(f.verts) == 4 and not MeshUtils.is_convex(f):
                bmesh.ops.triangulate(bm, faces=[f], quad_method='SHORT_EDGE',
                                      ngon_method='BEAUTY')
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()

# -----------------------------------------------------------------------------
# Weights
# -----------------------------------------------------------------------------

class ScoreWeights:
    __slots__ = (
        'loop_length_weight', 'polygon_bonus_weight',
        'adjacent_triangle_penalty_weight', 'quad_perfection_weight',
        'hexagon_perfection_weight',
        'branch_penalty_weight',
        'short_edge_penalty_weight', 'center_subs_penalty_weight',
        'area_penalty_weight', 'original_quad_penalty_weight',
    )

    TOPOLOGY_WEIGHTS = (
        'loop_length_weight', 'polygon_bonus_weight',
        'adjacent_triangle_penalty_weight', 'branch_penalty_weight',
        'center_subs_penalty_weight', 'original_quad_penalty_weight',
    )
    SHAPE_WEIGHTS = (
        'quad_perfection_weight', 'hexagon_perfection_weight',
        'short_edge_penalty_weight',
        'area_penalty_weight',
    )

    def __init__(self, props=None):
        defaults = {
            'loop_length_weight': DEFAULT_LOOP_LENGTH_WEIGHT,
            'polygon_bonus_weight': DEFAULT_POLYGON_BONUS_WEIGHT,
            'adjacent_triangle_penalty_weight': DEFAULT_ADJACENT_TRIANGLE_PENALTY_WEIGHT,
            'branch_penalty_weight': DEFAULT_BRANCH_PENALTY_WEIGHT,
            'short_edge_penalty_weight': DEFAULT_SHORT_EDGE_PENALTY_WEIGHT,
            'center_subs_penalty_weight': DEFAULT_CENTER_SUBS_PENALTY_WEIGHT,
            'area_penalty_weight': DEFAULT_AREA_PENALTY_WEIGHT,
            'original_quad_penalty_weight': DEFAULT_ORIGINAL_QUAD_PENALTY_WEIGHT,
            'quad_perfection_weight': DEFAULT_QUAD_PERFECTION_WEIGHT,
            'hexagon_perfection_weight': DEFAULT_HEXAGON_PERFECTION_WEIGHT,
        }
        if props is None:
            topo = DEFAULT_TOPOLOGY_STRENGTH
            shape = DEFAULT_SHAPE_STRENGTH
        else:
            topo = getattr(props, 'topology_strength', DEFAULT_TOPOLOGY_STRENGTH)
            shape = getattr(props, 'shape_strength', DEFAULT_SHAPE_STRENGTH)
        topo_factor = topo / DEFAULT_TOPOLOGY_STRENGTH
        shape_factor = shape / DEFAULT_SHAPE_STRENGTH
        for k, v in defaults.items():
            if k in ScoreWeights.TOPOLOGY_WEIGHTS:
                factor = topo_factor
            elif k in ScoreWeights.SHAPE_WEIGHTS:
                factor = shape_factor
            else:
                factor = 1.0
            setattr(self, k, v * factor)

# -----------------------------------------------------------------------------
# Quad Loop — Best-First Search
# -----------------------------------------------------------------------------

class _SearchNode:
    __slots__ = ('edge', 'quad_face', 'path_edges', 'length',
                 'branch_offs', 'visited', 'partial_score',
                 'quad_dev_sum', 'short_edge_sum',
                 'adj_tri_penalty', 'origin_tri')

    def __init__(self, edge, quad_face, path_edges, length,
                 branch_offs, visited, partial_score,
                 quad_dev_sum=0.0, short_edge_sum=0.0,
                 adj_tri_penalty=0.0, origin_tri=None):
        self.edge = edge
        self.quad_face = quad_face
        self.path_edges = path_edges
        self.length = length
        self.branch_offs = branch_offs
        self.visited = visited
        self.partial_score = partial_score
        self.quad_dev_sum = quad_dev_sum
        self.short_edge_sum = short_edge_sum
        self.adj_tri_penalty = adj_tri_penalty
        self.origin_tri = origin_tri


class QuadLoopSearch:
    def __init__(self, bm, weights, max_length=20, max_branch_offs=2):
        self.bm = bm
        self.w = weights
        self.max_length = max_length
        self.max_branch_offs = max_branch_offs
        self._heap_counter = 0

    @staticmethod
    def edge_is_valid(edge, for_traversal=False):
        if len(edge.link_faces) > 2:
            return False
        for f in edge.link_faces:
            n = len(f.verts)
            if n not in SOLVERS and n != 4:
                return False
            if for_traversal and n != 4 and n + 1 != 4 and (n + 1) not in SOLVERS:
                return False
        return True

    def _short_edge_penalty(self, edge, face):
        if self.w.short_edge_penalty_weight <= 0.0:
            return 0.0
        max_len = max(e.calc_length() for e in face.edges)
        if max_len <= 0:
            return 0.0
        ratio = edge.calc_length() / max_len
        return self.w.short_edge_penalty_weight * (1.0 - ratio)

    @staticmethod
    def _other_face(edge, face):
        for f in edge.link_faces:
            if f != face:
                return f
        return None

    @staticmethod
    def _find_loop(edge, face):
        for loop in edge.link_loops:
            if loop.face == face:
                return loop
        return None

    @staticmethod
    def _opposite_loop(loop):
        return loop.link_loop_next.link_loop_next

    @staticmethod
    def _adjacent_loops(loop):
        return [loop.link_loop_next, loop.link_loop_prev]

    def _make_leaf(self, edge, path, length, penalty,
                   quad_dev_sum, short_edge_sum):
        term_score = (-self.w.loop_length_weight * length
                      + LOOP_TERMINATION_BONUS
                      - self.w.adjacent_triangle_penalty_weight * penalty
                      - self.w.quad_perfection_weight * quad_dev_sum
                      - short_edge_sum)

        ops = self._path_to_ops(path)
        return SolutionCandidate(ops, term_score, {
            'loop_length': length, 'termination': 'polygon', 'branch_offs': 0})

    def _make_dead_leaf(self, edge, path, length, penalty, reason,
                        quad_dev_sum, short_edge_sum):
        score = (-self.w.loop_length_weight * length
                 - self.w.adjacent_triangle_penalty_weight * penalty
                 - self.w.quad_perfection_weight * quad_dev_sum
                 - short_edge_sum)
        if reason == 'boundary':
            score += LOOP_TERMINATION_BONUS
        ops = self._path_to_ops(path)
        return SolutionCandidate(ops, score, {
            'loop_length': length, 'termination': reason, 'branch_offs': 0})

    def _path_to_ops(self, path_edges):
        return [('quad_loop', list(path_edges))]

    def search(self, start_edge, triangle, max_results=3, max_expansions=200):
        start_face = self._other_face(start_edge, triangle)
        if start_face is None:
            return []

        # Triangle-triangle adjacent: split shared edge → both become quads
        if len(start_face.verts) == 3:
            ops = [('quad_loop', [start_edge])]
            penalty = 1.0  # adjacent-triangle penalty applies
            score = (-self.w.adjacent_triangle_penalty_weight * penalty
                     - self._short_edge_penalty(start_edge, start_face))
            return [SolutionCandidate(ops, score, {
                'loop_length': 0, 'termination': 'tris_adjacent',
                'branch_offs': 0})]

        # Triangle-pentagon adjacent: split shared edge → triangle→quad, pentagon→hexagon
        if len(start_face.verts) == 5:
            ops = [('quad_loop', [start_edge])]
            score = -self._short_edge_penalty(start_edge, start_face)
            return [SolutionCandidate(ops, score, {
                'loop_length': 0, 'termination': 'tri_pent_adjacent',
                'branch_offs': 0})]

        if len(start_face.verts) != 4:
            return []

        adj_tri = any(len(f.verts) == 3 for f in start_edge.link_faces if f != triangle)

        start_loop = self._find_loop(start_edge, start_face)
        if start_loop is None:
            return []

        visited = {start_edge.index}
        root = _SearchNode(
            edge=start_edge, quad_face=start_face,
            path_edges=[start_edge], length=0,
            branch_offs=0, visited=visited,
            partial_score=0.0, adj_tri_penalty=adj_tri,
            origin_tri=triangle,
        )

        results = []
        heap = [(0.0, self._heap_counter, root)]
        self._heap_counter += 1
        _n_expansions = 0

        while heap and len(results) < max_results:
            _, _, node = heapq.heappop(heap)

            if node.length > self.max_length:
                continue

            opp_loop = self._opposite_loop(
                self._find_loop(node.edge, node.quad_face))
            self._expand(node, opp_loop, False, heap, results)
            _n_expansions += 1

            if node.branch_offs < self.max_branch_offs and _n_expansions < max_expansions:
                for adj_loop in self._adjacent_loops(
                        self._find_loop(node.edge, node.quad_face)):
                    self._expand(node, adj_loop, True, heap, results)
                    _n_expansions += 1

            if _n_expansions >= max_expansions:
                break

        return results

    def _expand(self, node, exit_loop, is_branch, heap, results):
        exit_edge = exit_loop.edge

        if not self.edge_is_valid(exit_edge, for_traversal=True):
            return

        quad_dev = MeshUtils.angle90_deviation(node.quad_face)
        short_edge = self._short_edge_penalty(exit_edge, node.quad_face)

        new_path = list(node.path_edges) + [exit_edge]
        new_len = node.length + 1
        new_visited = set(node.visited)
        new_visited.add(exit_edge.index)

        # Check termination: polygon reached
        poly_reached = None
        for f in exit_edge.link_faces:
            n = len(f.verts)
            if n in (3, 5):
                poly_reached = True
                break

        if poly_reached:
            if f is node.origin_tri and n == 3:
                results.append(self._make_dead_leaf(
                    exit_edge, new_path, new_len,
                    node.adj_tri_penalty, 'fractal',
                    node.quad_dev_sum + quad_dev,
                    node.short_edge_sum + short_edge))
                return
            results.append(self._make_leaf(
                exit_edge, new_path, new_len, node.adj_tri_penalty,
                node.quad_dev_sum + quad_dev,
                node.short_edge_sum + short_edge))
            return

        # Boundary termination
        if len(exit_edge.link_faces) < 2:
            results.append(self._make_dead_leaf(
                exit_edge, new_path, new_len, node.adj_tri_penalty, 'boundary',
                node.quad_dev_sum + quad_dev,
                node.short_edge_sum + short_edge))
            return

        # Loop-back termination
        if exit_edge.index in node.visited:
            results.append(self._make_dead_leaf(
                exit_edge, new_path, new_len, node.adj_tri_penalty, 'loop',
                node.quad_dev_sum + quad_dev,
                node.short_edge_sum + short_edge))
            return

        # Continue to next quad
        next_face = self._other_face(exit_edge, node.quad_face)
        if next_face is None or len(next_face.verts) != 4:
            results.append(self._make_dead_leaf(
                exit_edge, new_path, new_len, node.adj_tri_penalty, 'dead_end',
                node.quad_dev_sum + quad_dev,
                node.short_edge_sum + short_edge))
            return

        next_loop = self._find_loop(exit_edge, next_face)
        if next_loop is None:
            return

        new_branch_offs = node.branch_offs + (1 if is_branch else 0)
        new_score = (node.partial_score
                     - self.w.loop_length_weight
                     - self.w.quad_perfection_weight * quad_dev
                     - self.w.branch_penalty_weight * new_branch_offs
                     - short_edge)

        child = _SearchNode(
            edge=exit_edge, quad_face=next_face,
            path_edges=new_path, length=new_len,
            branch_offs=new_branch_offs, visited=new_visited,
            partial_score=new_score,
            quad_dev_sum=node.quad_dev_sum + quad_dev,
            short_edge_sum=node.short_edge_sum + short_edge,
            adj_tri_penalty=node.adj_tri_penalty,
            origin_tri=node.origin_tri,
        )
        heapq.heappush(heap, (-new_score, self._heap_counter, child))
        self._heap_counter += 1

# -----------------------------------------------------------------------------
# Base Solver
# -----------------------------------------------------------------------------

class BaseSolver:
    def solve(self, bm, face, weights, orig_quad_keys=None):
        raise NotImplementedError

# -----------------------------------------------------------------------------
# Triangle Solver
# -----------------------------------------------------------------------------

class TriangleSolver(BaseSolver):
    def _merge_candidate(self, bm, tri, edge, quad, weights, orig_quad_keys=None):
        shared = list(edge.verts)
        apex = None
        for v in tri.verts:
            if v not in shared:
                apex = v
                break
        if apex is None:
            return None
        far = None
        for e in quad.edges:
            if e is edge:
                continue
            if (e.verts[0] not in shared and e.verts[1] not in shared):
                far = e
                break
        if far is None:
            return None
        # Splitting `far` adds a vertex to every face sharing it; if a 6+ gon
        # sits across it, that face would grow into an unsolvable 7+ gon.
        for f in far.link_faces:
            if f is not quad and len(f.verts) >= 6:
                return None
        loop_ab = None
        for loop in edge.link_loops:
            if loop.face == quad:
                loop_ab = loop
                break
        if loop_ab is None:
            return None
        b = loop_ab.link_loop_next.vert
        d = loop_ab.link_loop_next.link_loop_next.vert
        e_v = loop_ab.link_loop_prev.vert
        m_co = (far.verts[0].co + far.verts[1].co) * 0.5
        coords_q1 = [loop_ab.vert.co, apex.co, m_co, e_v.co]
        coords_q2 = [apex.co, b.co, d.co, m_co]
        dev_sum = (MeshUtils.quad_dev_coords(coords_q1)
                   + MeshUtils.quad_dev_coords(coords_q2))
        if math.isinf(dev_sum):
            return None
        score = (LOOP_TERMINATION_BONUS
                 - weights.loop_length_weight * MERGE_LOOP_LENGTH
                 - weights.quad_perfection_weight * dev_sum)
        if orig_quad_keys and weights.original_quad_penalty_weight > 0.0:
            key = frozenset(tuple(round(v.co[j], 6) for j in range(3))
                            for v in quad.verts)
            if key in orig_quad_keys:
                score -= weights.original_quad_penalty_weight
        ops = [('tri_quad_merge', tri, edge)]
        return SolutionCandidate(ops, score, {
            'solver': 'triangle', 'start_edge': edge.index,
            'termination': 'tri_quad_merge', 'quad_dev': dev_sum})

    def solve(self, bm, face, weights, orig_quad_keys=None):
        candidates = []
        qls = QuadLoopSearch(bm, weights)

        for edge in face.edges:
            if not QuadLoopSearch.edge_is_valid(edge, for_traversal=True):
                continue
            neighbor = QuadLoopSearch._other_face(edge, face)
            if neighbor is not None and len(neighbor.verts) == 4:
                merge_c = self._merge_candidate(
                    bm, face, edge, neighbor, weights, orig_quad_keys)
                if merge_c is not None:
                    candidates.append(merge_c)
            results = qls.search(edge, face)
            for c in results:
                c.sub_scores['solver'] = 'triangle'
                c.sub_scores['start_edge'] = edge.index
            candidates.extend(results)

        if not candidates:
            safe_edges = []
            face_edges = list(face.edges)
            for edge in face_edges:
                for f in edge.link_faces:
                    if f == face:
                        continue
                    if len(f.verts) >= 6:
                        break
                else:
                    safe_edges.append(edge)
            if safe_edges:
                def _edge_score(e):
                    s = -weights.loop_length_weight * 10.0
                    if weights.short_edge_penalty_weight > 0.0:
                        max_len = max(x.calc_length() for x in face.edges)
                        if max_len > 0:
                            ratio = e.calc_length() / max_len
                            s -= weights.short_edge_penalty_weight * (1.0 - ratio)
                    return s
                best_edge = max(safe_edges, key=_edge_score)
                ops = [('quad_loop', [best_edge])]
                score = _edge_score(best_edge)
                return [SolutionCandidate(ops, score, {
                    'solver': 'triangle', 'start_edge': best_edge.index,
                    'fallback': True, 'termination': 'direct_split'})]
            else:
                score = -weights.loop_length_weight * 15.0
                if weights.center_subs_penalty_weight > 0.0:
                    layer = bm.faces.layers.int.get(CENTER_LAYER_NAME)
                    if layer is not None:
                        score -= weights.center_subs_penalty_weight * face[layer]
                ops = [('poke_tri', face)]
                return [SolutionCandidate(ops, score, {
                    'solver': 'triangle', 'fallback': True,
                    'termination': 'poke'})]

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

# -----------------------------------------------------------------------------
# Pentagon Solver
# -----------------------------------------------------------------------------

class PentagonSolver(BaseSolver):
    # A pentagon vertex within this many degrees of being perfectly
    # straight (interior angle) is treated as a degenerate spike: dissolving
    # it yields a quad without introducing tiny sliver faces.
    DEGENERATE_ANGLE = 170.0

    def solve(self, bm, face, weights, orig_quad_keys=None):
        verts = list(face.verts)
        candidates = []

        for i in range(5):
            v = verts[i]
            p = verts[i - 1]
            n = verts[(i + 1) % 5]
            d1 = p.co - v.co
            d2 = n.co - v.co
            l1 = d1.length
            l2 = d2.length
            if l1 > MeshUtils.EPSILON_LENGTH and l2 > MeshUtils.EPSILON_LENGTH:
                dot = max(-1.0, min(1.0, d1.dot(d2) / (l1 * l2)))
                angle = math.degrees(math.acos(dot))
                if angle >= self.DEGENERATE_ANGLE:
                    score = LOOP_TERMINATION_BONUS
                    if weights.center_subs_penalty_weight > 0.0:
                        layer = bm.faces.layers.int.get(CENTER_LAYER_NAME)
                        if layer is not None:
                            score -= weights.center_subs_penalty_weight * face[layer]
                    ops = [('dissolve_vert', face, v)]
                    candidates.append(SolutionCandidate(ops, score, {
                        'solver': 'pentagon', 'dissolve': i,
                        'termination': 'degenerate_dissolve'}))

        for i in range(5):
            j = (i + 2) % 5

            quad_idx = [(i + k) % 5 for k in range(4)]

            quad_verts = [verts[k] for k in quad_idx]

            quad_dev = 0.0
            for k in range(4):
                v0 = quad_verts[k].co
                v1 = quad_verts[(k + 1) % 4].co
                v2 = quad_verts[(k + 2) % 4].co
                a = (v1 - v0).normalized()
                b = (v2 - v1).normalized()
                dot = max(-1, min(1, a.dot(b)))
                quad_dev += abs(math.degrees(math.acos(dot)) - 90)

            score = -weights.quad_perfection_weight * quad_dev

            ops = [('diagonal_cut', face, verts[i], verts[j])]
            candidates.append(SolutionCandidate(ops, score, {
                'solver': 'pentagon', 'cut': (i, j),
                'quad_dev': quad_dev}))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

# -----------------------------------------------------------------------------
# Hexagon Solver
# -----------------------------------------------------------------------------

class HexagonSolver(BaseSolver):
    def solve(self, bm, face, weights, orig_quad_keys=None):
        verts = list(face.verts)
        if len(verts) != 6:
            return [SolutionCandidate([], float('-inf'))]

        centroid = MeshUtils.centroid(verts)
        candidates = []

        for offset in (0, 1):
            dissolve = [(offset + 1 + i * 2) % 6 for i in range(3)]
            ops = [('hexagon_center', face, centroid, dissolve)]

            predicted_dev = 0.0
            for i in range(3):
                idx0 = (offset + i * 2) % 6
                idx1 = (offset + i * 2 + 1) % 6
                idx2 = (offset + i * 2 + 2) % 6
                pts = [centroid, verts[idx0].co, verts[idx1].co, verts[idx2].co]
                for k in range(4):
                    a = (pts[(k + 1) % 4] - pts[k]).normalized()
                    b = (pts[(k + 2) % 4] - pts[(k + 1) % 4]).normalized()
                    dot = max(-1, min(1, a.dot(b)))
                    predicted_dev += abs(math.degrees(math.acos(dot)) - 90)

            score = -weights.hexagon_perfection_weight * predicted_dev
            if weights.center_subs_penalty_weight > 0.0:
                layer = bm.faces.layers.int.get(CENTER_LAYER_NAME)
                if layer is not None:
                    score -= weights.center_subs_penalty_weight * face[layer]
            candidates.append(SolutionCandidate(ops, score, {
                'solver': 'hexagon', 'pattern': offset,
                'quads_deviation': predicted_dev}))

        # Always offer the direct two-quad cut as a fallback: the center
        # pattern can produce concave quads on non-planar (yet convex)
        # hexagons, and validation then falls back to a diagonal cut.
        for i in range(3):
            j = i + 3
            quads = ([verts[(i + k) % 6] for k in range(4)],
                     [verts[(j + k) % 6] for k in range(4)])
            dev = 0.0
            for quad in quads:
                for k in range(4):
                    v0 = quad[k].co
                    v1 = quad[(k + 1) % 4].co
                    v2 = quad[(k + 2) % 4].co
                    d1 = v1 - v0
                    d2 = v2 - v1
                    l1 = d1.length
                    l2 = d2.length
                    if l1 < MeshUtils.EPSILON_LENGTH or l2 < MeshUtils.EPSILON_LENGTH:
                        continue
                    dot = max(-1.0, min(1.0, d1.dot(d2) / (l1 * l2)))
                    dev += abs(math.degrees(math.acos(dot)) - 90)
            score = -weights.quad_perfection_weight * dev
            if weights.short_edge_penalty_weight > 0.0:
                max_len = max(e.calc_length() for e in face.edges)
                if max_len > 0:
                    cut_len = (verts[i].co - verts[j].co).length
                    score -= weights.short_edge_penalty_weight * (1.0 - cut_len / max_len)
            ops = [('diagonal_cut', face, verts[i], verts[j])]
            candidates.append(SolutionCandidate(ops, score, {
                'solver': 'hexagon', 'pattern': 'diag_%d' % i,
                'quads_deviation': dev}))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

# -----------------------------------------------------------------------------
# Solvers dict : n_sides -> solver_class
# -----------------------------------------------------------------------------

SOLVERS = {
    3: TriangleSolver,
    5: PentagonSolver,
    6: HexagonSolver,
}

# -----------------------------------------------------------------------------
# Topology operations
# -----------------------------------------------------------------------------

class TopologyApplier:
    @staticmethod
    def split_edge(bm, edge):
        if not edge or not edge.is_valid:
            return None
        result = bmesh.utils.edge_split(edge, edge.verts[0], 0.5)
        if result:
            return result[1]
        return None

    @staticmethod
    def diagonal_cut(bm, face, v1, v2):
        if not all(x.is_valid for x in (face, v1, v2)):
            return None
        result = bmesh.utils.face_split(face, v1, v2)
        if result:
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
        return result

    @staticmethod
    def tri_quad_merge(bm, tri, shared_edge, center_layer_name=CENTER_LAYER_NAME):
        if not (tri is not None and tri.is_valid
                and shared_edge is not None and shared_edge.is_valid):
            return None
        quad = None
        for f in shared_edge.link_faces:
            if f is not tri and f.is_valid and len(f.verts) == 4:
                quad = f
                break
        if quad is None:
            return None
        apex = None
        for v in tri.verts:
            if v not in shared_edge.verts:
                apex = v
                break
        if apex is None:
            return None
        far = None
        for e in quad.edges:
            if e is shared_edge:
                continue
            if (e.verts[0] not in shared_edge.verts
                    and e.verts[1] not in shared_edge.verts):
                far = e
                break
        if far is None:
            return None
        for f in far.link_faces:
            if f is not quad and len(f.verts) >= 6:
                return None

        parent_count = 0
        if center_layer_name:
            layer = bm.faces.layers.int.get(center_layer_name)
            if layer is not None:
                parent_count = max(tri[layer], quad[layer])

        m = TopologyApplier.split_edge(bm, far)
        if m is None:
            return None
        bm.verts.ensure_lookup_table()
        bmesh.ops.dissolve_edges(bm, edges=[shared_edge], use_verts=False)
        bm.faces.ensure_lookup_table()

        merged = None
        for f in m.link_faces:
            if f.is_valid and apex in f.verts and len(f.verts) >= 5:
                merged = f
                break
        if merged is None:
            return None

        result = bmesh.utils.face_split(merged, apex, m)
        bm.faces.ensure_lookup_table()
        if not result:
            return None

        out = []
        for item in result:
            f = getattr(item, 'face', item)
            if f is not None and f.is_valid:
                out.append(f)
                if center_layer_name and parent_count < 255:
                    layer = bm.faces.layers.int.get(center_layer_name)
                    if layer is not None:
                        f[layer] = parent_count
        return out

    @staticmethod
    def hexagon_center(bm, face, centroid_co, dissolve_indices, center_layer_name=CENTER_LAYER_NAME):
        if not face or not face.is_valid:
            return None
        verts = list(face.verts)
        if len(verts) != 6:
            return None

        parent_count = 0
        if center_layer_name:
            layer = bm.faces.layers.int.get(center_layer_name)
            if layer is not None:
                parent_count = face[layer]

        res = bmesh.ops.poke(bm, faces=[face])
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        center = res['verts'][0]

        if center_layer_name and parent_count < 255:
            layer = bm.faces.layers.int.get(center_layer_name)
            if layer is not None:
                for f in center.link_faces:
                    if f.is_valid:
                        f[layer] = parent_count + 1

        edges_to_dissolve = []
        for i in dissolve_indices:
            v = verts[i]
            if not v or not v.is_valid:
                continue
            for e in center.link_edges:
                if e.other_vert(center) == v:
                    edges_to_dissolve.append(e)
                    break

        if edges_to_dissolve:
            bmesh.ops.dissolve_edges(bm, edges=edges_to_dissolve, use_verts=False)
            bm.faces.ensure_lookup_table()

        result_faces = [f for f in center.link_faces if f.is_valid]
        return result_faces

    @staticmethod
    def _face_boundary(face):
        return [loop.vert for loop in face.loops]

    @staticmethod
    def _find_opposite_edge(face, vert, incoming_edge):
        boundary = TopologyApplier._face_boundary(face)
        n = len(boundary)
        try:
            vert_idx = boundary.index(vert)
        except ValueError:
            return None
        other_vert = incoming_edge.other_vert(vert)
        prev_idx = (vert_idx - 1) % n
        next_idx = (vert_idx + 1) % n
        if boundary[prev_idx] == other_vert:
            direction = 1
        elif boundary[next_idx] == other_vert:
            direction = -1
        else:
            return None
        far_indices = []
        idx = vert_idx
        for _ in range(n - 2):
            idx = (idx + direction) % n
            far_indices.append(idx)
        num_internal = len(far_indices) - 1
        if num_internal <= 0:
            return None
        mid = num_internal // 2
        v1 = boundary[far_indices[mid]]
        v2 = boundary[far_indices[mid + 1]]
        for e in face.edges:
            if v1 in e.verts and v2 in e.verts:
                return e
        return None

    @staticmethod
    def _find_opposite_vertex(face, vert, incoming_edge):
        boundary = TopologyApplier._face_boundary(face)
        n = len(boundary)
        if n % 2 != 0:
            return None
        try:
            vert_idx = boundary.index(vert)
        except ValueError:
            return None
        other_vert = incoming_edge.other_vert(vert)
        prev_idx = (vert_idx - 1) % n
        next_idx = (vert_idx + 1) % n
        if boundary[prev_idx] == other_vert:
            direction = 1
        elif boundary[next_idx] == other_vert:
            direction = -1
        else:
            return None
        opp_idx = (vert_idx + direction * (n // 2)) % n
        return boundary[opp_idx]

    @staticmethod
    def quad_loop(bm, edge_refs, center_layer_name=CENTER_LAYER_NAME):
        edges = TopologyApplier._resolve_edge_refs(bm, edge_refs)
        if not edges:
            return []

        e0 = edges[0]
        if not e0.is_valid:
            return []
        e0_orig_v0 = e0.verts[0]
        e0_orig_v1 = e0.verts[1]
        result = bmesh.utils.edge_split(e0, e0.verts[0], 0.5)
        if not result:
            return []
        prev_vert = result[1]
        entry_edge = result[0]
        bm.faces.ensure_lookup_table()

        affected = [f for f in prev_vert.link_faces if f.is_valid]

        if len(edges) == 1:
            return affected

        for path_edge in edges[1:]:
            if not path_edge.is_valid:
                break

            target_face = None
            for f in prev_vert.link_faces:
                if not f.is_valid or len(f.verts) <= 4:
                    continue
                if path_edge in f.edges:
                    target_face = f
                    break

            if target_face is None:
                break

            nv = len(target_face.verts)

            path_shares_vert = (
                prev_vert != path_edge.verts[0] and
                prev_vert != path_edge.verts[1] and
                (e0_orig_v0 in path_edge.verts or e0_orig_v1 in path_edge.verts)
            )

            if path_shares_vert and nv == 5:
                is_boundary_exit = (path_edge is edges[-1]
                                    and len(path_edge.link_faces) < 2)
                if not is_boundary_exit:
                    opp_edge = TopologyApplier._find_opposite_edge(
                        target_face, prev_vert, entry_edge)
                    if opp_edge is None:
                        break
                    skip = False
                    for other_f in opp_edge.link_faces:
                        if other_f != target_face and len(other_f.verts) >= 6:
                            skip = True
                            break
                    if skip:
                        break
                    spl = bmesh.utils.edge_split(
                        opp_edge, opp_edge.verts[0], 0.5)
                    if not spl:
                        break
                    exit_vert = spl[1]
                    bm.faces.ensure_lookup_table()
                    spl_result = bmesh.utils.face_split(
                        target_face, prev_vert, exit_vert)
                    if spl_result:
                        bm.faces.ensure_lookup_table()
                        affected.extend(
                            f for f in spl_result if f and f.is_valid)
                    break
                else:
                    shared = None
                    for v in (e0_orig_v0, e0_orig_v1):
                        if v in path_edge.verts:
                            shared = v
                            break
                    if shared is None:
                        break
                    A_vert = (e0_orig_v0 if e0_orig_v0 != shared
                              else e0_orig_v1)
                    C_vert = (path_edge.verts[0]
                              if path_edge.verts[0] != shared
                              else path_edge.verts[1])
                    D_vert = None
                    for v in target_face.verts:
                        if v not in (A_vert, shared, C_vert, prev_vert):
                            if v not in path_edge.verts:
                                D_vert = v
                                break
                    if D_vert is None:
                        break

                    spl = bmesh.utils.edge_split(
                        path_edge, shared, 0.5)
                    if not spl:
                        break
                    exit_vert = spl[1]
                    bm.faces.ensure_lookup_table()

                    co = (A_vert.co + shared.co
                          + C_vert.co + D_vert.co) / 4.0
                    O = bm.verts.new(co)
                    bm.verts.ensure_lookup_table()

                    fv = list(target_face.verts)
                    nf = len(fv)
                    try:
                        i_x = fv.index(prev_vert)
                        i_s = fv.index(shared)
                    except ValueError:
                        break
                    ccw_dir = (i_s - i_x) % nf == 1

                    parent_count = 0
                    if center_layer_name:
                        layer = bm.faces.layers.int.get(center_layer_name)
                        if layer is not None:
                            parent_count = target_face[layer]

                    bm.faces.remove(target_face)

                    if ccw_dir:
                        q1 = bm.faces.new((A_vert, prev_vert, O, D_vert))
                        q2 = bm.faces.new((prev_vert, shared, exit_vert, O))
                        q3 = bm.faces.new((exit_vert, C_vert, D_vert, O))
                    else:
                        q1 = bm.faces.new((D_vert, O, prev_vert, A_vert))
                        q2 = bm.faces.new((O, exit_vert, shared, prev_vert))
                        q3 = bm.faces.new((O, D_vert, C_vert, exit_vert))

                    if center_layer_name and parent_count < 255:
                        layer = bm.faces.layers.int.get(center_layer_name)
                        if layer is not None:
                            for qf in (q1, q2, q3):
                                if qf.is_valid:
                                    qf[layer] = parent_count + 1

                    bm.faces.ensure_lookup_table()
                    affected.extend([q1, q2, q3])
                    break
            else:
                spl = bmesh.utils.edge_split(
                    path_edge, path_edge.verts[0], 0.5)
                if not spl:
                    break
                exit_vert = spl[1]
                bm.faces.ensure_lookup_table()
                spl_result = bmesh.utils.face_split(
                    target_face, prev_vert, exit_vert)
                if spl_result:
                    bm.faces.ensure_lookup_table()
                    affected.extend(
                        f for f in spl_result if f and f.is_valid)
                prev_vert = exit_vert

        return affected

    @staticmethod
    def _resolve_edge_refs(bm, edge_refs):
        edges = []
        for ref in edge_refs:
            if isinstance(ref, int):
                bm.edges.ensure_lookup_table()
                e = bm.edges[ref]
            else:
                e = ref
            if e and e.is_valid:
                edges.append(e)
        return edges

    @staticmethod
    def apply(bm, operations, center_layer_name=CENTER_LAYER_NAME):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        affected = []
        for op in operations:
            if not op:
                continue
            kind = op[0]
            if kind == 'quad_loop':
                r = TopologyApplier.quad_loop(bm, op[1], center_layer_name)
                if r:
                    for f in r:
                        if f.is_valid:
                            affected.append(f)
            elif kind == 'diagonal_cut':
                _, face, v1, v2 = op
                r = TopologyApplier.diagonal_cut(bm, face, v1, v2)
                if r and r[1] and r[1].is_valid:
                    affected.append(r[1])
            elif kind == 'hexagon_center':
                _, face, co, diss = op
                r = TopologyApplier.hexagon_center(bm, face, co, diss, center_layer_name)
                if r:
                    for f in r:
                        if f.is_valid:
                            affected.append(f)
            elif kind == 'tri_quad_merge':
                _, tri_face, shared_edge = op
                r = TopologyApplier.tri_quad_merge(
                    bm, tri_face, shared_edge, center_layer_name)
                if r:
                    for f in r:
                        if f.is_valid:
                            affected.append(f)
            elif kind == 'poke_tri':
                _, face = op
                parent_count = 0
                if center_layer_name:
                    layer = bm.faces.layers.int.get(center_layer_name)
                    if layer is not None:
                        parent_count = face[layer]
                r = bmesh.ops.poke(bm, faces=[face])
                bm.verts.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                if r and 'verts' in r:
                    center = r['verts'][0]
                    if center_layer_name and parent_count < 255:
                        layer = bm.faces.layers.int.get(center_layer_name)
                        if layer is not None:
                            for f in center.link_faces:
                                if f.is_valid:
                                    f[layer] = parent_count + 1
                    for f in bm.faces:
                        if f.is_valid and len(f.verts) == 3:
                            affected.append(f)
            elif kind == 'dissolve_vert':
                _, face, v = op
                bmesh.ops.dissolve_verts(bm, verts=[v])
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                if face.is_valid:
                    affected.append(face)

        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        return affected

    @staticmethod
    def _ops_to_indices(ops):
        idx_ops = []
        for op in ops:
            kind = op[0]
            if kind == 'quad_loop':
                idx_ops.append(('quad_loop', [e.index for e in op[1]]))
            elif kind == 'diagonal_cut':
                _, face, v1, v2 = op
                idx_ops.append(('diagonal_cut', face.index, v1.index, v2.index))
            elif kind == 'hexagon_center':
                _, face, co, diss = op
                idx_ops.append(('hexagon_center', face.index, co, diss))
            elif kind == 'tri_quad_merge':
                idx_ops.append(('tri_quad_merge', op[1].index, op[2].index))
            elif kind == 'poke_tri':
                idx_ops.append(('poke_tri', op[1].index))
            elif kind == 'dissolve_vert':
                idx_ops.append(('dissolve_vert', op[1].index, op[2].index))
            else:
                idx_ops.append(op)
        return idx_ops

    @staticmethod
    def _resolve_ops(bm, idx_ops):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        ops = []
        for op in idx_ops:
            kind = op[0]
            if kind == 'quad_loop':
                ops.append(('quad_loop', [bm.edges[i] for i in op[1]]))
            elif kind == 'diagonal_cut':
                ops.append(('diagonal_cut', bm.faces[op[1]], bm.verts[op[2]], bm.verts[op[3]]))
            elif kind == 'hexagon_center':
                ops.append(('hexagon_center', bm.faces[op[1]], op[2], op[3]))
            elif kind == 'tri_quad_merge':
                ops.append(('tri_quad_merge', bm.faces[op[1]], bm.edges[op[2]]))
            elif kind == 'poke_tri':
                ops.append(('poke_tri', bm.faces[op[1]]))
            elif kind == 'dissolve_vert':
                ops.append(('dissolve_vert', bm.faces[op[1]], bm.verts[op[2]]))
            else:
                ops.append(op)
        return ops

# -----------------------------------------------------------------------------
# Engine
# -----------------------------------------------------------------------------

class QuadrangulationEngine:
    def __init__(self, obj, weights, max_length=20, max_branch_offs=2,
                 max_relax=10, max_iterations=500, min_area=DEFAULT_MIN_AREA,
                 collinear_angle=175, push_factor=0.15,
                 reflex_lerp=0.5, relax_max_edge_count=5):
        self.obj = obj
        self.w = weights
        self.max_length = max_length
        self.max_branch_offs = max_branch_offs
        self.max_relax = max_relax
        self.max_iterations = max_iterations
        self.min_area = min_area
        self.max_edge_count = relax_max_edge_count
        self.collinear_angle = collinear_angle
        self.push_factor = push_factor
        self.reflex_lerp = reflex_lerp
        self.failed_sigs = set()

    @staticmethod
    def _orig_quad_keys_from_mesh(me, rounding=6):
        """Face keys (rounded vertex coords) of the input mesh's quads.

        Used to detect how many original quads survive a solve: a quad whose
        coordinate key is still present at the end was never modified or merged.
        Rounds to 6 decimals so untouched quads match exactly while relaxed
        verts drift out of the set.
        """
        keys = set()
        for poly in me.polygons:
            if len(poly.vertices) == 4:
                keys.add(frozenset(
                    tuple(round(me.vertices[i].co[j], rounding) for j in range(3))
                    for i in poly.vertices))
        return keys

    @staticmethod
    def _face_key_rounded(face, rounding=6):
        return frozenset(tuple(round(v.co[j], rounding) for j in range(3))
                         for v in face.verts)

    def run(self):
        me = self.obj.data
        orig_quad_keys = self._orig_quad_keys_from_mesh(me)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        for f in bm.faces:
            f.tag = False

        clayer = bm.faces.layers.int.new(CENTER_LAYER_NAME)
        for f in bm.faces:
            f[clayer] = 0

        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        self._preprocess_concave(bm)

        stats = {'solved': 0, 'failed': 0, 'unsupported': 0, 'remaining': {}}

        iteration = 0
        while True:
            if self.max_iterations > 0 and iteration >= self.max_iterations:
                for f in bm.faces:
                    if len(f.verts) != 4:
                        stats['remaining'][len(f.verts)] = \
                            stats['remaining'].get(len(f.verts), 0) + 1
                break
            iteration += 1

            polygons = self._find_untagged(bm)
            if not polygons:
                break

            face, n_sides = self._pick_best(bm, polygons, self.w)
            if face is None:
                for f in polygons:
                    n = len(f.verts)
                    stats['remaining'][n] = stats['remaining'].get(n, 0) + 1
                break

            solver_cls = SOLVERS.get(n_sides)
            if solver_cls is None:
                stats['unsupported'] += 1
                self.failed_sigs.add((id(face), n_sides))
            else:
                solver = solver_cls()
                candidates = solver.solve(bm, face, self.w, orig_quad_keys)

                if not candidates:
                    stats['failed'] += 1
                    self.failed_sigs.add((id(face), n_sides))
                else:
                    best = self._first_valid_candidate(bm, candidates)
                    if best is None:
                        stats['failed'] += 1
                        self.failed_sigs.add((id(face), n_sides))
                    else:
                        affected = TopologyApplier.apply(bm, best.operations)
                        if self.max_relax > 0:
                            MeshUtils.relax_faces(
                                bm, affected, self.max_relax,
                                collinear_angle=self.collinear_angle,
                                push_factor=self.push_factor,
                                reflex_lerp=self.reflex_lerp,
                                max_edge_count=self.max_edge_count)
                        bm.faces.index_update()
                        stats['solved'] += 1
                        # Topology changed: a face that failed earlier may now
                        # be solvable. Only clear on actual progress so a fully
                        # stuck mesh still terminates via an empty untagged set.
                        self.failed_sigs.clear()

            self._reset_tags(bm)

        MeshUtils.fix_concave_quads(bm)
        remaining = {}
        for f in bm.faces:
            n = len(f.verts)
            if n != 4:
                remaining[n] = remaining.get(n, 0) + 1
        stats['remaining'] = remaining
        if stats['solved'] > 0 or remaining:
            bm.to_mesh(me)
            me.update()

        bm.free()
        return stats

    def _reset_tags(self, bm):
        for f in bm.faces:
            n = len(f.verts)
            f.tag = (n == 4 or n not in SOLVERS)

    @staticmethod
    def _preprocess_concave(bm):
        """Triangulate concave input quads before the solve loop.

        A concave quad can never be solved (n=4, not in SOLVERS) and the
        end-of-pass fix would triangulate it into two unsolvable triangles.
        Triangulating up front lets the triangle solvers recover them as
        quads during the solve.
        """
        for f in list(bm.faces):
            if f.is_valid and len(f.verts) == 4 and not MeshUtils.is_convex(f):
                bmesh.ops.triangulate(bm, faces=[f], quad_method='SHORT_EDGE',
                                      ngon_method='BEAUTY')
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    def _find_untagged(self, bm):
        return [f for f in bm.faces
                if not f.tag and len(f.verts) != 4
                and (id(f), len(f.verts)) not in self.failed_sigs
                and f.calc_area() >= self.min_area]

    @staticmethod
    def _pick_best(bm, faces, weights=None):
        by_side = {}
        for f in faces:
            by_side.setdefault(len(f.verts), []).append(f)

        for n in sorted(by_side.keys()):
            if n in SOLVERS:
                pool = by_side[n]
                if weights is not None and weights.area_penalty_weight > 0.0:
                    max_area = max(f.calc_area() for f in pool) or 1.0
                else:
                    max_area = 1.0
                pool.sort(key=lambda f, _max=max_area, _w=weights: (
                    min(abs(math.degrees(loop.calc_angle()) - 90)
                        for loop in f.loops) if f.loops else 0
                    + (_w.area_penalty_weight * (1.0 - f.calc_area() / _max)
                       if _w is not None and _w.area_penalty_weight > 0.0 else 0.0),
                    sum(v.co.x + v.co.y + v.co.z for v in f.verts)
                ))
                return pool[0], n

        return None, 0

    @staticmethod
    def _pick_top_faces(bm, faces, k, weights=None):
        by_side = {}
        for f in faces:
            by_side.setdefault(len(f.verts), []).append(f)
        pool = []
        for n in sorted(by_side.keys()):
            if n in SOLVERS:
                if weights is not None and weights.area_penalty_weight > 0.0:
                    max_area = max(f.calc_area() for f in by_side[n]) or 1.0
                else:
                    max_area = 1.0
                by_side[n].sort(key=lambda f, _max=max_area, _w=weights: (
                    min(abs(math.degrees(loop.calc_angle()) - 90)
                        for loop in f.loops) if f.loops else 0
                    + (_w.area_penalty_weight * (1.0 - f.calc_area() / _max)
                       if _w is not None and _w.area_penalty_weight > 0.0 else 0.0),
                    sum(v.co.x + v.co.y + v.co.z for v in f.verts)
                ))
                for f in by_side[n]:
                    pool.append((n, f))
                if len(pool) >= k:
                    break
        return [(f, n) for n, f in pool[:k]]

    # =========================================================================
    # Concavity prevention — reject candidates that would create bad geometry
    # =========================================================================

    def _new_faces_are_bad(self, bm, new_faces):
        for f in new_faces:
            if not f.is_valid:
                return True
            n = len(f.verts)
            if n < 3:
                return True
            if n > 6:
                # Solvers only handle 3, 5 and 6 sides; a 7+ gon created during
                # a pass can never be resolved and stays forever, so reject it.
                return True
            if n > 3 and not MeshUtils.is_convex(f):
                return True
            if f.calc_area() < self.min_area:
                return True
        return False

    def _first_valid_candidate(self, bm, candidates):
        for c in candidates:
            if not c or not c.operations or c.score == float('-inf'):
                continue
            if not self._candidate_creates_bad_faces(bm, c):
                return c
        return None

    def _candidate_creates_bad_faces(self, bm, candidate):
        if not candidate or not candidate.operations:
            return False
        kinds = {op[0] for op in candidate.operations if op}
        if not (kinds & {'quad_loop', 'diagonal_cut', 'hexagon_center',
                         'tri_quad_merge', 'dissolve_vert'}):
            return False
        copy = bm.copy()
        try:
            old = {self._face_key(f) for f in copy.faces}
            idx_ops = TopologyApplier._ops_to_indices(candidate.operations)
            ops_resolved = TopologyApplier._resolve_ops(copy, idx_ops)
            TopologyApplier.apply(copy, ops_resolved)
            copy.faces.ensure_lookup_table()
            copy.normal_update()
            # Keyed by vertex coordinates, not wrapper identity: an operation
            # may grow an existing face (e.g. edge split on a hexagon turning
            # it into a 7-gon) and that must be treated as a bad new face too.
            new_faces = [f for f in copy.faces if self._face_key(f) not in old]
            return self._new_faces_are_bad(copy, new_faces)
        except Exception:
            return True
        finally:
            copy.free()

    @staticmethod
    def _face_key(f):
        return frozenset((round(v.co[0], 8), round(v.co[1], 8), round(v.co[2], 8))
                         for v in f.verts)

    # =========================================================================
    # Multi-Start Greedy — run N independent greedy passes, keep best
    # =========================================================================

    def _score_bmesh(self, bm, orig_quad_keys=None):
        nq = 0
        concave = 0
        dev = 0.0
        destroyed_orig = 0
        for f in bm.faces:
            if not f.is_valid:
                continue
            if len(f.verts) != 4:
                nq += 1
            else:
                if not MeshUtils.is_convex(f):
                    concave += 1
                dev += MeshUtils.angle90_deviation(f)
        if orig_quad_keys and self.w.original_quad_penalty_weight > 0.0:
            present = {self._face_key_rounded(f) for f in bm.faces
                       if f.is_valid and len(f.verts) == 4}
            destroyed_orig = len(orig_quad_keys - present)
        return (-nq * (POLYGON_REACHED_BONUS * self.w.polygon_bonus_weight)
                - concave * (POLYGON_REACHED_BONUS * self.w.adjacent_triangle_penalty_weight)
                - dev * self.w.quad_perfection_weight
                - destroyed_orig * self.w.original_quad_penalty_weight)

    @staticmethod
    def _pick_randomized(bm, faces, rng, top_k=3, weights=None):
        by_side = {}
        for f in faces:
            by_side.setdefault(len(f.verts), []).append(f)
        for n in sorted(by_side.keys()):
            if n in SOLVERS:
                pool = by_side[n]
                if weights is not None and weights.area_penalty_weight > 0.0:
                    max_area = max(f.calc_area() for f in pool) or 1.0
                else:
                    max_area = 1.0
                pool.sort(key=lambda f, _max=max_area, _w=weights: (
                    min(abs(math.degrees(loop.calc_angle()) - 90)
                        for loop in f.loops) if f.loops else 0
                    + (_w.area_penalty_weight * (1.0 - f.calc_area() / _max)
                       if _w is not None and _w.area_penalty_weight > 0.0 else 0.0),
                ))
                candidates = pool[:top_k]
                if not candidates:
                    continue
                weights = [top_k - i for i in range(len(candidates))]
                return rng.choices(candidates, weights=weights)[0], n
        return None, 0

    def multi_start_greedy(self, rng_seed=0, num_runs=8, top_k=3):
        rng = random.Random(rng_seed)
        me = self.obj.data
        orig_faces = len(me.polygons)
        orig_quad_keys = self._orig_quad_keys_from_mesh(me)

        best_bm = None
        best_score = float('-inf')
        best_stats = None

        for run in range(num_runs):
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            for f in bm.faces:
                f.tag = False

            clayer = bm.faces.layers.int.new(CENTER_LAYER_NAME)
            for f in bm.faces:
                f[clayer] = 0

            self._preprocess_concave(bm)

            solved = 0
            failed = 0
            unsupported = 0
            remaining = {}
            failed_sigs = set()
            iteration = 0

            while True:
                if self.max_iterations > 0 and iteration >= self.max_iterations:
                    for f in bm.faces:
                        if len(f.verts) != 4:
                            remaining[len(f.verts)] = remaining.get(len(f.verts), 0) + 1
                    break
                iteration += 1

                polygons = [f for f in bm.faces
                            if not f.tag and len(f.verts) != 4
                            and (id(f), len(f.verts)) not in failed_sigs
                            and f.calc_area() >= self.min_area]
                if not polygons:
                    break

                face, n_sides = self._pick_randomized(bm, polygons, rng, top_k, self.w)
                if face is None:
                    for f in polygons:
                        remaining[len(f.verts)] = remaining.get(len(f.verts), 0) + 1
                    break

                solver_cls = SOLVERS.get(n_sides)
                if solver_cls is None:
                    unsupported += 1
                    failed_sigs.add((id(face), n_sides))
                else:
                    solver = solver_cls()
                    candidates = solver.solve(bm, face, self.w, orig_quad_keys)
                    if not candidates:
                        failed += 1
                        failed_sigs.add((id(face), n_sides))
                    else:
                        best = self._first_valid_candidate(bm, candidates)
                        if best is None:
                            failed += 1
                            failed_sigs.add((id(face), n_sides))
                        else:
                            affected = TopologyApplier.apply(bm, best.operations)
                            if self.max_relax > 0:
                                MeshUtils.relax_faces(
                                    bm, affected, self.max_relax,
                                    collinear_angle=self.collinear_angle,
                                    push_factor=self.push_factor,
                                    reflex_lerp=self.reflex_lerp,
                                    max_edge_count=self.max_edge_count)
                            bm.faces.index_update()
                            solved += 1
                            failed_sigs.clear()

                for f in bm.faces:
                    n_side = len(f.verts)
                    f.tag = (n_side == 4 or n_side not in SOLVERS)

            score = self._score_bmesh(bm, orig_quad_keys)
            if score > best_score:
                if best_bm is not None:
                    best_bm.free()
                best_bm = bm
                best_score = score
                best_stats = {
                    'solved': solved, 'failed': failed,
                    'unsupported': unsupported, 'remaining': remaining,
                    'final_faces': len(bm.faces),
                }
            else:
                bm.free()

        stats = {'solved': 0, 'failed': 0, 'unsupported': 0, 'remaining': {},
                 'orig_faces': orig_faces, 'final_faces': 0}
        if best_bm is not None:
            MeshUtils.fix_concave_quads(best_bm)
            remaining = {}
            for f in best_bm.faces:
                n = len(f.verts)
                if n != 4:
                    remaining[n] = remaining.get(n, 0) + 1
            best_bm.to_mesh(me)
            me.update()
            stats.update(best_stats)
            stats['orig_faces'] = orig_faces
            stats['remaining'] = remaining
            stats['final_faces'] = len(best_bm.faces)
            best_bm.free()
        return stats

    # =========================================================================
    # Beam Search — explore K global solutions in parallel
    # =========================================================================

    def beams(self, beam_width=5, max_candidates=3):
        _w = self.w
        me = self.obj.data
        orig_faces = len(me.polygons)
        orig_quad_keys = self._orig_quad_keys_from_mesh(me)
        bm_root = bmesh.new()
        bm_root.from_mesh(me)
        bm_root.verts.ensure_lookup_table()
        bm_root.edges.ensure_lookup_table()
        bm_root.faces.ensure_lookup_table()
        clayer = bm_root.faces.layers.int.new(CENTER_LAYER_NAME)
        for f in bm_root.faces:
            f[clayer] = 0

        self._preprocess_concave(bm_root)

        class _BeamState:
            __slots__ = ('bm', 'op_seq', 'failed_sigs', 'dead', 'w')
            def __init__(self, bm, op_seq=None, failed_sigs=None):
                self.bm = bm
                self.op_seq = op_seq or []
                self.failed_sigs = failed_sigs or set()
                self.dead = False
                self.w = _w

            def score(self):
                nq = 0
                concave = 0
                dev = 0.0
                for f in self.bm.faces:
                    if not f.is_valid:
                        continue
                    if len(f.verts) != 4:
                        nq += 1
                    else:
                        if not MeshUtils.is_convex(f):
                            concave += 1
                        dev += MeshUtils.angle90_deviation(f)
                # non-quad dominates, then concave, then angle quality
                return (-nq * (POLYGON_REACHED_BONUS * self.w.polygon_bonus_weight)
                        - concave * (POLYGON_REACHED_BONUS * self.w.adjacent_triangle_penalty_weight)
                        - dev * self.w.quad_perfection_weight)

            def clone(self):
                nb = self.bm.copy()
                nb.verts.ensure_lookup_table()
                nb.edges.ensure_lookup_table()
                nb.faces.ensure_lookup_table()
                return _BeamState(nb, list(self.op_seq), set(self.failed_sigs))

            def free(self):
                self.bm.free()

        def _reset_tags(bm):
            for f in bm.faces:
                n = len(f.verts)
                f.tag = (n == 4 or n not in SOLVERS)

        def _find_untagged(bm, failed_sigs):
            return [f for f in bm.faces
                    if f.is_valid and not f.tag and len(f.verts) != 4
                    and (id(f), len(f.verts)) not in failed_sigs
                    and f.calc_area() >= self.min_area]

        states = [_BeamState(bm_root)]
        best_all_quads = None
        iteration = 0

        while states and iteration < self.max_iterations:
            iteration += 1
            new_states = []

            for st in states:
                if st.dead:
                    continue
                bm = st.bm
                _reset_tags(bm)
                polygons = _find_untagged(bm, st.failed_sigs)

                if not polygons:
                    if best_all_quads is None or st.score() > best_all_quads.score():
                        best_all_quads = st.clone()
                    continue

                # Pick top-K faces to create divergence
                face_pool = self._pick_top_faces(bm, polygons, max_candidates, self.w)
                if not face_pool:
                    st.dead = True
                    new_states.append(st)
                    continue

                _had_child = False
                for face, n_sides in face_pool:
                    solver_cls = SOLVERS.get(n_sides)
                    if solver_cls is None:
                        continue
                    solver = solver_cls()
                    candidates = solver.solve(bm, face, self.w, orig_quad_keys)
                    if not candidates or candidates[0].score == float('-inf'):
                        continue
                    count = 0
                    for c in candidates:
                        if count >= max_candidates:
                            break
                        child = st.clone()
                        idx_ops = TopologyApplier._ops_to_indices(c.operations)
                        try:
                            ops_resolved = TopologyApplier._resolve_ops(child.bm, idx_ops)
                            before = {self._face_key(f) for f in child.bm.faces}
                            affected = TopologyApplier.apply(child.bm, ops_resolved)
                            child.bm.faces.ensure_lookup_table()
                            # Keyed by vertex coordinates, not wrapper identity:
                            # an op may grow an existing face into a 7+ gon.
                            new_faces = [f for f in child.bm.faces
                                         if self._face_key(f) not in before]
                            if self.max_relax > 0:
                                MeshUtils.relax_faces(
                                    child.bm, affected, self.max_relax,
                                    collinear_angle=self.collinear_angle,
                                    push_factor=self.push_factor,
                                    reflex_lerp=self.reflex_lerp,
                                    max_edge_count=self.max_edge_count)
                            child.bm.faces.ensure_lookup_table()
                            child.bm.normal_update()
                            if self._new_faces_are_bad(child.bm, new_faces):
                                child.free()
                                continue
                            child.op_seq.append(idx_ops)
                            new_states.append(child)
                            _had_child = True
                            count += 1
                        except Exception:
                            child.free()
                            continue
                # if no child was produced for this state, mark dead
                if not _had_child:
                    st.dead = True
                    new_states.append(st)

            new_states.sort(key=lambda s: s.score(), reverse=True)
            for st in new_states[beam_width:]:
                st.free()
            states = new_states[:beam_width]

            # Check for finished
            for st in states:
                _reset_tags(st.bm)
                if not _find_untagged(st.bm, st.failed_sigs):
                    if best_all_quads is None or st.score() > best_all_quads.score():
                        best_all_quads = st.clone()

        final = best_all_quads if best_all_quads else states[0]

        stats = {'solved': len(final.op_seq), 'failed': 0, 'unsupported': 0, 'remaining': {},
                 'orig_faces': orig_faces, 'final_faces': len(final.bm.faces)}
        MeshUtils.fix_concave_quads(final.bm)
        remaining = {}
        for f in final.bm.faces:
            if f.is_valid and len(f.verts) != 4:
                remaining[len(f.verts)] = remaining.get(len(f.verts), 0) + 1
        stats['remaining'] = remaining
        stats['final_faces'] = len(final.bm.faces)
        final.bm.to_mesh(me)
        me.update()
        final.bm.free()

        for st in states:
            if st is not final:
                st.free()

        return stats

# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------

class QuadrangulationProperties(bpy.types.PropertyGroup):
    seed: bpy.props.IntProperty(
        name="Seed", description="Random seed for deterministic results (0 = use fixed seed)",
        default=DEFAULT_SEED, min=0, max=2147483647)
    topology_strength: bpy.props.FloatProperty(
        name="Structure",
        description="Prefers a clean quad flow: short loops, no branches, few adjacent "
                    "triangles, avoids poking faces (center-vertex fallbacks), especially "
                    "nested ones. 0.5 = default, 0 = ignore, 1 = maximize",
        default=DEFAULT_TOPOLOGY_STRENGTH, min=0.0, max=1.0)
    shape_strength: bpy.props.FloatProperty(
        name="Shape",
        description="Prefers well-formed faces: right-angle quads, even edge lengths, "
                    "large faces cut first. 0.5 = default, 0 = ignore, 1 = maximize",
        default=DEFAULT_SHAPE_STRENGTH, min=0.0, max=1.0)
    max_loop_length: bpy.props.IntProperty(
        name="Max Loop Length",
        description="Maximum quad loop length (0 = no limit)",
        default=DEFAULT_MAX_LOOP_LENGTH, min=0, max=200)
    max_branch_offs: bpy.props.IntProperty(
        name="Max Branch-Offs",
        description="Maximum branch-offs per quad loop branch",
        default=DEFAULT_MAX_BRANCH_OFFS, min=0, max=10)
    max_relax_iterations: bpy.props.IntProperty(
        name="Max Relax Iterations",
        description="Maximum convexity relaxation iterations per face",
        default=DEFAULT_MAX_RELAX_ITERATIONS, min=0, max=100)
    relax_max_edge_count: bpy.props.IntProperty(
        name="Relax Max Edge Count",
        description="Skip vertices with more than this many linked edges during relaxation (0=disabled)",
        default=DEFAULT_RELAX_MAX_EDGE_COUNT, min=0, max=50)
    relax_collinear_angle: bpy.props.FloatProperty(
        name="Collinear Angle",
        description="Angle threshold (degrees) for collinear vertex detection",
        default=DEFAULT_RELAX_COLLINEAR_ANGLE, min=90.0, max=180.0)
    relax_push_factor: bpy.props.FloatProperty(
        name="Push Factor",
        description="Fraction of edge length for collinear push",
        default=DEFAULT_RELAX_PUSH_FACTOR, min=0.0, max=1.0)
    relax_reflex_lerp: bpy.props.FloatProperty(
        name="Reflex Lerp",
        description="Interpolation factor toward centroid for reflex vertices",
        default=DEFAULT_RELAX_REFLEX_LERP, min=0.0, max=1.0)
    num_runs: bpy.props.IntProperty(
        name="Search Runs",
        description="Number of greedy passes (higher = more thorough but slower)",
        default=8, min=1, max=200)
    min_area: bpy.props.FloatProperty(
        name="Min Area",
        description="Minimum face area (Blender units²) to attempt cutting (hard limit)",
        default=DEFAULT_MIN_AREA, min=0.0, max=0.01, precision=6)


# -----------------------------------------------------------------------------
# Operator
# -----------------------------------------------------------------------------

class MESH_OT_Quadrangulate(bpy.types.Operator):
    bl_idname = "mesh.quadrangulate"
    bl_label = "Quadrangulate"
    bl_description = "Convert non-quad faces to quads"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode in {'OBJECT', 'EDIT'}

    def execute(self, context):
        obj = context.active_object
        props = context.scene.quadrangulation_props

        w = ScoreWeights(props)

        was_edit = (obj.mode == 'EDIT')
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')

        engine = QuadrangulationEngine(
            obj, w,
            max_length=props.max_loop_length if props.max_loop_length > 0 else 999999,
            max_branch_offs=props.max_branch_offs,
            max_relax=props.max_relax_iterations,
            min_area=props.min_area,
            collinear_angle=props.relax_collinear_angle,
            push_factor=props.relax_push_factor,
            reflex_lerp=props.relax_reflex_lerp,
            relax_max_edge_count=props.relax_max_edge_count,
        )
        stats = engine.multi_start_greedy(rng_seed=props.seed, num_runs=props.num_runs)

        if was_edit:
            bpy.ops.object.mode_set(mode='EDIT')

        self._report_stats(context, stats)
        return {'FINISHED'}

    def _report_stats(self, context, stats):
        parts = []
        if 'orig_faces' in stats:
            parts.append(f"Faces: {stats['orig_faces']}→{stats['final_faces']}")
        if stats['solved']:
            parts.append(f"Solved: {stats['solved']}")
        if stats['failed']:
            parts.append(f"Skipped: {stats['failed']}")
        if stats['unsupported']:
            parts.append(f"Unsupported: {stats['unsupported']}")
        if stats['remaining']:
            for n, count in sorted(stats['remaining'].items()):
                parts.append(f"{count}x {n}-gons left")
        elif stats['solved']:
            parts.append("All quads")
        else:
            parts.append("Nothing to do — mesh is already all quads")
        self.report({'INFO'}, " | ".join(parts))

# -----------------------------------------------------------------------------
# Panel
# -----------------------------------------------------------------------------

class MESH_PT_Quadrangulate(bpy.types.Panel):
    bl_idname = "MESH_PT_Quadrangulate"
    bl_label = "Quadrangulation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Edit"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        p = context.scene.quadrangulation_props

        box = layout.box()
        row = box.split(factor=0.7)
        row.operator("mesh.quadrangulate")
        row.operator("mesh.quadrangulate_reset", text="Reset")
        box.prop(p, "seed")

        box = layout.box()
        box.label(text="Weights")
        box.prop(p, "topology_strength")
        box.prop(p, "shape_strength")

        box = layout.box()
        box.label(text="Search")
        box.prop(p, "num_runs")
        box.prop(p, "min_area")
        box.prop(p, "max_loop_length")
        box.prop(p, "max_branch_offs")
        box.prop(p, "max_relax_iterations")

        box = layout.box()
        box.label(text="Relax")
        box.prop(p, "relax_collinear_angle")
        box.prop(p, "relax_push_factor")
        box.prop(p, "relax_reflex_lerp")
        box.prop(p, "relax_max_edge_count")

class MESH_OT_QuadrangulateReset(bpy.types.Operator):
    """Reset Quadrangulation Parameters"""
    bl_idname = "mesh.quadrangulate_reset"
    bl_label = "Reset"
    bl_description = "Reset all parameters to factory defaults"

    def execute(self, context):
        props = context.scene.quadrangulation_props
        props.seed = DEFAULT_SEED
        props.num_runs = 8
        props.topology_strength = DEFAULT_TOPOLOGY_STRENGTH
        props.shape_strength = DEFAULT_SHAPE_STRENGTH
        props.max_loop_length = DEFAULT_MAX_LOOP_LENGTH
        props.max_branch_offs = DEFAULT_MAX_BRANCH_OFFS
        props.max_relax_iterations = DEFAULT_MAX_RELAX_ITERATIONS
        props.relax_collinear_angle = DEFAULT_RELAX_COLLINEAR_ANGLE
        props.relax_push_factor = DEFAULT_RELAX_PUSH_FACTOR
        props.relax_reflex_lerp = DEFAULT_RELAX_REFLEX_LERP
        props.relax_max_edge_count = DEFAULT_RELAX_MAX_EDGE_COUNT
        props.min_area = DEFAULT_MIN_AREA
        return {'FINISHED'}

# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

CLASSES = (
    QuadrangulationProperties,
    MESH_OT_Quadrangulate,
    MESH_OT_QuadrangulateReset,
    MESH_PT_Quadrangulate,
)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.quadrangulation_props = bpy.props.PointerProperty(
        type=QuadrangulationProperties)

def unregister():
    del bpy.types.Scene.quadrangulation_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
