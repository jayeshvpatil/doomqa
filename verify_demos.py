import json, glob, os
from doomqa.env import make_game, read
res=[]
for f in sorted(glob.glob('out/combat_MAP*.json')):
    r=json.load(open(f)); m=r['map']
    g=make_game(m, god=False, skill=3, labels=True, sectors=True, timeout=2100, seed=3)
    for e in r['episodes']:
        g.replay_episode(os.path.join('out/demos',e['demo'])); last=None; t=0
        while not g.is_episode_finished():
            if t % 4 == 1:            # live reads happen at tic 1, 5, 9, ... (1 idle tic, then 4-tic actions)
                last=read(g) or last
            g.advance_action(); t+=1
        ok = last is not None and last['kills']==e['kills'] and last['damage_taken']==e['damage_taken'] and last['items']==e['items']
        res.append(dict(map=m, ep=e['ep'], live=[e['kills'],e['items'],e['damage_taken']], replay=[last['kills'],last['items'],last['damage_taken']] if last else None, match=ok))
    g.close()
json.dump(res, open('out/demo_verify.json','w'))
print(sum(r['match'] for r in res), '/', len(res))
for r in res:
    if not r['match']: print(r)
