"""Assemble the demo report: reads out/*.json, curates tickets, embeds images, writes report/index.html."""
import json, glob, os, base64, io, statistics, sys
from PIL import Image

OUT = 'out'
J = lambda p: json.load(open(p))


def uri(path, fmt=None, scale=None):
    im = Image.open(path)
    if scale:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    b = io.BytesIO(); im.convert('RGB').save(b, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode()


maps = ['MAP01', 'MAP02', 'MAP03', 'MAP04', 'MAP05', 'MAP06']
det = J(f'{OUT}/det_ALL.json')
reps = J(f'{OUT}/replays.json')
old_reps = J(f'{OUT}/old/replays.json') if os.path.exists(f'{OUT}/old/replays.json') else {}
perf = {r['map']: r for r in J(f'{OUT}/perf_serial.json')}
demo_v = J(f'{OUT}/demo_verify.json')
smoke = [J(f) for f in sorted(glob.glob(f'{OUT}/smoke_MAP*.json'))]
combat = [J(f'{OUT}/combat_{m}.json') for m in maps]
med_tps = statistics.median(p['tics_per_s'] for p in perf.values())

D = dict(budget=120_000, maps={}, tickets=[])
seeds = J(f'{OUT}/seeds.json') if os.path.exists(f'{OUT}/seeds.json') else []
total_tics = 0
all_findings = []
for m in maps:
    geo = J(f'{OUT}/geo_{m}.json')
    mm = dict(geo=dict(bounds=geo['bounds'], cell=geo['cell'], lines=geo['lines'], walkable_cells=geo['walkable_cells']),
              walkable=len(geo['walkable_cells']))
    for k, mode in (('ge', 'goexplore'), ('rnd', 'random')):
        r = J(f'{OUT}/{mode}_{m}.json')
        total_tics += r['budget_tics']
        fl = []
        for f in r['findings']:
            all_findings.append(f)
            fl.append(dict(x=f['pos'][0], y=f['pos'][1], tic=f['tic'], closed=False))
        mm[k] = dict(events=[[t, c[0], c[1]] for t, c in r['events']], cov=r['coverage'], cells=r['cells_reached'],
                     exits=[dict(tic=e['tic'], x=None, y=None) for e in r['exits']], findings=fl,
                     unreached=[[round(p['x']), round(p['y'])] for p in r['unreached_pickups']],
                     pick_reached=r['pickups_reached'], pick_total=r['pickups_total'])
        mm[k]['covs'] = [r['coverage']] + [s['coverage'] for s in seeds if s['map'] == m and s['mode'] == mode]
        mm[k]['exit_runs'] = int(bool(r['exits'])) + sum(1 for s in seeds if s['map'] == m and s['mode'] == mode and s['exits'])
    D['maps'][m] = mm

# ---------------- tickets
T = D['tickets']
li = det['load_input']
T.append(dict(id='QA-001', area='Engine · ViZDoom 1.3.2', sev='high', sevLabel='High · blocks test tooling', status='open', repro_ok=True,
    reproLabel='Reproduced · MAP01 and MAP07',
    title='Player input is ignored after the second save-state load',
    what='After loading the same save state a second time, the next movement and turn commands do nothing. The first load works; every later load leaves the player frozen until one idle tic has run. This silently breaks any tool that rewinds the game with save states. On a short MAP01 run our explorer reached 11% of the map with the defect and 21% once we worked around it, and any stuck-spot detector built on loads reports false positives.',
    evidence=[(f'load {i + 1}: moved {d} units', d == 0) for i, d in enumerate(li['displacement_per_load'])] +
             [(f'with 1 idle tic: {li["with_idle_tic"][0]} units every load', False)],
    kv=[('Expected', 'Each load followed by 20 forward steps moves the player the same distance.'),
        ('Workaround', 'Run one idle tic after every load (applied in the harness, see doomqa/env.py).'),
        ('Upstream', 'Not mentioned in the documented save/load API. The ViZDoom issue tracker has not been searched yet; worth checking before filing.')],
    code="g.save('s.sav')\nfor i in range(4):\n    g.load('s.sav')\n    for _ in range(20):\n        g.make_action(FORWARD, 4)   # 4 tics per step\n# distance moved per load: %s" % ', '.join(map(str, li['displacement_per_load']))))

sf = det['save_fidelity']
ex_old = old_reps.get('MAP01-goexplore-exit', {}).get('distance')
f4_old = old_reps.get('MAP04-goexplore-001', {}).get('distance')
T.append(dict(id='QA-002', area='Engine · ViZDoom 1.3.2', sev='low', sevLabel='Low · affects repro design', status='open', repro_ok=True,
    reproLabel='Reproduced · deterministic',
    title='A loaded save state is not bit-identical to the live game',
    what=f'Saving, continuing 60 steps, then loading and replaying the same 60 steps ends {sf["drift_units"]} map units from where the live run ended. It is small and deterministic, but it means a run that used save states cannot be rebuilt by replaying its inputs from spawn: each load shifts the trajectory slightly and the shifts add up.',
    evidence=[(f'live end ({sf["live"][0]}, {sf["live"][1]})', False), (f'after load ({sf["after_load"][0]}, {sf["after_load"][1]})', False), (f'drift {sf["drift_units"]} units', True)],
    kv=[('Impact', 'Bug reports can’t rely on “replay these inputs from spawn” once save states were used.'),
        ('Harness change', 'Every finding now captures the segment’s starting save state and the inputs that followed.')]))

ir, dr = det['input_replay'], det['demo_replay']
nmatch = sum(r['match'] for r in demo_v)
T.append(dict(id='QA-003', area='Test design', sev='info', sevLabel='Info · how to file repros', status='open', repro_ok=True,
    reproLabel=f'Demos replayed {nmatch}/{len(demo_v)} exactly',
    title='Same seed and same inputs don’t reproduce a match; engine demos do' if not ir['identical'] else 'Engine demos reproduce runs exactly',
    what=('Three fresh episodes with the same seed and identical inputs ended with different health ('
          + ', '.join(str(int(r[2])) for r in ir['runs']) + '), because combat randomness is not reset per episode. The engine’s own demo recordings replayed each run exactly. '
          if not ir['identical'] else 'Three fresh episodes with identical inputs ended identically, and demo recordings matched. ')
         + f'All {len(demo_v)} combat-bot episodes were recorded as demos and replayed in a fresh process; final kills, items and damage matched in {nmatch} of {len(demo_v)}.',
    evidence=[(f'run {i + 1}: health {int(r[2])}', False) for i, r in enumerate(ir['runs'])] + [(f'demo replays match: {sum(dr["matches_original"])}/3', False)],
    kv=[('Recommendation', 'Attach the demo file (or a save + inputs) to every ticket. Treat input logs as notes, not repro.')]))

# agent findings: the two "stuck" candidates, closed in triage
snag = J(f'{OUT}/snag_triage.json')
seedtri = J(f'{OUT}/seed_triage.json') if os.path.exists(f'{OUT}/seed_triage.json') else {}
n = 4
stuck = [f for f in all_findings if f['kind'] == 'stuck']
if stuck:
    f0 = [f for f in stuck if f['map'] == 'MAP04'] or stuck
    f0 = f0[0]
    mons = '; '.join(f"{f['map']}: " + ', '.join(f"{k} at {d} units" for k, d in snag[f['id']]['monsters']) for f in stuck if f['id'] in snag)
    T.append(dict(id=f'QA-{n:03d}', area=' · '.join(sorted({f['map'] for f in stuck})) + ' · random agent', sev='info', sevLabel='Closed · test artifact', status='closed', repro_ok=False,
        reproLabel='Reproduced, then closed',
        title=f'{len(stuck) + len(seedtri)} “player can’t move” reports were the god-mode player boxed in by monsters',
        what='The random agent stopped moving in a corridor on MAP03 and next to a blue-key door on MAP04. Both replayed exactly from their save states in a fresh process. Triage then found two Demons within about 50 units in each case: in god mode the player can’t die and the Demons won’t back off, so nobody moves. In normal play the player kills them or dies. The extra seed runs saved six more stuck states; all six had monsters within 72 units, four were still blocked after a 10-second wait, and in the other two the monster had moved off. The stuck detector now lists nearby monsters and files these as “blocked by actors” instead of a level bug.',
        evidence=[(f"{f['map']}: moved ≤ {snag[f['id']]['probe_real_turns']} units in 8 headings", False) for f in stuck if f['id'] in snag] +
                 [(f"{f['map']}: escape test reached {f['escape_test']['farthest_units']} units", False) for f in stuck],
        kv=[('Monsters nearby', mons),
            ('Replay', ', '.join(f"{f['map']} {reps.get(f['id'], {}).get('distance', '?')} units off, still stuck" for f in stuck)),
            ('Better setup', 'For navigation coverage, run explorers with monsters set to ignore the player (notarget) or removed, and keep monsters for the combat bot.'),
            ('Also found', 'Our probe’s turn command was being dropped (the delta turn button applies a tic late), so the first probe only ever tried one heading. Fixed: turns now use the turn buttons and check the real angle.')],
        shot=uri(os.path.join(OUT, 'shots', f0['shot'])), shotCap=f"{f0['map']} at detection: blue-key door ahead, Demons behind"))
    n += 1

# closed false positive from the first campaign
fp_img = os.path.join(OUT, 'shots', 'MAP04-floor-fp.png')
if os.path.exists(fp_img):
    p = fp_img
    T.append(dict(id=f'QA-{n:03d}', area='MAP04 · harness', sev='info', sevLabel='Closed · harness bug', status='closed', repro_ok=False,
        reproLabel='Closed during triage',
        title='“Player below the floor” on MAP04 was our own lookup error',
        what='The floor check reported the player 24 units below the floor of sector 5. An exact geometry test showed the point sits where sector 5’s outline overlaps two other sectors, and the player was standing on sector 40, whose floor is exactly at z = −24. The check now uses every sector under the player’s footprint, and the finding no longer fires.',
        kv=[('Root cause', 'Per-sector point-in-polygon picked one of several overlapping sectors.'),
            ('Fix', 'Compare z with the lowest floor of all sectors under the player’s 16-unit radius.')],
        shot=uri(p), shotCap='Frame at detection: player on a grate above a lower floor'))
    n += 1

# performance
slow = sorted(perf.values(), key=lambda r: r['tics_per_s'])[0]
sm = {r['map']: r for r in smoke}
if slow['tics_per_s'] < med_tps * 0.5:
    s0 = sm[slow['map']]
    T.append(dict(id=f'QA-{n:03d}', area=f'{slow["map"]} · performance', sev='low', sevLabel='Low · performance outlier', status='open', repro_ok=True,
        reproLabel='Measured serially, one map at a time',
        title=f'{slow["map"]} simulates {med_tps / slow["tics_per_s"]:.1f}× slower than the median map',
        what=f'With the same bot and inputs, {slow["map"]} ran at {slow["tics_per_s"]:,} tics/s against a median of {med_tps:,.0f}. It is also the heaviest map ({s0["lines"]:,} wall segments, {s0["monsters"]} monsters). For a live game the same check runs per build and flags maps whose frame cost jumps.',
        kv=[('Tic time', f'p50 {slow["ms_per_tic_p50"]} ms, p99 {slow["ms_per_tic_p99"]} ms (headless, 320×240)'),
            ('Next step', 'Profile the map with the engine’s profiler; compare against the previous build.')]))
    n += 1

# ---------------- states
E, visits = {}, {}
eps, outc = 0, {'died': 0, 'timeout': 0, 'exit': 0}
for c in combat:
    for a, b, k in c['edges']:
        E[(a, b)] = E.get((a, b), 0) + k
    for s, k in c['states'].items():
        visits[s] = visits.get(s, 0) + k
    for e in c['episodes']:
        eps += 1; outc[e['outcome']] += 1
from importlib import import_module
sys.path.insert(0, '.')
EXP = import_module('doomqa.checks').EXPECTED_EDGES
D['states'] = dict(edges=[[a, b, k] for (a, b), k in E.items()], expected=[list(e) for e in EXP], visits=visits, episodes=eps, maps=len(combat),
                   outcomes=f'{outc["died"]} deaths, {outc["timeout"]} reached the 60-second limit, {outc["exit"]} level exits. '
                            f'Kills per episode ranged {min(e["kills"] or 0 for c in combat for e in c["episodes"]):.0f}–{max(e["kills"] or 0 for c in combat for e in c["episodes"]):.0f}. The bot is deliberately simple; a stronger persona would cover the exit and pickup edges.')

# ---------------- smoke
D['smoke'] = [dict(map=r['map'], ok=r['ok'], checks=r['checks'], boot_s=r.get('boot_s', 0), tps=perf[r['map']]['tics_per_s'],
                   lines=r.get('lines', 0), monsters=r.get('monsters', 0), pickups=r.get('pickups', 0), keys=r.get('keys', []),
                   slow=perf[r['map']]['tics_per_s'] < med_tps * 0.5) for r in smoke]

# ---------------- hero
ge_avg = statistics.mean(statistics.mean(D['maps'][m]['ge']['covs']) for m in maps)
rn_avg = statistics.mean(statistics.mean(D['maps'][m]['rnd']['covs']) for m in maps)
nseeds = len(D['maps'][maps[0]]['ge']['covs'])
wins = sum(statistics.mean(D['maps'][m]['ge']['covs']) - statistics.mean(D['maps'][m]['rnd']['covs']) >= 0.02 for m in maps)
loss = sum(statistics.mean(D['maps'][m]['ge']['covs']) - statistics.mean(D['maps'][m]['rnd']['covs']) <= -0.02 for m in maps)
D['nseeds'] = nseeds
combat_tics = sum(e['tics'] for c in combat for e in c['episodes'])
smoke_tics = 32 * 900
game_h = (total_tics + combat_tics + smoke_tics) / 35 / 3600
open_t = [t for t in T if t['status'] == 'open' and t['sev'] in ('high', 'med', 'low')]
n_closed = len(stuck) + len(seedtri) + 1
n_cand = n_closed + len([x for x in T if x['status'] == 'open'])
D['cand'] = dict(total=n_cand, closed=n_closed)
D['run'] = dict(
    lede='Freedoom is a complete, open-source game for the Doom engine. We ran it headless through ViZDoom and pointed four agent types at it: a scripted smoke bot, a random-walk baseline, a curiosity agent that returns to its least-visited frontier, and a combat bot. Every finding below was re-run in a fresh process before it was filed.',
    meta=[('Game', 'Freedoom: Phase 2 (32 maps)'), ('Engine', 'ViZDoom 1.3.2, headless'), ('Hardware', '2 CPU cores, cloud sandbox'),
          ('Game time', f'{game_h:.1f} hours simulated'), ('Budget', '120,000 tics (57 min) per map per explorer'), ('Run date', '16 Oct 2026')])
D['tiles'] = [
    dict(n=f'{sum(r["ok"] for r in smoke)}/32', l='Maps passed smoke: boot, spawn, move, fire, use, invariants', c='mint'),
    dict(n=f'{game_h:.1f} h', l='Game time played by agents, at up to 60× real time', c='cyan'),
    dict(n=str(len([x for x in T if x['status'] == 'open'])), l=f"Tickets filed with repro; {n_closed} more candidates closed in triage", c='mag'),
    dict(n=f'{ge_avg * 100:.0f}% vs {rn_avg * 100:.0f}%', l=f'Average map coverage, curiosity agent vs. random walk ({nseeds} seeds per map)', c='gold'),
]
best = combat[1]['episodes'][0]['demo'] if len(combat) > 1 else ''
D['clip'] = 'data:image/webp;base64,' + base64.b64encode(open(f'{OUT}/clip.webp', 'rb').read()).decode()
D['cliptext'] = (f'This clip is not a screen recording of the original run. It is 21 seconds of MAP03 episode 1 re-simulated from the demo file the combat bot wrote while playing: '
                 f'the engine replays the recorded inputs and produces the same game. All {len(demo_v)} combat episodes replayed this way and {nmatch} matched the live run’s kills, items and damage exactly. '
                 'That is the repro a developer gets attached to a ticket.')
D['covnote'] = 'MAP06 hits the same ceiling in every run for both agents (19.2–19.3%): the area reachable from spawn stays closed until something is triggered that neither agent finds. That is the cue for a goal-directed persona (keys, switches) rather than more exploration time.'
D['mapping'] = [
    dict(tag='Per-commit tier', h='Scripted smoke bot', p='Boot, spawn, move, fire, use and invariant checks on all 32 maps in about a second each. Cheap enough to gate every build.'),
    dict(tag='Exploration', h='Go-Explore with novelty weighting', p=f'Returns to rarely visited cells through save states. Over {nseeds} seeds it beat random walk on {wins} of 6 maps at equal budget, lost on {loss}, and tied on {6 - wins - loss}. Maps gated by keys or switches need a goal-seeking agent instead.'),
    dict(tag='State coverage', h='Transitions against a designer graph', p='Player states are classified each step and counted against the transitions a designer expects, so gaps (no level exit, few pickups) show up as missing edges.'),
    dict(tag='Invariants', h='Checks on every step', p='Ammo, health and armor ranges, monotonic kill and item counts, and inside-the-map and above-the-floor geometry checks.'),
    dict(tag='Triage', h='Re-run before filing', p=f'Each candidate is replayed from its save state in a fresh process, and stuck spots get an escape test and a nearby-monster check. {n_closed} of {n_cand} candidates were closed: {n_closed - 1} test artifacts and one bug in our own checks.'),
    dict(tag='Other engines', h='What changes on a bigger game', p='Replace the ViZDoom wrapper with an agent API into the game build: state read-out, actions, save/restore and replay capture (on Unreal, Gauntlet sessions plus network emulation). The checks, agents and triage flow keep their shape.'),
]
D['footer'] = ['Freedoom (freedoom.github.io) and ViZDoom (vizdoom.farama.org) are open source. Exploration follows Go-Explore (Ecoffet et al., Nature 2021) and EA SEED’s count-based curiosity testing (Gordillo et al., CoG 2021).',
               'Coverage counts 64-unit map cells whose area is at least half inside a sector; some of those cells are decorative or deliberately unreachable, so 100% is not attainable. Exploration runs use god mode so agents aren’t killed; combat runs do not.',
               'Harness code, raw results, demo recordings and repro save files are in the repository alongside this page.']

html = open('report/template.html').read().replace('__DATA__', json.dumps(D, separators=(',', ':')))
open('report/index.html', 'w').write(html)
print('wrote report/index.html', round(len(html) / 1e6, 2), 'MB', 'tickets', len(T))
