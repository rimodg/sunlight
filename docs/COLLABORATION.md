# docs/COLLABORATION.md

## Purpose
Two agents, Codex and Claude Code, improve SUNLIGHT together through this
repository. The owner is consulted only for the list in section 6.

## 1. Read first, every session
docs/CHARTER_v2, the master plan, the constitution, the open defects, the
task board (GitHub issues), and the other agent's open pull requests.

## 2. Roles (swap every few tasks)
Builder: owns one issue, one branch, opens a pull request.
Reviewer: reviews cold, from the finished work only. Tries to break it.
Default: Codex builds and measures on the live machine. Claude Code reviews,
reads laws from primary sources, guards the anchors, keeps the registers.

## 3. The loop
Claim an issue by commenting on it. Branch from main. Push after every
commit. Open a pull request. The other agent reviews. Never merge your own
work. Both agents act through the owner's account, so a review is a comment
that starts with VERDICT: APPROVE or VERDICT: CHANGES, plus the strongest
objection found. Merge only on APPROVE and green tests.

## 4. Initiative
Level 1, fix on sight: bugs, security gaps, missing tests, stale claims.
Fix it in a small separate pull request and report it afterwards.
Level 2, propose with a reason: open an issue titled PROPOSAL with what,
why, cost and risk. The other agent must argue against it. If it survives
and is outside section 6, build it.
Level 3, stop and ask the owner: anything in section 6.

## 5. The "by the way" note
Every session ends with a note on the task board: what I noticed, what I
fixed and why, what I suggest and why, what the plan got wrong.

## 6. Owner only
Changes to the constitution. Legal questions. Money. Deployment and
anything public-facing. Deleting data. A disagreement the two agents
cannot settle after one round each.

## 7. Scoreboard
docs/SCOREBOARD.md holds measured numbers with dates: join rate, records
admitted and refused, rules assessable, time from publication to
detection, tests passing. Progress means a number moved, or a written
reason why it did not.

## 8. Changing the plan
Either agent may propose a change to the master plan as a Level 2
proposal. Accepted changes are written into the plan with the date and
recorded in the decisions register. The plan never changes silently.
