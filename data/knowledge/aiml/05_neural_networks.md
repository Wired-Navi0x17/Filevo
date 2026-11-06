---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Neural networks and deep learning
summary: Layered differentiable models trained by backpropagation, from the perceptron to transformers.
prereq: Mathematical foundations > Calculus and gradients
prereq: Mathematical foundations > Optimisation

```definition
A neural network is a composition of simple functions called layers. Each layer applies a linear transformation followed by a non-linear activation. Stacking many layers lets the network learn its own features from raw data, which is what "deep" learning refers to.
```

## The perceptron
summary: The single artificial neuron and its learning rule.

```definition
The perceptron computes a weighted sum of its inputs and outputs 1 if the sum is above zero and 0 otherwise. Rosenblatt's learning rule adjusts the weights only when the prediction is wrong.
```

```formula
name: Perceptron output and update
latex: \hat{y} = \mathbb{1}\big[\mathbf{w}^{\top}\mathbf{x} + b > 0\big], \qquad \mathbf{w} \leftarrow \mathbf{w} + \eta\,(y - \hat{y})\,\mathbf{x}
text: The weights move towards misclassified positive examples and away from misclassified negative ones.
```

```pitfall
A single perceptron can only learn linearly separable functions. It cannot learn XOR, which is why hidden layers are needed.
```

```history
Rosenblatt introduced the perceptron in 1958. Minsky and Papert's 1969 analysis of its limits contributed to the first AI winter, and interest returned with backpropagation for multi-layer networks in the 1980s.
```

## Multi-layer perceptrons
summary: Fully connected networks with hidden layers that can approximate any continuous function.
prereq: Neural networks and deep learning > The perceptron

```formula
name: Forward pass of a layer
latex: \mathbf{h}^{(l)} = \phi\big(W^{(l)}\mathbf{h}^{(l-1)} + \mathbf{b}^{(l)}\big), \qquad \mathbf{h}^{(0)} = \mathbf{x}
text: Each layer multiplies the previous layer's output by a weight matrix, adds a bias, and applies an activation function phi.
```

```intuition
The universal approximation theorem says a network with one hidden layer and enough units can approximate any continuous function on a bounded region. Deep networks reach the same accuracy with far fewer units, because each layer reuses the features built by the one before it.
```

## Activation functions
summary: The non-linearities that give networks their power.

```compare
caption: Common activation functions
Activation, Formula, Range, Notes
Sigmoid, 1 / (1 + e^-z), (0 1), Saturates and causes vanishing gradients; used for binary outputs
Tanh, (e^z - e^-z) / (e^z + e^-z), (-1 1), Zero-centred but also saturates
ReLU, max(0 z), [0 infinity), Default for hidden layers; units can die if they stay negative
Leaky ReLU, max(0.01z z), real line, Keeps a small gradient for negative inputs
GELU, z times Phi(z), about (-0.17 infinity), Smooth; standard in transformers
Softmax, e^z_k / sum_j e^z_j, (0 1) summing to 1, Output layer for multi-class classification
```

```pitfall
Without a non-linear activation a stack of linear layers collapses into a single linear layer, however deep it is.
```

## Backpropagation
summary: Computing all gradients of the loss efficiently with the chain rule.
prereq: Neural networks and deep learning > Multi-layer perceptrons

```definition
Backpropagation computes the gradient of the loss with respect to every weight in one backward sweep. It stores the intermediate values of the forward pass and then applies the chain rule from the output layer back to the input layer.
```

```formula
name: Error signal of a layer
latex: \boldsymbol{\delta}^{(L)} = \nabla_{\hat{\mathbf{y}}} \mathcal{L} \odot \phi'(\mathbf{z}^{(L)}), \qquad \boldsymbol{\delta}^{(l)} = \big(W^{(l+1)\top}\boldsymbol{\delta}^{(l+1)}\big) \odot \phi'(\mathbf{z}^{(l)})
text: The error at each layer is the next layer's error sent back through its weights and scaled by the activation's slope.
```

```formula
name: Weight gradient
latex: \frac{\partial \mathcal{L}}{\partial W^{(l)}} = \boldsymbol{\delta}^{(l)} \, \mathbf{h}^{(l-1)\top}, \qquad \frac{\partial \mathcal{L}}{\partial \mathbf{b}^{(l)}} = \boldsymbol{\delta}^{(l)}
text: Each weight's gradient is the error at its output times the activation at its input.
```

```steps
title: One training step of a neural network
1. Forward pass: compute every layer's pre-activation z and activation h for a mini-batch.
2. Compute the loss between the network output and the labels.
3. Backward pass: compute the error signal at the output and propagate it backwards layer by layer.
4. Accumulate the gradients for every weight and bias.
5. Update the parameters with an optimiser such as SGD with momentum or Adam.
```

```pitfall
Vanishing gradients: with saturating activations the product of many small derivatives shrinks towards zero, so early layers stop learning. Exploding gradients are the opposite. ReLU-family activations, careful initialisation, normalisation, residual connections and gradient clipping all help.
```

## Training deep networks
summary: Initialisation, normalisation, dropout and other techniques that make deep networks trainable.
prereq: Neural networks and deep learning > Backpropagation

```formula
name: He and Xavier initialisation
latex: W_{ij} \sim \mathcal{N}\!\left(0, \frac{2}{n_{\text{in}}}\right) \text{ (He, ReLU)}, \qquad W_{ij} \sim \mathcal{N}\!\left(0, \frac{2}{n_{\text{in}} + n_{\text{out}}}\right) \text{ (Xavier, tanh)}
text: Scaling the initial weights by layer size keeps activations and gradients at a stable size through many layers.
```

```formula
name: Batch normalisation
latex: \hat{x} = \frac{x - \mu_{\mathcal{B}}}{\sqrt{\sigma_{\mathcal{B}}^2 + \epsilon}}, \qquad y = \gamma \hat{x} + \beta
text: Each feature is normalised with the mini-batch mean and variance, then rescaled by learned gamma and beta; layer normalisation does the same across the features of one example instead.
```

```definition
Dropout randomly sets each hidden unit to zero with probability p during training, which stops units from relying on each other and acts like averaging many thinner networks. At test time all units are kept and outputs are scaled to match.
```

```formula
name: Residual connection
latex: \mathbf{h}^{(l+1)} = \mathbf{h}^{(l)} + F\big(\mathbf{h}^{(l)}\big)
text: A layer learns a correction F added to its input, so gradients can flow straight through the identity path; this makes networks with hundreds of layers trainable.
```

```compare
caption: Regularisation and stabilisation techniques for deep networks
Technique, Problem addressed, Where applied
Weight decay, large weights and overfitting, every weight
Dropout, co-adaptation and overfitting, hidden activations
Batch normalisation, unstable activations, after linear or convolution layers
Layer normalisation, unstable activations with small batches, transformers and RNNs
Early stopping, overfitting late in training, the training loop
Data augmentation, too little data, the input pipeline
Gradient clipping, exploding gradients, the optimiser step
```

## Convolutional neural networks
summary: Networks with shared local filters for images and other grid-structured data.
prereq: Neural networks and deep learning > Backpropagation

```definition
A convolutional neural network (CNN) slides small learned filters over the input. Each filter detects one local pattern, such as an edge, everywhere in the image. Weight sharing and local connections give far fewer parameters than a fully connected layer and make the network robust to where a pattern appears.
```

```formula
name: Discrete 2D convolution (cross-correlation)
latex: S(i, j) = \sum_{m}\sum_{n} I(i + m, j + n)\, K(m, n)
text: Each output value is the sum of the input patch multiplied element-wise by the kernel K.
```

```formula
name: Output size of a convolution
latex: O = \left\lfloor \frac{W - K + 2P}{S} \right\rfloor + 1
text: For input width W, kernel size K, padding P and stride S.
```

```example
A 32 x 32 RGB image passed through a convolution with 16 filters of size 3 x 3, padding 1 and stride 1 gives a 32 x 32 x 16 output. The layer has 16 x (3 x 3 x 3 + 1) = 448 parameters; a fully connected layer producing the same output would need over 50 million.
```

```compare
caption: Landmark CNN architectures
Network, Year, Key idea
LeNet-5, 1998, Convolution and pooling for digit recognition
AlexNet, 2012, Deep CNN with ReLU and dropout trained on GPUs; won ImageNet
VGG, 2014, Very deep stacks of 3 x 3 convolutions
GoogLeNet, 2014, Inception modules with parallel filter sizes
ResNet, 2015, Residual connections enabling 100+ layers
```

## Recurrent neural networks
summary: Networks with a hidden state carried across time steps, including LSTM and GRU.
prereq: Neural networks and deep learning > Backpropagation

```definition
A recurrent neural network (RNN) processes a sequence one element at a time and keeps a hidden state that summarises what it has seen so far. The same weights are used at every time step. Training unrolls the network through time and applies backpropagation through time.
```

```formula
name: Simple RNN update
latex: \mathbf{h}_t = \tanh\big(W_{hh}\mathbf{h}_{t-1} + W_{xh}\mathbf{x}_t + \mathbf{b}\big)
text: The new hidden state mixes the previous state with the current input.
```

```formula
name: LSTM cell
latex: \mathbf{c}_t = \mathbf{f}_t \odot \mathbf{c}_{t-1} + \mathbf{i}_t \odot \tilde{\mathbf{c}}_t, \qquad \mathbf{h}_t = \mathbf{o}_t \odot \tanh(\mathbf{c}_t)
text: Forget, input and output gates (each a sigmoid of the input and previous state) decide what to erase, what to write and what to reveal; the additive cell update lets gradients survive over long sequences.
```

```pitfall
Plain RNNs forget information from more than a few dozen steps back because gradients vanish over time. LSTMs and GRUs reduce the problem, and attention removes it by connecting every position to every other.
```

## Attention and transformers
summary: Self-attention layers that relate every position of a sequence to every other, the basis of modern language models.
prereq: Neural networks and deep learning > Training deep networks

```definition
Attention lets a model build each output as a weighted average of all input positions, where the weights depend on how relevant each position is. A transformer stacks self-attention and feed-forward layers with residual connections and layer normalisation, and processes all positions in parallel.
```

```formula
name: Scaled dot-product attention
latex: \mathrm{Attention}(Q, K, V) = \mathrm{softmax}\!\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V
text: Queries are compared with keys by dot product, scaled by the square root of the key size so the softmax does not saturate, and the resulting weights average the values.
```

```formula
name: Multi-head attention
latex: \mathrm{MultiHead}(X) = \mathrm{Concat}(\mathrm{head}_1, \ldots, \mathrm{head}_h)W^{O}, \quad \mathrm{head}_i = \mathrm{Attention}(XW_i^{Q}, XW_i^{K}, XW_i^{V})
text: Several attention heads with their own projections look for different kinds of relationships at once.
```

```formula
name: Sinusoidal positional encoding
latex: PE_{(pos, 2i)} = \sin\!\left(\frac{pos}{10000^{2i/d}}\right), \qquad PE_{(pos, 2i+1)} = \cos\!\left(\frac{pos}{10000^{2i/d}}\right)
text: Attention itself ignores order, so a position signal is added to each token embedding.
```

```compare
caption: RNNs versus transformers
Aspect, RNN or LSTM, Transformer
Processing, one step at a time, all positions in parallel
Long-range links, through many steps, one attention step
Cost per layer, O(n d^2), O(n^2 d)
Training on GPUs, slow, fast
Typical use today, small streaming tasks, language and vision foundation models
```

```history
The transformer was introduced in "Attention Is All You Need" (Vaswani et al., 2017). Encoder models such as BERT, decoder models such as GPT, and vision transformers all build on it.
```

## Embeddings
summary: Dense vectors that place similar items close together.

```definition
An embedding maps a discrete item, such as a word, a product or a user, to a dense vector of a few hundred numbers. The vectors are learned so that items used in similar contexts get similar vectors, and similarity is then measured by cosine similarity.
```

```application
Word2vec and GloVe word vectors, sentence embeddings such as MiniLM for semantic search, and user and item embeddings in recommender systems.
```
