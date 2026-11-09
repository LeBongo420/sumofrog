"""Make the miner screenshots in docs/screens/ (fake example numbers, no network). Run: python3 scripts/miner_screenshots.py"""
import io, os, sys, contextlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "miner")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shutil
import sumo_miner as m
from ansi_to_png import render
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "screens"); os.makedirs(out, exist_ok=True)
hud = dict(block=47, rate="2.41 MH/S", guesses=31_250_000, diff="26.0 BITS", reward="20 SUMO", mined=3,
           balance="310", halving=525_553, pays_to="8Hjt...4fhi", reward_won="20 SUMO")
def shot(name, cols, found=False, frame=0, events=()):
    buf = io.StringIO()
    shutil.get_terminal_size = lambda fallback=(120, 30): os.terminal_size((cols, 30))
    s = m.Screen(True); s.frame = frame; s.events = list(events)
    with contextlib.redirect_stdout(buf):
        s.draw(hud, found=found)
    
    render(buf.getvalue(), f"{out}/{name}.png", cols)
    print(name, buf.getvalue().count("\n"), "lines")
ev = ["21:14 Mining on the private Sumo test network with 8 CPU workers",
      "21:15 *** BLOCK FOUND! #46  +20 SUMO after 58,600,000 guesses (24s)"]
shot("miner_mining", 96, frame=1, events=ev)
shot("miner_found", 96, found=True, frame=0, events=ev)
shot("miner_narrow", 80, frame=2, events=ev)
