---
name: challenge
description: Use before Gate 1 (consult variants) and before Gate 2 (consult challenge). Calls the independent challenger on the case files, records a written verdict on every objection, runs the capped debate on rejected critical ones, and shows unresolved objections at the gate.
---

# Challenge

The challenger is a strong model from another vendor (the peer model, `STRAT_PEER_*`). It sees
the case files only, never this conversation, so it cannot be talked into agreeing. Its
objections go to `objections.jsonl`; the gate check fails while any of them has no verdict.

| When | Call | It looks for |
|---|---|---|
| Plan, after `options.md` and `table.md` are written, before Gate 1 | `bin/strat consult variants` | a missing option, the best case for "keep as is" and "close", rewordings |
| Options, after the final `options.md`, before Gate 2 | `bin/strat consult challenge` | an objection per option, statements their claims do not support, whether options differ |

## 1. Call the challenger

Run the call. It prints the new objections (`O001 [critical] <target>: <text>`) and logs the
model's tokens and cost. A call that is already logged is not repeated; after you rewrite the
files and want a second look, give a new step id: `--step consult.challenge.2`.

Exit 3 means there is no peer key, or the call failed. Then run the challenger yourself as a
native subagent with a fresh context (in Claude Code: the Task tool with a general-purpose
agent):

1. Give it `agents/challenger.md`, the task text the command printed and the file paths it
   listed. Nothing from this conversation.
2. Save its final JSON answer to `cases/<case>/challenger-<call>.json`.
3. Import it: `bin/strat consult <call> --from-file cases/<case>/challenger-<call>.json`.
   The objections are stored with `by: same-vendor`. Tell the user at the gate that the
   challenger was the same vendor as you, so it is weaker than an outside model.

Exit 1 with "fixed JSON shape" means the answer could not be read: nothing was stored. Run the
call again with a new `--step`, or use the subagent route.

## 2. A verdict on every objection

For each objection decide and write the reason in Russian:

```
bin/strat consult verdict O001 accepted --reason "Добавили вариант ... в options.md"
bin/strat consult verdict O002 rejected --reason "Отток вырос после повышения цены [C004]"
bin/strat consult verdict O003 open --reason "Решат данные о когортах, их нет [C009]"
```

- `accepted`: the option changes, merges or drops. Change `options.md` and `table.md` to match.
  If you agree with it but nothing in the documents changes (the problem stays), it is `open`,
  not `accepted`: "accepted, still open" hides it from the gate.
- `rejected`: the reason must cite the claim that answers the objection; the command refuses a
  rejection without an existing claim id.
- `open`: you cannot answer it with a claim. It is shown to the user at the gate.
- `not-chosen` (after Gate 2 only): the option it targets was not chosen; the reason names the
  chosen option.
- `risk-accepted`: the user said in this chat that they accept the risk; the reason quotes
  their words. Never set it on your own.

Copy each objection with its verdict into "Возражения" in `options.md`, citing claims as usual.

## 3. Debate a rejected critical objection

A critical objection you rejected gets one debate round:
`bin/strat debate O002`. The challenger receives the objection, your reason and the claims they
cite, and concedes or maintains.

- Concedes: the rejection stands.
- Maintains: the verdict becomes `open` again. Decide again in writing: reject with a better
  reason (another round, if the caps allow), accept, or leave it open for the user.

Caps (`config/limits.yaml`, `debate:`): at most 2 rounds per objection and 2 debated objections
per case. The command refuses past them; then the objection stays as it is and goes to the gate.
Without a peer key `strat debate` exits 3: run the subagent as above with the printed task and
import with `bin/strat debate O002 --from-file <file>`.

## 4. Show it at the gate

`bin/strat consult list` prints every objection with its verdict and the unresolved ones: no
verdict, `open`, or rejected while the challenger still maintains it (`DISPUTED`). Show every
unresolved objection to the user at the gate in Russian, with your reason and, for a disputed
one, the challenger's last reply. The user decides on them; you do not hide them.
