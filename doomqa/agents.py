"""Test agents: smoke bot, random-walk baseline, Go-Explore curiosity explorer, combat bot."""
import os, time, json, math, shutil
import numpy as np
from PIL import Image
from .env import make_game, start_episode, read, frame, load, ACTIONS, ACTION_NAMES, NOOP, FRAME_SKIP, DELTA, ATK
from .geometry import MapGeometry
from .checks import invariants, classify, MONSTERS

PICKUPS = {n.lower() for n in [
    'Clip', 'ClipBox', 'Shell', 'ShellBox', 'RocketAmmo', 'RocketBox', 'Cell', 'CellPack', 'Stimpack', 'Medikit',
    'HealthBonus', 'ArmorBonus', 'GreenArmor', 'BlueArmor', 'Soulsphere', 'Megasphere', 'Backpack', 'Shotgun',
    'SuperShotgun', 'Chaingun', 'RocketLauncher', 'PlasmaRifle', 'BFG9000', 'Chainsaw', 'BlueCard', 'RedCard',
    'YellowCard', 'BlueSkull', 'RedSkull', 'YellowSkull', 'Berserk', 'Allmap', 'Infrared', 'RadSuit',
    'InvulnerabilitySphere', 'BlurSphere']}
KEYS = {'bluecard', 'redcard', 'yellowcard', 'blueskull', 'redskull', 'yellowskull'}

# action policy shared by random walk and explorer: forward-heavy, with persistence
P_NAMES = ['fwd', 'fwd_left', 'fwd_right', 'left', 'right', 'back', 'strafe_l', 'strafe_r', 'fwd_use', 'attack', 'use']
P_W = np.array([.30, .12, .12, .06, .06, .04, .06, .06, .14, .02, .02]); P_W /= P_W.sum()


class Policy:
    def __init__(self, rng):
        self.rng, self.cur, self.left = rng, 'fwd', 0

    def __call__(self):
        if self.left <= 0:
            self.cur = P_NAMES[self.rng.choice(len(P_NAMES), p=P_W)]
            self.left = int(self.rng.integers(1, 9))
        self.left -= 1
        return self.cur


def _shot(g, path):
    f = frame(g)
    if f is not None:
        Image.fromarray(f).save(path)
        return os.path.basename(path)


def _floors(g):
    s = g.get_state()
    return None if s is None else [sec.floor_height for sec in s.sectors]


class Findings:
    def __init__(self, out, mapn, agent):
        self.items, self.seen, self.out, self.map, self.agent = [], set(), out, mapn, agent
        os.makedirs(os.path.join(out, 'shots'), exist_ok=True)

    def add(self, g, kind, rule, detail, tic, pos, key, **extra):
        if key in self.seen:
            return None
        self.seen.add(key)
        fid = f'{self.map}-{self.agent}-{len(self.items) + 1:03d}'
        shot = _shot(g, os.path.join(self.out, 'shots', fid + '.png'))
        f = dict(id=fid, map=self.map, agent=self.agent, kind=kind, rule=rule, detail=detail, tic=tic,
                 pos=[round(pos[0], 1), round(pos[1], 1), round(pos[2], 1)], shot=shot, **extra)
        self.items.append(f)
        return f


# ---------------------------------------------------------------- smoke
def smoke(mapn, out):
    t0 = time.time()
    res = dict(map=mapn, checks={}, ok=True)
    try:
        g = make_game(mapn, god=True, objects=True, sectors=True, resolution=__import__('vizdoom').ScreenResolution.RES_160X120)
        start_episode(g)
        res['boot_s'] = round(time.time() - t0, 2)
        s = g.get_state()
        cur = read(g)
        res['checks']['spawn'] = bool(cur and all(math.isfinite(cur[k]) for k in 'xyz'))
        names = [o.name.lower() for o in s.objects]
        res['monsters'] = sum(n in MONSTERS for n in names)
        res['pickups'] = sum(n in PICKUPS for n in names)
        res['keys'] = sorted({n for n in names if n in KEYS})
        res['sectors'] = len(s.sectors)
        res['lines'] = sum(len(x.lines) for x in s.sectors)
        # movement: forward for 1s, try 4 headings
        moved = 0
        for h in range(4):
            a = read(g)
            g.make_action(ACTIONS['fwd'], 35)
            b = read(g)
            moved = max(moved, math.hypot(b['x'] - a['x'], b['y'] - a['y']))
            if moved > 16:
                break
            _turn_by(g, 90)
        res['checks']['movement'] = moved > 16
        a = read(g)['ammo']
        g.make_action(ACTIONS['attack'], 20)
        b = read(g)['ammo']
        res['checks']['weapon_fires'] = b < a
        g.make_action(ACTIONS['use'], 8)
        res['checks']['use'] = read(g) is not None
        rng = np.random.default_rng(0); pol = Policy(rng); prev = None; bad = []
        t1 = time.time(); n = 0
        while n < 700 and not g.is_episode_finished():
            g.make_action(ACTIONS[pol()], FRAME_SKIP); n += FRAME_SKIP
            cur = read(g)
            if cur:
                bad += invariants(prev, cur)
                prev = cur
        res['tics_per_s'] = round(n / (time.time() - t1))
        res['checks']['invariants'] = len(bad) == 0
        res['violations'] = bad[:5]
        g.close()
    except Exception as e:  # a crash is a result, not a harness failure
        res['checks']['no_crash'] = False
        res['error'] = repr(e)
    res['checks'].setdefault('no_crash', True)
    res['ok'] = all(res['checks'].values())
    return res


# ---------------------------------------------------------------- exploration
def _turn_by(g, deg, max_tics=90):
    """Rotate by roughly `deg` degrees (positive = left) using the turn buttons, checking the real angle.
    (The TURN_LEFT_RIGHT_DELTA button is applied a tic late, so an immediate read shows no change.)"""
    a0 = read(g)['angle']
    btn = ACTIONS['left'] if deg > 0 else ACTIONS['right']
    for _ in range(max_tics):
        cur = read(g)
        if cur is None:
            return
        turned = (cur['angle'] - a0 + 540) % 360 - 180
        if abs(turned) >= abs(deg) - 2:
            return
        g.make_action(btn, 1)


def _stuck_probe(g, tmp):
    """From the current state, try 8 real headings x (forward, forward+use, strafe). Max displacement."""
    g.save(tmp)
    best = 0.0
    for h in range(8):
        for act in ('fwd', 'fwd_use', 'strafe_l'):
            load(g, tmp)
            a = read(g)
            if h:
                _turn_by(g, 45 * h if h <= 4 else -45 * (8 - h))
            g.make_action(ACTIONS[act], 10)
            b = read(g)
            if b is None:
                return 999.0
            best = max(best, math.hypot(b['x'] - a['x'], b['y'] - a['y']))
            if best > 4:
                load(g, tmp)
                return best
    load(g, tmp)
    return best


def _deep_escape(g, start_sav, work, rng, budget=4000):
    """Validate a stuck candidate: local exploration from the stuck state. Returns farthest distance reached."""
    load(g, start_sav)
    o = read(g)
    files, far, tics, pol = [start_sav], 0.0, 0, Policy(rng)
    while tics < budget and far <= 256:
        load(g, files[int(rng.integers(len(files)))])
        for _ in range(25):
            g.make_action(ACTIONS[pol()], FRAME_SKIP); tics += FRAME_SKIP
            if g.is_episode_finished():
                far = 9999.0; break
            c = read(g)
            d = math.hypot(c['x'] - o['x'], c['y'] - o['y'])
            if d > far + 8 and len(files) < 40:
                pth = os.path.join(work, f'_esc{len(files)}.sav'); g.save(pth); files.append(pth)
            far = max(far, d)
            if far > 256:
                break
    load(g, start_sav)
    return far


def explore(mapn, out, budget=150_000, mode='goexplore', seed=1, seg_len=30):
    """mode='goexplore': return to archived frontier cells via save states (count-based novelty).
       mode='random': same action policy, never returns (reset only if confirmed stuck).
       Every finding carries a repro: the save state at the start of the segment plus the inputs that followed."""
    rng = np.random.default_rng(seed)
    g = make_game(mapn, god=True, sectors=True, objects=True)
    start_episode(g)
    s = g.get_state()
    geom = MapGeometry(s.sectors)
    pickups = [dict(name=o.name, x=o.position_x, y=o.position_y) for o in s.objects if o.name.lower() in PICKUPS]
    work = os.path.join(out, 'saves', f'{mapn}_{mode}'); os.makedirs(work, exist_ok=True)
    rdir = os.path.join(out, 'repro'); os.makedirs(rdir, exist_ok=True)
    F = Findings(out, mapn, mode)
    root = geom.cell(read(g)['x'], read(g)['y'])
    archive = {root: dict(save=os.path.join(work, 'root.sav'), chosen=0, seen=0)}
    g.save(archive[root]['save'])
    events = [(0, list(root))]
    visited_pos, tics, exits, t0, act_ms, resets = [], 0, [], time.time(), [], 0
    pol = Policy(rng)
    prev = read(g)
    cur_cell = root

    def attach(f, seg_start, inputs):
        if f is None:
            return
        name = f['id'] + '_start.sav'
        shutil.copy(seg_start, os.path.join(rdir, name))
        f['repro'] = dict(kind='save+inputs', save=name, inputs=list(inputs))

    while tics < budget:
        if mode == 'goexplore':
            keys = list(archive)
            w = np.array([1 / math.sqrt(1 + archive[k]['chosen']) / math.sqrt(1 + archive[k]['seen']) for k in keys])
            pick = keys[rng.choice(len(keys), p=w / w.sum())]
            archive[pick]['chosen'] += 1
            if g.is_episode_finished():
                start_episode(g)
            seg_start = archive[pick]['save']
            load(g, seg_start)
            prev = read(g)
        else:
            if g.is_episode_finished():
                start_episode(g); prev = read(g)
            seg_start = os.path.join(work, '_seg.sav'); g.save(seg_start)
        seg, poss, floors, floor_streak = [], [], None, 0
        for k in range(seg_len):
            an = pol()
            ts = time.perf_counter()
            g.make_action(ACTIONS[an], FRAME_SKIP)
            act_ms.append((time.perf_counter() - ts) * 1000)
            tics += FRAME_SKIP
            seg.append(ACTION_NAMES.index(an))
            if g.is_episode_finished():
                ex = dict(tic=tics)
                if not exits:
                    name = f'{mapn}-{mode}-exit_start.sav'
                    shutil.copy(seg_start, os.path.join(rdir, name))
                    ex['repro'] = dict(kind='save+inputs', save=name, inputs=list(seg))
                exits.append(ex)
                break
            cur = read(g)
            floors = _floors(g)
            viol = invariants(prev, cur, geom, floors)
            # physics checks must persist 3 consecutive steps (12 tics) to rule out moving lifts/doors
            floor_streak = floor_streak + 1 if any(r == 'above_floor' for r, _ in viol) else 0
            viol = [v for v in viol if v[0] != 'above_floor' or floor_streak >= 3]
            for rule, detail in viol:
                c = geom.cell(cur['x'], cur['y'])
                attach(F.add(g, 'invariant', rule, detail, tics, (cur['x'], cur['y'], cur['z']), (rule, c)), seg_start, seg)
            prev = cur
            poss.append((cur['x'], cur['y']))
            c = geom.cell(cur['x'], cur['y'])
            cur_cell = c
            if c in archive:
                archive[c]['seen'] += 1
            else:
                pth = os.path.join(work, f'{c[0]}_{c[1]}.sav')
                if mode == 'goexplore':
                    g.save(pth)
                archive[c] = dict(save=pth, chosen=0, seen=0)
                events.append((tics, list(c)))
        if len(poss) >= 15 and not g.is_episode_finished():
            xs, ys = zip(*poss[-15:])
            if max(xs) - min(xs) < 3 and max(ys) - min(ys) < 3:
                d = _stuck_probe(g, os.path.join(work, '_probe.sav'))
                if d < 2:
                    cur = read(g)
                    f = F.add(g, 'stuck', 'can_leave_position',
                              f'no heading lets the player move more than {d:.1f} units (forward, use, strafe tried)',
                              tics, (cur['x'], cur['y'], cur['z']), ('stuck', geom.cell(cur['x'], cur['y'])))
                    if f:
                        attach(f, seg_start, seg)
                        so = g.get_state().objects
                        f['actors_within_64'] = sorted(o.name for o in so if o.name.lower() in MONSTERS and math.hypot(o.position_x - cur['x'], o.position_y - cur['y']) < 64)
                        if f['actors_within_64']:
                            f['rule'] = 'blocked_by_actors'
                        stuck_sav = os.path.join(rdir, f['id'] + '_stuck.sav'); g.save(stuck_sav)
                        far = _deep_escape(g, stuck_sav, work, rng)
                        f['escape_test'] = dict(budget_tics=4000, farthest_units=round(far, 1))
                        f['confirmed'] = far < 96
                        f['stuck_save'] = os.path.basename(stuck_sav)
                        if mode == 'random' and f['confirmed']:
                            start_episode(g); prev = read(g); resets += 1
                            f['note'] = 'random agent reset to spawn'
        if poss:
            visited_pos.append([round(poss[-1][0]), round(poss[-1][1])])
    wall = time.time() - t0
    reached = set(archive)
    walk = geom.cells
    def near(p):
        return any(abs(p['x'] - (geom.x0 + (c[0] + .5) * 64)) < 64 and abs(p['y'] - (geom.y0 + (c[1] + .5) * 64)) < 64 for c in reached)
    item_reached = [p for p in pickups if near(p)]
    res = dict(map=mapn, mode=mode, budget_tics=budget, wall_s=round(wall, 1), tics_per_s=round(tics / wall),
               cells_reached=len(reached), walkable_cells=len(walk),
               coverage=round(len(reached & walk) / max(1, len(walk)), 4),
               events=events, exits=exits, findings=F.items, resets=resets,
               pickups_total=len(pickups), pickups_reached=len(item_reached),
               unreached_pickups=[p for p in pickups if p not in item_reached],
               action_ms_p50=round(float(np.percentile(act_ms, 50)), 2), action_ms_p99=round(float(np.percentile(act_ms, 99)), 2),
               trail=visited_pos[::2])
    g.close()
    shutil.rmtree(work, ignore_errors=True)
    return res, geom.to_json()


def replay_check(mapn, repro, out, fid, expect_pos=None, kind='invariant'):
    """Reproduce a finding in a fresh game process: load the captured save state, replay the inputs."""
    g = make_game(mapn, god=True, sectors=True)
    start_episode(g)
    load(g, os.path.join(out, 'repro', repro['save']))
    ended = False
    for a in repro['inputs']:
        g.make_action(ACTIONS[ACTION_NAMES[a]], FRAME_SKIP)
        if g.is_episode_finished():
            ended = True; break
    res = dict(method='fresh process: load save, replay %d inputs' % len(repro['inputs']), ended=ended)
    if kind == 'exit':
        res['reproduced'] = ended
    elif not ended:
        cur = read(g)
        res['shot'] = _shot(g, os.path.join(out, 'shots', fid + '_replay.png'))
        d = math.hypot(cur['x'] - expect_pos[0], cur['y'] - expect_pos[1])
        res.update(distance=round(d, 1), end_pos=[round(cur['x'], 1), round(cur['y'], 1)])
        ok = d < 32
        if kind == 'stuck':
            tmp = os.path.join(out, 'repro', '_tmp.sav')
            res['still_stuck'] = _stuck_probe(g, tmp) < 2
            os.remove(tmp)
            ok = ok and res['still_stuck']
        res['reproduced'] = ok
    else:
        res['reproduced'] = False
    g.close()
    return res


# ---------------------------------------------------------------- combat bot
def combat(mapn, out, episodes=4, tics_per_ep=2100, seed=3):
    import vizdoom as vzd
    rng = np.random.default_rng(seed)
    g = make_game(mapn, god=False, skill=3, labels=True, sectors=True, timeout=tics_per_ep, seed=seed)
    os.makedirs(os.path.join(out, 'demos'), exist_ok=True)
    F = Findings(out, mapn, 'combat')
    edges, states_seen, eps = {}, {}, []
    geom = None
    W = g.get_screen_width()
    for ep in range(episodes):
        demo = os.path.join(out, 'demos', f'{mapn}_combat_ep{ep + 1}.lmp')
        start_episode(g, demo)
        if geom is None:
            geom = MapGeometry(g.get_state().sectors)
        prev, state, tics, last_pos, stuck_n = None, 'Spawn', 0, None, 0
        states_seen['Spawn'] = states_seen.get('Spawn', 0) + 1
        pol = Policy(rng)
        outcome = 'timeout'
        while True:
            s = g.get_state()
            if s is None:
                break
            vis = [l for l in s.labels if l.object_name.lower() in MONSTERS]
            if vis:
                tgt = max(vis, key=lambda l: l.width * l.height)
                off = (tgt.x + tgt.width / 2) - W / 2
                if abs(off) < W * 0.06:
                    g.make_action(ACTIONS['attack'], FRAME_SKIP)
                else:
                    v = list(ACTIONS['left'] if off < 0 else ACTIONS['right']); v[ATK] = int(abs(off) < W * 0.15)
                    g.make_action(v, FRAME_SKIP)
            else:
                an = pol()
                g.make_action(ACTIONS[an], FRAME_SKIP)
            tics += FRAME_SKIP
            if g.is_episode_finished():
                if g.is_player_dead():
                    new = 'Dead'; outcome = 'died'
                elif g.is_episode_timeout_reached():
                    new = None
                else:
                    new = 'LevelExit'; outcome = 'exit'
                if new:
                    edges[(state, new)] = edges.get((state, new), 0) + 1
                    states_seen[new] = states_seen.get(new, 0) + 1
                break
            cur = read(g)
            for rule, detail in invariants(prev, cur, geom):
                F.add(g, 'invariant', rule, detail, tics, (cur['x'], cur['y'], cur['z']), (rule, geom.cell(cur['x'], cur['y'])), demo=os.path.basename(demo))
            new = classify(prev, cur, bool(vis))
            if new != state:
                edges[(state, new)] = edges.get((state, new), 0) + 1
                states_seen[new] = states_seen.get(new, 0) + 1
                state = new
            if cur['dead'] > 0:
                pass
            prev = cur
        if outcome == 'died' and ep < episodes - 1:
            edges[('Dead', 'Spawn')] = edges.get(('Dead', 'Spawn'), 0) + 1
        fin = prev or {}
        eps.append(dict(ep=ep + 1, outcome=outcome, tics=tics, kills=fin.get('kills'), items=fin.get('items'),
                        damage_taken=fin.get('damage_taken'), demo=os.path.basename(demo)))
    g.new_episode(); g.close()
    return dict(map=mapn, episodes=eps, edges=[[a, b, n] for (a, b), n in edges.items()], states=states_seen, findings=F.items)
