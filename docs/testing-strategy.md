# Testing strategy

## The problem this solves

The bugs that reach this site are almost never logic bugs. The code is usually
right; the **data flowing through it** is wrong, or the **rendered result** is
wrong. Four real examples from a single day:

| bug | visible in code review? |
|---|---|
| episode name shown where the genre goes | no — the component did exactly what it should |
| invisible Unicode in 22 titles | no — a string went into a string field |
| 549 serials missing from the catalog | no — every reference was parsed correctly |
| harvest rewrote the URL manifest 49 113 → 1 538 | no — it "succeeded", exit code 0 |

So the target of testing is **the exported JSON and the rendered page**, not the
source code. This is a gift, not a burden: the site is static, so almost
everything worth asserting can be asserted without a browser.

## Three activities, three rhythms

### 1. Shape sweep — after every catalog sweep, minutes

List the **extremes** of the data, per field: longest and shortest values, empty
fields, unusual characters, rarest values. Do not judge; enumerate. A human scans
the output for ten seconds.

This is what surfaces the unknown-unknowns. `21:00`, `VI`, `#2` and
`Young Rock- Season 1` would all have appeared at the top of such a list months
before anyone noticed them on screen.

### 2. Deep pass — occasionally, on one named surface

Several reviewers in parallel, each with **one narrow, completable task**, all
pointed at the real artifacts:

| lens | would have caught |
|---|---|
| referential integrity — does every reference resolve? | 549 missing serials |
| pipeline — does any stage overwrite instead of merge? | the harvest manifest wipe |
| rendering — screenshots at three widths, read the actual text | genre slot showing an episode name |
| payload — what does a page actually download? | the multi-MB `titles_detail.json` |
| language — does this read naturally in Czech? | `21:00` where a genre belongs |

The value is **diversity of perspective, not depth of one**. A single reviewer
told to "find anything wrong" has a fixed blind spot; five reviewers each given
one completable question do not share it.

Follow with a round that tries to **disprove** the findings. Independent
reviewers always produce plausible-sounding nonsense alongside real defects;
without the adversarial round you get a long list nobody can trust, which is
worse than no list.

Scope it to one surface at a time ("the Kalendár", "the export contract"). Aimed
at "the whole site" it produces mush.

### 3. Immunity — every confirmed bug becomes a permanent check

Activity 2 finds **new** classes. Activity 3 ensures you never see an **old** one
again. Without it you rediscover the same defect forever.

## How findings are recorded

Three levels. **Not every bug gets all three** — that is deliberate, or the
process becomes bureaucracy and gets abandoned.

| level | when | where |
|---|---|---|
| 1. Sighting | always, ten seconds | `docs/bugs.md` |
| 2. Understanding | took >30 min to understand, or could recur | `docs/solutions/<category>/<slug>.md` |
| 3. Immunity | detectable from the data or the export | a rule in `scripts/check_data_quality.py` |

### The link between a write-up and its guard

Each solution doc's frontmatter names the check that protects it:

```yaml
guard: "check_data_quality.py::check_root_references"
```

and an honest "no" is a valid answer, as long as it is a decision rather than an
oversight:

```yaml
guard: "none — not assertable; caught by the shape sweep"
```

Each rule in `check_data_quality.py` names the solution doc in return. So both
questions can be answered: *what is this check protecting?* and *did that fix
ever get a guard, or can it come back quietly?*

## The gates

One command before deploying:

```
python3 scripts/check_all.py
```

| gate | question |
|---|---|
| `check_completeness.py` | is everything **there**? — canary titles, no duplicates, floor count |
| `check_data_quality.py` | are the **values** sane? — readable text, live references, no silent shrink |

Both run even if the first fails; seeing every problem at once beats fixing them
one deploy at a time.

## What a human still has to do

Two things that do not automate:

- **Domain facts.** That Voyo is Oneplay. No amount of analysis produces that.
- **Judging whether text reads naturally** in Czech, in context, on a card next
  to other cards.

Design the process so human attention is spent **only there** — on the output of
the shape sweep — and not on reading code or hunting through 50 000 titles.
