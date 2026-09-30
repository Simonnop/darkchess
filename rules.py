"""暗棋（Dark Chess）规则实现 —— 服务端权威版本。

与前端 web/dark_chess.html 的单机规则保持一致：
- 32 子混洗盖放，随机铺满 32 个标准开局点（纯随机，兩个將位物理同色也不重洗）
- 开局随机指定一方先手（各 50%）：先手原地翻开自己將位即锁定双方颜色——翻开什么色
  执什么色，对方执另一色；对方随后翻开自己將位，之后先手先走
- 暗子只能由所在半场的一方操作；首手按「所在格原本的兵种」走，走完/被吃强制翻开
- 兵/卒 朝「所属玩家」的对面走（下方玩家向北、上方玩家向南），进入对方半场后可横走
- 暗子可盲吃任意未知子（含己方，误伤自担）；吃对方將/帥即胜，误伤吃到己方將/帥即负
- 暗士（士位上未翻开的子）首手不得走出本侧九宫（田字格）；翻开后无九宫限制
- 对方將位翻出与先手同色的牌，该牌归先手方（按物理颜色归属）
- 两个將/帥都翻开后不得照面：明子主动走成照面为禁手；暗子翻出才发现照面则翻出方判负
- 无棋可走判负；和棋双方同意
"""

import random

ROWS, COLS = 10, 9
RED, BLK = "r", "b"

NAMES = {
    "r": {"K": "帥", "A": "仕", "B": "相", "N": "馬", "R": "車", "C": "炮", "P": "兵"},
    "b": {"K": "將", "A": "士", "B": "象", "N": "馬", "R": "車", "C": "砲", "P": "卒"},
}
MULT = {"K": 1, "A": 2, "B": 2, "N": 2, "R": 2, "C": 2, "P": 5}
FILES = "abcdefghi"


def _build_base():
    base = [[None] * COLS for _ in range(ROWS)]
    back = ["R", "N", "B", "A", "K", "A", "B", "N", "R"]
    for c, t in enumerate(back):
        base[0][c] = (BLK, t)
        base[9][c] = (RED, t)
    for c in (1, 7):
        base[2][c] = (BLK, "C")
        base[7][c] = (RED, "C")
    for c in (0, 2, 4, 6, 8):
        base[3][c] = (BLK, "P")
        base[6][c] = (RED, "P")
    return base


BASE = _build_base()
SQUARES = [(r, c) for r in range(ROWS) for c in range(COLS) if BASE[r][c]]
# 各半场「將位」：定色阶段只能原地翻开这个格子的牌
GEN_SQ = {"bottom": (9, 4), "top": (0, 4)}


def other(col):
    return BLK if col == RED else RED


def color_name(col):
    return "红方" if col == RED else "黑方"


def piece_name(p):
    return color_name(p["color"]) + NAMES[p["color"]][p["type"]]


def sq_name(r, c):
    return FILES[c] + str(10 - r)


def half_of(seat):
    """座位对应的半场行范围"""
    return range(5, 10) if seat == "bottom" else range(0, 5)


# ---------------------------------------------------------------- 开局

def new_state(rng=None, first_side=None):
    """开局：纯随机发牌（两个將位可能物理同色，不重洗）。

    先手由 first_side 指定（bottom/top）；不传则随机掷出（公平，各 50%）。
    先手翻开自己將位即锁定双方颜色，对方随后翻开自己將位，之后先手先走。
    """
    rng = rng or random
    squares = SQUARES[:]
    rng.shuffle(squares)
    pool = []
    for col in (RED, BLK):
        for t in ("K", "A", "B", "N", "R", "C", "P"):
            pool.extend([(col, t)] * MULT[t])
    rng.shuffle(pool)
    board = [[None] * COLS for _ in range(ROWS)]
    for (r, c), (col, t) in zip(squares, pool):
        board[r][c] = {"color": col, "type": t, "hidden": True}
    if first_side not in ("bottom", "top"):
        first_side = "bottom" if rng.random() < 0.5 else "top"
    st = {
        "board": board,
        "turn": None,
        "phase": "opening",
        "opening_first": first_side,
        "bottom_color": None,
        "top_color": None,
        "over": False,
        "result": "",
        "taken": [],
        "log": [],
        "pending_draw": None,
    }
    log(st, "开局：%s先手，请先翻开自己將位的牌，翻开什么色就执什么色"
            % ("下方" if first_side == "bottom" else "上方"))
    return st


def log(st, text):
    st["log"].append(text)
    if len(st["log"]) > 200:
        del st["log"][:100]


def flip_general(st, seat):
    """定色阶段：原地翻开自己半场將位的那张牌（不走动）。

    先手首翻即锁定双方颜色（翻开什么色执什么色，对方执另一色）；
    对方二翻后进入行棋，由先手先走。对方將位若物理同色，该牌归先手方。
    返回 (ok, evt, err)。
    """
    if st.get("phase") != "opening":
        return False, None, "已经定色了"
    r, c = GEN_SQ[seat]
    p = st["board"][r][c]
    if not p or not p["hidden"]:
        return False, None, "这张已经翻开了"
    g0, g1 = st["board"][9][4], st["board"][0][4]
    both_hidden = g0["hidden"] and g1["hidden"]
    if both_hidden and seat != st["opening_first"]:
        return False, None, "还没轮到你翻牌"
    who = "下方" if seat == "bottom" else "上方"

    if both_hidden:
        # 先手首翻：锁定双方颜色
        p["hidden"] = False
        if seat == "bottom":
            st["bottom_color"], st["top_color"] = p["color"], other(p["color"])
        else:
            st["top_color"], st["bottom_color"] = p["color"], other(p["color"])
        log(st, "%s先手翻开 %s：%s，%s执%s" % (
            who, sq_name(r, c), piece_name(p), who, color_name(p["color"])))
    else:
        # 对方二翻：颜色已锁，仅翻开；物理同色归先手
        p["hidden"] = False
        owner_seat = "bottom" if st["bottom_color"] == p["color"] else "top"
        log(st, "%s翻开 %s：%s" % (who, sq_name(r, c), piece_name(p))
            + ("" if owner_seat == seat else "（与先手同色，归%s）"
               % ("下方" if owner_seat == "bottom" else "上方")))
        st["phase"] = "play"
        st["turn"] = seat_color(st, st["opening_first"])
        log(st, "定色：下方执%s · 上方执%s · %s先走" % (
            color_name(st["bottom_color"]), color_name(st["top_color"]),
            "先手" + ("（下方）" if st["opening_first"] == "bottom" else "（上方）")))

    evt = {"fr": r, "fc": c, "tr": r, "tc": c,
           "cap": None, "end": None, "flip": True}
    return True, evt, None


# ---------------------------------------------------------------- 基本信息

def seat_color(st, seat):
    return st["bottom_color"] if seat == "bottom" else st["top_color"]


def color_seat(st, col):
    return "bottom" if col == st["bottom_color"] else "top"


# ---------------------------------------------------------------- 走法生成

KDIR = ((-1, 0), (1, 0), (0, -1), (0, 1))
ADIR = ((-1, -1), (-1, 1), (1, -1), (1, 1))
NDIR = ((-2, -1, -1, 0), (-2, 1, -1, 0), (2, -1, 1, 0), (2, 1, 1, 0),
        (-1, -2, 0, -1), (1, -2, 0, -1), (-1, 2, 0, 1), (1, 2, 0, 1))


def in_b(r, c):
    return 0 <= r < ROWS and 0 <= c < COLS


def pseudo_moves(board, r, c, bottom_color):
    p = board[r][c]
    if not p:
        return []
    pos = BASE[r][c]
    typ = pos[1] if p["hidden"] else p["type"]
    out = []

    def add(tr, tc):
        if not in_b(tr, tc):
            return
        t = board[tr][tc]
        if t and not p["hidden"] and not t["hidden"] and t["color"] == p["color"]:
            return
        out.append((tr, tc))

    if typ == "K":
        for dr, dc in KDIR:
            add(r + dr, c + dc)
    elif typ == "A":
        if p["hidden"]:
            rmin, rmax = (0, 2) if r < 5 else (7, 9)   # 暗士首手不得走出本侧九宫（田字格）
            for dr, dc in ADIR:
                tr, tc = r + dr, c + dc
                if rmin <= tr <= rmax and 3 <= tc <= 5:
                    add(tr, tc)
        else:
            for dr, dc in ADIR:
                add(r + dr, c + dc)
    elif typ == "B":
        for dr, dc in ADIR:
            tr, tc = r + 2 * dr, c + 2 * dc
            if not in_b(tr, tc) or board[r + dr][c + dc]:
                continue
            add(tr, tc)
    elif typ == "N":
        for dr, dc, lr, lc in NDIR:
            tr, tc = r + dr, c + dc
            if not in_b(tr, tc) or board[r + lr][c + lc]:
                continue
            add(tr, tc)
    elif typ == "R":
        for dr, dc in KDIR:
            tr, tc = r + dr, c + dc
            while in_b(tr, tc):
                if board[tr][tc]:
                    add(tr, tc)
                    break
                add(tr, tc)
                tr += dr
                tc += dc
    elif typ == "C":
        for dr, dc in KDIR:
            tr, tc = r + dr, c + dc
            screen = False
            while in_b(tr, tc):
                if board[tr][tc]:
                    if screen:
                        add(tr, tc)
                        break
                    screen = True
                elif not screen:
                    add(tr, tc)
                tr += dr
                tc += dc
    elif typ == "P":
        # 暗子按所在格「向前一步」；翻开后朝「对手方向」（所属玩家的对面）
        north = (pos[0] == RED) if p["hidden"] else (p["color"] == bottom_color)
        f = -1 if north else 1
        add(r + f, c)
        crossed = (r <= 4) if north else (r >= 5)
        if crossed:
            add(r, c - 1)
            add(r, c + 1)
    return out


def _same_line_clear(board, a, b):
    """a/b = (color, r, c, revealed)"""
    if a[1] != b[1] and a[2] != b[2]:
        return False
    dr = (b[1] > a[1]) - (b[1] < a[1])
    dc = (b[2] > a[2]) - (b[2] < a[2])
    r, c = a[1] + dr, a[2] + dc
    while (r, c) != (b[1], b[2]):
        if board[r][c]:
            return False
        r += dr
        c += dc
    return True


def evaluate_move(board, fr, fc, tr, tc):
    p = board[fr][fc]
    if not p:
        return {"ok": False}
    t = board[tr][tc]
    if t and not p["hidden"] and not t["hidden"] and t["color"] == p["color"]:
        return {"ok": False}
    nb = [row[:] for row in board]
    nb[tr][tc] = p
    nb[fr][fc] = None
    gs = []
    for r in range(ROWS):
        for c in range(COLS):
            q = nb[r][c]
            if q and q["type"] == "K":
                gs.append((q["color"], r, c, (not q["hidden"]) or (r == tr and c == tc)))
    if len(gs) == 2 and gs[0][3] and gs[1][3] and _same_line_clear(nb, gs[0], gs[1]):
        if p["hidden"] and p["type"] == "K":
            return {"ok": True, "capture": t, "reveal": True,
                    "end": {"type": "facing", "loser": p["color"]}}
        return {"ok": False}
    if t and t["type"] == "K":
        return {"ok": True, "capture": t, "reveal": p["hidden"],
                "end": {"type": "capture", "loser": t["color"]}}
    return {"ok": True, "capture": t, "reveal": p["hidden"], "end": None}


def legal_moves(board, r, c, bottom_color):
    return [m for m in pseudo_moves(board, r, c, bottom_color)
            if evaluate_move(board, r, c, m[0], m[1])["ok"]]


# ---------------------------------------------------------------- 操作权

def operable(st, seat, r, c):
    if st["over"]:
        return False
    if st.get("phase") == "opening":
        gr, gc = GEN_SQ[seat]                       # 定色阶段：只能翻自己將位
        if not (r == gr and c == gc):
            return False
        p = st["board"][r][c]
        if not p or not p["hidden"]:
            return False
        g0, g1 = st["board"][9][4], st["board"][0][4]
        if g0["hidden"] and g1["hidden"]:           # 还没人翻：只有随机先手可以先翻
            return seat == st["opening_first"]
        return True
    p = st["board"][r][c]
    if not p:
        return False
    if p["hidden"]:
        return r in half_of(seat)
    return p["color"] == seat_color(st, seat)


def has_any_move(st, seat):
    for r in range(ROWS):
        for c in range(COLS):
            if operable(st, seat, r, c) and legal_moves(st["board"], r, c, st["bottom_color"]):
                return True
    return False


def select_moves(st, seat, r, c):
    if not operable(st, seat, r, c):
        return None
    return legal_moves(st["board"], r, c, st["bottom_color"])


# ---------------------------------------------------------------- 行棋

def do_move(st, seat, fr, fc, tr, tc):
    """执行一步（服务端权威）。返回 (ok, event, err)"""
    if st["over"]:
        return False, None, "对局已结束"
    if st.get("phase") == "opening":
        return False, None, "请先翻开將位定色"
    if not operable(st, seat, fr, fc):
        return False, None, "这不是你能动的子"
    if st["turn"] != seat_color(st, seat):
        return False, None, "还没轮到你"
    v = evaluate_move(st["board"], fr, fc, tr, tc)
    if not v["ok"]:
        return False, None, "这步走不了"
    if (tr, tc) not in pseudo_moves(st["board"], fr, fc, st["bottom_color"]):
        return False, None, "这步走不了"

    p = st["board"][fr][fc]
    t = st["board"][tr][tc]
    was_hidden = p["hidden"]
    cap_hidden = bool(t and t["hidden"])
    st["board"][tr][tc] = p
    st["board"][fr][fc] = None
    if t:
        t["hidden"] = False
        st["taken"].append({"color": t["color"], "type": t["type"]})
    if was_hidden:
        p["hidden"] = False

    if was_hidden:
        b = BASE[fr][fc]
        msg = "%s 暗子（%s位）%s→%s，翻开是 %s" % (
            color_name(st["turn"]), NAMES[b[0]][b[1]], sq_name(fr, fc), sq_name(tr, tc), piece_name(p))
    else:
        msg = "%s %s %s→%s" % (color_name(p["color"]), NAMES[p["color"]][p["type"]],
                               sq_name(fr, fc), sq_name(tr, tc))
    if t:
        msg += "，%s%s" % ("误伤己方" if t["color"] == p["color"] else "吃掉", NAMES[t["color"]][t["type"]])
    log(st, msg)

    evt = {"fr": fr, "fc": fc, "tr": tr, "tc": tc,
           "cap": ({"color": t["color"], "type": t["type"], "hidden": cap_hidden} if t else None),
           "end": v["end"]}

    if v["end"]:
        finish(st, v["end"])
        return True, evt, None

    st["turn"] = other(st["turn"])
    nxt = color_seat(st, st["turn"])
    if not has_any_move(st, nxt):
        finish(st, {"type": "nomove", "loser": st["turn"]})
    return True, evt, None


def finish(st, end):
    st["over"] = True
    if end["type"] == "draw":
        st["result"] = "和棋 · 双方同意"
    else:
        winner = other(end["loser"])
        why = ("%s的%s被吃" % (color_name(end["loser"]), NAMES[end["loser"]]["K"])
               if end["type"] == "capture"
               else ("%s將/帥照面" % color_name(end["loser"])
                     if end["type"] == "facing"
                     else "%s无棋可走" % color_name(end["loser"])))
        st["result"] = "%s胜 · %s" % (color_name(winner), why)
    log(st, "—— " + st["result"] + " ——")


# ---------------------------------------------------------------- 下发视图

def preset_view():
    """开局前的占位视图：32 个开局点全是暗子，不翻棋、不定色"""
    board = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            row.append({"h": 1} if BASE[r][c] else None)
        board.append(row)
    return {"board": board, "turn": None, "phase": "lobby",
            "bottomColor": None, "topColor": None,
            "over": False, "result": "", "taken": [], "log": [], "draw": "none"}


def view(st, seat):
    """给客户端的可见信息：暗子只给 h 标记，不含真实身份"""
    if st.get("phase") == "opening":
        board = []
        for row in st["board"]:
            out = []
            for p in row:
                if not p:
                    out.append(None)
                elif p["hidden"]:
                    out.append({"h": 1})
                else:
                    out.append({"hidden": False, "color": p["color"], "type": p["type"]})
            board.append(out)
        return {
            "board": board,
            "turn": None,
            "phase": "opening",
            "openingFirst": st["opening_first"],
            "bottomColor": st["bottom_color"],
            "topColor": st["top_color"],
            "seatColor": None,
            "over": False,
            "result": "",
            "taken": [],
            "log": st["log"][-40:],
            "draw": "none",
        }
    board = []
    for row in st["board"]:
        out = []
        for p in row:
            if not p:
                out.append(None)
            elif p["hidden"]:
                out.append({"h": 1})
            else:
                out.append({"hidden": False, "color": p["color"], "type": p["type"]})
        board.append(out)
    return {
        "board": board,
        "turn": st["turn"],
        "phase": "play",
        "bottomColor": st["bottom_color"],
        "topColor": st["top_color"],
        "seatColor": seat_color(st, seat),
        "over": st["over"],
        "result": st["result"],
        "taken": st["taken"],
        "log": st["log"][-40:],
        "draw": ("mine" if st["pending_draw"] == seat
                 else "theirs" if st["pending_draw"] else "none"),
    }
