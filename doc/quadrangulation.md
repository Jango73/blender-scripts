# Mesh Quadrangulation Algorithm (Poly-to-Quad)

## 1. Goal

Convert every face of a mesh into quads. Throughout this document, a
**polygon** refers to any face that is **not** a quad (triangle, pentagon,
hexagon, N-gon). Existing quads are never processing targets themselves,
but may be affected (cut) as a side effect of a solution.

## 2. Vocabulary

| Term | Definition |
|---|---|
| **Polygon** | A mesh face with a side count ≠ 4. |
| **Quad loop** | A chain of consecutive quads connected through opposite edges. Enter a quad through one edge, exit through its opposite edge, thereby entering the next quad. |
| **Solution tree** | The set of candidate solutions for solving *one* given polygon, organized as a tree (each branch = a structuring choice, e.g. which edge, which cut). |
| **Score** | A numeric value assigned to a candidate solution, used to compare branches of the tree. |
| **Sub-score** | A component of the score, computed independently and then combined (e.g. loop length, angle perfection, bonus, penalty). |
| **Solver** | The module responsible for generating candidate solutions for a given polygon type (Triangle Solver, Pentagon Solver, Hexagon Solver, ...). |

### 2.1 Underlying Mesh Representation

The algorithm assumes the same mesh representation as Blender's BMesh
(3.x and above): `BMVert`, `BMEdge`, `BMFace`, and `BMLoop`, where each
face stores an ordered cycle of `BMLoop` elements (one per edge/vertex
pair around the face), each loop linking to the next/previous loop around
its face and to the radial loop on the opposite side of its edge.

Using this representation, the vocabulary defined above maps directly onto
BMesh navigation:
- **Opposite edge in a quad**: for a `BMLoop` `entryLoop` sitting on the
  entry edge, the opposite edge's loop is
  `entryLoop.link_loop_next.link_loop_next` (2 hops forward around the
  quad's 4-loop cycle).
- **Adjacent edges in a quad**: `entryLoop.link_loop_next` (next edge) and
  `entryLoop.link_loop_prev` (previous edge) — there are always **two**
  adjacent edges to any entry edge in a quad, not one (see §5.2).
- **Face on the other side of an edge**: reached through the edge's radial
  loop (`loop.link_loop_radial_next`), giving access to the neighboring
  face and its own loop cycle to continue traversal.
- **Edge shared by more than 2 faces (non-manifold, §9.4)**: detected
  directly from the edge's radial loop cycle having more than 2 entries.

This mapping removes the need to redefine loop-walking utilities from
scratch: `next` / `prev` / `radial` navigation directly matches the
"opposite edge" / "adjacent edge" / "neighboring face" vocabulary used
throughout this document.

## 3. General Architecture

```
While at least one polygon remains in the mesh:
    1. Select the polygon to process (see §3.1 — processing order)
    2. Build the solution tree FOR THIS POLYGON ONLY
    3. Score every candidate solution (leaf of the tree)
    4. Select the solution with the best score
    5. Apply the solution (topological modification of the mesh)
    6. Start over (since the topology changed, any previous tree is invalid)
```

Key point explicitly required: the tree is **never** built for all
polygons of the mesh at once. Every applied solution modifies the local
topology (and sometimes further, via cut quad loops), so trees must be
rebuilt polygon by polygon, on the fly.

### 3.1 Polygon Processing Order

**Rule adopted**: process polygons in increasing side-count order
(triangles first, then pentagons, then hexagons, then N-gons). Within the
same type, prioritize the polygon whose best solution has the highest
score (the "easy/winning" cases first).

Rationale: triangles are the only ones that can generate the "polygon
reached" bonus at the end of a quad loop (§5.3), which has the strongest
impact on the score. Processing them first maximizes the chance of
chaining these bonuses before the surrounding topology gets modified by
the resolution of other polygons. Processing pentagons or hexagons first
would risk "consuming" configurations that could have been exploited by a
neighboring triangle.

### 3.2 Modularity

Each polygon type is handled by an independent solver, following a common
interface:

```
Solver(polygon, mesh) -> List[SolutionCandidate]
```

Each `SolutionCandidate` exposes:
- the list of topological operations to apply (vertex insertion, cut, etc.)
- its total score
- the breakdown of its sub-scores (for debugging / tuning)

A registry maps `side count -> Solver`, allowing new solvers (7-gon,
8-gon, ...) to be added without touching the rest of the algorithm. Any
polygon whose side count has no dedicated solver in the registry is simply
left untouched (see §8).

### 3.3 Post-Application Convexity Relaxation

No solver (§5, §6, §7, or any future N-gon solver) takes convexity into
account when generating or scoring candidate solutions: cuts are proposed
and applied purely based on side count and the scoring rules of §4,
regardless of whether the polygon being solved, or the resulting faces,
are convex or concave.

Instead, convexity is handled as a **generic post-processing step**,
applied right after step 5 of the main loop (§3) for every face whose
vertex set was affected by the applied solution (a newly inserted vertex,
or an existing vertex reused in a new cut):

1. Check each affected face for **collinearity** (internal angle ≥ 175°,
   edge nearly flat) and **concavity** (reflex vertex > 180°).
2. For a **collinear** vertex:
   - Compute a push direction perpendicular to the edge formed by the
     two neighboring vertices (`edge_dir × face.normal`), pointing
     outward (convex bump).
   - Move the vertex by a small fraction of the shortest incident edge
     length in that direction.
   For a **reflex (concave)** vertex:
   - Move the vertex toward the face's centroid
     (`lerp(v.co, centroid, 0.5)`).
3. Repeat steps 1–2 iteratively until no vertex exceeds 175° nor
   remains reflex, or a maximum iteration count `maxRelaxIterations`
   (tweakable parameter, same safeguard pattern as `maxLoopLength`,
   §9.5) is reached.

This mechanism is intentionally simple and treated as a **first pass,
expected to be refined later** — it is not tied to any specific solver and
does not need to be revisited when new N-gon solvers are added.

### 3.4 Global Invariant: No Solution May Create an Unsolvable Polygon

No candidate solution, from any solver (§3.2), may ever produce a face
whose side count has no solver registered for it. This is a **hard
constraint on solution-tree construction itself**, not merely a scoring
penalty: a branch that would violate it must never be generated as a
valid candidate in the first place — it is not filtered out afterward by
a bad score, it simply cannot exist in the tree.

This principle is the general rule behind two specific cases already
described elsewhere in this document, both of which are instances of it
rather than separate rules:

- The Triangle Solver's quad loop may not terminate on an existing
  hexagon (§5.2), since that would turn it into an unsolvable 7-gon.
- Edges belonging to any polygon with no registered solver are excluded
  from every candidate, in every solver, for the same reason (§9.4).

Any future solver added to the registry (7-gon, 8-gon, ...) must uphold
this invariant itself when generating its own candidate solutions — e.g. a
hypothetical 7-gon solver must never propose a cut that would leave a
residual face with a side count that has no registered solver at the time
it runs.

## 4. Scoring System

Every candidate solution receives a total score, a combination of
sub-scores. The spec defines the following sub-scores (non-fixed,
extensible list):

| Sub-score | Applies to | Effect |
|---|---|---|
| Length of the cut quad loop | Triangle | The longer the loop, the worse the score (increasing penalty) |
| "Polygon reached" bonus | Triangle | Large bonus if the loop terminates on a triangle or pentagon (solves 2 polygons in one operation) |
| "Adjacent triangle-triangle" penalty | Triangle | Malus if the chosen edge is shared by two triangles (visually poor result), but the solution remains valid if it is the only one available |
| Perfection of generated quads | All types except cut-loop quads | Malus proportional to how far the internal angles deviate from 90° |

**Weighting between sub-scores.** These weights are not hard-coded: they
are exposed as **UI-tweakable parameters**, letting the user adjust them
on the fly without recompiling or modifying code. The spec imposes no
default values; they will need to be calibrated empirically depending on
the meshes being processed. Concretely, each solver exposes its own named
weights (e.g. `loopLengthWeight`, `polygonBonusWeight`,
`adjacentTrianglePenaltyWeight`, `quadPerfectionWeight`,
`trianglePerfectionWeight`), grouped in a common parameter panel.

## 5. Solver: Triangle → Quad

### 5.1 Principle

A vertex is inserted at the midpoint of one of the triangle's 3 edges.
This directly turns the triangle into a quad (3 vertices + 1 new = 4).
Since the chosen edge is shared with a neighboring face (presumably a
quad, as the mesh is already largely quadrangulated), this new vertex also
"breaks" that neighboring quad, which must be re-cut into two quads to
remain valid — this initiates the traversal of a **quad loop**.

### 5.2 Solution Tree Generation

For each edge of the triangle (3 root branches):
1. Enter the quad loop from this edge.
2. Walk the loop quad by quad (entry edge → opposite edge → next quad),
   incrementing a length counter.
3. At each traversed quad, **three** choices are possible (tree branches —
   a quad has exactly one opposite edge and two adjacent edges relative to
   its entry edge, see §2.1):
   - **Continue straight**: exit through the opposite edge, continue the
     loop.
   - **Branch off (left or right)**: exit through one of the two adjacent
     edges instead of the opposite one. This is **not** a termination — it
     is a routing option, evaluated only in the context of searching for
     the shortest path from the current triangle to a target odd-sided
     polygon (3/5/7/9-gon, ...) not yet processed. It is worth taking only
     when it shortens or enables reaching such a target that continuing
     straight would not reach. The quad thus traversed diagonally (4
     original vertices + entry vertex + exit vertex on the chosen adjacent
     edge) becomes a **pass-through hexagon**: the Hexagon Solver (§7) is
     invoked directly on it — for a hexagon there is no loop search to
     perform, the solver *is* the cut into 3 quads, so there is nothing
     else left to resolve afterward. The loop then **continues** its
     traversal beyond it, starting from the new exit edge.
4. The loop terminates (leaf node) in one of the following cases:
   - It reaches an edge belonging to an existing triangle or pentagon
     (**strong bonus**, solves 2 polygons — see §10.4). Reaching an
     existing hexagon is deliberately **not** included here: adding a
     vertex on a hexagon's edge would turn it into a 7-gon, which has no
     solver (§8) and would be left as an unresolved leftover — the
     opposite of a bonus. More generally, an edge belonging to any
     polygon with no solver in the registry is never a valid termination
     (or a valid edge to traverse at all) — see §9.4.
   - It reaches a mesh boundary (neutral termination, see §9.2).
   - It loops back on itself (neutral termination, see §9.3).
   - **It reaches the originating triangle on a different edge (fractal
     rejection, see §5.4)**.

### 5.3 Leaf Score Computation

```
score = - loopLengthWeight * loopLength
        + polygonBonusWeight * (bonus if terminating on a polygon)
        - adjacentTrianglePenaltyWeight * (1 if chosen edge is shared by 2 triangles)
        - perfectionWeight * sum(angle90Deviation(quad) for each pass-through
                              hexagon crossed via branching, once cut by
                              the Hexagon Solver, §7)
```

The perfection score does **not** apply to ordinary quads of a straight-cut
quad loop (explicitly specified in the requirements). It does apply,
however, to pass-through hexagons resulting from a branch-off: the Hexagon
Solver (§7) deterministically yields exactly 3 quads, and their perfection
(using the same formula as §7.3) is computed the same way and integrated
into the overall score of the triangle solution.

## 6. Solver: Pentagon → Quad

### 6.1 Principle

A cut (diagonal edge) is made from one vertex of the pentagon to a
non-adjacent one, producing a quad + a triangle. The resulting triangle is
not resolved here; it will be handled in a later pass as a full-fledged
polygon. This applies identically whether the pentagon is convex or
concave — convexity is not considered here, it is handled separately as a
generic post-processing step (§3.3).

### 6.2 Solution Tree Generation

A pentagon has 5 vertices; the valid (non-adjacent) cuts number 5 (each
vertex to the vertex "2 steps away"). Each constitutes a branch/leaf of
the tree (no further sub-tree here, unlike the triangle case).

### 6.3 Score Computation

The score accounts for the perfection of **both** faces produced by the cut:
the quad and the residual triangle.

- **Quad perfection**: as with other solvers, the deviation of the 4 internal
  angles from 90°.
- **Triangle perfection**: a triangle is considered "perfect" when it is
  **equilateral**. The chosen measure is the deviation between the lengths
  of the 3 sides (equivalently, the deviation between the 3 internal
  angles) — the more the sides differ from one another, the less
  perfect the triangle. An equilateral triangle (all 3 sides equal)
  receives the maximum score.

```
score = -quadPerfectionWeight * angle90Deviation(resultingQuad)
        -trianglePerfectionWeight * equilateralDeviation(resultingTriangle)
```

*Open point*: the relative weighting between `quadPerfectionWeight` and
`trianglePerfectionWeight` is exposed as a UI parameter (see §4, point 2,
resolved) — no imposed value, empirical calibration.

## 7. Solver: Hexagon → Quad

### 7.1 Principle

A center vertex is created (the hexagon's centroid), then connected to 3
alternating vertices, producing 3 quads. Two alternating cut patterns are
possible:

- Cuts center→V0, center→V2, center→V4
- Cuts center→V1, center→V3, center→V5

The center vertex is always placed at the **centroid** of the polygon's
vertices (here, the hexagon's 6 vertices — see §10.6), with no adjustment
or projection. This placement rule is general: it will apply the same way
to any future N-gon solver based on a center vertex (§8). As with the
Pentagon Solver, convexity of the hexagon (or of the resulting quads) is
not considered here — it is handled separately as a generic
post-processing step (§3.3).

### 7.2 Solution Tree Generation

A 2-branch tree (one per alternating cut pattern), each a direct leaf.

### 7.3 Score Computation

```
score = -perfectionWeight * sum(angle90Deviation(quad) for each generated quad)
```

## 8. Polygons Without a Dedicated Solver (N-gon, 7+)

The spec explicitly states that other solutions will exist for 7-gons and
beyond, and that the algorithm must be able to integrate them without a
rewrite (via the `side count -> Solver` registry, §3.2).

**Rule adopted for missing solvers**: any polygon whose side count has no
associated solver in the registry is **left untouched**, with no generic
resolution attempt. It is never selected during the "next polygon to
process" step (§3.1) and generates no error — it simply remains present in
the final mesh until a dedicated solver is added for its side count.

## 9. Quad Loop Traversal — Details and Unspecified Cases

### 9.1 Basic Mechanics

Enter a quad through one edge, exit through the opposite edge (or branch
off, §5.2), inserting at each step the vertices needed to cut every
traversed quad into two clean quads once the whole loop is resolved.

### 9.2 Termination at a Mesh Boundary

If the quad loop reaches a mesh boundary (edge with no neighboring face)
without having crossed a polygon or looped back on itself, this is a
**neutral termination**: the solution remains valid and is included
normally as a leaf of the tree. It only receives the usual length penalty
(§5.3), without the "polygon reached" bonus (since none was crossed). This
is never a branch to exclude from the tree.

### 9.3 Loop Closing Back on Itself

While traversing a quad loop, the list of edges already visited in the
current branch is kept. If the traversal falls back on an already-visited
edge (or the starting edge), this is an **immediate, valid termination**
(leaf of the tree): the loop is closed, with no risk of infinite
exploration. This case can never yield the "polygon reached" bonus
(§5.3), since no external polygon was crossed — only the length penalty
applies.

### 9.4 Excluded Edges: Non-Manifold and Solver-less Polygons

Two kinds of edges are **excluded from the candidates** for cutting: they
can never be chosen as the starting edge for a triangle (§5.2), nor
traversed or reached while walking a quad loop (§9.1).

- **Non-manifold edges**: an edge shared by more than 2 faces. These
  edges are intentionally left untouched by the algorithm, with no error
  or warning — this kind of configuration is rare but can be intentional
  (e.g. seams/hems on garment meshes).
- **Edges belonging to a polygon with no solver in the registry** (any
  N-gon with no dedicated solver, §8): inserting a vertex there would
  change that polygon's side count without a solver able to resolve it
  (e.g. turning a 7-gon into an 8-gon, or a hexagon into a 7-gon), leaving
  an unresolved leftover instead of progress. Such edges are therefore
  never valid, whether as a starting edge, a mid-loop traversal edge, or a
  termination target.

### 9.5 Anti-Combinatorial-Explosion Bounds

Two complementary, cumulative safeguards, to avoid excessive branching
(large meshes, high-valence areas/poles):

- **Maximum loop length** (`maxLoopLength`, tweakable parameter): beyond
  this length, the branch is simply **dropped** (pruned from the tree)
  without being scored — it would be unfavorable anyway due to the length
  penalty. A value of `0` is a special convention meaning **no cap**: the
  loop is allowed to keep cutting straight for as long as needed, until it
  simply can no longer continue (e.g. it reaches a mesh boundary, §9.2).
- **Maximum number of branch-offs per branch** (`maxBranchOffsPerBranch`,
  tweakable parameter, typical value 1 or 2): each branch-off (§5.2)
  adds two extra candidate branches to explore at that quad, which can
  combinatorially explode in high-valence areas. This bound limits the
  number of branch-offs allowed per branch.

### 9.6 Search Algorithm

Even though the mesh can have tens of thousands of polygons, the search
performed for a single triangle stays **local and bounded** by
`maxLoopLength` / `maxBranchOffsPerBranch` (§9.5) — the total mesh size has
no direct impact on the cost of a single search. What matters is the
efficiency of that local, bounded search itself.

**Recommended approach: best-first search with branch-and-bound
pruning**, rather than plain DFS or BFS:

- Candidate branches are explored from a priority queue ordered by their
  current partial score (best partial score first).
- Since the length penalty (§5.3) grows monotonically with every quad
  traversed, a branch whose partial score can no longer exceed the best
  full solution found so far is **pruned immediately** without further
  exploration.
- The search can **stop early** as soon as a leaf achieves the "polygon
  reached" bonus with a good length — no need to keep exploring branches
  that provably cannot score better.

This is more efficient than plain DFS (which explores irrelevant deep
branches before backtracking) or plain BFS (which explores all branches
level by level regardless of how promising they are), and it scales well
because the search cost per polygon is bounded independently of overall
mesh size — the total processing cost of the algorithm is therefore
roughly `numberOfPolygonsToProcess * boundedLocalSearchCost`, not tied to
total mesh size directly.

## 10. Formula Reference

This section formalizes every named quantity used in the scoring formulas
throughout this document.

### 10.1 `angle90Deviation(quad)`

Measures how far a quad is from a perfect square/rectangle (all internal
angles at 90°). For a quad with internal angles `angle1, angle2, angle3,
angle4` (in degrees):

```
angle90Deviation(quad) = sum(|angle_i - 90| for angle_i in [angle1, angle2, angle3, angle4])
```

Lower is better; `0` means a perfect rectangle. This value is unbounded
above (a very degenerate quad can have an arbitrarily large deviation).

### 10.2 `equilateralDeviation(triangle)`

Measures how far a triangle is from being equilateral. For a triangle
with side lengths `sideA, sideB, sideC`:

```
equilateralDeviation(triangle) = max(|sideA - sideB|, |sideB - sideC|, |sideA - sideC|)
                                  / (sideA + sideB + sideC)
```

The division by the perimeter makes the measure scale-invariant (a tiny
and a huge equilateral triangle score the same). The `max` (rather than
`min`) is used deliberately: an equilateral triangle requires **all
three** sides to be close in length, so the worst (largest) pairwise
difference is what should drive the score down. Lower is better; `0`
means all 3 sides are exactly equal.

### 10.3 `loopLength`

The number of quads traversed by a quad loop between its entry edge (on
the polygon being solved) and its termination leaf (polygon reached, mesh
boundary, or self-closing loop — §9.2, §9.3). Counted as an integer number
of quads, not edges or vertices.

### 10.4 Polygon-reached bonus

A fixed constant value, added to the score only when a loop's termination
leaf is an existing triangle or pentagon (§5.2, case 1). `0` in every
other termination case.

### 10.5 Adjacent triangle-triangle penalty

A binary term: `1` if the edge chosen as the loop's entry edge is shared
by two triangles (§4), `0` otherwise.

### 10.6 Centroid (center vertex)

For any polygon with `n` vertices at positions `p1, ..., pn`, the centroid
used for hexagon center-vertex placement (§7.1, and any future N-gon
solver reusing the same rule) is the simple arithmetic mean:

```
centroid = (p1 + p2 + ... + pn) / n
```

No adjustment or projection is applied.

### 10.7 Branch-off count

An integer counter, incremented by 1 every time a branch-off (§5.2) is
taken while walking a given branch of the solution tree. Compared against
`maxBranchOffsPerBranch` (§9.5) to decide whether the branch-off option is
still available at a given quad.

## 11. Testing

### 11.1 Methodology

Tests are built by constructing a real mesh in the implementation
environment (BMesh, §2.1) and running the algorithm on it, then asserting
on the **resulting topology** directly (which edges got cut, how many
quads exist, which faces are connected through which loop, whether a
target face was reached) — not on internal solver return values in
isolation.

**Base mesh**: a flat N×N grid of quads (e.g. 10×10) is used as the
foundation for every test. Individual defects (a triangle, a pentagon, a
hexagon, a non-manifold edge, ...) are injected into this grid at chosen
positions by locally editing the topology (e.g. collapsing a diagonal
to turn one grid quad into two triangles, then deleting one; or merging
two adjacent quads' shared vertex to produce a pentagon at that spot).
This gives full control over: the distance (in quads) between defects,
whether a straight path or a turn is required to connect them, and
proximity to the mesh boundary.

**Weights**: since sub-score weights are UI parameters with no imposed
default (§4), tests that need an unambiguous "best" solution must fix an
explicit, documented set of weight values for that test (stated in the
test itself), rather than relying on whatever default happens to be
shipped. Tests that specifically target weight sensitivity (§11.4, W-series)
deliberately vary these values between runs.

### 11.2 Single-Polygon Recipes

| # | Recipe | Assertion |
|---|---|---|
| G1 | Grid with a single triangle injected on a boundary edge, positioned so one mesh edge is clearly closer than the others | The edge chosen for the vertex insertion is the one giving the shortest quad loop to the boundary (§5.2); resulting mesh is 100% quads |
| G2 | Triangle injected at a grid **corner** (shortest possible boundary distance in that direction) | The loop resolves in the minimum number of quads; verify it is shorter than any alternative edge on the same triangle |
| G3 | Pentagon injected in the middle of the grid, away from any other defect | One of the 5 possible cuts is applied, producing exactly 1 quad + 1 residual triangle (§6); the triangle is **not** resolved in this same run pass — verify it still exists as a triangle immediately after this polygon's solution is applied, before the next iteration of the main loop |
| G4 | Hexagon injected in the middle of the grid, shaped irregularly enough that the two alternating cut patterns give clearly different results | Exactly 3 quads result (§7); center vertex position equals the exact average of the 6 hexagon vertex positions (§10.6) |
| G5 | 7-gon injected in the middle of the grid, no solver registered for it, no other defect present | Running the full algorithm leaves the mesh unchanged: the 7-gon is still a 7-gon, no vertex was ever inserted on any of its edges (§8, §9.4) |

### 11.3 Two-Polygon Combination Recipes

| # | Recipe | Assertion |
|---|---|---|
| G6 | Two triangles injected on the grid, aligned so a straight quad strip of length *d* connects them | After running, both triangles are quads, and every one of the *d* quads that were between them is cut into two — verify the two triangles end up connected through a single continuous edge loop of new vertices |
| G7 | Two triangles positioned so no straight strip connects them, but an L-shaped path (one turn) does | The connecting loop takes the turn: verify a pass-through hexagon appears at the turning quad and is itself cut into exactly 3 quads (§5.2, §7), and that both original triangles still end up fully resolved into quads |
| G8 | One triangle and one pentagon connected by a straight quad strip | The pentagon's crossed edge receives a vertex, turning it into a hexagon that is immediately cut into 3 quads (§5.2); verify the final state has zero triangles, zero pentagons, and only quads along the whole path |
| G9 | One triangle and one hexagon, positioned so the *only* non-boundary path from the triangle would end on the hexagon's edge | Verify the hexagon's edges are never selected as the loop's target (§9.4): the algorithm instead terminates on the mesh boundary in some other direction (or leaves the triangle unresolved this pass if no other edge exists) |

### 11.4 Multi-Polygon Best-Solution Selection Recipes

| # | Recipe | Assertion |
|---|---|---|
| G10 | One starting triangle with 3 other untouched triangles placed at different quad-strip distances in different directions | With fixed test weights, verify the algorithm connects to the closest one that yields the best score — not an arbitrary reachable one, and not necessarily the geometrically nearest one if a longer path scores better under the fixed weights |
| G11 (weight sensitivity) | Grid with both a short boundary-terminated path and a longer path reaching a pentagon, from the same triangle | Run once with `polygonBonusWeight` high: the longer, pentagon-reaching path is chosen. Run again with `polygonBonusWeight` low/zero: the short boundary path is chosen instead — same mesh, different outcome purely from weight change (§4) |
| G12 | Grid with 10+ triangles scattered across it, some connectable to each other, some only to the boundary | Run the full main loop to completion; for each individual resolution, independently verify (by hand-computed expectation for that specific configuration) that the chosen solution matches the best-scoring one; verify the final mesh is 100% quads |
| G13 | Grid containing a mix of triangles, pentagons, hexagons, and one unsupported 7-gon | Run to completion; verify triangles were processed before pentagons, which were processed before hexagons (§3.1); verify the final mesh is all quads **except** the surviving 7-gon |

### 11.5 Degenerate / Excluded-Case Recipes

| # | Recipe | Assertion |
|---|---|---|
| G14 | Two triangles sharing one edge on the grid boundary, with no other viable edge reachable from either | Verify the shared edge is still used despite the penalty (§4, §10.5): the two triangles become two quads with two aligned edges, as expected for this "only option" case |
| G15 | Grid with a non-manifold edge (3+ faces sharing it) stitched in near a triangle, plus a normal alternative edge on the same triangle | Verify the non-manifold edge is never chosen; the triangle resolves through the alternative edge instead (§9.4) |
| G16 | Triangle whose only viable path exceeds a small test `maxLoopLength` before reaching a boundary or any target | With that small `maxLoopLength`: verify the branch is dropped and the triangle is left unresolved after this pass (§9.5). Re-run the identical mesh with `maxLoopLength = 0`: verify it now resolves via the long boundary-reaching loop |
| G17 | Quad strip forming a closed ring that loops back to a triangle's own entry edge (e.g. a cylindrical band of quads around the grid) | Verify the algorithm terminates this branch immediately upon detecting the closed loop (§9.3), with no crash or infinite loop, and that the resulting solution reflects a neutral (no-bonus) termination |
| G18 | Concave pentagon injected in the grid, shaped so at least one of the 5 candidate cuts would exit the polygon's outline if convexity were not corrected afterward | Verify the cut is still applied without any convexity check during solving (§3.3, §6.1); then verify the post-application relax pass detects the resulting reflex vertex and moves it until the affected face(s) become convex, within `maxRelaxIterations` |

## 12. Special Cases Already Covered by the Spec (Reminder)

- **Adjacent triangle-triangle penalty** (§5): still applied when it is
  the only available solution — never a pure exclusion.
- **Perfection ignored on cut-loop quads**: the perfection score only applies to
  quads *newly generated* by a direct cutting operation (pentagon,
  hexagon), not to quads resulting from a simple straight loop cut in two.

## 13. Implementation Guidance: Prefer Existing Tooling

Before implementing any mechanic described in this document from scratch,
the implementer (human or AI) **must check whether the target
environment already provides a suitable built-in operator or utility for
it**, and use that instead of a custom reimplementation. This applies both
to mesh-model-level operations (BMesh, §2.1) and to general utility
libraries available in the target environment.

**This is a research step, not optional polish**: the target environment's
own API documentation must be actively searched for each mechanic before
writing code for it, not assumed from memory or skipped. Reasons this
matters specifically for this algorithm:

- Built-in operators are typically far more robust on edge cases
  (degenerate geometry, floating-point precision, mesh-invariant
  consistency) than a hand-rolled reimplementation.
- At the target scale (tens of thousands of polygons, §9.6), hand-rolled
  Python-level loops over individual mesh elements can be significantly
  slower than a built-in operator implemented in the host application's
  native code.
- Hand-editing low-level mesh structures directly can silently break
  internal invariants (indices, selection flags, loop/radial links) in
  ways that are hard to debug later — built-in operators are guaranteed to
  keep the mesh consistent.

**Starting points to search for** (given the BMesh representation adopted
in §2.1) — these names should be treated as *leads to verify against the
current documentation of the Blender version actually targeted*, not as
guaranteed-correct signatures to use blindly:

| Document mechanic | Look for a built-in operator around... |
|---|---|
| Midpoint vertex insertion on an edge (§5.1) | Edge subdivision operators (e.g. something in `bmesh.ops` for subdividing edges) |
| Pentagon diagonal cut (§6.1) | Vertex-connecting / face-splitting operators (e.g. connecting two verts within a face) |
| Hexagon center vertex + fan cuts (§7.1) | Face "poke" operators (center vertex + full fan), combined with an edge-dissolve operator to merge alternate triangle pairs back into quads |
| Angle / centroid / vector math (§10.1, §10.2, §10.6) | The environment's math utility module (vector, angle-between, polygon-area helpers) rather than hand-written trigonometry |
| Convexity check and collinear/reflex relax (§3.3) | Vertex-smoothing operators already built into the mesh API, before writing a custom averaging/perpendicular-push loop |
| Non-manifold edge detection (§9.4) | Built-in edge/face validity or manifold-check utilities, rather than manually counting radial loops |

If, after actively searching, no suitable built-in tool exists for a given
mechanic, a custom implementation is of course acceptable — the
requirement is to check first, not to avoid custom code altogether.