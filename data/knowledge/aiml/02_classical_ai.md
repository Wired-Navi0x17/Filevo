---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Intelligent agents and search
summary: Agents that perceive and act, and the search algorithms they use to find sequences of actions that reach a goal.

```definition
An agent perceives its environment through sensors and acts on it through actuators. A rational agent chooses the action that is expected to maximise its performance measure given what it has perceived so far.
```

## Agents and environments
summary: The PEAS description and the properties that make an environment easy or hard.

```definition
An agent is specified by PEAS: the Performance measure, the Environment, the Actuators and the Sensors. An automated taxi, for example, is measured on safety, speed and comfort, works on roads with traffic and pedestrians, acts through steering, accelerator and brakes, and senses through cameras, lidar, GPS and speedometer.
```

```compare
caption: Environment properties that decide which kind of agent is needed
Property, Easy case, Hard case
Observability, Fully observable (chess), Partially observable (poker)
Determinism, Deterministic (puzzle), Stochastic (driving)
Episodes, Episodic (image labelling), Sequential (navigation)
Change, Static (crossword), Dynamic (traffic)
State space, Discrete (board games), Continuous (robot arm)
Agents, Single agent (maze), Multi-agent (football)
```

```compare
caption: Agent architectures from simplest to most capable
Agent type, Decides using, Limitation
Simple reflex, Current percept and condition-action rules, Fails when the world is partially observable
Model-based reflex, Internal state of the world, Has no explicit goal
Goal-based, Goals and search or planning, Treats all goal states as equally good
Utility-based, A utility function over states, Needs a utility to be specified
Learning agent, Feedback that improves its own components, Needs data and exploration
```

## Problem formulation
summary: States, actions, transition model, goal test and path cost.

```definition
A search problem is defined by an initial state, the actions available in each state, a transition model that gives the result of an action, a goal test, and a path cost function. A solution is a sequence of actions from the initial state to a goal state; an optimal solution has the lowest path cost.
```

```formula
name: Search complexity measures
latex: O(b^{d}) \text{ nodes for breadth-first search}, \qquad O(b^{m}) \text{ for depth-first search}
text: The branching factor b is the number of successors per state, d is the depth of the shallowest goal, and m is the maximum depth of the search tree.
```

## Uninformed search
summary: Breadth-first, uniform-cost, depth-first and iterative deepening search, which use no knowledge about where the goal is.
prereq: Intelligent agents and search > Problem formulation

```definition
Uninformed (blind) search strategies only know how to generate successors and recognise a goal. They differ in the order in which they expand nodes from the frontier.
```

```steps
title: Breadth-first search
1. Put the initial state in a first-in, first-out queue and mark it as reached.
2. Remove the oldest node from the queue.
3. For each successor that has not been reached, test whether it is a goal; if so, return the path.
4. Otherwise mark it as reached and add it to the back of the queue.
5. Repeat from step 2 until the queue is empty, which means there is no solution.
```

```steps
title: Uniform-cost search (Dijkstra's algorithm)
1. Put the initial state in a priority queue ordered by path cost g(n).
2. Pop the node with the lowest g(n); if it is a goal, return its path.
3. Expand it, and for each successor compute g = g(parent) + step cost.
4. Add the successor, or replace a worse copy already in the queue.
5. Repeat until the queue is empty.
```

```compare
caption: Properties of uninformed search strategies
Strategy, Complete, Optimal, Time, Space
Breadth-first, yes if b is finite, yes with unit step costs, O(b^d), O(b^d)
Uniform-cost, yes if step costs are positive, yes, O(b^(1+C*/e)), O(b^(1+C*/e))
Depth-first, no in infinite spaces, no, O(b^m), O(bm)
Depth-limited, no, no, O(b^l), O(bl)
Iterative deepening, yes, yes with unit step costs, O(b^d), O(bd)
```

```pitfall
Depth-first search can run forever down an infinite branch, and breadth-first search runs out of memory long before it runs out of time. Iterative deepening combines the small memory of depth-first search with the completeness of breadth-first search.
```

## Informed search
summary: Greedy best-first and A* search, which use a heuristic estimate of the distance to the goal.
prereq: Intelligent agents and search > Uninformed search

```definition
Informed search uses a heuristic h(n), an estimate of the cheapest cost from node n to a goal, to expand the most promising nodes first.
```

```formula
name: A* evaluation function
latex: f(n) = g(n) + h(n)
text: A* expands the node with the smallest estimated total cost: the cost already paid g(n) plus the estimated cost still to pay h(n).
```

```formula
name: Admissibility and consistency
latex: h(n) \le h^{*}(n) \qquad h(n) \le c(n, a, n') + h(n')
text: An admissible heuristic never overestimates the true cost h*(n); a consistent heuristic obeys the triangle inequality. With an admissible heuristic tree-search A* is optimal, and with a consistent one graph-search A* is optimal.
```

```example
For route finding on a map, the straight-line distance to the destination is admissible, because no road can be shorter than a straight line. For the 8-puzzle, the sum of Manhattan distances of the tiles from their goal squares is admissible and dominates the number of misplaced tiles, so it expands fewer nodes.
```

```compare
caption: Greedy best-first search versus A*
Algorithm, Expands lowest, Optimal, Typical behaviour
Greedy best-first, h(n), no, Fast but can follow a misleading heuristic
A*, g(n) + h(n), yes with an admissible heuristic, Expands every node with f below the optimal cost
```

## Adversarial search
summary: Minimax and alpha-beta pruning for two-player, zero-sum games.
prereq: Intelligent agents and search > Problem formulation

```definition
In a two-player zero-sum game one player's gain is the other's loss. The MAX player chooses moves that maximise the final utility and assumes the MIN player will choose moves that minimise it.
```

```formula
name: Minimax value
latex: \mathrm{MM}(s) = \begin{cases} \mathrm{Utility}(s) & \text{if } s \text{ is terminal} \\ \max_{a} \mathrm{MM}(\mathrm{Result}(s,a)) & \text{if MAX moves} \\ \min_{a} \mathrm{MM}(\mathrm{Result}(s,a)) & \text{if MIN moves} \end{cases}
text: The value of a position is the utility reached when both sides play optimally from it.
```

```steps
title: Alpha-beta pruning
1. Search the game tree depth-first as in minimax, carrying two bounds: alpha (the best value MAX can guarantee so far) and beta (the best value MIN can guarantee so far).
2. At a MAX node, update alpha with each child's value.
3. At a MIN node, update beta with each child's value.
4. Stop exploring a node's remaining children as soon as alpha is greater than or equal to beta, because the opponent would never allow play to reach it.
5. Return the same move that full minimax would return.
```

```intuition
With perfect move ordering alpha-beta examines about b^(m/2) nodes instead of b^m, which lets it search roughly twice as deep in the same time. Real game programs add move ordering, transposition tables and a depth cut-off with an evaluation function.
```

## Constraint satisfaction problems
summary: Variables, domains and constraints, solved with backtracking search and constraint propagation.

```definition
A constraint satisfaction problem (CSP) has a set of variables, a domain of possible values for each, and constraints that restrict which combinations of values are allowed. A solution assigns every variable a value that satisfies every constraint. Map colouring, timetabling and Sudoku are CSPs.
```

```steps
title: Backtracking search with heuristics
1. Pick an unassigned variable with the minimum-remaining-values heuristic (fewest legal values left).
2. Try its values in least-constraining-value order (the value that rules out the fewest options for neighbours).
3. After each assignment run forward checking or arc consistency (AC-3) to remove now-impossible values from neighbouring domains.
4. If some domain becomes empty, undo the assignment and try the next value.
5. If every value fails, backtrack to the previous variable.
```

```definition
Arc consistency: an arc X to Y is consistent if every value of X has some value of Y that satisfies the constraint between them. AC-3 repeatedly removes values that break this rule until no more can be removed.
```

## Logic and knowledge representation
summary: Propositional and first-order logic, inference by resolution, and forward and backward chaining.

```definition
A knowledge-based agent stores facts as sentences in a formal language and derives new sentences by inference. Propositional logic uses true/false symbols joined by connectives; first-order logic adds objects, relations, functions and the quantifiers for all and there exists.
```

```formula
name: Entailment and modus ponens
latex: KB \models \alpha \qquad \frac{\alpha \Rightarrow \beta, \quad \alpha}{\beta}
text: A knowledge base entails alpha when alpha is true in every model where the knowledge base is true; modus ponens derives beta from an implication and its premise.
```

```compare
caption: Inference methods for knowledge bases
Method, Works on, Direction, Complete for
Model checking, propositional logic, enumerate models, propositional logic
Resolution, clauses in conjunctive normal form, proof by contradiction, propositional and first-order logic
Forward chaining, definite clauses, data-driven, definite clauses
Backward chaining, definite clauses, goal-driven, definite clauses
```

## Classical planning
summary: Describing actions by preconditions and effects and searching for plans that reach a goal.
prereq: Intelligent agents and search > Informed search

```definition
In classical planning (STRIPS/PDDL), a state is a set of facts, and each action has preconditions that must hold and effects that add or delete facts. A planner searches for a sequence of actions that turns the initial state into one that satisfies the goal.
```

```intuition
Planners use domain-independent heuristics, such as ignoring delete effects to get a relaxed problem, so the same A* style search works for logistics, robot tasks and games without hand-written heuristics.
```
