import sys, numpy as np
from PIL import Image
from doomqa.env import make_game
m, demo, out, secs = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]); start = float(sys.argv[5]) if len(sys.argv) > 5 else 0
g = make_game(m, god=False, skill=3, labels=True, sectors=True, timeout=2100, seed=3)
g.replay_episode(demo)
frames=[]; t=0
while not g.is_episode_finished() and t < (start+secs)*35:
    s=g.get_state()
    if s is not None and t % 3 == 0 and t >= start*35:
        frames.append(Image.fromarray(np.array(s.screen_buffer)))
    g.advance_action(); t+=1
g.close()
frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000*3/35), loop=0, quality=70, method=4)
print(len(frames), 'frames')
