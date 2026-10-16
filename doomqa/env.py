"""Thin wrapper around ViZDoom: one place that defines buttons, actions, variables and game setup."""
import os
import numpy as np
import vizdoom as vzd

WAD = os.path.join(os.path.dirname(vzd.__file__), 'freedoom2.wad')

BUTTONS = [vzd.Button.MOVE_FORWARD, vzd.Button.MOVE_BACKWARD, vzd.Button.MOVE_LEFT, vzd.Button.MOVE_RIGHT,
           vzd.Button.TURN_LEFT, vzd.Button.TURN_RIGHT, vzd.Button.USE, vzd.Button.ATTACK,
           vzd.Button.TURN_LEFT_RIGHT_DELTA]
F, B, SL, SR, TL, TR, USE, ATK, DELTA = range(9)


def _a(*on):
    v = [0] * 9
    for i in on:
        v[i] = 1
    return v


ACTIONS = {
    'fwd': _a(F), 'fwd_left': _a(F, TL), 'fwd_right': _a(F, TR), 'left': _a(TL), 'right': _a(TR),
    'back': _a(B), 'strafe_l': _a(SL), 'strafe_r': _a(SR), 'fwd_use': _a(F, USE), 'attack': _a(ATK), 'use': _a(USE),
}
ACTION_NAMES = list(ACTIONS)
NOOP = [0] * 9

VARS = [vzd.GameVariable.POSITION_X, vzd.GameVariable.POSITION_Y, vzd.GameVariable.POSITION_Z,
        vzd.GameVariable.ANGLE, vzd.GameVariable.HEALTH, vzd.GameVariable.ARMOR,
        vzd.GameVariable.SELECTED_WEAPON_AMMO, vzd.GameVariable.KILLCOUNT, vzd.GameVariable.ITEMCOUNT,
        vzd.GameVariable.DEAD, vzd.GameVariable.DAMAGECOUNT, vzd.GameVariable.DAMAGE_TAKEN]
VAR_NAMES = ['x', 'y', 'z', 'angle', 'health', 'armor', 'ammo', 'kills', 'items', 'dead', 'damage_dealt', 'damage_taken']

FRAME_SKIP = 4  # tics per action (Doom runs 35 tics/s)


class Game(vzd.DoomGame):
    """DoomGame plus a flag for whether god mode is re-applied each episode."""
    pass


def make_game(map_name, god=False, skill=3, seed=7, sectors=False, objects=False, labels=False,
              resolution=vzd.ScreenResolution.RES_320X240, timeout=0):
    g = Game()
    g.set_doom_game_path(WAD)
    g.set_doom_map(map_name)
    g.set_window_visible(False)
    g.set_sound_enabled(False)
    g.set_mode(vzd.Mode.PLAYER)
    g.set_screen_resolution(resolution)
    g.set_screen_format(vzd.ScreenFormat.RGB24)
    g.set_render_hud(True)
    g.set_sectors_info_enabled(sectors)
    g.set_objects_info_enabled(objects)
    g.set_labels_buffer_enabled(labels)
    g.set_available_buttons(BUTTONS)
    g.set_button_max_value(vzd.Button.TURN_LEFT_RIGHT_DELTA, 180)
    g.set_available_game_variables(VARS)
    g.set_doom_skill(skill)
    g.set_seed(seed)
    g.set_episode_timeout(timeout)
    g.add_game_args('+sv_cheats 1')
    g.init()
    g._god = god
    return g


def start_episode(g, record=''):
    """New episode; god mode re-applied because ZDoom resets player flags per episode."""
    g.new_episode(record)
    if g._god:
        g.send_game_command('god')
    g.make_action(NOOP, 1)


def read(g):
    s = g.get_state()
    if s is None:
        return None
    return dict(zip(VAR_NAMES, (float(v) for v in s.game_variables)))


def frame(g):
    s = g.get_state()
    return None if s is None else np.array(s.screen_buffer)


def load(g, path):
    """Load a save state. Works around a ViZDoom 1.3.2 defect found by this harness: after the second
    load in a session, the next make_action() inputs are ignored unless one idle tic runs first."""
    g.load(path)
    g.make_action(NOOP, 1)
