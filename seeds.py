import json, sys
from multiprocessing import Pool
from doomqa.agents import explore
MAPS=['MAP01','MAP02','MAP03','MAP04','MAP05','MAP06']
def job(j):
    m,mode,seed=j
    r,_=explore(m,'out_seeds',budget=120_000,mode=mode,seed=seed)
    return dict(map=m,mode=mode,seed=seed,coverage=r['coverage'],exits=len(r['exits']),findings=len(r['findings']))
if __name__=='__main__':
    jobs=[(m,k,s) for s in (2,3) for m in MAPS for k in ('goexplore','random')]
    with Pool(2) as p: res=p.map(job,jobs,chunksize=1)
    json.dump(res,open('out/seeds.json','w'))
