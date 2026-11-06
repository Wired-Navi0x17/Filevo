---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Probabilistic models
summary: Models that represent uncertainty explicitly: parameter estimation, Bayesian networks and hidden Markov models.
prereq: Mathematical foundations > Bayes' theorem

```definition
A probabilistic model defines a joint distribution over the variables of a problem. Learning fits the distribution's parameters to data, and inference answers questions such as "how likely is this cause, given these observations?".
```

## Maximum likelihood and MAP estimation
summary: Choosing parameters that make the observed data most probable, with or without a prior.

```formula
name: Maximum likelihood estimate
latex: \hat{\theta}_{\text{MLE}} = \arg\max_{\theta} \sum_{i=1}^{n} \log p(x_i \mid \theta)
text: Pick the parameters under which the observed data are most likely; taking logs turns the product of probabilities into a sum.
```

```formula
name: Maximum a posteriori estimate
latex: \hat{\theta}_{\text{MAP}} = \arg\max_{\theta} \Big[ \sum_{i=1}^{n} \log p(x_i \mid \theta) + \log p(\theta) \Big]
text: MAP adds the log of a prior over the parameters; a Gaussian prior gives L2 regularisation and a Laplace prior gives L1.
```

```example
A coin lands heads 7 times in 10 flips. The MLE of the heads probability is 7/10 = 0.7. With a Beta(2, 2) prior, which favours fair coins, the MAP estimate is (7 + 2 - 1) / (10 + 2 + 2 - 2) = 8/12, about 0.67, pulled slightly towards 0.5.
```

```compare
caption: Frequentist and Bayesian views of parameters
Aspect, MLE (frequentist), Bayesian
Parameters, fixed unknown constants, random variables with a prior
Output, one point estimate, a full posterior distribution
Small data, can overfit, prior regularises the estimate
Uncertainty, from confidence intervals, from credible intervals of the posterior
```

## Bayesian networks
summary: Directed acyclic graphs that factor a joint distribution into local conditional distributions.
prereq: Probabilistic models > Maximum likelihood and MAP estimation

```definition
A Bayesian network is a directed acyclic graph where each node is a random variable and each edge points from a direct cause to its effect. Every node stores a conditional probability table given its parents, and the joint distribution is the product of these tables.
```

```formula
name: Factorisation of a Bayesian network
latex: p(x_1, \ldots, x_n) = \prod_{i=1}^{n} p\big(x_i \mid \mathrm{Parents}(x_i)\big)
text: Each variable depends directly only on its parents, which can shrink the number of parameters exponentially.
```

```example
The classic alarm network has Burglary and Earthquake as parents of Alarm, and Alarm as parent of JohnCalls and MaryCalls. The full joint over five binary variables needs 31 numbers; the network needs 1 + 1 + 4 + 2 + 2 = 10.
```

```compare
caption: Inference methods for Bayesian networks
Method, Exact, Idea
Enumeration, yes, sum the joint over hidden variables
Variable elimination, yes, sum out variables one at a time and cache factors
Rejection sampling, no, sample the network and discard samples that contradict the evidence
Likelihood weighting, no, fix the evidence and weight each sample by its likelihood
Gibbs sampling (MCMC), no, resample one variable at a time given its Markov blanket
```

## Hidden Markov models
summary: Sequences of hidden states that emit observations, decoded with the forward and Viterbi algorithms.
prereq: Probabilistic models > Bayesian networks

```definition
A hidden Markov model (HMM) describes a system that moves between hidden states according to transition probabilities, and in each state emits an observation according to emission probabilities. Only the observations are seen.
```

```formula
name: HMM joint probability
latex: p(\mathbf{z}_{1:T}, \mathbf{x}_{1:T}) = p(z_1) \prod_{t=2}^{T} p(z_t \mid z_{t-1}) \prod_{t=1}^{T} p(x_t \mid z_t)
text: The initial state, then a chain of transitions, times the emission of each observation from its state.
```

```formula
name: Forward algorithm
latex: \alpha_t(j) = p(x_t \mid z_t = j) \sum_{i} \alpha_{t-1}(i)\, p(z_t = j \mid z_{t-1} = i)
text: The probability of the observations so far and of being in state j now, computed in O(T K^2) time instead of summing over all K^T state paths.
```

```formula
name: Viterbi recursion
latex: \delta_t(j) = p(x_t \mid z_t = j) \max_{i} \big[ \delta_{t-1}(i)\, p(z_t = j \mid z_{t-1} = i) \big]
text: Replacing the sum with a max gives the probability of the single best state path; back-pointers recover the path itself.
```

```compare
caption: The three classic HMM problems
Problem, Question, Algorithm
Evaluation, how likely are the observations, forward algorithm
Decoding, which hidden state sequence is most likely, Viterbi algorithm
Learning, which parameters best explain the data, Baum-Welch (EM)
```

```application
Speech recognition before deep learning, part-of-speech tagging, gene finding and gesture recognition.
```
