"""Invariants checked on every step, and the player-state classifier used for transition coverage."""
import math

MONSTERS = {n.lower() for n in [
    'ZombieMan', 'ShotgunGuy', 'ChaingunGuy', 'DoomImp', 'Demon', 'Spectre', 'LostSoul', 'Cacodemon',
    'HellKnight', 'BaronOfHell', 'Arachnotron', 'PainElemental', 'Revenant', 'Fatso', 'Archvile',
    'SpiderMastermind', 'Cyberdemon', 'WolfensteinSS', 'CommanderKeen']}

# The "designer graph": transitions we expect a match to exercise.
EXPECTED_EDGES = [
    ('Spawn', 'Explore'), ('Explore', 'Combat'), ('Combat', 'Explore'), ('Combat', 'Hurt'),
    ('Hurt', 'Combat'), ('Hurt', 'Explore'), ('Explore', 'Pickup'), ('Pickup', 'Explore'),
    ('Hurt', 'Pickup'), ('Combat', 'Pickup'), ('Pickup', 'Combat'), ('Hurt', 'Dead'), ('Combat', 'Dead'),
    ('Dead', 'Spawn'), ('Explore', 'LevelExit'), ('Explore', 'Hurt'),
]


def classify(prev, cur, enemy_visible):
    if cur['dead'] > 0 or cur['health'] <= 0:
        return 'Dead'
    if prev is not None and cur['health'] < prev['health']:
        return 'Hurt'
    if prev is not None and cur['items'] > prev['items']:
        return 'Pickup'
    if enemy_visible:
        return 'Combat'
    return 'Explore'


def invariants(prev, cur, geom=None, floor_heights=None):
    """Return list of (rule, detail) violations. prev may be None at episode start."""
    bad = []
    for k in ('x', 'y', 'z', 'health', 'ammo'):
        if not math.isfinite(cur[k]):
            bad.append(('finite_state', f'{k} is {cur[k]}'))
    if cur['ammo'] < 0:
        bad.append(('ammo_non_negative', f"ammo={cur['ammo']}"))
    if cur['health'] > 200:
        bad.append(('health_cap', f"health={cur['health']} > 200"))
    if cur['armor'] > 200 or cur['armor'] < 0:
        bad.append(('armor_range', f"armor={cur['armor']}"))
    if (cur['dead'] > 0) != (cur['health'] <= 0):
        bad.append(('dead_flag_consistent', f"dead={cur['dead']} health={cur['health']}"))
    if prev is not None:
        if cur['kills'] < prev['kills']:
            bad.append(('kills_monotonic', f"{prev['kills']} -> {cur['kills']}"))
        if cur['items'] < prev['items']:
            bad.append(('items_monotonic', f"{prev['items']} -> {cur['items']}"))
    if geom is not None:
        under = geom.sectors_under(cur['x'], cur['y'])
        if not under:
            bad.append(('inside_map', f"({cur['x']:.0f},{cur['y']:.0f}) is under no sector"))
        elif floor_heights is not None:
            lo = min(floor_heights[s] for s in under)
            if cur['z'] < lo - 2:
                bad.append(('above_floor', f"z={cur['z']:.1f} is below every floor under the player (lowest {lo:.1f}, sectors {sorted(under)})"))
    return bad
