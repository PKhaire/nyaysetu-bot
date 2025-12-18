# translations.py

TRANSLATIONS = {
    # =====================================================
    # 🇬🇧 ENGLISH (DEFAULT)
    # =====================================================
    "en": {
        # ---------- GENERAL ----------
        "welcome": (
            "👋 Welcome to NyaySetu — The Bridge To Justice ⚖️\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Please select your language:"
        ),
        "restart": "🔄 Session reset.\nType *Hi* to start again.",

        # ---------- AI ----------
        "ask_ai_or_book": "How would you like to proceed?",
        "ask_ai": "Ask AI",
        "ask_ai_prompt": "🤖 Ask your legal question.",
        "ai_cooldown": "⏳ Please wait a moment before sending another message.",
        "book_consult": "Book Consultation",

        # ---------- RATE LIMIT ----------
        "rate_limit_exceeded": (
            "⏳ You’re sending messages too quickly.\n"
            "Please wait a moment and try again."
        ),

        # ---------- USER DETAILS ----------
        "ask_name": "Please tell me your *full name*.",
        "ask_name_retry": "Please enter your *full name* 🙂",

        "ask_state": "Which *state* are you in?",
        "ask_state_retry": "Please select or type your *state* 🙂",
        "choose_state": "Choose your state",
        "choose_state_or_more": "Choose your state or tap More",
        "thanks_state": "Thanks 🙏\nWhich state are you in?",
        "select_state": "Select State",
        "indian_states": "Indian States",

        "ask_district": "Choose district",
        "choose_district": "Choose your district",
        "select_district_in": "Select district in {state}",
        "district_invalid": (
            "❌ Could not identify district *{district}* in {state}.\n"
            "Please select from the list below 👇"
        ),

        # ---------- CATEGORY ----------
        "select_category": "Select Legal Category",
        "choose_category": "Choose the category that best matches your issue",
        "category_retry": "Please select a legal category from the list 👇",

        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "Select Sub-Category",
        "choose_subcategory": "Choose the issue type",
        "subcategory_retry": "Please select a sub-category from the list 👇",
        "subcategory_mismatch": (
            "Selected sub-category does not match your category. "
            "Please try again 👇"
        ),

        # ---------- DATE ----------
        "select_date": "Select appointment date 👇",
        "select_date_retry": "Please select an appointment *date* from the list 👇",
        "available_dates": "Available dates",
        "invalid_date": "Invalid date selected. Please choose again 👇",
        "past_date_error": (
            "⚠️ You cannot select a past or same-day appointment.\n"
            "Please choose a future date 👇"
        ),
        "available_on": "Available on {date}",
        "next_7_days": "Next available days",


        # ---------- SLOT ----------
        "select_slot": "Select time slot for",
        "available_slots": "Available time slots (IST)",
        "time_slots": "Time Slots",
        "slot_retry": "Please select a time slot from the list 👇",
        "invalid_slot": "Invalid time slot selected. Please choose again 👇",
        "no_slots": (
            "⚠️ No available time slots for this date.\n"
            "Please select another date 👇"
        ),

        # ---------- BOOKING / PAYMENT ----------
        "booking_missing": (
            "⚠️ Some booking details are missing. "
            "Please restart booking."
        ),
        "free_limit_reached": (
            "🚫 Free AI limit reached.\n"
            "Please book a consultation."
        ),
        "payment_in_progress": (
            "⚠️ Payment is in progress.\n"
            "Please complete or wait."
        ),
        "payment_success": (
            "💳 Payment successful.\n"
            "Your consultation is confirmed."
        ),
        "session_start": (
            "✅ *Payment received successfully.*\n\n"
            "You may now ask your legal questions here.\n"
            "Our legal expert will also call you at the scheduled date and time."
        ),

        "appointment_summary": (
            "✅ Your appointment details:\n"
            "Name: {name}\n"
            "State: {state}\n"
            "District: {district}\n"
            "Category: {category}\n"
            "Date: {date}\n"
            "Slot: {slot}\n"
            "Fees: ₹{amount} (one-time session) 🙂\n\n"
            "Please complete payment:"
        ),
        
        # ---------- COMMON ----------
        "invalid_selection": "Invalid selection. Please try again 👇",
    },

    # =====================================================
    # 🇮🇳 HINGLISH
    # =====================================================
    "hi": {
        "welcome": (
            "👋 NyaySetu mein aapka swagat hai ⚖️\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Kripya apni language select karein:"
        ),
        "restart": "🔄 Session reset ho gaya.\n*Hi* type karke dobara shuru karein.",

        "ask_ai_or_book": "Aap kaise aage badhna chahenge?",
        "ask_ai": "AI se poochein",
        "ask_ai_prompt": "🤖 Apna legal sawal poochein.",
        "ai_cooldown": "⏳ Thoda ruk kar dobara message bhejein.",
        "book_consult": "Consultation book karein",

        "rate_limit_exceeded": (
            "⏳ Aap bahut fast messages bhej rahe hain.\n"
            "Thoda ruk kar dobara try karein."
        ),

        "ask_name": "Apna *full name* batayein.",
        "ask_name_retry": "Kripya apna *poora naam* enter karein 🙂",

        "ask_state": "Aap kis *state* mein hain?",
        "ask_state_retry": "Apna *state* select ya type karein 🙂",
        "choose_state": "Apna state choose karein",
        "choose_state_or_more": "State choose karein ya More par tap karein",
        "thanks_state": "Dhanyavaad 🙏\nAap kis state mein hain?",
        "select_state": "State select karein",
        "indian_states": "Indian States",

        "ask_district": "District choose karein",
        "choose_district": "Apna district choose karein",
        "select_district_in": "{state} mein district select karein",
        "district_invalid": (
            "❌ *{district}* district {state} mein nahi mila.\n"
            "Neeche list se select karein 👇"
        ),

        "select_category": "Legal Category select karein",
        "choose_category": "Apni problem ke hisaab se category choose karein",
        "category_retry": "List se legal category select karein 👇",

        "select_subcategory": "Sub-Category select karein",
        "choose_subcategory": "Issue type choose karein",
        "subcategory_retry": "List se sub-category select karein 👇",
        "subcategory_mismatch": (
            "Selected sub-category, category se match nahi karti.\n"
            "Dobara try karein 👇"
        ),

        "select_date": "Appointment date select karein 👇",
        "select_date_retry": "List se appointment *date* select karein 👇",
        "available_dates": "Available dates",
        "invalid_date": "Galat date select hui hai. Dobara choose karein 👇",
        "past_date_error": (
            "⚠️ Aap past ya same-day appointment select nahi kar sakte.\n"
            "Future date choose karein 👇"
        ),
        "available_on": "{date} ko available",
        "next_7_days": "Agale available din",

        "select_slot": "Time slot select karein",
        "available_slots": "Available time slots (IST)",
        "time_slots": "Time Slots",
        "slot_retry": "List se time slot select karein 👇",
        "invalid_slot": "Galat time slot select hua hai. Dobara try karein 👇",
        "no_slots": (
            "⚠️ Is date ke liye koi time slot available nahi hai.\n"
            "Dusri date choose karein 👇"
        ),

        "booking_missing": (
            "⚠️ Kuch booking details missing hain.\n"
            "Kripya booking dobara start karein."
        ),
        "free_limit_reached": (
            "🚫 Free AI limit khatam ho gayi hai.\n"
            "Consultation book karein."
        ),
        "payment_in_progress": (
            "⚠️ Payment process mein hai.\n"
            "Kripya complete hone dein."
        ),
        "payment_success": (
            "💳 Payment successful.\n"
            "Aapki consultation confirm ho gayi hai."
        ),
        "session_start": (
            "✅ *Payment successfully receive ho gaya.*\n\n"
            "Ab aap yahan apne legal questions pooch sakte hain.\n"
            "Legal expert aapko scheduled date aur time par call karega."
        ),
        
        "appointment_summary": (
            "✅ Aapke appointment details:\n"
            "Naam: {name}\n"
            "State: {state}\n"
            "District: {district}\n"
            "Category: {category}\n"
            "Date: {date}\n"
            "Slot: {slot}\n"
            "Fees: ₹{amount} (one-time session) 🙂\n\n"
            "Kripya payment complete karein:"
        ),
        "invalid_selection": "Galat selection. Dobara try karein 👇",
    },

    # =====================================================
    # 🇮🇳 MARATHI
    # =====================================================
    "mr": {
        "welcome": (
            "👋 NyaySetu मध्ये आपले स्वागत आहे ⚖️\n\n"
            "🆔 केस आयडी: {case_id}\n\n"
            "कृपया आपली भाषा निवडा:"
        ),
        "restart": "🔄 सत्र रीसेट झाले.\n*Hi* टाइप करून पुन्हा सुरू करा.",

        "ask_ai_or_book": "आपण पुढे कसे जायचे आहे?",
        "ask_ai": "AI ला विचारा",
        "ask_ai_prompt": "🤖 आपला कायदेशीर प्रश्न विचारा.",
        "ai_cooldown": "⏳ कृपया थोडा वेळ थांबून पुन्हा संदेश पाठवा.",
        "book_consult": "सल्ला बुक करा",

        "rate_limit_exceeded": (
            "⏳ आपण खूप वेगाने संदेश पाठवत आहात.\n"
            "कृपया थोडा वेळ थांबा."
        ),

        "ask_name": "कृपया आपले *पूर्ण नाव* सांगा.",
        "ask_name_retry": "कृपया आपले *पूर्ण नाव* पुन्हा टाका 🙂",

        "ask_state": "आपण कोणत्या *राज्यात* आहात?",
        "ask_state_retry": "कृपया आपले *राज्य* निवडा किंवा लिहा 🙂",
        "choose_state": "राज्य निवडा",
        "choose_state_or_more": "राज्य निवडा किंवा More वर टॅप करा",
        "thanks_state": "धन्यवाद 🙏\nआपण कोणत्या राज्यात आहात?",
        "select_state": "राज्य निवडा",
        "indian_states": "भारतीय राज्ये",

        "ask_district": "जिल्हा निवडा",
        "choose_district": "आपला जिल्हा निवडा",
        "select_district_in": "{state} मधील जिल्हा निवडा",
        "district_invalid": (
            "❌ *{district}* हा जिल्हा {state} मध्ये आढळला नाही.\n"
            "खालील यादीतून निवडा 👇"
        ),

        "select_category": "कायदेशीर श्रेणी निवडा",
        "choose_category": "आपल्या समस्येशी जुळणारी श्रेणी निवडा",
        "category_retry": "कृपया यादीतून कायदेशीर श्रेणी निवडा 👇",

        "select_subcategory": "उप-श्रेणी निवडा",
        "choose_subcategory": "समस्येचा प्रकार निवडा",
        "subcategory_retry": "कृपया यादीतून उप-श्रेणी निवडा 👇",
        "subcategory_mismatch": (
            "निवडलेली उप-श्रेणी मुख्य श्रेणीशी जुळत नाही.\n"
            "कृपया पुन्हा प्रयत्न करा 👇"
        ),

        "select_date": "अपॉइंटमेंटची तारीख निवडा 👇",
        "select_date_retry": "कृपया यादीतून अपॉइंटमेंट *तारीख* निवडा 👇",
        "available_dates": "उपलब्ध तारखा",
        "invalid_date": "चुकीची तारीख निवडली आहे. पुन्हा निवडा 👇",
        "past_date_error": (
            "⚠️ आपण मागील किंवा आजची तारीख निवडू शकत नाही.\n"
            "भविष्यातील तारीख निवडा 👇"
        ),
        "available_on": "{date} रोजी उपलब्ध",
        "next_7_days": "पुढील उपलब्ध दिवस",

        "select_slot": "वेळ निवडा",
        "available_slots": "उपलब्ध वेळा (IST)",
        "time_slots": "वेळा",
        "slot_retry": "कृपया यादीतून वेळ निवडा 👇",
        "invalid_slot": "चुकीची वेळ निवडली आहे. पुन्हा प्रयत्न करा 👇",
        "no_slots": (
            "⚠️ या तारखेसाठी कोणतीही वेळ उपलब्ध नाही.\n"
            "दुसरी तारीख निवडा 👇"
        ),

        "booking_missing": (
            "⚠️ काही बुकिंग तपशील अपूर्ण आहेत.\n"
            "कृपया बुकिंग पुन्हा सुरू करा."
        ),
        "free_limit_reached": (
            "🚫 मोफत AI मर्यादा संपली आहे.\n"
            "सल्ला बुक करा."
        ),
        "payment_in_progress": (
            "⚠️ पेमेंट सुरू आहे.\n"
            "कृपया पूर्ण होऊ द्या."
        ),
        "payment_success": (
            "💳 पेमेंट यशस्वी.\n"
            "आपली सल्लामसलत निश्चित झाली आहे."
        ),
        "session_start": (
            "✅ *पेमेंट यशस्वीरीत्या प्राप्त झाले आहे.*\n\n"
            "आता आपण येथे आपले कायदेशीर प्रश्न विचारू शकता.\n"
            "नियोजित तारीख व वेळेस आमचे तज्ज्ञ आपल्याशी संपर्क साधतील."
        ),
        
        "appointment_summary": (
            "✅ आपल्या अपॉइंटमेंटचे तपशील:\n"
            "नाव: {name}\n"
            "राज्य: {state}\n"
            "जिल्हा: {district}\n"
            "श्रेणी: {category}\n"
            "तारीख: {date}\n"
            "वेळ: {slot}\n"
            "फीस: ₹{amount} (एकदाच सत्र) 🙂\n\n"
            "कृपया पेमेंट पूर्ण करा:"
        ),

        "invalid_selection": "चुकीची निवड. कृपया पुन्हा प्रयत्न करा 👇",
    },
}
