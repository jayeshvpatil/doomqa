doomqa

[01Findings](#findings) [02Coverage race](#coverage) [03State model](#states) [04Smoke matrix](#smoke) [05Replay](#clip) [06What carries over](#mapping)

Agentic game QA · open-source demo

# Pointing a game-testing agent harness at a real open-source shooter

01 · Findings

## What the agents found, after triage

Every candidate was re-run in a fresh game process before it became a ticket.

02 · Coverage race

## Curiosity agent vs. random walk, same budget

The maps below show seed 1; the table averages all seeds. Both agents get the same number of game tics and the same action style. The curiosity agent keeps an archive of save states and goes back to the cells it has visited least (Go-Explore with a count-based novelty weight). Press play or drag the timeline.

Curiosity agent

Random walk

Curiosity agentRandom walkShare of map cells reached vs. game time

03 · State model

## Which player-state transitions the combat bot exercised

The combat bot plays without god mode: it aims at visible monsters and fires, and otherwise roams. Every step is classified into a player state, and each change of state is counted against the transitions a designer would expect to see.

04 · Smoke matrix

## All 32 maps boot, spawn, move, fire and hold invariants

The scripted bot runs each map for about 20 seconds of game time. Throughput was measured afterwards, one map at a time. The first, parallel run had flagged MAP28 as five times slower than the median; measured on its own it sits in the normal range, so there is no performance ticket.

Combat bot playing MAP03, replayed from its recorded demo

05 · Replay

## Every combat run is recorded as an engine demo

06 · What carries over

## What would transfer to a larger shooter