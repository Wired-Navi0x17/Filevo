---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Mathematical foundations
summary: The probability, linear algebra, calculus, information theory and optimisation that every learning algorithm is built on.

```definition
Machine learning describes data, models and errors with mathematics. Probability measures uncertainty, linear algebra represents data as vectors and matrices, calculus says how a quantity changes when parameters change, information theory measures surprise and difference between distributions, and optimisation searches for the parameters that make a loss as small as possible.
```

## Probability and statistics
summary: Random variables, distributions, expectation, variance and the rules for combining uncertain events.

```definition
A random variable X maps each outcome of an experiment to a number. Its probability distribution says how likely each value is: a probability mass function p(x) for discrete X, and a probability density function f(x) for continuous X, where probabilities come from areas under f.
```

```formula
name: Expectation
latex: \mathbb{E}[X] = \sum_{x} x \, p(x) \qquad \mathbb{E}[X] = \int x \, f(x)\, dx
text: The expected value is the probability-weighted average of all values the variable can take.
```

```formula
name: Variance
latex: \mathrm{Var}(X) = \mathbb{E}\big[(X - \mathbb{E}[X])^2\big] = \mathbb{E}[X^2] - \mathbb{E}[X]^2
text: Variance measures how far values spread from the mean; its square root is the standard deviation.
```

```formula
name: Sum and product rules
latex: p(x) = \sum_{y} p(x, y) \qquad p(x, y) = p(x \mid y)\, p(y)
text: Marginalising sums a joint distribution over the variable you do not care about; the product rule factors a joint distribution into a conditional times a marginal.
```

```formula
name: Gaussian (normal) density
latex: \mathcal{N}(x \mid \mu, \sigma^2) = \frac{1}{\sqrt{2\pi\sigma^2}} \exp\!\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)
text: The bell curve with mean mu and variance sigma squared; sums of many independent effects tend towards it (central limit theorem).
```

```compare
caption: Common probability distributions and where they appear in machine learning
Distribution, Support, Parameters, Typical use
Bernoulli, {0 1}, p, Binary labels and logistic regression
Categorical, {1 ... K}, p_1 ... p_K, Multi-class labels and softmax outputs
Binomial, {0 ... n}, n and p, Counts of successes in n trials
Poisson, {0 1 2 ...}, lambda, Event counts per interval
Gaussian, real line, mu and sigma^2, Noise models and linear regression
Beta, [0 1], alpha and beta, Prior over a probability
Dirichlet, probability simplex, alpha vector, Prior over categorical probabilities
```

```pitfall
Independence is not the same as zero correlation. Two variables can have zero covariance and still depend on each other non-linearly, for example X uniform on [-1, 1] and Y = X squared.
```

## Bayes' theorem
summary: How to update a belief about a hypothesis after seeing evidence.
prereq: Mathematical foundations > Probability and statistics

```definition
Bayes' theorem turns the probability of the evidence given a hypothesis into the probability of the hypothesis given the evidence. The prior p(h) is the belief before data, the likelihood p(d | h) says how well the hypothesis explains the data, and the posterior p(h | d) is the updated belief.
```

```formula
name: Bayes' theorem
latex: p(h \mid d) = \frac{p(d \mid h)\, p(h)}{p(d)} = \frac{p(d \mid h)\, p(h)}{\sum_{h'} p(d \mid h')\, p(h')}
text: Posterior equals likelihood times prior, divided by the evidence that normalises the result.
```

```example
A test for a disease that affects 1% of people has 99% sensitivity and a 5% false-positive rate. For a positive result, p(disease | +) = 0.99 x 0.01 / (0.99 x 0.01 + 0.05 x 0.99) = 0.0099 / 0.0594, which is about 0.167. Even after a positive test, the chance of having the disease is only about 17%, because the disease is rare.
```

```pitfall
Base-rate neglect: ignoring the prior p(h) makes rare events look far more likely than they are after a positive signal.
```

## Linear algebra
summary: Vectors, matrices, dot products, norms, eigen-decomposition and the singular value decomposition.

```definition
A data set with n examples and d features is a matrix X with n rows and d columns. A model's parameters are often a vector w, and a prediction for every example at once is the matrix-vector product Xw.
```

```formula
name: Dot product and cosine similarity
latex: \mathbf{a} \cdot \mathbf{b} = \sum_{i=1}^{d} a_i b_i = \lVert \mathbf{a} \rVert \, \lVert \mathbf{b} \rVert \cos\theta
text: The dot product measures how much two vectors point the same way; dividing by both lengths gives cosine similarity in [-1, 1].
```

```formula
name: Lp norms
latex: \lVert \mathbf{x} \rVert_1 = \sum_i |x_i| \qquad \lVert \mathbf{x} \rVert_2 = \sqrt{\sum_i x_i^2}
text: The L1 norm adds absolute values and the L2 norm is Euclidean length; both reappear as regularisation penalties.
```

```formula
name: Eigen-decomposition
latex: A\mathbf{v} = \lambda \mathbf{v} \qquad A = Q \Lambda Q^{\top} \text{ for symmetric } A
text: An eigenvector keeps its direction when multiplied by A and is only scaled by its eigenvalue lambda; a symmetric matrix factors into orthogonal eigenvectors and real eigenvalues.
```

```formula
name: Singular value decomposition
latex: X = U \Sigma V^{\top}
text: Any matrix factors into two orthogonal matrices and a diagonal matrix of non-negative singular values; keeping the largest k singular values gives the best rank-k approximation.
```

```application
Principal component analysis, least-squares regression, recommender systems (matrix factorisation) and word embeddings all reduce to matrix products and decompositions.
```

## Calculus and gradients
summary: Derivatives, partial derivatives, the gradient, the chain rule and the Jacobian.

```definition
The gradient of a scalar function f(w) is the vector of its partial derivatives. It points in the direction of steepest increase, so stepping against it decreases f fastest.
```

```formula
name: Gradient
latex: \nabla_{\mathbf{w}} f = \left( \frac{\partial f}{\partial w_1}, \ldots, \frac{\partial f}{\partial w_d} \right)
text: Each component says how much f changes when one parameter changes a little.
```

```formula
name: Chain rule
latex: \frac{\partial L}{\partial x} = \frac{\partial L}{\partial y} \cdot \frac{\partial y}{\partial x}
text: The derivative of a composed function is the product of the derivatives along the path; backpropagation applies it layer by layer.
```

```formula
name: Taylor approximation
latex: f(\mathbf{w} + \boldsymbol{\delta}) \approx f(\mathbf{w}) + \nabla f(\mathbf{w})^{\top}\boldsymbol{\delta} + \tfrac{1}{2}\boldsymbol{\delta}^{\top} H \boldsymbol{\delta}
text: Near a point, a smooth function looks like a plane (first order) or a bowl given by the Hessian H (second order); this justifies gradient and Newton methods.
```

## Information theory
summary: Entropy, cross-entropy, KL divergence, Jensen-Shannon divergence and mutual information.
prereq: Mathematical foundations > Probability and statistics

```definition
Information theory measures uncertainty in bits. A sure event carries no information; a rare event carries a lot. Entropy is the average information of a distribution, and divergences measure how different two distributions are.
```

```formula
name: Shannon entropy
latex: H(P) = -\sum_{i} p_i \log_2 p_i
text: Entropy is zero when one outcome is certain and is largest, log2 K, when all K outcomes are equally likely.
```

```formula
name: Cross-entropy
latex: H(P, Q) = -\sum_{i} p_i \log q_i
text: The average cost of encoding data from P with a code built for Q; it is the standard classification loss when P is the one-hot label and Q the model's prediction.
```

```formula
name: Kullback-Leibler divergence
latex: D_{\mathrm{KL}}(P \,\|\, Q) = \sum_{i} p_i \log \frac{p_i}{q_i} = H(P, Q) - H(P)
text: KL divergence is the extra cost of using Q instead of P. It is never negative, is zero only when P equals Q, and is not symmetric.
```

```formula
name: Jensen-Shannon divergence
latex: \mathrm{JSD}(P \,\|\, Q) = \tfrac{1}{2} D_{\mathrm{KL}}(P \,\|\, M) + \tfrac{1}{2} D_{\mathrm{KL}}(Q \,\|\, M), \quad M = \tfrac{1}{2}(P + Q)
text: A symmetric, bounded version of KL; with log base 2 it lies between 0 and 1.
```

```formula
name: Mutual information
latex: I(X; Y) = D_{\mathrm{KL}}\big(p(x, y) \,\|\, p(x)p(y)\big) = H(X) - H(X \mid Y)
text: How much knowing Y reduces uncertainty about X; zero exactly when X and Y are independent.
```

```application
Decision trees split on the feature with the highest information gain, classifiers minimise cross-entropy, variational autoencoders penalise a KL term, and calibration methods compare predicted and true distributions.
```

## Optimisation
summary: Loss functions, convexity, gradient descent and its variants, and regularisation.
prereq: Mathematical foundations > Calculus and gradients

```definition
Training a model means choosing parameters w that minimise a loss L(w) averaged over the training data. Optimisation is the set of methods that search for that minimum.
```

```formula
name: Empirical risk
latex: \hat{R}(\mathbf{w}) = \frac{1}{n}\sum_{i=1}^{n} \ell\big(f_{\mathbf{w}}(\mathbf{x}_i), y_i\big)
text: The average loss over the n training examples; minimising it is empirical risk minimisation.
```

```intuition
A function is convex when the straight line between any two points on its graph lies above the graph. Convex losses, such as squared error for linear regression and log loss for logistic regression, have no bad local minima, so gradient descent reaches the global minimum. Neural network losses are not convex, but gradient methods still work well in practice.
```

### Gradient descent
summary: Repeatedly step against the gradient of the loss.

```formula
name: Gradient descent update
latex: \mathbf{w}_{t+1} = \mathbf{w}_t - \eta \, \nabla_{\mathbf{w}} L(\mathbf{w}_t)
text: Move the parameters a small step of size eta (the learning rate) downhill.
```

```steps
title: Batch gradient descent
1. Initialise the parameters w, for example to zeros or small random values.
2. Compute the loss and its gradient over the whole training set.
3. Update w by subtracting the learning rate times the gradient.
4. Repeat until the loss stops decreasing or a step budget is used up.
```

```pitfall
A learning rate that is too large makes the loss oscillate or explode; one that is too small makes training painfully slow. A learning-rate schedule or warm-up often helps.
```

### Stochastic and mini-batch gradient descent
summary: Estimate the gradient from a random subset of examples.

```definition
Stochastic gradient descent (SGD) uses one example, and mini-batch SGD uses a small batch of B examples, to estimate the gradient. Each step is cheap and noisy, and the noise can help escape flat regions and saddle points.
```

```formula
name: Mini-batch gradient
latex: \mathbf{g}_t = \frac{1}{B}\sum_{i \in \mathcal{B}_t} \nabla_{\mathbf{w}} \ell\big(f_{\mathbf{w}}(\mathbf{x}_i), y_i\big)
text: An unbiased estimate of the full gradient whose variance shrinks as the batch size B grows.
```

### Momentum and Adam
summary: Optimisers that smooth and rescale the gradient.

```formula
name: Momentum
latex: \mathbf{v}_{t+1} = \beta \mathbf{v}_t + \mathbf{g}_t, \qquad \mathbf{w}_{t+1} = \mathbf{w}_t - \eta \mathbf{v}_{t+1}
text: Momentum keeps a running velocity, so consistent gradient directions build speed and zig-zags cancel out; beta is typically 0.9.
```

```formula
name: Adam
latex: \mathbf{m}_t = \beta_1 \mathbf{m}_{t-1} + (1-\beta_1)\mathbf{g}_t, \quad \mathbf{v}_t = \beta_2 \mathbf{v}_{t-1} + (1-\beta_2)\mathbf{g}_t^2, \quad \mathbf{w}_{t} = \mathbf{w}_{t-1} - \eta \frac{\hat{\mathbf{m}}_t}{\sqrt{\hat{\mathbf{v}}_t} + \epsilon}
text: Adam keeps moving averages of the gradient and of its square, corrects their start-up bias (the hats), and scales each parameter's step by its own recent gradient size. Common defaults are beta1 = 0.9, beta2 = 0.999 and epsilon = 1e-8.
```

```compare
caption: Gradient-based optimisers compared
Optimiser, State kept, Strength, Weakness
SGD, none, Simple and generalises well, Sensitive to learning rate
SGD with momentum, velocity, Faster through ravines, One more hyperparameter
RMSProp, squared-gradient average, Adapts per-parameter step, Can be unstable without tuning
Adam, first and second moments, Fast and robust default, May generalise slightly worse than tuned SGD
```

### Regularisation
summary: Penalties and techniques that stop a model fitting noise.

```definition
Regularisation adds a preference for simpler models so that the model generalises to new data instead of memorising the training set.
```

```formula
name: L2 and L1 regularised loss
latex: L_{\text{ridge}}(\mathbf{w}) = \hat{R}(\mathbf{w}) + \lambda \lVert \mathbf{w} \rVert_2^2 \qquad L_{\text{lasso}}(\mathbf{w}) = \hat{R}(\mathbf{w}) + \lambda \lVert \mathbf{w} \rVert_1
text: L2 (ridge, weight decay) shrinks all weights smoothly; L1 (lasso) pushes many weights exactly to zero and so selects features. Lambda sets the strength.
```

```application
Weight decay, dropout, early stopping and data augmentation are the regularisers used most often when training neural networks.
```
