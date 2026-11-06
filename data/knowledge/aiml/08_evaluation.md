---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Model evaluation and selection
summary: Measuring how well a model generalises, choosing between models, and checking that its probabilities can be trusted.
prereq: Supervised learning

```definition
A model is only useful if it works on data it has not seen. Evaluation estimates that generalisation performance with held-out data and suitable metrics, and model selection uses those estimates to choose features, algorithms and hyperparameters without fooling ourselves.
```

## Data splits and cross-validation
summary: Train, validation and test sets, and k-fold cross-validation.

```definition
The training set fits parameters, the validation set chooses hyperparameters and compares models, and the test set is used once at the end to report performance. Using the test set for any decision leaks information and makes the reported score optimistic.
```

```steps
title: k-fold cross-validation
1. Shuffle the data and split it into k equal folds, commonly k = 5 or 10.
2. For each fold, train on the other k - 1 folds and evaluate on the held-out fold.
3. Average the k scores, and report their standard deviation as a measure of stability.
4. Use stratified folds for classification so each fold keeps the class proportions.
```

```pitfall
Data leakage happens when information from outside the training fold reaches the model: scaling with statistics from the whole data set, duplicates shared between train and test, or future data in time-series problems. Fit every preprocessing step inside the training fold, and split time series by time.
```

## Bias-variance trade-off
summary: Underfitting versus overfitting and the decomposition of expected error.

```formula
name: Bias-variance decomposition
latex: \mathbb{E}\big[(y - \hat{f}(\mathbf{x}))^2\big] = \mathrm{Bias}\big[\hat{f}(\mathbf{x})\big]^2 + \mathrm{Var}\big[\hat{f}(\mathbf{x})\big] + \sigma^2
text: Expected squared error splits into bias (error from wrong assumptions), variance (sensitivity to the particular training set) and irreducible noise sigma squared.
```

```compare
caption: Diagnosing underfitting and overfitting
Symptom, Training error, Validation error, Remedy
Underfitting (high bias), high, high, more features or a more flexible model or less regularisation
Overfitting (high variance), low, much higher, more data or regularisation or a simpler model or early stopping
Good fit, low, close to training error, keep the model
```

## Classification metrics
summary: Accuracy, precision, recall, F1, the confusion matrix and ROC-AUC.

```definition
A confusion matrix counts true positives (TP), false positives (FP), true negatives (TN) and false negatives (FN). Every common classification metric is built from these four numbers.
```

```formula
name: Precision, recall and F1
latex: \mathrm{Precision} = \frac{TP}{TP + FP}, \qquad \mathrm{Recall} = \frac{TP}{TP + FN}, \qquad F_1 = \frac{2 \cdot \mathrm{Precision} \cdot \mathrm{Recall}}{\mathrm{Precision} + \mathrm{Recall}}
text: Precision is how many predicted positives are right, recall is how many real positives are found, and F1 is their harmonic mean.
```

```formula
name: Accuracy
latex: \mathrm{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}
text: The share of all predictions that are correct.
```

```example
A fraud model flags 50 transactions, 40 of them truly fraudulent, and misses 10 frauds. Precision is 40/50 = 0.80, recall is 40/50 = 0.80 and F1 is 0.80. If only 1% of 10,000 transactions are fraud, a model that never flags anything still scores 99% accuracy, which is why accuracy misleads on imbalanced data.
```

```definition
The ROC curve plots the true-positive rate against the false-positive rate as the decision threshold moves from 1 to 0. The area under it (ROC-AUC) is the probability that a random positive is scored above a random negative: 0.5 is chance and 1.0 is perfect. For heavily imbalanced problems the precision-recall curve is more informative.
```

```compare
caption: Which classification metric to use
Situation, Prefer, Reason
Balanced classes and equal costs, accuracy, simple and meaningful
False positives are costly (spam filter), precision, avoid flagging good items
False negatives are costly (cancer screening), recall, avoid missing real cases
Imbalanced classes, F1 or PR-AUC, accuracy is dominated by the majority class
Ranking quality across thresholds, ROC-AUC, threshold-independent
```

## Regression metrics
summary: MAE, MSE, RMSE and the coefficient of determination.

```formula
name: Regression error metrics
latex: \mathrm{MAE} = \frac{1}{n}\sum_i |y_i - \hat{y}_i|, \qquad \mathrm{RMSE} = \sqrt{\frac{1}{n}\sum_i (y_i - \hat{y}_i)^2}, \qquad R^2 = 1 - \frac{\sum_i (y_i - \hat{y}_i)^2}{\sum_i (y_i - \bar{y})^2}
text: MAE is robust to outliers, RMSE penalises large errors more and is in the target's units, and R squared is the share of variance explained compared with predicting the mean.
```

## Calibration
summary: Whether predicted probabilities match observed frequencies, measured by ECE and the Brier score and fixed by temperature scaling.
prereq: Mathematical foundations > Information theory

```definition
A classifier is calibrated when its confidence matches reality: of all the predictions made with 80% confidence, about 80% should be correct. Modern neural networks are often over-confident, which matters whenever decisions depend on the probabilities themselves.
```

```formula
name: Expected calibration error
latex: \mathrm{ECE} = \sum_{m=1}^{M} \frac{|B_m|}{n} \, \big| \mathrm{acc}(B_m) - \mathrm{conf}(B_m) \big|
text: Group predictions into M confidence bins and average the gap between accuracy and confidence, weighted by how many predictions fall in each bin.
```

```formula
name: Brier score
latex: \mathrm{BS} = \frac{1}{n}\sum_{i=1}^{n}\sum_{k=1}^{K} \big(p_{ik} - y_{ik}\big)^2
text: The mean squared error between predicted probabilities and one-hot labels; lower is better and it rewards both accuracy and calibration.
```

```formula
name: Temperature scaling
latex: \hat{p}_i = \mathrm{softmax}(\mathbf{z}_i / T), \qquad T^{*} = \arg\min_{T} \; -\sum_{i \in \text{val}} \log \hat{p}_{i, y_i}
text: Divide the logits by one learned temperature T, chosen to minimise negative log-likelihood on validation data; T above 1 softens over-confident predictions without changing which class wins.
```

```application
Calibrated probabilities are needed for risk gates that decide when a system should defer to a human, for medical triage, for weather forecasts and for combining several models' outputs.
```

## Hyperparameter tuning
summary: Grid search, random search and Bayesian optimisation over settings the model does not learn itself.

```compare
caption: Hyperparameter search strategies
Strategy, How it works, When to use
Grid search, try every combination on a grid, two or three hyperparameters with few values
Random search, sample combinations at random, many hyperparameters where only a few matter
Bayesian optimisation, model the score and pick promising points, expensive training runs
Early-stopping schedulers (Hyperband), stop poor runs early, large search spaces with iterative training
```
