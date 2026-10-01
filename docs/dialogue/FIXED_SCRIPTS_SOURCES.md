# Fixed scripts — draft wording, decisions and sources

Status: **drafted 2026-10-01, IN REVIEW, not speakable.** Text lives in `ml/dialogue/scripts/fixed_scripts.py` (`DRAFT_TEXT`). A script becomes speakable only when its record is set to `APPROVED` with a named reviewer and a review date; the fail-closed behaviour in `FIXED_SCRIPTS_REVIEW.md` is unchanged until then.

Written at the project lead's direction from published guidance, instead of waiting for in-team authoring. The content requirements of `STATES.md` are unchanged. **SX still needs the counsellor or psychology faculty review that `STATES.md` requires before any use beyond invited testers**, and a native Hindi speaker should read every Hindi script as crisis language in its own right, not as a translation.

Every script passes the same content checks as generated text: banned patterns, the prohibition lexicon and the phrase rules, in both languages. None asks a question and none trips the crisis pre-check (`ml/tests/test_fixed_script_content.py`).

## Scripts

| | English | Hindi |
|---|---|---|
| **S0** | I am SAHAY, an AI assistant, not a person. A human helpline officer reads everything you share here, and you can ask to talk to a person at any time. When you are ready, tell me what happened, in your own words. | मैं सहाय हूँ, एक एआई सहायक, कोई व्यक्ति नहीं। आप यहाँ जो भी बताएँगे, उसे हेल्पलाइन का एक अधिकारी पढ़ता है, और आप कभी भी किसी व्यक्ति से बात करने के लिए कह सकते हैं। जब आप तैयार हों, तो अपने शब्दों में बताइए कि क्या हुआ। |
| **S9** | Thank you, what you shared has been recorded. A human helpline officer will review it, and you can follow updates under My requests, where your reference number is shown. You can ask to talk to a person at any time. | धन्यवाद, आपने जो बताया वह दर्ज हो गया है। हेल्पलाइन का एक अधिकारी इसे देखेगा, और आप "मेरी शिकायतें" में इसकी जानकारी देख सकते हैं, जहाँ आपका संदर्भ नंबर भी दिखाया गया है। आप कभी भी किसी व्यक्ति से बात करने के लिए कह सकते हैं। |
| **SX** | Thank you for telling me. I am connecting you to a person right now. Please stay here. | मुझे बताने के लिए धन्यवाद। आपको अभी एक व्यक्ति से जोड़ा जा रहा है। कृपया यहीं रहिए। |
| **SH** | I am connecting you to a person now. Please stay here; they will see what you have already shared, so you do not have to repeat it. | आपको अभी एक व्यक्ति से जोड़ा जा रहा है। कृपया यहीं रहिए; आपने जो पहले बताया है, वह उन्हें दिखेगा, इसलिए आपको दोबारा बताने की ज़रूरत नहीं है। |

## Decisions taken (numbering from `FIXED_SCRIPTS_REVIEW.md`)

| # | Decision | Why |
|---|---|---|
| S0-1 | The assistant names itself "SAHAY, an AI assistant, not a person". | WHO's AI-for-health guidance puts transparency and autonomy first [3]; the first sentence removes any doubt about who is speaking. The product name avoids implying a government operator. |
| S0-2 | Recording is not restated; it stays on the consent screen. | The consent screen already carries it; S0 keeps to the four required facts. |
| S0-3 | NHAA 14566 is not named. | This prototype is not the government service [1]; naming it would imply that it is. |
| S0-4 | Fixed scripts may run to three sentences. | Each carries several required facts; generated turns keep the one-sentence rule. |
| S0-5 | Formal आप throughout; no Hinglish in the scripts. | Respectful default register; replies still match the user's language. |
| S0-6 | Open invitation in the person's own words, with "when you are ready". | Trauma-informed practice puts choice and control with the person [2]; S1 expects an open narrative. |
| S9-1 | The reference number is not read out; S9 points to My requests, where it is displayed. | Spoken codes fail on poor lines; the app already shows it. |
| S9-2 | "A human helpline officer will review it" — process only. | No outcome, timeline, arrest or compensation (prohibition lexicon `promise_outcome`). |
| S9-3 | No callback is implied. | The demo cannot place callbacks; updates appear under My requests. |
| S9-4 | One closing for every case, including abstention. | Wording must not reveal any assessment. |
| S9-5 | The closing repeats the right to a person. | Invariant 7. |
| SX-2 | Acknowledgement: "Thank you for telling me." | Listening without judgement and recognising that it took courage to speak [5]; no minimising language. |
| SX-3 | "I am connecting you to a person right now" (Hindi: passive, "you are being connected"), not "a person will speak with you". | True at the moment it is said: the system has requested takeover. The 988 policy centres active engagement and keeping the person connected [4]; the script makes no promise the demo cannot keep. |
| SX-4 | No helpline number is spoken. | `STATES.md`: SX says nothing else. A referral mid-crisis is a clinical decision. The tester briefing (`docs/DEPLOY_TESTERS.md`) lists Tele-MANAS 14416 [6] and 112 outside the app. |
| SX-5 | SX says nothing about what was detected. | No assessment reaches the victim (invariant 3). |
| SX-6 | After SX the session holds silently; the app shows the human controls. | SX does not return to intake. |
| SX-7 | Same script when crisis words are attributed to someone else. | The pre-check cannot tell reliably; the safer script is identical. Open for counsellor review. |
| SH-1 | One script for requested and escalated handoffs. | The person needs the same two facts either way. |
| SH-2 | Same script when consent was declined. | Nothing in it refers to AI analysis. |
| SH-3 | The takeover notice stays a separate app string (`human.joined`). | It is shown when the server reports a person has joined. |
| SH-4 | No wait time is stated. | The demo cannot guarantee one. "You do not have to repeat it" reflects the product goal of not retelling the account. |

## Sources

1. Press Information Bureau, Ministry of Social Justice and Empowerment — *National Helpline Against Atrocities on SCs/STs launched* (14566, docket number per complaint, status tracking). https://www.pib.gov.in/PressReleasePage.aspx?PRID=1780979
2. SAMHSA's six principles of a trauma-informed approach (safety; trustworthiness and transparency; peer support; collaboration and mutuality; empowerment, voice and choice; cultural, historical and gender issues). Summary: https://pmc.ncbi.nlm.nih.gov/articles/PMC9319668/
3. World Health Organization (2021) — *Ethics and governance of artificial intelligence for health* (protect autonomy; ensure transparency, explainability and intelligibility). https://iris.who.int/server/api/core/bitstreams/f780d926-4ae3-42ce-a6d6-e898a5562621/content
4. 988 Suicide and Crisis Lifeline — *Suicide Safety Policy* (active engagement; least invasive, most collaborative intervention; staying connected with the person until help is present). https://988lifeline.org/wp-content/uploads/2023/02/FINAL_988_Suicide_and_Crisis_Lifeline_Suicide_Safety_Policy_-3.pdf
5. Samaritans — *Listen without judgement*. https://www.samaritans.org/how-we-can-help/if-youre-worried-about-someone-else/how-to-interrupt-someones-suicidal-thoughts-guide/listen-without-judgement/
6. Press Information Bureau, Ministry of Health and Family Welfare — Tele-MANAS national tele-mental-health helpline 14416. https://www.pib.gov.in/PressReleasePage.aspx?PRID=2022057
