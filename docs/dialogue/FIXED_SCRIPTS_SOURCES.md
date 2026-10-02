# Fixed scripts — draft wording, decisions and sources

Status: **drafted 2026-10-01, IN REVIEW, not speakable.** Text lives in `ml/dialogue/scripts/fixed_scripts.py` (`DRAFT_TEXT`). A script becomes speakable only when its record is set to `APPROVED` with a named reviewer and a review date; the fail-closed behaviour in `FIXED_SCRIPTS_REVIEW.md` is unchanged until then.

Written at the project lead's direction from published guidance, instead of waiting for in-team authoring. The content requirements of `STATES.md` are unchanged. **SX still needs the counsellor or psychology faculty review that `STATES.md` requires before any use beyond invited testers**, and a native Hindi speaker should read every Hindi script as crisis language in its own right, not as a translation.

Every script passes the same content checks as generated text: banned patterns, the prohibition lexicon and the phrase rules, in both languages. None asks a question and none trips the crisis pre-check (`ml/tests/test_fixed_script_content.py`).

## Scripts

Revised 2026-10-02 after the `dialogue-safety-reviewer` pass (findings and outcomes below).

| | English | Hindi |
|---|---|---|
| **S0** | I am SAHAY, an AI assistant, not a person. A human support officer can read everything you share here, and you can ask to talk to a person at any time. When you are ready, tell me what happened, in your own words; you can share as much or as little as you want. | मैं सहाय हूँ, एक एआई सहायक, कोई इंसान नहीं। आप यहाँ जो भी बताएँ, उसे सहायता अधिकारी पढ़ सकते हैं, और जब भी चाहें, किसी व्यक्ति से बात करने के लिए कहिए। जब आप तैयार हों, अपने शब्दों में बताइए कि क्या हुआ; आप जितना चाहें, उतना ही बताइए। |
| **S9** | Thank you. What you shared has been saved. A human support officer can review it, and you can see its status under My requests, where your reference number is shown. You can ask to talk to a person at any time. | धन्यवाद, आपकी बात सहेज ली गई है। सहायता अधिकारी इसे देख सकते हैं, और "मेरे अनुरोध" में इसकी स्थिति देखी जा सकती है, जहाँ आपकी संदर्भ संख्या दी गई है। जब भी चाहें, किसी व्यक्ति से बात करने के लिए कहिए। |
| **SX** | Thank you for telling me. I am connecting you to a person right now. Please stay in this conversation. | आपने मुझे यह बताया, इसके लिए धन्यवाद। आपको अभी एक व्यक्ति से जोड़ा जा रहा है। कृपया इस बातचीत में बने रहिए। |
| **SH** | I am connecting you to a person now. Please stay in this conversation; they can see everything you share here. | आपको अभी एक व्यक्ति से जोड़ा जा रहा है। कृपया इस बातचीत में बने रहिए; आप यहाँ जो भी बताएँ, वह उन्हें दिखेगा। |

## Decisions taken (numbering from `FIXED_SCRIPTS_REVIEW.md`)

| # | Decision | Why |
|---|---|---|
| S0-1 | The assistant names itself "SAHAY, an AI assistant, not a person", and the human is a "support officer", the label the chat already shows. | WHO's AI-for-health guidance puts transparency and autonomy first [3]; the first sentence removes any doubt about who is speaking. Neither the product name nor "support officer" implies a government operator. |
| S0-2 | Recording is not restated; it stays on the consent screen. | The consent screen already carries it; S0 keeps to the four required facts. |
| S0-3 | NHAA 14566 is not named. | This prototype is not the government service [1]; naming it would imply that it is. |
| S0-4 | Fixed scripts may run to three sentences. | Each carries several required facts; generated turns keep the one-sentence rule. |
| S0-5 | Formal आप throughout; no Hinglish in the scripts. | Respectful default register; replies still match the user's language. |
| S0-6 | Open invitation in the person's own words, with "when you are ready" and "as much or as little as you want". | Trauma-informed practice puts choice and control with the person [2]; S1 expects an open narrative. |
| S0-7 | "A human support officer **can** read everything", not "reads". | True on both the staffed laptop demo and the hosted tester build, where nobody may be watching. |
| Hindi | Gender-neutral forms (बताएँ, कहिए, देख सकते हैं); "सहेज ली गई" rather than "दर्ज", and the app label "मेरे अनुरोध" rather than "मेरी शिकायतें". | "दर्ज" with "शिकायतें" reads as a registered official complaint, which this prototype does not create. |
| S9-1 | The reference number is not read out; S9 points to My requests, where it is displayed. | Spoken codes fail on poor lines; the app already shows it. |
| S9-2 | "A human helpline officer will review it" — process only. | No outcome, timeline, arrest or compensation (prohibition lexicon `promise_outcome`). |
| S9-3 | No callback is implied. | The demo cannot place callbacks; updates appear under My requests. |
| S9-4 | One closing for every case, including abstention. | Wording must not reveal any assessment. |
| S9-5 | The closing repeats the right to a person. | Invariant 7. |
| SX-2 | Acknowledgement: "Thank you for telling me." | Listening without judgement and recognising that it took courage to speak [5]; no minimising language. |
| SX-3 | "I am connecting you to a person right now" (Hindi: passive, "you are being connected"), not "a person will speak with you". | True at the moment it is said: the system has requested takeover. The 988 policy centres active engagement and keeping the person connected [4]; the script makes no promise the demo cannot keep. |
| SX-4 | No helpline number is spoken. | `STATES.md`: SX says nothing else. A referral mid-crisis is a clinical decision. The tester briefing (`docs/DEPLOY_TESTERS.md`) lists Tele-MANAS 14416 [6] and 112 outside the app. |
| SX-5 | SX says nothing about what was detected. | No assessment reaches the victim (invariant 3). |
| SX-6 | After SX the session holds silently; the app shows the human controls. Enforced in code: a fixed script is said once, on entering its state. | SX does not return to intake, and repeating "thank you for telling me" to every later message is harmful. |
| SX-7 | Same script when crisis words are attributed to someone else. | The pre-check cannot tell reliably; the safer script is identical. Open for counsellor review. |
| SH-1 | One script for requested and escalated handoffs. | The person needs the same two facts either way. |
| SH-2 | Same script when consent was declined. | Nothing in it refers to AI analysis. |
| SH-3 | The takeover notice stays a separate app string (`human.joined`). | It is shown when the server reports a person has joined. |
| SH-4 | No wait time is stated, and no promise about what the officer will or will not ask. | The demo cannot guarantee either. |
| Stay | SX and SH say "stay in this conversation", not "stay here". | "Stay here" (Hindi यहीं) can be heard as an instruction about a physical place, for someone on a roof or in a room the abuser can reach. |

## Safety review (dialogue-safety-reviewer, 2026-10-02)

Fixed: repeated SX/SH/S9 on later turns (B1); SH after the session ended (B2); S0 "reads" claim (B4); S9 Hindi implying a registered complaint (B5); STATES.md not matching the decisions (B6); "stay here" (B7); and the advisory wording, language, empty-closing, set-approval and audit-marker findings. Tests cover each.

**Still blocking APPROVED status:**

- **SX-1:** no named counsellor or psychology faculty reviewer yet.
- **SX-3 on the hosted build (B3):** SX says "I am connecting you to a person right now", but the hosted tester build may have no officer signed in. Before SX is approved there, either guarantee a signed-in officer (with an alert sound) for every window in which sessions can be created, or take SX-4 (speaking a helpline number) back to the counsellor. This is operational; weaker wording is not the fix.

**Raised for a lead decision (pre-existing, outside these scripts):**

- `assistant.turn` carries `intent: "crisis_script"` to the victim client, which labels a crisis detection on the victim's device (frozen CONTRACTS.md §1; needs a proposal).
- ~~With consent declined, the crisis pre-check never ran.~~ **Decided 2026-10-02 by the project lead:** the keyword pre-check runs on declined and pending sessions too. A match raises the crisis alert and the takeover request and says SX once; no assessment, score, band, extraction or dialogue runs. After an officer has taken over, nothing runs (the officer is reading).

## Sources

1. Press Information Bureau, Ministry of Social Justice and Empowerment — *National Helpline Against Atrocities on SCs/STs launched* (14566, docket number per complaint, status tracking). https://www.pib.gov.in/PressReleasePage.aspx?PRID=1780979
2. SAMHSA's six principles of a trauma-informed approach (safety; trustworthiness and transparency; peer support; collaboration and mutuality; empowerment, voice and choice; cultural, historical and gender issues). Summary: https://pmc.ncbi.nlm.nih.gov/articles/PMC9319668/
3. World Health Organization (2021) — *Ethics and governance of artificial intelligence for health* (protect autonomy; ensure transparency, explainability and intelligibility). https://iris.who.int/server/api/core/bitstreams/f780d926-4ae3-42ce-a6d6-e898a5562621/content
4. 988 Suicide and Crisis Lifeline — *Suicide Safety Policy* (active engagement; least invasive, most collaborative intervention; staying connected with the person until help is present). https://988lifeline.org/wp-content/uploads/2023/02/FINAL_988_Suicide_and_Crisis_Lifeline_Suicide_Safety_Policy_-3.pdf
5. Samaritans — *Listen without judgement*. https://www.samaritans.org/how-we-can-help/if-youre-worried-about-someone-else/how-to-interrupt-someones-suicidal-thoughts-guide/listen-without-judgement/
6. Press Information Bureau, Ministry of Health and Family Welfare — Tele-MANAS national tele-mental-health helpline 14416. https://www.pib.gov.in/PressReleasePage.aspx?PRID=2022057
