"""Determinism suite: what can a bug report rely on to reproduce a run?"""
import math, tempfile
import numpy as np

TMP = tempfile.mkdtemp(prefix='doomqa_det_')
from .env import make_game, start_episode, read, ACTIONS, NOOP, FRAME_SKIP


def _acts(n, seed=1):
    rng = np.random.default_rng(seed)
    names = ['fwd', 'fwd_left', 'fwd_right', 'use']
    return [names[int(rng.integers(0, 4))] for _ in range(n)]


def _pos(g):
    r = read(g)
    return None if r is None else (round(r['x'], 3), round(r['y'], 3), r['health'])


def run():
    out = {}
    acts = _acts(120)
    # 1. same seed + same inputs, three fresh episodes, normal damage
    g = make_game('MAP01', god=False, skill=1)
    fresh = []
    for k in range(3):
        g.new_episode(f'{TMP}/det_{k}.lmp')   # plain episode start, no idle tic, so monsters engage early
        for a in acts:
            g.make_action(ACTIONS[a], FRAME_SKIP)
        fresh.append(_pos(g))
    g.new_episode()
    reps = []
    for k in range(3):
        g.replay_episode(f'{TMP}/det_{k}.lmp')
        last = None
        while not g.is_episode_finished():
            last = _pos(g) or last
            g.advance_action()
        reps.append(last)
    g.close()
    out['input_replay'] = dict(runs=fresh, identical=len(set(fresh)) == 1)
    out['demo_replay'] = dict(replays=reps, matches_original=[r == f for r, f in zip(reps, fresh)])
    # 2. repeated loads of one save: does input still register?
    raw = []
    g = make_game('MAP01', god=True); start_episode(g); g.save(f'{TMP}/det.sav')
    for k in range(4):
        g.load(f'{TMP}/det.sav'); a = read(g)
        for i in range(20):
            g.make_action(ACTIONS['fwd'], FRAME_SKIP)
        b = read(g); raw.append(round(math.hypot(b['x'] - a['x'], b['y'] - a['y'])))
    fixed = []
    for k in range(4):
        g.load(f'{TMP}/det.sav'); g.make_action(NOOP, 1); a = read(g)
        for i in range(20):
            g.make_action(ACTIONS['fwd'], FRAME_SKIP)
        b = read(g); fixed.append(round(math.hypot(b['x'] - a['x'], b['y'] - a['y'])))
    g.close()
    out['load_input'] = dict(displacement_per_load=raw, with_idle_tic=fixed)
    # 3. save -> continue vs load -> same inputs (state fidelity)
    g = make_game('MAP01', god=True); start_episode(g)
    for a in acts[:60]:
        g.make_action(ACTIONS[a], FRAME_SKIP)
    g.save(f'{TMP}/det2.sav')
    for a in acts[60:]:
        g.make_action(ACTIONS[a], FRAME_SKIP)
    live = _pos(g)
    g.load(f'{TMP}/det2.sav'); g.make_action(NOOP, 1)
    for a in acts[60:]:
        g.make_action(ACTIONS[a], FRAME_SKIP)
    loaded = _pos(g)
    g.close()
    out['save_fidelity'] = dict(live=live, after_load=loaded,
                                drift_units=round(math.hypot(live[0] - loaded[0], live[1] - loaded[1]), 3))
    return out
