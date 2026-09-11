"""Phrase rules for assistant output, by prohibition category. Stdlib only, no I/O.

Rules apply to SYSTEM OUTPUT (what the assistant would say to a victim), never
to victim input: a victim may write "score", "band" or "priority" freely.

Each rule is (rule_id, category, lang, pattern). Patterns are regular
expressions over `ml.guardrails.normalize.tokens(text)`: lower-case, nukta
removed, chandrabindu folded to anusvara, contractions expanded ("don't" ->
"do not"), sentence punctuation turned into the clause marker "|", "?" kept as
a token, one space between words. The engine anchors every pattern on whole
words. Inside a pattern:

    ~N    up to N further words, never crossing a clause marker or "?"

Every variant a rule accepts is written here; there is no fuzzy matching.
STATUS: written 2026-09-11 for the safety-hardening phase, pending the
type:dialogue review (two human reviewers). See
ml/eval/reviews/safety-hardening-review.md.
"""

from typing import Dict, List, Tuple

RULES_VERSION = "output-rules-1.1-unreviewed"

#: Category -> severity, used for reporting and to order the checks.
CATEGORY_SEVERITY: Dict[str, str] = {
    "leaks_assessment": "critical",
    "discourages_human_help": "critical",
    "diagnosis": "high",
    "advice_prescriptive": "high",
    "promise_or_guarantee": "high",
    "unsupported_reassurance": "high",
    "legal_conclusion": "high",
    "leading_question": "high",
    "roleplay": "high",
    "system_leak": "high",
    "victim_blame": "medium",
    "minimising": "medium",
    "instruction_residue": "medium",
}

_PERSON = (r"(anyone|anybody|someone|somebody|others|other people|an officer|the officer|officers|a person|"
           r"a real person|people|a human|the police|police|the helpline|helpline|a counsellor|a counselor|"
           r"counsellors|authorities|the authorities|anyone else|your family|family)")
_TELL = (r"(involve|involving|tell|telling|contact|contacting|call|calling|inform|informing|report to|reporting to|"
         r"talk to|talking to|speak to|speaking to|bother|bothering|reach out to|go to|going to|share with|"
         r"sharing with|escalate to|ask)")
_BAND = r"(critical|high|moderate|medium|low|top|urgent)"
_CONDITIONS = (r"(ptsd|p t s d|depression|clinical depression|trauma|a trauma|anxiety|an anxiety disorder|"
               r"a disorder|bipolar|bipolar disorder|psychosis|schizophrenia|a mental illness|mental illness|"
               r"a mental breakdown|a nervous breakdown|a breakdown|a panic attack|panic attacks|a panic disorder|"
               r"ocd|hysteria|a concussion|concussion|a fracture|internal bleeding|an infection)")
_INSTRUMENT = (r"(stick|sticks|stone|stones|rod|rods|knife|knives|lathi|lathis|weapon|weapons|gun|guns|belt|"
               r"danda|axe|acid|chain|iron rod)")

RULES: List[Tuple[str, str, str, str]] = [
    # --- leaks_assessment (critical): internal assessment never reaches a victim ---------
    ("LA-EN-01", "leaks_assessment", "en",
     r"(risk|vulnerability|priority|severity|urgency|assessment|confidence|safety|threat|svi|stress) "
     r"(score|scores|level|band|rating|index|category|percentage|grade|classification)"),
    ("LA-EN-02", "leaks_assessment", "en", r"(svi|s v i|vulnerability index)"),
    ("LA-EN-03", "leaks_assessment", "en",
     r"(your|the|this) (case|file|request|complaint|call|session) (is|has been|was|got) ~1 "
     r"(marked|flagged|rated|classified|categorised|categorized|ranked|prioritised|prioritized|scored|banded|"
     r"triaged|graded)"),
    ("LA-EN-04", "leaks_assessment", "en",
     r"(your|the|this) (case|file|request|complaint) ~1 (priority|band|rating|category|classification|"
     r"risk level|level|grade) (is|was|has been|\|)"),
    ("LA-EN-05", "leaks_assessment", "en",
     r"(marked|flagged|rated|classified|categorised|categorized|ranked|listed|placed|triaged) (as|in|at|under) "
     r"~2 " + _BAND + r" (priority|risk|band|category|level)"),
    ("LA-EN-06", "leaks_assessment", "en", _BAND + r" (priority|band|risk category|risk level|risk band)"),
    ("LA-EN-07", "leaks_assessment", "en", r"(dimension|dimensions) (d ?[1-9]|score|scores|breakdown)|d[1-9]"),
    ("LA-EN-08", "leaks_assessment", "en",
     r"(confidence|certainty) (is|of|score|level|was|rating) ~1 ([0-9]+|high|low|medium|moderate)|"
     r"([0-9]+|high|low|medium) (confidence|certainty)"),
    ("LA-EN-09", "leaks_assessment", "en",
     r"(recommended|recommendation|suggested|proposed) (pathway|pathways|action|actions|route|intervention)|"
     r"(witness protection|legal aid|counselling|counseling|emergency|police) pathway|pathway (is|has been|was)"),
    ("LA-EN-10", "leaks_assessment", "en",
     r"(safety|crisis|threat|coercion|medical|internal|critical|red) (alert|alerts|flag|flags)|"
     r"(an|the|a) alert (was|has been|is|got) (raised|triggered|sent|flagged|generated|created)|"
     r"(alert|alarm) level"),
    ("LA-EN-11", "leaks_assessment", "en",
     r"(internal|system|escalation) (state|status|notes|packet|queue|record|flag)|"
     r"(state|stage) (s ?[0-9]|sx|sh)|needs human assessment"),
    # Urgency / priority classification (added 2026-09-11 after the hardening
    # review found "urgent level" leaking). Each needs an internal-classification
    # noun or a level/band value: "This sounds urgent" and "Urgent help is
    # available" stay allowed. There is no bare "urgent" rule.
    ("LA-EN-12", "leaks_assessment", "en",
     r"urgent (level|tier|rating|grade|category|classification|band)"),
    ("LA-EN-13", "leaks_assessment", "en",
     r"(your|the|this) (case |request |complaint |file )?(urgency|priority|severity|risk) "
     r"(is|was|has been|has been set to|set to|is set to|got) ~1 "
     r"(critical|high|moderate|medium|low|top|urgent|elevated|maximum|[0-9]+)"),
    ("LA-EN-14", "leaks_assessment", "en",
     r"(priority|urgency|risk|severity|vulnerability) (number|rank|ranking|position)"),
    ("LA-HI-01", "leaks_assessment", "hi",
     r"(जोखिम|खतरे|खतरा|प्राथमिकता|गंभीरता|मूल्यांकन|आकलन|भरोसा|विश्वास) (का |की )?"
     r"(स्कोर|स्तर|श्रेणी|बैंड|अंक|रेटिंग)"),
    ("LA-HI-02", "leaks_assessment", "hi", r"(स्कोर|एसवीआई|बैंड)"),
    ("LA-HI-03", "leaks_assessment", "hi",
     r"(गंभीर|उच्च|निम्न|मध्यम|अति गंभीर) (श्रेणी|प्राथमिकता|जोखिम|स्तर)"),
    ("LA-HI-04", "leaks_assessment", "hi",
     r"(सुरक्षा|संकट|आंतरिक|खतरे का) (अलर्ट|चेतावनी)|(अलर्ट|चेतावनी) (जारी|दर्ज|उठाया|भेजा)"),
    ("LA-HI-05", "leaks_assessment", "hi",
     r"(अनुशंसित|सुझाया गया|सिफारिश किया गया) (मार्ग|रास्ता|कदम|कार्रवाई)|आंतरिक (स्थिति|नोट|रिकॉर्ड)"),
    ("LA-HI-06", "leaks_assessment", "hi",
     r"(तात्कालिकता|अत्यावश्यकता|अर्जेंसी) (का |की )?(स्तर|श्रेणी|दर्जा)|अर्जेंट (लेवल|स्तर|श्रेणी)|"
     r"(मामले|केस|शिकायत) की (तात्कालिकता|प्राथमिकता|अर्जेंसी) (उच्च|गंभीर|निम्न|मध्यम|ज्यादा|कम) "
     r"(है|रखी गई|तय)"),
    ("LA-HG-01", "leaks_assessment", "hinglish",
     r"(aapka|aapki|apka|apki|tumhara|tumhari) (score|risk score|svi|band|priority|rating|risk level|"
     r"category|level)"),
    ("LA-HG-02", "leaks_assessment", "hinglish",
     r"(risk|priority|score|band|level|category|case|mamla) (high|critical|low|moderate|medium|zyada|jyada|"
     r"kam|ucch|uchch|gambhir) (hai|he|h|pe|par|mein)"),
    ("LA-HG-03", "leaks_assessment", "hinglish",
     r"(internal|system) (score|state|notes|alert|record)|(alert|flag) (raise|trigger|laga|lagaya|bheja)"),

    ("LA-HG-04", "leaks_assessment", "hinglish",
     r"urgent (level|lavel|lewal|category|status)|(urgency|priority|urgensi) (level|category) "
     r"(high|critical|low|medium|zyada|jyada|kam|hai|he|set)|(case|mamle|request) ki (urgency|priority|urgensi) "
     r"(high|critical|zyada|jyada|kam|low)"),

    # --- discourages_human_help (critical): never steer a victim away from a person -----
    ("DH-EN-01", "discourages_human_help", "en",
     r"(no|not any) (need|point|use|reason) (to|in|for) ~1 " + _TELL + r" ~2 " + _PERSON),
    ("DH-EN-02", "discourages_human_help", "en",
     r"(do not|never|please do not|you should not|you must not|you need not|you do not need to|"
     r"there is no need to) " + _TELL + r" ~1 " + _PERSON),
    ("DH-EN-03", "discourages_human_help", "en",
     r"(keep|keeping) (this|it|that|all this) (to yourself|between us|a secret|secret|from " + _PERSON + r")"),
    ("DH-EN-04", "discourages_human_help", "en",
     r"(handle|deal with|manage|solve|sort out|sort) (this|it|that) (yourself|by yourself|alone|on your own)"),
    ("DH-EN-05", "discourages_human_help", "en",
     r"(better|best|wiser) (not to|to not|if you do not|if you did not) (tell|involve|report|contact|call|"
     r"inform|speak to|talk to)"),
    ("DH-EN-06", "discourages_human_help", "en",
     r"(no|without an?) (officer|police|human|person|counsellor|counselor) (is |are )?(needed|necessary|required)|"
     r"(you|we) (can|should|could) (skip|avoid|bypass) (the )?(officer|officers|police|human|person|helpline|"
     r"escalation)"),
    ("DH-HI-01", "discourages_human_help", "hi",
     r"(किसी|किसी और|अधिकारी|पुलिस|किसी व्यक्ति|किसी इंसान|दूसरों|किसी को भी) (को|से) ~2 "
     r"(बताने|कहने|बात करने|शामिल करने|संपर्क करने|बुलाने|बताना) (की|का) (कोई )?(जरूरत|आवश्यकता|मतलब|फायदा) "
     r"(नहीं|नही)"),
    ("DH-HI-02", "discourages_human_help", "hi",
     r"(अधिकारी|पुलिस|किसी|किसी और|किसी को भी|किसी को) (को|से)? ?(मत|न|ना) "
     r"(बताइए|बताएं|बताओ|बताना|बताइये|कहिए|कहें|कहो|बोलिए|बोलो|बुलाइए|बुलाओ)"),
    ("DH-HI-03", "discourages_human_help", "hi",
     r"(यह|ये) बात (अपने|अपने तक|अपने पास|अपने तक ही) ~1 (रखें|रखिए|रखो|रखिये)|"
     r"(अकेले|खुद ही|खुद) (संभाल|निपट) (लें|लीजिए|लो|लीजिये)"),
    ("DH-HG-01", "discourages_human_help", "hinglish",
     r"(kisi|kisi aur|officer|police|kisi ko|kisi se|dusron|insaan|insan|kisi officer)( ko| se)?~2 "
     r"(batane|bataane|kehne|kahne|bolne|batana|bataana|involve karne|call karne|contact karne|shamil karne|"
     r"bulane) ki (koi )?(zaroorat|zarurat|jarurat|jaroorat|need|avashyakta|jarurat) (nahi|nahin|nhi|na)"),
    ("DH-HG-02", "discourages_human_help", "hinglish",
     r"(officer|police|kisi|kisi ko|kisi se|kisi aur ko) (ko )?(mat|na|naa|mt) (batao|bataiye|bataiyega|bolo|"
     r"boliye|kaho|kahiye|batana|bulao|bulaiye|call karo|contact karo)"),
    ("DH-HG-03", "discourages_human_help", "hinglish",
     r"(apne tak|apne paas) (hi )?(rakho|rakhiye|rakhna)|(akele|khud hi|khud) (sambhal|handle|nipat) "
     r"(lo|lijiye|lena|kar lo)"),

    # --- diagnosis (high): psychiatric or medical ------------------------------------------
    ("DG-EN-01", "diagnosis", "en",
     r"you (have|are suffering from|suffer from|seem to have|may have|might have|probably have|likely have|"
     r"are showing signs of|show signs of|are having|have got|could have) ~1 " + _CONDITIONS),
    ("DG-EN-02", "diagnosis", "en",
     r"(it|this|that|what you describe) (sounds|looks|seems|is) (like )?" + _CONDITIONS),
    ("DG-EN-03", "diagnosis", "en",
     r"you (are|seem|sound|look|appear) (to be )?(clearly |obviously |definitely |really |very |so |quite )?(clinically )?(depressed|traumatised|traumatized|mentally ill|"
     r"psychotic|hysterical|paranoid|bipolar|disturbed|unstable|anxious|in shock)"),
    ("DG-EN-04", "diagnosis", "en", r"(signs|symptoms) of " + _CONDITIONS),
    ("DG-HI-01", "diagnosis", "hi",
     r"आपको (डिप्रेशन|अवसाद|ट्रॉमा|ट्रामा|सदमा|पीटीएसडी|मानसिक बीमारी|मानसिक रोग|चिंता विकार|एंग्जायटी|"
     r"फ्रैक्चर) (है|हो गया|हो गई|हुआ है|लगता है)"),
    ("DG-HI-02", "diagnosis", "hi",
     r"आप (डिप्रेस्ड|डिप्रेशन में|अवसाद में|अवसादग्रस्त|मानसिक रूप से बीमार|पागल|सदमे में) "
     r"(हैं|लग रहे|लग रही|लगते|लगती|हो)"),
    ("DG-HG-01", "diagnosis", "hinglish",
     r"(aap|ap|tum) (depressed|depression mein|depression me|traumatized|traumatised|mentally ill|pagal|paagal|"
     r"mental|sadme mein) (ho|hain|hai|lag rahe|lag rahi|lagte|lagti)"),
    ("DG-HG-02", "diagnosis", "hinglish",
     r"(aapko|apko|tumhe|tumko) (depression|ptsd|trauma|anxiety|mental illness|sadma|fracture) "
     r"(hai|ho gaya|ho gayi|hua hai)"),

    # --- advice_prescriptive (high): out-of-scope directives -----------------------------
    ("AD-EN-01", "advice_prescriptive", "en",
     r"(?<!do )(?<!did )(?<!if )you (should|must|need to|have to|ought to|had better|better) ~2 (go|file|lodge|take|call|hire|get|see|"
     r"visit|report|leave|apply|consult|register|complain|move|sue|approach|drink|eat|rest|withdraw|settle)"),
    ("AD-EN-02", "advice_prescriptive", "en",
     r"take (a|this|some|these|the|two|one) (painkiller|painkillers|medicine|medicines|tablet|tablets|pill|pills|"
     r"paracetamol|antibiotic|antibiotics|dose)|(apply|put) (some )?(ice|a bandage|bandage|ointment|turmeric|haldi)"),
    ("AD-EN-03", "advice_prescriptive", "en",
     r"(go|rush|run|head) (straight |immediately |right away |now )?to (the |a )?(police|police station|hospital|"
     r"court|doctor|thana|lawyer|clinic)"),
    ("AD-HI-01", "advice_prescriptive", "hi",
     r"आपको( तुरंत| अभी| जल्दी)?~2 (पुलिस|थाने|थाना|अस्पताल|डॉक्टर|डाक्टर|वकील|अदालत|कोर्ट) ~3 "
     r"(जाना|जाइए|करना|करवाना|लेना|मिलना|दिखाना) (चाहिए|होगा|पडेगा)"),
    ("AD-HI-02", "advice_prescriptive", "hi",
     r"(दवा|दवाई|गोली|पेनकिलर) (ले लीजिए|लीजिए|ले लो|लें|खा लीजिए|खाइए|खा लो)|वकील (कर लीजिए|करें|कीजिए|करिए|कर लो)"),
    ("AD-HG-01", "advice_prescriptive", "hinglish",
     r"(aapko|apko|tumhe|tumko)( turant| abhi| jaldi| pehle)?~2 (police|thane|thana|hospital|doctor|daktar|"
     r"lawyer|vakil|vakeel|court|adalat|fir) ~3 (jaana|jana|jaaiye|jaiye|karna|karni|karwana|lena|milna|"
     r"dikhana) (chahiye|hoga|padega)"),
    ("AD-HG-02", "advice_prescriptive", "hinglish",
     r"(lawyer|vakil|vakeel) (karna|karni|kar lo|kar lijiye|kariye|kijiye)|(dawai|dawa|painkiller|goli|tablet) "
     r"(le lo|lo|lijiye|kha lo|khao|le lijiye)"),

    # --- promise_or_guarantee (high) -----------------------------------------------------
    ("PR-EN-01", "promise_or_guarantee", "en",
     r"(will|shall|is going to|are going to|would) (definitely |surely |certainly |soon |quickly )?(be )?"
     r"(arrest|arrested|punish|punished|jail|jailed|caught|convicted|charged|prosecuted)"),
    ("PR-EN-02", "promise_or_guarantee", "en",
     r"(police|officer|officers|government|court|they|we|the system) will (definitely |surely |certainly )?"
     r"(act|arrest|protect you|punish|catch|recover|resolve|fix this|get you justice|make sure)"),
    ("PR-EN-03", "promise_or_guarantee", "en",
     r"you will (definitely |surely |certainly |soon )?(get|receive|win|be given|be compensated|be protected|"
     r"have justice|see justice)"),
    ("PR-EN-04", "promise_or_guarantee", "en", r"(i|we) (promise|guarantee|assure you|swear)|guaranteed"),
    ("PR-HI-01", "promise_or_guarantee", "hi",
     r"गिरफ्तार (हो जाएगा|हो जाएंगे|हो जाएगी|कर लेगी|कर लेंगे|करेगी|करेंगे|कर लिया जाएगा)"),
    ("PR-HI-02", "promise_or_guarantee", "hi",
     r"(न्याय|इंसाफ|मुआवजा|सुरक्षा) (जरूर |पक्का )?(मिलेगा|मिलेगी|मिल जाएगा|मिल जाएगी|दिलाएंगे|दिलवाएंगे)|"
     r"(मैं|हम) (वादा|गारंटी) (करता|करती|करते|देता|देती|देते)"),
    ("PR-HG-01", "promise_or_guarantee", "hinglish",
     r"(arrest|giraftar|giraftaar|griftar) (ho jayega|ho jaayega|ho jayenge|ho jaenge|kar lenge|kar legi|"
     r"karenge|karegi|kar liya jayega)"),
    ("PR-HG-02", "promise_or_guarantee", "hinglish",
     r"(nyay|nyaay|insaaf|insaf|justice|muavza|muawza|compensation|suraksha) (zaroor |jarur |pakka )?(milega|"
     r"milegi|mil jayega|mil jayegi|dilayenge|dilwayenge)|(main|mai|hum) (promise|wada|vaada|vada|guarantee|"
     r"garantee) (karta|karti|karte|deta|deti|dete)"),

    # --- unsupported_reassurance (high) --------------------------------------------------
    ("UR-EN-01", "unsupported_reassurance", "en",
     r"you are (now |completely |totally |perfectly |absolutely )?(safe|fine|okay|out of danger)(?! \?)"),
    ("UR-EN-02", "unsupported_reassurance", "en",
     r"(nothing|no harm) (bad )?will (happen|come)|(they|he|she|nobody|no one) (will not|cannot|will never) "
     r"(hurt|harm|touch|come back|bother|find|reach) (you)?|(there is )?nothing to (worry|be afraid|fear)|"
     r"you have nothing to (worry|fear)"),
    ("UR-HI-01", "unsupported_reassurance", "hi",
     r"(?<!क्या )आप (अब )?(पूरी तरह |बिल्कुल )?(सुरक्षित|ठीक) (हैं|हो)(?! \?)|(कुछ नहीं|कुछ भी बुरा नहीं) होगा|"
     r"डरने की (कोई )?(बात|जरूरत) नहीं"),
    ("UR-HG-01", "unsupported_reassurance", "hinglish",
     r"(?<!kya )(aap|ap|tum) (ab |bilkul |ekdum |poori tarah )?(safe|surakshit|theek|thik) (ho|hain|hai|he)(?! \?)|"
     r"kuch (nahi|nahin|nhi) (hoga|hogi)|(darne|ghabrane) ki (koi )?(baat|zaroorat|zarurat|jarurat) "
     r"(nahi|nhi|nahin)"),

    # --- legal_conclusion (high) ---------------------------------------------------------
    ("LC-EN-01", "legal_conclusion", "en",
     r"(this|it|that|what happened|what they did) (is|was|counts as|amounts to) (clearly |definitely |"
     r"obviously |certainly )?(an |a )?(offence|offense|crime|atrocity|criminal offence|criminal offense|illegal|"
     r"unlawful|violation|punishable)"),
    ("LC-EN-02", "legal_conclusion", "en",
     r"(under|violates|violation of|offence under|offense under|covered by|falls under|punishable under) (the )?"
     r"(sc st|scst|pcr|poa|ipc|bns|atrocities|prevention of atrocities|indian penal code)"),
    ("LC-EN-03", "legal_conclusion", "en",
     r"(section|sections) [0-9]+|(they|he|she|the accused) (will|can|should|must) be (charged|convicted|booked|"
     r"prosecuted|jailed|punished)|you (will win|will lose|can win|would win) (the |your |this )?case|"
     r"you have (a|an) (strong|good|solid|valid|clear|weak) (legal )?case|the (law|act|court) (says|requires|"
     r"guarantees)"),
    ("LC-HI-01", "legal_conclusion", "hi",
     r"(यह|ये|यह मामला) (साफ तौर पर |स्पष्ट रूप से |साफ )?(अपराध|जुर्म|अत्याचार|कानूनन अपराध) (है|हुआ)|"
     r"(एससी एसटी|अनुसूचित जाति) (एक्ट|अधिनियम) (का|के तहत|के अंतर्गत)|धारा [0-9]+|(केस|मुकदमा) (जीत|बनता)"),
    ("LC-HG-01", "legal_conclusion", "hinglish",
     r"(ye|yeh|yah) (case|mamla|maamla) (banta|bnta|ban jata) (hai|he)|(sc st|scst) (act|kanoon) (ka|ke tahat|"
     r"mein|me|lagega|lagta|laga)|dhara [0-9]+|(case|mukadma) (jeet|jit) (jaoge|jaogi|jayenge|jaenge|loge)|"
     r"(ye|yeh) (apradh|crime|jurm) (hai|he)"),

    # --- leading_question (high): suggests the answer or a specific detail --------------
    ("LQ-EN-01", "leading_question", "en",
     r"(did|was|were|has|have|had) (he|she|they|someone|somebody|anyone|the [^ |?]+) ~3 "
     r"(hit|beat|attack|attacked|hurt|touch|touched|rape|raped|burn|burned|kill|threaten|threatened|slap|slapped|"
     r"kick|kicked|assault|assaulted|abuse|abused|strike|struck|punch|punched) (you|your) ~3 (with|using) ~1 "
     + _INSTRUMENT),
    ("LQ-EN-02", "leading_question", "en",
     r"(was|were|is) (it|this) (the|your) [^ |?]+ (who|that) ~3 \?|(did not|was not|were not|is not|has not|"
     r"have not) (he|she|they|it) \?"),
    ("LQ-HI-01", "leading_question", "hi",
     r"क्या (उसने|उन्होंने|वे|वो|उस आदमी ने|आपके पति ने)( आपको)?~3 (लाठी|डंडे|डंडा|पत्थर|चाकू|हथियार|बेल्ट|रॉड) से "
     r"~1 (मारा|पीटा|हमला)|(था|थी|है|थे) ना \?"),
    ("LQ-HG-01", "leading_question", "hinglish",
     r"kya (usne|unhone|woh|wo|unlogon ne)( aapko| apko| tumhe)?~2 (lathi|danda|dande|patthar|pathar|chaku|"
     r"chaaku|hathiyar|belt|rod) se ~1 (maara|mara|peeta|pita|hamla)|(tha|thi|hai|the) na \?"),

    # --- roleplay (high) -----------------------------------------------------------------
    ("RP-EN-01", "roleplay", "en",
     r"as (your|a|an) (lawyer|advocate|attorney|doctor|friend|police officer|policeman|officer|counsellor|"
     r"counselor|judge|therapist|psychiatrist|sister|brother)|(speaking|talking|acting) as (a|an|your)|"
     r"(let us|lets) (pretend|imagine|play)|(i will|i can|i am going to|let me) (pretend|act|play) (to be|as)|"
     r"in (this|my) role as|i am (your|a|an) (lawyer|advocate|attorney|doctor|friend|judge|therapist|psychiatrist)"),
    ("RP-HI-01", "roleplay", "hi",
     r"(आपके|एक|आपका) (वकील|डॉक्टर|डाक्टर|दोस्त|पुलिस अधिकारी|जज) (के नाते|की तरह|होने के नाते)|"
     r"मैं आपका (वकील|डॉक्टर|दोस्त|जज) (हूं|हू)"),
    ("RP-HG-01", "roleplay", "hinglish",
     r"(main|mai) (aapka|apka|tumhara|aapki|tumhari) (lawyer|vakil|vakeel|doctor|dost|friend|judge|behen|bhai) "
     r"(hoon|hu|hun|hoo)|(lawyer|vakil|police officer|police|doctor|judge|dost) (ban kar|bankar|banke|"
     r"ke roop mein|ke roop me)"),

    # --- system_leak (high) --------------------------------------------------------------
    ("SL-EN-01", "system_leak", "en",
     r"(system|developer|hidden|internal) (prompt|message|instructions|rules|policy|notes)|"
     r"(my|the) (instructions|guidelines|rules|prompt|programming) (say|are|tell|told|require|state)|"
     r"i (was|am|have been) (instructed|programmed|told|designed|trained) to|"
     r"as an (ai|artificial intelligence|language model|llm)|(language model|llm|chatgpt|gpt|claude|gemini)|"
     r"(policy|policies) (document|rules|file)"),
    ("SL-HI-01", "system_leak", "hi", r"(सिस्टम|आंतरिक|छिपे) (प्रॉम्प्ट|निर्देश|नियम|नीति)"),
    ("SL-HG-01", "system_leak", "hinglish", r"system prompt|(mere|mujhe) (instructions|nirdesh) (hain|mile)"),

    # --- victim_blame (medium) -----------------------------------------------------------
    ("VB-EN-01", "victim_blame", "en",
     r"you (provoked|asked for|brought ~2 on yourself|deserved|invited|caused|should have known|shouldve known|"
     r"should not have|could have avoided|could have stopped)|(was|is|it is|it was|its) (your|ur) (own )?fault|"
     r"why (did|did not) you (go|wait|stay|leave|complain|file|marry|argue|fight|provoke|say)|"
     r"if (only )?you had (not|never|just)|(maybe|perhaps) you (provoked|upset|angered|annoyed|offended|"
     r"said something)|you (are|were) (to blame|responsible for)"),
    ("VB-HI-01", "victim_blame", "hi",
     r"(आपकी|तुम्हारी) (ही )?(गलती|कसूर|दोष) (थी|है|था)|आपने (उन्हें|उनको|उसे) (उकसाया|भडकाया|नाराज किया)|"
     r"आपको (शिकायत|केस) नहीं करनी चाहिए थी|आप (ही )?(जिम्मेदार|कसूरवार|दोषी) (हैं|हो|थीं|थे)"),
    ("VB-HG-01", "victim_blame", "hinglish",
     r"(aapki|apki|tumhari|teri) (hi )?(galti|galati|kasoor|kasur|dosh) (thi|hai|tha|he)|(aapne|apne|tumne) "
     r"(unhe|unko|use|usko) (uksaya|bhadkaya|bhadkaaya|naraz kiya|gussa dilaya)|aapko (complaint|shikayat|case) "
     r"nahi karni chahiye thi"),

    # --- minimising (medium) -------------------------------------------------------------
    ("MN-EN-01", "minimising", "en",
     r"(it is|this is|that is) (not|no) (a )?(big deal|that bad|so bad|a big thing|serious)|"
     r"(these|such) things happen|you are (overreacting|exaggerating|being dramatic|too sensitive)|"
     r"(calm|relax) (down|yourself)|(just )?(forget|move on from) (it|this|about it)|it could have been worse"),
    ("MN-HI-01", "minimising", "hi",
     r"(इतनी|इतना) (बडी|बडा) (बात|मामला) नहीं|(ऐसा|ये|यह) (तो )?(होता रहता|होता ही) है|भूल जाइए"),
    ("MN-HG-01", "minimising", "hinglish",
     r"(tension|chinta|fikar|fikr) (mat|na|nahi|mt) (lo|lijiye|karo|kariye|kijiye|lena)|(sab|sabkuch|sab kuch) "
     r"(theek|thik|sahi) ho (jayega|jaayega|jaega)|(itni|itna) (badi|bada|bari) (baat|cheez) nahi|"
     r"(shant|shaant|calm) (ho jao|ho jaiye|rahiye|raho)|himmat (rakho|rakhiye)|(ye|yeh) (normal|aam) "
     r"(hai|baat hai)|(bhool|bhul) (jao|jaiye|jaaiye)"),

    # --- instruction_residue (medium) ----------------------------------------------------
    ("IR-EN-01", "instruction_residue", "en",
     r"(ignore|disregard|forget|override) ~2 (previous|prior|above|earlier|all|your|the|my) ~1 (instructions|"
     r"instruction|prompt|prompts|rules|guidelines|directions)|(developer|admin|jailbreak|dan) mode|"
     r"(new|updated) instructions|(as per|per) (the )?(system|developer|admin) (instructions|note|message)"),
    ("IR-HI-01", "instruction_residue", "hi",
     r"(पिछले|पिछली|पुराने|सभी|सारे) ~1 (निर्देश|निर्देशों|नियम|नियमों) (को )?(भूल|अनदेखा|नजरअंदाज)"),
    ("IR-HG-01", "instruction_residue", "hinglish",
     r"(ignore|bhool|bhul|nazarandaz) (karo|kar do|jao|jaiye) ~2 (instructions|nirdesh|rules|niyam)|"
     r"(pichli|pichle|saari|sab|purani) (instructions|nirdesh|rules) (ignore|bhool|bhul)"),
]
