import json, os, sys, time, traceback
from multiprocessing import Pool
from doomqa.agents import smoke, explore, combat, replay_check
from doomqa import determinism
OUT = 'out'; os.makedirs(OUT, exist_ok=True)
EXPLORE_MAPS = ['MAP01', 'MAP02', 'MAP03', 'MAP04', 'MAP05', 'MAP06']
BUDGET = 120_000

def log(*a):
    with open(f'{OUT}/progress.log', 'a') as f: print(time.strftime('%H:%M:%S'), *a, file=f, flush=True)

def job(j):
    kind, m = j
    t = time.time()
    try:
        if kind == 'smoke': r = smoke(m, OUT)
        elif kind == 'combat': r = combat(m, OUT, episodes=4)
        elif kind == 'det': r = determinism.run()
        else:
            r, geo = explore(m, OUT, budget=BUDGET, mode=kind)
            json.dump(geo, open(f'{OUT}/geo_{m}.json', 'w'))
        json.dump(r, open(f'{OUT}/{kind}_{m}.json', 'w'))
        log('done', kind, m, round(time.time() - t, 1))
    except Exception:
        log('FAIL', kind, m, traceback.format_exc())

if __name__ == '__main__':
    import sys
    only = sys.argv[1:]
    jobs = [('det', 'ALL')] + [('smoke', f'MAP{i:02d}') for i in range(1, 33)] + [('combat', m) for m in EXPLORE_MAPS]
    jobs += [(k, m) for m in EXPLORE_MAPS for k in ('goexplore', 'random')]
    if only: jobs = [j for j in jobs if j[0] in only]
    with Pool(2) as p:
        p.map(job, jobs, chunksize=1)
    # replay verification: every finding and the first level exit, in a fresh process
    rep = {}
    for m in EXPLORE_MAPS:
        for mode in ('goexplore', 'random'):
            f = f'{OUT}/{mode}_{m}.json'
            if not os.path.exists(f): continue
            r = json.load(open(f))
            for fd in r['findings']:
                if fd.get('repro'):
                    rep[fd['id']] = replay_check(m, fd['repro'], OUT, fd['id'], fd['pos'], fd['kind'])
            if r['exits'] and r['exits'][0].get('repro'):
                rep[f'{m}-{mode}-exit'] = replay_check(m, r['exits'][0]['repro'], OUT, f'{m}-{mode}-exit', kind='exit')
        log('replayed', m)
    json.dump(rep, open(f'{OUT}/replays.json', 'w'))
    log('ALL DONE')
