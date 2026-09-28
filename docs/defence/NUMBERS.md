# Headline numbers

Generated from `eval-2026-09-28.json` and evaluation table `eval-table-1.0`. Locked-set metrics: **pending** (0 locked samples). Every number below names its evidence class; `pending` means not measured, never zero.

## Safety routing by language

Crisis pre-check recall and critical-event misses per language. Small n: read every rate with its denominator.

| Split | Language | n | Critical events missed | Crisis pre-check recall | Crisis pre-check precision |
|---|---|---|---|---|---|
| exposed development | English | 28 | 0/9 | 4/4 | 4/5 |
| exposed development | Hindi | 13 | 0/3 | 2/2 | 2/3 |
| exposed development | Hinglish | 16 | 0/5 | 3/3 | 3/3 |
| exposed candidate | English | 22 | 1/7 | 4/5 | 4/5 |
| exposed candidate | Hindi | 12 | 0/3 | 2/2 | 2/3 |
| exposed candidate | Hinglish | 14 | 0/4 | 2/2 | 2/2 |

## Safety routing and red-team

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Critical-event miss rate | dev | 0.000 | [0.000, 0.184] | 17 | exposed_development |
| Critical routing recall | dev | 1.000 | [0.816, 1.000] | 17 | exposed_development |
| Critical routing precision | dev | 0.895 | [0.686, 0.971] | 19 | exposed_development |
| Crisis pre-check recall | dev | 1.000 | [0.701, 1.000] | 9 | exposed_development |
| Crisis pre-check precision | dev | 0.818 | [0.523, 0.949] | 11 | exposed_development |
| Critical-event miss rate | candidate | 0.071 | [0.013, 0.315] | 14 | exposed_candidate |
| Critical routing recall | candidate | 0.929 | [0.685, 0.987] | 14 | exposed_candidate |
| Critical routing precision | candidate | 0.867 | [0.621, 0.963] | 15 | exposed_candidate |
| Crisis pre-check recall | candidate | 0.889 | [0.565, 0.980] | 9 | exposed_candidate |
| Crisis pre-check precision | candidate | 0.800 | [0.490, 0.943] | 10 | exposed_candidate |
| Red-team cases blocked before synthesis | redteam | 1.000 | [0.910, 1.000] | 39 | exposed_redteam |

## Turn latency (M2)

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Server voice turn: audio received to reply text ready, p50 | local_service ASR, laptop | 475.7 | — | 70 | synthetic_speech_server_side |
| Server voice turn: audio received to reply text ready, p95 | local_service ASR, laptop | 581.0 | — | 70 | synthetic_speech_server_side |
| Speech-to-text request (budget 600 ms), p50 | local_service ASR, laptop | 463.3 | — | 70 | synthetic_speech_server_side |
| Speech-to-text request (budget 600 ms), p95 | local_service ASR, laptop | 572.1 | — | 70 | synthetic_speech_server_side |
| Reply path after the transcript (pre-check, policy, reply), p50 | local_service ASR, laptop | 8.6 | — | 70 | synthetic_speech_server_side |
| Reply path after the transcript (pre-check, policy, reply), p95 | local_service ASR, laptop | 13.1 | — | 70 | synthetic_speech_server_side |
| Server p95 plus the configured 700 ms end-of-speech wait | budget 3000 ms | 1281.0 | — | — | synthetic_speech_server_side |

## Speech emotion, shadow (selected rows)

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Speech emotion UAR: baseline-both-s13/pooled_normalised | test:crema_d | 0.527 | [0.497, 0.560] | 873 | acted_corpus_actor_disjoint |
| Speech emotion UAR: baseline-both-s13/pooled_normalised | test:ravdess_audio_speech | 0.357 | [0.280, 0.435] | 141 | acted_corpus_actor_disjoint |
| Speech emotion UAR: baseline-both-s13/speaker_normalised | test:crema_d | 0.580 | [0.551, 0.611] | 873 | acted_corpus_actor_disjoint |
| Speech emotion UAR: baseline-both-s13/speaker_normalised | test:ravdess_audio_speech | 0.432 | [0.359, 0.509] | 141 | acted_corpus_actor_disjoint |
| Speech emotion UAR: e2v-head-both-s13/default | test:crema_d | 0.784 | [0.756, 0.813] | 873 | possibly_seen_in_pretraining |
| Speech emotion UAR: e2v-head-both-s13/default | test:ravdess_audio_speech | 0.796 | [0.724, 0.863] | 141 | possibly_seen_in_pretraining |
| Speech emotion UAR: e2v-zeroshot-both-s0/abstaining_9to5 | test:crema_d | 0.741 | — | 873 | possibly_seen_in_pretraining |
| Speech emotion UAR: e2v-zeroshot-both-s0/abstaining_9to5 | test:ravdess_audio_speech | 0.782 | — | 141 | possibly_seen_in_pretraining |
| Speech emotion UAR: e2v-zeroshot-both-s0/forced_5 | test:crema_d | 0.766 | — | 873 | possibly_seen_in_pretraining |
| Speech emotion UAR: e2v-zeroshot-both-s0/forced_5 | test:ravdess_audio_speech | 0.809 | — | 141 | possibly_seen_in_pretraining |
| Speech emotion UAR: wavlm-both-s13/default | test:crema_d | 0.758 | [0.730, 0.786] | 873 | acted_corpus_actor_disjoint |
| Speech emotion UAR: wavlm-both-s13/default | test:ravdess_audio_speech | 0.758 | [0.680, 0.833] | 141 | acted_corpus_actor_disjoint |
| Speech emotion UAR: whisper-head-both-s13/default | test:crema_d | 0.767 | [0.740, 0.795] | 873 | acted_corpus_actor_disjoint |
| Speech emotion UAR: whisper-head-both-s13/default | test:ravdess_audio_speech | 0.784 | [0.712, 0.852] | 141 | acted_corpus_actor_disjoint |

## Text affect, shadow

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Text affect UAR: muril-base-s13 | test:en | 0.815 | [0.786, 0.844] | 2000 | source_corpus_upstream_split |
| Text affect UAR: muril-base-s13 | test:hi | 0.742 | [0.704, 0.777] | 778 | source_corpus_sentence_disjoint |
| Text affect UAR: muril-base-s13 | test:hi_user_turns | 0.703 | — | 495 | source_corpus_sentence_disjoint |
| Text affect UAR: muril-base-s13 | test:hinglish | 0.713 | [0.675, 0.753] | 777 | transliterated_augmentation |
| Text affect UAR: muril-stagea-s13 | test:en | 0.812 | [0.780, 0.839] | 2000 | source_corpus_upstream_split |
| Text affect UAR: muril-stagea-s13 | test:hi | 0.745 | [0.709, 0.781] | 778 | source_corpus_sentence_disjoint |
| Text affect UAR: muril-stagea-s13 | test:hi_user_turns | 0.707 | — | 495 | source_corpus_sentence_disjoint |
| Text affect UAR: muril-stagea-s13 | test:hinglish | 0.699 | [0.664, 0.736] | 777 | transliterated_augmentation |
| Text affect UAR: xlmr-base-s13 | test:en | 0.805 | [0.774, 0.833] | 2000 | source_corpus_upstream_split |
| Text affect UAR: xlmr-base-s13 | test:hi | 0.748 | [0.711, 0.787] | 778 | source_corpus_sentence_disjoint |
| Text affect UAR: xlmr-base-s13 | test:hi_user_turns | 0.710 | — | 495 | source_corpus_sentence_disjoint |
| Text affect UAR: xlmr-base-s13 | test:hinglish | 0.705 | [0.669, 0.744] | 777 | transliterated_augmentation |

## Shadow safety detector, Stage W

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Shadow detector macro F1, fictional holdout (W2 seed 13) | synthetic holdout | 0.733 | — | 1190 | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W2 seed 13) | en | 0.990 | — | — | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W2 seed 13) | hi | 0.944 | — | — | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W2 seed 13) | hinglish | 0.835 | — | — | synthetic_development |
| Shadow detector recall vs source label: D5 (W2 seed 13) | weak test bucket | 0.812 | [0.775, 0.844] | 505 | weak_supervision_from_source_label |
| Shadow detector recall vs source label: continuing_threat (W2 seed 13) | weak test bucket | 0.807 | [0.777, 0.834] | 741 | weak_supervision_from_source_label |
| Shadow detector recall vs source label: crisis_self_harm (W2 seed 13) | weak test bucket | 0.959 | [0.951, 0.966] | 3000 | weak_supervision_from_source_label |
| Shadow detector micro F1 vs deterministic rules (W2 seed 13) | dev | 0.595 | — | 57 | exposed_development |
| Shadow detector micro F1 vs deterministic rules (W2 seed 13) | candidates | 0.584 | — | 48 | exposed_candidate |
| Shadow detector fires on indirect-wording probes (W2 seed 13) | 10 probes | 0.857 | — | 7 | descriptive_probe |
| Shadow detector macro F1 (W0 seed 13, corpus 7b-v2), multi-turn records | synthetic holdout | 0.721 | — | 440 | synthetic_development |
| Shadow detector macro F1 (W0 seed 13, corpus 7b-v2), single-turn records | synthetic holdout | 0.696 | — | 1008 | synthetic_development |
| Shadow detector macro F1, fictional holdout (W0 seed 13, corpus 7b-v2) | synthetic holdout | 0.710 | — | 1448 | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W0 seed 13, corpus 7b-v2) | en | 0.991 | — | — | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W0 seed 13, corpus 7b-v2) | hi | 0.941 | — | — | synthetic_development |
| Shadow detector crisis recall, fictional holdout (W0 seed 13, corpus 7b-v2) | hinglish | 0.756 | — | — | synthetic_development |
| Shadow detector recall vs source label: D5 (W0 seed 13, corpus 7b-v2) | weak test bucket | 0.865 | [0.833, 0.892] | 505 | weak_supervision_from_source_label |
| Shadow detector recall vs source label: continuing_threat (W0 seed 13, corpus 7b-v2) | weak test bucket | 0.111 | [0.090, 0.135] | 741 | weak_supervision_from_source_label |
| Shadow detector recall vs source label: crisis_self_harm (W0 seed 13, corpus 7b-v2) | weak test bucket | 0.941 | [0.932, 0.949] | 3000 | weak_supervision_from_source_label |
| Shadow detector micro F1 vs deterministic rules (W0 seed 13, corpus 7b-v2) | dev | 0.562 | — | 57 | exposed_development |
| Shadow detector micro F1 vs deterministic rules (W0 seed 13, corpus 7b-v2) | candidates | 0.619 | — | 48 | exposed_candidate |
| Shadow detector fires on indirect-wording probes (W0 seed 13, corpus 7b-v2) | 10 probes | 0.857 | — | 7 | descriptive_probe |

## Interpretable baseline, AE-15

| Metric | Scope | Value | 95% CI | n | Evidence |
|---|---|---|---|---|---|
| Logistic baseline macro F1, fictional holdout (LR-W0) | synthetic holdout | 0.477 | — | 1190 | synthetic_development |
| Logistic baseline AUROC vs source label: continuing_threat (LR-W0) | weak test bucket | 0.530 | — | 1652 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: crisis_self_harm (LR-W0) | weak test bucket | 0.615 | — | 6000 | weak_supervision_from_source_label |
| Logistic baseline micro F1 vs deterministic rules (LR-W0) | dev | 0.244 | — | 57 | exposed_development |
| Logistic baseline micro F1 vs deterministic rules (LR-W0) | candidates | 0.290 | — | 48 | exposed_candidate |
| Logistic baseline macro F1, fictional holdout (LR-W2, corpus candidates) | synthetic holdout | 0.497 | — | 1190 | synthetic_development |
| Logistic baseline AUROC vs source label: D5 (LR-W2, corpus candidates) | weak test bucket | 0.762 | — | 968 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: continuing_threat (LR-W2, corpus candidates) | weak test bucket | 0.801 | — | 1652 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: crisis_self_harm (LR-W2, corpus candidates) | weak test bucket | 0.935 | — | 6000 | weak_supervision_from_source_label |
| Logistic baseline micro F1 vs deterministic rules (LR-W2, corpus candidates) | dev | 0.477 | — | 57 | exposed_development |
| Logistic baseline micro F1 vs deterministic rules (LR-W2, corpus candidates) | candidates | 0.373 | — | 48 | exposed_candidate |
| Logistic baseline macro F1 (LR-W0, corpus 7b-v2), multi-turn records | synthetic holdout | 0.419 | — | 440 | synthetic_development |
| Logistic baseline macro F1 (LR-W0, corpus 7b-v2), single-turn records | synthetic holdout | 0.453 | — | 1008 | synthetic_development |
| Logistic baseline macro F1, fictional holdout (LR-W0, corpus 7b-v2) | synthetic holdout | 0.440 | — | 1448 | synthetic_development |
| Logistic baseline AUROC vs source label: continuing_threat (LR-W0, corpus 7b-v2) | weak test bucket | 0.530 | — | 1652 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: crisis_self_harm (LR-W0, corpus 7b-v2) | weak test bucket | 0.630 | — | 6000 | weak_supervision_from_source_label |
| Logistic baseline micro F1 vs deterministic rules (LR-W0, corpus 7b-v2) | dev | 0.203 | — | 57 | exposed_development |
| Logistic baseline micro F1 vs deterministic rules (LR-W0, corpus 7b-v2) | candidates | 0.286 | — | 48 | exposed_candidate |
| Logistic baseline macro F1 (LR-W2, corpus candidates), multi-turn records | synthetic holdout | 0.467 | — | 440 | synthetic_development |
| Logistic baseline macro F1 (LR-W2, corpus candidates), single-turn records | synthetic holdout | 0.491 | — | 1008 | synthetic_development |
| Logistic baseline macro F1, fictional holdout (LR-W2, corpus candidates) | synthetic holdout | 0.484 | — | 1448 | synthetic_development |
| Logistic baseline AUROC vs source label: D5 (LR-W2, corpus candidates) | weak test bucket | 0.763 | — | 968 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: continuing_threat (LR-W2, corpus candidates) | weak test bucket | 0.808 | — | 1652 | weak_supervision_from_source_label |
| Logistic baseline AUROC vs source label: crisis_self_harm (LR-W2, corpus candidates) | weak test bucket | 0.938 | — | 6000 | weak_supervision_from_source_label |
| Logistic baseline micro F1 vs deterministic rules (LR-W2, corpus candidates) | dev | 0.486 | — | 57 | exposed_development |
| Logistic baseline micro F1 vs deterministic rules (LR-W2, corpus candidates) | candidates | 0.378 | — | 48 | exposed_candidate |

## Not measured yet

- **M7** Detector recall: explicit_human_request (dev): pending, no positives in this split
- **M7** Detector precision: explicit_human_request (dev): pending, no positives in this split
- **M7** Detector recall: explicit_human_request (candidate): pending, no positives in this split
- **M7** Detector precision: explicit_human_request (candidate): pending, no positives in this split
- **M1** Critical-event miss rate (locked): pending, locked set has 0 samples; crisis and danger samples need two reviewer approvals
- **M3** Time to first safety alert on the console (end to end): pending, needs scripted end-to-end runs
- **M4** Executive decision time on the packet (rehearsal): pending, needs a rehearsal with a non-team reader
- **M6** Speech-to-text word error rate by language and condition (hi, en): pending, no target claimed; needs the approved evaluation audio
- **M9** Repeat-question rate per session (scenario transcripts): pending
- **D4** Voice prosody rule (D4) agreement with human judgement (voice turns): unvalidated, rule is unit-tested only; needs team recordings and expert review
- **M2** Turn latency on a phone (victim stops to assistant starts) (phone, Wi-Fi, Hindi): pending, needs the phone, LAN upload, TTS (M13) and Hindi recordings (H5)
