"""Generate the PWA / home-screen icons. Re-run if the mark changes.

    ../.venv/bin/python make_icons.py
"""
import os
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icons")
os.makedirs(OUT, exist_ok=True)

INK = (14, 12, 10)     # #0a0c0e  (BGR)
VOLT = (53, 241, 200)  # #c8f135  (BGR)


def render(size):
    """Dark tile with a volt running figure + slash — matches the Form/Check UI."""
    img = np.full((size, size, 3), INK, np.uint8)
    s = size / 512.0

    def P(x, y):
        return (int(x * s), int(y * s))

    th = max(2, int(32 * s))
    # Motion streaks trailing behind the runner (lower-left), not touching them.
    for y in (250, 300, 350):
        cv2.line(img, P(70, y), P(175, y), VOLT, max(2, int(14 * s)), cv2.LINE_AA)
    # Runner: head
    cv2.circle(img, P(330, 150), int(40 * s), VOLT, -1, cv2.LINE_AA)
    # torso leaning forward
    cv2.line(img, P(330, 192), P(288, 300), VOLT, th, cv2.LINE_AA)
    # arms (front driving forward, rear swung back)
    cv2.line(img, P(312, 222), P(378, 248), VOLT, th, cv2.LINE_AA)
    cv2.line(img, P(378, 248), P(400, 300), VOLT, th, cv2.LINE_AA)
    cv2.line(img, P(308, 232), P(246, 250), VOLT, th, cv2.LINE_AA)
    cv2.line(img, P(246, 250), P(238, 302), VOLT, th, cv2.LINE_AA)
    # legs (mid-stride)
    cv2.line(img, P(288, 300), P(352, 348), VOLT, th, cv2.LINE_AA)   # front thigh
    cv2.line(img, P(352, 348), P(346, 432), VOLT, th, cv2.LINE_AA)   # front shin
    cv2.line(img, P(288, 300), P(250, 378), VOLT, th, cv2.LINE_AA)   # rear thigh
    cv2.line(img, P(250, 378), P(300, 420), VOLT, th, cv2.LINE_AA)   # rear shin
    return img


master = render(512)
for sz in (512, 192, 180):
    out = master if sz == 512 else cv2.resize(master, (sz, sz), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, f"icon-{sz}.png"), out)
    print("wrote", f"icon-{sz}.png")
