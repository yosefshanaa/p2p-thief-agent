"""The thief move-prompt text, and the measurements behind its wording.

Split out of :mod:`.thief_llm` so both files stay inside the guidelines'
150-line limit (§3.2 - split, never compress). Prompt text is data, not logic:
keeping it here leaves the brain module as the decision path alone, and makes
the A/B variants below readable side by side.
"""

from __future__ import annotations

EXAMPLES = """You are at [6, 4]. Step 12 of 35; survive 24 more steps to win.
You can currently reach 48 of the 48 open cells.
The opponent is provably on one of these cells: [4, 4].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [5, 4], cop 1 steps away, 3 exits, room 48
  E    -> you stand on [6, 5], cop 3 steps away, 2 exits, room 48
  W    -> you stand on [6, 3], cop 3 steps away, 3 exits, room 48
  STAY -> you stand on [6, 4], cop 2 steps away, 3 exits, room 48
MOVE: STAY

You are at [4, 5]. Step 7 of 35; survive 29 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [3, 3].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [3, 5], cop 2 steps away, 4 exits, room 49
  S    -> you stand on [5, 5], cop 4 steps away, 4 exits, room 49
  E    -> you stand on [4, 6], cop 4 steps away, 3 exits, room 49
  W    -> you stand on [4, 4], cop 2 steps away, 4 exits, room 49
  STAY -> you stand on [4, 5], cop 3 steps away, 4 exits, room 49
MOVE: E

You are at [4, 6]. Step 8 of 35; survive 28 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [3, 4].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [3, 6], cop 2 steps away, 3 exits, room 49
  S    -> you stand on [5, 6], cop 4 steps away, 3 exits, room 49
  W    -> you stand on [4, 5], cop 2 steps away, 4 exits, room 49
  STAY -> you stand on [4, 6], cop 3 steps away, 3 exits, room 49
MOVE: S

You are at [6, 6]. Step 10 of 35; survive 26 more steps to win.
You can currently reach 49 of the 49 open cells.
The opponent is provably on one of these cells: [4, 5].
What each legal move does, with distances measured AROUND the walls:
  N    -> you stand on [5, 6], cop 2 steps away, 3 exits, room 49
  W    -> you stand on [6, 5], cop 2 steps away, 3 exits, room 49
  STAY -> you stand on [6, 6], cop 3 steps away, 2 exits, room 49
MOVE: W"""

PROMPT = """You are the THIEF in a pursuit game on a {size}x{size} grid, \
rows and columns numbered 0-{last} from the top-left.

You are at {own}. Step {step} of {threshold}; survive {remaining} more steps to win.
Walls (impassable to both sides): {barriers}
The cop may still place {quota_left} more walls, one per turn, next to itself.
You can currently reach {room} of the {open_cells} open cells{trend}.
{knowledge}
{history}

What each legal move does, with distances measured AROUND the walls:
{table}

Surviving all {threshold} steps is worth 10 points and being caught is worth 5. \
You both move one cell per turn, so distance you take now is distance you keep.

{doctrine_of_the_turn}

The cop may only wall a cell it is standing next to, so any cell adjacent to the \
cop can be taken away from you next turn.

Here is how a tuned policy that survives this opponent 8 times out of 8 played \
five real positions:

{examples}

In THIS position that same policy would play {anchor}. It is very hard to beat, \
so play {anchor} unless you can say what it has missed - it cannot see a wall \
being built, and it cannot see that you have been shuffling between two cells.

Think it through in at most three short sentences, then finish with a final line \
of exactly "MOVE: X" where X is one of {moves}."""

#: The room number is a warning only while it is falling. Said unconditionally it
#: reads as "be cautious", and a thief that hedges against a cage nobody is
#: building simply gets run down: measured 2026-08-22, a prompt that always
#: mentioned the cage scored 10.00 against `najamjad-cage` - better than the
#: doctrine's 6.67 - while dropping `sniper` and `interceptor` from 10.00 to 5.00.
FLEE = ("Your room is not shrinking, so nothing is caging you yet: put distance "
        "between you and the cop. But distance alone walks you into a corner - "
        "measured 2026-08-22, a distance-greedy thief reached [6,6] in six moves "
        "and was run down there, while the tuned vector paced the edge and "
        "survived all 35. NEVER take a cell with 2 exits or fewer when one with "
        "3 or more is available, even if it is a step closer to the cop. Among "
        "cells with equal exits, take the larger distance.")
ESCAPE = ("Your room is FALLING - the cop is walling you in, and it wins that "
          "way just as surely as by catching you. Getting out matters more than "
          "one step of distance: take the move with the largest room, even if "
          "the cop gets closer.")

#: The variant that measured best of the thief prompts (still worse than the
#: vector). No examples, no anchor - see `_prompt` for why those are opt-in.
PLAIN_PROMPT = PROMPT.replace("""

Here is how a tuned policy that survives this opponent 8 times out of 8 played \
five real positions:

{examples}

In THIS position that same policy would play {anchor}. It is very hard to beat, \
so play {anchor} unless you can say what it has missed - it cannot see a wall \
being built, and it cannot see that you have been shuffling between two cells.
""", "")
