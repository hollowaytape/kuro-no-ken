"""Where can the player walk? Ask the game, one step at a time, and remember.

There is no map format to read for this: the collision test (BD.BIN 0x456a) checks bits
another routine has precomputed per object from the tiles around it, and chasing that
back to the tile data is more reverse-engineering than the question deserves. The game
answers directly instead. From a save state a tap in a direction either moves the
player exactly one tile (two map units) that way, or it does not - a wall slides the
player sideways, so a move counts only when the delta is the direction's own vector -
and with a probe at ~8 ms and a state reload at ~3 ms, a whole map is learned in a
breadth-first walk in a few minutes: every reachable tile, and which of its four
neighbours it connects to. NPCs standing in the way count as walls at learning time,
which is what a player meets too.

    grid = Grid(emu)
    grid.learn()                         # from where the player stands
    path = grid.path(emu.pos(), (x, y))  # tiles to step through, or None
    grid.walk(path)                      # tap along it, checking every step

The grid is keyed by the map's zone layout (Emu.map_sig) and cached in memory for the
tour; a map is learned once per run.
"""
import collections
import heapq
import zlib

STEP = 2                         # one tap moves one tile = two map units
DIRS = {'UP': (0, -STEP), 'DOWN': (0, STEP), 'LEFT': (-STEP, 0), 'RIGHT': (STEP, 0)}
SETTLE = 0.12                    # seconds of game time for a step to land


class Grid:
    def __init__(self, emu, log=lambda *a: None):
        self.emu = emu
        self.log = log
        self.edges = collections.defaultdict(set)     # cell -> {cell}
        self.cells = set()
        self.origin = None

    # --- learning ------------------------------------------------------------
    def probe(self, raw, cell):
        """From the state `raw` (player at `cell`), which neighbours can be stepped to?
        -> {neighbour cell: raw state standing there}"""
        out = {}
        for key, (dx, dy) in DIRS.items():
            self.emu.m.load_state(raw)
            self.emu.tap(key, self.emu.nudge)
            self.emu.wait(SETTLE)
            x, y = self.emu.pos()
            if (x - cell[0], y - cell[1]) == (dx, dy) and self.emu.state() == 'field':
                out[(x, y)] = self.emu.m.save_state()
        self.emu.m.load_state(raw)
        return out

    def learn(self, max_cells=8000, budget_s=None):
        """Breadth-first from where the player stands. Compressed states ride on the
        frontier only; the player is put back where it started afterwards."""
        import time
        start = self.emu.pos()
        base = self.emu.m.save_state()
        self.origin = start
        self.cells.add(start)
        frontier = collections.deque([(start, zlib.compress(base, 1))])
        seen = {start}
        t0 = time.time()
        while frontier and len(self.cells) < max_cells:
            if budget_s and time.time() - t0 > budget_s:
                self.log('  grid: out of time after %d cells' % len(self.cells))
                break
            cell, z = frontier.popleft()
            for nxt, raw in self.probe(zlib.decompress(z), cell).items():
                self.edges[cell].add(nxt)
                self.edges[nxt].add(cell)
                if nxt not in seen:
                    seen.add(nxt)
                    self.cells.add(nxt)
                    frontier.append((nxt, zlib.compress(raw, 1)))
        self.emu.m.load_state(base)
        self.log('  grid: %d tiles reachable in %.0fs' % (len(self.cells), time.time() - t0))
        return len(self.cells)

    # --- routing -------------------------------------------------------------
    def nearest_cell(self, x, y, within=6):
        """The learned tile closest to a point, if one is within reach of it."""
        best = min(self.cells, key=lambda c: abs(c[0] - x) + abs(c[1] - y), default=None)
        if best and abs(best[0] - x) + abs(best[1] - y) <= within:
            return best
        return None

    def path(self, src, dst):
        """Tiles from src to dst (both learned cells), shortest, or None."""
        if src not in self.cells or dst not in self.cells:
            return None
        h = lambda c: abs(c[0] - dst[0]) + abs(c[1] - dst[1])
        heap, came, cost = [(h(src), src)], {src: None}, {src: 0}
        while heap:
            _f, c = heapq.heappop(heap)
            if c == dst:
                out = []
                while c is not None:
                    out.append(c)
                    c = came[c]
                return out[::-1]
            for n in self.edges[c]:
                g = cost[c] + 1
                if g < cost.get(n, 1e9):
                    cost[n], came[n] = g, c
                    heapq.heappush(heap, (g + h(n), n))
        return None

    def distance(self, src, dst):
        p = self.path(src, dst)
        return len(p) - 1 if p else None

    def snap(self, cell, tries=8):
        """Step onto `cell` from within a few units of it: a one-frame tap moves one
        unit, a normal tap two. Talking chases NPCs with tiny taps and leaves the
        player anywhere; the grid is the two-unit lattice of the tile it was learned
        from, and every route starts on it."""
        for _ in range(tries):
            x, y = self.emu.pos()
            dx, dy = cell[0] - x, cell[1] - y
            if (dx, dy) == (0, 0):
                return True
            if abs(dx) >= abs(dy):
                key, d = ('RIGHT' if dx > 0 else 'LEFT'), abs(dx)
            else:
                key, d = ('DOWN' if dy > 0 else 'UP'), abs(dy)
            self.emu.tap(key, self.emu.nudge if d >= 2 else 1 / 60.0)
            self.emu.wait(SETTLE)
            if self.emu.state() != 'field':
                return False
        return self.emu.pos() == cell

    def root(self, within=3):
        """The learned tile the player stands on, or the nearest within a few units."""
        here = self.emu.pos()
        if here in self.cells:
            return here
        near = [c for c in self.cells if abs(c[0] - here[0]) + abs(c[1] - here[1]) <= within]
        return min(near, key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1])) if near else None

    def walk(self, path, on_interrupt=None):
        """Tap along a path, one tile per tap, checking where the player lands.
        Stops early (returning False) when something else took over - a scene, a
        battle, an NPC that stepped into the way - after letting `on_interrupt` deal
        with it."""
        for a, b in zip(path, path[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            key = next(k for k, v in DIRS.items() if v == (dx, dy))
            if self.emu.pos() != a:
                return False
            self.emu.tap(key, self.emu.nudge)
            self.emu.wait(SETTLE)
            if self.emu.state() != 'field':
                if on_interrupt:
                    on_interrupt()
                return False
            if self.emu.pos() != b:
                return False
        return True
