# HOW TO MINE SUMO FROG ($SUMO)

*A short guide for friends trying the test miner on Windows.*

> **This is a TEST chain.** Test SUMO has no value, can't be bought or sold, and may be reset before any real launch. This is not an investment. It's a hobby project for trying out mining.

## What you need

- A Windows PC with an internet connection.
- **Python.** The miner runs on Python. If it's missing, the miner tells you, and you install it once (see step 1).
- About 5 minutes. The first run sets itself up, which takes about a minute.

## 1. Install Python (only if you don't have it)

1. Go to **python.org/downloads** and click the big yellow **Download Python** button.
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"**, then click **Install Now**.

Not sure if you have it? Skip this step. If Python is missing, the miner says "Python isn't installed yet" and you can come back here.

## 2. Download and unzip the miner

1. Download the miner: **[sumo-miner-v0.6.zip](downloads/sumo-miner-v0.6.zip)**. Check the file: SHA-256 `6167759cccfbdd0db8a6ee423aef21582b8ca725e1c5ae7c86afaba5d4cac1c9`.
2. Right-click the zip and choose **Extract All…**, then click **Extract**.
3. Open the new folder. Copy `sumo_config.example.json` to `sumo_config.json`, then open that file and replace `YOUR_SERVER` with the test gateway address you were given. The miner cannot connect until you do this. Leave `"network"` set to `"private"` unless you were told to switch it to `"devnet"`. You'll also see `START HERE.txt`, `Mine SUMO.bat`, `Check balance.bat`, `Get test SOL.bat`, `Set payout address.bat` and `Withdraw SOL.bat`.

## 3. Double-click "Mine SUMO"

1. Double-click **Mine SUMO.bat**.
2. If Windows says **"Windows protected your PC"**, click **More info**, then **Run anyway**. It's a plain text script; you can right-click it and choose **Edit** to see exactly what it does.
3. The first time, it sets itself up for about a minute, makes your test wallet and gets you some free test SOL to pay the tiny network fees.
4. Then mining starts. Leave the window open.

![The miner while it's working: the box on the right says ">> MINING..."](screens/miner_mining.png)

While it works, the box on the right says **>> MINING...**. When you win a block, it turns into **\*\*\* BLOCK FOUND! +20 SUMO \*\*\*** and the frog throws its arms up.

![The miner when it wins a block: "*** BLOCK FOUND! +20 SUMO ***"](screens/miner_found.png)

Your computer's fans may speed up. That's normal, because mining uses all of your processor.

**What the numbers mean**

| Label | Meaning |
|---|---|
| BLOCK | the block everyone is racing for right now |
| HASH/S | how many guesses your PC makes per second |
| GUESS # | how many guesses it has made on this block so far |
| DIFF | how hard a block is (each +1 doubles the work) |
| REWARD | SUMO for winning a block: 20 now, halving once a year |
| MINED | blocks you've won since you opened the window |
| BALANCE | SUMO in the wallet your rewards go to |
| HALVING IN | blocks left until the reward halves |

If the window is narrow, the miner hides the frog picture and just shows the numbers. Make the window wider (about 100 columns) to see the frog.

## 4. Send rewards to your own wallet (optional)

By default, rewards stay in the miner's own test wallet. To send them to a wallet you already use:

1. Double-click **Set payout address.bat**.
2. Paste your wallet's **public address** (the one you'd share to receive coins) and press Enter.
3. Check the address it shows you, then type **YES**.

From then on, each reward goes straight to that address. The miner's own test wallet still pays the tiny test fees, so keep a little test SOL in it. To go back, run **Set payout address.bat** again and type **none**.

Advanced: you can also start the miner with `sumo_miner.py mine --payout YOUR_PUBLIC_ADDRESS`.

**Only ever paste a public address.** Never type a seed phrase or private key into the miner or anywhere else. The miner refuses them, and nothing here will ever ask for one.

## 5. Check your balance

Double-click **Check balance.bat** at any time. It shows your test SUMO (and your payout address's SUMO, if you set one), your test SOL and the network stats (blocks mined, difficulty, reward, supply).

## 6. Stop mining

**Close the miner window**, or press **Ctrl+C** in it. You can start again any time with **Mine SUMO.bat**; your coins stay in your wallet.

## 7. Take your test SOL back out (optional)

When you've finished mining on a PC, you can send the miner's leftover test SOL to your own wallet:

1. Double-click **Withdraw SOL.bat**.
2. Paste your wallet's **public address**, or just press Enter to use your payout address (it shows it and asks you to confirm).
3. It shows how much test SOL it will send, where to, and the fee. Type **y** to send, or press Enter to cancel.

It sends everything minus the tiny fee, so the miner's wallet ends at 0 and closes cleanly. If the miner's wallet also holds SUMO (because you mined without a payout address), it asks whether to send that too. It refuses seed phrases, private keys, program addresses and the miner's own address. To mine again afterwards, get test SOL first with **Get test SOL.bat**.

![Withdraw: the amount, the address and the fee are shown before anything is sent](screens/miner_withdraw.png)

Advanced: `sumo_miner.py withdraw YOUR_PUBLIC_ADDRESS --sumo --yes` sends SOL and SUMO without asking.

## Your wallet file: keep it private

- The miner makes its own wallet file called **`sumo-devnet-key.json`** in the miner folder. It's made for you the first time you run Mine SUMO.
- **You never type a seed phrase or private key.** Nothing in this guide or the miner will ever ask for one. If anything does, it isn't us, so don't do it.
- **Don't share that file or send it to anyone.** Whoever has it controls the test coins in it.
- **Don't delete it.** It holds your test SUMO. If you download a newer miner later, unzip it over the same folder and the wallet file stays put.
- It's a test-only wallet. Don't use it for anything else, and don't send real coins to it.

## If something goes wrong

- **"needs a little test SOL for fees"**: double-click **Get test SOL.bat**, wait for it to finish, then start **Mine SUMO.bat** again. The faucet gives one request every 10 minutes.
- **"Python isn't installed yet"**: do step 1, then double-click **Mine SUMO.bat** again.
- **"Install failed"**: check your internet connection and try again.
- **"Another miner got there first"**: that's normal. Someone else won that block, and the miner moves on to the next one by itself.
- **Strange symbols instead of colours**: your console is very old. Run the miner in plain mode: `.venv\Scripts\python.exe sumo_miner.py mine --plain`.

## How it works, in one paragraph

Your computer makes millions of guesses (guess #1, guess #2, ...), looking for a hash that beats the current difficulty. The first miner to find one wins the block and gets the block reward of test SUMO: 20 SUMO now, halving once a year, and never more than 21 million in total. There's no premine and no team share: every SUMO comes from mining. The difficulty adjusts so blocks keep coming at a steady pace however many people are mining.
