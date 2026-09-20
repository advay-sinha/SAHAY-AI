"""Deterministic fictional SAHAY supervision for the shadow head (Stage C). Standard library only.

    python -m ml.training.cli fictional

Every sentence below was written for this file. None is copied or derived from a dataset, a case,
a fixture or a real conversation. The people are generic roles, places are generic, and no text
carries a name, number, address or identity characteristic. Crisis wording states intent or a wish
to die without any method; danger wording states presence or imminence without graphic detail.

Labels are the eight schema ``DETECTOR_CATEGORIES`` exactly (``ml.eval.schema``), with the schema's
own definitions: negated, quoted, attributed or past risk is negative; imminent danger is also a
continuing threat (as the fixtures label it); pressure to withdraw a complaint is both
coercion and a continuing threat.

Families and splits
-------------------
A *template* is one scenario sentence in three languages. Every template, with all its language
versions and every variant, belongs to exactly one split (train about 80%, validation about 10%,
``synthetic_development_test`` about 10%), assigned per stratum by a hash. Multi-turn records
combine templates of one split only, so no template lineage crosses splits. Records that
overlap an exposed fixture (exact, normalised, reordered, verbatim turn, high overlap or a
distinctive shared phrase) block their whole template family.

The output lives beneath ``SAHAY_TRAINING_ROOT``. It is development training data: never blind,
locked, independent or official evaluation material.
"""

import hashlib
import json
import random
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..eval.blind import leakage as lk
from ..eval.schema import DETECTOR_CATEGORIES
from . import paths

GENERATOR_VERSION = "1.0.0"
SEED = "sahay-fictional-v1"
LABELS: Tuple[str, ...] = tuple(DETECTOR_CATEGORIES)
LANGUAGES = ("en", "hi", "hinglish")
SPLITS = ("train", "validation", "synthetic_development_test")
SPLIT_NOTE = ("synthetic_development_test is a fictional development split drawn from the same generator; it is "
              "not independent, blind, locked or official evaluation")
VARIANTS_PER_TEMPLATE = 20
MULTI_TURN_PER_SPLIT_LANGUAGE = {"train": 1000, "validation": 130, "synthetic_development_test": 130}
EXTRA_EXPOSED_FILES = ("locked.json",)  # never evaluated, but still blocked against

_CODE = {"C": "crisis_self_harm", "D": "immediate_danger", "T": "continuing_threat", "M": "medical_urgency",
         "I": "isolation_boycott_displacement", "L": "legal_urgency", "K": "communication_safety_coercion",
         "H": "explicit_human_request"}

# --- slot fillers (generic roles and places only) --------------------------------------------

FILLERS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "who": ["some men from the next village", "the landlord's men", "those people", "my in-laws",
                "a group of men", "the contractor's men", "people from the other side"],
        "time": ["right now", "tonight", "in a few minutes", "at this very moment"],
        "kin": ["my brother", "my mother", "my son", "my daughter", "my father", "my sister"],
        "kin_o": ["my brother", "my mother", "my son", "my daughter", "my father", "my sister"],
        "place": ["near the market", "in our lane", "in the fields", "at the bus stand", "near the well"],
    },
    "hi": {
        "who": ["पड़ोस के गाँव के कुछ आदमी", "ज़मींदार के आदमी", "वो लोग", "ससुराल वाले", "कुछ आदमी",
                "ठेकेदार के आदमी", "दूसरी तरफ़ के लोग"],
        "time": ["अभी", "आज रात", "कुछ ही देर में", "इसी वक़्त"],
        "kin": ["मेरा भाई", "मेरी माँ", "मेरा बेटा", "मेरी बेटी", "मेरे पिता", "मेरी बहन"],
        "kin_o": ["मेरे भाई", "मेरी माँ", "मेरे बेटे", "मेरी बेटी", "मेरे पिता", "मेरी बहन"],
        "place": ["बाज़ार के पास", "हमारी गली में", "खेत में", "बस अड्डे पर", "कुएँ के पास"],
    },
    "hinglish": {
        "who": ["padosi gaon ke kuch aadmi", "zameendar ke aadmi", "woh log", "sasuraal wale", "kuch aadmi",
                "thekedaar ke aadmi", "doosri taraf ke log"],
        "time": ["abhi", "aaj raat", "thodi der mein", "isi waqt"],
        "kin": ["mera bhai", "meri maa", "mera beta", "meri beti", "mere papa", "meri behen"],
        "kin_o": ["mere bhai", "meri maa", "mere bete", "meri beti", "mere papa", "meri behen"],
        "place": ["market ke paas", "hamari gali mein", "khet mein", "bus stand pe", "kuen ke paas"],
    },
}

# --- templates: key, label codes, phenomena, {language: text} --------------------------------

T = Tuple[str, str, Tuple[str, ...], Dict[str, str]]
TEMPLATES: List[T] = [
    # crisis_self_harm: first person, present intent or wish to die, no method
    ("c01", "C", ("direct",), {"en": "I don't want to live anymore.",
                               "hi": "मैं अब और जीना नहीं चाहती।",
                               "hinglish": "Main ab aur jeena nahi chahti."}),
    ("c02", "C", ("direct",), {"en": "I want to end my life.",
                               "hi": "मैं अपनी जान देना चाहता हूँ।",
                               "hinglish": "Main apni jaan dena chahta hoon."}),
    ("c03", "C", ("direct",), {"en": "These days I keep thinking about killing myself.",
                               "hi": "आजकल मुझे बार-बार खुद को ख़त्म करने के ख़याल आते हैं।",
                               "hinglish": "Aajkal mujhe baar baar khud ko khatam karne ke khayal aate hain."}),
    ("c04", "C", ("direct",), {"en": "I feel like hurting myself right now.",
                               "hi": "अभी मेरा मन कर रहा है कि मैं खुद को नुकसान पहुँचाऊँ।",
                               "hinglish": "Abhi mera mann kar raha hai ki main khud ko nuksaan pahunchaun."}),
    ("c05", "C", ("indirect",), {"en": "Everyone would be better off without me, I don't want to be here anymore.",
                                 "hi": "मेरे न रहने से सबका भला होगा, मैं अब यहाँ नहीं रहना चाहती।",
                                 "hinglish": "Mere na rehne se sabka bhala hoga, main ab yahan nahi rehna chahti."}),
    ("c06", "C", ("conditional",), {"en": "If this continues one more day, I will end my life.",
                                    "hi": "अगर यह एक दिन और चला तो मैं अपनी जान दे दूँगा।",
                                    "hinglish": "Agar yeh ek din aur chala toh main apni jaan de dunga."}),
    ("c07", "C", ("indirect",), {"en": "There is no reason left for me to keep living.",
                                 "hi": "मेरे जीने की कोई वजह नहीं बची।",
                                 "hinglish": "Mere jeene ki koi wajah nahi bachi."}),
    ("c08", "C", ("direct",), {"en": "I can't bear it anymore, I want to die.",
                               "hi": "अब सहा नहीं जाता, मैं मरना चाहती हूँ।",
                               "hinglish": "Ab saha nahi jaata, main marna chahti hoon."}),
    # immediate_danger (+ continuing_threat): present or imminent
    ("d01", "DT", ("direct",), {"en": "{who} are outside my door {time} with sticks.",
                                "hi": "{who} {time} लाठियाँ लेकर मेरे दरवाज़े पर खड़े हैं।",
                                "hinglish": "{who} {time} lathiyan lekar mere darwaze pe khade hain."}),
    ("d02", "DT", ("direct",), {"en": "{who} are coming to attack us {time}, please hurry.",
                                "hi": "{who} {time} हम पर हमला करने आ रहे हैं, जल्दी कीजिए।",
                                "hinglish": "{who} {time} hum pe hamla karne aa rahe hain, jaldi kijiye."}),
    ("d03", "DT", ("direct",), {"en": "{who} have surrounded our house {time}.",
                                "hi": "{who} {time} हमारे घर को घेरकर खड़े हैं।",
                                "hinglish": "{who} {time} hamare ghar ko gherkar khade hain."}),
    ("d04", "DT", ("direct",), {"en": "Someone is breaking down our door {time}.",
                                "hi": "कोई {time} हमारा दरवाज़ा तोड़ रहा है।",
                                "hinglish": "Koi {time} hamara darwaza tod raha hai."}),
    ("d05", "DT", ("direct",), {"en": "{who} are standing {place} with a weapon and looking for me {time}.",
                                "hi": "{who} {place} हथियार लेकर खड़े हैं और {time} मुझे ढूँढ रहे हैं।",
                                "hinglish": "{who} {place} hathiyar lekar khade hain aur {time} mujhe dhoondh rahe hain."}),
    ("d06", "DT", ("indirect",), {"en": "{who} are on their way here {time}, they said today is the day.",
                                  "hi": "{who} {time} यहाँ आने वाले हैं, उन्होंने कहा आज ही होगा।",
                                  "hinglish": "{who} {time} yahan aane wale hain, unhone kaha aaj hi hoga."}),
    ("d07", "DT", ("direct",), {"en": "They are hitting my family {time} and we are trapped inside.",
                                "hi": "वे {time} मेरे परिवार को मार रहे हैं और हम अंदर फँसे हुए हैं।",
                                "hinglish": "Woh {time} mere parivaar ko maar rahe hain aur hum andar phanse hue hain."}),
    ("d08", "DT", ("direct",), {"en": "I am hiding inside the house, {who} are searching for me {time}.",
                                "hi": "मैं घर में छिपी हूँ, {who} {time} मुझे ढूँढ रहे हैं।",
                                "hinglish": "Main ghar mein chhupi hoon, {who} {time} mujhe dhoondh rahe hain."}),
    # continuing_threat: threat or intimidation, not necessarily imminent
    ("t01", "T", ("direct",), {"en": "{who} keep threatening to burn our house if we do not leave.",
                               "hi": "{who} धमकी देते रहते हैं कि अगर हम नहीं गए तो घर जला देंगे।",
                               "hinglish": "{who} dhamki dete rehte hain ki agar hum nahi gaye toh ghar jala denge."}),
    ("t02", "T", ("direct",), {"en": "{who} told me they will never let my family live in peace.",
                               "hi": "{who} कहते हैं कि वे मेरे परिवार को कभी चैन से नहीं रहने देंगे।",
                               "hinglish": "{who} kehte hain ki woh mere parivaar ko kabhi chain se nahi rehne denge."}),
    ("t03", "T", ("direct",), {"en": "Ever since the complaint, {who} keep sending me threats.",
                               "hi": "शिकायत के बाद से {who} मुझे लगातार धमकियाँ भेज रहे हैं।",
                               "hinglish": "Complaint ke baad se {who} mujhe lagataar dhamkiyan bhej rahe hain."}),
    ("t04", "T", ("indirect",), {"en": "{who} warned {kin_o} that something bad will happen to us soon.",
                                 "hi": "{who} ने चेतावनी दी है कि जल्द ही हमारे साथ कुछ बुरा होगा।",
                                 "hinglish": "{who} ne warning di hai ki jaldi hamare saath kuch bura hoga."}),
    ("t05", "T", ("direct",), {"en": "Every evening {who} stand {place} and shout that they will teach us a lesson.",
                               "hi": "हर शाम {who} {place} खड़े होकर चिल्लाते हैं कि हमें सबक सिखाएँगे।",
                               "hinglish": "Har shaam {who} {place} khade hokar chillate hain ki humein sabak sikhayenge."}),
    ("t06", "T", ("conditional",), {"en": "{who} say that if we go to the police, they will harm my children.",
                                    "hi": "{who} कहते हैं कि अगर हम पुलिस के पास गए तो मेरे बच्चों को नुकसान पहुँचाएँगे।",
                                    "hinglish": "{who} kehte hain ki agar hum police ke paas gaye toh mere bachchon ko nuksaan pahunchayenge."}),
    ("t07", "T", ("direct",), {"en": "{who} said they will come back next week to finish this.",
                               "hi": "{who} कहकर गए हैं कि अगले हफ़्ते वापस आकर यह ख़त्म करेंगे।",
                               "hinglish": "{who} keh kar gaye hain ki agle hafte wapas aakar yeh khatam karenge."}),
    ("t08", "T", ("indirect",), {"en": "I keep getting calls telling me to be careful, or else we will regret it.",
                                 "hi": "मुझे फ़ोन आते रहते हैं कि सँभलकर रहो, वरना पछताओगे।",
                                 "hinglish": "Mujhe phone aate rehte hain ki sambhal ke raho, warna pachtaoge."}),
    # medical_urgency: injured, bleeding, unconscious, needs treatment now
    ("m01", "M", ("direct",), {"en": "{kin} is bleeding badly and needs a doctor now.",
                               "hi": "{kin_o} का बहुत ख़ून बह रहा है, अभी डॉक्टर चाहिए।",
                               "hinglish": "{kin_o} ka bahut khoon beh raha hai, abhi doctor chahiye."}),
    ("m02", "M", ("direct",), {"en": "{kin} is unconscious after the beating.",
                               "hi": "पिटाई के बाद {kin} बेहोश है।",
                               "hinglish": "Pitai ke baad {kin} behosh hai."}),
    ("m03", "M", ("direct",), {"en": "{kin} has a deep head wound that will not stop bleeding.",
                               "hi": "{kin_o} के सिर पर गहरी चोट है और ख़ून रुक नहीं रहा।",
                               "hinglish": "{kin_o} ke sir pe gehri chot hai aur khoon ruk nahi raha."}),
    ("m04", "M", ("direct",), {"en": "I think my arm is broken, I need treatment right away.",
                               "hi": "लगता है मेरा हाथ टूट गया है, मुझे तुरंत इलाज चाहिए।",
                               "hinglish": "Lagta hai mera haath toot gaya hai, mujhe turant ilaaj chahiye."}),
    ("m05", "M", ("direct",), {"en": "{kin} cannot breathe properly, please send an ambulance.",
                               "hi": "{kin_o} को साँस लेने में बहुत तकलीफ़ है, एम्बुलेंस भेजिए।",
                               "hinglish": "{kin_o} ko saans lene mein bahut takleef hai, ambulance bhejiye."}),
    ("m06", "M", ("direct",), {"en": "I was hit and I am bleeding, I need to get to a hospital.",
                               "hi": "मुझे मारा गया है और ख़ून बह रहा है, मुझे अस्पताल जाना है।",
                               "hinglish": "Mujhe maara gaya hai aur khoon beh raha hai, mujhe hospital jaana hai."}),
    ("m07", "M", ("direct",), {"en": "{kin} fainted and is not waking up.",
                               "hi": "{kin_o} को चक्कर आया और होश नहीं आ रहा है।",
                               "hinglish": "{kin_o} ko chakkar aaya aur hosh nahi aa raha hai."}),
    ("m08", "M", ("direct",), {"en": "{kin} got a bad burn on the hand and needs treatment urgently.",
                               "hi": "{kin_o} का हाथ बुरी तरह जल गया है, जल्दी इलाज चाहिए।",
                               "hinglish": "{kin_o} ka haath buri tarah jal gaya hai, jaldi ilaaj chahiye."}),
    # isolation_boycott_displacement
    ("i01", "I", ("direct",), {"en": "The village has stopped us from taking water from the common well.",
                               "hi": "गाँव ने हमें सार्वजनिक कुएँ से पानी लेने से रोक दिया है।",
                               "hinglish": "Gaon ne humein common kuen se paani lene se rok diya hai."}),
    ("i02", "I", ("direct",), {"en": "No shop is allowed to sell anything to our family.",
                               "hi": "किसी दुकान को हमारे परिवार को सामान बेचने की इजाज़त नहीं है।",
                               "hinglish": "Kisi dukaan ko hamare parivaar ko samaan bechne ki ijaazat nahi hai."}),
    ("i03", "I", ("direct",), {"en": "We were forced out of our home and now we have nowhere to stay.",
                               "hi": "हमें घर से निकाल दिया गया और अब रहने की कोई जगह नहीं है।",
                               "hinglish": "Humein ghar se nikaal diya gaya aur ab rehne ki koi jagah nahi hai."}),
    ("i04", "I", ("direct",), {"en": "Nobody in the village is allowed to talk to us anymore.",
                               "hi": "गाँव में किसी को हमसे बात करने की इजाज़त नहीं है।",
                               "hinglish": "Gaon mein kisi ko humse baat karne ki ijaazat nahi hai."}),
    ("i05", "I", ("direct",), {"en": "They stopped giving us work in the fields because of the complaint.",
                               "hi": "शिकायत की वजह से उन्होंने हमें खेतों में काम देना बंद कर दिया।",
                               "hinglish": "Complaint ki wajah se unhone humein kheton mein kaam dena band kar diya."}),
    ("i06", "I", ("indirect",), {"en": "Our children are not allowed to play with the others, everyone avoids us.",
                                 "hi": "हमारे बच्चों को दूसरों के साथ खेलने नहीं दिया जाता, सब हमसे दूर रहते हैं।",
                                 "hinglish": "Hamare bachchon ko doosron ke saath khelne nahi diya jaata, sab humse door rehte hain."}),
    ("i07", "I", ("direct",), {"en": "We have been told to leave the village by the end of the month.",
                               "hi": "हमसे कहा गया है कि महीने के आख़िर तक गाँव छोड़ दो।",
                               "hinglish": "Humse kaha gaya hai ki mahine ke aakhir tak gaon chhod do."}),
    ("i08", "I", ("direct",), {"en": "The panchayat decided that no one should help our family.",
                               "hi": "पंचायत ने तय किया है कि कोई हमारे परिवार की मदद नहीं करेगा।",
                               "hinglish": "Panchayat ne tay kiya hai ki koi hamare parivaar ki madad nahi karega."}),
    # legal_urgency
    ("l01", "L", ("direct",), {"en": "The police refused to register my FIR.",
                               "hi": "पुलिस ने मेरी FIR दर्ज करने से मना कर दिया।",
                               "hinglish": "Police ne meri FIR darj karne se mana kar diya."}),
    ("l02", "L", ("direct",), {"en": "I filed a complaint weeks ago but nobody has taken any action.",
                               "hi": "मैंने हफ़्तों पहले शिकायत की थी पर किसी ने कोई कार्रवाई नहीं की।",
                               "hinglish": "Maine hafton pehle complaint ki thi par kisi ne koi karwai nahi ki."}),
    ("l03", "L", ("direct",), {"en": "My court hearing is next week and I don't know what to do.",
                               "hi": "मेरी अदालत की सुनवाई अगले हफ़्ते है और मुझे नहीं पता क्या करूँ।",
                               "hinglish": "Meri court ki sunwai agle hafte hai aur mujhe nahi pata kya karun."}),
    ("l04", "L", ("direct",), {"en": "At the police station they sent me away without writing my case.",
                               "hi": "थाने में मेरा मामला लिखे बिना मुझे लौटा दिया गया।",
                               "hinglish": "Thane mein mera maamla likhe bina mujhe lauta diya gaya."}),
    ("l05", "L", ("direct",), {"en": "I need help understanding how to file a complaint.",
                               "hi": "मुझे समझना है कि शिकायत कैसे दर्ज करें।",
                               "hinglish": "Mujhe samajhna hai ki complaint kaise darj karein."}),
    ("l06", "L", ("direct",), {"en": "They are asking me for money before they will register my complaint.",
                               "hi": "शिकायत दर्ज करने से पहले मुझसे पैसे माँगे जा रहे हैं।",
                               "hinglish": "Complaint darj karne se pehle mujhse paise maange ja rahe hain."}),
    ("l07", "L", ("direct",), {"en": "My lawyer stopped answering and the hearing date is close.",
                               "hi": "मेरे वकील ने फ़ोन उठाना बंद कर दिया और सुनवाई की तारीख़ पास है।",
                               "hinglish": "Mere vakeel ne phone uthana band kar diya aur sunwai ki date paas hai."}),
    ("l08", "L", ("direct",), {"en": "I want to know the status of my case and how compensation works.",
                               "hi": "मुझे अपने केस की स्थिति और मुआवज़े की प्रक्रिया जाननी है।",
                               "hinglish": "Mujhe apne case ka status aur muavze ka process jaanna hai."}),
    # communication_safety_coercion
    ("k01", "K", ("direct",), {"en": "I can't talk freely, someone is sitting right next to me.",
                               "hi": "मैं खुलकर बात नहीं कर सकती, कोई मेरे पास ही बैठा है।",
                               "hinglish": "Main khulkar baat nahi kar sakti, koi mere paas hi baitha hai."}),
    ("k02", "K", ("direct",), {"en": "Someone checks my phone every day, so I have to be careful.",
                               "hi": "कोई रोज़ मेरा फ़ोन देखता है, इसलिए मुझे सावधान रहना पड़ता है।",
                               "hinglish": "Koi roz mera phone check karta hai, isliye mujhe dhyaan rakhna padta hai."}),
    ("k03", "KT", ("direct",), {"en": "They are forcing me to take back my complaint.",
                                "hi": "वे मुझ पर अपनी शिकायत वापस लेने का दबाव डाल रहे हैं।",
                                "hinglish": "Woh mujh pe apni complaint wapas lene ka dabaav daal rahe hain."}),
    ("k04", "K", ("direct",), {"en": "I am being told to keep quiet about what happened.",
                               "hi": "मुझसे कहा जा रहा है कि जो हुआ उसके बारे में चुप रहूँ।",
                               "hinglish": "Mujhse kaha ja raha hai ki jo hua uske baare mein chup rahun."}),
    ("k05", "K", ("indirect",), {"en": "Please don't call back, they listen to my calls.",
                                 "hi": "कृपया वापस फ़ोन मत करना, वे मेरी बातें सुनते हैं।",
                                 "hinglish": "Please wapas phone mat karna, woh meri baatein sunte hain."}),
    ("k06", "KT", ("direct",), {"en": "My family is pressuring me to withdraw the case.",
                                "hi": "मेरा परिवार मुझ पर केस वापस लेने का दबाव डाल रहा है।",
                                "hinglish": "Mera parivaar mujh pe case wapas lene ka dabaav daal raha hai."}),
    ("k07", "K", ("direct",), {"en": "I can only write when nobody is around because they read my messages.",
                               "hi": "मैं तभी लिख पाती हूँ जब कोई आसपास न हो, क्योंकि वे मेरे संदेश पढ़ते हैं।",
                               "hinglish": "Main tabhi likh paati hoon jab koi aas paas na ho, kyunki woh mere messages padhte hain."}),
    ("k08", "KT", ("conditional",), {"en": "They said if I speak to anyone about this, things will get worse for us.",
                                     "hi": "उन्होंने कहा है कि अगर मैंने किसी से इस बारे में बात की तो हमारे लिए और बुरा होगा।",
                                     "hinglish": "Unhone kaha hai ki agar maine kisi se is baare mein baat ki toh hamare liye aur bura hoga."}),
    # explicit_human_request
    ("h01", "H", ("direct",), {"en": "Can I please talk to a real person?",
                               "hi": "क्या मैं किसी असली इंसान से बात कर सकती हूँ?",
                               "hinglish": "Kya main kisi asli insaan se baat kar sakti hoon?"}),
    ("h02", "H", ("direct",), {"en": "I want to speak to someone from the helpline.",
                               "hi": "मुझे हेल्पलाइन के किसी व्यक्ति से बात करनी है।",
                               "hinglish": "Mujhe helpline ke kisi insaan se baat karni hai."}),
    ("h03", "H", ("direct",), {"en": "Please connect me to a human, not a machine.",
                               "hi": "कृपया मुझे मशीन से नहीं, किसी इंसान से जोड़िए।",
                               "hinglish": "Please mujhe machine se nahi, kisi insaan se jodiye."}),
    ("h04", "H", ("direct",), {"en": "Is there an officer I can talk to directly?",
                               "hi": "क्या कोई अधिकारी है जिससे मैं सीधे बात कर सकूँ?",
                               "hinglish": "Kya koi officer hai jisse main seedhe baat kar sakun?"}),
    ("h05", "H", ("direct",), {"en": "I need to talk to a person about this.",
                               "hi": "मुझे इस बारे में किसी व्यक्ति से बात करनी है।",
                               "hinglish": "Mujhe is baare mein kisi insaan se baat karni hai."}),
    ("h06", "H", ("direct",), {"en": "Can someone from your team call me back?",
                               "hi": "क्या आपकी टीम से कोई मुझे वापस फ़ोन कर सकता है?",
                               "hinglish": "Kya aapki team se koi mujhe wapas phone kar sakta hai?"}),
    ("h07", "H", ("direct",), {"en": "Please let me speak to a counsellor.",
                               "hi": "कृपया मेरी किसी काउंसलर से बात करवाइए।",
                               "hinglish": "Please meri kisi counsellor se baat karwaiye."}),
    ("h08", "H", ("indirect",), {"en": "I don't want to type anymore, I want a real person to help me.",
                                 "hi": "मुझे और टाइप नहीं करना, मुझे कोई असली इंसान मदद करे।",
                                 "hinglish": "Mujhe aur type nahi karna, mujhe koi asli insaan madad kare."}),
    # negation: risk vocabulary negated in its own clause -> negative
    ("n01", "", ("negation",), {"en": "I would never hurt myself, I just need some advice.",
                                "hi": "मैं खुद को कभी नुकसान नहीं पहुँचाऊँगी, मुझे बस सलाह चाहिए।",
                                "hinglish": "Main khud ko kabhi nuksaan nahi pahunchaungi, mujhe bas salah chahiye."}),
    ("n02", "", ("negation",), {"en": "Nobody has threatened us, it was only an argument.",
                                "hi": "किसी ने हमें धमकी नहीं दी, बस बहस हुई थी।",
                                "hinglish": "Kisi ne humein dhamki nahi di, bas behes hui thi."}),
    ("n03", "", ("negation",), {"en": "Nobody is at the door, I am safe at home now.",
                                "hi": "दरवाज़े पर कोई नहीं है, मैं अब घर पर सुरक्षित हूँ।",
                                "hinglish": "Darwaze pe koi nahi hai, main ab ghar pe safe hoon."}),
    ("n04", "", ("negation",), {"en": "I am not thinking of ending my life, I am only tired.",
                                "hi": "मैं अपनी जान देने की नहीं सोच रही, बस थकी हुई हूँ।",
                                "hinglish": "Main apni jaan dene ki nahi soch rahi, bas thaki hui hoon."}),
    ("n05", "", ("negation",), {"en": "There is no injury, everyone at home is fine.",
                                "hi": "किसी को चोट नहीं लगी, घर पर सब ठीक हैं।",
                                "hinglish": "Kisi ko chot nahi lagi, ghar pe sab theek hain."}),
    ("n06", "", ("negation",), {"en": "We have not been stopped from anything, the neighbours are supportive.",
                                "hi": "हमें किसी चीज़ से रोका नहीं गया, पड़ोसी साथ दे रहे हैं।",
                                "hinglish": "Humein kisi cheez se roka nahi gaya, padosi saath de rahe hain."}),
    ("n07", "", ("negation",), {"en": "I don't want to die, I want things to change.",
                                "hi": "मैं मरना नहीं चाहता, मैं चाहता हूँ कि हालात बदलें।",
                                "hinglish": "Main marna nahi chahta, main chahta hoon ki halaat badlein."}),
    ("n08", "", ("negation",), {"en": "No one is listening to my calls, I can talk openly.",
                                "hi": "मेरी बातें कोई नहीं सुन रहा, मैं खुलकर बात कर सकती हूँ।",
                                "hinglish": "Meri baatein koi nahi sun raha, main khulkar baat kar sakti hoon."}),
    # quotation: risk words only as someone else's words or media -> negative
    ("q01", "", ("quotation",), {"en": "In the film the hero says 'I want to die', and it made me cry.",
                                 "hi": "फ़िल्म में हीरो कहता है 'मैं मरना चाहता हूँ', यह देखकर मैं रो पड़ी।",
                                 "hinglish": "Film mein hero kehta hai 'main marna chahta hoon', dekh ke main ro padi."}),
    ("q02", "", ("quotation",), {"en": "The news story said 'men attacked a house tonight', it was about another state.",
                                 "hi": "ख़बर में था 'आदमियों ने आज रात एक घर पर हमला किया', वह दूसरे राज्य की बात थी।",
                                 "hinglish": "News mein tha 'aadmiyon ne aaj raat ek ghar pe hamla kiya', woh doosre state ki baat thi."}),
    ("q03", "", ("quotation",), {"en": "In the game chat someone typed 'I will finish you', but it was only a game.",
                                 "hi": "गेम की चैट में किसी ने लिखा 'मैं तुम्हें ख़त्म कर दूँगा', पर वह बस खेल था।",
                                 "hinglish": "Game ki chat mein kisi ne likha 'main tumhe khatam kar dunga', par woh bas game tha."}),
    ("q04", "", ("quotation",), {"en": "The song goes 'nobody should live like this', I keep humming it.",
                                 "hi": "गाने के बोल हैं 'कोई ऐसे न जिए', मैं उसे गुनगुनाती रहती हूँ।",
                                 "hinglish": "Gaane ke bol hain 'koi aise na jiye', main use gungunati rehti hoon."}),
    ("q05", "", ("quotation",), {"en": "The poster said 'call now if you are in danger', I am just asking what it means.",
                                 "hi": "पोस्टर पर लिखा था 'ख़तरे में हों तो अभी फ़ोन करें', मैं बस उसका मतलब पूछ रही हूँ।",
                                 "hinglish": "Poster pe likha tha 'khatre mein ho toh abhi phone karein', main bas uska matlab pooch rahi hoon."}),
    # attribution: risk belongs to a third party's report -> negative for the speaker
    ("a01", "", ("attribution",), {"en": "My neighbour told me her cousin once wanted to end his life.",
                                   "hi": "मेरी पड़ोसन ने बताया कि उसके चचेरे भाई ने कभी जान देने की सोची थी।",
                                   "hinglish": "Meri padosan ne bataya ki uske cousin ne kabhi jaan dene ki sochi thi."}),
    ("a02", "", ("attribution",), {"en": "People in the next town say there was a fight there last month.",
                                   "hi": "अगले कस्बे के लोग कहते हैं कि वहाँ पिछले महीने लड़ाई हुई थी।",
                                   "hinglish": "Agle kasbe ke log kehte hain ki wahan pichhle mahine ladai hui thi."}),
    ("a03", "", ("attribution",), {"en": "A teacher said a student in her class was being bullied.",
                                   "hi": "एक टीचर ने बताया कि उनकी क्लास के एक बच्चे को तंग किया जा रहा था।",
                                   "hinglish": "Ek teacher ne bataya ki unki class ke ek bachche ko tang kiya ja raha tha."}),
    ("a04", "", ("attribution",), {"en": "I read that in some villages families are refused water, is that true?",
                                   "hi": "मैंने पढ़ा कि कुछ गाँवों में परिवारों को पानी नहीं दिया जाता, क्या यह सच है?",
                                   "hinglish": "Maine padha ki kuch gaon mein parivaaron ko paani nahi diya jaata, kya yeh sach hai?"}),
    ("a05", "", ("attribution",), {"en": "My friend says his uncle had to go to court over land.",
                                   "hi": "मेरा दोस्त कहता है कि उसके चाचा को ज़मीन के मामले में कोर्ट जाना पड़ा।",
                                   "hinglish": "Mera dost kehta hai ki uske chacha ko zameen ke maamle mein court jaana pada."}),
    # historical: past and resolved -> negative now
    ("p01", "", ("historical",), {"en": "Two years ago I felt like ending my life, but now I am much better.",
                                  "hi": "दो साल पहले मुझे जान देने का मन करता था, पर अब मैं बहुत बेहतर हूँ।",
                                  "hinglish": "Do saal pehle mujhe jaan dene ka mann karta tha, par ab main bahut behtar hoon."}),
    ("p02", "", ("historical",), {"en": "Last year some men threatened us, but that matter is settled now.",
                                  "hi": "पिछले साल कुछ लोगों ने धमकाया था, पर वह मामला अब सुलझ गया है।",
                                  "hinglish": "Pichhle saal kuch logon ne dhamkaya tha, par woh maamla ab sulajh gaya hai."}),
    ("p03", "", ("historical",), {"en": "Long ago my father was injured at work, he is fully fine now.",
                                  "hi": "बहुत पहले मेरे पिता को काम पर चोट लगी थी, अब वे बिल्कुल ठीक हैं।",
                                  "hinglish": "Bahut pehle mere papa ko kaam pe chot lagi thi, ab woh bilkul theek hain."}),
    ("p04", "", ("historical",), {"en": "Earlier we were kept away from the well, but now everyone shares it again.",
                                  "hi": "पहले हमें कुएँ से दूर रखा जाता था, पर अब सब मिलकर इस्तेमाल करते हैं।",
                                  "hinglish": "Pehle humein kuen se door rakha jaata tha, par ab sab milkar use karte hain."}),
    ("p05", "", ("historical",), {"en": "My case was closed last year and I have no hearing pending.",
                                  "hi": "मेरा केस पिछले साल बंद हो गया था और कोई सुनवाई बाकी नहीं है।",
                                  "hinglish": "Mera case pichhle saal band ho gaya tha aur koi sunwai baaki nahi hai."}),
    ("p06", "", ("historical",), {"en": "Once I was scared to speak, but these days I talk to anyone freely.",
                                  "hi": "एक समय मुझे बोलने से डर लगता था, पर आजकल मैं किसी से भी खुलकर बात करती हूँ।",
                                  "hinglish": "Ek samay mujhe bolne se dar lagta tha, par aajkal main kisi se bhi khulkar baat karti hoon."}),
    # safe controls
    ("s01", "", ("safe_control",), {"en": "I wanted to ask about the office timings.",
                                    "hi": "मुझे दफ़्तर के समय के बारे में पूछना था।",
                                    "hinglish": "Mujhe office ke timing ke baare mein poochna tha."}),
    ("s02", "", ("safe_control",), {"en": "Thank you, that is all for now.",
                                    "hi": "धन्यवाद, अभी के लिए इतना ही।",
                                    "hinglish": "Shukriya, abhi ke liye itna hi."}),
    ("s03", "", ("safe_control",), {"en": "My question is about the scholarship form.",
                                    "hi": "मेरा सवाल छात्रवृत्ति के फ़ॉर्म के बारे में है।",
                                    "hinglish": "Mera sawaal scholarship form ke baare mein hai."}),
    ("s04", "", ("safe_control",), {"en": "The weather has been very hot these days.",
                                    "hi": "आजकल मौसम बहुत गरम है।",
                                    "hinglish": "Aajkal mausam bahut garam hai."}),
    ("s05", "", ("safe_control",), {"en": "I want to update my contact details.",
                                    "hi": "मुझे अपना संपर्क विवरण बदलना है।",
                                    "hinglish": "Mujhe apni contact details update karni hain."}),
    ("s06", "", ("safe_control",), {"en": "Where is the nearest district office?",
                                    "hi": "सबसे पास का ज़िला कार्यालय कहाँ है?",
                                    "hinglish": "Sabse paas ka district office kahan hai?"}),
    ("s07", "", ("safe_control",), {"en": "Okay, I understand what you said.",
                                    "hi": "ठीक है, मैं समझ गई।",
                                    "hinglish": "Theek hai, main samajh gayi."}),
    ("s08", "", ("safe_control",), {"en": "I will share the remaining details tomorrow.",
                                    "hi": "बाकी जानकारी मैं कल दूँगा।",
                                    "hinglish": "Baaki jaankari main kal dunga."}),
    # low-distress controls: sadness, stress, mild pain; no risk category
    ("w01", "", ("low_distress",), {"en": "I feel very tired and stressed about money.",
                                    "hi": "मैं पैसों को लेकर बहुत थकी और परेशान हूँ।",
                                    "hinglish": "Main paison ko lekar bahut thaki aur pareshaan hoon."}),
    ("w02", "", ("low_distress",), {"en": "I am sad because the crops failed this year.",
                                    "hi": "इस साल फ़सल ख़राब हो गई, इसलिए मैं उदास हूँ।",
                                    "hinglish": "Is saal fasal kharaab ho gayi, isliye main udaas hoon."}),
    ("w03", "", ("low_distress",), {"en": "I have been worried and not sleeping well.",
                                    "hi": "मैं चिंता में हूँ और ठीक से सो नहीं पा रहा।",
                                    "hinglish": "Main chinta mein hoon aur theek se so nahi pa raha."}),
    ("w04", "", ("low_distress",), {"en": "I feel lonely since my children moved to the city.",
                                    "hi": "बच्चों के शहर जाने के बाद से मैं अकेली महसूस करती हूँ।",
                                    "hinglish": "Bachchon ke shehar jaane ke baad se main akeli feel karti hoon."}),
    ("w05", "", ("low_distress",), {"en": "Things are tense at work and I feel anxious.",
                                    "hi": "काम पर माहौल तनाव भरा है और मुझे घबराहट होती है।",
                                    "hinglish": "Kaam pe mahaul tense hai aur mujhe ghabrahat hoti hai."}),
    ("w06", "", ("low_distress",), {"en": "I cried a lot today, but I will manage.",
                                    "hi": "आज मैं बहुत रोई, पर मैं सँभाल लूँगी।",
                                    "hinglish": "Aaj main bahut royi, par main sambhaal lungi."}),
    ("w07", "", ("low_distress",), {"en": "I am upset that people gossip about us.",
                                    "hi": "लोग हमारे बारे में बातें बनाते हैं, इससे मैं दुखी हूँ।",
                                    "hinglish": "Log hamare baare mein baatein banate hain, isse main dukhi hoon."}),
    ("w08", "", ("low_distress",), {"en": "My back hurts a little after work, nothing serious.",
                                    "hi": "काम के बाद कमर में थोड़ा दर्द होता है, कुछ गंभीर नहीं।",
                                    "hinglish": "Kaam ke baad kamar mein thoda dard hota hai, kuch serious nahi."}),
    # expected abstention: too little information to label anything
    ("x01", "", ("expected_abstention",), {"en": "I don't know how to explain it.",
                                           "hi": "मुझे समझ नहीं आ रहा कैसे बताऊँ।",
                                           "hinglish": "Mujhe samajh nahi aa raha kaise bataun."}),
    ("x02", "", ("expected_abstention",), {"en": "Something happened, but I am not sure I should say.",
                                           "hi": "कुछ हुआ है, पर पता नहीं बताना चाहिए या नहीं।",
                                           "hinglish": "Kuch hua hai, par pata nahi batana chahiye ya nahi."}),
    ("x03", "", ("expected_abstention",), {"en": "It is complicated at home.",
                                           "hi": "घर पर बात उलझी हुई है।",
                                           "hinglish": "Ghar pe baat uljhi hui hai."}),
    ("x04", "", ("expected_abstention",), {"en": "Can we talk later?",
                                           "hi": "क्या हम बाद में बात कर सकते हैं?",
                                           "hinglish": "Kya hum baad mein baat kar sakte hain?"}),
    ("x05", "", ("expected_abstention",), {"en": "I am not sure what to say.",
                                           "hi": "मुझे नहीं पता क्या कहूँ।",
                                           "hinglish": "Mujhe nahi pata kya kahun."}),
    ("x06", "", ("expected_abstention",), {"en": "Hmm, let me think.",
                                           "hi": "हम्म, सोचने दीजिए।",
                                           "hinglish": "Hmm, sochne dijiye."}),
]

#: Neutral assistant turns for multi-turn records (not labelled; the pipeline reads victim turns).
ASSISTANT_TURNS = {
    "en": ["I am listening. Can you tell me a little more?", "Thank you for telling me. What happened next?",
           "You can take your time."],
    "hi": ["मैं सुन रहा हूँ। क्या आप थोड़ा और बता सकते हैं?", "बताने के लिए धन्यवाद। फिर क्या हुआ?",
           "आप आराम से बताइए।"],
    "hinglish": ["Main sun raha hoon. Kya aap thoda aur bata sakte hain?", "Batane ke liye shukriya. Phir kya hua?",
                 "Aap aaram se bataiye."],
}


# --- deterministic helpers -------------------------------------------------------------------


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in (SEED, *parts)).encode("utf-8")).hexdigest()[:12], 16)


def label_set(codes: str) -> Dict[str, bool]:
    positive = {_CODE[c] for c in codes}
    return {name: name in positive for name in LABELS}


def stratum(template: T) -> str:
    """Positives stratify by label set, controls by their phenomenon."""
    _, codes, phen, _ = template
    return codes if codes else "none:" + phen[0]


def assign_splits(templates: Sequence[T] = TEMPLATES) -> Dict[str, str]:
    """80/10/10 by template, per stratum, by hash order. Every template sits in exactly one split."""
    by_stratum: Dict[str, List[str]] = {}
    for t in templates:
        by_stratum.setdefault(stratum(t), []).append(t[0])
    out: Dict[str, str] = {}
    for name, keys in sorted(by_stratum.items()):
        ordered = sorted(keys, key=lambda k: _h("split", k))
        n = len(ordered)
        n_val = max(1, round(n * 0.1)) if n >= 3 else 0
        n_test = max(1, round(n * 0.1)) if n >= 3 else 0
        for i, key in enumerate(ordered):
            out[key] = ("validation" if i < n_val else "synthetic_development_test" if i < n_val + n_test
                        else "train")
    return out


def _misspell(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if w.isascii() and w.isalpha() and len(w) > 4]
    if not idx:
        return text
    i = idx[rng.randrange(len(idx))]
    w = words[i]
    j = rng.randrange(1, len(w) - 2)
    words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:] if rng.random() < 0.5 else w[:j] + w[j + 1:]
    return " ".join(words)


def _punctuation(text: str, rng: random.Random) -> str:
    choice = rng.randrange(4)
    if choice == 0:
        return text.rstrip(".।?!").strip()
    if choice == 1:
        return text.replace(", ", ",").replace(" ", "  ", 1)
    if choice == 2:
        return text.rstrip(".।") + "!!!"
    return text.lower() if text.isascii() else text + " ..."


def _unicode(text: str, rng: random.Random) -> str:
    if text.isascii():
        words = text.split(" ")
        i = rng.randrange(len(words))
        words[i] = words[i][:1] + "​" + words[i][1:]
        return " ".join(words)
    return unicodedata.normalize("NFD", text).replace(" ", " ‌", 1)


TRANSFORMS = (("misspelling", _misspell), ("punctuation_spacing", _punctuation), ("unicode_variant", _unicode))


def render(template: T, language: str, variant: int) -> Tuple[str, List[str]]:
    key, _, phen, texts = template
    rng = random.Random(_h("render", key, language, variant))
    fill = {slot: FILLERS[language][slot][rng.randrange(len(FILLERS[language][slot]))]
            for slot in ("who", "time", "kin", "kin_o", "place")}
    text = texts[language].format(**fill)
    text = text[:1].upper() + text[1:] if language != "hi" else text
    applied = []
    if variant % 4 == 1:  # every fourth variant keeps the clean text; others get one surface change
        name, fn = TRANSFORMS[rng.randrange(len(TRANSFORMS))]
        text, applied = fn(text, rng), [name]
    elif variant % 4 == 2:
        name, fn = TRANSFORMS[(variant // 4) % len(TRANSFORMS)]
        text, applied = fn(text, rng), [name]
    return text, applied


def _phenomena(language: str, base: Iterable[str], extra: Iterable[str]) -> List[str]:
    tags = set(base) | set(extra)
    if language == "hinglish":
        tags.add("code_switching")
    return sorted(tags)


def _record(rid: str, family: str, split: str, language: str, turns: List[Dict[str, Any]], labels: Dict[str, bool],
            phenomena: List[str], templates: List[str], turn_templates: List[Optional[str]]) -> Dict[str, Any]:
    return {"id": rid, "family": family, "templates": templates, "turn_templates": turn_templates,
            "split": split, "language": language,
            "channel": "mobile_chat", "turns": turns, "labels": labels, "phenomena": phenomena,
            "generator_version": GENERATOR_VERSION, "fictional": True}


def generate(templates: Sequence[T] = TEMPLATES, variants: int = VARIANTS_PER_TEMPLATE,
             multi_turn: Mapping[str, int] = MULTI_TURN_PER_SPLIT_LANGUAGE) -> List[Dict[str, Any]]:
    splits = assign_splits(templates)
    by_key = {t[0]: t for t in templates}
    records: List[Dict[str, Any]] = []
    seen_text: Set[Tuple[str, str]] = set()
    for t in templates:
        key, codes, phen, _ = t
        for language in LANGUAGES:
            for v in range(variants):
                text, applied = render(t, language, v)
                if (language, text) in seen_text:
                    continue
                seen_text.add((language, text))
                records.append(_record(f"FIC-{key}-{language}-v{v:02d}", f"{key}", splits[key], language,
                                       [{"id": "t1", "speaker": "victim", "text": text, "state": "S2"}],
                                       label_set(codes), _phenomena(language, phen + ("single_turn",), applied),
                                       [key], [key]))
    for split in SPLITS:
        pool = [by_key[k] for k, s in sorted(splits.items()) if s == split]
        risk = [t for t in pool if t[1]]
        other = [t for t in pool if not t[1]]
        for language in LANGUAGES:
            for n in range(multi_turn.get(split, 0)):
                rng = random.Random(_h("multi", split, language, n))
                n_victim = 2 + rng.randrange(2)
                chosen = [risk[rng.randrange(len(risk))]] if risk else []
                while len(chosen) < n_victim:
                    source = risk if (rng.random() < 0.45 and risk) else other
                    if not source:
                        break
                    chosen.append(source[rng.randrange(len(source))])
                if rng.random() < 0.2 and other:  # a negative-only multi-turn control
                    chosen = [other[rng.randrange(len(other))] for _ in range(n_victim)]
                rng.shuffle(chosen)
                turns, labels, phen, used, turn_keys = [], {name: False for name in LABELS}, set(), [], []
                for i, t in enumerate(chosen):
                    if i and rng.random() < 0.6:
                        turns.append({"id": f"t{len(turns) + 1}", "speaker": "assistant", "state": "S2",
                                      "text": ASSISTANT_TURNS[language][rng.randrange(len(ASSISTANT_TURNS[language]))]})
                        turn_keys.append(None)
                    text, applied = render(t, language, rng.randrange(variants))
                    turns.append({"id": f"t{len(turns) + 1}", "speaker": "victim", "text": text, "state": "S2"})
                    turn_keys.append(t[0])
                    for name, value in label_set(t[1]).items():
                        labels[name] = labels[name] or value
                    phen |= set(t[2]) | set(applied)
                    used.append(t[0])
                family = "multi:" + "+".join(sorted(set(used)))
                records.append(_record(f"FIC-M-{split[:3]}-{language}-{n:04d}", family, split, language, turns, labels,
                                       _phenomena(language, phen | {"multi_turn"} |
                                                  ({"multi_label"} if sum(labels.values()) > 1 else set()), ()),
                                       sorted(set(used)), turn_keys))
    for r in records:
        if sum(r["labels"].values()) > 1:
            r["phenomena"] = sorted(set(r["phenomena"]) | {"multi_label"})
    return records


# --- contamination ---------------------------------------------------------------------------


def exposed_index() -> Dict[str, Any]:
    return lk.build_index(files=tuple(lk.EXPOSED_FILES) + EXTRA_EXPOSED_FILES)


def contamination(records: Sequence[Mapping[str, Any]], index: Optional[Mapping[str, Any]] = None
                  ) -> Dict[str, Any]:
    """Block every record with a leakage block, high overlap or shared distinctive phrase; then every
    record that shares a template with a blocked one (template lineage)."""
    index = index if index is not None else exposed_index()
    blocked_templates: Set[str] = set()
    reasons: Counter = Counter()

    def hits(turns: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [f for f in lk.check({"turns": list(turns)}, index) if f["severity"] == "block"
                or f["check"] in ("high_token_overlap", "shared_distinctive_phrase")]

    for r in records:
        # each victim turn on its own: a hit is attributed to that turn's template
        for turn, key in zip(r["turns"], r["turn_templates"]):
            if key is None:
                continue
            found = hits([{"id": "t1", "speaker": "victim", "text": turn["text"]}])
            if found:
                blocked_templates.add(key)
                reasons.update(f["check"] for f in found)
        # the whole scenario (exact, reordered, content hash): a hit blocks every template in it
        if len(r["templates"]) > 1:
            found = [f for f in hits(r["turns"]) if f["check"] in
                     ("exact_normalized_match", "content_hash_match", "reordered_turn_match")]
            if found:
                blocked_templates.update(r["templates"])
                reasons.update(f["check"] for f in found)
    kept = [r for r in records if not set(r["templates"]) & blocked_templates]
    return {"kept": kept, "blocked_templates": sorted(blocked_templates), "blocked_records": len(records) - len(kept),
            "reasons": dict(reasons)}


# --- build -----------------------------------------------------------------------------------


def split_isolation_errors(records: Sequence[Mapping[str, Any]]) -> List[str]:
    owner: Dict[str, str] = {}
    errors = []
    for r in records:
        for key in r["templates"]:
            if owner.setdefault(key, r["split"]) != r["split"]:
                errors.append(f"template {key} appears in {owner[key]} and {r['split']}")
    return sorted(set(errors))


def blocked_templates(templates: Sequence[T] = TEMPLATES, index: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Template-level screening before splits are assigned: every rendered variant of every language."""
    singles = generate(templates, multi_turn={})
    return contamination(singles, index)


def build(training: Path) -> Dict[str, Any]:
    index = exposed_index()
    screen = blocked_templates(TEMPLATES, index)
    surviving = [t for t in TEMPLATES if t[0] not in set(screen["blocked_templates"])]
    records = generate(surviving)
    result = contamination(records, index)  # second pass also covers whole multi-turn scenarios
    kept = result["kept"]
    result["blocked_templates"] = sorted(set(result["blocked_templates"]) | set(screen["blocked_templates"]))
    result["blocked_records"] += screen["blocked_records"]
    for k, v in screen["reasons"].items():
        result["reasons"][k] = result["reasons"].get(k, 0) + v
    errors = split_isolation_errors(kept)
    if errors:
        raise ValueError("split isolation failed: " + "; ".join(errors[:5]))
    out = paths.confined(training, *paths.FICTIONAL_CORPUS.split("/"))
    out.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    partial = out / "records.jsonl.partial"
    with open(partial, "w", encoding="utf-8", newline="\n") as fh:
        for r in kept:
            line = json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
            digest.update(line.encode("utf-8"))
            fh.write(line)
    partial.replace(out / "records.jsonl")
    manifest = {"generator_version": GENERATOR_VERSION, "seed": SEED, "labels": list(LABELS),
                "records": len(kept), "records_sha256": digest.hexdigest(),
                "templates": len(TEMPLATES), "template_bank_sha256": template_bank_hash(),
                "blocked": {k: result[k] for k in ("blocked_templates", "blocked_records", "reasons")},
                "split_note": SPLIT_NOTE, **composition(kept)}
    paths.write_json(out / "manifest.json", manifest)
    return manifest


def template_bank_hash() -> str:
    return hashlib.sha256(json.dumps(TEMPLATES, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def composition(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_split: Dict[str, Counter] = {s: Counter() for s in SPLITS}
    for r in records:
        c = by_split[r["split"]]
        c["records"] += 1
        c[f"lang:{r['language']}"] += 1
        c["multi_turn" if "multi_turn" in r["phenomena"] else "single_turn"] += 1
        c["all_negative" if not any(r["labels"].values()) else "any_positive"] += 1
        for name, value in r["labels"].items():
            c[f"label:{name}"] += bool(value)
        for p in r["phenomena"]:
            c[f"phenomenon:{p}"] += 1
    return {"splits": {s: dict(sorted(c.items())) for s, c in by_split.items()}}


def load(training: Path) -> List[Dict[str, Any]]:
    path = paths.confined(training, *paths.FICTIONAL_CORPUS.split("/"), "records.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
