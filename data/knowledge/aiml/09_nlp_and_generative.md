---
domain: aiml
root: Artificial intelligence and machine learning
source: seed://aiml
license: CC BY 4.0 (Filevo curated seed)
---

# Natural language processing
summary: Turning text into representations a model can learn from, and the models that understand and generate language.
prereq: Neural networks and deep learning > Embeddings

```definition
Natural language processing (NLP) builds systems that read, classify, translate, summarise and generate human language. The core challenge is representing words and sentences as numbers that keep their meaning.
```

## Text representation
summary: Tokenisation, bag of words, TF-IDF and subword vocabularies.

```definition
Tokenisation splits text into units called tokens. Classic systems used whole words; modern models use subword units from byte-pair encoding (BPE) or WordPiece, so rare words are built from common pieces and no word is ever out of vocabulary.
```

```formula
name: TF-IDF weight
latex: \mathrm{tfidf}(t, d) = \mathrm{tf}(t, d) \cdot \log \frac{N}{\mathrm{df}(t)}
text: A term counts more the more often it appears in the document (term frequency) and the fewer documents contain it (inverse document frequency); N is the number of documents.
```

```formula
name: BM25 ranking function
latex: \mathrm{score}(q, d) = \sum_{t \in q} \mathrm{IDF}(t) \cdot \frac{\mathrm{tf}(t, d)\,(k_1 + 1)}{\mathrm{tf}(t, d) + k_1\big(1 - b + b\,\frac{|d|}{\mathrm{avgdl}}\big)}
text: A refinement of TF-IDF used by search engines: term frequency saturates (k_1 is around 1.2 to 2) and long documents are normalised (b is around 0.75).
```

## Language models
summary: Assigning probabilities to sequences of tokens, from n-grams to large transformer models.
prereq: Neural networks and deep learning > Attention and transformers

```formula
name: Autoregressive language model
latex: p(w_1, \ldots, w_T) = \prod_{t=1}^{T} p(w_t \mid w_1, \ldots, w_{t-1})
text: A language model predicts each token from the tokens before it; generation samples one token at a time from this distribution.
```

```formula
name: Perplexity
latex: \mathrm{PPL} = \exp\!\Big( -\frac{1}{T}\sum_{t=1}^{T} \log p(w_t \mid w_{<t}) \Big)
text: The exponentiated average negative log-likelihood; it is the effective number of choices the model is uncertain between, and lower is better.
```

```compare
caption: Families of transformer language models
Family, Attention, Pre-training task, Examples
Encoder-only, bidirectional, masked-token prediction, BERT and RoBERTa
Decoder-only, causal (left to right), next-token prediction, GPT family and Llama and SmolLM
Encoder-decoder, both, span corruption or translation, T5 and BART
```

```pitfall
Language models generate fluent text that can be false (hallucination), because they model what text is likely, not what is true. Grounding generation in retrieved sources and checking each claim against them reduces the problem.
```

## Retrieval-augmented generation
summary: Combining a search step over a document store with a generator.
prereq: Natural language processing > Text representation

```steps
title: Retrieval-augmented generation (RAG)
1. Split source documents into chunks and index them with keyword (BM25) and dense (embedding) search.
2. For a question, retrieve the most relevant chunks, often fusing both rankings with reciprocal rank fusion.
3. Put the retrieved chunks into the model's prompt as context.
4. Generate an answer that cites the chunks it used.
5. Check that each generated sentence is supported by a retrieved chunk.
```

```formula
name: Reciprocal rank fusion
latex: \mathrm{RRF}(d) = \sum_{r \in \text{rankers}} \frac{1}{k + \mathrm{rank}_r(d)}
text: Combine several ranked lists by position only, so rankers with different score scales can be merged; k is commonly 60.
```

# Generative models
summary: Models that learn a data distribution well enough to sample new examples: VAEs, GANs and diffusion models.
prereq: Neural networks and deep learning
prereq: Mathematical foundations > Information theory

```definition
A generative model learns p(x), the distribution of the data itself, so it can create new images, sounds or text that look like the training data. Discriminative models only learn p(y | x).
```

## Variational autoencoders
summary: Encoder-decoder models trained to maximise a lower bound on the data likelihood.

```formula
name: Evidence lower bound (ELBO)
latex: \log p(\mathbf{x}) \ge \mathbb{E}_{q_{\phi}(\mathbf{z} \mid \mathbf{x})}\big[\log p_{\theta}(\mathbf{x} \mid \mathbf{z})\big] - D_{\mathrm{KL}}\big(q_{\phi}(\mathbf{z} \mid \mathbf{x}) \,\|\, p(\mathbf{z})\big)
text: The first term rewards accurate reconstruction; the KL term keeps the encoder's latent distribution close to a simple prior so new samples can be drawn from it.
```

```definition
The reparameterisation trick writes the latent sample as z = mu + sigma times epsilon with epsilon drawn from a standard normal, so gradients can flow through the sampling step into the encoder.
```

## Generative adversarial networks
summary: A generator and a discriminator trained against each other.

```formula
name: GAN minimax objective
latex: \min_{G}\max_{D} \; \mathbb{E}_{\mathbf{x} \sim p_{\text{data}}}\big[\log D(\mathbf{x})\big] + \mathbb{E}_{\mathbf{z} \sim p(\mathbf{z})}\big[\log\big(1 - D(G(\mathbf{z}))\big)\big]
text: The discriminator D learns to tell real from generated samples while the generator G learns to fool it.
```

```pitfall
GAN training is unstable: mode collapse (the generator produces only a few kinds of sample) and oscillation are common. Wasserstein losses, spectral normalisation and careful learning rates help.
```

## Diffusion models
summary: Learning to reverse a gradual noising process.

```formula
name: Forward noising process
latex: q(\mathbf{x}_t \mid \mathbf{x}_0) = \mathcal{N}\big(\mathbf{x}_t;\, \sqrt{\bar{\alpha}_t}\,\mathbf{x}_0,\, (1 - \bar{\alpha}_t) I\big)
text: Gaussian noise is added over T steps until the data become pure noise.
```

```formula
name: Denoising training loss
latex: L = \mathbb{E}_{t, \mathbf{x}_0, \boldsymbol{\epsilon}}\Big[ \big\lVert \boldsymbol{\epsilon} - \boldsymbol{\epsilon}_{\theta}\big(\sqrt{\bar{\alpha}_t}\,\mathbf{x}_0 + \sqrt{1 - \bar{\alpha}_t}\,\boldsymbol{\epsilon},\, t\big) \big\rVert^2 \Big]
text: A network learns to predict the noise that was added; generation starts from noise and removes it step by step.
```

```compare
caption: Generative model families compared
Family, Sample quality, Training stability, Sampling speed, Likelihood
VAE, blurrier, stable, fast, lower bound available
GAN, sharp, unstable, fast, not available
Diffusion, state of the art, stable, slow (many steps), approximate
Autoregressive, high, stable, slow (one token at a time), exact
```
