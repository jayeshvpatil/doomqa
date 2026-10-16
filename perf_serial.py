import json, time, math
import numpy as np
from doomqa.env import make_game, start_episode, read, ACTIONS, FRAME_SKIP
from doomqa.agents import Policy
import vizdoom as vzd
rows=[]
for i in range(1,33):
    m=f'MAP{i:02d}'
    g=make_game(m,god=True,resolution=vzd.ScreenResolution.RES_320X240); start_episode(g)
    pol=Policy(np.random.default_rng(0)); n=0; ms=[]
    t=time.time()
    while n<2800 and not g.is_episode_finished():
        s=time.perf_counter(); g.make_action(ACTIONS[pol()],FRAME_SKIP); ms.append((time.perf_counter()-s)*1000/FRAME_SKIP); n+=FRAME_SKIP
    rows.append(dict(map=m,tics_per_s=round(n/(time.time()-t)),ms_per_tic_p50=round(float(np.median(ms)),3),ms_per_tic_p99=round(float(np.percentile(ms,99)),3)))
    g.close()
json.dump(rows,open('out/perf_serial.json','w'))
