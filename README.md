# doomqa: agentic end-to-end testing demo on Freedoom / ViZDoom

A small, working version of the agent-based QA harness from the IG Labs proposal, pointed at a real
open-source shooter: **Freedoom: Phase 2** running headless in **ViZDoom 1.3.2**.

## What's in here

| Path | What it is |
|---|---|
| `doomqa/env.py` | Game setup, buttons, discrete actions, state read-out, and `load()` with the idle-tic workaround (QA-001) |
| `doomqa/geometry.py` | Map geometry from sector data: wall segments, walkable 64-unit cells, sectors under the player's footprint |
| `doomqa/checks.py` | Per-step invariants (ammo, health, armor, monotonic counters, inside-map, above-floor) and the player-state classifier + designer graph |
| `doomqa/agents.py` | Smoke bot, random-walk baseline, Go-Explore curiosity agent, combat bot, stuck probe, deep-escape validation, fresh-process replay check |
| `doomqa/determinism.py` | Determinism suite: input replay vs. demo replay, repeated loads, save fidelity |
| `run_all.py` | The campaign: smoke on 32 maps, combat on 6, both explorers on 6, then replay of every finding |
| `seeds.py` | Extra seeds for the coverage comparison |
| `verify_demos.py` | Replays every combat demo and compares kills, items and damage with the live run |
| `perf_serial.py` | Throughput per map, one map at a time |
| `clip.py` | Renders a clip from a recorded demo |
| `report/` | `build_report.py` + `template.html` → `index.html` (the demo page) |
| `out/` | Raw results (JSON), recorded demos (`demos/*.lmp`), repro save files (`repro/*.sav`), screenshots |

## Run it

```bash
pip install vizdoom numpy pillow            # vizdoom ships Freedoom
python3 run_all.py                          # ~30 min on 2 cores
python3 seeds.py                            # optional, ~40 min
python3 verify_demos.py && python3 perf_serial.py
python3 report/build_report.py              # writes report/index.html
```

Run only some jobs: `python3 run_all.py smoke combat` (job kinds: `det smoke combat goexplore random`).

## Reproducing a finding

Every exploration finding ships as a save state plus the inputs that followed it:

```python
from doomqa.env import make_game, start_episode, load, ACTIONS, ACTION_NAMES, FRAME_SKIP
g = make_game('MAP04', god=True); start_episode(g)
load(g, 'out/repro/MAP04-random-001_start.sav')
for a in finding['repro']['inputs']:
    g.make_action(ACTIONS[ACTION_NAMES[a]], FRAME_SKIP)
```

Combat runs are recorded as engine demos (`out/demos/*.lmp`); `game.replay_episode(path)` replays them exactly.

## Things we learned about the engine (see the report for detail)

- **QA-001**: after the second `load()`, input is ignored until one idle tic runs. Always use `env.load()`.
- **QA-002**: a loaded save is not bit-identical to the live game; don't rebuild runs from input logs.
- **QA-003**: same seed and inputs don't reproduce a fight; demos do.
- `TURN_LEFT_RIGHT_DELTA` takes effect a tic late, so an immediate read shows no turn. Use the turn buttons and check the angle (`agents._turn_by`).

## Moving this to a production shooter

Replace `doomqa/env.py` with an agent API into the client's build (state read-out, actions, save/restore, demo
or replay capture). On Unreal that sits on Gauntlet sessions and the automation framework, with network
conditions from NetEmulation. `checks.py`, `agents.py` and the triage flow carry over unchanged in shape.
