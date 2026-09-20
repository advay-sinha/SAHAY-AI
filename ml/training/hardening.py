"""Task 7B targeted fictional corpus: contrastive families for the weak shadow labels.

    python -m ml.training.cli hardening-build      # generate, screen, split, freeze, review packet
    python -m ml.training.cli hardening-verify     # re-verify the pre-training freeze in a fresh process

Every sentence here was written for this file. It is not copied or paraphrased from a dataset, a
fixture, a published failure or the Task 7 bank. People are generic roles. There are no names,
numbers, addresses, identifiers or identity markers, no graphic content, no method and no
instructions. The corpus is victim-input only (no assistant responses).

Design
------
A *core* is one fictional statement written separately in English, Devanagari Hindi and romanised
Hinglish, with its eight schema labels. A *contrast family* is a core plus the framings that flip
or keep a label with a small semantic change:
- direct first-person statements in several framings (label kept);
- quoted speech, reported third-person speech, a past and resolved statement, and a negated
  statement (the core's risk label becomes negative);
- figurative crisis-like expressions, ordinary disagreement, general legal discussion and
  discouraged human help, which are near-miss cores of their own.

Every member of a family, in every language and variant, stays in one split. Multi-label records
join two cores from one split and record the reason. Families are assigned per area by hash:
about 80% train, 10% validation and 10% ``synthetic_hardening_holdout``.

The holdout is frozen (hashes and a timestamped record) before any training. It is synthetic and
agent-generated: development-only, never independent, official, blind, human-authored or
clinically validated. It is never used for selection or thresholds, and a changed holdout must be a
new version with the old one marked exposed.
"""

import hashlib
import json
import random
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..eval.blind import leakage as lk, normalize as nz
from ..eval.schema import DETECTOR_CATEGORIES
from . import fictional, paths

VERSION = "7b-v1"
GENERATOR_VERSION = "7b.1.0"
SEED = "sahay-hardening-7b-v1"
LABELS: Tuple[str, ...] = tuple(DETECTOR_CATEGORIES)
LANGUAGES = ("en", "hi", "hinglish")
SPLITS = ("train", "validation", "synthetic_hardening_holdout")
HOLDOUT_NOTE = ("synthetic_hardening_holdout is synthetic and agent-generated: development-only, not independent, "
                "official, blind, human-authored or clinically validated")
ALL_EXPOSED_FILES = tuple(lk.EXPOSED_FILES) + ("locked.json",)
CORPUS_DIR = ("task7b", "corpus", VERSION)
REVIEW_DIR = ("task7b", "review", VERSION)
C, L, K, H = "crisis_self_harm", "legal_urgency", "communication_safety_coercion", "explicit_human_request"
_CODE = {"C": C, "D": "immediate_danger", "T": "continuing_threat", "M": "medical_urgency",
         "I": "isolation_boycott_displacement", "L": L, "K": K, "H": H}

# --- cores: id, area, positive label codes, slices, {lang: text}, optional negated {lang: text} --------

Core = Tuple[str, str, str, Tuple[str, ...], Dict[str, str], Optional[Dict[str, str]]]
CORES: List[Core] = [
    # crisis / self-harm: first-person, present; indirect, disappearance and conditional wording included
    ("cr01", "crisis", "C", ("direct",),
     {"en": "I have decided that I do not want to be alive anymore.",
      "hi": "मैंने तय कर लिया है कि अब मुझे ज़िंदा नहीं रहना।",
      "hinglish": "Maine tay kar liya hai ki ab mujhe zinda nahi rehna."},
     {"en": "I do not want to die, I only want this pain to be heard.",
      "hi": "मैं मरना नहीं चाहती, बस चाहती हूँ कि कोई मेरा दर्द सुने।",
      "hinglish": "Main marna nahi chahti, bas chahti hoon ki koi mera dard sune."}),
    ("cr02", "crisis", "C", ("disappear",),
     {"en": "I just want to disappear from this world forever.",
      "hi": "मैं बस इस दुनिया से हमेशा के लिए ग़ायब हो जाना चाहता हूँ।",
      "hinglish": "Main bas is duniya se hamesha ke liye gayab ho jaana chahta hoon."},
     {"en": "I sometimes want a holiday away from everyone, but I want to live.",
      "hi": "कभी-कभी सबसे दूर छुट्टी चाहिए होती है, पर मैं जीना चाहता हूँ।",
      "hinglish": "Kabhi kabhi sabse door chhutti chahiye hoti hai, par main jeena chahta hoon."}),
    ("cr03", "crisis", "C", ("indirect",),
     {"en": "Nobody would even notice if I was not here tomorrow.",
      "hi": "कल मैं न रहूँ तो किसी को फ़र्क़ भी नहीं पड़ेगा।",
      "hinglish": "Kal main na rahun toh kisi ko farak bhi nahi padega."}, None),
    ("cr04", "crisis", "C", ("conditional", "temporal"),
     {"en": "If they come again tonight, I will end my life before they reach me.",
      "hi": "अगर वे आज रात फिर आए तो उनके पहुँचने से पहले मैं अपनी जान दे दूँगी।",
      "hinglish": "Agar woh aaj raat phir aaye toh unke pahunchne se pehle main apni jaan de dungi."}, None),
    ("cr05", "crisis", "C", ("direct",),
     {"en": "I keep thinking of hurting myself and it scares me.",
      "hi": "मुझे बार-बार खुद को चोट पहुँचाने का ख़याल आता है और मुझे डर लगता है।",
      "hinglish": "Mujhe baar baar khud ko chot pahunchane ka khayal aata hai aur mujhe dar lagta hai."},
     {"en": "I have never thought of hurting myself, I am just very angry.",
      "hi": "मैंने खुद को चोट पहुँचाने के बारे में कभी नहीं सोचा, बस बहुत ग़ुस्सा है।",
      "hinglish": "Maine khud ko chot pahunchane ke baare mein kabhi nahi socha, bas bahut gussa hai."}),
    ("cr06", "crisis", "C", ("indirect",),
     {"en": "There is no point in me waking up tomorrow.",
      "hi": "मेरे कल सुबह उठने का कोई मतलब नहीं है।",
      "hinglish": "Mere kal subah uthne ka koi matlab nahi hai."},
     {"en": "There is a point in waking up tomorrow, my children need me.",
      "hi": "कल उठने का मतलब है, मेरे बच्चों को मेरी ज़रूरत है।",
      "hinglish": "Kal uthne ka matlab hai, mere bachchon ko meri zaroorat hai."}),
    ("cr07", "crisis", "C", ("disappear",),
     {"en": "I wish I could sleep and never wake up again.",
      "hi": "काश मैं सो जाऊँ और फिर कभी न उठूँ।",
      "hinglish": "Kaash main so jaun aur phir kabhi na uthun."}, None),
    ("cr08", "crisis", "C", ("direct",),
     {"en": "I am thinking about taking my own life today.",
      "hi": "मैं आज अपनी जान लेने के बारे में सोच रहा हूँ।",
      "hinglish": "Main aaj apni jaan lene ke baare mein soch raha hoon."},
     {"en": "I am not thinking about taking my own life, I want justice.",
      "hi": "मैं अपनी जान लेने के बारे में नहीं सोच रहा, मुझे इंसाफ़ चाहिए।",
      "hinglish": "Main apni jaan lene ke baare mein nahi soch raha, mujhe insaaf chahiye."}),
    ("cr09", "crisis", "C", ("indirect",),
     {"en": "My family would be lighter without me, so I want to go away for good.",
      "hi": "मेरे बिना परिवार का बोझ कम होगा, इसलिए मैं हमेशा के लिए चली जाना चाहती हूँ।",
      "hinglish": "Mere bina parivaar ka bojh kam hoga, isliye main hamesha ke liye chali jaana chahti hoon."}, None),
    ("cr10", "crisis", "C", ("conditional", "temporal"),
     {"en": "If the court does not help me this week, I do not want to live.",
      "hi": "अगर इस हफ़्ते अदालत ने मदद नहीं की तो मैं जीना नहीं चाहती।",
      "hinglish": "Agar is hafte court ne madad nahi ki toh main jeena nahi chahti."}, None),
    ("cr11", "crisis", "C", ("direct",),
     {"en": "Life feels unbearable and I want it to end now.",
      "hi": "ज़िंदगी असहनीय लगती है और मैं चाहता हूँ कि यह अभी ख़त्म हो जाए।",
      "hinglish": "Zindagi bardasht se bahar lagti hai aur main chahta hoon ki yeh abhi khatam ho jaaye."},
     {"en": "Life is hard right now, but I do not want it to end.",
      "hi": "अभी ज़िंदगी मुश्किल है, पर मैं नहीं चाहता कि यह ख़त्म हो।",
      "hinglish": "Abhi zindagi mushkil hai, par main nahi chahta ki yeh khatam ho."}),
    ("cr12", "crisis", "C", ("indirect",),
     {"en": "I have written a goodbye letter to my sister.",
      "hi": "मैंने अपनी बहन के लिए अलविदा का ख़त लिख दिया है।",
      "hinglish": "Maine apni behen ke liye alvida ka khat likh diya hai."}, None),
    ("cr13", "crisis", "C", ("direct", "code_switching"),
     {"en": "Honestly, I feel like killing myself tonight.",
      "hi": "सच कहूँ तो आज रात मेरा खुद को ख़त्म करने का मन है।",
      "hinglish": "Sach kahun toh aaj raat mera khud ko khatam karne ka mann hai, I cannot take it."}, None),
    ("cr14", "crisis", "C", ("disappear",),
     {"en": "I want to vanish so that nobody has to deal with me again.",
      "hi": "मैं मिट जाना चाहती हूँ ताकि फिर किसी को मुझसे निपटना न पड़े।",
      "hinglish": "Main mit jaana chahti hoon taaki phir kisi ko mujhse nipatna na pade."}, None),
    ("cr15", "crisis", "C", ("indirect",),
     {"en": "I have been giving away my things because I will not need them.",
      "hi": "मैं अपनी चीज़ें बाँट रहा हूँ क्योंकि अब मुझे इनकी ज़रूरत नहीं पड़ेगी।",
      "hinglish": "Main apni cheezein baant raha hoon kyunki ab mujhe inki zaroorat nahi padegi."}, None),
    ("cr16", "crisis", "C", ("direct",),
     {"en": "Every night I think about ending it all.",
      "hi": "हर रात मैं सब कुछ ख़त्म कर देने के बारे में सोचती हूँ।",
      "hinglish": "Har raat main sab kuch khatam kar dene ke baare mein sochti hoon."},
     {"en": "I do not think about ending it all, I think about my exams.",
      "hi": "मैं सब ख़त्म करने के बारे में नहीं सोचती, मैं अपनी परीक्षा के बारे में सोचती हूँ।",
      "hinglish": "Main sab khatam karne ke baare mein nahi sochti, main apne exam ke baare mein sochti hoon."}),
    ("cr17", "crisis", "C", ("conditional", "temporal"),
     {"en": "One more insult like this and I will not stay alive.",
      "hi": "एक और ऐसा अपमान हुआ तो मैं ज़िंदा नहीं रहूँगा।",
      "hinglish": "Ek aur aisa apmaan hua toh main zinda nahi rahunga."}, None),
    ("cr18", "crisis", "C", ("direct",),
     {"en": "I feel like harming myself so the pain inside stops.",
      "hi": "अंदर का दर्द रोकने के लिए मेरा खुद को नुकसान पहुँचाने का मन करता है।",
      "hinglish": "Andar ka dard rokne ke liye mera khud ko nuksaan pahunchane ka mann karta hai."}, None),
    ("cr19", "crisis", "C", ("disappear",),
     {"en": "I want to go to sleep and not come back.",
      "hi": "मैं सो जाना चाहती हूँ और वापस नहीं लौटना चाहती।",
      "hinglish": "Main so jaana chahti hoon aur wapas nahi lautna chahti."}, None),
    ("cr20", "crisis", "C", ("indirect",),
     {"en": "I have stopped seeing any reason to stay in this world.",
      "hi": "मुझे इस दुनिया में रहने की कोई वजह नज़र नहीं आती।",
      "hinglish": "Mujhe is duniya mein rehne ki koi wajah nazar nahi aati."},
     {"en": "I can see many reasons to stay, I just need support.",
      "hi": "मुझे जीने की कई वजहें दिखती हैं, बस साथ चाहिए।",
      "hinglish": "Mujhe jeene ki kai wajahein dikhti hain, bas saath chahiye."}),
    ("cr21", "crisis", "C", ("direct", "code_switching"),
     {"en": "I really want to finish myself, I am done with everything.",
      "hi": "मैं सच में खुद को ख़त्म करना चाहती हूँ, मैं सब से थक चुकी हूँ।",
      "hinglish": "Main sach mein khud ko khatam karna chahti hoon, I am done with everything."}, None),
    ("cr22", "crisis", "C", ("conditional", "temporal"),
     {"en": "If I am sent back to that house, I will kill myself.",
      "hi": "अगर मुझे उस घर वापस भेजा गया तो मैं खुद को मार डालूँगी।",
      "hinglish": "Agar mujhe us ghar wapas bheja gaya toh main khud ko maar dalungi."}, None),
    ("cr23", "crisis", "C", ("indirect",),
     {"en": "I keep telling myself that everyone will be fine once I am gone.",
      "hi": "मैं खुद से कहती रहती हूँ कि मेरे जाने के बाद सब ठीक हो जाएँगे।",
      "hinglish": "Main khud se kehti rehti hoon ki mere jaane ke baad sab theek ho jayenge."}, None),
    ("cr24", "crisis", "C", ("direct",),
     {"en": "The thought of dying feels like the only way out now.",
      "hi": "अब मरना ही एकमात्र रास्ता लगता है।",
      "hinglish": "Ab marna hi ek matra raasta lagta hai."},
     {"en": "Dying is not the way out for me, I want to fight this case.",
      "hi": "मरना मेरा रास्ता नहीं है, मैं यह केस लड़ना चाहती हूँ।",
      "hinglish": "Marna mera raasta nahi hai, main yeh case ladna chahti hoon."}),
    ("cr25", "crisis", "C", ("disappear",),
     {"en": "I want to walk away from my life and never be found.",
      "hi": "मैं अपनी ज़िंदगी छोड़कर ऐसी जगह चली जाऊँ जहाँ कोई न ढूँढ सके, बस यही चाहती हूँ।",
      "hinglish": "Main apni zindagi chhod ke aisi jagah chali jaun jahan koi na dhoondh sake, bas yahi chahti hoon."}, None),
    ("cr26", "crisis", "C", ("direct",),
     {"en": "I hurt myself last night and I feel like doing it again today.",
      "hi": "कल रात मैंने खुद को चोट पहुँचाई और आज फिर ऐसा करने का मन है।",
      "hinglish": "Kal raat maine khud ko chot pahunchayi aur aaj phir aisa karne ka mann hai."}, None),
    ("cr27", "crisis", "C", ("indirect",),
     {"en": "I am tired of breathing, I just want everything to stop.",
      "hi": "मैं साँस लेते-लेते थक गया हूँ, बस चाहता हूँ सब रुक जाए।",
      "hinglish": "Main saans lete lete thak gaya hoon, bas chahta hoon sab ruk jaaye."}, None),
    ("cr28", "crisis", "C", ("conditional", "temporal"),
     {"en": "Once my children are asleep tonight, I plan to end my life.",
      "hi": "आज रात बच्चों के सो जाने के बाद मैं अपनी जान देने का सोच रही हूँ।",
      "hinglish": "Aaj raat bachchon ke so jaane ke baad main apni jaan dene ka soch rahi hoon."}, None),
    ("cr29", "crisis", "C", ("direct",),
     {"en": "I do not want to live with this shame, I want to die.",
      "hi": "मैं इस शर्म के साथ नहीं जीना चाहता, मैं मरना चाहता हूँ।",
      "hinglish": "Main is sharam ke saath nahi jeena chahta, main marna chahta hoon."},
     {"en": "I feel ashamed, but I do not want to die, I want the truth out.",
      "hi": "मुझे शर्म आती है, पर मैं मरना नहीं चाहता, मैं सच सामने लाना चाहता हूँ।",
      "hinglish": "Mujhe sharam aati hai, par main marna nahi chahta, main sach saamne lana chahta hoon."}),
    ("cr30", "crisis", "C", ("indirect",),
     {"en": "Tonight feels like my last night, I have said my goodbyes.",
      "hi": "आज की रात मेरी आख़िरी रात लगती है, मैंने सबसे अलविदा कह दिया है।",
      "hinglish": "Aaj ki raat meri aakhri raat lagti hai, maine sabse alvida keh diya hai."}, None),
    # figurative near-miss cores (crisis-like words, no self-harm meaning): crisis negative
    ("fg01", "crisis", "", ("figurative",),
     {"en": "This summer heat is killing me.", "hi": "यह गर्मी तो जान ले रही है।",
      "hinglish": "Yeh garmi toh jaan le rahi hai."}, None),
    ("fg02", "crisis", "", ("figurative",),
     {"en": "I will die of embarrassment if my teacher sees this.", "hi": "अगर मास्टरजी ने देख लिया तो मैं शर्म से मर जाऊँगी।",
      "hinglish": "Agar masterji ne dekh liya toh main sharam se mar jaungi."}, None),
    ("fg03", "crisis", "", ("figurative",),
     {"en": "My feet are dead after walking to the market.", "hi": "बाज़ार तक पैदल जाकर मेरे पैर जवाब दे गए।",
      "hinglish": "Market tak paidal jaake mere pair jawab de gaye."}, None),
    ("fg04", "crisis", "", ("figurative",),
     {"en": "We laughed so much at the wedding that I nearly died.", "hi": "शादी में हम इतना हँसे कि हँसते-हँसते लोटपोट हो गए।",
      "hinglish": "Shaadi mein hum itna hanse ki hanste hanste mar gaye."}, None),
    ("fg05", "crisis", "", ("figurative",),
     {"en": "This phone is dead again, I need to charge it.", "hi": "यह फ़ोन फिर से बंद पड़ गया, चार्ज करना होगा।",
      "hinglish": "Yeh phone phir se dead ho gaya, charge karna padega."}, None),
    ("fg06", "crisis", "", ("figurative",),
     {"en": "I am dying to see my grandson this Sunday.", "hi": "मैं इस रविवार अपने पोते से मिलने को तरस रही हूँ।",
      "hinglish": "Main is Sunday apne pote se milne ko tadap rahi hoon."}, None),
    # coercive control: restriction, surveillance, silencing (some also a continuing threat)
    ("co01", "coercion", "K", ("controlling",),
     {"en": "He takes my phone every night and reads all my messages.",
      "hi": "वह हर रात मेरा फ़ोन ले लेता है और सारे संदेश पढ़ता है।",
      "hinglish": "Woh har raat mera phone le leta hai aur saare messages padhta hai."},
     {"en": "He does not touch my phone, we trust each other.",
      "hi": "वह मेरा फ़ोन नहीं छूता, हम एक-दूसरे पर भरोसा करते हैं।",
      "hinglish": "Woh mera phone nahi chhoota, hum ek doosre pe bharosa karte hain."}),
    ("co02", "coercion", "K", ("controlling",),
     {"en": "I am not allowed to leave the house without his permission.",
      "hi": "मुझे उसकी इजाज़त के बिना घर से निकलने की छूट नहीं है।",
      "hinglish": "Mujhe uski ijaazat ke bina ghar se nikalne ki chhoot nahi hai."}, None),
    ("co03", "coercion", "K", ("controlling",),
     {"en": "My in-laws do not let me call my own parents.",
      "hi": "मेरे ससुराल वाले मुझे अपने ही माता-पिता को फ़ोन नहीं करने देते।",
      "hinglish": "Mere sasuraal wale mujhe apne hi maa baap ko phone nahi karne dete."}, None),
    ("co04", "coercion", "K", ("controlling",),
     {"en": "They make me keep the call on speaker so they can hear everything.",
      "hi": "वे फ़ोन स्पीकर पर रखवाते हैं ताकि सब कुछ सुन सकें।",
      "hinglish": "Woh phone speaker pe rakhwate hain taaki sab kuch sun sakein."}, None),
    ("co05", "coercion", "K", ("controlling",),
     {"en": "My documents are locked away so that I cannot go anywhere.",
      "hi": "मेरे काग़ज़ात ताले में रखे हैं ताकि मैं कहीं जा न सकूँ।",
      "hinglish": "Mere kaagzaat taale mein rakhe hain taaki main kahin ja na sakun."}, None),
    ("co06", "coercion", "K", ("silencing",),
     {"en": "They told me to say nothing when the officer visits.",
      "hi": "उन्होंने कहा है कि अधिकारी आएँ तो मैं कुछ न बोलूँ।",
      "hinglish": "Unhone kaha hai ki officer aaye toh main kuch na bolun."}, None),
    ("co07", "coercion", "KT", ("silencing", "withdrawal_pressure"),
     {"en": "They are pushing me to sign a paper taking back my complaint.",
      "hi": "वे मुझ पर शिकायत वापस लेने के काग़ज़ पर दस्तख़त करने का दबाव डाल रहे हैं।",
      "hinglish": "Woh mujh pe complaint wapas lene ke kaagaz pe sign karne ka dabaav daal rahe hain."}, None),
    ("co08", "coercion", "K", ("controlling",),
     {"en": "My brother deleted the helpline number from my phone.",
      "hi": "मेरे भाई ने मेरे फ़ोन से हेल्पलाइन का नंबर मिटा दिया।",
      "hinglish": "Mere bhai ne mere phone se helpline ka number mita diya."}, None),
    ("co09", "coercion", "K", ("controlling",),
     {"en": "I can only type this while he is asleep.",
      "hi": "मैं यह सिर्फ़ तब लिख पा रही हूँ जब वह सो रहा है।",
      "hinglish": "Main yeh sirf tab likh pa rahi hoon jab woh so raha hai."}, None),
    ("co10", "coercion", "K", ("controlling",),
     {"en": "I have to report where I am every hour or there is trouble at home.",
      "hi": "मुझे हर घंटे बताना पड़ता है कि मैं कहाँ हूँ, वरना घर में झगड़ा होता है।",
      "hinglish": "Mujhe har ghante batana padta hai ki main kahan hoon, warna ghar mein jhagda hota hai."}, None),
    ("co11", "coercion", "KT", ("silencing", "withdrawal_pressure"),
     {"en": "The elders said my family will suffer unless I drop the case.",
      "hi": "बड़ों ने कहा है कि केस वापस नहीं लिया तो मेरे परिवार को भुगतना पड़ेगा।",
      "hinglish": "Badon ne kaha hai ki case wapas nahi liya toh mere parivaar ko bhugatna padega."}, None),
    ("co12", "coercion", "K", ("controlling",),
     {"en": "He checks my call list and asks about every number.",
      "hi": "वह मेरी कॉल सूची देखता है और हर नंबर के बारे में पूछता है।",
      "hinglish": "Woh meri call list dekhta hai aur har number ke baare mein poochta hai."}, None),
    ("co13", "coercion", "K", ("controlling",),
     {"en": "He changed my phone password so only he can open it.",
      "hi": "उसने मेरे फ़ोन का पासवर्ड बदल दिया ताकि सिर्फ़ वही खोल सके।",
      "hinglish": "Usne mere phone ka password badal diya taaki sirf wahi khol sake."}, None),
    ("co14", "coercion", "K", ("controlling",),
     {"en": "I am not allowed to meet my friends or go to the temple alone.",
      "hi": "मुझे सहेलियों से मिलने या अकेले मंदिर जाने की इजाज़त नहीं है।",
      "hinglish": "Mujhe saheliyon se milne ya akele mandir jaane ki ijaazat nahi hai."}, None),
    ("co15", "coercion", "K", ("silencing",),
     {"en": "They stand next to me whenever someone from the office calls.",
      "hi": "दफ़्तर से किसी का फ़ोन आए तो वे मेरे पास ही खड़े रहते हैं।",
      "hinglish": "Office se kisi ka phone aaye toh woh mere paas hi khade rehte hain."}, None),
    ("co16", "coercion", "KT", ("silencing", "withdrawal_pressure"),
     {"en": "My uncle keeps telling me to forgive them and withdraw the report, or else.",
      "hi": "मेरे चाचा बार-बार कहते हैं कि उन्हें माफ़ कर दो और रिपोर्ट वापस ले लो, वरना देख लेना।",
      "hinglish": "Mere chacha baar baar kehte hain ki unhe maaf kar do aur report wapas le lo, warna dekh lena."}, None),
    ("co17", "coercion", "K", ("controlling",),
     {"en": "My salary goes straight to him and I must ask for every rupee.",
      "hi": "मेरी तनख़्वाह सीधे उसके पास जाती है और मुझे हर पैसे के लिए माँगना पड़ता है।",
      "hinglish": "Meri tankhwah seedhe uske paas jaati hai aur mujhe har paise ke liye maangna padta hai."}, None),
    ("co18", "coercion", "K", ("silencing",),
     {"en": "I was told that if I speak to the helpline I will not be let back in.",
      "hi": "मुझसे कहा गया है कि हेल्पलाइन से बात की तो घर में घुसने नहीं देंगे।",
      "hinglish": "Mujhse kaha gaya hai ki helpline se baat ki toh ghar mein ghusne nahi denge."}, None),
    ("od07", "coercion", "", ("ordinary_disagreement",),
     {"en": "My brother and I do not agree on which phone to buy for our mother.",
      "hi": "माँ के लिए कौन-सा फ़ोन लें, इस पर भाई और मेरी राय नहीं मिलती।",
      "hinglish": "Maa ke liye kaun sa phone lein, is pe bhai aur meri raay nahi milti."}, None),
    ("od08", "coercion", "", ("care",),
     {"en": "My husband reminds me to lock the door at night, and I do the same for him.",
      "hi": "पति रात को दरवाज़ा बंद करने की याद दिलाते हैं, और मैं भी उन्हें याद दिलाती हूँ।",
      "hinglish": "Pati raat ko darwaza band karne ki yaad dilate hain, aur main bhi unhe yaad dilati hoon."}, None),
    # ordinary disagreement and care: coercion near-misses (negative)
    ("od01", "coercion", "", ("ordinary_disagreement",),
     {"en": "My husband and I argued about school fees, but we sorted it out.",
      "hi": "मेरी और पति की स्कूल फ़ीस पर बहस हुई, पर हमने सुलझा ली।",
      "hinglish": "Meri aur pati ki school fees pe behes hui, par humne suljha li."}, None),
    ("od02", "coercion", "", ("ordinary_disagreement",),
     {"en": "My sister and I disagree about the wedding menu.",
      "hi": "मेरी और बहन की शादी के खाने को लेकर राय अलग है।",
      "hinglish": "Meri aur behen ki shaadi ke khaane ko lekar raay alag hai."}, None),
    ("od03", "coercion", "", ("ordinary_disagreement",),
     {"en": "My roommate and I keep arguing about whose turn it is to clean.",
      "hi": "मेरी और साथ रहने वाली की सफ़ाई की बारी पर नोकझोंक होती रहती है।",
      "hinglish": "Meri aur roommate ki safai ki baari pe nokjhok hoti rehti hai."}, None),
    ("od04", "coercion", "", ("care",),
     {"en": "My mother calls to check whether I have eaten, because she worries.",
      "hi": "माँ फ़ोन करके पूछती हैं कि मैंने खाना खाया या नहीं, क्योंकि उन्हें फ़िक्र रहती है।",
      "hinglish": "Maa phone karke poochti hain ki maine khana khaya ya nahi, kyunki unhe fikar rehti hai."}, None),
    ("od05", "coercion", "", ("ordinary_disagreement",),
     {"en": "We had a loud discussion about money and then laughed about it.",
      "hi": "पैसों को लेकर हमारी ज़ोरदार बात हुई और फिर हम हँस पड़े।",
      "hinglish": "Paison ko lekar hamari zordar baat hui aur phir hum hans pade."}, None),
    ("od06", "coercion", "", ("care",),
     {"en": "My father asks me to share my location on long bus trips, and I agree.",
      "hi": "लंबी बस यात्रा में पिताजी मेरी लोकेशन माँगते हैं और मैं ख़ुशी से भेजती हूँ।",
      "hinglish": "Lambi bus yatra mein papa meri location maangte hain aur main khushi se bhejti hoon."}, None),
    # legal urgency: a matter of the speaker's own that needs action or information
    ("lg01", "legal", "L", ("deadline",),
     {"en": "My court hearing is tomorrow morning and I still have no lawyer.",
      "hi": "मेरी सुनवाई कल सुबह है और अभी तक मेरे पास वकील नहीं है।",
      "hinglish": "Meri sunwai kal subah hai aur abhi tak mere paas vakeel nahi hai."}, None),
    ("lg02", "legal", "L", ("police_refusal",),
     {"en": "The police sent me back without writing down my complaint.",
      "hi": "पुलिस ने मेरी शिकायत लिखे बिना मुझे वापस भेज दिया।",
      "hinglish": "Police ne meri complaint likhe bina mujhe wapas bhej diya."}, None),
    ("lg03", "legal", "L", ("deadline",),
     {"en": "The last date to file my appeal is this Friday.",
      "hi": "मेरी अपील दाख़िल करने की आख़िरी तारीख़ इसी शुक्रवार है।",
      "hinglish": "Meri appeal daakhil karne ki aakhri tareekh isi Friday hai."}, None),
    ("lg04", "legal", "L", ("police_refusal",),
     {"en": "The officer wants money before he will register my report.",
      "hi": "अधिकारी मेरी रिपोर्ट दर्ज करने से पहले पैसे माँग रहा है।",
      "hinglish": "Officer meri report darj karne se pehle paise maang raha hai."}, None),
    ("lg05", "legal", "L", ("information_need",),
     {"en": "I received a summons and I do not understand what I must do.",
      "hi": "मुझे समन मिला है और समझ नहीं आ रहा कि मुझे क्या करना है।",
      "hinglish": "Mujhe summon mila hai aur samajh nahi aa raha ki mujhe kya karna hai."}, None),
    ("lg06", "legal", "L", ("delay",),
     {"en": "A month has passed since my complaint and nobody has contacted me.",
      "hi": "मेरी शिकायत को एक महीना हो गया और किसी ने संपर्क नहीं किया।",
      "hinglish": "Meri complaint ko ek mahina ho gaya aur kisi ne contact nahi kiya."}, None),
    ("lg07", "legal", "L", ("deadline",),
     {"en": "They said my case will be closed if I do not appear today.",
      "hi": "उन्होंने कहा है कि आज हाज़िर नहीं हुई तो मेरा केस बंद कर देंगे।",
      "hinglish": "Unhone kaha hai ki aaj haazir nahi hui toh mera case band kar denge."}, None),
    ("lg08", "legal", "L", ("information_need",),
     {"en": "I need someone to help me write my statement for the police.",
      "hi": "मुझे पुलिस के लिए अपना बयान लिखने में मदद चाहिए।",
      "hinglish": "Mujhe police ke liye apna bayaan likhne mein madad chahiye."}, None),
    ("lg09", "legal", "L", ("information_need",),
     {"en": "The accused got bail and nobody informed me.",
      "hi": "आरोपी को ज़मानत मिल गई और मुझे किसी ने बताया तक नहीं।",
      "hinglish": "Aaropi ko zamanat mil gayi aur mujhe kisi ne bataya tak nahi."}, None),
    ("lg10", "legal", "L", ("information_need",),
     {"en": "How do I get the free legal aid lawyer for my own case?",
      "hi": "अपने केस के लिए मुफ़्त सरकारी वकील कैसे मिलेगा?",
      "hinglish": "Apne case ke liye free sarkari vakeel kaise milega?"}, None),
    ("lg11", "legal", "L", ("police_refusal",),
     {"en": "The station in-charge refuses to accept my written complaint.",
      "hi": "थाना प्रभारी मेरी लिखित शिकायत लेने से इनकार कर रहे हैं।",
      "hinglish": "Thana incharge meri likhit complaint lene se inkaar kar rahe hain."}, None),
    ("lg12", "legal", "L", ("deadline",),
     {"en": "I have to give my statement before the magistrate on Monday and I am scared.",
      "hi": "सोमवार को मुझे मजिस्ट्रेट के सामने बयान देना है और मुझे डर लग रहा है।",
      "hinglish": "Monday ko mujhe magistrate ke saamne bayaan dena hai aur mujhe dar lag raha hai."}, None),
    ("lg13", "legal", "L", ("information_need",),
     {"en": "They gave me a copy of the charge sheet and I cannot read it.",
      "hi": "मुझे आरोप पत्र की कॉपी दी गई है पर मैं उसे पढ़ नहीं पा रही।",
      "hinglish": "Mujhe charge sheet ki copy di gayi hai par main use padh nahi pa rahi."}, None),
    ("lg14", "legal", "L", ("delay",),
     {"en": "My compensation application has been pending for months with no answer.",
      "hi": "मेरी मुआवज़े की अर्ज़ी महीनों से अटकी है और कोई जवाब नहीं।",
      "hinglish": "Meri muavze ki arzi mahino se atki hai aur koi jawab nahi."}, None),
    ("lg15", "legal", "L", ("information_need",),
     {"en": "I want to know whether I can ask for my case to be moved to another court.",
      "hi": "मुझे जानना है कि क्या मैं अपना केस दूसरी अदालत में भेजने की माँग कर सकती हूँ।",
      "hinglish": "Mujhe jaanna hai ki kya main apna case doosri court mein bhejne ki maang kar sakti hoon."}, None),
    ("lg16", "legal", "L", ("police_refusal",),
     {"en": "The police wrote a weaker section in my complaint than what happened.",
      "hi": "पुलिस ने मेरी शिकायत में जो हुआ उससे हल्की धारा लिखी है।",
      "hinglish": "Police ne meri complaint mein jo hua usse halki dhara likhi hai."}, None),
    ("gl06", "legal", "", ("general_legal",),
     {"en": "Our college held a debate about reforms in the justice system.",
      "hi": "हमारे कॉलेज में न्याय व्यवस्था में सुधार पर वाद-विवाद हुआ।",
      "hinglish": "Hamare college mein nyay vyavastha mein sudhaar pe debate hua."}, None),
    ("gl07", "legal", "", ("general_legal",),
     {"en": "My cousin just passed her law exams and is looking for a job.",
      "hi": "मेरी चचेरी बहन ने अभी क़ानून की परीक्षा पास की है और नौकरी ढूँढ रही है।",
      "hinglish": "Meri cousin ne abhi law ke exam pass kiye hain aur naukri dhoondh rahi hai."}, None),
    # general legal discussion: legal near-misses (negative)
    ("gl01", "legal", "", ("general_legal",),
     {"en": "My son has a school project about how courts work.",
      "hi": "मेरे बेटे का स्कूल प्रोजेक्ट अदालतों के काम करने के तरीक़े पर है।",
      "hinglish": "Mere bete ka school project courts ke kaam karne ke tareeke pe hai."}, None),
    ("gl02", "legal", "", ("general_legal",),
     {"en": "I watched a film about a lawyer yesterday and enjoyed it.",
      "hi": "कल मैंने एक वकील पर बनी फ़िल्म देखी, अच्छी लगी।",
      "hinglish": "Kal maine ek vakeel pe bani film dekhi, achhi lagi."}, None),
    ("gl03", "legal", "", ("general_legal",),
     {"en": "My neighbour is studying hard to become a judge.",
      "hi": "मेरी पड़ोसन जज बनने के लिए मेहनत से पढ़ रही है।",
      "hinglish": "Meri padosan judge banne ke liye mehnat se padh rahi hai."}, None),
    ("gl04", "legal", "", ("general_legal", "historical"),
     {"en": "My uncle's land case was settled many years ago.",
      "hi": "मेरे चाचा का ज़मीन वाला मामला बरसों पहले निपट गया था।",
      "hinglish": "Mere chacha ka zameen wala maamla barson pehle nipat gaya tha."}, None),
    ("gl05", "legal", "", ("general_legal",),
     {"en": "The newspaper wrote about the new court building in the district.",
      "hi": "अख़बार में ज़िले की नई अदालत की इमारत के बारे में छपा था।",
      "hinglish": "Akhbaar mein zile ki nayi court building ke baare mein chhapa tha."}, None),
    # explicit human request vs discouraged or declined help
    ("hr01", "human", "H", ("request",),
     {"en": "Please put me through to an officer, I want to talk to a person.",
      "hi": "कृपया मुझे किसी अधिकारी से जोड़िए, मुझे इंसान से बात करनी है।",
      "hinglish": "Please mujhe kisi officer se jodiye, mujhe insaan se baat karni hai."}, None),
    ("hr02", "human", "H", ("request",),
     {"en": "Can a counsellor call me back this evening?",
      "hi": "क्या आज शाम कोई परामर्शदाता मुझे वापस फ़ोन कर सकता है?",
      "hinglish": "Kya aaj shaam koi counsellor mujhe wapas phone kar sakta hai?"}, None),
    ("hr03", "human", "H", ("request",),
     {"en": "I would rather speak to a real woman officer than type here.",
      "hi": "यहाँ लिखने से अच्छा मैं किसी महिला अधिकारी से सीधे बात करूँ।",
      "hinglish": "Yahan likhne se achha main kisi mahila officer se seedhe baat karun."}, None),
    ("hd01", "human", "", ("discouraged_help",),
     {"en": "My husband says talking to any officer is useless.",
      "hi": "मेरे पति कहते हैं कि किसी अधिकारी से बात करना बेकार है।",
      "hinglish": "Mere pati kehte hain ki kisi officer se baat karna bekaar hai."}, None),
    ("hd02", "human", "", ("declined_help",),
     {"en": "I do not want to speak to anyone right now, I am only reading.",
      "hi": "मैं अभी किसी से बात नहीं करना चाहती, बस पढ़ रही हूँ।",
      "hinglish": "Main abhi kisi se baat nahi karna chahti, bas padh rahi hoon."}, None),
    ("hr04", "human", "H", ("request",),
     {"en": "I want a human being to talk to me about this, not an automatic reply.",
      "hi": "मुझे इस बारे में किसी इंसान से बात करनी है, अपने-आप आने वाला जवाब नहीं चाहिए।",
      "hinglish": "Mujhe is baare mein kisi insaan se baat karni hai, automatic reply nahi chahiye."}, None),
    ("hd03", "human", "", ("discouraged_help",),
     {"en": "My neighbour told me nobody at the office will listen, so why bother.",
      "hi": "पड़ोसन ने कहा कि दफ़्तर में कोई नहीं सुनेगा, तो क्या फ़ायदा।",
      "hinglish": "Padosan ne kaha ki office mein koi nahi sunega, toh kya fayda."}, None),
    # remaining detector categories and controls
    ("dg02", "other", "DT", ("imminent",),
     {"en": "Two men with sticks are climbing over our back wall right now.",
      "hi": "अभी दो आदमी लाठी लेकर हमारी पीछे की दीवार फाँद रहे हैं।",
      "hinglish": "Abhi do aadmi lathi lekar hamari peeche ki deewar phaand rahe hain."}, None),
    ("th02", "other", "T", ("threat",),
     {"en": "Every week they send a message that we will be taught a lesson.",
      "hi": "हर हफ़्ते वे संदेश भेजते हैं कि हमें सबक सिखाया जाएगा।",
      "hinglish": "Har hafte woh message bhejte hain ki humein sabak sikhaya jayega."}, None),
    ("md02", "other", "M", ("injury",),
     {"en": "My mother fainted after they pushed her and she is not responding well.",
      "hi": "धक्का लगने के बाद माँ बेहोश हो गईं और ठीक से जवाब नहीं दे रहीं।",
      "hinglish": "Dhakka lagne ke baad maa behosh ho gayi aur theek se jawab nahi de rahi."}, None),
    ("is02", "other", "I", ("boycott",),
     {"en": "We have been told to leave our rented room by the end of the week.",
      "hi": "हमसे कहा गया है कि हफ़्ते के आख़िर तक किराए का कमरा ख़ाली कर दो।",
      "hinglish": "Humse kaha gaya hai ki hafte ke aakhir tak kiraye ka kamra khaali kar do."}, None),
    ("sc04", "other", "", ("safe_control",),
     {"en": "Where can I renew my ration card?", "hi": "मैं अपना राशन कार्ड कहाँ नवीनीकृत करवाऊँ?",
      "hinglish": "Main apna ration card kahan renew karwaun?"}, None),
    ("sc05", "other", "", ("low_distress",),
     {"en": "I am stressed about my daughter's exams but managing.", "hi": "बेटी की परीक्षा को लेकर तनाव है, पर सँभाल रही हूँ।",
      "hinglish": "Beti ke exam ko lekar tension hai, par sambhaal rahi hoon."}, None),
    ("dg01", "other", "DT", ("imminent",),
     {"en": "A crowd is gathering outside our gate and banging on it right now.",
      "hi": "हमारे गेट के बाहर अभी भीड़ जमा है और गेट पीट रही है।",
      "hinglish": "Hamare gate ke bahar abhi bheed jama hai aur gate peet rahi hai."}, None),
    ("th01", "other", "T", ("threat",),
     {"en": "They warned that our crops will be burnt if we speak up.",
      "hi": "उन्होंने चेतावनी दी है कि बोले तो हमारी फ़सल जला देंगे।",
      "hinglish": "Unhone warning di hai ki bole toh hamari fasal jala denge."}, None),
    ("md01", "other", "M", ("injury",),
     {"en": "My father's leg is badly swollen after the attack and he cannot stand.",
      "hi": "हमले के बाद पिताजी का पैर बहुत सूज गया है और वे खड़े नहीं हो पा रहे।",
      "hinglish": "Hamle ke baad papa ka pair bahut sooj gaya hai aur woh khade nahi ho pa rahe."}, None),
    ("is01", "other", "I", ("boycott",),
     {"en": "The village has stopped selling us milk since the complaint.",
      "hi": "शिकायत के बाद से गाँव ने हमें दूध देना बंद कर दिया है।",
      "hinglish": "Complaint ke baad se gaon ne humein doodh dena band kar diya hai."}, None),
    ("sc01", "other", "", ("safe_control",),
     {"en": "I want to know the timing of the ration shop.", "hi": "मुझे राशन की दुकान का समय जानना है।",
      "hinglish": "Mujhe ration ki dukaan ka time jaanna hai."}, None),
    ("sc02", "other", "", ("low_distress",),
     {"en": "I feel low because it has been raining for days.", "hi": "कई दिनों से बारिश हो रही है, इसलिए मन उदास है।",
      "hinglish": "Kai dinon se baarish ho rahi hai, isliye mann udaas hai."}, None),
    ("sc03", "other", "", ("safe_control",),
     {"en": "Thank you, I got the information I needed.", "hi": "धन्यवाद, मुझे जो जानकारी चाहिए थी मिल गई।",
      "hinglish": "Shukriya, mujhe jo jaankari chahiye thi mil gayi."}, None),
]

# --- framings: direct keeps the label; the others remove the core's risk labels --------------------

DIRECT_FRAMES = {
    "en": ["{core}", "{core} Please listen to me.", "I have not told anyone this. {core}",
           "{core} It has been like this for days.", "I need to say it plainly. {core}",
           "Sorry to write so late. {core}", "{core} I do not know who else to tell.", "Right now, today: {core}"],
    "hi": ["{core}", "{core} कृपया मेरी बात सुनिए।", "मैंने यह किसी को नहीं बताया। {core}",
           "{core} कई दिनों से ऐसा ही है।", "साफ़-साफ़ कहती हूँ। {core}",
           "इतनी देर से लिखने के लिए माफ़ी। {core}", "{core} समझ नहीं आता और किसे बताऊँ।", "आज, अभी की बात है: {core}"],
    "hinglish": ["{core}", "{core} Please meri baat suniye.", "Maine yeh kisi ko nahi bataya. {core}",
                 "{core} Kai dinon se aisa hi hai.", "Seedhi baat bolti hoon. {core}",
                 "Itni der se likhne ke liye sorry. {core}", "{core} Samajh nahi aata aur kisko bataun.",
                 "Aaj, abhi ki baat hai: {core}"],
}
QUOTED_FRAMES = {
    "en": ['In a TV serial last night a character said, "{core}"', 'The song on the radio had the line "{core}"',
           'My daughter is practising a school play where the actor says, "{core}"'],
    "hi": ['कल रात एक धारावाहिक में एक किरदार ने कहा, "{core}"', 'रेडियो के गाने में पंक्ति थी, "{core}"',
           'मेरी बेटी स्कूल के नाटक का अभ्यास कर रही है जिसमें कलाकार कहता है, "{core}"'],
    "hinglish": ['Kal raat ek serial mein ek character ne kaha, "{core}"', 'Radio ke gaane mein line thi, "{core}"',
                 'Meri beti school ke natak ki practice kar rahi hai jismein actor kehta hai, "{core}"'],
}
REPORTED_FRAMES = {
    "en": ['My friend messaged me, "{core}" How can I help her?', 'A woman in my building told me, "{core}"',
           'My colleague said this about his cousin: "{core}"'],
    "hi": ['मेरी सहेली ने मुझे लिखा, "{core}" मैं उसकी मदद कैसे करूँ?', 'मेरी बिल्डिंग की एक महिला ने मुझसे कहा, "{core}"',
           'मेरे साथ काम करने वाले ने अपने रिश्तेदार के बारे में बताया: "{core}"'],
    "hinglish": ['Meri saheli ne mujhe likha, "{core}" Main uski madad kaise karun?',
                 'Meri building ki ek aurat ne mujhse kaha, "{core}"',
                 'Mere colleague ne apne rishtedaar ke baare mein bataya: "{core}"'],
}
PAST_FRAMES = {
    "en": ['Three years ago I used to feel this: "{core}" That time has passed and I am better now.',
           'Long ago it was like this for me: "{core}" It is all behind me now.'],
    "hi": ['तीन साल पहले मुझे ऐसा लगता था: "{core}" वह समय बीत गया, अब मैं बेहतर हूँ।',
           'बहुत पहले मेरे साथ ऐसा था: "{core}" अब वह सब पीछे छूट गया।'],
    "hinglish": ['Teen saal pehle mujhe aisa lagta tha: "{core}" Woh waqt beet gaya, ab main behtar hoon.',
                 'Bahut pehle mere saath aisa tha: "{core}" Ab woh sab peeche chhoot gaya.'],
}
#: framings whose meaning removes the core's risk labels (the family's contrast members)
NEAR_MISS = (("quoted", QUOTED_FRAMES, "quotation"), ("reported", REPORTED_FRAMES, "attribution"),
             ("past", PAST_FRAMES, "historical"))
ROMAN_VARIANTS = (("nahi", "nhi"), ("mujhe", "muje"), ("kya", "kia"), ("hai", "h"), ("zinda", "jinda"),
                  ("aur", "or"), ("baat", "bat"), ("zindagi", "jindagi"), ("kuch", "kuchh"), ("please", "plz"))


# --- deterministic helpers ------------------------------------------------------------------------


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in (SEED, *parts)).encode("utf-8")).hexdigest()[:12], 16)


def labels_of(codes: str) -> Dict[str, bool]:
    pos = {_CODE[c] for c in codes}
    return {n: n in pos for n in LABELS}


def script_of(text: str) -> str:
    dev = any("ऀ" <= ch <= "ॿ" for ch in text)
    lat = any(ch.isascii() and ch.isalpha() for ch in text)
    return "mixed" if dev and lat else "devanagari" if dev else "latin" if lat else "none"


def _variant(text: str, language: str, v: int) -> Tuple[str, List[str]]:
    """Surface variation. v % 4 == 0 keeps the text clean."""
    rng = random.Random(_h("variant", text, v))
    kind = v % 4
    if kind == 0:
        return text, []
    if kind == 1:
        if language == "hi":
            if "़" in text or "ँ" in text:
                return unicodedata.normalize("NFC", text.replace("़", "").replace("ँ", "ं")), ["hindi_spelling_variant"]
            return unicodedata.normalize("NFD", text).replace(" ", " ‌", 1), ["unicode_variant"]
        if language == "hinglish":
            out = text
            for a, b in ROMAN_VARIANTS:
                if re.search(rf"\b{a}\b", out, re.I) and rng.random() < 0.7:
                    out = re.sub(rf"\b{a}\b", b, out, count=1, flags=re.I)
            if out != text:
                return out, ["romanized_spelling_variant"]
        words = text.split(" ")
        idx = [i for i, w in enumerate(words) if w.isalpha() and len(w) > 4]
        if idx:
            i = idx[rng.randrange(len(idx))]
            w = words[i]
            words[i] = w[:2] + w[3] + w[2] + w[4:]
            return " ".join(words), ["misspelling"]
        return text, []
    if kind == 2:
        return (text.rstrip(".।?!") + " ..." if rng.random() < 0.5 else text.replace(", ", ",")), ["punctuation_spacing"]
    if language == "hi":  # Devanagari has no case: vary danda, spacing and Unicode form instead
        option = (v // 4) % 3
        if option == 0:
            return text.replace(" ", "  ", 1), ["punctuation_spacing"]
        if option == 1:
            return text.replace("।", "."), ["punctuation_spacing"]
        return unicodedata.normalize("NFD", text).replace("़", "‌़", 1), ["unicode_variant"]
    return text.lower(), ["case_or_spacing"]


def assign_splits(cores: Sequence[Core] = CORES) -> Dict[str, str]:
    """About 80/10/10 of families per area, by hash; every area has a validation and a holdout family."""
    by_area: Dict[str, List[str]] = {}
    for cid, area, codes, *_ in cores:
        by_area.setdefault(f"{area}:{'pos' if codes else 'neg'}", []).append(cid)
    out: Dict[str, str] = {}
    for _, ids in sorted(by_area.items()):
        ordered = sorted(ids, key=lambda c: _h("split", c))
        n = len(ordered)
        n_val = max(1, round(n * 0.1)) if n >= 3 else 0
        n_hold = max(1, round(n * 0.1)) if n >= 3 else 0
        for i, cid in enumerate(ordered):
            out[cid] = "validation" if i < n_val else "synthetic_hardening_holdout" if i < n_val + n_hold else "train"
    return out


def _record(rid: str, family: str, group: str, split: str, language: str, turns: List[str], labels: Dict[str, bool],
            negatives: List[str], slices: Iterable[str], lineage: Mapping[str, Any], reason: Optional[str] = None
            ) -> Dict[str, Any]:
    victim = [{"id": f"t{i + 1}", "speaker": "victim", "text": t, "state": "S2"} for i, t in enumerate(turns)]
    joined = " ".join(turns)
    s = set(slices)
    if language == "hinglish":
        s.add("code_switching")
    if sum(labels.values()) > 1:
        s.add("multi_label")
    s.add("multi_turn" if len(turns) > 1 else "single_turn")
    return {"id": rid, "family": family, "contrast_group": group, "split": split, "language": language,
            "script": script_of(joined), "turns": victim, "labels": labels,
            "positive_labels": [n for n in LABELS if labels[n]], "negative_labels": sorted(negatives),
            "challenge_slices": sorted(s), "generator_version": GENERATOR_VERSION, "seed": SEED,
            "lineage": dict(lineage), "multi_label_reason": reason,
            "content_hash": hashlib.sha256(nz.compare(joined).encode("utf-8")).hexdigest(),
            "review_status": "unreviewed", "fictional": True}


def generate(variants: int = 10, combos_per_pair: int = 40) -> List[Dict[str, Any]]:
    splits = assign_splits()
    records: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    def add(rec: Dict[str, Any]) -> None:
        key = (rec["language"], rec["content_hash"])
        if key not in seen:
            seen.add(key)
            records.append(rec)

    for cid, area, codes, slices, texts, negated in CORES:
        split, labels = splits[cid], labels_of(codes)
        risk = [n for n in LABELS if labels[n]]
        for lang in LANGUAGES:
            frames = DIRECT_FRAMES[lang] if codes else ["{core}"]
            for f, frame in enumerate(frames):
                for v in range(variants):
                    text, extra = _variant(frame.format(core=texts[lang]), lang, v)
                    add(_record(f"HX-{cid}-{lang}-d{f}v{v}", cid, cid, split, lang, [text], labels,
                                [] if codes else [C] if area == "crisis" else [K] if area == "coercion" else
                                [L] if area == "legal" else [H] if area == "human" else [],
                                (*slices, "direct" if codes else slices[0], *extra),
                                {"core": cid, "frame": f"direct{f}", "variant": v}))
            if not codes:
                continue
            for name, bank, slice_name in NEAR_MISS:
                for f, frame in enumerate(bank[lang]):
                    for v in range(max(2, variants // 2)):
                        text, extra = _variant(frame.format(core=texts[lang]), lang, v)
                        add(_record(f"HX-{cid}-{lang}-{name}{f}v{v}", cid, cid, split, lang, [text],
                                    labels_of(""), risk, (slice_name, "contrast", *extra),
                                    {"core": cid, "frame": f"{name}{f}", "variant": v}))
            if negated:
                for v in range(max(2, variants // 2)):
                    text, extra = _variant(negated[lang], lang, v)
                    add(_record(f"HX-{cid}-{lang}-neg-v{v}", cid, cid, split, lang, [text], labels_of(""), risk,
                                ("negation", "contrast", *extra), {"core": cid, "frame": "negated", "variant": v}))

    # multi-label: two positive cores of different areas, same split, joined as two victim turns
    positives = [c for c in CORES if c[2]]
    pairs = [("crisis", "coercion"), ("crisis", "legal"), ("coercion", "legal"), ("crisis", "other"),
             ("coercion", "other"), ("legal", "other"), ("crisis", "human"), ("coercion", "human")]
    for a_area, b_area in pairs:
        for split in SPLITS:
            a_pool = [c for c in positives if c[1] == a_area and splits[c[0]] == split]
            b_pool = [c for c in positives if c[1] == b_area and splits[c[0]] == split]
            if not a_pool or not b_pool:
                continue
            for lang in LANGUAGES:
                n = combos_per_pair if split == "train" else max(4, combos_per_pair // 4)
                for i in range(n):
                    rng = random.Random(_h("combo", a_area, b_area, split, lang, i))
                    a, b = a_pool[rng.randrange(len(a_pool))], b_pool[rng.randrange(len(b_pool))]
                    first, fx = _variant(a[4][lang], lang, rng.randrange(variants))
                    second, sx = _variant(b[4][lang], lang, rng.randrange(variants))
                    turns = [first, second] if rng.random() < 0.5 else [second, first]
                    labels = {n: labels_of(a[2])[n] or labels_of(b[2])[n] for n in LABELS}
                    reason = (f"turn composition: core {a[0]} ({'+'.join(sorted(_CODE[c] for c in a[2]))}) "
                              f"and core {b[0]} ({'+'.join(sorted(_CODE[c] for c in b[2]))})")
                    add(_record(f"HX-M-{a[0]}-{b[0]}-{lang}-{i:03d}", f"combo:{a[0]}+{b[0]}", f"combo:{a[0]}+{b[0]}",
                                split, lang, turns, labels, [], ("multi_turn_combo", *fx, *sx),
                                {"cores": [a[0], b[0]], "variant": i}, reason))
    return records


# --- contamination ----------------------------------------------------------------------------------


def _norm_hash(text: str) -> str:
    return hashlib.sha256(nz.compare(text).encode("utf-8")).hexdigest()


def contamination(records: Sequence[Mapping[str, Any]], task7: Sequence[Mapping[str, Any]],
                  external_keys: Optional[Set[str]], index: Optional[Mapping[str, Any]] = None,
                  blind_available: bool = False) -> Dict[str, Any]:
    """Block exact, normalised, reordered and verbatim-turn matches against exposed fixtures, the Task 7
    corpus and Task 5 external text; block cross-split duplicates. Warn on near overlap and shared
    token windows. A block removes the whole family. IDs and counts only."""
    index = index if index is not None else lk.build_index(files=ALL_EXPOSED_FILES)
    t7_turns = {_norm_hash(t["text"]) for r in task7 for t in r["turns"] if t["speaker"] == "victim"}
    t7_scen = {_norm_hash(" ".join(t["text"] for t in r["turns"] if t["speaker"] == "victim")) for r in task7}
    t7_shingles: Set[Tuple[str, ...]] = set()
    for r in task7:
        for t in r["turns"]:
            if t["speaker"] == "victim":
                t7_shingles |= nz.shingles(nz.compare(t["text"]), 6)
    blocked: Dict[str, List[str]] = {}
    warnings: Counter = Counter()
    owner: Dict[str, Tuple[str, str]] = {}
    for r in records:
        reasons: List[str] = []
        for f in lk.check({"turns": r["turns"]}, index):
            if f["severity"] == "block":
                reasons.append(f"fixture:{f['check']}")
            else:
                warnings[f"fixture:{f['check']}"] += 1
        victim = [t["text"] for t in r["turns"]]
        if r["content_hash"] in t7_scen or any(_norm_hash(t) in t7_turns for t in victim):
            reasons.append("task7:exact_or_normalized")
        elif any(nz.shingles(nz.compare(t), 6) & t7_shingles for t in victim):
            warnings["task7:shared_token_window"] += 1
        if external_keys and (r["content_hash"] in external_keys or any(_norm_hash(t) in external_keys for t in victim)):
            reasons.append("external:exact_or_normalized")
        prior = owner.setdefault(r["content_hash"], (r["family"], r["split"]))
        if prior[1] != r["split"]:
            reasons.append("duplicate_across_splits")
        if reasons:
            blocked.setdefault(r["family"], []).extend(reasons)
    kept = [r for r in records if r["family"] not in blocked]
    return {"kept": kept, "blocked_families": {k: dict(Counter(v)) for k, v in sorted(blocked.items())},
            "blocked_records": len(records) - len(kept), "warnings": dict(warnings),
            "blind_corpus": "compared" if blind_available else "unavailable: no private blind corpus is configured"}


# --- coverage, freeze, review packet -------------------------------------------------------------


def area_of(r: Mapping[str, Any]) -> str:
    if r["family"].startswith("combo:"):
        return "multi_label"
    core = next(c for c in CORES if c[0] == r["family"])
    return {"crisis": "crisis", "coercion": "coercion", "legal": "legal"}.get(core[1], "controls_and_other")


def coverage(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_split = {s: Counter() for s in SPLITS}
    problems: List[str] = []
    for r in records:
        c = by_split[r["split"]]
        c["records"] += 1
        c[f"lang:{r['language']}"] += 1
        c[f"area:{area_of(r)}"] += 1
        for n in r["positive_labels"]:
            c[f"label:{n}"] += 1
            c[f"label_lang:{n}:{r['language']}"] += 1
        if not r["positive_labels"]:
            c["no_alert"] += 1
        for s in r["challenge_slices"]:
            c[f"slice:{s}"] += 1
    for split in SPLITS:
        for n in (C, L, K):
            for lang in LANGUAGES:
                if not by_split[split][f"label_lang:{n}:{lang}"]:
                    problems.append(f"{split}: no {n} positive in {lang}")
    families: Dict[str, Set[str]] = {}
    for r in records:
        families.setdefault(r["family"], set()).add(r["split"])
    problems += [f"family {f} crosses splits" for f, s in families.items() if len(s) > 1]
    return {"splits": {s: dict(sorted(c.items())) for s, c in by_split.items()}, "problems": problems,
            "families": {s: sorted(f for f, sp in families.items() if s in sp) for s in SPLITS}}


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def bank_hash() -> str:
    return _sha({"cores": CORES, "direct": DIRECT_FRAMES, "near_miss": [(n, b, s) for n, b, s in NEAR_MISS],
                 "roman": ROMAN_VARIANTS})


def freeze_payload(records: Sequence[Mapping[str, Any]], cov: Mapping[str, Any]) -> Dict[str, Any]:
    split_hashes = {s: _sha(sorted(r["content_hash"] + "|" + r["id"] for r in records if r["split"] == s))
                    for s in SPLITS}
    family_hashes = {s: _sha(cov["families"][s]) for s in SPLITS}
    return {"version": VERSION, "generator_version": GENERATOR_VERSION, "seed": SEED, "bank_sha256": bank_hash(),
            "split_record_sha256": split_hashes, "split_family_sha256": family_hashes,
            "records": {s: sum(r["split"] == s for r in records) for s in SPLITS},
            "holdout_note": HOLDOUT_NOTE}


def build(root: Path, external_keys: Optional[Set[str]] = None) -> Dict[str, Any]:
    out = paths.confined(root, *CORPUS_DIR)
    if (out / "freeze.json").is_file():
        raise RuntimeError(f"corpus {VERSION} is frozen; create a new version instead of regenerating it")
    records = generate()
    screen = contamination(records, fictional.load(root), external_keys)
    kept = screen["kept"]
    cov = coverage(kept)
    if cov["problems"]:
        raise RuntimeError("coverage failed: " + "; ".join(cov["problems"][:6]))
    out.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        rows = [r for r in kept if r["split"] == split]
        tmp = out / f"{split}.jsonl.partial"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
        tmp.replace(out / f"{split}.jsonl")
    paths.write_json(out / "split_manifest.json", {"families": cov["families"], "coverage": cov["splits"]})
    frozen = freeze_payload(kept, cov)
    frozen.update({"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "state": "frozen_before_training",
                   "files_sha256": {f"{s}.jsonl": paths.sha256_file(out / f"{s}.jsonl") for s in SPLITS}
                   | {"split_manifest.json": paths.sha256_file(out / "split_manifest.json")}})
    paths.write_json(out / "freeze.json", frozen)
    packet = review_packet(root, kept)
    report = {"generated": len(records), "kept": len(kept), "contamination": {k: v for k, v in screen.items()
                                                                                if k != "kept"},
              "coverage": cov["splits"], "families": {s: len(v) for s, v in cov["families"].items()},
              "freeze": frozen, "review_packet": packet}
    paths.write_json(paths.confined(root, "task7b", "reports", "corpus.json"), report)
    return report


def load_split(root: Path, split: str) -> List[Dict[str, Any]]:
    path = paths.confined(root, *CORPUS_DIR, f"{split}.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def verify_freeze(root: Path) -> Dict[str, Any]:
    """Recompute every frozen hash from the files on disk (run in a fresh process)."""
    out = paths.confined(root, *CORPUS_DIR)
    frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    files_ok = {name: paths.sha256_file(out / name) == digest for name, digest in frozen["files_sha256"].items()}
    records = [r for s in SPLITS for r in load_split(root, s)]
    manifest = json.loads((out / "split_manifest.json").read_text(encoding="utf-8"))
    recomputed = freeze_payload(records, {"families": manifest["families"]})
    same = {k: recomputed[k] == frozen[k] for k in ("split_record_sha256", "split_family_sha256", "records",
                                                     "bank_sha256")}
    return {"version": frozen["version"], "frozen_at": frozen["frozen_at"], "files_match": files_ok,
            "hashes_match": same, "ok": all(files_ok.values()) and all(same.values())}


REVIEW_FIELDS = ("reviewer_identity", "role", "language_correct", "label_correct", "contrast_correct",
                 "safety_concern", "decision", "reasoning", "timestamp")


def review_packet(root: Path, records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """A private sampling of every family, label, language, contrast type and multi-label combination,
    with every review field empty. No review is ever filled in here."""
    chosen: Dict[str, Mapping[str, Any]] = {}

    def take(r: Mapping[str, Any], why: str) -> None:
        chosen.setdefault(r["id"], {**r, "sampled_for": why})

    by_key: Dict[Tuple[Any, ...], List[Mapping[str, Any]]] = {}
    for r in records:
        frame = r["lineage"].get("frame", "combo")
        by_key.setdefault((r["family"], r["language"], re.sub(r"\d+$", "", frame)), []).append(r)
    for key, rs in sorted(by_key.items()):
        take(sorted(rs, key=lambda x: x["id"])[0], "family/language/contrast type")
    for n in LABELS:
        for lang in LANGUAGES:
            rs = sorted((r for r in records if n in r["positive_labels"] and r["language"] == lang), key=lambda x: x["id"])
            if rs:
                take(rs[0], f"label {n} in {lang}")
    for r in records:
        if C in r["positive_labels"] and "conditional" in r["challenge_slices"]:
            take(r, "high-risk crisis example")
    rows = [{"template_family": r["family"], "record_id": r["id"], "language": r["language"], "split": r["split"],
             "labels": r["positive_labels"], "negative_labels": r["negative_labels"],
             "challenge_slices": r["challenge_slices"], "multi_label_reason": r["multi_label_reason"],
             "turns": [t["text"] for t in r["turns"]], "sampled_for": r["sampled_for"],
             **{f: None for f in REVIEW_FIELDS}, "decision_options": ["approve", "revise", "reject"],
             "review_state": "pending_human_review"} for r in sorted(chosen.values(), key=lambda x: x["id"])]
    out = paths.confined(root, *REVIEW_DIR)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "review-packet.jsonl.partial", "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "review-packet.jsonl.partial").replace(out / "review-packet.jsonl")
    summary = {"items": len(rows), "families": len({r["template_family"] for r in rows}),
               "languages": sorted({r["language"] for r in rows}), "state": "pending_human_review",
               "completed_reviews": 0, "note": "Human review is mandatory before any future product-promotion "
                                               "decision and is not simulated here."}
    paths.write_json(out / "review-summary.json", summary)
    return summary
