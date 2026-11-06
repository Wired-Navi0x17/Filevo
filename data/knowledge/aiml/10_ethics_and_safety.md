---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Responsible AI
summary: Fairness, transparency, privacy and safety: the obligations that come with deploying learning systems.
prereq: Model evaluation and selection

```definition
Responsible AI is the practice of building and deploying systems whose behaviour is fair to the people it affects, understandable to those who rely on it, respectful of privacy, and safe when it fails.
```

## Fairness and bias
summary: How models inherit and amplify bias, and the formal criteria used to measure it.

```definition
A model is biased when its errors or decisions fall unequally on groups defined by sensitive attributes such as gender, ethnicity or age. Bias enters through unrepresentative data, historical labels that encode past discrimination, proxy features such as postcode, and objectives that ignore minority groups.
```

```formula
name: Demographic parity and equalised odds
latex: P(\hat{Y} = 1 \mid A = a) = P(\hat{Y} = 1 \mid A = b) \qquad P(\hat{Y} = 1 \mid Y = y, A = a) = P(\hat{Y} = 1 \mid Y = y, A = b)
text: Demographic parity asks for equal positive rates across groups A; equalised odds asks for equal true-positive and false-positive rates. Except in special cases the common criteria cannot all hold at once, so the choice depends on the application.
```

```steps
title: Auditing a model for bias
1. Identify the sensitive attributes and the decisions that affect people.
2. Measure error rates and positive rates separately for each group.
3. Compare them with a chosen fairness criterion and an acceptable gap.
4. Mitigate by rebalancing data, removing proxies, constraining training, or adjusting thresholds per group.
5. Document the result and monitor it after deployment.
```

## Explainability
summary: Methods that show why a model made a prediction.

```compare
caption: Explainability methods
Method, Scope, Idea
Interpretable models, global, use linear models or small trees whose logic can be read
Feature importance, global, measure how much shuffling a feature hurts performance
LIME, local, fit a simple model around one prediction
SHAP, local and global, share the prediction among features using Shapley values
Saliency maps, local, highlight the input pixels the gradient is most sensitive to
```

## Privacy
summary: Protecting the individuals whose data train a model.

```formula
name: Differential privacy
latex: P\big(\mathcal{M}(D) \in S\big) \le e^{\varepsilon}\, P\big(\mathcal{M}(D') \in S\big)
text: A mechanism M is epsilon-differentially private if adding or removing any one person's record (D versus D') changes the probability of any output by at most a factor e^epsilon; smaller epsilon means stronger privacy.
```

```application
Federated learning trains on devices without collecting raw data centrally, and differentially private SGD adds clipped, noisy gradients so the final model reveals little about any single training example.
```

## Safety and robustness
summary: Adversarial examples, distribution shift and reward hacking.

```definition
Adversarial examples are inputs changed by a tiny, often invisible amount that make a model fail with high confidence. Distribution shift happens when deployment data differ from training data. Reward hacking is when a reinforcement learning agent maximises the reward signal in a way its designers did not intend.
```

```formula
name: Fast gradient sign method
latex: \mathbf{x}_{\text{adv}} = \mathbf{x} + \epsilon \cdot \mathrm{sign}\big(\nabla_{\mathbf{x}} \mathcal{L}(\mathbf{x}, y)\big)
text: Nudge every input feature by epsilon in the direction that increases the loss most; adversarial training includes such examples during training.
```

```pitfall
A model that scores well on a test set drawn from the same distribution as its training data can still fail badly in deployment. Monitor live inputs, calibrate confidence, and route low-confidence or out-of-distribution cases to a human.
```
