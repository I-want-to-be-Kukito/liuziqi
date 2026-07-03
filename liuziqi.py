# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, ttk
import math
import array
import io
import random
import threading
import time
import sys
import os

BOARD_SIZE = 15
CELL_SIZE = 40
MARGIN = 32
PIECE_RADIUS = 17
BOARD_PX = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)

EMPTY = 0
BLACK = 1
WHITE = 2

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


class SoundManager:
    def __init__(self):
        self.pygame = None
        self.initialized = False
        self.bgm_playing = False
        self.sfx_enabled = True
        self._init_pygame()

    def _init_pygame(self):
        try:
            import pygame
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
            self.pygame = pygame
            self.initialized = True
            self._gen_all_sounds()
        except Exception as e:
            print("Sound init failed:", e)

    def _make_wav_bytes(self, samples_mono):
        scaled = [max(-32767, min(32767, int(s * 32767))) for s in samples_mono]
        stereo = array.array('h')
        for s in scaled:
            stereo.append(s)
            stereo.append(s)
        return stereo.tobytes()

    def _gen_tone(self, freq, duration, volume=0.5, decay=0):
        sr = 22050
        n = int(sr * duration)
        samples = []
        for i in range(n):
            t = i / sr
            env = 1.0
            if decay > 0:
                env = math.exp(-decay * t)
            s = math.sin(2 * math.pi * freq * t) * env * volume
            samples.append(s)
        return samples

    def _gen_all_sounds(self):
        # place stone: two-layer click
        sr = 22050
        n1 = int(sr * 0.02)
        click = []
        for i in range(n1):
            t = i / sr
            env = 1 - i / n1
            s = math.sin(2 * math.pi * 1200 * t) * env * 0.4
            s += math.sin(2 * math.pi * 1800 * t) * env * 0.2
            click.append(s)
        self.place_sound = self._make_wav_bytes(click)

        # win: triumphant ascending arpeggio
        win_samples = []
        freqs = [523, 659, 784, 1047, 1319]
        seg = int(sr * 0.12)
        for fi, f in enumerate(freqs):
            for i in range(seg):
                t = i / sr
                env = 1 - i / seg
                s = math.sin(2 * math.pi * f * t) * env * 0.35
                win_samples.append(s)
        self.win_sound = self._make_wav_bytes(win_samples)

        # lose: descending tones
        lose_samples = []
        lfreqs = [784, 659, 523, 392]
        seg = int(sr * 0.15)
        for fi, f in enumerate(lfreqs):
            for i in range(seg):
                t = i / sr
                env = 1 - i / seg
                s = math.sin(2 * math.pi * f * t) * env * 0.3
                lose_samples.append(s)
        self.lose_sound = self._make_wav_bytes(lose_samples)

        # invalid: low buzz
        inv = self._gen_tone(180, 0.15, 0.3)
        self.invalid_sound = self._make_wav_bytes(inv)

        # BGM: gentle ambient loop ~10s
        bgm_samples = []
        bpmin = 70
        beat_len = 60 / bpmin
        sr_bgm = 22050
        total_beats = 16
        total_n = int(sr_bgm * beat_len * total_beats)

        progression = [
            ([262, 330, 392], 4),
            ([294, 370, 440], 2),
            ([330, 415, 494], 2),
            ([262, 330, 392], 4),
            ([349, 440, 523], 2),
            ([294, 370, 440], 2),
        ]
        chord_pattern = []
        for chord, beats in progression:
            chord_pattern.extend([chord] * beats)

        for bi, chord in enumerate(chord_pattern):
            beat_start = bi * beat_len
            for i in range(int(sr_bgm * beat_len)):
                t = (beat_start + i / sr_bgm)
                env = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 2))
                s = 0
                for f in chord:
                    s += math.sin(2 * math.pi * f * t)
                    s += math.sin(2 * math.pi * f * 0.5 * t) * 0.3
                s = s / len(chord) * env * 0.12
                bgm_samples.append(s)

        # pad to full length
        while len(bgm_samples) < total_n:
            bgm_samples.append(0)

        self.bgm_data = self._make_wav_bytes(bgm_samples[:total_n])

    def play_place(self):
        if self.initialized and self.sfx_enabled:
            s = self.pygame.mixer.Sound(buffer=self.place_sound)
            s.play()

    def play_win(self):
        if self.initialized and self.sfx_enabled:
            s = self.pygame.mixer.Sound(buffer=self.win_sound)
            s.play()

    def play_lose(self):
        if self.initialized and self.sfx_enabled:
            s = self.pygame.mixer.Sound(buffer=self.lose_sound)
            s.play()

    def play_invalid(self):
        if self.initialized and self.sfx_enabled:
            s = self.pygame.mixer.Sound(buffer=self.invalid_sound)
            s.play()

    def start_bgm(self):
        if self.initialized and not self.bgm_playing:
            try:
                self.pygame.mixer.music.load(io.BytesIO(self.bgm_data))
                self.pygame.mixer.music.set_volume(0.3)
                self.pygame.mixer.music.play(-1)
                self.bgm_playing = True
            except Exception as e:
                print("BGM error:", e)

    def stop_bgm(self):
        if self.initialized and self.bgm_playing:
            self.pygame.mixer.music.stop()
            self.bgm_playing = False


class SixInARow:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("六子棋")
        self.win.resizable(False, False)

        self.sound = SoundManager()

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

        self.bgm_on = tk.BooleanVar(value=True)

        self._build_ui()
        self._draw_board()
        self.sound.start_bgm()
        self._update_status()

        if self.ai_enabled and self.current_player == self.ai_player:
            self.win.after(300, self._ai_move)

    def _build_ui(self):
        self.cv = tk.Canvas(self.win, width=BOARD_PX, height=BOARD_PX,
                            bg="#DEB887", highlightthickness=0)
        self.cv.pack()
        self.cv.bind("<Button-1>", self._on_click)

        ctrl = tk.Frame(self.win, bg="#DEB887")
        ctrl.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.status = tk.Label(ctrl, text="", font=("Microsoft YaHei", 11, "bold"),
                               bg="#DEB887", width=30, anchor=tk.W)
        self.status.pack(side=tk.LEFT, padx=5)

        self.move_info = tk.Label(ctrl, text="", font=("Microsoft YaHei", 9),
                                  bg="#DEB887", fg="#555555", anchor=tk.W)
        self.move_info.pack(side=tk.LEFT, padx=5)

        btn_frame = tk.Frame(ctrl, bg="#DEB887")
        btn_frame.pack(side=tk.RIGHT)

        self.bgm_btn = tk.Checkbutton(btn_frame, text="音乐", variable=self.bgm_on,
                                      font=("Microsoft YaHei", 10), bg="#DEB887",
                                      command=self._toggle_bgm)
        self.bgm_btn.pack(side=tk.LEFT, padx=2)

        self.sfx_btn = tk.Button(btn_frame, text="音效", font=("Microsoft YaHei", 10),
                                 command=self._toggle_sfx, width=4)
        self.sfx_btn.pack(side=tk.LEFT, padx=2)

        self.ai_btn = tk.Button(btn_frame, text="人机", font=("Microsoft YaHei", 10),
                                command=self._toggle_ai, width=4)
        self.ai_btn.pack(side=tk.LEFT, padx=2)

        undo_btn = tk.Button(btn_frame, text="悔棋", font=("Microsoft YaHei", 10),
                             command=self._undo, width=4)
        undo_btn.pack(side=tk.LEFT, padx=2)

        restart_btn = tk.Button(btn_frame, text="重开", font=("Microsoft YaHei", 10),
                                command=self._restart, width=4)
        restart_btn.pack(side=tk.LEFT, padx=2)

    def _board_to_pixel(self, row, col):
        return MARGIN + col * CELL_SIZE, MARGIN + row * CELL_SIZE

    def _pixel_to_board(self, x, y):
        col = round((x - MARGIN) / CELL_SIZE)
        row = round((y - MARGIN) / CELL_SIZE)
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            return row, col
        return None

    def _draw_board(self):
        self.cv.delete("all")
        self.cv.create_rectangle(0, 0, BOARD_PX, BOARD_PX,
                                 fill="#DEB887", outline="#8B4513", width=2)

        for i in range(BOARD_SIZE):
            x = MARGIN + i * CELL_SIZE
            self.cv.create_line(x, MARGIN, x, MARGIN + (BOARD_SIZE - 1) * CELL_SIZE,
                                fill="#8B4513", width=1)
            y = MARGIN + i * CELL_SIZE
            self.cv.create_line(MARGIN, y, MARGIN + (BOARD_SIZE - 1) * CELL_SIZE, y,
                                fill="#8B4513", width=1)

        stars = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
        for r, c in stars:
            px, py = self._board_to_pixel(r, c)
            self.cv.create_oval(px - 4, py - 4, px + 4, py + 4,
                                fill="#8B4513", outline="")

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY:
                    self._draw_piece(r, c, self.board[r][c], highlight=False)

        for r, c in self.last_moves_this_turn:
            self._draw_piece(r, c, self.board[r][c], highlight=True)

    def _draw_piece(self, row, col, player, highlight=False):
        x, y = self._board_to_pixel(row, col)
        color = "#000000" if player == BLACK else "#FFFFFF"
        outline = "#333333" if player == BLACK else "#AAAAAA"

        self.cv.create_oval(x - PIECE_RADIUS, y - PIECE_RADIUS,
                            x + PIECE_RADIUS, y + PIECE_RADIUS,
                            fill=color, outline=outline, width=1)
        if highlight:
            self.cv.create_oval(x - 4, y - 4, x + 4, y + 4,
                                fill="#FF4444", outline="")

    def _on_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        if self.ai_enabled and self.current_player != BLACK:
            return
        pos = self._pixel_to_board(event.x, event.y)
        if pos is None:
            self.sound.play_invalid()
            return
        row, col = pos
        if self.board[row][col] != EMPTY:
            self.sound.play_invalid()
            return
        self._place_stone(row, col)

    def _place_stone(self, row, col, is_ai=False):
        if self.game_over:
            return

        self.board[row][col] = self.current_player
        self.move_history.append((row, col, self.current_player))
        self.last_move = (row, col)
        self.last_moves_this_turn.append((row, col))
        self.stones_this_turn += 1

        if not is_ai:
            self.sound.play_place()

        self._draw_board()

        if self._check_win(row, col, self.current_player):
            self.game_over = True
            winner = "黑棋" if self.current_player == BLACK else "白棋"
            self.status.config(text=f"{winner} 获胜！")
            self.move_info.config(text="")
            if (self.ai_enabled and
                ((self.current_player == self.ai_player) or
                 (not self.ai_enabled))):
                self.sound.play_win()
            elif self.ai_enabled:
                self.sound.play_lose()
            else:
                self.sound.play_win()
            messagebox.showinfo("游戏结束", f"{winner} 获胜！")
            return

        if self._is_draw():
            self.game_over = True
            self.status.config(text="平局！")
            self.move_info.config(text="")
            self.sound.play_win()
            messagebox.showinfo("游戏结束", "平局！")
            return

        if self.stones_this_turn >= self.max_stones_this_turn:
            self.current_player = 3 - self.current_player
            self.stones_this_turn = 0
            self.max_stones_this_turn = 2
            self.last_moves_this_turn = []
        else:
            pass

        self._update_status()

        if self.ai_enabled and self.current_player == self.ai_player and not self.game_over:
            self.win.after(200, self._ai_move)

    def _update_status(self):
        if self.game_over:
            return
        player_name = "黑棋" if self.current_player == BLACK else "白棋"
        remaining = self.max_stones_this_turn - self.stones_this_turn
        if remaining > 1:
            self.status.config(text=f"{player_name}走 (还需落 {remaining} 子)")
        else:
            self.status.config(text=f"{player_name}走 (还需落 {remaining} 子)")
        total_moves = len(self.move_history)
        self.move_info.config(text=f" 第 {total_moves} 手")

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

    def _undo(self):
        if self.game_over:
            return
        if self.ai_thinking:
            return
        if not self.move_history:
            self.sound.play_invalid()
            return

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
        self._draw_board()
        self._update_status()

    def _recalc_last_moves(self):
        self.last_moves_this_turn = []
        if not self.move_history:
            self.last_move = None
            return
        cur_player = self.move_history[-1][2]
        for i in range(len(self.move_history) - 1, -1, -1):
            if self.move_history[i][2] == cur_player:
                self.last_moves_this_turn.append(
                    (self.move_history[i][0], self.move_history[i][1]))
            else:
                break
        self.last_moves_this_turn = self.last_moves_this_turn[:2]
        self.last_move = self.move_history[-1][:2]

    def _restart(self):
        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.stones_this_turn = 0
        self.max_stones_this_turn = 1
        self.game_over = False
        self.move_history = []
        self.last_move = None
        self.last_moves_this_turn = []
        self.ai_thinking = False
        self._draw_board()
        self._update_status()
        if self.ai_enabled and self.current_player == self.ai_player:
            self.win.after(300, self._ai_move)

    def _toggle_bgm(self):
        if self.bgm_on.get():
            self.sound.start_bgm()
        else:
            self.sound.stop_bgm()

    def _toggle_sfx(self):
        self.sound.sfx_enabled = not self.sound.sfx_enabled
        self.sfx_btn.config(relief=tk.SUNKEN if not self.sound.sfx_enabled else tk.RAISED)

    def _toggle_ai(self):
        self.ai_enabled = not self.ai_enabled
        self.ai_btn.config(relief=tk.SUNKEN if not self.ai_enabled else tk.RAISED)
        if self.ai_enabled and self.current_player == self.ai_player and not self.game_over:
            self.win.after(300, self._ai_move)

    def _ai_move(self):
        if self.game_over or self.ai_thinking:
            return
        if not self.ai_enabled or self.current_player != self.ai_player:
            return
        self.ai_thinking = True
        self.win.config(cursor="watch")
        self.status.config(text="AI 思考中...")

        def do_ai():
            try:
                remaining = self.max_stones_this_turn - self.stones_this_turn
                moves = self._ai_get_moves(remaining)
                self.win.after(0, lambda: self._apply_ai_moves(moves))
            except Exception as e:
                self.win.after(0, lambda: self._ai_error(str(e)))

        threading.Thread(target=do_ai, daemon=True).start()

    def _apply_ai_moves(self, moves):
        self.ai_thinking = False
        self.win.config(cursor="")
        for r, c in moves:
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == EMPTY:
                self._place_stone(r, c, is_ai=True)
                if self.game_over:
                    return

    def _ai_error(self, msg):
        self.ai_thinking = False
        self.win.config(cursor="")
        self.status.config(text="AI 出错")
        print("AI error:", msg)

    def _ai_get_moves(self, count):
        best_moves = []
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

        for r, c, _ in scored:
            if self.board[r][c] == EMPTY:
                best_moves.append((r, c))
                if len(best_moves) >= count:
                    break

        if not best_moves:
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if self.board[r][c] == EMPTY:
                        best_moves.append((r, c))
                        if len(best_moves) >= count:
                            break
                if len(best_moves) >= count:
                    break

        return best_moves[:count]

    def _score_all_positions(self, player):
        opponent = 3 - player
        scored = []

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.board[r][c] != EMPTY:
                    continue
                score = self._evaluate_position(r, c, player, opponent)
                scored.append((r, c, score))

        return scored

    def _evaluate_position(self, row, col, player, opponent):
        score = 0.0

        center = BOARD_SIZE // 2
        dist = abs(row - center) + abs(col - center)
        score += max(0, 10 - dist) * 0.5

        for dr, dc in DIRECTIONS:
            score += self._line_score(row, col, dr, dc, player, opponent)

        return score

    def _line_score(self, row, col, dr, dc, player, opponent):
        score = 0

        own_count = 1
        own_forward = self._count_dir(row, col, dr, dc, player)
        own_backward = self._count_dir(row, col, -dr, -dc, player)
        own_count += own_forward + own_backward

        opp_count = 1
        opp_forward = self._count_dir(row, col, dr, dc, opponent)
        opp_backward = self._count_dir(row, col, -dr, -dc, opponent)
        opp_count += opp_forward + opp_backward

        own_open = self._open_ends(row, col, dr, dc, player, own_forward, own_backward)
        opp_open = self._open_ends(row, col, dr, dc, opponent, opp_forward, opp_backward)

        if own_count >= 6:
            score += 100000
        elif own_count == 5:
            score += 10000 * own_open
        elif own_count == 4:
            score += 1000 * own_open
        elif own_count == 3:
            score += 100 * own_open
        elif own_count == 2:
            score += 10 * own_open

        if opp_count >= 6:
            score += 50000
        elif opp_count == 5:
            score += 8000 * opp_open
        elif opp_count == 4:
            score += 800 * opp_open
        elif opp_count == 3:
            score += 80 * opp_open

        return score

    def _count_dir(self, row, col, dr, dc, player):
        count = 0
        r, c = row + dr, col + dc
        while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
            count += 1
            r += dr
            c += dc
        return count

    def _open_ends(self, row, col, dr, dc, player, forward, backward):
        open_ends = 0
        r = row + dr * (forward + 1)
        c = col + dc * (forward + 1)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == EMPTY:
            open_ends += 1
        r = row - dr * (backward + 1)
        c = col - dc * (backward + 1)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == EMPTY:
            open_ends += 1
        return open_ends

    def run(self):
        self.win.mainloop()


if __name__ == "__main__":
    game = SixInARow()
    game.run()
