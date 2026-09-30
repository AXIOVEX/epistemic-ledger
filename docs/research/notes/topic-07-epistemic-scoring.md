# Topic 7 — Non-binary epistemic scoring (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism
- **Credences as probabilities (subjective Bayesianism):** rational degree of belief in a proposition = a number in [0,1] obeying the probability axioms (de Finetti 1937; Savage 1954; representation theorems: Koopman/Savage/Hawthorne — a qualitative "at least as plausible" relation satisfying axioms is uniquely representable by a probability function).
- **Updating:** Bayes' rule P(H|E) = P(E|H)·P(H)/P(E). Sequential structure: **today's posterior is tomorrow's prior**; with conditionally independent evidence, update order doesn't matter; accumulating evidence drives belief toward 0 or 1 (consistency/convergence results). Structural norms (probabilities), evidential norms (calibration to known chances, deference to experts), equivocation norms (indifference without evidence) — per the BJPS "Bayesian Account of Establishing."
- **Uncertain evidence — Jeffrey conditionalization / probability kinematics** (Jeffrey, *The Logic of Decision*): when evidence shifts P(B) without making B certain, P_new(A) = P_old(A|B)·P_new(B) + P_old(A|¬B)·P_new(¬B). "It's probabilities all the way down" — rejects the demand for certain foundations (vs. Cromwell's rule: nothing known for certain). Alternatives: Jaynes' maximum-entropy updating; Skyrms' reflection principle.
- **Alternatives to single-number probability:**
  - **Dempster–Shafer theory** (Dempster 1967; Shafer, *A Mathematical Theory of Evidence*, 1976): belief functions returning [belief, plausibility] intervals; designed to separate *uncertainty from ignorance* — mass can sit on "don't know" (Θ) rather than being forced onto specific hypotheses; Bel(A) = 1 − Bel(¬A) does *not* hold in general (unlike probability); Dempster's rule combines independent evidence. Generalizes probability (tighten the disjunction axiom and you recover probability functions).
  - **Imprecise probabilities** (Walley 1991): sets of distributions instead of one.
  - **Possibility theory** (Dubois & Prade); qualitative probability relations.
- **LLM-era scoring:** verbalized confidence, calibration of neural networks (Guo et al. 2017 "On Calibration of Modern Neural Networks" — modern nets are poorly calibrated; temperature scaling), uncertainty estimation for generated claims.

## How scores are revised over time as evidence accumulates
- Conjugate updating (beta-binomial: successes/failures shift the posterior mean and shrink variance); Kalman-style for continuous state.
- Sequential Bayesian updating = the natural "fluid certainty score" protocol: each observation is a message that sharpens the distribution; with enough evidence the score converges (very high or very low).
- Jeffrey kinematics handles the realistic case where the new "fact" itself arrives with less-than-certainty (a sensor reading, an LLM-extracted claim) — exactly the ledger's situation.

## Canonical references
1. de Finetti (1937), Savage, *The Foundations of Statistics* (1954) — subjective probability.
2. Jeffrey, *The Logic of Decision* (1965; 2nd ed. 1983) — probability kinematics / radical probabilism.
3. Dempster (1967); Shafer, *A Mathematical Theory of Evidence*, Princeton UP, 1976.
4. Walley, *Statistical Reasoning with Imprecise Probabilities*, 1991.
5. Bernardo & Smith; Gelman et al., *Bayesian Data Analysis* — practice.
6. Guo et al., "On Calibration of Modern Neural Networks," ICML 2017 — neural calibration.

## Practical limitations
- **Need priors and likelihoods:** prior sensitivity; elicitation is hard; model misspecification produces *confidently wrong* posteriors.
- **Cromwell's rule:** never assign 0 or 1 (except logical truths) or no evidence can ever move you.
- Dempster's rule gives counterintuitive results under high conflict (Yager's conflict-to-Θ rule and others proposed; subjects behave between the two — Golden 1993/4); mass functions blow up exponentially (2^n values for n alternatives — exceeds working memory fast).
- Bayesian convergence assumes the true hypothesis is in the support and evidence is genuinely informative; adversarial/misspecified likelihoods break it.
- LLM verbalized confidences are poorly calibrated out of the box; calibration must be measured on a frozen eval set and re-measured as distributions shift.

## Sources
- https://github.com/fleetingthoughts/obsidian/blob/HEAD/Theory%20and%20Reality%20-%2014%20Bayesianism%20and%20Modern%20Theories%20of%20Evidence.md (subjectivist probabilities; "today's priors become tomorrow's posteriors")
- https://github.com/cyberia-to/cyber/blob/HEAD/root/Bayes%20theorem.md (sequential update loop; order-independence under conditional independence)
- https://www.journals.uchicago.edu/doi/full/10.1086/714798 (BJPS: structural/evidential/equivocation norms; calibration norm; deference norm)
- https://en.wikipedia.org/wiki/Radical_probabilism (Jeffrey conditioning / probability kinematics; Cromwell's rule; "probabilities all the way down"; Jaynes max-entropy alternative)
- https://plato.stanford.edu/archIves/win2023/entries/logic-inductive/sup-uncertain-inf.html (SEP: Dempster-Shafer belief functions as generalization of probability; belief/plausibility)
- https://arxiv.org/pdf/1006.3868 (Gelman & Shalizi, "Philosophy and the practice of Bayesian statistics": evidence accumulation; model checking as error probes)
