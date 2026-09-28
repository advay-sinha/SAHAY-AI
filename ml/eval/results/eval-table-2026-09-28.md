# SAHAY-AI evaluation table

Table `eval-table-1.0` · evaluation run 2026-09-28T00:00:00+00:00 · commit `0f05ec466e47`

Every number below comes from the file named in its source column. `pending` means not measured yet; it is never a zero. Exposed fixtures were published during development, so results on them show regression behaviour, not generalisation. Intervals are 95%: Wilson for proportions, item-level bootstrap for UAR (1000 resamples, seed 13), which ignores speaker clustering and is therefore optimistic.

Locked-set metrics: **pending** (0 locked samples).

Versions: corpus `2026.09.11-1`, crisis_lexicon `crisis-v1.2-unreviewed`, label_schema `1.0.0`, pipeline `text-lexicon-v1+d4-prosody-1.0`, redteam_corpus `2026.09.11-1`, scoring `svi-2026.09-pc08`, validator `guardrails-v1.1`

## Safety routing and red-team (HANDOVER M1, M5)

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| M1 | Critical-event miss rate | dev | 0.000 | [0.000, 0.184] | 17 | exposed_development | measured | 0 of 17 critical events missed |
| M1a | Critical routing recall | dev | 1.000 | [0.816, 1.000] | 17 | exposed_development | measured |  |
| M1b | Critical routing precision | dev | 0.895 | [0.686, 0.971] | 19 | exposed_development | measured | 2 false escalations |
| M1c | Crisis pre-check recall | dev | 1.000 | [0.701, 1.000] | 9 | exposed_development | measured |  |
| M1d | Crisis pre-check precision | dev | 0.818 | [0.523, 0.949] | 11 | exposed_development | measured |  |
| M1 | Critical-event miss rate | candidate | 0.071 | [0.013, 0.315] | 14 | exposed_candidate | measured | 1 of 14 critical events missed |
| M1a | Critical routing recall | candidate | 0.929 | [0.685, 0.987] | 14 | exposed_candidate | measured |  |
| M1b | Critical routing precision | candidate | 0.867 | [0.621, 0.963] | 15 | exposed_candidate | measured | 2 false escalations |
| M1c | Crisis pre-check recall | candidate | 0.889 | [0.565, 0.980] | 9 | exposed_candidate | measured |  |
| M1d | Crisis pre-check precision | candidate | 0.800 | [0.490, 0.943] | 10 | exposed_candidate | measured |  |
| M1 | Critical-event miss rate | locked | **pending** | — | 0 | locked | pending | locked set has 0 samples; crisis and danger samples need two reviewer approvals |
| M5 | Red-team cases blocked before synthesis | redteam | 1.000 | [0.910, 1.000] | 39 | exposed_redteam | measured | critical failures 0; fixtures exposed on 2026-09-11 |

## Detectors (HANDOVER M7)

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| M7 | Detector recall: communication_safety_coercion | dev | 0.857 | [0.487, 0.974] | 7 | exposed_development | measured |  |
| M7 | Detector precision: communication_safety_coercion | dev | 1.000 | [0.610, 1.000] | 6 | exposed_development | measured |  |
| M7 | Detector recall: continuing_threat | dev | 0.900 | [0.699, 0.972] | 20 | exposed_development | measured |  |
| M7 | Detector precision: continuing_threat | dev | 1.000 | [0.824, 1.000] | 18 | exposed_development | measured |  |
| M7 | Detector recall: crisis_self_harm | dev | 1.000 | [0.646, 1.000] | 7 | exposed_development | measured |  |
| M7 | Detector precision: crisis_self_harm | dev | 0.636 | [0.354, 0.848] | 11 | exposed_development | measured |  |
| M7 | Detector recall: explicit_human_request | dev | **pending** | — | 0 | exposed_development | pending | no positives in this split |
| M7 | Detector precision: explicit_human_request | dev | **pending** | — | 0 | exposed_development | pending | no positives in this split |
| M7 | Detector recall: immediate_danger | dev | 1.000 | [0.676, 1.000] | 8 | exposed_development | measured |  |
| M7 | Detector precision: immediate_danger | dev | 1.000 | [0.676, 1.000] | 8 | exposed_development | measured |  |
| M7 | Detector recall: isolation_boycott_displacement | dev | 0.800 | [0.376, 0.964] | 5 | exposed_development | measured |  |
| M7 | Detector precision: isolation_boycott_displacement | dev | 1.000 | [0.510, 1.000] | 4 | exposed_development | measured |  |
| M7 | Detector recall: legal_urgency | dev | 1.000 | [0.701, 1.000] | 9 | exposed_development | measured |  |
| M7 | Detector precision: legal_urgency | dev | 1.000 | [0.701, 1.000] | 9 | exposed_development | measured |  |
| M7 | Detector recall: medical_urgency | dev | 1.000 | [0.510, 1.000] | 4 | exposed_development | measured |  |
| M7 | Detector precision: medical_urgency | dev | 1.000 | [0.510, 1.000] | 4 | exposed_development | measured |  |
| M7 | Detector recall: communication_safety_coercion | candidate | 0.600 | [0.231, 0.882] | 5 | exposed_candidate | measured |  |
| M7 | Detector precision: communication_safety_coercion | candidate | 1.000 | [0.439, 1.000] | 3 | exposed_candidate | measured |  |
| M7 | Detector recall: continuing_threat | candidate | 0.917 | [0.646, 0.985] | 12 | exposed_candidate | measured |  |
| M7 | Detector precision: continuing_threat | candidate | 1.000 | [0.741, 1.000] | 11 | exposed_candidate | measured |  |
| M7 | Detector recall: crisis_self_harm | candidate | 0.889 | [0.565, 0.980] | 9 | exposed_candidate | measured |  |
| M7 | Detector precision: crisis_self_harm | candidate | 0.800 | [0.490, 0.943] | 10 | exposed_candidate | measured |  |
| M7 | Detector recall: explicit_human_request | candidate | **pending** | — | 0 | exposed_candidate | pending | no positives in this split |
| M7 | Detector precision: explicit_human_request | candidate | **pending** | — | 0 | exposed_candidate | pending | no positives in this split |
| M7 | Detector recall: immediate_danger | candidate | 1.000 | [0.566, 1.000] | 5 | exposed_candidate | measured |  |
| M7 | Detector precision: immediate_danger | candidate | 1.000 | [0.566, 1.000] | 5 | exposed_candidate | measured |  |
| M7 | Detector recall: isolation_boycott_displacement | candidate | 0.500 | [0.150, 0.850] | 4 | exposed_candidate | measured |  |
| M7 | Detector precision: isolation_boycott_displacement | candidate | 1.000 | [0.342, 1.000] | 2 | exposed_candidate | measured |  |
| M7 | Detector recall: legal_urgency | candidate | 0.857 | [0.487, 0.974] | 7 | exposed_candidate | measured |  |
| M7 | Detector precision: legal_urgency | candidate | 1.000 | [0.610, 1.000] | 6 | exposed_candidate | measured |  |
| M7 | Detector recall: medical_urgency | candidate | 0.667 | [0.208, 0.939] | 3 | exposed_candidate | measured |  |
| M7 | Detector precision: medical_urgency | candidate | 1.000 | [0.342, 1.000] | 2 | exposed_candidate | measured |  |

## Abstention and bands

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| A1 | Abstains when abstention is expected | dev | 1.000 | [0.510, 1.000] | 4 | exposed_development | measured |  |
| A2 | Band agreement with the labelled band | dev | 1.000 | [0.816, 1.000] | 17 | exposed_development | measured |  |
| A1 | Abstains when abstention is expected | candidate | 1.000 | [0.206, 1.000] | 1 | exposed_candidate | measured |  |
| A2 | Band agreement with the labelled band | candidate | 0.929 | [0.685, 0.987] | 14 | exposed_candidate | measured |  |

## Speech emotion (shadow; acted English only)

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| SER | Speech emotion UAR: baseline-both-s13/pooled_normalised | test:crema_d | 0.527 | [0.497, 0.560] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.5282; lowest class recall 0.3778 |
| SER | Speech emotion UAR: baseline-both-s13/pooled_normalised | test:ravdess_audio_speech | 0.357 | [0.280, 0.435] | 141 | acted_corpus_actor_disjoint | measured | macro-F1 0.3444; lowest class recall 0.1613 |
| SER | Speech emotion UAR: baseline-both-s13/speaker_normalised | test:crema_d | 0.580 | [0.551, 0.611] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.5686; lowest class recall 0.3167 |
| SER | Speech emotion UAR: baseline-both-s13/speaker_normalised | test:ravdess_audio_speech | 0.432 | [0.359, 0.509] | 141 | acted_corpus_actor_disjoint | measured | macro-F1 0.3785; lowest class recall 0.1875 |
| SER | Speech emotion UAR: baseline-crema-s13/pooled_normalised | cross:ravdess_audio_speech | 0.345 | [0.327, 0.363] | 849 | acted_corpus_actor_disjoint | measured | macro-F1 0.2101; lowest class recall 0.0052 |
| SER | Speech emotion UAR: baseline-crema-s13/pooled_normalised | test:crema_d | 0.544 | [0.511, 0.579] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.5413; lowest class recall 0.3611 |
| SER | Speech emotion UAR: baseline-crema-s13/speaker_normalised | cross:ravdess_audio_speech | 0.487 | [0.455, 0.520] | 849 | acted_corpus_actor_disjoint | measured | macro-F1 0.4471; lowest class recall 0.2461 |
| SER | Speech emotion UAR: baseline-crema-s13/speaker_normalised | test:crema_d | 0.594 | [0.561, 0.625] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.583; lowest class recall 0.3389 |
| SER | Speech emotion UAR: e2v-head-both-s13/default | test:crema_d | 0.784 | [0.756, 0.813] | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7805; lowest class recall 0.6167 |
| SER | Speech emotion UAR: e2v-head-both-s13/default | test:ravdess_audio_speech | 0.796 | [0.724, 0.863] | 141 | possibly_seen_in_pretraining | measured | macro-F1 0.7926; lowest class recall 0.6774 |
| SER | Speech emotion UAR: e2v-head-crema-s13/default | cross:ravdess_audio_speech | 0.872 | [0.850, 0.893] | 849 | possibly_seen_in_pretraining | measured | macro-F1 0.859; lowest class recall 0.7435 |
| SER | Speech emotion UAR: e2v-head-crema-s13/default | test:crema_d | 0.790 | [0.763, 0.817] | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7873; lowest class recall 0.6611 |
| SER | Speech emotion UAR: e2v-zeroshot-both-s0/abstaining_9to5 | test:crema_d | 0.741 | — | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7496; lowest class recall 0.4889; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-both-s0/abstaining_9to5 | test:ravdess_audio_speech | 0.782 | — | 141 | possibly_seen_in_pretraining | measured | macro-F1 0.7817; lowest class recall 0.6129; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-both-s0/forced_5 | test:crema_d | 0.766 | — | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7559; lowest class recall 0.5111; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-both-s0/forced_5 | test:ravdess_audio_speech | 0.809 | — | 141 | possibly_seen_in_pretraining | measured | macro-F1 0.7946; lowest class recall 0.6129; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-crema-s0/abstaining_9to5 | cross:ravdess_audio_speech | 0.851 | — | 849 | possibly_seen_in_pretraining | measured | macro-F1 0.8429; lowest class recall 0.6911; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-crema-s0/abstaining_9to5 | test:crema_d | 0.741 | — | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7496; lowest class recall 0.4889; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-crema-s0/forced_5 | cross:ravdess_audio_speech | 0.868 | — | 849 | possibly_seen_in_pretraining | measured | macro-F1 0.8509; lowest class recall 0.7016; no prediction file |
| SER | Speech emotion UAR: e2v-zeroshot-crema-s0/forced_5 | test:crema_d | 0.766 | — | 873 | possibly_seen_in_pretraining | measured | macro-F1 0.7559; lowest class recall 0.5111; no prediction file |
| SER | Speech emotion UAR: wavlm-both-s13/default | test:crema_d | 0.758 | [0.730, 0.786] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.7504; lowest class recall 0.5944 |
| SER | Speech emotion UAR: wavlm-both-s13/default | test:ravdess_audio_speech | 0.758 | [0.680, 0.833] | 141 | acted_corpus_actor_disjoint | measured | macro-F1 0.7634; lowest class recall 0.6562 |
| SER | Speech emotion UAR: wavlm-crema-s13/default | cross:ravdess_audio_speech | 0.447 | [0.422, 0.471] | 849 | acted_corpus_actor_disjoint | measured | macro-F1 0.3804; lowest class recall 0.0157 |
| SER | Speech emotion UAR: wavlm-crema-s13/default | test:crema_d | 0.735 | [0.708, 0.762] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.7243; lowest class recall 0.5778 |
| SER | Speech emotion UAR: whisper-head-both-s13/default | test:crema_d | 0.767 | [0.740, 0.795] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.7637; lowest class recall 0.6056 |
| SER | Speech emotion UAR: whisper-head-both-s13/default | test:ravdess_audio_speech | 0.784 | [0.712, 0.852] | 141 | acted_corpus_actor_disjoint | measured | macro-F1 0.7864; lowest class recall 0.6562 |
| SER | Speech emotion UAR: whisper-head-crema-s13/default | cross:ravdess_audio_speech | 0.706 | [0.677, 0.736] | 849 | acted_corpus_actor_disjoint | measured | macro-F1 0.6889; lowest class recall 0.3704 |
| SER | Speech emotion UAR: whisper-head-crema-s13/default | test:crema_d | 0.751 | [0.723, 0.778] | 873 | acted_corpus_actor_disjoint | measured | macro-F1 0.7542; lowest class recall 0.6722 |

## Text affect (shadow)

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| TXT | Text affect UAR: muril-base-s13 | test:en | 0.815 | [0.786, 0.844] | 2000 | source_corpus_upstream_split | measured | macro-F1 0.5963; lowest class recall 0.6814 |
| TXT | Text affect UAR: muril-base-s13 | test:hi | 0.742 | [0.704, 0.777] | 778 | source_corpus_sentence_disjoint | measured | macro-F1 0.7202; lowest class recall 0.5811 |
| TXT | Text affect UAR: muril-base-s13 | test:hi_user_turns | 0.703 | — | 495 | source_corpus_sentence_disjoint | measured | macro-F1 0.6896; lowest class recall 0.3958; subset not identifiable in the prediction file; interval omitted |
| TXT | Text affect UAR: muril-base-s13 | test:hinglish | 0.713 | [0.675, 0.753] | 777 | transliterated_augmentation | measured | macro-F1 0.693; lowest class recall 0.5 |
| TXT | Text affect UAR: muril-stagea-s13 | test:en | 0.812 | [0.780, 0.839] | 2000 | source_corpus_upstream_split | measured | macro-F1 0.5896; lowest class recall 0.6696 |
| TXT | Text affect UAR: muril-stagea-s13 | test:hi | 0.745 | [0.709, 0.781] | 778 | source_corpus_sentence_disjoint | measured | macro-F1 0.7206; lowest class recall 0.5946 |
| TXT | Text affect UAR: muril-stagea-s13 | test:hi_user_turns | 0.707 | — | 495 | source_corpus_sentence_disjoint | measured | macro-F1 0.6935; lowest class recall 0.4375; subset not identifiable in the prediction file; interval omitted |
| TXT | Text affect UAR: muril-stagea-s13 | test:hinglish | 0.699 | [0.664, 0.736] | 777 | transliterated_augmentation | measured | macro-F1 0.6743; lowest class recall 0.4459 |
| TXT | Text affect UAR: xlmr-base-s13 | test:en | 0.805 | [0.774, 0.833] | 2000 | source_corpus_upstream_split | measured | macro-F1 0.595; lowest class recall 0.6771 |
| TXT | Text affect UAR: xlmr-base-s13 | test:hi | 0.748 | [0.711, 0.787] | 778 | source_corpus_sentence_disjoint | measured | macro-F1 0.7308; lowest class recall 0.6351 |
| TXT | Text affect UAR: xlmr-base-s13 | test:hi_user_turns | 0.710 | — | 495 | source_corpus_sentence_disjoint | measured | macro-F1 0.6987; lowest class recall 0.4792; subset not identifiable in the prediction file; interval omitted |
| TXT | Text affect UAR: xlmr-base-s13 | test:hinglish | 0.705 | [0.669, 0.744] | 777 | transliterated_augmentation | measured | macro-F1 0.6803; lowest class recall 0.5 |

## Not yet measured or enforced by tests (HANDOVER M2–M4, M6, M8, M9; D4)

| ID | Metric | Scope | Value | 95% CI | n | Evidence | Status | Note |
|---|---|---|---|---|---|---|---|---|
| M2 | Turn latency p50 / p95 (victim stops to assistant starts) | voice turn | **pending** | — | — | none | pending | the turn loop is not instrumented end to end; speech-to-text smoke timings are not M2 |
| M3 | Time to first safety alert on the console | end to end | **pending** | — | — | none | pending | needs scripted end-to-end runs |
| M4 | Executive decision time on the packet | rehearsal | **pending** | — | — | none | pending | needs a rehearsal with a non-team reader |
| M6 | Speech-to-text word error rate by language and condition | hi, en | **pending** | — | — | none | pending | no target claimed; needs the approved evaluation audio |
| M8 | Assessment data reaching the victim client | backend payloads | **test_enforced** | — | — | automated_test | test_enforced | enforced by tests on every run; not a sampled measurement |
| M9 | Repeat-question rate per session | scenario transcripts | **pending** | — | — | none | pending |  |
| D4 | Voice prosody rule (D4) agreement with human judgement | voice turns | **unvalidated** | — | — | none | unvalidated | rule is unit-tested only; needs team recordings and expert review |

## Sources

- `SAHAY_TRAINING_ROOT/ser/runs/baseline-both-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/baseline-crema-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/e2v-head-both-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/e2v-head-crema-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/e2v-zeroshot-both-s0/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/e2v-zeroshot-crema-s0/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/wavlm-both-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/wavlm-crema-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/whisper-head-both-s13/report.json`
- `SAHAY_TRAINING_ROOT/ser/runs/whisper-head-crema-s13/report.json`
- `SAHAY_TRAINING_ROOT/textaffect/runs-v2/muril-base-s13/report.json`
- `SAHAY_TRAINING_ROOT/textaffect/runs-v2/muril-stagea-s13/report.json`
- `SAHAY_TRAINING_ROOT/textaffect/runs-v2/xlmr-base-s13/report.json`
- `backend/tests/test_role_fanout.py; backend/tests/test_timeline_leakage.py`
- `docs/HANDOVER.md`
- `eval-2026-09-28.json`
- `ml/acoustics/D4_CARD.md`
