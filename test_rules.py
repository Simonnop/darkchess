"""暗棋服务端规则自测：与前端 JS 用例对齐 + 随机自对弈不变量。"""
import random
import sys

sys.path.insert(0, "/home/ubuntu/darkchess")
import rules as R

ROWS, COLS = R.ROWS, R.COLS
fails = []


def mk(color, typ, hidden=False):
    return {"color": color, "type": typ, "hidden": hidden}


def empty():
    return [[None] * COLS for _ in range(ROWS)]


def check(label, got, want):
    if got != want:
        fails.append("%s\n  got  %s\n  want %s" % (label, got, want))
        print("FAIL", label, "got", got, "want", want)


def moves(board, r, c, bottom="r"):
    return ["%d,%d" % m for m in R.pseudo_moves(board, r, c, bottom)]


def state_of(board, bottom="r", turn=None):
    st = {"board": board, "turn": turn or bottom, "bottom_color": bottom,
          "top_color": R.other(bottom), "over": False, "result": "",
          "taken": [], "log": [], "pending_draw": None}
    return st


# ---------- 兵/卒：暗子按格向前一步；翻开后朝对手方向 ----------
b = empty(); b[6][0] = mk("r", "P", True)
check("兵位暗子(真红) 向前一步", moves(b, 6, 0), ["5,0"])
b = empty(); b[6][0] = mk("b", "P", True)
check("兵位暗子(真黑) 也向前一步", moves(b, 6, 0), ["5,0"])
b = empty(); b[3][0] = mk("b", "P", True)
check("卒位暗子(真黑) 向前一步", moves(b, 3, 0), ["4,0"])
b = empty(); b[3][0] = mk("r", "P", True)
check("卒位暗子(真红) 也向前一步", moves(b, 3, 0), ["4,0"])
b = empty(); b[7][0] = mk("b", "P", False)
check("下方执红：翻开黑卒(属上方) 向南+横", moves(b, 7, 0), ["8,0", "7,1"])
b = empty(); b[9][0] = mk("r", "P", False)
check("下方执红：翻开红兵(属下方) 向北", moves(b, 9, 0), ["8,0"])
b = empty(); b[9][4] = mk("b", "P", False)
check("下方执黑：翻开黑卒(属下方) 向北进攻", moves(b, 9, 4, "b"), ["8,4"])
b = empty(); b[0][4] = mk("r", "P", False)
check("下方执黑：翻开红兵(属上方) 向南进攻", moves(b, 0, 4, "b"), ["1,4"])
b = empty(); b[9][4] = mk("r", "P", False)
check("下方执黑：红兵(属上方) 在下方半场只能横走", moves(b, 9, 4, "b"), ["9,3", "9,5"])
b = empty(); b[6][0] = mk("b", "P", True)
check("暗子方向与执色无关", moves(b, 6, 0, "b"), ["5,0"])

# ---------- 马 / 炮 / 象 / 士 ----------
b = empty(); b[0][1] = mk("r", "P", True)
m = moves(b, 0, 1)
check("黑马位暗子走日", sorted([x for x in m if x in ("2,0", "2,2", "1,3")]), ["1,3", "2,0", "2,2"])
b[1][1] = mk("r", "P", False)
m = moves(b, 0, 1)
check("蹩马腿", [x for x in m if x in ("2,0", "2,2")], [])
b = empty(); b[7][7] = mk("r", "P", True); b[7][3] = mk("b", "N", False)
check("无炮架不能吃", [x for x in moves(b, 7, 7) if x == "7,3"], [])
b[7][2] = mk("b", "R", False)
check("隔一子可吃架后", [x for x in moves(b, 7, 7) if x == "7,2"], ["7,2"])
b[7][0] = mk("b", "B", False)
check("不能吃架后第二子", [x for x in moves(b, 7, 7) if x == "7,0"], [])
b = empty(); b[9][6] = mk("b", "R", True)
check("相位暗子走田", sorted([x for x in moves(b, 9, 6) if x in ("7,4", "7,8")]), ["7,4", "7,8"])
b = empty(); b[9][5] = mk("r", "P", True)
check("士位暗子斜一步", sorted(moves(b, 9, 5)), ["8,4", "8,6"])
b = empty(); b[0][4] = mk("b", "K", True)
check("將位暗子按將走法", sorted(moves(b, 0, 4)), ["0,3", "0,5", "1,4"])

# ---------- 照面 ----------
b = empty(); b[0][4] = mk("b", "K", False); b[5][4] = mk("r", "R", False); b[9][4] = mk("r", "K", False)
check("明子走开造成照面=禁手", R.evaluate_move(b, 5, 4, 5, 3)["ok"], False)
check("沿线走仍挡子=合法", R.evaluate_move(b, 5, 4, 4, 4)["ok"], True)
v = R.evaluate_move(b, 5, 4, 0, 4)
check("车吃黑将=黑负", v["ok"] and v["end"] == {"type": "capture", "loser": "b"}, True)

b = empty(); b[9][4] = mk("r", "K", False); b[7][1] = mk("b", "K", True)
v = R.evaluate_move(b, 7, 1, 7, 4)
check("暗将翻出照面=黑负", v["ok"] and v["end"] == {"type": "facing", "loser": "b"}, True)

b = empty(); b[9][0] = mk("b", "K", False); b[9][4] = mk("r", "K", False); b[9][2] = mk("r", "R", True)
check("暗子走开造成已明双方照面=禁手", R.evaluate_move(b, 9, 2, 7, 4)["ok"], False)

# ---------- 吃子 / 盲吃 / 误伤 ----------
b = empty(); b[9][4] = mk("r", "K", False); b[0][3] = mk("b", "K", False)
b[6][0] = mk("b", "R", True); b[5][0] = mk("r", "N", False)
check("暗子可盲吃己方明子", "5,0" in moves(b, 6, 0), True)
check("盲吃合法", R.evaluate_move(b, 6, 0, 5, 0)["ok"], True)
b = empty(); b[9][4] = mk("r", "K", False); b[0][4] = mk("b", "K", False); b[5][0] = mk("r", "R", False); b[5][1] = mk("r", "N", False)
check("明子不能吃己方明子", [x for x in moves(b, 5, 0) if x == "5,1"], [])
b = empty(); b[9][4] = mk("r", "K", False); b[0][4] = mk("b", "K", False); b[8][4] = mk("r", "R", True)
v = R.evaluate_move(b, 8, 4, 9, 4)
check("暗子误伤己方帅=红负", v["end"] == {"type": "capture", "loser": "r"}, True)

# ---------- 操作权 / 无棋可走 ----------
st = state_of(empty()); st["board"][6][0] = mk("b", "R", True); st["board"][3][0] = mk("r", "R", True)
check("下方可动己半场暗子", R.operable(st, "bottom", 6, 0), True)
check("下方不能动对方半场暗子", R.operable(st, "bottom", 3, 0), False)
check("上方可动己半场暗子", R.operable(st, "top", 3, 0), True)
st = state_of(empty()); st["board"][9][4] = mk("r", "K", False); st["board"][0][4] = mk("b", "K", False)
check("红帅有棋走", R.has_any_move(st, "bottom"), True)

# ---------- 随机自对弈不变量 ----------
random.seed(20260929)
games = 300
done = 0
steps = 0
for g in range(games):
    st = R.new_state()
    mv = 0
    while not st["over"] and mv < 800:
        cands = []
        for r in range(ROWS):
            for c in range(COLS):
                if R.operable(st, R.color_seat(st, st["turn"]), r, c):
                    ms = R.select_moves(st, R.color_seat(st, st["turn"]), r, c)
                    if ms:
                        cands.append((r, c, ms))
        if not cands:
            fails.append("自对弈：无候选但未结束")
            break
        r, c, ms = random.choice(cands)
        tr, tc = random.choice(ms)
        before = st["board"][r][c]
        ok, evt, err = R.do_move(st, R.color_seat(st, st["turn"]), r, c, tr, tc)
        if not ok:
            fails.append("自对弈：合法走法被拒 %s" % err)
            break
        if before["hidden"] and st["board"][tr][tc]["hidden"]:
            fails.append("自对弈：暗子走完未翻开")
        onb = sum(1 for row in st["board"] for p in row if p)
        if onb + len(st["taken"]) != 32:
            fails.append("自对弈：棋子不守恒")
        for row in range(ROWS):
            for col in range(COLS):
                p = st["board"][row][col]
                if p and p["hidden"] and not R.BASE[row][col]:
                    fails.append("自对弈：暗子出现在非开局点")
        mv += 1
        steps += 1
    if st["over"]:
        done += 1

print("自对弈：%d/%d 局在 800 步内结束，共 %d 步" % (done, games, steps))

# 服务端视图不得泄露暗子身份
st = R.new_state()
v = R.view(st, "bottom")
leak = False
for r in range(ROWS):
    for c in range(COLS):
        cell = v["board"][r][c]
        if cell and "h" in cell and ("color" in cell or "type" in cell):
            leak = True
check("视图不含暗子身份", leak, False)

if fails:
    print("\n共 %d 处失败：" % len(fails))
    for f in fails[:10]:
        print(" -", f)
    sys.exit(1)
print("\n全部通过 ✓")
