"""Triage stuck-spot candidates: for each saved stuck state, list monsters within 96 units, re-run the
stuck probe with real turns, and re-run it after a 10-second wait. Writes out/snag_triage.json
(main campaign) and out/seed_triage.json (extra seeds)."""
import glob, json, math, os, tempfile
from doomqa.env import make_game, start_episode, read, load, NOOP
from doomqa.agents import _stuck_probe, MONSTERS

TMP = os.path.join(tempfile.mkdtemp(prefix='doomqa_triage_'), 'probe.sav')


def triage(paths):
    res = {}
    for p in sorted(paths):
        fid = os.path.basename(p).replace('_stuck.sav', '')
        m = fid[:5]
        g = make_game(m, god=True, sectors=True, objects=True)
        start_episode(g)
        load(g, p)
        c = read(g)
        mons = sorted((o.name, round(math.hypot(o.position_x - c['x'], o.position_y - c['y'])))
                      for o in g.get_state().objects
                      if o.name.lower() in MONSTERS and math.hypot(o.position_x - c['x'], o.position_y - c['y']) < 96)
        d = _stuck_probe(g, TMP)
        load(g, p); g.make_action(NOOP, 350)
        d2 = _stuck_probe(g, TMP)
        res[fid] = dict(pos=[round(c['x']), round(c['y']), round(c['z'])], monsters=mons,
                        probe_real_turns=round(d, 1), probe=round(d, 1), after_wait=round(d2, 1), probe_after_10s=round(d2, 1))
        g.close()
    return res


if __name__ == '__main__':
    json.dump(triage(glob.glob('out/repro/*_stuck.sav')), open('out/snag_triage.json', 'w'), indent=1)
    if os.path.isdir('out_seeds/repro'):
        json.dump(triage(glob.glob('out_seeds/repro/*_stuck.sav')), open('out/seed_triage.json', 'w'), indent=1)
    print('done')
