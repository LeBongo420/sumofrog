Animated frog sprite (optional)
================================
Pixy can drop animation in this folder only. The miner plays what it
finds here, in this order:

  1. A GIF named frog.gif (or any other .gif)
  2. A sequence of PNG frames named frame_001.png, frame_002.png, ...
     (frog_001.png also works)

To keep the window light, it accepts at most 48 frames, each file at
most 2 MB, and each picture at most 1024 pixels on a side. Larger or
extra files are skipped, as are aliases that point outside this folder,
and the still frog picture is used if nothing valid is left.

Leave this folder otherwise empty and the miner shows the still frog
picture until frames are added. No code change is needed.
