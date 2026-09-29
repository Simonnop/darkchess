"""与前端 JS 引擎对拍：同一批局面的合法走法必须完全一致。"""
import json
import sys
sys.path.insert(0, "/home/ubuntu/darkchess")
import rules as R

data = json.load(open("/tmp/posdump.json"))
bad = 0
cells = 0
for i, snap in enumerate(data):
    board = [[None] * R.COLS for _ in range(R.ROWS)]
    for r, row in enumerate(snap["board"]):
        for c, cell in enumerate(row):
            if cell:
                board[r][c] = {"color": cell["c"], "type": cell["t"], "hidden": bool(cell["h"])}
    for key, want in snap["moves"].items():
        r, c = map(int, key.split(","))
        got = ["%d,%d" % m for m in R.legal_moves(board, r, c, snap["bottomColor"])]
        cells += 1
        if sorted(got) != sorted(want):
            bad += 1
            if bad <= 5:
                print("MISMATCH #%d 局面%d (%s)\n  py=%s\n  js=%s" % (bad, i, key, got, want))
print("对拍完成：%d 张快照、%d 个棋子的走法，%d 处不一致" % (len(data), cells, bad))
sys.exit(1 if bad else 0)
