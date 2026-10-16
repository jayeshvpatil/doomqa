"""Map geometry from ViZDoom sector info: wall segments for drawing, and a raster that says which
sector (if any) contains a point, so we can check out-of-bounds and fall-through-floor."""
import numpy as np

RES = 16      # raster resolution in map units
CELL = 64     # coverage cell size in map units


class MapGeometry:
    def __init__(self, sectors):
        self.lines = []
        for si, sec in enumerate(sectors):
            for l in sec.lines:
                self.lines.append((l.x1, l.y1, l.x2, l.y2, bool(l.is_blocking)))
        xs = [v for l in self.lines for v in (l[0], l[2])]
        ys = [v for l in self.lines for v in (l[1], l[3])]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)
        nx = int((self.x1 - self.x0) // RES) + 1
        ny = int((self.y1 - self.y0) // RES) + 1
        gx = self.x0 + (np.arange(nx) + 0.5) * RES
        gy = self.y0 + (np.arange(ny) + 0.5) * RES
        PX, PY = np.meshgrid(gx, gy)
        self.sector_of = np.full(PX.shape, -1, dtype=np.int32)
        self.floor0 = np.array([s.floor_height for s in sectors])
        self.sec_lines = [[(l.x1, l.y1, l.x2, l.y2) for l in s.lines] for s in sectors]
        self.sec_bbox = [(min(min(a[0], a[2]) for a in L), min(min(a[1], a[3]) for a in L),
                          max(max(a[0], a[2]) for a in L), max(max(a[1], a[3]) for a in L)) if L else (0, 0, -1, -1)
                         for L in self.sec_lines]
        for si, sec in enumerate(sectors):
            inside = np.zeros(PX.shape, dtype=bool)
            for l in sec.lines:
                x1, y1, x2, y2 = l.x1, l.y1, l.x2, l.y2
                if y1 == y2:
                    continue
                cond = (y1 > PY) != (y2 > PY)
                xint = (x2 - x1) * (PY - y1) / (y2 - y1) + x1
                inside ^= cond & (PX < xint)
            self.sector_of[inside] = si
        # walkable coverage cells: CELL-sized cells with >=50% raster points inside some sector
        k = CELL // RES
        inside = (self.sector_of >= 0).astype(np.float32)
        H, W = inside.shape
        Hc, Wc = H // k, W // k
        frac = inside[:Hc * k, :Wc * k].reshape(Hc, k, Wc, k).mean(axis=(1, 3))
        self.cells = {(int(cx), int(cy)) for cy, cx in zip(*np.nonzero(frac >= 0.5))}

    def cell(self, x, y):
        return (int((x - self.x0) // CELL), int((y - self.y0) // CELL))

    def sector_at(self, x, y):
        ix = int((x - self.x0) // RES)
        iy = int((y - self.y0) // RES)
        if iy < 0 or ix < 0 or iy >= self.sector_of.shape[0] or ix >= self.sector_of.shape[1]:
            return -1
        # tolerate raster edge: check the 3x3 neighbourhood
        win = self.sector_of[max(0, iy - 1):iy + 2, max(0, ix - 1):ix + 2]
        c = self.sector_of[iy, ix]
        if c >= 0:
            return int(c)
        vals = win[win >= 0]
        return int(vals[0]) if len(vals) else -1

    def sectors_under(self, x, y, r=16):
        """All sectors that contain any sample point of the player's footprint (radius r)."""
        pts = [(x + dx, y + dy) for dx in (-r, 0, r) for dy in (-r, 0, r)]
        out = set()
        for si, (bx0, by0, bx1, by1) in enumerate(self.sec_bbox):
            if bx1 < x - r or bx0 > x + r or by1 < y - r or by0 > y + r:
                continue
            for px, py in pts:
                c = False
                for x1, y1, x2, y2 in self.sec_lines[si]:
                    if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                        c = not c
                if c:
                    out.add(si); break
        return out

    def to_json(self):
        return {'bounds': [self.x0, self.y0, self.x1, self.y1], 'cell': CELL,
                'lines': [[round(a, 1) for a in l[:4]] + [int(l[4])] for l in self.lines],
                'walkable_cells': sorted(self.cells)}
