---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Supervised learning
summary: Learning a function from inputs to known outputs using labelled examples, for regression and classification.
prereq: Mathematical foundations > Optimisation

```definition
In supervised learning each training example is a pair (x, y): an input x and the correct output y. The algorithm learns a function f such that f(x) is close to y on new, unseen inputs. When y is a real number the task is regression; when y is a category it is classification.
```

```steps
title: The supervised learning workflow
1. Collect labelled data and split it into training, validation and test sets.
2. Choose features and a model family.
3. Fit the model's parameters on the training set by minimising a loss.
4. Tune hyperparameters on the validation set.
5. Report final performance once on the untouched test set.
```

## Linear regression
summary: Predicting a real value as a weighted sum of features, fitted by least squares.

```definition
Linear regression models the output as a weighted sum of the inputs plus a bias. It is fitted by choosing the weights that minimise the mean squared error between predictions and targets.
```

```formula
name: Linear model
latex: \hat{y} = \mathbf{w}^{\top}\mathbf{x} + b
text: The prediction is the dot product of the weight vector and the feature vector, plus an intercept b.
```

```formula
name: Mean squared error
latex: \mathrm{MSE}(\mathbf{w}) = \frac{1}{n}\sum_{i=1}^{n} \big(y_i - \mathbf{w}^{\top}\mathbf{x}_i\big)^2
text: The average squared distance between each target and its prediction.
```

```formula
name: Normal equation
latex: \mathbf{w}^{*} = \big(X^{\top}X\big)^{-1} X^{\top}\mathbf{y}
text: The closed-form least-squares solution; it costs about O(d^3) to invert, so gradient descent is preferred when the number of features d is large.
```

```formula
name: Ridge regression solution
latex: \mathbf{w}^{*}_{\text{ridge}} = \big(X^{\top}X + \lambda I\big)^{-1} X^{\top}\mathbf{y}
text: Adding lambda to the diagonal makes the matrix invertible even when features are correlated, and shrinks the weights.
```

```example
Predicting house price from floor area: with fitted weight 1,500 per square metre and bias 20,000, a 100 square metre house is predicted at 1,500 x 100 + 20,000 = 170,000.
```

```pitfall
Linear regression assumes a linear relationship and is sensitive to outliers, because squared error grows quickly with distance. Check residual plots, and consider robust losses such as Huber loss when outliers are present.
```

## Logistic regression
summary: A linear classifier that outputs a probability through the sigmoid function and is trained with cross-entropy.
prereq: Supervised learning > Linear regression
prereq: Mathematical foundations > Information theory

```definition
Logistic regression is a classification model despite its name. It passes a linear score through the sigmoid function to get the probability that the label is 1, and predicts class 1 when that probability is above a threshold, usually 0.5.
```

```formula
name: Sigmoid function
latex: \sigma(z) = \frac{1}{1 + e^{-z}}, \qquad p(y = 1 \mid \mathbf{x}) = \sigma(\mathbf{w}^{\top}\mathbf{x} + b)
text: The sigmoid squashes any real score into the range 0 to 1.
```

```formula
name: Binary cross-entropy (log loss)
latex: L(\mathbf{w}) = -\frac{1}{n}\sum_{i=1}^{n} \Big[ y_i \log \hat{p}_i + (1 - y_i)\log(1 - \hat{p}_i) \Big]
text: The negative log-likelihood of the labels; it heavily penalises confident wrong predictions.
```

```formula
name: Log-loss gradient
latex: \nabla_{\mathbf{w}} L = \frac{1}{n}\sum_{i=1}^{n} (\hat{p}_i - y_i)\,\mathbf{x}_i
text: The gradient has the same simple form as in linear regression: prediction error times input.
```

```formula
name: Softmax for multi-class classification
latex: p(y = k \mid \mathbf{x}) = \frac{\exp(\mathbf{w}_k^{\top}\mathbf{x})}{\sum_{j=1}^{K}\exp(\mathbf{w}_j^{\top}\mathbf{x})}
text: Multinomial logistic regression gives each class its own weight vector and normalises the exponentiated scores so they sum to one.
```

```intuition
The decision boundary w.x + b = 0 is a straight line (a hyperplane in higher dimensions). The weights are log-odds: increasing feature j by one unit multiplies the odds of class 1 by exp(w_j).
```

## k-nearest neighbours
summary: Predicting from the labels of the k most similar training examples.

```definition
k-nearest neighbours (kNN) stores the whole training set. To predict for a new point it finds the k closest training points under a distance measure and returns the majority label (classification) or the average target (regression).
```

```formula
name: Euclidean and Manhattan distance
latex: d_2(\mathbf{x}, \mathbf{z}) = \sqrt{\sum_{j}(x_j - z_j)^2} \qquad d_1(\mathbf{x}, \mathbf{z}) = \sum_{j}|x_j - z_j|
text: The two most common distance measures; features must be on comparable scales for either to be meaningful.
```

```compare
caption: Effect of the number of neighbours k
Choice of k, Bias, Variance, Boundary
Small k (for example 1), low, high, Jagged and sensitive to noise
Large k, high, low, Smooth but may blur classes together
```

```pitfall
kNN suffers from the curse of dimensionality: in many dimensions all points are nearly equally far apart, so neighbours stop being informative. Scale features and reduce dimensions first.
```

## Naive Bayes
summary: A probabilistic classifier that assumes features are independent given the class.
prereq: Mathematical foundations > Bayes' theorem

```definition
Naive Bayes applies Bayes' theorem and assumes every feature is conditionally independent of the others given the class. The assumption is rarely true but the classifier is fast, needs little data, and works well for text.
```

```formula
name: Naive Bayes decision rule
latex: \hat{y} = \arg\max_{c} \; p(c) \prod_{j=1}^{d} p(x_j \mid c)
text: Choose the class whose prior times the product of per-feature likelihoods is largest; in practice sums of logarithms are used to avoid underflow.
```

```formula
name: Laplace smoothing
latex: p(w \mid c) = \frac{\mathrm{count}(w, c) + 1}{\sum_{w'} \mathrm{count}(w', c) + |V|}
text: Adding one to every count stops an unseen word from forcing the whole product to zero; V is the vocabulary.
```

```application
Spam filtering, sentiment analysis and document categorisation, where the features are word counts.
```

## Decision trees
summary: Recursive splits on features chosen to make the resulting groups as pure as possible.
prereq: Mathematical foundations > Information theory

```definition
A decision tree asks a sequence of yes/no questions about the features. Each internal node tests one feature against a threshold, each branch is an answer, and each leaf gives a prediction. Trees are easy to read and need no feature scaling.
```

```formula
name: Gini impurity
latex: G(S) = 1 - \sum_{k=1}^{K} p_k^2
text: The chance of mislabelling a random element of S if it were labelled at random according to the class proportions p_k; zero means the node is pure.
```

```formula
name: Information gain
latex: \mathrm{IG}(S, A) = H(S) - \sum_{v \in \mathrm{values}(A)} \frac{|S_v|}{|S|} H(S_v)
text: The reduction in entropy achieved by splitting S on attribute A; ID3 and C4.5 split on the attribute with the highest gain.
```

```steps
title: Growing a classification tree (CART)
1. Start with all training examples at the root.
2. For every feature and candidate threshold, compute the impurity after splitting.
3. Choose the split that reduces impurity the most and create two child nodes.
4. Repeat on each child until a stopping rule holds: maximum depth, minimum samples per leaf, or no gain.
5. Optionally prune the tree back using a validation set or cost-complexity pruning.
```

```example
A node with 10 examples, 5 of each class, has Gini impurity 1 - (0.5^2 + 0.5^2) = 0.5. A split into a pure child of 4 and a child with 1 positive and 5 negative has weighted Gini 0.4 x 0 + 0.6 x (1 - (1/6)^2 - (5/6)^2), which is 0.6 x 0.278, about 0.167, so the split reduces impurity by about 0.333.
```

```pitfall
An unrestricted tree keeps splitting until it memorises the training set. Limit depth, require a minimum leaf size, or prune, and prefer ensembles of trees for accuracy.
```

## Support vector machines
summary: Maximum-margin classifiers and the kernel trick for non-linear boundaries.
prereq: Mathematical foundations > Linear algebra
prereq: Mathematical foundations > Optimisation

```definition
A support vector machine (SVM) chooses the separating hyperplane with the largest margin, the widest gap between the hyperplane and the closest training points of each class. Those closest points are the support vectors, and they alone determine the boundary.
```

```formula
name: Hard-margin SVM
latex: \min_{\mathbf{w}, b} \; \tfrac{1}{2}\lVert \mathbf{w} \rVert^2 \quad \text{s.t. } y_i(\mathbf{w}^{\top}\mathbf{x}_i + b) \ge 1 \;\; \forall i
text: Minimising the weight norm maximises the margin, which equals 2 divided by the norm of w.
```

```formula
name: Soft-margin SVM with hinge loss
latex: \min_{\mathbf{w}, b} \; \tfrac{1}{2}\lVert \mathbf{w} \rVert^2 + C \sum_{i=1}^{n} \max\big(0, 1 - y_i(\mathbf{w}^{\top}\mathbf{x}_i + b)\big)
text: Slack lets some points sit inside the margin or on the wrong side; C trades margin width against training errors.
```

```formula
name: Kernel trick
latex: f(\mathbf{x}) = \sum_{i} \alpha_i y_i K(\mathbf{x}_i, \mathbf{x}) + b, \qquad K_{\text{RBF}}(\mathbf{x}, \mathbf{z}) = \exp\!\big(-\gamma \lVert \mathbf{x} - \mathbf{z} \rVert^2\big)
text: In the dual form the data appear only through dot products, so a kernel K can replace them and give a linear boundary in a high-dimensional feature space without computing that space.
```

```compare
caption: Common SVM kernels
Kernel, Formula, Good for
Linear, x.z, Many features such as text
Polynomial, (x.z + c)^p, Feature interactions of fixed degree
RBF (Gaussian), exp(-gamma |x - z|^2), General non-linear boundaries
Sigmoid, tanh(a x.z + c), Neural-network-like boundaries
```

## Ensemble methods
summary: Combining many models to reduce variance (bagging) or bias (boosting).
prereq: Supervised learning > Decision trees

```definition
An ensemble combines the predictions of several base models. Bagging trains models independently on resampled data and averages them, which mainly reduces variance. Boosting trains models in sequence, each one focusing on the errors of the previous ones, which mainly reduces bias.
```

### Bagging and random forests
summary: Averaging trees trained on bootstrap samples with random feature subsets.

```steps
title: Random forest
1. Draw a bootstrap sample of the training set (n examples sampled with replacement).
2. Grow a deep decision tree on it, but at every split consider only a random subset of features, typically the square root of d for classification.
3. Repeat to grow many trees, often hundreds.
4. Predict by majority vote (classification) or by averaging (regression).
5. Estimate accuracy for free on the out-of-bag examples each tree did not see.
```

```formula
name: Variance of an average of correlated models
latex: \mathrm{Var}\Big(\frac{1}{B}\sum_{b=1}^{B} f_b\Big) = \rho \sigma^2 + \frac{1 - \rho}{B}\sigma^2
text: Averaging B models with variance sigma squared and pairwise correlation rho reduces variance; random feature subsets lower rho, which is why random forests beat plain bagging.
```

### Boosting
summary: AdaBoost and gradient boosting, which add weak learners one at a time.

```formula
name: AdaBoost learner weight
latex: \alpha_t = \tfrac{1}{2}\ln\frac{1 - \varepsilon_t}{\varepsilon_t}, \qquad w_i \leftarrow w_i \exp\big(-\alpha_t y_i h_t(\mathbf{x}_i)\big)
text: A weak learner with error epsilon below 0.5 gets a positive vote alpha; misclassified examples get heavier weights for the next round.
```

```formula
name: Gradient boosting step
latex: F_m(\mathbf{x}) = F_{m-1}(\mathbf{x}) + \nu \, h_m(\mathbf{x}), \qquad h_m \approx -\frac{\partial L(y, F)}{\partial F}\Big|_{F = F_{m-1}}
text: Each new tree h_m is fitted to the negative gradient of the loss (the residuals for squared error) and added with a small learning rate nu.
```

```compare
caption: Bagging versus boosting
Aspect, Bagging and random forests, Boosting
Training, parallel and independent, sequential
Main effect, reduces variance, reduces bias
Base learners, deep trees, shallow trees (stumps or depth 3 to 8)
Overfitting risk, low, higher without a learning rate and early stopping
Examples, Random forest and Extra trees, AdaBoost and XGBoost and LightGBM
```

```application
Gradient-boosted trees are usually the strongest method for tabular data such as credit scoring, fraud detection and click-through prediction.
```
