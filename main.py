# -*- coding: utf-8 -*-
import kivy
kivy.require('2.0.0')

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
import math
import array
import struct
import wave
import io
import os
import tempfile
import random
import threading

BOARD_SIZE = 15
CELL_SIZE = 38
MARGIN = 28
PIECE_RADIUS = 16
BOARD_PX = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)

EMPTY = 0
BLACK = 1
WHITE = 2

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


def _gen_wav_data(samples_mono, sample_rate=22050):
    import struct
    n = len(samples_mono)
    data = array.array('h')
    for s in samples_mono:
        clamped = max(-1.0, min(1.0, s))
        val = int(clamped * 32767)
        data.append(val)
        data.append(val)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())
    return buf.getvalue()


def _gen_place_sound():
    sr = 22050
    n = int(sr * 0.03)
    samples = []
    for i in range(n):
        t = i / sr
        env = math.exp(-60 * t)
        s = math.sin(2 * math.pi * 1200 * t) * env * 0.4
        s += math.sin(2 * math.pi * 1800 * t) * env * 0.2
        samples.append(s)
    return _gen_wav_data(samples)


def _gen_win_sound():
    sr = 22050
    samples = []
    freqs = [523, 659, 784, 1047, 1319]
    seg = int(sr * 0.12)
    for f in freqs:
        for i in range(seg):
            t = i / sr
            env = 1 - i / seg
            s = math.sin(2 * math.pi * f * t) * env * 0.35
            samples.append(s)
    return _gen_wav_data(samples)


def _gen_lose_sound():
    sr = 22050
    samples = []
    freqs = [784, 659, 523, 392]
    seg = int(sr * 0.15)
    for f in freqs:
        for i in range(seg):
            t = i / sr
            env = 1 - i / seg
            s = math.sin(2 * math.pi * f * t) * env * 0.3
            samples.append(s)
    return _gen_wav_data(samples)


def _gen_invalid_sound():
    sr = 22050
    n = int(sr * 0.15)
    samples = []
    for i in range(n):
        t = i / sr
        s = math.sin(2 * math.pi * 180 * t) * 0.3
        samples.append(s)
    return _gen_wav_data(samples)


def _gen_bgm_data():
    sr = 22050
    bpmin = 70
    beat_len = 60.0 / bpmin
    total_beats = 16
    total_n = int(sr * beat_len * total_beats)
    chords = [[262, 330, 392], [294, 370, 440], [330, 415, 494],
              [262, 330, 392], [349, 440, 523], [294, 370, 440]]
    pattern = []
    for chord, beats in zip(chords, [4, 2, 2, 4, 2, 2]):
        pattern.extend([chord] * beats)
    samples = []
    for bi, chord in enumerate(pattern):
        for i in range(int(sr * beat_len)):
            t = (bi * beat_len + i / sr)
            env = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 2))
            s = sum(math.sin(2 * math.pi * f * t) + 0.3 * math.sin(2 * math.pi * f * 0.5 * t) for f in chord)
            s = s / len(chord) * env * 0.12
            samples.append(s)
    while len(samples) < total_n:
        samples.append(0)
    return _gen_wav_data(samples[:total_n])


class BoardWidget(Widget):
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self.size_hint = (None, None)
        self.size = (BOARD_PX, BOARD_PX)
        self.bind(size=self._redraw)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return
        self.game._on_touch(touch.x, touch.y)

    def _redraw(self, *args):
        Clock.schedule_once(lambda dt: self.game._draw_board(), 0)

    def draw(self):
        self.canvas.clear()

        with self.canvas:
            Color(0.871, 0.722, 0.529, 1)
            Rectangle(pos=self.pos, size=self.size)

            Color(0.545, 0.271, 0.075, 1)
            Line(rectangle=(self.x, self.y, self.size[0], self.size[1]), width=2)

            for i in range(BOARD_SIZE):
                x = self.x + MARGIN + i * CELL_SIZE
                Line(points=[x, self.y + MARGIN, x, self.y + MARGIN + (BOARD_SIZE - 1) * CELL_SIZE], width=1)
                y = self.y + MARGIN + i * CELL_SIZE
                Line(points=[self.x + MARGIN, y, self.x + MARGIN + (BOARD_SIZE - 1) * CELL_SIZE, y], width=1)

            stars = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
            for r, c in stars:
                px = self.x + MARGIN + c * CELL_SIZE
                py = self.y + MARGIN + r * CELL_SIZE
                Ellipse(pos=(px - 4, py - 4), size=(8, 8))

            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if self.game.board[r][c] != EMPTY:
                        self._draw_piece(r, c, self.game.board[r][c], False)

            for r, c in self.game.last_moves_this_turn:
                self._draw_piece(r, c, self.game.board[r][c], True)

    def _draw_piece(self, row, col, player, highlight):
        x = self.x + MARGIN + col * CELL_SIZE
        y = self.y + MARGIN + row * CELL_SIZE
        if player == BLACK:
            Color(0.1, 0.1, 0.1, 1)
            Ellipse(pos=(x - PIECE_RADIUS, y - PIECE_RADIUS), size=(PIECE_RADIUS * 2, PIECE_RADIUS * 2))
        else:
            Color(1, 1, 1, 1)
            Ellipse(pos=(x - PIECE_RADIUS, y - PIECE_RADIUS), size=(PIECE_RADIUS * 2, PIECE_RADIUS * 2))
            Color(0.7, 0.7, 0.7, 1)
            Line(ellipse=(x - PIECE_RADIUS, y - PIECE_RADIUS, PIECE_RADIUS * 2, PIECE_RADIUS * 2), width=1)
        if highlight:
            Color(1, 0.2, 0.2, 1)
            Ellipse(pos=(x - 4, y - 4), size=(8, 8))


class SoundManagerKivy:
    def __init__(self):
        self.sfx_enabled = True
        self.bgm_playing = False
        self.place_sound = None
        self.win_sound = None
        self.lose_sound = None
        self.invalid_sound = None
        self.bgm = None
        self._init_sounds()

    def _init_sounds(self):
        self._load_from_data('place', _gen_place_sound)
        self._load_from_data('win', _gen_win_sound)
        self._load_from_data('lose', _gen_lose_sound)
        self._load_from_data('invalid', _gen_invalid_sound)
        self._load_bgm()

    def _load_from_data(self, name, gen_func):
        try:
            data = gen_func()
            path = os.path.join(tempfile.gettempdir(), f'liuziqi_{name}.wav')
            with open(path, 'wb') as f:
                f.write(data)
            sound = SoundLoader.load(path)
            setattr(self, f'{name}_sound', sound)
        except Exception as e:
            print(f"Sound {name} load error:", e)

    def _load_bgm(self):
        try:
            data = _gen_bgm_data()
            path = os.path.join(tempfile.gettempdir(), 'liuziqi_bgm.wav')
            with open(path, 'wb') as f:
                f.write(data)
            self.bgm = SoundLoader.load(path)
            if self.bgm:
                self.bgm.loop = True
                self.bgm.volume = 0.3
        except Exception as e:
            print("BGM load error:", e)

    def play_place(self):
        if self.sfx_enabled and self.place_sound:
            self.place_sound.play()

    def play_win(self):
        if self.sfx_enabled and self.win_sound:
            self.win_sound.play()

    def play_lose(self):
        if self.sfx_enabled and self.lose_sound:
            self.lose_sound.play()

    def play_invalid(self):
        if self.sfx_enabled and self.invalid_sound:
            self.invalid_sound.play()

    def start_bgm(self):
        if self.bgm and not self.bgm_playing:
            self.bgm.play()
            self.bgm_playing = True

    def stop_bgm(self):
        if self.bgm and self.bgm_playing:
            self.bgm.stop()
            self.bgm_playing = False


class GameLogic:
    def __init__(self, app):
        self.app = app
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.stones_this_turn = 0
        self.max_stones_this_turn = 1
        self.game_over = False
        self.move_history = []
        self.last_move = None
        self.last_moves_this_turn = []
        self.ai_enabled = True
        self.ai_player = WHITE
        self.ai_thinking = False

    def reset(self):
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.stones_this_turn = 0
        self.max_stones_this_turn = 1
        self.game_over = False
        self.move_history = []
        self.last_move = None
        self.last_moves_this_turn = []
        self.ai_thinking = False

    def place_stone(self, row, col, is_ai=False):
        if self.game_over or not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return False
        if self.board[row][col] != EMPTY:
            return False

        self.board[row][col] = self.current_player
        self.move_history.append((row, col, self.current_player))
        self.last_move = (row, col)
        self.last_moves_this_turn.append((row, col))
        self.stones_this_turn += 1

        if not is_ai:
            self.app.sound.play_place()

        if self._check_win(row, col, self.current_player):
            self.game_over = True
            return 'win'

        if self._is_draw():
            self.game_over = True
            return 'draw'

        if self.stones_this_turn >= self.max_stones_this_turn:
            self.current_player = 3 - self.current_player
            self.stones_this_turn = 0
            self.max_stones_this_turn = 2
            self.last_moves_this_turn = []

        return True

    def _check_win(self, row, col, player):
        for dr, dc in DIRECTIONS:
            count = 1
            r, c = row + dr, col + dc
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
                count += 1
                r += dr
                c += dc
            r, c = row - dr, col - dc
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
                count += 1
                r -= dr
                c -= dc
            if count >= 6:
                return True
        return False

    def _is_draw(self):
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] == EMPTY:
                    return False
        return True

    def undo(self):
        if self.game_over or self.ai_thinking or not self.move_history:
            return False

        if self.stones_this_turn > 0:
            r, c, p = self.move_history.pop()
            self.board[r][c] = EMPTY
            self.stones_this_turn -= 1
            self.current_player = p
        else:
            last_player = self.move_history[-1][2]
            while self.move_history and self.move_history[-1][2] == last_player:
                r, c, _ = self.move_history.pop()
                self.board[r][c] = EMPTY
            self.current_player = last_player
            self.stones_this_turn = 0
            self.max_stones_this_turn = 2 if len(self.move_history) > 0 else 1

        self._recalc_last_moves()
        return True

    def _recalc_last_moves(self):
        self.last_moves_this_turn = []
        if not self.move_history:
            self.last_move = None
            return
        cur = self.move_history[-1][2]
        for i in range(len(self.move_history) - 1, -1, -1):
            if self.move_history[i][2] == cur:
                self.last_moves_this_turn.append((self.move_history[i][0], self.move_history[i][1]))
            else:
                break
        self.last_moves_this_turn = self.last_moves_this_turn[:2]
        self.last_move = self.move_history[-1][:2]

    def get_ai_moves(self, count):
        scored = self._score_all_positions(self.ai_player)
        if not scored:
            if self.board[7][7] == EMPTY:
                return [(7, 7)]
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if self.board[r][c] == EMPTY:
                        return [(r, c)]
            return []
        scored.sort(key=lambda x: -x[2])
        best = []
        for r, c, _ in scored:
            if self.board[r][c] == EMPTY:
                best.append((r, c))
                if len(best) >= count:
                    break
        if not best:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if self.board[r][c] == EMPTY:
                        best.append((r, c))
                        if len(best) >= count:
                            break
                if len(best) >= count:
                    break
        return best[:count]

    def _score_all_positions(self, player):
        opp = 3 - player
        scored = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY:
                    continue
                score = self._eval_pos(r, c, player, opp)
                scored.append((r, c, score))
        return scored

    def _eval_pos(self, row, col, player, opp):
        score = 0.0
        center = BOARD_SIZE // 2
        dist = abs(row - center) + abs(col - center)
        score += max(0, 10 - dist) * 0.5
        for dr, dc in DIRECTIONS:
            score += self._line_score(row, col, dr, dc, player, opp)
        return score

    def _line_score(self, row, col, dr, dc, player, opp):
        score = 0
        own_f = self._count_dir(row, col, dr, dc, player)
        own_b = self._count_dir(row, col, -dr, -dc, player)
        own_cnt = 1 + own_f + own_b
        opp_f = self._count_dir(row, col, dr, dc, opp)
        opp_b = self._count_dir(row, col, -dr, -dc, opp)
        opp_cnt = 1 + opp_f + opp_b
        own_open = self._open_ends(row, col, dr, dc, own_f, own_b)
        opp_open = self._open_ends(row, col, dr, dc, opp_f, opp_b)

        if own_cnt >= 6:
            score += 100000
        elif own_cnt == 5:
            score += 10000 * own_open
        elif own_cnt == 4:
            score += 1000 * own_open
        elif own_cnt == 3:
            score += 100 * own_open
        elif own_cnt == 2:
            score += 10 * own_open

        if opp_cnt >= 6:
            score += 50000
        elif opp_cnt == 5:
            score += 8000 * opp_open
        elif opp_cnt == 4:
            score += 800 * opp_open
        elif opp_cnt == 3:
            score += 80 * opp_open

        return score

    def _count_dir(self, row, col, dr, dc, player):
        cnt = 0
        r, c = row + dr, col + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
            cnt += 1
            r += dr
            c += dc
        return cnt

    def _open_ends(self, row, col, dr, dc, fwd, bwd):
        n = 0
        r = row + dr * (fwd + 1)
        c = col + dc * (fwd + 1)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == EMPTY:
            n += 1
        r = row - dr * (bwd + 1)
        c = col - dc * (bwd + 1)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == EMPTY:
            n += 1
        return n


class ControlBar(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 48
        self.padding = [4, 4]
        self.spacing = 4

        self.status_label = Label(text='黑棋走', size_hint_x=0.35, halign='left',
                                  valign='middle', font_size=16, bold=True,
                                  color=(0.1, 0.1, 0.1, 1))
        self.status_label.bind(size=self.status_label.setter('text_size'))
        self.add_widget(self.status_label)

        self.move_label = Label(text='', size_hint_x=0.15, halign='left',
                                valign='middle', font_size=12,
                                color=(0.4, 0.4, 0.4, 1))
        self.move_label.bind(size=self.move_label.setter('text_size'))
        self.add_widget(self.move_label)

        def mk_btn(text, callback, w=0.12):
            btn = Button(text=text, size_hint_x=w, font_size=13, bold=False,
                         background_normal='', background_color=(0.7, 0.5, 0.3, 1),
                         color=(1, 1, 1, 1))
            btn.bind(on_press=callback)
            self.add_widget(btn)
            return btn

        mk_btn('音乐', lambda _: self._toggle_bgm())
        mk_btn('音效', lambda _: self._toggle_sfx())
        self.ai_btn = mk_btn('人机', lambda _: self._toggle_ai())
        mk_btn('悔棋', lambda _: self.app.do_undo())
        mk_btn('重开', lambda _: self.app.do_restart())

    def _toggle_bgm(self):
        s = self.app.sound
        if s.bgm_playing:
            s.stop_bgm()
        else:
            s.start_bgm()

    def _toggle_sfx(self):
        self.app.sound.sfx_enabled = not self.app.sound.sfx_enabled

    def _toggle_ai(self):
        self.app.game.ai_enabled = not self.app.game.ai_enabled
        self.ai_btn.background_color = (0.7, 0.5, 0.3, 1) if self.app.game.ai_enabled else (0.5, 0.5, 0.5, 1)
        if self.app.game.ai_enabled and self.app.game.current_player == self.app.game.ai_player and not self.app.game.game_over:
            self.app._schedule_ai()

    def update_status(self):
        g = self.app.game
        if g.game_over:
            return
        name = '黑棋' if g.current_player == BLACK else '白棋'
        rem = g.max_stones_this_turn - g.stones_this_turn
        self.status_label.text = f'{name}走 (还需{rem}子)'
        self.move_label.text = f'第{len(g.move_history)}手'

    def show_result(self, text):
        self.status_label.text = text
        self.move_label.text = ''


class SixInARowApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = '六子棋'
        self.sound = SoundManagerKivy()
        self.game = GameLogic(self)

    def build(self):
        root = BoxLayout(orientation='vertical', padding=0, spacing=0)

        self.board_widget = BoardWidget(self)
        root.add_widget(self.board_widget)

        self.control_bar = ControlBar(self)
        root.add_widget(self.control_bar)

        Clock.schedule_once(lambda dt: self._start_bgm(), 1)
        Clock.schedule_once(lambda dt: self.board_widget.draw(), 0)

        return root

    def _start_bgm(self):
        self.sound.start_bgm()
        self.control_bar.update_status()

    def _on_touch(self, tx, ty):
        g = self.game
        if g.game_over or g.ai_thinking:
            return
        if g.ai_enabled and g.current_player != BLACK:
            return

        x = tx - self.board_widget.x
        y = ty - self.board_widget.y
        col = round((x - MARGIN) / CELL_SIZE)
        row = round((y - MARGIN) / CELL_SIZE)
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            self.sound.play_invalid()
            return
        if g.board[row][col] != EMPTY:
            self.sound.play_invalid()
            return

        self._do_place(row, col)

    def _do_place(self, row, col, is_ai=False):
        g = self.game
        result = g.place_stone(row, col, is_ai)
        self.board_widget.draw()
        self.control_bar.update_status()

        if result == 'win':
            winner = '黑棋' if g.current_player == BLACK else '白棋'
            self.control_bar.show_result(f'{winner} 获胜！')
            if g.ai_enabled:
                if g.current_player == g.ai_player:
                    self.sound.play_win()
                else:
                    self.sound.play_lose()
            else:
                self.sound.play_win()
            self._show_popup(f'{winner} 获胜！')
            return
        elif result == 'draw':
            self.control_bar.show_result('平局！')
            self.sound.play_win()
            self._show_popup('平局！')
            return
        elif not result:
            return

        self._schedule_ai()

    def _schedule_ai(self):
        g = self.game
        if g.ai_enabled and g.current_player == g.ai_player and not g.game_over:
            Clock.schedule_once(lambda dt: self._run_ai(), 0.3)

    def _run_ai(self):
        g = self.game
        if g.game_over or g.ai_thinking:
            return
        if not g.ai_enabled or g.current_player != g.ai_player:
            return

        g.ai_thinking = True
        self.control_bar.status_label.text = 'AI思考中...'

        def ai_thread():
            try:
                remaining = g.max_stones_this_turn - g.stones_this_turn
                moves = g.get_ai_moves(remaining)
                Clock.schedule_once(lambda dt: self._apply_ai(moves), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._ai_error(str(e)), 0)

        threading.Thread(target=ai_thread, daemon=True).start()

    def _apply_ai(self, moves):
        g = self.game
        g.ai_thinking = False
        for r, c in moves:
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and g.board[r][c] == EMPTY:
                self._do_place(r, c, is_ai=True)
                if g.game_over:
                    return

    def _ai_error(self, msg):
        self.game.ai_thinking = False
        self.control_bar.status_label.text = 'AI出错'
        print('AI error:', msg)

    def do_undo(self):
        if not self.sound.sfx_enabled:
            pass
        if self.game.undo():
            self.board_widget.draw()
            self.control_bar.update_status()
        else:
            self.sound.play_invalid()

    def do_restart(self):
        self.game.reset()
        self.board_widget.draw()
        self.control_bar.update_status()
        if self.game.ai_enabled and self.game.current_player == self.game.ai_player:
            self._schedule_ai()

    def _show_popup(self, text):
        popup = Popup(title='游戏结束', content=Label(text=text, font_size=18),
                      size_hint=(0.6, 0.3), auto_dismiss=True)
        popup.open()


if __name__ == '__main__':
    SixInARowApp().run()
