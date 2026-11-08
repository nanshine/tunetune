import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'assets'


def image_uri(name):
    data = (ROOT / 'characters' / name).read_bytes()
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')


USER_PNG, GHOST_PNG = image_uri('user.png'), image_uri('ghost.png')

W, H = 1500, 412
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
BLUE, GREEN, GOLD = '#1744ef', '#337245', '#b3904b'

LANG = {
    'zh': dict(
        title='TuneTune 研究流程',
        desc='你描述需求和例子，确认方案和预算，审阅参考答案，最后试用并验收模型。小鬼负责其余步骤：了解与调研、写方案，准备评测集、测基线，再一轮轮规划、运行和分析实验；达到目标或预算用完时验证并交付。研究中你随时可以改目标、质疑评分或提出方法想法，Agent 会转到对应环节。',
        chips=['描述需求和例子', '确认方案和预算', '审阅参考答案', '试用并验收'],
        boxes=['了解与调研', '写方案', '准备评测集', '测基线', '规划一轮', '运行实验', '分析结果', '验证并交付'],
        next='下一轮', stop=['达到目标', '或预算用完'],
        note_head='研究中随时可以说', note=[('目标变了', '修改方案'), ('评分不对', '更新评测'), ('有新想法', '放进下一轮')],
        chip_fs=15, box_fs=17, note_fs=14, cw=15.2, small_fs=13,
    ),
    'en': dict(
        title='TuneTune research workflow',
        desc='You describe the need with examples, approve the plan and budget, review reference answers, and finally try and accept the model. The ghost does the rest: investigate, write the proposal, prepare evaluation samples, measure a baseline, then plan, run and analyze experiment rounds; when the goal is met or the budget is spent it verifies and delivers a model. At any time you can change the goal, question the scores or suggest a method, and the Agent returns to the matching stage.',
        chips=['Describe the need', 'Approve plan & budget', 'Review references', 'Try the model'],
        boxes=['Investigate', 'Write proposal', 'Prepare samples', 'Measure baseline', 'Plan a round', 'Run experiments', 'Analyze results', 'Verify & deliver'],
        next='next round', stop=['goal met or', 'budget spent'],
        note_head='Anytime', note=[('New goal', 'revise proposal'), ('Doubtful scores', 'new evaluation'), ('Method idea', 'next round')],
        chip_fs=14, box_fs=14.5, note_fs=13, cw=7.9, small_fs=12.5,
    ),
}


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def line(points, color, width=2, dash=None):
    d = 'M' + 'L'.join(f'{x} {y}' for x, y in points)
    extra = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{extra}/>'


def head(x, y, direction, color):
    s = 6
    if direction == 'right':
        pts = [(x - s, y - s * 0.6), (x, y), (x - s, y + s * 0.6)]
    elif direction == 'down':
        pts = [(x - s * 0.6, y - s), (x, y), (x + s * 0.6, y - s)]
    else:  # up
        pts = [(x - s * 0.6, y + s), (x, y), (x + s * 0.6, y + s)]
    return line(pts, color)


def text(x, y, s, fs, fill, weight=500, anchor='middle'):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{fs}" font-weight="{weight}" fill="{fill}">{esc(s)}</text>'


def build(lang):
    L = LANG[lang]
    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" xml:lang="{lang}" role="img" aria-labelledby="title desc">')
    a(f'<title id="title">{esc(L["title"])}</title>')
    a(f'<desc id="desc">{esc(L["desc"])}</desc>')
    a(f'<defs><image id="user" width="70" height="64" href="{USER_PNG}"/></defs>')
    a(f'<rect width="{W}" height="{H}" rx="20" fill="#fffdf8"/>')
    a(f'<g font-family="{FONT}" fill="#292a30">')

    BW, BH = 138, 60
    FP, G, G2, FG = 18, 26, 44, 24
    ROW1, ROW2 = 196, 316
    FT = 132  # frame top

    init_x = 140
    b1 = init_x + FP
    b2 = b1 + BW + G
    init_w = FP * 2 + BW * 2 + G
    eval_x = init_x + init_w + FG
    b3 = eval_x + FP
    b4 = b3 + BW + G2
    eval_w = FP * 2 + BW * 2 + G2
    exp_x = eval_x + eval_w + FG
    exp_r = W - 16
    b5 = exp_x + FP
    b6 = b5 + BW + 48
    b8 = exp_r - FP - BW
    gate1 = init_x + init_w + FG / 2
    gate2 = b3 + BW + G2 / 2

    short_bottom = ROW1 + BH / 2 + 42
    long_bottom = ROW2 + BH / 2 + 42

    # skill frames
    for x, w, bottom, name in [
        (init_x, init_w, short_bottom, 'tunetune-init'),
        (eval_x, eval_w, short_bottom, 'build-evaluation'),
        (exp_x, exp_r - exp_x, long_bottom, 'run-experiments'),
    ]:
        a(f'<rect x="{x}" y="{FT}" width="{w}" height="{bottom - FT}" rx="16" fill="#f4f6ff" stroke="#dde3f6" stroke-width="1.5"/>')
        a(text(x + 18, bottom - 14, name, 14, '#53669f', 500, 'start'))

    # boxes
    def box(x, cy, label, kind='normal'):
        fill, stroke, color = {
            'normal': ('#ffffff', '#cbd4f4', '#292a30'),
            'deliver': ('#e9f5eb', '#a8ceb0', GREEN),
        }[kind]
        a(f'<rect x="{x}" y="{cy - BH / 2}" width="{BW}" height="{BH}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        a(text(x + BW / 2, cy + L['box_fs'] * 0.36, label, L['box_fs'], color, 600))

    labels = L['boxes']
    for x, lab in zip([b1, b2, b3, b4, b5, b6], labels[:6]):
        box(x, ROW1, lab)
    box(b6, ROW2, labels[6])
    box(b8, ROW2, labels[7], 'deliver')

    # agent flow
    def arrow_r(x1, x2, y, color=BLUE):
        a(line([(x1, y), (x2, y)], color))
        a(head(x2, y, 'right', color))

    a(f'<image x="28" y="{ROW1 - 44}" width="92" height="88" href="{GHOST_PNG}"/>')
    arrow_r(124, b1 - 3, ROW1)
    arrow_r(b1 + BW + 3, b2 - 3, ROW1)
    arrow_r(b2 + BW + 3, b3 - 3, ROW1)
    arrow_r(b3 + BW + 3, b4 - 3, ROW1)
    arrow_r(b4 + BW + 3, b5 - 3, ROW1)
    arrow_r(b5 + BW + 3, b6 - 3, ROW1)
    # run -> analyze
    cx6 = b6 + BW / 2
    a(line([(cx6, ROW1 + BH / 2 + 3), (cx6, ROW2 - BH / 2 - 3)], BLUE))
    a(head(cx6, ROW2 - BH / 2 - 3, 'down', BLUE))
    # analyze -> plan (next round)
    cx5 = b5 + BW / 2
    a(line([(b6 - 3, ROW2), (cx5 + 12, ROW2)], BLUE))
    a(f'<path d="M{cx5 + 12} {ROW2}Q{cx5} {ROW2} {cx5} {ROW2 - 12}" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linecap="round"/>')
    a(line([(cx5, ROW2 - 12), (cx5, ROW1 + BH / 2 + 3)], BLUE))
    a(head(cx5, ROW1 + BH / 2 + 3, 'up', BLUE))
    a(text((cx5 + b6) / 2 + 6, ROW2 - 9, L['next'], L['small_fs'], '#2448b8', 600))
    # analyze -> deliver
    arrow_r(b6 + BW + 3, b8 - 3, ROW2, GREEN)
    mid = (b6 + BW + b8) / 2
    a(text(mid, ROW2 - 26, L['stop'][0], L['small_fs'], GREEN, 500))
    a(text(mid, ROW2 - 10, L['stop'][1], L['small_fs'], GREEN, 500))

    # user lane
    LANE = 60
    a(f'<use href="#user" x="34" y="{LANE - 34}"/>')
    targets = [
        (b1 + BW / 2, 'box', ROW1),
        (gate1, 'gate', ROW1),
        (gate2, 'gate', ROW1),
        (b8 + BW / 2, 'box', ROW2),
    ]
    a(line([(112, LANE), (targets[-1][0], LANE)], '#d8c8a2', 1.5))
    CH = 38
    for (tx, kind, row), label in zip(targets, L['chips']):
        if kind == 'gate':
            a(line([(tx, LANE + CH / 2), (tx, row - 8)], GOLD, 2, '5 6'))
            a(head(tx, row - 8, 'down', GOLD))
            a(f'<circle cx="{tx}" cy="{row}" r="4" fill="{GOLD}"/>')
        else:
            end = row - BH / 2 - 3
            a(line([(tx, LANE + CH / 2), (tx, end)], GOLD, 2, '5 6'))
            a(head(tx, end, 'down', GOLD))
    for (tx, kind, row), label in zip(targets, L['chips']):
        w = round(len(label) * L['cw'] + 34) if lang == 'en' else round(len(label) * L['chip_fs'] + 34)
        a(f'<rect x="{tx - w / 2}" y="{LANE - CH / 2}" width="{w}" height="{CH}" rx="19" fill="#fff4dc" stroke="#e4d2a8" stroke-width="1.5"/>')
        a(text(tx, LANE + L['chip_fs'] * 0.36, label, L['chip_fs'], '#6f5a30', 600))

    # anytime note under init + evaluation frames
    nx, nw = init_x, eval_x + eval_w - init_x
    ny, nh = long_bottom - 52, 52
    a(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{nh}" rx="14" fill="#fffaf0" stroke="#e8dcc0" stroke-width="1.5" stroke-dasharray="4 5"/>')
    ty = ny + nh / 2 + 5
    a(f'<use href="#user" transform="translate({nx + 14} {ny + 9}) scale(0.53)"/>')
    parts = [f'<tspan font-weight="600" fill="#6f5a30">{esc(L["note_head"])}</tspan>']
    for i, (k, v) in enumerate(L['note']):
        gap = '　' if lang == 'zh' else '  '
        sep = f'<tspan fill="#cdbb92">{gap}·{gap}</tspan>' if i else f'<tspan>{gap}</tspan>'
        parts.append(f'{sep}<tspan fill="#6f5a30">{esc(k)}</tspan><tspan fill="{GOLD}"> → </tspan><tspan fill="#53669f">{esc(v)}</tspan>')
    nfs = L['note_fs']
    a(f'<text x="{nx + 62}" y="{ty}" font-size="{nfs}" font-weight="500" xml:space="preserve">{"".join(parts)}</text>')

    a('</g></svg>')
    return '\n'.join(out) + '\n'


dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
for lang in ('zh', 'en'):
    (dest / f'workflow-{lang}.svg').write_text(build(lang))
print('ok')
