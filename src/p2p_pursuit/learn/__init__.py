"""Offline policy search: tune the doctrine between matches, never during one.

Two stages, in this order:

1. **Search.** ``arena`` scores a :class:`~p2p_pursuit.strategy.params.Doctrine`
   as *league points per sub-game* against a population of opponents, and
   ``cem`` moves the vector uphill. The result is frozen into
   ``config/doctrine.json`` and committed, so a counted match plays a fixed
   policy that the audit can reproduce from its ``github_commit``.
2. **Clone.** After a real match the sealed logs contain the opponent's exact
   position and move at every step - the protocol hands us a labelled dataset
   of a live team. ``clone_data`` extracts it, ``clone_fit`` fits a policy to
   it, and that policy joins the population for the next search.

Stage 2 is the point. Self-play alone is a measured liar here: the police
scored 90-98% against our own thief and 0/5 against the live reference peer,
because a simulation with one evader in it teaches you about that evader.
Every match played makes the population one opponent less hypothetical.
"""
