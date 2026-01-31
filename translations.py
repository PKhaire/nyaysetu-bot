TRANSLATIONS = {

    # =====================================================
    # 🇬🇧 ENGLISH (DEFAULT)
    # =====================================================
    "en": {
        # ---------- GENERAL ----------
        "welcome": (
            "🙏  Welcome to NyaySetu\n"
            "⚖️ The Bridge To Justice\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Please select your preferred language:"
        ),
        "restart": "Your session has been reset.\nPlease type \"Hi\" to start again.",

        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "Please select how you would like to proceed:",
        "ask_ai": "Get Legal Guidance",
        "ask_ai_prompt": "Please enter your legal query:",
        "ai_cooldown": "Please wait for a moment before sending another message.",
        "book_consult": "Book Consultation",

        "rate_limit_exceeded": (
            "You are sending messages too quickly.\n"
            "Please wait for a moment and try again."
        ),

        # ---------- USER DETAILS ----------
        "ask_name": "Please enter your full name.",
        "ask_name_retry": "Please enter your full name.",
        
        "ask_state": "Please select the state you are currently residing in.",
        "ask_state_retry": "Please select your state from the list below.",
        "choose_state": "Select State",
        "choose_state_or_more": "Select your state or tap More",
        "thanks_state": "Thank you.\nPlease confirm your state.",
        "select_state": "Select State",
        "indian_states": "Indian States",
        
        "ask_district": "Select District",
        "choose_district": "Select your district",
        "select_district_in": "Select district in {state}",
        "district_invalid": (
            "The district \"{district}\" could not be identified in {state}.\n"
            "Please select a valid district from the list below."
        ),


        # ---------- CATEGORY ----------
        "select_category": "Select Legal Category",
        "choose_category": "Please select the category that best describes your legal matter.",
        "category_retry": "Please select a legal category from the list below.",
        
        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "Select Sub-Category",
        "choose_subcategory": "Please select the option that best describes your legal matter.",
        "subcategory_retry": "Please select a sub-category from the list below.",
        "subcategory_mismatch": (
            "The selected sub-category does not correspond to the chosen legal category.\n"
            "Please select a valid sub-category."
        ),

        # ---------- DATE ----------
        "select_date": "Select appointment date",
        "select_date_retry": "Please select an appointment date from the list below.",
        "available_dates": "Available Dates",
        "invalid_date": "The selected date is invalid. Please select again.",
        "past_date_error": (
            "You cannot select a past or same-day appointment.\n"
            "Please select a future date."
        ),
        "available_on": "Available on {date}",
        "next_7_days": "Next Available Days",
        
        # ---------- SLOT ----------
        "select_slot": "Select Time Slot",
        "available_slots": "Available Time Slots (IST)",
        "time_slots": "Time Slots",
        "slot_retry": "Please select a time slot from the list below.",
        "invalid_slot": "The selected time slot is invalid. Please select again.",
        "no_slots": (
            "No time slots are available for the selected date.\n"
            "Please select another date."
        ),

        # ---------- BOOKING / PAYMENT ----------
        "booking_missing": (
            "Some booking details are missing.\n"
            "Please restart the booking process."
        ),
        "free_limit_reached": (
            "The free legal guidance limit has been reached.\n"
            "Please book a consultation."
        ),
        "payment_in_progress": (
            "Payment is currently in progress.\n"
            "Please wait."
        ),
        "payment_success": (
            "Payment completed successfully.\n"
            "Your consultation has been confirmed."
        ),
        "session_start": (
            "Payment received successfully.\n\n"
            "You may now submit your legal queries here.\n"
            "Our legal expert will contact you on the scheduled date and time."
        ),
        "payment_link_text": "Your payment link is active:",

        "appointment_summary": (
            "Appointment Details:\n"
            "Name: {name}\n"
            "State: {state}\n"
            "District: {district}\n"
            "Category: {category}\n"
            "Date: {date}\n"
            "Time Slot: {slot}\n"
            "Fees: ₹{amount} (one-time session)\n\n"
            "Please proceed to complete the payment."
        ),
        "receipt_help": "If you have not received the receipt, please type RECEIPT.",
        
        # ---------- COMMON ----------
        "invalid_selection": "The selected option is invalid. Please try again.",
    },

    # =====================================================
    # 🇮🇳 HINGLISH
    # =====================================================
    "hi": {
        "welcome": (
            "🙏  NyaySetu mein aapka swagat hai\n"
            "⚖️ The Bridge To Justice\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Kripya apni pasand ki bhasha select karein:"
        ),
        "restart": "Aapka session reset ho gaya hai.\nKripya \"Hi\" type karke dobara shuru karein.",

        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "Kripya batayein aap kaise aage badhna chahte hain:",
        "ask_ai": "Legal Guidance Prapt Karein",
        "ask_ai_prompt": "Kripya apna legal prashn darj karein:",
        "ai_cooldown": "Kripya agla message bhejne se pehle thoda intezaar karein.",
        "book_consult": "Consultation Book Karein",

        "rate_limit_exceeded": (
            "Aap bahut tezi se messages bhej rahe hain.\n"
            "Kripya thoda intezaar karke dobara koshish karein."
        ),

        # ---------- USER DETAILS ----------
        "ask_name": "Kripya apna poora naam darj karein.",
        "ask_name_retry": "Kripya apna poora naam darj karein.",
        
        "ask_state": "Kripya batayein aap vartamaan mein kis rajya mein rehte hain.",
        "ask_state_retry": "Kripya neeche di gayi list se apna rajya select karein.",
        "choose_state": "Rajya Select Karein",
        "choose_state_or_more": "Apna rajya select karein ya More par tap karein",
        "thanks_state": "Dhanyavaad.\nKripya apna rajya confirm karein.",
        "select_state": "Rajya Select Karein",
        "indian_states": "Bharatiya Rajya",
        
        "ask_district": "Zila Select Karein",
        "choose_district": "Apna zila select karein",
        "select_district_in": "{state} mein zila select karein",
        "district_invalid": (
            "\"{district}\" zila {state} mein pehchana nahi ja saka.\n"
            "Kripya neeche di gayi list se sahi zila select karein."
        ),

        # ---------- CATEGORY ----------
        "select_category": "Legal Category Select Karein",
        "choose_category": "Kripya apne legal matter se sabse zyada milti-julti category select karein.",
        "category_retry": "Kripya neeche di gayi list se ek legal category select karein.",
        
        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "Sub-Category Select Karein",
        "choose_subcategory": "Kripya apne legal matter ko sabse achchhe se describe karne wala option select karein.",
        "subcategory_retry": "Kripya neeche di gayi list se ek sub-category select karein.",
        "subcategory_mismatch": (
            "Select ki gayi sub-category, chuni hui legal category se sambandhit nahi hai.\n"
            "Kripya ek valid sub-category select karein."
        ),

        # ---------- DATE ----------
        "select_date": "Appointment ki date select karein",
        "select_date_retry": "Kripya neeche di gayi list se appointment ki date select karein.",
        "available_dates": "Available Dates",
        "invalid_date": "Select ki gayi date valid nahi hai. Kripya dobara select karein.",
        "past_date_error": (
            "Aap pichhli ya aaj ki date ke liye appointment select nahi kar sakte.\n"
            "Kripya future ki date select karein."
        ),
        "available_on": "{date} ko uplabdh",
        "next_7_days": "Agale uplabdh din",
        
        # ---------- SLOT ----------
        "select_slot": "Time Slot Select Karein",
        "available_slots": "Available Time Slots (IST)",
        "time_slots": "Time Slots",
        "slot_retry": "Kripya neeche di gayi list se time slot select karein.",
        "invalid_slot": "Select kiya gaya time slot valid nahi hai. Kripya dobara select karein.",
        "no_slots": (
            "Is date ke liye koi time slot uplabdh nahi hai.\n"
            "Kripya kisi aur date ko select karein."
        ),

        # ---------- BOOKING / PAYMENT ----------
        "booking_missing": (
            "Kuch booking details uplabdh nahi hain.\n"
            "Kripya booking process dobara shuru karein."
        ),
        "free_limit_reached": (
            "Free legal guidance ki limit poori ho chuki hai.\n"
            "Kripya consultation book karein."
        ),
        "payment_in_progress": (
            "Payment process chal rahi hai.\n"
            "Kripya thoda intezaar karein."
        ),
        "payment_success": (
            "Payment safalta se poori ho gayi hai.\n"
            "Aapki consultation confirm ho chuki hai."
        ),
        "session_start": (
            "Payment safalta se prapt ho gaya hai.\n\n"
            "Ab aap apne legal prashn yahan darj kar sakte hain.\n"
            "Hamare legal expert nirdharit tareekh aur samay par aapse sampark karenge."
        ),
        "payment_link_text": "Aapka payment link active hai:",

        "appointment_summary": (
            "Appointment Details:\n"
            "Naam: {name}\n"
            "Rajya: {state}\n"
            "Zila: {district}\n"
            "Category: {category}\n"
            "Tareekh: {date}\n"
            "Time Slot: {slot}\n"
            "Fees: ₹{amount} (one-time session)\n\n"
            "Kripya payment poori karne ke liye aage badhein."
        ),
        "receipt_help": "Agar aapko receipt prapt nahi hui hai, to kripya RECEIPT type karein.",
        
        # ---------- COMMON ----------
        "invalid_selection": "Select kiya gaya option valid nahi hai. Kripya dobara koshish karein.",

    },

    # =====================================================
    # 🇮🇳 MARATHI
    # =====================================================
    "mr": {
        "welcome": (
            "🙏  NyaySetu मध्ये आपले स्वागत आहे\n"
            "⚖️ The Bridge To Justice\n\n"
            "🆔 केस आयडी: {case_id}\n\n"
            "कृपया आपली पसंतीची भाषा निवडा:"
        ),
        "restart": "आपले सत्र रीसेट करण्यात आले आहे.\nकृपया \"Hi\" टाइप करून पुन्हा सुरू करा.",
        
        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "कृपया पुढे कसे जायचे आहे ते निवडा:",
        "ask_ai": "कायदेशीर मार्गदर्शन मिळवा",
        "ask_ai_prompt": "कृपया आपला कायदेशीर प्रश्न नोंदवा:",
        "ai_cooldown": "कृपया पुढील संदेश पाठवण्यापूर्वी थोडा वेळ थांबा.",
        "book_consult": "सल्लामसलत बुक करा",

        "rate_limit_exceeded": (
            "आपण खूप वेगाने संदेश पाठवत आहात.\n"
            "कृपया थोडा वेळ थांबून पुन्हा प्रयत्न करा."
        ),

        # ---------- USER DETAILS ----------
        "ask_name": "कृपया आपले पूर्ण नाव नोंदवा.",
        "ask_name_retry": "कृपया आपले पूर्ण नाव नोंदवा.",
        
        "ask_state": "कृपया आपण सध्या कोणत्या राज्यात राहता ते निवडा.",
        "ask_state_retry": "कृपया खाली दिलेल्या यादीतून आपले राज्य निवडा.",
        "choose_state": "राज्य निवडा",
        "choose_state_or_more": "आपले राज्य निवडा किंवा More वर टॅप करा",
        "thanks_state": "धन्यवाद.\nकृपया आपले राज्य निश्चित करा.",
        "select_state": "राज्य निवडा",
        "indian_states": "भारतीय राज्ये",
        
        "ask_district": "जिल्हा निवडा",
        "choose_district": "आपला जिल्हा निवडा",
        "select_district_in": "{state} मधील जिल्हा निवडा",
        "district_invalid": (
            "\"{district}\" हा जिल्हा {state} मध्ये आढळला नाही.\n"
            "कृपया खालील यादीतून वैध जिल्हा निवडा."
        ),
        
        # ---------- CATEGORY ----------
        "select_category": "कायदेशीर श्रेणी निवडा",
        "choose_category": "कृपया आपल्या कायदेशीर विषयाशी सर्वाधिक संबंधित असलेली श्रेणी निवडा.",
        "category_retry": "कृपया खाली दिलेल्या यादीतून कायदेशीर श्रेणी निवडा.",
        
        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "उप-श्रेणी निवडा",
        "choose_subcategory": "कृपया आपल्या कायदेशीर विषयाचे योग्य वर्णन करणारा पर्याय निवडा.",
        "subcategory_retry": "कृपया खाली दिलेल्या यादीतून उप-श्रेणी निवडा.",
        "subcategory_mismatch": (
            "निवडलेली उप-श्रेणी निवडलेल्या कायदेशीर श्रेणीशी संबंधित नाही.\n"
            "कृपया वैध उप-श्रेणी निवडा."
        ),

        # ---------- DATE ----------
        "select_date": "अपॉइंटमेंटची तारीख निवडा",
        "select_date_retry": "कृपया खाली दिलेल्या यादीतून अपॉइंटमेंटची तारीख निवडा.",
        "available_dates": "उपलब्ध तारखा",
        "invalid_date": "निवडलेली तारीख वैध नाही. कृपया पुन्हा निवडा.",
        "past_date_error": (
            "मागील किंवा आजच्या तारखेसाठी अपॉइंटमेंट निवडता येणार नाही.\n"
            "कृपया भविष्यातील तारीख निवडा."
        ),
        "available_on": "{date} रोजी उपलब्ध",
        "next_7_days": "पुढील उपलब्ध दिवस",
        
        # ---------- SLOT ----------
        "select_slot": "वेळेचा स्लॉट निवडा",
        "available_slots": "उपलब्ध वेळेचे स्लॉट (IST)",
        "time_slots": "वेळेचे स्लॉट",
        "slot_retry": "कृपया खाली दिलेल्या यादीतून वेळेचा स्लॉट निवडा.",
        "invalid_slot": "निवडलेला वेळेचा स्लॉट वैध नाही. कृपया पुन्हा निवडा.",
        "no_slots": (
            "या तारखेसाठी कोणतेही वेळेचे स्लॉट उपलब्ध नाहीत.\n"
            "कृपया दुसरी तारीख निवडा."
        ),

        # ---------- BOOKING / PAYMENT ----------
        "booking_missing": (
            "काही बुकिंग तपशील उपलब्ध नाहीत.\n"
            "कृपया बुकिंग प्रक्रिया पुन्हा सुरू करा."
        ),
        "free_limit_reached": (
            "मोफत कायदेशीर मार्गदर्शनाची मर्यादा पूर्ण झाली आहे.\n"
            "कृपया सल्लामसलत बुक करा."
        ),
        "payment_in_progress": (
            "पेमेंट प्रक्रिया सुरू आहे.\n"
            "कृपया थोडा वेळ थांबा."
        ),
        "payment_success": (
            "पेमेंट यशस्वीरीत्या पूर्ण झाले आहे.\n"
            "आपली सल्लामसलत निश्चित झाली आहे."
        ),
        "session_start": (
            "पेमेंट यशस्वीरीत्या प्राप्त झाले आहे.\n\n"
            "आता आपण आपले कायदेशीर प्रश्न येथे नोंदवू शकता.\n"
            "आमचे कायदेशीर तज्ञ निश्चित केलेल्या तारीख आणि वेळेला आपल्याशी संपर्क साधतील."
        ),
        "payment_link_text": "आपला पेमेंट लिंक सक्रिय आहे:",

        "appointment_summary": (
            "अपॉइंटमेंट तपशील:\n"
            "नाव: {name}\n"
            "राज्य: {state}\n"
            "जिल्हा: {district}\n"
            "श्रेणी: {category}\n"
            "तारीख: {date}\n"
            "वेळेचा स्लॉट: {slot}\n"
            "शुल्क: ₹{amount} (एकदाच होणारी सत्र शुल्क)\n\n"
            "कृपया पेमेंट पूर्ण करण्यासाठी पुढे जा."
        ),
        "receipt_help": "आपल्याला पावती प्राप्त झाली नसेल तर कृपया RECEIPT टाइप करा.",
        
        # ---------- COMMON ----------
        "invalid_selection": "निवडलेला पर्याय वैध नाही. कृपया पुन्हा प्रयत्न करा.",

    },
}
