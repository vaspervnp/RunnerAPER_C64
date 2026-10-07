# RUNNER A.P.E.R

## Player's Manual

*Athens Piraeus Electric Railways* · for the Commodore 64 (PAL) · disk

![Runner A.P.E.R](screenshots/01_menu.png)

---

## Loading

1. Switch on your Commodore 64 and the disk drive (device 8).
2. Insert the **RUNNER APER** disk.
3. Type `LOAD"RUNNER",8` and press **RETURN**. When `READY.` appears, type `RUN` and press **RETURN**.

The game takes about two minutes to load on a standard 1541 drive (less with a fast loader cartridge). Then the main
menu comes up.

Plug the joystick into **port 2**, or play with the keyboard.

> Your high scores are saved on the disk, in the file `SCORES`. Do **not** write-protect the disk if you want to keep
> your records.

---

## The story: The Last Souvlaki Man

It's 6:47 a.m. in Kiato. Your uncle Babis, the finest souvlaki man in Piraeus, has just called you in a total panic.
At noon the judge of the "Golden Skewer" contest arrives at his shop, and Babis has left Grandma's secret spice in
Kiato: a little jar labelled "DO NOT TOUCH, BABIS".

You head for the suburban train. It's cancelled "due to the unforeseen presence of a goat on the line". There's no
taxi either, because the only taxi driver in Kiato is Babis himself.

So you run along the tracks with the jar in your pocket. You jump the buffer stops. You climb onto the roofs of
trains that, strangely, run perfectly on time for everyone except you. You grab coins for the ticket you never had
time to buy.

The ticket inspector has been chasing you since Loutraki. So has the goat.

If you don't make it, Babis will season the skewers with supermarket oregano. In Piraeus, that is never forgiven.

**RUN!**

---

## The main menu

Move with **↑ ↓** (the joystick, `Q` / `A` or the cursor keys) and choose with **SPACE** or **FIRE**.

| Option | What it does |
|---|---|
| START | Starts a run |
| CONTROLS | Shows the keys |
| HIGH SCORES | The 8 best runners |
| STORY | Why on earth you are running |
| DIFFICULTY | EASY / MEDIUM / HARD |
| MUSIC | Tunes on or off |
| SOUND | All sound on or off |

Press **L** to switch between English and Greek.

![The menu in Greek](screenshots/02_menu_greek.png)

---

## Controls

| Action | Joystick (port 2) | Keyboard |
|---|---|---|
| Move one lane left | left | `O` or `CRSR ←` |
| Move one lane right | right | `P` or `CRSR →` |
| Jump | up or FIRE | `Q`, `SPACE` or `CRSR ↑` |
| Land quickly | down | `A` or `CRSR ↓` |
| Pause / continue | — | `H` |
| Music on/off | — | `M` |
| Give up, back to the menu | — | `RUN/STOP` |

---

## Playing the game

![In the city](screenshots/05_city.png)

You run at the bottom of the screen and the line comes towards you from the top. There are **three tracks**. Change
lane to dodge what is ahead, jump to clear it, and pick up every coin you can. While you are in the air you fly
**over** coins and power-ups and don't collect them, so time your jumps.

Every run starts with a countdown on the track: **3, 2, 1, GO!** On **HARD** the game first warns you, in the panel
at the bottom, to jump between the wagons.

![The countdown on HARD](screenshots/08_hard_countdown.png)

The line runs through the **city**, beside a busy avenue with cars, buses and kiosks, and out into the **forest**.
Footbridges and road bridges pass overhead, and you run underneath them. The longer you run, the more crowded the
tracks get.

![In the forest](screenshots/06_forest.png)

### Difficulty

| Level | Speed | Special |
|---|---|---|
| EASY | gentle | Obstacles get denser slowly, never more than 2 on one track in a screen |
| MEDIUM | a third faster | Obstacles get denser faster |
| HARD | as MEDIUM | You must **jump the gaps between wagons** when you run on the roofs |

### Heights

The runner gets bigger on screen the higher he is.

| Height | Where you are |
|---|---|
| 1 | On the ground |
| 2 | Jumping from the ground: clears buffer stops |
| 3 | On a train roof |
| 4 | Jumping on a roof, over the wagons |
| 5 | The highest jump above a train |

### Lives

You have **3 lives**. After a crash you blink for a moment: you are protected. When the last life is gone, the game
is over.

---

## The screen

The track takes up the whole width of the screen. The panel at the bottom is the train's dashboard:

- first line: your **score** (white) and the **best score** (cyan), your **coins** and the **lives** left;
- second line: the **route** from Kiato to Piraeus, a mark for every station, the red mark is you. Names show up here
  for two seconds: the power-up you took, the station you are passing, and PAUSE;
- third line: all six **power-ups**: dark when you don't have them, lit with a time bar while they run.

## The route

You run from Kiato to Piraeus: **Corinth, Megara, Elefsina, Aspropyrgos, Rentis, Piraeus**. The bell rings and the
station's name appears in the panel as you pass it, with its platforms on either side of you. **Piraeus gives 1000
points**, and then the route starts again.

---

## Power-ups

A power-up turns up every 50 to 120 rows, never right in front of an obstacle. Some sit on the train roofs: take the
ramp to reach them.

![A power-up](screenshots/07_power_up.png)

| Power-up | Effect | Lasts |
|---|---|---|
| Coin | 10 points | — |
| TURBO | Faster, and the distance counts double (the most common) | 8 s |
| SLOW | Half speed: a breather | 8 s |
| MAGNET | Pulls in the coins of your lane and the lanes next to it | 10 s |
| SUPER JUMP | Jump from the ground right over a train | 10 s |
| HELMET | Saves you from one crash | until hit |
| 2X COINS | Every coin is worth double | 15 s |

TURBO and SLOW cancel each other.

---

## Obstacles

| Obstacle | How to get past |
|---|---|
| Wagon | Change lane, run up a ramp, or use the SUPER JUMP |
| Gap between wagons | On HARD only: jump it when you run on the roofs |
| Locomotive | Don't meet one head-on at ground level! |
| Ramp | Takes you up onto the roof; the end of the train takes you back down |
| Buffer stop | Jump it or change lane |
| Signal | Always red: change lane, or jump it from a train roof (or with the SUPER JUMP) |

---

## Scoring and high scores

```
score = distance (x2 with TURBO) + coins x 10 (x2 with 2X COINS)
```

If your score makes the top 8, enter your initials: **↑ ↓** choose a letter, **SPACE** or **FIRE** accepts it. The
table is saved on the disk (the screen goes dark for a moment while the drive writes), so the records are still there
next time.

![Game over](screenshots/09_game_over.png)

---

## Hints and tips

- Coins on a train roof mean a ramp is near: go up and collect them.
- Don't jump too early: in the air you miss the coins.
- Keep the HELMET for the crowded stretches. It is used up on the first crash.
- SLOW is your friend on HARD when the tracks get full.
- A signal ahead on your track means: change lane now.

---

## Credits

**REVIVE8BIT · 2026 · VASPER**

Runner A.P.E.R for the Commodore 64: 6510 code, multicolor graphics and SID music, from the Amstrad CPC 6128 game.
Inspired by the Athens–Piraeus electric railway (Line 1).

*No goats were harmed in the making of this game.*
