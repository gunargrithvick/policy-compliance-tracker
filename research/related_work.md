# Related Work

This section contains a core set of 20 recent, citable scholarly papers directly related to the Policy Compliance Tracker. The list prioritizes official conference proceedings, journals, and publisher records. The project uses these papers as design guidance; it does not claim to reproduce their models or benchmark results.

## Agentic and Evidence-Grounded Workflows

1. Yao et al. (2023), [ReAct: Synergizing Reasoning and Acting in Language Models](https://openreview.net/forum?id=WE_vluYUL-X). ICLR 2023. Supports staged reasoning and tool interaction.
2. Gao et al. (2023), [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/). EMNLP 2023. Supports evidence-linked compliance conclusions.
3. Asai et al. (2024), [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://openreview.net/forum?id=hSyW5go0v8). ICLR 2024. Supports self-review and groundedness checks.
4. Liu et al. (2024), [Lost in the Middle: How Language Models Use Long Contexts](https://aclanthology.org/2024.tacl-1.9/). TACL 2024. Motivates careful chunk selection and ordering.

## Retrieval and Evaluation

5. Reuter et al. (2025), [Towards Reliable Retrieval in RAG Systems for Large Legal Datasets](https://aclanthology.org/2025.nllp-1.3/). NLLP 2025. Supports retrieval reliability checks for legal information.
6. Jeong et al. (2024), [Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity](https://aclanthology.org/2024.naacl-long.389/). NAACL 2024. Supports query-complexity-aware retrieval.
7. Saad-Falcon et al. (2024), [ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems](https://aclanthology.org/2024.naacl-long.20/). NAACL 2024. Supports separate retrieval and generation measurements.
8. Es et al. (2024), [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://aclanthology.org/2024.eacl-demo.16/). EACL 2024. Supports context relevance, faithfulness, and answer-quality evaluation.
9. Niu et al. (2024), [RAGTruth: A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models](https://aclanthology.org/2024.acl-long.585/). ACL 2024. Motivates hallucination and unsupported-claim checks.
10. Rau et al. (2024), [BERGEN: A Benchmarking Library for Retrieval-Augmented Generation](https://aclanthology.org/2024.findings-emnlp.449/). Findings of EMNLP 2024. Supports reproducible comparison of retrievers, rerankers, and generators.
11. Krishna et al. (2025), [Fact, Fetch, and Reason: A Unified Evaluation of Retrieval-Augmented Generation](https://aclanthology.org/2025.naacl-long.243/). NAACL 2025. Supports evaluating factuality, retrieval, and reasoning separately.

## Legal, Regulatory, and Policy Analysis

12. Guha et al. (2023), [LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models](https://papers.neurips.cc/paper_files/paper/2023/hash/89e44582fd28ddfea1ea4dcb0ebbf4b0-Abstract-Datasets_and_Benchmarks.html). NeurIPS 2023. Motivates structured legal reasoning evaluation.
13. Fei et al. (2024), [LawBench: Benchmarking Legal Knowledge of Large Language Models](https://aclanthology.org/2024.emnlp-main.452/). EMNLP 2024. Motivates evaluating legal knowledge, understanding, and application separately.
14. Hou et al. (2025), [CLERC: A Dataset for U.S. Legal Case Retrieval and Retrieval-Augmented Analysis Generation](https://aclanthology.org/2025.findings-naacl.441/). Findings of NAACL 2025. Supports evaluating legal retrieval and grounded analysis.
15. [LeReRAG: Measuring Legal Relevance in Retrieval Augmented Generation Applications](https://journals.sagepub.com/doi/10.3233/FAIA241284) (2024). JURIX 2024. Motivates legal-relevance scoring beyond generic retrieval metrics.
16. [Approaching the AI Act with AI: LLMs and Knowledge Graphs to Extract and Analyse Obligations](https://doi.org/10.1016/j.clsr.2025.106230) (2025). Computer Law & Security Review. Supports extracting and structuring regulatory obligations.
17. [LLM-assisted Extraction of Regulatory Requirements: A Case Study on the GDPR](https://orbilu.uni.lu/handle/10993/65265) (2025). IEEE Requirements Engineering 2025. Supports converting regulatory text into structured requirements.
18. [Policy-Aware Generative AI for Safe, Auditable Data Access Governance](https://doi.org/10.1109/KSE68178.2025.11309632) (2025). IEEE KSE 2025. Supports policy gates, auditability, and human governance.

## Graph-Based Policy and Control Relationships

19. [LegalGraphRAG: Multi-Agent Graph Retrieval-Augmented Generation](https://aclanthology.org/2026.acl-long.1738/) (2026). ACL 2026. Supports graph-based legal evidence retrieval and multi-agent analysis.
20. He et al. (2024), [G-Retriever: Retrieval-Augmented Generation for Textual Graph Understanding and Question Answering](https://proceedings.neurips.cc/paper_files/paper/2024/hash/efaf1c9726648c8ba363a5c927440529-Abstract-Conference.html). NeurIPS 2024. Supports retrieving connected policy and control evidence.

## Additional Preprints

These are legitimate and useful, but should be labelled as preprints rather than peer-reviewed publications: [Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884), [RAGChecker](https://arxiv.org/abs/2408.08067), [NLP-based Regulatory Compliance](https://arxiv.org/abs/2412.20602), [LegalBench-RAG](https://arxiv.org/abs/2408.10343), and [Legal RAG Bench](https://arxiv.org/abs/2603.01710).

## Research Gap Addressed by This Project

The cited work addresses individual parts of the problem: agentic workflows, evidence-grounded retrieval, legal reasoning, regulatory obligation extraction, evaluation, and graph-based retrieval. Policy Compliance Tracker combines these ideas into a local compliance-monitoring workflow that maps regulatory updates to internal policies and controls, produces a duplicate-aware impact tracker, assigns review metadata, and preserves alerts and audit history. The project evaluates retrieval with labelled source expectations, baseline comparison, F1 and MRR metrics, latency, and per-case failure categories.
