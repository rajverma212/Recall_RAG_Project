# Evaluation Report: smoke

**Run ID**: `e11d5ca4-95e9-4d0d-86c4-6d1356332732`
**Dataset**: `/Users/rajverma/RAG_Resume_Project/evaluation/datasets/eval_set.json`
**Created**: 2026-06-16T00:16:48.235109Z
**Examples**: 70

## Aggregate Metrics

| Metric | Score |
| ------ | ----- |
| Retrieval Recall | 0.907 |
| Answer Correctness | 0.233 |
| Faithfulness | 0.437 |
| Citation Accuracy | 0.365 |
| Confidence Calibration | 0.497 |
| Pass Rate | 0.014 |

## Per-Category Breakdown

| Category | Retrieval Recall | Answer Correctness | Faithfulness | Citation Accuracy | Confidence Calibration | Pass Rate | N |
| -------- | ---------------- | ------------------ | ------------ | ----------------- | ---------------------- | --------- | ---- |
| ambiguous | 0.731 | 0.114 | 0.676 | 0.659 | 0.497 | 0.000 | 13 |
| direct | 0.964 | 0.341 | 0.405 | 0.309 | 0.497 | 0.000 | 28 |
| multi_hop | 0.882 | 0.312 | 0.290 | 0.229 | 0.497 | 0.059 | 17 |
| no_answer | 1.000 | 0.000 | 0.462 | 0.369 | 0.497 | 0.000 | 12 |

## Configuration Snapshot

```json
{
  "chunking_strategy": "recursive",
  "dense_weight": 1.0,
  "sparse_weight": 1.0,
  "dataset": "/Users/rajverma/RAG_Resume_Project/evaluation/datasets/eval_set.json",
  "prompt_version": "v1"
}
```

## Per-Example Results

| ID | Category | Pass | R-Recall | A-Correct | Faith | Cit-Acc | Conf | Question |
| ---- | -------- | ---- | -------- | --------- | ----- | ------- | ---- | -------- |
| direct_001 | direct | ✗ | 1.000 | 1.000 | 0.250 | 0.167 | 0.451 | How many days of paid sick leave do Acme Corp employees rece… |
| direct_002 | direct | ✗ | 1.000 | 0.709 | 0.333 | 0.167 | 0.467 | What is the 401(k) employer match at Acme Corp? |
| direct_003 | direct | ✗ | 1.000 | 0.446 | 0.200 | 0.200 | 0.432 | What is the rate limit for the Acme DataStream authenticatio… |
| direct_004 | direct | ✗ | 1.000 | 0.031 | 0.667 | 0.667 | 0.669 | How long do Acme DataStream access tokens last before expiri… |
| direct_005 | direct | ✗ | 1.000 | 0.062 | 1.000 | 1.000 | 0.781 | What are the SEV-1 incident response and resolution targets … |
| direct_006 | direct | ✗ | 1.000 | 0.120 | 0.400 | 0.200 | 0.491 | What MFA methods are approved for accessing company systems … |
| direct_007 | direct | ✗ | 1.000 | 0.133 | 0.333 | 0.167 | 0.461 | What is the maximum batch size when publishing records to Ac… |
| direct_008 | direct | ✗ | 1.000 | 0.074 | 0.400 | 0.200 | 0.498 | What is the parental leave policy for primary caregivers at … |
| direct_009 | direct | ✗ | 1.000 | 0.154 | 0.200 | 0.200 | 0.437 | What is the minimum coverage threshold for new Python code a… |
| direct_010 | direct | ✗ | 1.000 | 0.240 | 0.375 | 0.250 | 0.482 | What Kafka version does the Acme DataStream platform run? |
| direct_011 | direct | ✗ | 1.000 | 1.000 | 0.167 | 0.167 | 0.409 | What home office stipend do remote employees receive at Acme… |
| direct_012 | direct | ✗ | 1.000 | 0.141 | 0.375 | 0.250 | 0.507 | What is the RTO and RPO for the Acme DataStream disaster rec… |
| direct_013 | direct | ✗ | 1.000 | 0.129 | 0.667 | 0.667 | 0.575 | How are Acme Corp RSUs vested for full-time employees? |
| direct_014 | direct | ✗ | 1.000 | 0.000 | 0.400 | 0.200 | 0.493 | What is the vulnerability remediation SLA for critical sever… |
| direct_015 | direct | ✗ | 1.000 | 0.061 | 0.400 | 0.200 | 0.492 | What are the deployment window hours at Acme Corp? |
| direct_016 | direct | ✗ | 1.000 | 0.222 | 0.250 | 0.167 | 0.442 | What is the maximum retention_days setting for a stream on A… |
| direct_017 | direct | ✗ | 1.000 | 0.133 | 0.375 | 0.250 | 0.493 | What is the external learning budget for Acme Corp employees… |
| direct_018 | direct | ✗ | 1.000 | 0.033 | 0.500 | 0.500 | 0.515 | What PostgreSQL version does Acme DataStream's metadata stor… |
| direct_019 | direct | ✗ | 0.000 | 0.818 | 0.333 | 0.167 | 0.461 | What is the maximum number of records in a list endpoint res… |
| direct_020 | direct | ✗ | 1.000 | 0.515 | 0.333 | 0.167 | 0.459 | What happens to a Acme DataStream webhook if it fails 5 cons… |
| multi_hop_001 | multi_hop | ✗ | 0.000 | 0.082 | 0.250 | 0.167 | 0.437 | An engineer at Acme Corp wants to deploy a production fix on… |
| multi_hop_002 | multi_hop | ✗ | 1.000 | 0.393 | 0.333 | 0.167 | 0.468 | A new Acme Corp employee at L2 wants to know their annual PT… |
| multi_hop_003 | multi_hop | ✗ | 1.000 | 0.853 | 0.300 | 0.200 | 0.463 | If an Acme Corp remote employee's internet costs $85/month, … |
| multi_hop_004 | multi_hop | ✗ | 1.000 | 0.133 | 0.333 | 0.333 | 0.483 | What programming language is recommended for all new Acme Co… |
| multi_hop_005 | multi_hop | ✗ | 0.000 | 0.076 | 0.200 | 0.200 | 0.427 | A developer wants to publish records to Acme DataStream and … |
| multi_hop_006 | multi_hop | ✗ | 1.000 | 0.094 | 0.167 | 0.167 | 0.407 | If Qdrant on qdrant-01 node has a full disk, what are the sp… |
| multi_hop_007 | multi_hop | ✗ | 1.000 | 0.108 | 0.200 | 0.200 | 0.436 | Under Acme Corp's security policy, what tier is source code … |
| multi_hop_008 | multi_hop | ✗ | 1.000 | 0.603 | 0.250 | 0.167 | 0.438 | What happens if an Acme Corp employee gets two consecutive p… |
| multi_hop_009 | multi_hop | ✗ | 1.000 | 0.110 | 0.375 | 0.250 | 0.512 | What is the expected end-to-end latency target for record de… |
| multi_hop_010 | multi_hop | ✗ | 1.000 | 0.145 | 0.200 | 0.000 | 0.441 | When does the EU Data Residency feature become available for… |
| multi_hop_011 | multi_hop | ✗ | 1.000 | 0.071 | 0.250 | 0.167 | 0.437 | What is Acme Corp's policy for an employee who leaves the co… |
| multi_hop_012 | multi_hop | ✗ | 1.000 | 0.886 | 0.250 | 0.250 | 0.467 | What Python SDK is available for Acme DataStream and how do … |
| multi_hop_013 | multi_hop | ✗ | 1.000 | 0.017 | 0.300 | 0.200 | 0.463 | What AWS instance type is used for the Kafka brokers in the … |
| multi_hop_014 | multi_hop | ✓ | 1.000 | 0.952 | 0.667 | 0.667 | 0.590 | Under what conditions must Acme Corp notify individuals affe… |
| ambiguous_001 | ambiguous | ✗ | 1.000 | 0.368 | 0.200 | 0.200 | 0.409 | How does Acme handle on-call? |
| ambiguous_002 | ambiguous | ✗ | 1.000 | 0.217 | 1.000 | 1.000 | 0.771 | What's the Acme DataStream free tier? |
| ambiguous_003 | ambiguous | ✗ | 1.000 | 0.060 | 1.000 | 1.000 | 0.711 | What is Acme Corp's security incident process? |
| ambiguous_004 | ambiguous | ✗ | 1.000 | 0.038 | 1.000 | 1.000 | 0.772 | How does Acme Corp handle performance? |
| ambiguous_005 | ambiguous | ✗ | 0.000 | 0.116 | 0.375 | 0.250 | 0.504 | What are the limits for streams in Acme DataStream? |
| ambiguous_006 | ambiguous | ✗ | 0.000 | 0.020 | 1.000 | 1.000 | 0.770 | How does Acme Corp handle code reviews? |
| ambiguous_007 | ambiguous | ✗ | 0.500 | 0.047 | 0.667 | 0.667 | 0.599 | What backup options does Acme have? |
| ambiguous_008 | ambiguous | ✗ | 1.000 | 0.114 | 0.300 | 0.200 | 0.459 | What are the rules around AI coding tools at Acme Corp? |
| ambiguous_009 | ambiguous | ✗ | 1.000 | 0.244 | 0.500 | 0.500 | 0.517 | How does Acme DataStream handle transformations? |
| ambiguous_010 | ambiguous | ✗ | 0.500 | 0.098 | 0.500 | 0.500 | 0.556 | What is Acme Corp's approach to software dependencies and th… |
| ambiguous_011 | ambiguous | ✗ | 1.000 | 0.085 | 0.250 | 0.250 | 0.466 | What's the process for a new Acme DataStream connector? |
| ambiguous_012 | ambiguous | ✗ | 0.500 | 0.023 | 1.000 | 1.000 | 0.770 | How does Acme Corp protect its production network? |
| no_answer_001 | no_answer | ✗ | 1.000 | 0.000 | 0.300 | 0.200 | 0.470 | What is the salary range for a Senior Engineer (L5) at Acme … |
| no_answer_002 | no_answer | ✗ | 1.000 | 0.000 | 0.250 | 0.167 | 0.437 | What is the CEO's name at Acme Corp? |
| no_answer_003 | no_answer | ✗ | 1.000 | 0.000 | 0.500 | 0.500 | 0.510 | What is the stock price of Acme Corp today? |
| no_answer_004 | no_answer | ✗ | 1.000 | 0.000 | 0.375 | 0.250 | 0.482 | Does Acme DataStream support streaming to Databricks directl… |
| no_answer_005 | no_answer | ✗ | 1.000 | 0.000 | 0.375 | 0.250 | 0.487 | What is the SLA for the Acme Corp IT support desk response t… |
| no_answer_006 | no_answer | ✗ | 1.000 | 0.000 | 0.400 | 0.200 | 0.490 | What are the office hours for the Austin HQ cafeteria? |
| no_answer_007 | no_answer | ✗ | 1.000 | 0.000 | 1.000 | 1.000 | 0.772 | How many employees does Acme Corp currently have? |
| no_answer_008 | no_answer | ✗ | 1.000 | 0.000 | 0.250 | 0.000 | 0.429 | What is Acme DataStream's SLA for the Pro tier support respo… |
| no_answer_009 | no_answer | ✗ | 1.000 | 0.000 | 0.300 | 0.200 | 0.464 | What programming languages is the Acme DataStream CLI v1 wri… |
| no_answer_010 | no_answer | ✗ | 1.000 | 0.000 | 0.500 | 0.500 | 0.510 | What is the name of the Acme Corp dental insurance provider? |
| no_answer_011 | no_answer | ✗ | 1.000 | 0.000 | 0.625 | 0.500 | 0.579 | Does Acme Corp offer a company car or transportation stipend… |
| no_answer_012 | no_answer | ✗ | 1.000 | 0.000 | 0.667 | 0.667 | 0.603 | How many offices does Acme Corp have outside of Austin? |
| direct_021 | direct | ✗ | 1.000 | 1.000 | 0.300 | 0.200 | 0.449 | What is the maximum PTO carryover allowed at Acme Corp at ye… |
| direct_022 | direct | ✗ | 1.000 | 1.000 | 0.400 | 0.200 | 0.500 | What is the severance pay formula for Acme Corp employees te… |
| direct_023 | direct | ✗ | 1.000 | 0.080 | 0.625 | 0.500 | 0.580 | What is Acme Corp's target developer account growth in 2026? |
| direct_024 | direct | ✗ | 1.000 | 0.114 | 0.167 | 0.167 | 0.400 | Which reranker model does the Acme RAG platform use? |
| direct_025 | direct | ✗ | 1.000 | 0.080 | 1.000 | 1.000 | 0.770 | What line length does Acme Corp enforce for Python code? |
| direct_026 | direct | ✗ | 1.000 | 1.000 | 0.300 | 0.200 | 0.466 | What is the health insurance coverage percentage for depende… |
| direct_027 | direct | ✗ | 1.000 | 0.092 | 0.375 | 0.250 | 0.501 | What are the supported output formats when reading records f… |
| direct_028 | direct | ✗ | 1.000 | 0.150 | 0.200 | 0.200 | 0.432 | What is the Acme DataStream API v1 end-of-life date? |
| multi_hop_015 | multi_hop | ✗ | 1.000 | 0.507 | 0.250 | 0.167 | 0.434 | What Kubernetes EKS version is used, and what is the Argo CD… |
| multi_hop_016 | multi_hop | ✗ | 1.000 | 0.150 | 0.400 | 0.400 | 0.502 | What are all the mandatory Day 1 training modules for new Ac… |
| multi_hop_017 | multi_hop | ✗ | 1.000 | 0.117 | 0.200 | 0.200 | 0.429 | What are the Acme DataStream Pro tier limits and when does t… |
| ambiguous_013 | ambiguous | ✗ | 1.000 | 0.054 | 1.000 | 1.000 | 0.709 | How is structured logging handled in Acme Corp production se… |
