"""Versioned, deterministic legal-information content for NyaySetu.

The content in this module is intentionally general. It is designed to help a
user organise facts, preserve documents, identify urgent situations, and
decide whether to book a lawyer. It must never be presented as personalised
legal advice or as a prediction of an outcome.

All content changes are tied to ``LEGAL_CONTENT_VERSION`` and the externally
configured ``LEGAL_CONTENT_REVIEWED_ON`` date. Production readiness checks
require the review date so an operator cannot accidentally publish an
unreviewed revision.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from category_labels import CATEGORY_LABELS
from config import LEGAL_CONTENT_REVIEWED_ON, LEGAL_CONTENT_VERSION
from subcategory_labels import SUBCATEGORY_LABELS


CATEGORY_SUBCATEGORIES = {
    "Family": [
        "Divorce",
        "Separation",
        "Maintenance",
        "Alimony",
        "Domestic Violence",
        "Child Custody",
        "Dowry Case",
        "Other Family Issue",
        "Not Sure",
    ],
    "Criminal": [
        "Police Case",
        "Bail Matter",
        "Cyber Crime",
        "Theft or Assault",
        "False FIR",
        "Police Harassment",
        "Not Sure",
    ],
    "Accident": [
        "Road Accident",
        "MACT Claim",
        "Personal Injury",
        "Accidental Death",
        "Hit and Run",
        "Not Sure",
    ],
    "Property": [
        "Property Dispute",
        "Illegal Possession",
        "Builder Issue",
        "Sale Deed Issue",
        "Partition Dispute",
        "Injunction Matter",
        "Not Sure",
    ],
    "Business": [
        "Cheque Bounce",
        "Money Recovery",
        "Contract Dispute",
        "Partner Dispute",
        "Business Fraud",
        "Not Sure",
    ],
    "Job": [
        "Wrongful Termination",
        "Unpaid Salary",
        "Workplace Harassment",
        "Service Dispute",
        "PF or Gratuity Issue",
        "Not Sure",
    ],
    "Consumer": [
        "Consumer Complaint",
        "Refund Issue",
        "Online Fraud",
        "Service Deficiency",
        "Product Defect",
        "Not Sure",
    ],
    "Banking": [
        "Loan Harassment",
        "Unauthorized Transaction",
        "Loan or Card Dispute",
        "Account Freeze",
        "Insurance Claim",
        "Not Sure",
    ],
    "Other": [
        "General Legal Query",
        "Legal Notice",
        "Draft Agreement",
        "Document Review",
        "Not Sure",
    ],
}


_UI = {
    "en": {
        "guide_categories": "Choose a legal area",
        "guide_categories_body": "Start with the area closest to your issue.",
        "guide_issues": "Choose your issue",
        "guide_issues_body": "Select the closest option. Choose Not Sure if needed.",
        "guide_row": "Guided information",
        "issue_focus": "For this issue",
        "issue_focus_default": (
            "Record what happened, the dates, the people or organisations "
            "involved, the documents available, and the outcome you want."
        ),
        "questions": "First, think about",
        "actions": "What to do now",
        "documents": "Documents to keep ready",
        "urgent": "Get urgent help when",
        "location": (
            "Law and procedure can vary by facts and location. During booking, "
            "NyaySetu asks for your state and district to route the consultation."
        ),
        "disclaimer": (
            "This is general legal information, not legal advice. Do not rely on "
            "it for a limitation period, court filing, arrest, settlement, or "
            "other time-sensitive decision. A qualified lawyer must review your "
            "specific facts and documents."
        ),
        "version": "Content version",
        "reviewed": "Lawyer-reviewed on",
        "review_pending": "Legal review pending",
        "helpful": "Was this guide helpful?",
        "yes": "Yes, helpful",
        "no": "Need more help",
        "thanks": "Thank you. Your response helps us improve the guides.",
        "more_help": (
            "This guide may not cover your facts. You can choose another guide, "
            "contact support, or book a lawyer consultation."
        ),
        "book": "Book lawyer",
        "support": "Support",
    },
    "hi": {
        "guide_categories": "Legal area chunein",
        "guide_categories_body": "Apne issue ke sabse kareeb legal area se shuru karein.",
        "guide_issues": "Apna issue chunein",
        "guide_issues_body": "Sabse kareeb option chunein. Zarurat ho to Not Sure chunein.",
        "guide_row": "Guided jaankari",
        "issue_focus": "Is issue ke liye",
        "issue_focus_default": (
            "Kya hua, kab hua, kaun involved tha, kaunse documents hain aur "
            "aapko kya outcome chahiye—yeh note karein."
        ),
        "questions": "Pehle yeh sochiye",
        "actions": "Abhi kya karein",
        "documents": "Kaunse documents ready rakhein",
        "urgent": "Turant madad kab lein",
        "location": (
            "Facts aur location ke hisaab se law aur process alag ho sakta hai. "
            "Booking ke waqt NyaySetu state aur district poochkar consultation "
            "route karta hai."
        ),
        "disclaimer": (
            "Yeh sirf general legal information hai, legal advice nahi. Limitation "
            "period, court filing, arrest, settlement ya kisi time-sensitive "
            "decision ke liye sirf is par nirbhar na rahein. Qualified lawyer ko "
            "aapke facts aur documents dekhne honge."
        ),
        "version": "Content version",
        "reviewed": "Lawyer review date",
        "review_pending": "Legal review pending",
        "helpful": "Kya yeh guide helpful thi?",
        "yes": "Haan, helpful",
        "no": "Aur madad chahiye",
        "thanks": "Dhanyavaad. Aapka response guides improve karne mein madad karta hai.",
        "more_help": (
            "Ho sakta hai yeh guide aapke sab facts cover na kare. Aap doosri "
            "guide, support, ya lawyer consultation choose kar sakte hain."
        ),
        "book": "Lawyer book karein",
        "support": "Support",
    },
    "mr": {
        "guide_categories": "कायदेशीर क्षेत्र निवडा",
        "guide_categories_body": "आपल्या समस्येशी सर्वात जवळचे कायदेशीर क्षेत्र निवडा.",
        "guide_issues": "आपली समस्या निवडा",
        "guide_issues_body": "सर्वात जवळचा पर्याय निवडा. गरज असल्यास निश्चित नाही निवडा.",
        "guide_row": "मार्गदर्शित माहिती",
        "issue_focus": "या समस्येसाठी",
        "issue_focus_default": (
            "काय घडले, तारीखा, संबंधित व्यक्ती किंवा संस्था, उपलब्ध कागदपत्रे "
            "आणि तुम्हाला हवा असलेला निकाल याची नोंद करा."
        ),
        "questions": "प्रथम याचा विचार करा",
        "actions": "आता काय करावे",
        "documents": "तयार ठेवायची कागदपत्रे",
        "urgent": "तातडीची मदत कधी घ्यावी",
        "location": (
            "तथ्ये आणि ठिकाणानुसार कायदा व प्रक्रिया बदलू शकते. बुकिंगच्या वेळी "
            "NyaySetu राज्य आणि जिल्हा विचारून सल्लामसलत योग्य ठिकाणी पाठवते."
        ),
        "disclaimer": (
            "ही सर्वसाधारण कायदेशीर माहिती आहे; कायदेशीर सल्ला नाही. मुदत, "
            "न्यायालयीन अर्ज, अटक, तडजोड किंवा इतर तातडीच्या निर्णयासाठी फक्त "
            "यावर अवलंबून राहू नका. पात्र वकिलांनी आपली तथ्ये व कागदपत्रे तपासणे आवश्यक आहे."
        ),
        "version": "माहिती आवृत्ती",
        "reviewed": "वकिलांनी तपासल्याची तारीख",
        "review_pending": "कायदेशीर तपासणी प्रलंबित",
        "helpful": "ही मार्गदर्शिका उपयुक्त होती का?",
        "yes": "होय, उपयुक्त",
        "no": "अधिक मदत हवी",
        "thanks": "धन्यवाद. आपल्या प्रतिसादामुळे मार्गदर्शिका सुधारण्यास मदत होते.",
        "more_help": (
            "ही मार्गदर्शिका आपल्या सर्व तथ्यांना लागू असेलच असे नाही. दुसरी "
            "मार्गदर्शिका, सहाय्य किंवा वकिलांची सल्लामसलत निवडा."
        ),
        "book": "वकील बुक करा",
        "support": "सहाय्य",
    },
}


_GUIDES = {
    "Family": {
        "en": {
            "summary": "Organise the relationship history, present arrangements, finances, children, and the outcome you seek.",
            "questions": [
                "What happened, on which dates, and are any proceedings already pending?",
                "Are children, shared property, maintenance, safety, or residence involved?",
                "What immediate and long-term outcome do you want?",
            ],
            "actions": [
                "Write a short factual timeline without exaggeration.",
                "Keep communication and financial records safely; do not alter evidence.",
                "Avoid signing a settlement or giving up rights without independent advice.",
            ],
            "documents": [
                "Marriage/relationship proof and identity/address documents",
                "Income, bank, property, child, notice, order, and communication records",
            ],
            "urgent": "there is violence, a threat, a child-safety concern, removal from the home, or an imminent court/police date",
        },
        "hi": {
            "summary": "Relationship history, current arrangement, finances, children aur aap kya outcome chahte hain—yeh organise karein.",
            "questions": [
                "Kya hua, kab hua, aur kya koi case/proceeding pehle se pending hai?",
                "Kya children, shared property, maintenance, safety ya residence involved hai?",
                "Aapko turant aur long-term mein kya outcome chahiye?",
            ],
            "actions": [
                "Important facts aur dates ki short timeline likhein.",
                "Communication aur financial records safe rakhein; evidence alter na karein.",
                "Independent advice ke bina settlement ya rights surrender na karein.",
            ],
            "documents": [
                "Marriage/relationship proof aur identity/address documents",
                "Income, bank, property, child, notice, order aur communication records",
            ],
            "urgent": "violence, threat, child-safety concern, ghar se nikala jana, ya turant court/police date ho",
        },
        "mr": {
            "summary": "नात्याचा इतिहास, सध्याची व्यवस्था, आर्थिक बाबी, मुले आणि अपेक्षित निकाल व्यवस्थित नोंदवा.",
            "questions": [
                "काय व केव्हा घडले आणि कोणती कार्यवाही आधीपासून सुरू आहे का?",
                "मुले, संयुक्त मालमत्ता, निर्वाहभत्ता, सुरक्षितता किंवा निवासाचा प्रश्न आहे का?",
                "आपल्याला तातडीने आणि दीर्घकाळात कोणता निकाल हवा आहे?",
            ],
            "actions": [
                "महत्त्वाच्या घटना व तारखांची लहान तथ्यात्मक कालरेषा लिहा.",
                "संवाद व आर्थिक नोंदी सुरक्षित ठेवा; पुराव्यात बदल करू नका.",
                "स्वतंत्र सल्ल्याशिवाय तडजोड किंवा हक्कांचा त्याग करू नका.",
            ],
            "documents": [
                "विवाह/नात्याचा पुरावा आणि ओळख/पत्ता कागदपत्रे",
                "उत्पन्न, बँक, मालमत्ता, मुले, नोटीस, आदेश आणि संवादाच्या नोंदी",
            ],
            "urgent": "हिंसा, धमकी, मुलांच्या सुरक्षिततेचा प्रश्न, घरातून काढणे किंवा जवळची न्यायालय/पोलीस तारीख असेल",
        },
    },
    "Criminal": {
        "en": {
            "summary": "Criminal and police matters can be time-sensitive. Preserve the exact notice, complaint, FIR, and event history.",
            "questions": [
                "Are you the complainant, accused person, witness, or affected family member?",
                "Was any FIR, notice, summons, seizure, arrest, or court date communicated?",
                "What evidence exists, and who currently controls it?",
            ],
            "actions": [
                "Do not ignore a police or court communication.",
                "Preserve original files and make secure copies; do not coach witnesses.",
                "Do not sign an unread statement or publish case details online.",
            ],
            "documents": [
                "FIR/complaint, notices, summons, orders, bail papers, and seizure records",
                "Original messages, call details, photographs, medical records, and witness information",
            ],
            "urgent": "arrest is threatened or occurring, someone is detained/missing, evidence may disappear, or a hearing is imminent",
        },
        "hi": {
            "summary": "Criminal aur police matters time-sensitive ho sakte hain. Exact notice, complaint, FIR aur event history preserve karein.",
            "questions": [
                "Aap complainant, accused, witness ya affected family member hain?",
                "Kya FIR, notice, summons, seizure, arrest ya court date communicate hui hai?",
                "Kaunsa evidence hai aur abhi kis ke control mein hai?",
            ],
            "actions": [
                "Police ya court communication ignore na karein.",
                "Original files preserve karke secure copies banayein; witness ko coach na karein.",
                "Bina padhe statement sign ya case details online publish na karein.",
            ],
            "documents": [
                "FIR/complaint, notices, summons, orders, bail papers aur seizure records",
                "Original messages, call details, photos, medical records aur witness information",
            ],
            "urgent": "arrest ka risk ho, koi detained/missing ho, evidence gayab ho sakta ho, ya hearing bahut paas ho",
        },
        "mr": {
            "summary": "फौजदारी आणि पोलीस प्रकरणे तातडीची असू शकतात. अचूक नोटीस, तक्रार, एफआयआर आणि घटनाक्रम जतन करा.",
            "questions": [
                "आपण तक्रारदार, आरोपी, साक्षीदार की प्रभावित कुटुंबीय आहात?",
                "एफआयआर, नोटीस, समन्स, जप्ती, अटक किंवा न्यायालयीन तारीख कळवली आहे का?",
                "कोणता पुरावा आहे आणि तो सध्या कोणाच्या ताब्यात आहे?",
            ],
            "actions": [
                "पोलीस किंवा न्यायालयीन संदेश दुर्लक्षित करू नका.",
                "मूळ फायली जतन करून सुरक्षित प्रती करा; साक्षीदारांना शिकवू नका.",
                "न वाचलेले निवेदन सही करू नका किंवा प्रकरण ऑनलाइन प्रसिद्ध करू नका.",
            ],
            "documents": [
                "एफआयआर/तक्रार, नोटिसा, समन्स, आदेश, जामीन व जप्ती कागदपत्रे",
                "मूळ संदेश, कॉल तपशील, फोटो, वैद्यकीय नोंदी व साक्षीदार माहिती",
            ],
            "urgent": "अटक होण्याची शक्यता, कोणी ताब्यात/बेपत्ता, पुरावा नष्ट होण्याची शक्यता किंवा जवळची सुनावणी असेल",
        },
    },
    "Accident": {
        "en": {
            "summary": "Record the accident, injuries, vehicles, treatment, reporting, insurance, and financial loss.",
            "questions": [
                "Where and when did it happen, and who was injured?",
                "Were police, hospital, employer, and insurer informed?",
                "Which vehicle, witness, CCTV, treatment, and income-loss records exist?",
            ],
            "actions": [
                "Prioritise medical care and obtain written medical records.",
                "Report accurately and preserve scene/vehicle photographs when safe.",
                "Notify the relevant insurer and avoid undocumented cash settlements.",
            ],
            "documents": [
                "Police report, vehicle/driver/insurance papers, photographs, and witness details",
                "Medical records, bills, disability/income records, and insurer correspondence",
            ],
            "urgent": "medical care is needed, a death or serious injury occurred, a vehicle fled, or evidence may be lost",
        },
        "hi": {
            "summary": "Accident, injuries, vehicles, treatment, reporting, insurance aur financial loss ki details record karein.",
            "questions": [
                "Accident kahan/kab hua aur kaun injured hua?",
                "Kya police, hospital, employer aur insurer ko inform kiya?",
                "Vehicle, witness, CCTV, treatment aur income-loss ke kya records hain?",
            ],
            "actions": [
                "Medical care ko priority dein aur written medical records lein.",
                "Sahi report karein aur safe ho to scene/vehicle photos preserve karein.",
                "Relevant insurer ko inform karein; undocumented cash settlement se bachein.",
            ],
            "documents": [
                "Police report, vehicle/driver/insurance papers, photos aur witness details",
                "Medical records, bills, disability/income records aur insurer communication",
            ],
            "urgent": "medical care chahiye, death/serious injury hui, vehicle bhaag gaya, ya evidence lose ho sakta hai",
        },
        "mr": {
            "summary": "अपघात, दुखापती, वाहने, उपचार, अहवाल, विमा आणि आर्थिक नुकसान नोंदवा.",
            "questions": [
                "अपघात कुठे व केव्हा झाला आणि कोण जखमी झाले?",
                "पोलीस, रुग्णालय, नियोक्ता आणि विमा कंपनीला कळवले का?",
                "वाहन, साक्षीदार, सीसीटीव्ही, उपचार व उत्पन्न नुकसान नोंदी कोणत्या आहेत?",
            ],
            "actions": [
                "वैद्यकीय उपचाराला प्राधान्य द्या आणि लेखी नोंदी घ्या.",
                "अचूक अहवाल द्या आणि सुरक्षित असल्यास घटनास्थळ/वाहन फोटो जतन करा.",
                "संबंधित विमा कंपनीला कळवा; नोंद नसलेली रोख तडजोड टाळा.",
            ],
            "documents": [
                "पोलीस अहवाल, वाहन/चालक/विमा कागदपत्रे, फोटो व साक्षीदार तपशील",
                "वैद्यकीय नोंदी, बिले, अपंगत्व/उत्पन्न नोंदी व विमा पत्रव्यवहार",
            ],
            "urgent": "वैद्यकीय मदत हवी, मृत्यू/गंभीर दुखापत झाली, वाहन पळाले किंवा पुरावा नष्ट होऊ शकतो",
        },
    },
    "Property": {
        "en": {
            "summary": "Separate title, possession, payment, construction, tenancy, and family-ownership facts.",
            "questions": [
                "Who claims ownership and possession, and on which documents?",
                "Is there a registered document, loan, tenancy, inheritance, or pending case?",
                "Has anyone threatened sale, demolition, dispossession, or construction?",
            ],
            "actions": [
                "Obtain readable copies and a chronological document list.",
                "Do not hand over originals or sign possession/title papers without review.",
                "Record notices and physical changes lawfully; avoid confrontation.",
            ],
            "documents": [
                "Sale/title/inheritance/tenancy papers, registration and property-tax records",
                "Payment, possession, plan/approval, loan, notice, and court records",
            ],
            "urgent": "dispossession, demolition, sale/registration, construction, or a court deadline is imminent",
        },
        "hi": {
            "summary": "Title, possession, payment, construction, tenancy aur family ownership ke facts alag-alag organise karein.",
            "questions": [
                "Ownership aur possession ka claim kaun aur kin documents par karta hai?",
                "Kya registered document, loan, tenancy, inheritance ya pending case hai?",
                "Kya sale, demolition, dispossession ya construction ka immediate risk hai?",
            ],
            "actions": [
                "Readable copies aur chronological document list banayein.",
                "Review ke bina originals hand over ya title/possession papers sign na karein.",
                "Notices aur physical changes lawfully record karein; confrontation se bachein.",
            ],
            "documents": [
                "Sale/title/inheritance/tenancy papers, registration aur property-tax records",
                "Payment, possession, plan/approval, loan, notice aur court records",
            ],
            "urgent": "dispossession, demolition, sale/registration, construction ya court deadline bahut paas ho",
        },
        "mr": {
            "summary": "मालकी, ताबा, पेमेंट, बांधकाम, भाडे आणि कौटुंबिक मालकीची तथ्ये वेगळी नोंदवा.",
            "questions": [
                "मालकी व ताब्याचा दावा कोण आणि कोणत्या कागदपत्रांवर करतो?",
                "नोंदणीकृत दस्तऐवज, कर्ज, भाडे, वारसा किंवा प्रलंबित प्रकरण आहे का?",
                "विक्री, पाडकाम, ताबा काढणे किंवा बांधकामाचा तातडीचा धोका आहे का?",
            ],
            "actions": [
                "वाचनीय प्रती आणि तारखेनुसार कागदपत्रांची यादी तयार करा.",
                "तपासणीशिवाय मूळ कागदपत्रे देऊ किंवा हक्क/ताबा कागदपत्रे सही करू नका.",
                "नोटिसा व प्रत्यक्ष बदल कायदेशीररीत्या नोंदवा; संघर्ष टाळा.",
            ],
            "documents": [
                "विक्री/मालकी/वारसा/भाडे कागदपत्रे, नोंदणी व मालमत्ता-कर नोंदी",
                "पेमेंट, ताबा, आराखडा/मंजुरी, कर्ज, नोटीस व न्यायालयीन नोंदी",
            ],
            "urgent": "ताबा काढणे, पाडकाम, विक्री/नोंदणी, बांधकाम किंवा न्यायालयीन मुदत जवळ असेल",
        },
    },
    "Business": {
        "en": {
            "summary": "Identify the parties, agreement, performance, invoices, payments, breach, and remedy requested.",
            "questions": [
                "Who agreed to what, and is the agreement written or electronic?",
                "What was delivered, paid, rejected, delayed, or misrepresented?",
                "Are personal guarantees, cheques, company assets, or insolvency involved?",
            ],
            "actions": [
                "Reconcile invoices, bank entries, delivery proof, and correspondence.",
                "Send no admission, threat, or settlement proposal without reviewing the record.",
                "Preserve company books and access controls; do not alter entries.",
            ],
            "documents": [
                "Contracts, purchase orders, invoices, ledgers, bank and tax records",
                "Delivery/acceptance proof, emails, notices, cheques, and company records",
            ],
            "urgent": "a cheque/notice deadline, asset transfer, account access loss, insolvency, or court action is imminent",
        },
        "hi": {
            "summary": "Parties, agreement, performance, invoices, payments, breach aur desired remedy identify karein.",
            "questions": [
                "Kisne kya agree kiya aur agreement written/electronic hai?",
                "Kya deliver, pay, reject, delay ya misrepresent hua?",
                "Kya personal guarantee, cheque, company assets ya insolvency involved hai?",
            ],
            "actions": [
                "Invoices, bank entries, delivery proof aur communication reconcile karein.",
                "Record review ke bina admission, threat ya settlement proposal na bhejein.",
                "Company books aur access controls preserve karein; entries alter na karein.",
            ],
            "documents": [
                "Contracts, purchase orders, invoices, ledgers, bank aur tax records",
                "Delivery/acceptance proof, emails, notices, cheques aur company records",
            ],
            "urgent": "cheque/notice deadline, asset transfer, account access loss, insolvency ya court action bahut paas ho",
        },
        "mr": {
            "summary": "पक्षकार, करार, कामगिरी, बिले, पेमेंट, उल्लंघन आणि अपेक्षित उपाय ओळखा.",
            "questions": [
                "कोणी काय मान्य केले आणि करार लेखी/इलेक्ट्रॉनिक आहे का?",
                "काय वितरित, दिले, नाकारले, उशिरा झाले किंवा चुकीचे सांगितले?",
                "वैयक्तिक हमी, धनादेश, कंपनी मालमत्ता किंवा दिवाळखोरीचा प्रश्न आहे का?",
            ],
            "actions": [
                "बिले, बँक नोंदी, वितरण पुरावे आणि संवाद जुळवा.",
                "नोंद तपासल्याशिवाय कबुली, धमकी किंवा तडजोड प्रस्ताव पाठवू नका.",
                "कंपनी पुस्तके व प्रवेश नियंत्रण जतन करा; नोंदी बदलू नका.",
            ],
            "documents": [
                "करार, खरेदी आदेश, बिले, खातेवही, बँक व कर नोंदी",
                "वितरण/स्वीकृती पुरावे, ईमेल, नोटिसा, धनादेश व कंपनी नोंदी",
            ],
            "urgent": "धनादेश/नोटीस मुदत, मालमत्ता हस्तांतरण, प्रवेश बंद, दिवाळखोरी किंवा न्यायालयीन कारवाई जवळ असेल",
        },
    },
    "Job": {
        "en": {
            "summary": "Record the employment terms, work performed, pay, workplace events, complaints, and exit process.",
            "questions": [
                "What was your role, employment type, location, pay, and service period?",
                "What salary, benefit, termination, harassment, or disciplinary issue occurred?",
                "Which internal complaint or response has already been made?",
            ],
            "actions": [
                "Create a dated employment and payment timeline.",
                "Raise a concise written request through the appropriate workplace channel.",
                "Preserve records lawfully without taking confidential material you are not entitled to keep.",
            ],
            "documents": [
                "Offer/appointment letter, policies, payslips, attendance, bank and benefit records",
                "HR correspondence, complaints, performance records, resignation/termination papers",
            ],
            "urgent": "there is a safety threat, coercion to sign, imminent disciplinary hearing, or loss of essential evidence/access",
        },
        "hi": {
            "summary": "Employment terms, work, pay, workplace events, complaints aur exit process record karein.",
            "questions": [
                "Role, employment type, location, pay aur service period kya tha?",
                "Salary, benefit, termination, harassment ya disciplinary issue kya hua?",
                "Kaunsi internal complaint ya response pehle hi diya gaya?",
            ],
            "actions": [
                "Employment aur payment ki dated timeline banayein.",
                "Sahi workplace channel se concise written request karein.",
                "Records lawfully preserve karein; aisa confidential material na lein jiska adhikar nahi.",
            ],
            "documents": [
                "Offer/appointment letter, policies, payslips, attendance, bank aur benefit records",
                "HR communication, complaints, performance, resignation/termination papers",
            ],
            "urgent": "safety threat, zabardasti sign, immediate disciplinary hearing ya important evidence/access lose hone ka risk ho",
        },
        "mr": {
            "summary": "नोकरीच्या अटी, केलेले काम, वेतन, कार्यस्थळ घटना, तक्रारी आणि सेवा समाप्ती नोंदवा.",
            "questions": [
                "भूमिका, नोकरीचा प्रकार, ठिकाण, वेतन व सेवा कालावधी काय होता?",
                "वेतन, लाभ, सेवासमाप्ती, छळ किंवा शिस्तभंगाचा कोणता प्रश्न झाला?",
                "कोणती अंतर्गत तक्रार किंवा उत्तर आधी दिले आहे?",
            ],
            "actions": [
                "नोकरी व पेमेंटची तारखेनुसार कालरेषा तयार करा.",
                "योग्य कार्यस्थळ माध्यमातून संक्षिप्त लेखी विनंती करा.",
                "नोंदी कायदेशीररीत्या जतन करा; अधिकार नसलेली गोपनीय सामग्री घेऊ नका.",
            ],
            "documents": [
                "ऑफर/नियुक्तीपत्र, धोरणे, वेतन पावत्या, उपस्थिती, बँक व लाभ नोंदी",
                "एचआर संवाद, तक्रारी, कामगिरी, राजीनामा/सेवासमाप्ती कागदपत्रे",
            ],
            "urgent": "सुरक्षिततेचा धोका, जबरदस्ती सही, जवळची शिस्तभंग सुनावणी किंवा महत्त्वाचा पुरावा/प्रवेश गमावण्याचा धोका असेल",
        },
    },
    "Consumer": {
        "en": {
            "summary": "Document what was promised, purchased, delivered, complained about, and the remedy requested.",
            "questions": [
                "Who supplied which product/service, when, and for what amount?",
                "What defect, deficiency, delay, refund, or misleading statement occurred?",
                "What written complaint and response already exist?",
            ],
            "actions": [
                "Raise a dated written complaint with a clear requested remedy.",
                "Preserve the product safely where relevant; do not destroy packaging or serial details.",
                "Keep screenshots and acknowledgements for every escalation.",
            ],
            "documents": [
                "Invoice/order, warranty, advertisement, payment and delivery records",
                "Photographs, complaint numbers, emails/chats, inspection and repair reports",
            ],
            "urgent": "the product/service creates a safety risk, evidence may disappear, or a formal deadline/notice is near",
        },
        "hi": {
            "summary": "Kya promise, purchase, deliver aur complain hua aur aap kya remedy chahte hain—record karein.",
            "questions": [
                "Kisne kaunsa product/service kab aur kitne amount mein diya?",
                "Kya defect, deficiency, delay, refund ya misleading statement hua?",
                "Kaunsi written complaint aur response already hai?",
            ],
            "actions": [
                "Clear requested remedy ke saath dated written complaint raise karein.",
                "Relevant ho to product safely preserve karein; packaging/serial details destroy na karein.",
                "Har escalation ke screenshots aur acknowledgement rakhein.",
            ],
            "documents": [
                "Invoice/order, warranty, advertisement, payment aur delivery records",
                "Photos, complaint numbers, emails/chats, inspection aur repair reports",
            ],
            "urgent": "product/service safety risk ban raha ho, evidence lose ho sakta ho, ya formal deadline/notice paas ho",
        },
        "mr": {
            "summary": "काय आश्वासन, खरेदी, वितरण व तक्रार झाली आणि कोणता उपाय हवा आहे ते नोंदवा.",
            "questions": [
                "कोणत्या पुरवठादाराने कोणते उत्पादन/सेवा केव्हा व किती रकमेला दिली?",
                "कोणता दोष, सेवेतील त्रुटी, उशीर, परतावा किंवा दिशाभूल झाली?",
                "कोणती लेखी तक्रार आणि उत्तर आधीपासून आहे?",
            ],
            "actions": [
                "अपेक्षित उपायासह तारखेसहित लेखी तक्रार करा.",
                "लागू असल्यास उत्पादन सुरक्षित ठेवा; पॅकेजिंग/क्रमांक नष्ट करू नका.",
                "प्रत्येक पाठपुराव्याचे स्क्रीनशॉट व पोच ठेवा.",
            ],
            "documents": [
                "बिल/ऑर्डर, वॉरंटी, जाहिरात, पेमेंट व वितरण नोंदी",
                "फोटो, तक्रार क्रमांक, ईमेल/चॅट, तपासणी व दुरुस्ती अहवाल",
            ],
            "urgent": "उत्पादन/सेवेमुळे सुरक्षिततेचा धोका, पुरावा नष्ट होण्याची शक्यता किंवा औपचारिक मुदत जवळ असेल",
        },
    },
    "Banking": {
        "en": {
            "summary": "Separate authorised and disputed transactions, account access, loan/card terms, complaints, and bank responses.",
            "questions": [
                "Which account/product and exact transaction, charge, freeze, or recovery action is disputed?",
                "When did you discover it and when/how was the bank informed?",
                "Were credentials shared, a device/SIM lost, or any police/cyber report made?",
            ],
            "actions": [
                "Contact the bank through an official channel and obtain a complaint/reference number.",
                "Block compromised access and change credentials from a trusted device.",
                "Do not share OTP, PIN, CVV, password, or remote-screen access with anyone.",
            ],
            "documents": [
                "Statements, transaction IDs, loan/card terms, notices and complaint references",
                "Bank responses, screenshots, device/SIM records, police/cyber acknowledgements",
            ],
            "urgent": "money is moving now, credentials/device are compromised, coercive recovery occurs, or essential funds are frozen",
        },
        "hi": {
            "summary": "Authorised/disputed transactions, account access, loan/card terms, complaints aur bank responses alag organise karein.",
            "questions": [
                "Kaunsa account/product aur exact transaction, charge, freeze ya recovery action disputed hai?",
                "Kab pata chala aur bank ko kab/kaise inform kiya?",
                "Kya credentials share, device/SIM lost, ya police/cyber report hui?",
            ],
            "actions": [
                "Official bank channel se complaint/reference number lein.",
                "Compromised access block karke trusted device se credentials change karein.",
                "OTP, PIN, CVV, password ya remote-screen access kisi ko na dein.",
            ],
            "documents": [
                "Statements, transaction IDs, loan/card terms, notices aur complaint references",
                "Bank responses, screenshots, device/SIM records, police/cyber acknowledgements",
            ],
            "urgent": "money abhi move ho raha ho, credentials/device compromised ho, coercive recovery ho, ya essential funds frozen hon",
        },
        "mr": {
            "summary": "मान्य/विवादित व्यवहार, खाते प्रवेश, कर्ज/कार्ड अटी, तक्रारी व बँक उत्तरे वेगळी नोंदवा.",
            "questions": [
                "कोणते खाते/उत्पादन आणि नेमका व्यवहार, शुल्क, गोठवणे किंवा वसुली विवादित आहे?",
                "ते केव्हा समजले आणि बँकेला केव्हा/कसे कळवले?",
                "गोपनीय माहिती दिली, उपकरण/SIM हरवले किंवा पोलीस/सायबर तक्रार केली का?",
            ],
            "actions": [
                "बँकेच्या अधिकृत माध्यमातून तक्रार/संदर्भ क्रमांक घ्या.",
                "धोक्यातील प्रवेश बंद करून विश्वासार्ह उपकरणावरून गोपनीय माहिती बदला.",
                "OTP, PIN, CVV, पासवर्ड किंवा स्क्रीन प्रवेश कोणालाही देऊ नका.",
            ],
            "documents": [
                "विवरणपत्रे, व्यवहार क्रमांक, कर्ज/कार्ड अटी, नोटिसा व तक्रार संदर्भ",
                "बँक उत्तरे, स्क्रीनशॉट, उपकरण/SIM नोंदी, पोलीस/सायबर पोच",
            ],
            "urgent": "पैसे आता जात आहेत, गोपनीय माहिती/उपकरण धोक्यात आहे, जबर वसुली किंवा आवश्यक निधी गोठवला आहे",
        },
    },
    "Other": {
        "en": {
            "summary": "Create a neutral timeline of the people, promises, documents, events, loss, and outcome involved.",
            "questions": [
                "Who is involved, what happened, where, and on which dates?",
                "What documents, notices, recordings, payments, or proceedings exist?",
                "What outcome do you want, and what have you already tried?",
            ],
            "actions": [
                "Prepare a one-page chronology and document index.",
                "Preserve originals and note how each item was obtained.",
                "Ask a lawyer to identify the legal category before taking irreversible action.",
            ],
            "documents": [
                "Identity/contact information necessary for the matter and all relevant agreements/notices",
                "Payments, communication, photographs, orders, and a list of witnesses",
            ],
            "urgent": "there is immediate danger, arrest, dispossession, financial loss in progress, or an approaching official deadline",
        },
        "hi": {
            "summary": "People, promises, documents, events, loss aur desired outcome ki neutral timeline banayein.",
            "questions": [
                "Kaun involved hai, kya hua, kahan aur kin dates par?",
                "Kaunse documents, notices, recordings, payments ya proceedings hain?",
                "Aap kya outcome chahte hain aur ab tak kya try kiya?",
            ],
            "actions": [
                "One-page chronology aur document index prepare karein.",
                "Originals preserve karein aur har item ka source note karein.",
                "Irreversible action se pehle lawyer se legal category identify karayein.",
            ],
            "documents": [
                "Matter ke liye zaruri identity/contact aur relevant agreements/notices",
                "Payments, communication, photos, orders aur witness list",
            ],
            "urgent": "immediate danger, arrest, dispossession, continuing financial loss ya official deadline paas ho",
        },
        "mr": {
            "summary": "व्यक्ती, आश्वासने, कागदपत्रे, घटना, नुकसान आणि अपेक्षित निकालाची तटस्थ कालरेषा तयार करा.",
            "questions": [
                "कोण सहभागी आहे, काय, कुठे आणि कोणत्या तारखांना घडले?",
                "कोणती कागदपत्रे, नोटिसा, रेकॉर्डिंग, पेमेंट किंवा कार्यवाही आहेत?",
                "आपल्याला काय निकाल हवा आणि आतापर्यंत काय केले?",
            ],
            "actions": [
                "एका पानाची कालरेषा आणि कागदपत्र सूची तयार करा.",
                "मूळ कागदपत्रे जतन करा आणि प्रत्येकाचा स्रोत नोंदवा.",
                "अपरिवर्तनीय कृतीपूर्वी वकिलांकडून कायदेशीर प्रकार ओळखून घ्या.",
            ],
            "documents": [
                "प्रकरणासाठी आवश्यक ओळख/संपर्क आणि संबंधित करार/नोटिसा",
                "पेमेंट, संवाद, फोटो, आदेश आणि साक्षीदारांची यादी",
            ],
            "urgent": "तातडीचा धोका, अटक, ताबा काढणे, सुरू असलेले आर्थिक नुकसान किंवा अधिकृत मुदत जवळ असेल",
        },
    },
}


_ISSUE_OVERLAYS = {
    "Domestic Violence": {
        "en": {
            "focus": "Prioritise immediate safety and preserve threatening messages, injury records, photographs, and details of people who witnessed events.",
            "urgent": "you or a child may be in immediate danger—move to a safer place if possible and contact local emergency services or a trusted person",
        },
        "hi": {
            "focus": "Sabse pehle safety dekhein. Threatening messages, injury records, photos aur witnesses ki details safe rakhein.",
            "urgent": "aap ya koi child turant danger mein ho—mumkin ho to safe jagah jaayein aur local emergency service ya trusted person se contact karein",
        },
        "mr": {
            "focus": "सर्वप्रथम सुरक्षिततेला प्राधान्य द्या. धमकीचे संदेश, दुखापतीच्या नोंदी, फोटो आणि साक्षीदारांची माहिती जतन करा.",
            "urgent": "तुम्हाला किंवा मुलाला तातडीचा धोका असेल—शक्य असल्यास सुरक्षित ठिकाणी जा आणि स्थानिक आपत्कालीन सेवा किंवा विश्वासू व्यक्तीशी संपर्क करा",
        },
    },
    "Police Case": {
        "en": {
            "focus": "Note the police station, officer details, document or notice received, dates, and every response already given. Keep copies and seek a lawyer promptly.",
        },
        "hi": {
            "focus": "Police station, officer details, mile hue notice/document, dates aur diye gaye response note karein. Copies rakhein aur jaldi lawyer se baat karein.",
        },
        "mr": {
            "focus": "पोलीस ठाणे, अधिकाऱ्यांची माहिती, मिळालेली नोटीस किंवा कागदपत्र, तारीखा आणि दिलेली उत्तरे नोंदवा. प्रती ठेवा आणि लवकर वकिलांशी बोला.",
        },
    },
    "Bail Matter": {
        "en": {
            "focus": "Treat arrest risk, custody, a police notice, or a court date as time-sensitive. Keep the case details and identity documents ready for a lawyer.",
            "urgent": "arrest appears imminent, someone is already in custody, or a hearing or reporting date is near",
        },
        "hi": {
            "focus": "Arrest risk, custody, police notice ya court date ko time-sensitive samjhein. Case details aur identity documents lawyer ke liye ready rakhein.",
            "urgent": "arrest ka turant risk ho, koi custody mein ho, ya hearing/reporting date kareeb ho",
        },
        "mr": {
            "focus": "अटकेचा धोका, कोठडी, पोलीस नोटीस किंवा न्यायालयाची तारीख ही तातडीची बाब समजा. प्रकरणाची माहिती व ओळखपत्रे वकिलांसाठी तयार ठेवा.",
            "urgent": "अटक होण्याची शक्यता तातडीची असेल, कोणी कोठडीत असेल किंवा सुनावणीची/हजेरीची तारीख जवळ असेल",
        },
    },
    "Cyber Crime": {
        "en": {
            "focus": "Stop further contact or payment, secure affected accounts, and preserve usernames, links, transaction references, screenshots, and device details.",
            "urgent": "money or account access is still being lost, intimate material is threatened, or personal safety is at risk",
        },
        "hi": {
            "focus": "Aage contact ya payment rok dein, affected accounts secure karein aur usernames, links, transaction references, screenshots aur device details save karein.",
            "urgent": "paise ya account access abhi bhi lose ho raha ho, private material ki threat ho, ya personal safety risk mein ho",
        },
        "mr": {
            "focus": "पुढील संपर्क किंवा पेमेंट थांबवा, प्रभावित खाती सुरक्षित करा आणि युजरनेम, लिंक, व्यवहार क्रमांक, स्क्रीनशॉट व डिव्हाइसची माहिती जतन करा.",
            "urgent": "पैसे किंवा खात्याचा प्रवेश अजूनही गमावत असाल, खासगी सामग्रीची धमकी असेल किंवा वैयक्तिक सुरक्षिततेला धोका असेल",
        },
    },
    "Road Accident": {
        "en": {
            "focus": "Prioritise medical care. Preserve the vehicle and scene details, photographs, treatment records, bills, insurance details, and witness contacts.",
        },
        "hi": {
            "focus": "Medical care ko priority dein. Vehicle aur scene details, photos, treatment records, bills, insurance details aur witness contacts save karein.",
        },
        "mr": {
            "focus": "वैद्यकीय उपचारांना प्राधान्य द्या. वाहन व घटनास्थळाची माहिती, फोटो, उपचार नोंदी, बिले, विमा तपशील आणि साक्षीदारांचे संपर्क जतन करा.",
        },
    },
    "Hit and Run": {
        "en": {
            "focus": "Seek medical help, note any part of the vehicle number or description, identify nearby cameras or witnesses, and preserve all treatment and travel records.",
        },
        "hi": {
            "focus": "Medical help lein, vehicle number ka koi hissa ya description note karein, nearby cameras/witnesses identify karein aur treatment records save karein.",
        },
        "mr": {
            "focus": "वैद्यकीय मदत घ्या, वाहन क्रमांकाचा उपलब्ध भाग किंवा वर्णन नोंदवा, जवळचे कॅमेरे किंवा साक्षीदार शोधा आणि उपचार नोंदी जतन करा.",
        },
    },
    "Illegal Possession": {
        "en": {
            "focus": "Do not use force. Preserve title and possession records, photographs, boundary details, communications, and the date you first learned of the issue.",
            "urgent": "there is violence, forced entry, demolition, disposal of property, or a risk that evidence will be destroyed",
        },
        "hi": {
            "focus": "Force use na karein. Title aur possession records, photos, boundary details, communication aur issue pata chalne ki date save karein.",
            "urgent": "violence, forced entry, demolition, property transfer ya evidence destroy hone ka risk ho",
        },
        "mr": {
            "focus": "बळाचा वापर करू नका. मालकी व ताब्याच्या नोंदी, फोटो, हद्दीची माहिती, संवाद आणि समस्या प्रथम कधी समजली ती तारीख जतन करा.",
            "urgent": "हिंसा, जबरदस्तीने प्रवेश, पाडकाम, मालमत्तेची विल्हेवाट किंवा पुरावा नष्ट होण्याचा धोका असेल",
        },
    },
    "Cheque Bounce": {
        "en": {
            "focus": "Preserve the cheque, return memo, underlying agreement or invoice, payment history, bank records, notices, and exact dates. Ask a lawyer to check deadlines.",
        },
        "hi": {
            "focus": "Cheque, return memo, agreement/invoice, payment history, bank records, notices aur exact dates safe rakhein. Deadlines lawyer se check karayein.",
        },
        "mr": {
            "focus": "धनादेश, रिटर्न मेमो, मूळ करार किंवा बिल, पेमेंट इतिहास, बँक नोंदी, नोटिसा आणि अचूक तारीखा जतन करा. मुदती वकिलांकडून तपासा.",
        },
    },
    "Workplace Harassment": {
        "en": {
            "focus": "Keep a dated incident log, messages, emails, complaint records, policies, witness details, and any retaliation after you raised the issue.",
            "urgent": "there is a safety threat, coercion, retaliation, forced resignation, or evidence may be deleted",
        },
        "hi": {
            "focus": "Dated incident log, messages, emails, complaint records, policies, witnesses aur complaint ke baad retaliation ki details save karein.",
            "urgent": "safety threat, pressure, retaliation, forced resignation ya evidence delete hone ka risk ho",
        },
        "mr": {
            "focus": "तारीखवार घटना नोंद, संदेश, ईमेल, तक्रार नोंदी, धोरणे, साक्षीदार आणि तक्रारीनंतर झालेल्या प्रतिशोधाची माहिती जतन करा.",
            "urgent": "सुरक्षिततेला धोका, दबाव, प्रतिशोध, सक्तीचा राजीनामा किंवा पुरावा नष्ट होण्याचा धोका असेल",
        },
    },
    "Unauthorized Transaction": {
        "en": {
            "focus": "Secure the account immediately, preserve alerts and transaction references, record when the bank was informed, and never share an OTP or remote-access code.",
            "urgent": "transactions are continuing, account access is lost, or someone is pressuring you to share codes or make another payment",
        },
        "hi": {
            "focus": "Account turant secure karein, alerts aur transaction references save karein, bank ko kab bataya note karein aur OTP/remote-access code share na karein.",
            "urgent": "transactions continue ho rahe hon, account access chala gaya ho, ya koi code/share/payment ke liye pressure daal raha ho",
        },
        "mr": {
            "focus": "खाते तात्काळ सुरक्षित करा, अलर्ट व व्यवहार क्रमांक जतन करा, बँकेला कधी कळवले ते नोंदवा आणि OTP किंवा रिमोट-अॅक्सेस कोड देऊ नका.",
            "urgent": "व्यवहार सुरूच असतील, खात्याचा प्रवेश गेला असेल किंवा कोणी कोड अथवा आणखी पेमेंटसाठी दबाव आणत असेल",
        },
    },
    "Account Freeze": {
        "en": {
            "focus": "Ask the bank for the stated reason or reference, preserve account statements and communications, and note any linked police, court, tax, or compliance contact.",
        },
        "hi": {
            "focus": "Bank se stated reason/reference maangein, statements aur communication save karein, aur linked police, court, tax ya compliance contact note karein.",
        },
        "mr": {
            "focus": "बँकेकडून नमूद कारण किंवा संदर्भ मागा, खाते विवरण व संवाद जतन करा आणि संबंधित पोलीस, न्यायालय, कर किंवा अनुपालन संपर्क नोंदवा.",
        },
    },
    "Legal Notice": {
        "en": {
            "focus": "Preserve the complete notice and delivery envelope or message, note the received date and any stated deadline, and get advice before replying or ignoring it.",
        },
        "hi": {
            "focus": "Poora notice aur delivery envelope/message save karein, received date aur stated deadline note karein, aur reply ya ignore karne se pehle advice lein.",
        },
        "mr": {
            "focus": "संपूर्ण नोटीस व वितरणाचे पाकीट किंवा संदेश जतन करा, मिळाल्याची तारीख व नमूद मुदत नोंदवा आणि उत्तर देण्यापूर्वी किंवा दुर्लक्ष करण्यापूर्वी सल्ला घ्या.",
        },
    },
}


_LEGACY_GUIDE_IDS = {
    "unpaid_salary": ("Job", "Unpaid Salary"),
    "divorce_family": ("Family", "Divorce"),
    "consumer_refund": ("Consumer", "Refund Issue"),
    "cheque_bounce": ("Business", "Cheque Bounce"),
    "cyber_fraud": ("Criminal", "Cyber Crime"),
    "property_dispute": ("Property", "Property Dispute"),
    "police_case": ("Criminal", "Police Case"),
}


_KEYWORD_ROUTES = (
    (
        "Banking",
        "Unauthorized Transaction",
        (
            "unauthorized transaction",
            "bank fraud",
            "upi fraud",
            "otp fraud",
            "account hacked",
            "khate se paise nikal",
            "खाते से पैसे",
            "अनधिकृत व्यवहार",
            "खात्यातून पैसे",
        ),
    ),
    (
        "Criminal",
        "Cyber Crime",
        (
            "cyber crime",
            "cyber fraud",
            "online scam",
            "sextortion",
            "blackmail online",
            "online dhokha",
            "ऑनलाइन धोखा",
            "सायबर फसवणूक",
            "ऑनलाईन फसवणूक",
        ),
    ),
    (
        "Job",
        "Unpaid Salary",
        (
            "unpaid salary",
            "salary not paid",
            "pending salary",
            "baki tankhwa",
            "salary nahi mili",
            "वेतन नहीं मिला",
            "पगार थकीत",
            "पगार मिळाला नाही",
        ),
    ),
    (
        "Job",
        "Wrongful Termination",
        (
            "wrongful termination",
            "fired",
            "terminated",
            "job se nikal",
            "नौकरी से निकाल",
            "नोकरीवरून काढ",
            "कामावरून काढ",
        ),
    ),
    (
        "Family",
        "Domestic Violence",
        (
            "domestic violence",
            "beating",
            "gharelu hinsa",
            "घरेलू हिंसा",
            "घरेलू मारपीट",
            "पति की मारपीट",
            "पति ने मारपीट",
            "घरगुती हिंसा",
        ),
    ),
    (
        "Criminal",
        "Theft or Assault",
        (
            "theft or assault",
            "assault",
            "मारपीट",
        ),
    ),
    (
        "Family",
        "Child Custody",
        ("child custody", "bachche ki custody", "बच्चे की कस्टडी", "मुलांचा ताबा"),
    ),
    (
        "Family",
        "Dowry Case",
        (
            "dowry case",
            "dowry",
            "dahej",
            "दहेज का मामला",
            "दहेज",
        ),
    ),
    ("Family", "Divorce", ("divorce", "talak", "तलाक", "घटस्फोट")),
    (
        "Business",
        "Cheque Bounce",
        (
            "cheque bounce",
            "check bounce",
            "dishonour",
            "bank memo",
            "चेक बाउंस",
            "धनादेश न वटणे",
        ),
    ),
    (
        "Consumer",
        "Refund Issue",
        (
            "refund",
            "money back",
            "return refused",
            "paise wapas",
            "पैसे वापस",
            "पैसे परत",
        ),
    ),
    (
        "Consumer",
        "Product Defect",
        ("defective product", "product defect", "faulty product"),
    ),
    (
        "Property",
        "Builder Issue",
        ("builder", "possession delay", "rera", "flat delay"),
    ),
    (
        "Property",
        "Illegal Possession",
        ("illegal possession", "encroachment", "kabza", "अतिक्रमण"),
    ),
    (
        "Accident",
        "Hit and Run",
        ("hit and run", "vehicle fled", "gaadi bhaag", "गाड़ी भाग", "वाहन पळून"),
    ),
    (
        "Accident",
        "Road Accident",
        (
            "road accident",
            "car accident",
            "bike accident",
            "sadak durghatna",
            "सड़क दुर्घटना",
            "रस्ता अपघात",
        ),
    ),
    (
        "Banking",
        "Loan Harassment",
        (
            "loan harassment",
            "recovery agent",
            "collection harassment",
            "वसूली एजेंट",
            "वसुली एजंट",
        ),
    ),
    (
        "Criminal",
        "Bail Matter",
        ("bail", "anticipatory bail", "zamanat", "जमानत", "जामीन"),
    ),
    (
        "Criminal",
        "Police Case",
        (
            "police",
            "fir",
            "summons",
            "arrest",
            "police notice",
            "पुलिस ने मुझे नोटिस दिया",
            "पुलिस ने नोटिस दिया",
            "पुलिस नोटिस",
            "पुलिस",
        ),
    ),
    (
        "Property",
        "Property Dispute",
        (
            "property",
            "land",
            "flat",
            "sale deed",
            "partition",
            "tenant",
            "rent",
            "संपत्ति विवाद",
        ),
    ),
    (
        "Business",
        "Contract Dispute",
        ("contract", "agreement breach", "business dispute"),
    ),
    (
        "Consumer",
        "Consumer Complaint",
        ("consumer complaint", "seller", "ecommerce", "online order"),
    ),
    (
        "Consumer",
        "Online Fraud",
        (
            "online shopping fraud",
            "ecommerce fraud",
            "shopping scam",
            "seller scam",
            "ऑनलाइन खरीदारी धोखा",
            "ऑनलाइन खरेदी फसवणूक",
        ),
    ),
    (
        "Job",
        "Service Dispute",
        ("job", "employer", "employee", "workplace"),
    ),
    (
        "Other",
        "General Legal Query",
        (
            "legal question",
            "general legal query",
            "kanooni sawal",
            "कानूनी सवाल",
            "कायदेशीर प्रश्न",
        ),
    ),
    (
        "Other",
        "Legal Notice",
        ("legal notice", "कानूनी नोटिस", "कायदेशीर नोटीस"),
    ),
)


def language_code(user: Any) -> str:
    raw = str(getattr(user, "language", "en") or "en").strip().lower()
    if raw in {"hi", "hindi", "hinglish"}:
        return "hi"
    if raw in {"mr", "marathi", "मराठी"}:
        return "mr"
    return "en"


def ui(user: Any, key: str) -> str:
    lang = language_code(user)
    return _UI.get(lang, _UI["en"]).get(key, _UI["en"][key])


def _category_from_key(category_key: str) -> Optional[str]:
    normalized = str(category_key or "").strip().lower().replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    for category in CATEGORY_SUBCATEGORIES:
        candidate = re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")
        if candidate == normalized:
            return category
    return None


def _subcategory_from_key(category: str, subcategory_key: str) -> Optional[str]:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(subcategory_key or "").strip().lower(),
    ).strip("_")
    for subcategory in CATEGORY_SUBCATEGORIES.get(category, ()):
        candidate = re.sub(r"[^a-z0-9]+", "_", subcategory.lower()).strip("_")
        if candidate == normalized:
            return subcategory
    return None


def category_key(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", category.lower()).strip("_")


def subcategory_key(subcategory: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", subcategory.lower()).strip("_")


def category_label(category: str, user: Any) -> str:
    lang = language_code(user)
    return CATEGORY_LABELS.get(category, {}).get(lang, category)


def subcategory_label(subcategory: str, user: Any) -> str:
    lang = language_code(user)
    return SUBCATEGORY_LABELS.get(subcategory, {}).get(lang, subcategory)


def guide_category_rows(user: Any) -> list[dict[str, str]]:
    return [
        {
            "id": f"guidecat::{category_key(category)}",
            "title": category_label(category, user)[:24],
            "description": ui(user, "guide_row")[:72],
        }
        for category in CATEGORY_SUBCATEGORIES
    ]


def guide_subcategory_rows(user: Any, raw_category: str) -> list[dict[str, str]]:
    category = _category_from_key(raw_category)
    if not category:
        return []
    return [
        {
            "id": (
                f"guide::{category_key(category)}::"
                f"{subcategory_key(subcategory)}"
            ),
            "title": subcategory_label(subcategory, user)[:24],
            "description": ui(user, "guide_row")[:72],
        }
        for subcategory in CATEGORY_SUBCATEGORIES[category]
    ]


def parse_guide_id(interactive_id: str) -> tuple[Optional[str], Optional[str]]:
    parts = str(interactive_id or "").split("::")
    if len(parts) == 2 and parts[0] == "guide":
        return _LEGACY_GUIDE_IDS.get(parts[1], (None, None))
    if len(parts) != 3 or parts[0] != "guide":
        return None, None
    category = _category_from_key(parts[1])
    if not category:
        return None, None
    return category, _subcategory_from_key(category, parts[2])


def _is_word_character(character: str) -> bool:
    if not character:
        return False
    return unicodedata.category(character)[0] in {"L", "M", "N"}


def _word_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    current: list[str] = []
    for character in str(value or "").casefold():
        if _is_word_character(character):
            current.append(character)
        elif current:
            tokens.add("".join(current))
            current = []
    if current:
        tokens.add("".join(current))
    return tokens


def _phrase_present(message: str, phrase: str) -> bool:
    """Match complete words/phrases instead of fragments inside other words."""

    candidate = str(phrase or "").casefold().strip()
    if not candidate:
        return False
    start = message.find(candidate)
    while start >= 0:
        end = start + len(candidate)
        before_is_word = start > 0 and _is_word_character(message[start - 1])
        after_is_word = (
            end < len(message)
            and _is_word_character(message[end])
        )
        if not before_is_word and not after_is_word:
            return True
        start = message.find(candidate, start + 1)
    return False


def find_guide(message: str) -> tuple[str, str]:
    normalized = re.sub(
        r"\s+",
        " ",
        str(message or "").casefold(),
    ).strip()
    matches: list[tuple[int, int, str, str]] = []
    route_order = 0
    for category, subcategory, phrases in _KEYWORD_ROUTES:
        for phrase in phrases:
            if _phrase_present(normalized, phrase):
                # Prefer the most specific phrase. Route order is the stable
                # tie-breaker for genuinely equivalent aliases.
                matches.append(
                    (
                        len(phrase.casefold()),
                        -route_order,
                        category,
                        subcategory,
                    )
                )
            route_order += 1

    # Canonical visible labels participate in the same specificity ranking.
    # This prevents a generic alias such as "police" or "fir" from
    # overriding the more precise "Police Harassment" or "False FIR" label.
    for category, subcategories in CATEGORY_SUBCATEGORIES.items():
        for subcategory in subcategories:
            if subcategory == "Not Sure":
                continue
            labels = SUBCATEGORY_LABELS.get(subcategory, {})
            visible_labels = {
                subcategory,
                *(labels.get(lang, "") for lang in ("en", "hi", "mr")),
            }
            for label in visible_labels:
                candidate = str(label or "").casefold().strip()
                if candidate and _phrase_present(normalized, candidate):
                    matches.append(
                        (
                            len(candidate),
                            -route_order,
                            category,
                            subcategory,
                        )
                    )
                route_order += 1
    if matches:
        _, _, category, subcategory = max(matches)
        return category, subcategory

    # Fall back to all visible English, Hindi/Hinglish, and Marathi labels.
    # Unicode letters and combining marks stay together so native-script
    # labels are scored as full words rather than isolated consonants.
    scored_candidates: list[tuple[int, int, str, str]] = []
    tokens = _word_tokens(normalized)
    for category, subcategories in CATEGORY_SUBCATEGORIES.items():
        for subcategory in subcategories:
            if subcategory == "Not Sure":
                continue
            labels = SUBCATEGORY_LABELS.get(subcategory, {})
            visible_labels = {
                subcategory,
                *(labels.get(lang, "") for lang in ("en", "hi", "mr")),
            }
            label_tokens = set().union(
                *(_word_tokens(label) for label in visible_labels)
            )
            score = len(tokens & label_tokens)
            specificity = sum(len(token) for token in tokens & label_tokens)
            if score:
                scored_candidates.append(
                    (score, specificity, category, subcategory)
                )
    if scored_candidates:
        best_score = max(
            (score, specificity)
            for score, specificity, _, _ in scored_candidates
        )
        winners = {
            (category, subcategory)
            for score, specificity, category, subcategory in scored_candidates
            if (score, specificity) == best_score
        }
        if len(winners) == 1:
            return next(iter(winners))
    return "Other", "Not Sure"


def guide_message(
    user: Any,
    category: str,
    subcategory: str,
    *,
    include_feedback_prompt: bool = True,
) -> str:
    resolved_category = _category_from_key(category) or category
    if resolved_category not in _GUIDES:
        resolved_category = "Other"
    resolved_subcategory = (
        _subcategory_from_key(resolved_category, subcategory)
        or subcategory
        or "Not Sure"
    )

    lang = language_code(user)
    content = _GUIDES[resolved_category].get(
        lang,
        _GUIDES[resolved_category]["en"],
    )
    overlay = _ISSUE_OVERLAYS.get(resolved_subcategory, {}).get(lang, {})
    issue_focus = overlay.get("focus", ui(user, "issue_focus_default"))
    urgent = overlay.get("urgent", content["urgent"])

    def bullets(items: list[str]) -> str:
        return "\n".join(f"• {item}" for item in items)

    review_status = (
        f"{ui(user, 'reviewed')}: {LEGAL_CONTENT_REVIEWED_ON}"
        if LEGAL_CONTENT_REVIEWED_ON
        else ui(user, "review_pending")
    )
    parts = [
        f"*{subcategory_label(resolved_subcategory, user)}*",
        content["summary"],
        f"*{ui(user, 'issue_focus')}*\n• {issue_focus}",
        f"*{ui(user, 'questions')}*\n{bullets(content['questions'])}",
        f"*{ui(user, 'actions')}*\n{bullets(content['actions'])}",
        f"*{ui(user, 'documents')}*\n{bullets(content['documents'])}",
        f"*{ui(user, 'urgent')}*\n• {urgent}",
        ui(user, "location"),
        f"⚠️ {ui(user, 'disclaimer')}",
        (
            f"{ui(user, 'version')}: {LEGAL_CONTENT_VERSION}\n"
            f"{review_status}"
        ),
    ]
    if include_feedback_prompt:
        parts.append(ui(user, "helpful"))
    return "\n\n".join(parts)


def guide_feedback_buttons(
    user: Any,
    category: str,
    subcategory: str,
) -> list[dict[str, str]]:
    cat_key = category_key(category)
    sub_key = subcategory_key(subcategory)
    return [
        {
            "id": f"guidefb::yes::{cat_key}::{sub_key}",
            "title": ui(user, "yes")[:20],
        },
        {
            "id": f"guidefb::no::{cat_key}::{sub_key}",
            "title": ui(user, "no")[:20],
        },
        {"id": "book_now", "title": ui(user, "book")[:20]},
    ]


def parse_guide_feedback_id(
    interactive_id: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    parts = str(interactive_id or "").split("::")
    if len(parts) != 4 or parts[0] != "guidefb" or parts[1] not in {"yes", "no"}:
        return None, None, None
    category = _category_from_key(parts[2])
    if not category:
        return None, None, None
    subcategory = _subcategory_from_key(category, parts[3])
    if not subcategory:
        return None, None, None
    return parts[1], category, subcategory
