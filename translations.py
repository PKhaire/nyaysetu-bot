TRANSLATIONS = {

    # =====================================================
    # 🇬🇧 ENGLISH (DEFAULT)
    # =====================================================
    "en": {
        # ---------- GENERAL ----------
        "welcome": (
            "🙏 Welcome to NyaySetu\n"
            "⚖️ The Bridge To Justice\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Please select your preferred language:"
        ),
        "restart": "Your session has been reset. Choose an option from the menu below.",

        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "How would you like to proceed?",
        "ask_ai": "Ask a Legal Question",
        "ask_ai_prompt": "Please type your legal query",
        "ai_cooldown": "Please wait for a moment before sending another message.",
        "book_consult": "Book Consultation",

        "rate_limit_exceeded": (
            "You are sending messages too quickly.\n"
            "Please wait for a moment and try again."
        ),
        # ---------- SYSTEM / STATUS ----------
        
        "ai_temporarily_unavailable": (
            "⚠️ AI service is temporarily unavailable.\n\n"
            "For personalised advice from a verified lawyer,\n"
            "type Book to continue with a paid consultation."
        ),
                
        "post_payment_ai_start": (
            "🤖 You can now ask your legal question."
        ),
        
        "consultation_expired": (
            "⏳ Your consultation window has ended.\n\n"
            "If you still need help, please book a new consultation."
        ),
        
        "consultation_already_confirmed": (
            "✅ Your consultation is confirmed.\n\n"
            "📄 Type RECEIPT for your receipt.\n"
            "💬 You may ask questions to prepare."
        ),
        "consultation_assistant_header": "Consultation Assistant",  
        "soft_booking_prompt": (
            "⚖️ Need personalised advice from a lawyer?"
        ),
        
        "ai_post_payment_cooldown": (
            "⏳ Please wait before asking another question."
        ),
        
        "receipt_pending": (
            "📄 Receipt will be available soon.\n"
            "Please contact support if required."
        ),
        
        "name_invalid": (
            "❌ Please enter a valid personal name.\n"
            "Example: Prashant Keshav Khaire"
        ),
        
        "verify_details": "Please verify your details:",
        
        "verified_button": "Verified",
        "edit_details_button": "Edit Details",
        
        "welcome_back": (
            "👋 Welcome back, {name}!\n\n"
            "What would you like to do today?"
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
        
        "ask_district_text": (
            "Please type the district where the concerned court is located "
            "(for example: Pune, Lucknow)."
        ),
        "district_not_identified": (
            "I couldn’t identify that district.\n"
            "Please type your district name (for example: Pune, Lucknow)."
        ),
        "district_multiple_matches": (
            "We found multiple matching districts.\n"
            "Please type the full district name."
        ),
        "district_retry": (
            "No problem 🙂\nPlease type your district again."
        ),
        
        # ---------- LOCATION CONFIRMATION ----------
        "location_found": "We found:",
        "confirm_location": "Is this correct?",
        "confirm_yes": "Yes",
        "confirm_change": "Change",

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
            "✅ Payment Successful\n\n"
            "Your legal consultation has been confirmed.\n\n"
            "📅 Date: {date}\n"
            "⏰ Time: {slot}\n"
            "💰 Fee Paid: ₹{amount}\n\n"
            "You will be contacted by the legal expert before the scheduled session.\n\n"
            "Thank you for choosing NyaySetu."
        ),
        "payment_success_reschedule_review": (
            "✅ Payment received\n\n"
            "Your payment of ₹{amount} is secure. The originally selected slot "
            "({date}, {slot}) became unavailable while payment confirmation was "
            "delayed, so our support team must arrange another slot or review a "
            "refund with you. Please do not make another payment. We will contact "
            "you using this WhatsApp number."
        ),

        "session_start": (
            "Payment received successfully.\n\n"
            "You may now submit your legal queries here.\n"
            "Our legal expert will contact you on the scheduled date and time."
        ),
        "payment_link_text": "Please use the secure link below to complete your payment:",
        "payment_link_error": "⚠️ Unable to generate payment link. Please try again.",
    
        "appointment_summary": (
            "📋 Appointment Summary\n\n"
            "Name: {name}\n"
            "Service Category: {category}\n"
            "Location: {district}, {state}\n"
            "Date: {date}\n"
            "Time: {slot}\n"
            "Consultation Fee: ₹{amount} (one-time)\n\n"
            "To confirm your appointment, please complete the payment below."
        ),
        "receipt_help": "If you have not received the receipt, please type RECEIPT.",

        # ---------- HOME & SELF-SERVICE ----------
        "home_menu": (
            "How can I help today?\n\n"
            "You can ask a general legal question, book a consultation, or open "
            "self-service options."
        ),
        "more_options": "More Options",
        "more_menu_header": "NyaySetu Services",
        "more_menu_body": "Choose an option. You can type MENU at any time to return home.",
        "more_menu_section": "Self-service",
        "my_appointment": "My Appointment",
        "my_appointment_desc": "View your latest booking",
        "prepare_consultation": "Prepare for Lawyer",
        "prepare_consultation_desc": "Documents and question checklist",
        "legal_guides": "Legal Guides",
        "legal_guides_desc": "Practical first-step information",
        "talk_to_support": "Talk to Support",
        "talk_to_support_desc": "Create a support request",
        "privacy_and_data": "Privacy & My Data",
        "privacy_and_data_desc": "How your information is used",
        "change_language": "Change Language",
        "change_language_desc": "English, Hindi/Hinglish, or Marathi",

        # ---------- BOOKING STATUS & PREPARATION ----------
        "no_appointment_found": (
            "No appointment was found yet. Choose Book Consultation from the home menu "
            "when you are ready."
        ),
        "booking_status_pending": "Awaiting payment",
        "booking_status_paid": "Confirmed and paid",
        "booking_status_expired": "Payment link expired",
        "booking_status_cancelled": "Cancelled",
        "booking_status_refunded": "Payment refunded",
        "booking_status_completed": "Consultation completed",
        "booking_status_unknown": "Status unavailable",
        "booking_status_summary": (
            "📅 *Appointment #{booking_id}*\n\n"
            "Status: {status}\n"
            "Matter: {category}\n"
            "Date: {date}\n"
            "Time: {slot} IST\n"
            "Fee: ₹{amount}"
        ),
        "preparation_checklist_message": (
            "🗂️ *Consultation preparation — {category}*\n\n{checklist}\n\n"
            "Do not send OTPs, passwords, complete identity numbers, or original "
            "documents in chat. Your lawyer will confirm what is actually required."
        ),

        # ---------- GUIDES, PRIVACY & SUPPORT ----------
        "guide_row_description": "General information and next steps",
        "guide_language_note": (
            "This guide is currently shown in English. Ask a legal question if you "
            "would like a simpler explanation in your selected language."
        ),
        "guide_disclaimer": (
            "General legal information only—not legal advice. Rules and deadlines can "
            "depend on the facts and current law; a qualified lawyer should verify them."
        ),
        "privacy_notice_short": (
            "🔐 NyaySetu uses your contact, matter details, booking, and payment status "
            "to provide this service. Please do not share OTPs, passwords, full Aadhaar/"
            "PAN numbers, bank credentials, or intimate evidence in chat. AI questions "
            "may be processed by a configured AI provider after you consent. You may "
            "ask support for access, correction, or deletion; some payment records may "
            "need to be retained for legal or accounting duties."
        ),
        "privacy_notice_link": "Full privacy notice",
        "support_phone": "Support phone",
        "support_email": "Support email",
        "support_prompt": (
            "Tell us briefly what you need help with. Do not include passwords, OTPs, "
            "bank credentials, or complete identity numbers. Your request will be saved "
            "for the NyaySetu support team."
        ),
        "support_request_saved": (
            "✅ Your support request *{ticket_id}* has been recorded. The team can use "
            "this reference when following up."
        ),
        "advocate_intake_saved": (
            "Your advocate-intake request *{ticket_id}* has been recorded. This is "
            "not a confirmed booking or advocate-client relationship. The NyaySetu "
            "team will review availability, scope, and conflict-check requirements "
            "before any consultation is offered."
        ),
        "support_request_retry": "Please describe the support issue in at least a few words.",
        "support_latest_status": "Latest support ticket {ticket_id}: {status}",
        "support_cancel": "Cancel",

        # ---------- AI CONSENT & BOOKING REVIEW ----------
        "ai_consent_prompt": (
            "Before using AI: NyaySetu provides general legal information, not legal "
            "advice. Your question may be processed by the configured AI provider. "
            "Please remove names, phone numbers, identity numbers, bank details, and "
            "other sensitive facts.\n\n"
            "Privacy notice: {privacy_url}\n"
            "Consent version: {policy_version}\n\n"
            "Do you consent to continue?"
        ),
        "ai_consent_accept": "I Consent",
        "ai_consent_decline": "No, Go Back",
        "booking_scope": (
            "A NyaySetu consultation costs *₹{amount}*. The booking connects you with "
            "the legal-support team for the selected date and time; outcomes are never "
            "guaranteed. We will collect only the details needed to arrange it.\n\n"
            "Would you like to continue?"
        ),
        "continue_booking": "Continue",
        "back_to_home": "Back to Home",
        "review_before_payment": (
            "Please review before we create the payment link.\n\n"
            "Name: {name}\n"
            "Matter: {category}\n"
            "Location: {district}, {state}\n"
            "Date: {date}\n"
            "Time: {slot} IST\n"
            "Fee: ₹{amount}\n\n"
            "Terms: {terms_url}\n"
            "Refund policy: {refund_url}\n"
            "Cancellation policy: {cancellation_url}\n"
            "Privacy: {privacy_url}\n"
            "Policy version: {policy_version}\n\n"
            "By choosing Accept & Pay, you accept these policies. You can change "
            "the date/time or cancel before paying."
        ),
        "pay_now": "Accept & Pay",
        "change_time": "Change Date/Time",
        "cancel_booking": "Cancel",
        "booking_cancelled_before_payment": "Booking cancelled. No payment link was created.",
        "payment_waiting_help": (
            "Your appointment is being held while payment is pending. Use the secure "
            "link below, check the latest status, or create a support request."
        ),
        "check_payment_status": "Check Status",
        "payment_help": "Payment Help",

        # ---------- FEEDBACK ----------
        "feedback_prompt": (
            "We hope your consultation was useful. Please rate your experience; your "
            "private feedback helps improve NyaySetu."
        ),
        "feedback_header": "Rate Consultation",
        "feedback_body": "Choose a rating from 1 to 5.",
        "feedback_section": "Your rating",
        "feedback_row_desc": "Tap to submit this rating",
        "feedback_rating_5": "5 ⭐ Excellent",
        "feedback_rating_4": "4 ⭐ Good",
        "feedback_rating_3": "3 ⭐ Okay",
        "feedback_rating_2": "2 ⭐ Needs improvement",
        "feedback_rating_1": "1 ⭐ Poor",
        "feedback_comment_prompt": (
            "Thank you. You may type one short private comment, or choose Skip."
        ),
        "feedback_skip": "Skip",
        "feedback_thanks": "Thank you—your feedback has been saved.",
        
        # ---------- COMMON ----------
        "select_button": "Select",
        "invalid_selection": "The selected option is invalid. Please try again.",
        "input_not_understood": (
            "I could not match that message to the current step. Your progress is "
            "safe—choose an option below, or type Menu at any time."
        ),
        "advocate_intake_invalid": (
            "I could not submit this advocate request because its prepared format "
            "was changed or incomplete. Please return to Ask an Advocate on "
            "nyaysetu.in and send a newly prepared message, or choose Support."
        ),
        "booking_record_problem": (
            "I could not safely open this appointment right now. No new payment was "
            "created. Please choose Support so the team can check it."
        ),
        "service_busy": (
            "NyaySetu is handling unusually high traffic. "
            "Please wait a moment and try again."
        ),
        "unsupported_message_type": (
            "I can currently handle text and menu selections. "
            "Please type your question, or type Support if you need help."
        ),
    },

    # =====================================================
    # 🇮🇳 HINGLISH
    # =====================================================
    "hi": {
        "welcome": (
            "🙏 NyaySetu mein aapka swagat hai\n"
            "⚖️ The Bridge To Justice\n\n"
            "🆔 Case ID: {case_id}\n\n"
            "Kripya apni pasand ki bhasha select karein:"
        ),
        "restart": "Aapka session reset ho gaya hai. Neeche menu se option chunein.",

        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "Aap kaise aage badhna chahenge?",
        "ask_ai": "Legal Sawal Poochho",
        "ask_ai_prompt": "Kripya apna legal prashn darj karein",
        "ai_cooldown": "Kripya agla message bhejne se pehle thoda intezaar karein.",
        "book_consult": "Book Consultation",

        "rate_limit_exceeded": (
            "Aap bahut tezi se messages bhej rahe hain.\n"
            "Kripya thoda intezaar karke dobara koshish karein."
        ),
        # ---------- SYSTEM / STATUS ----------
        
        "ai_temporarily_unavailable": (
            "⚠️ AI service filhaal uplabdh nahi hai.\n\n"
            "Verified lawyer se personalised salah ke liye,\n"
            "Book type karein aur paid consultation continue karein."
        ),
        
        "post_payment_ai_start": (
            "🤖 Ab aap apna legal prashn pooch sakte hain."
        ),
        
        "consultation_expired": (
            "⏳ Aapki consultation window samapt ho gayi hai.\n\n"
            "Agar abhi bhi madad chahiye, kripya nayi consultation book karein."
        ),
        
        "consultation_already_confirmed": (
            "✅ Aapki consultation confirm ho chuki hai.\n\n"
            "📄 Receipt ke liye RECEIPT type karein.\n"
            "💬 Aap prashn pooch sakte hain."
        ),
        "consultation_assistant_header": "Consultation Taiyari Assistant",        
        "soft_booking_prompt": (
            "⚖️ Personalised salah chahte hain?"
        ),
        
        "ai_post_payment_cooldown": (
            "⏳ Kripya agla prashn bhejne se pehle thoda intezaar karein."
        ),
        
        "receipt_pending": (
            "📄 Receipt jald uplabdh hogi.\n"
            "Zarurat ho to support se sampark karein."
        ),
        
        "name_invalid": (
            "❌ Kripya ek valid personal naam darj karein.\n"
            "Udaharan: Prashant Keshav Khaire"
        ),
        
        "verify_details": "Kripya apni details verify karein:",
        
        "verified_button": "Verified",
        "edit_details_button": "Edit Karein",
        
        "welcome_back": (
            "👋 Swagat hai, {name}!\n\n"
            "Aaj aap kya karna chahenge?"
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
        "ask_district_text": (
            "Kripya us zile ka naam likhein jahan sambandhit court sthit hai "
            "(jaise: Pune, Lucknow)."
        ),
        "district_not_identified": (
            "Yeh zila pehchana nahi ja saka.\n"
            "Kripya apne zile ka naam likhein (jaise: Pune, Lucknow)."
        ),
        "district_multiple_matches": (
            "Humein kai milte-julte zilon ke naam mile hain.\n"
            "Kripya poora zila naam likhein."
        ),
        "district_retry": (
            "Koi baat nahi 🙂\nKripya apna zila dobara likhein."
        ),
        
        # ---------- LOCATION CONFIRMATION ----------
        "location_found": "Humein yeh jagah mili hai:",
        "confirm_location": "Kya yeh sahi hai?",
        "confirm_yes": "Haan",
        "confirm_change": "Badlein",

        # ---------- CATEGORY ----------
        "select_category": "Legal Category",
        "choose_category": "Kripya apne legal matter se sabse zyada milti-julti category select karein.",
        "category_retry": "Kripya neeche di gayi list se ek legal category select karein.",
        
        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "Sub-Category",
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
            "✅ Payment Successful\n\n"
            "Aapki legal consultation confirm ho chuki hai.\n\n"
            "📅 Tareekh: {date}\n"
            "⏰ Time: {slot}\n"
            "💰 Fee Paid: ₹{amount}\n\n"
            "Nirdharit session se pehle legal expert aapse sampark karenge.\n\n"
            "NyaySetu chunne ke liye dhanyavaad."
        ),
        "payment_success_reschedule_review": (
            "✅ Payment mil gaya\n\n"
            "Aapka ₹{amount} payment secure hai. Confirmation delay ke dauran "
            "pehle chuna slot ({date}, {slot}) unavailable ho gaya. Support team "
            "naya slot arrange karegi ya refund review karegi. Dobara payment na "
            "karein; hum isi WhatsApp number par contact karenge."
        ),

        "session_start": (
            "Payment safalta se prapt ho gaya hai.\n\n"
            "Ab aap apne legal prashn yahan darj kar sakte hain.\n"
            "Hamare legal expert nirdharit tareekh aur samay par aapse sampark karenge."
        ),
        "payment_link_text": "Kripya payment poori karne ke liye neeche diya gaya surakshit link use karein:",
        "payment_link_error": "⚠️ Payment link generate nahi ho pa raha hai. Kripya dobara koshish karein.",


        "appointment_summary": (
            "📋 Appointment Summary\n\n"
            "Naam: {name}\n"
            "Service Category: {category}\n"
            "Location: {district}, {state}\n"
            "Tareekh: {date}\n"
            "Time: {slot}\n"
            "Consultation Fee: ₹{amount} (one-time)\n\n"
            "Appointment confirm karne ke liye kripya payment poori karein."
        ),
        "receipt_help": "Agar aapko receipt prapt nahi hui hai, to kripya RECEIPT type karein.",

        # ---------- HOME & SELF-SERVICE ----------
        "home_menu": (
            "Aaj main aapki kaise madad kar sakta hoon?\n\n"
            "Aap general legal sawaal poochh sakte hain, consultation book kar sakte "
            "hain, ya self-service options khol sakte hain."
        ),
        "more_options": "More Options",
        "more_menu_header": "NyaySetu Services",
        "more_menu_body": "Ek option choose karein. Home ke liye kabhi bhi MENU type karein.",
        "more_menu_section": "Self-service",
        "my_appointment": "My Appointment",
        "my_appointment_desc": "Apni latest booking dekhein",
        "prepare_consultation": "Lawyer Ke Liye Taiyari",
        "prepare_consultation_desc": "Documents aur questions checklist",
        "legal_guides": "Legal Guides",
        "legal_guides_desc": "Practical pehle steps",
        "talk_to_support": "Support Se Baat",
        "talk_to_support_desc": "Support request banayein",
        "privacy_and_data": "Privacy & My Data",
        "privacy_and_data_desc": "Aapki information ka use",
        "change_language": "Language Badlein",
        "change_language_desc": "English, Hindi/Hinglish ya Marathi",

        # ---------- BOOKING STATUS & PREPARATION ----------
        "no_appointment_found": (
            "Abhi koi appointment nahi mili. Ready hone par home menu se Book "
            "Consultation choose karein."
        ),
        "booking_status_pending": "Payment ka intezaar",
        "booking_status_paid": "Confirmed aur paid",
        "booking_status_expired": "Payment link expire ho gaya",
        "booking_status_cancelled": "Cancelled",
        "booking_status_refunded": "Payment refund ho gaya",
        "booking_status_completed": "Consultation complete",
        "booking_status_unknown": "Status available nahi",
        "booking_status_summary": (
            "📅 *Appointment #{booking_id}*\n\n"
            "Status: {status}\n"
            "Matter: {category}\n"
            "Date: {date}\n"
            "Time: {slot} IST\n"
            "Fee: ₹{amount}"
        ),
        "preparation_checklist_message": (
            "🗂️ *Consultation ki taiyari — {category}*\n\n{checklist}\n\n"
            "Chat mein OTP, password, poore identity numbers ya original documents "
            "mat bhejein. Lawyer confirm karega ki kya zaroori hai."
        ),

        # ---------- GUIDES, PRIVACY & SUPPORT ----------
        "guide_row_description": "General information aur next steps",
        "guide_language_note": (
            "Yeh guide abhi English mein hai. Selected language mein simple explanation "
            "ke liye legal sawaal poochhein."
        ),
        "guide_disclaimer": (
            "Yeh sirf general legal information hai, legal advice nahi. Facts aur current "
            "law ke hisaab se rules/deadlines badal sakti hain; lawyer se verify karein."
        ),
        "privacy_notice_short": (
            "🔐 NyaySetu service dene ke liye aapka contact, matter details, booking aur "
            "payment status use karta hai. Chat mein OTP, password, poora Aadhaar/PAN, "
            "bank credentials ya intimate evidence mat bhejein. Consent ke baad AI "
            "questions configured AI provider process kar sakta hai. Access, correction "
            "ya deletion ke liye support se poochh sakte hain; kuch payment records legal "
            "ya accounting duties ke liye rakhne pad sakte hain."
        ),
        "privacy_notice_link": "Full privacy notice",
        "support_phone": "Support phone",
        "support_email": "Support email",
        "support_prompt": (
            "Short mein batayein ki kis help ki zaroorat hai. Password, OTP, bank "
            "credentials ya poore identity numbers mat likhein. Request NyaySetu support "
            "team ke liye save hogi."
        ),
        "support_request_saved": (
            "✅ Aapki support request *{ticket_id}* record ho gayi hai. Follow-up mein "
            "team ko yeh reference batayein."
        ),
        "advocate_intake_saved": (
            "Aapki advocate-intake request *{ticket_id}* record ho gayi hai. Yeh "
            "confirmed booking ya advocate-client relationship nahi hai. NyaySetu "
            "team kisi consultation ko offer karne se pehle availability, scope aur "
            "conflict-check requirements review karegi."
        ),
        "support_request_retry": "Kripya support issue ko kuch shabdon mein samjhaayein.",
        "support_latest_status": "Latest support ticket {ticket_id}: {status}",
        "support_cancel": "Cancel",

        # ---------- AI CONSENT & BOOKING REVIEW ----------
        "ai_consent_prompt": (
            "AI use karne se pehle: NyaySetu general legal information deta hai, legal "
            "advice nahi. Aapka sawaal configured AI provider process kar sakta hai. "
            "Names, phone numbers, identity numbers, bank details aur sensitive facts "
            "hata dein.\n\n"
            "Privacy notice: {privacy_url}\n"
            "Consent version: {policy_version}\n\n"
            "Kya aap continue karne ki consent dete hain?"
        ),
        "ai_consent_accept": "I Consent",
        "ai_consent_decline": "Nahi, Wapas",
        "booking_scope": (
            "NyaySetu consultation ki fee *₹{amount}* hai. Booking selected date/time "
            "par legal-support team se connect karti hai; outcome ki guarantee kabhi "
            "nahi hoti. Hum sirf arrangement ke liye zaroori details lenge.\n\n"
            "Kya aap continue karna chahenge?"
        ),
        "continue_booking": "Continue",
        "back_to_home": "Home Par Wapas",
        "review_before_payment": (
            "Payment link banane se pehle details check karein.\n\n"
            "Naam: {name}\n"
            "Matter: {category}\n"
            "Location: {district}, {state}\n"
            "Date: {date}\n"
            "Time: {slot} IST\n"
            "Fee: ₹{amount}\n\n"
            "Terms: {terms_url}\n"
            "Refund policy: {refund_url}\n"
            "Cancellation policy: {cancellation_url}\n"
            "Privacy: {privacy_url}\n"
            "Policy version: {policy_version}\n\n"
            "Accept & Pay chun kar aap in policies ko accept karte hain. Pay karne "
            "se pehle date/time badal ya booking cancel kar sakte hain."
        ),
        "pay_now": "Accept & Pay",
        "change_time": "Date/Time Badlein",
        "cancel_booking": "Cancel",
        "booking_cancelled_before_payment": "Booking cancel ho gayi. Payment link nahi banaya gaya.",
        "payment_waiting_help": (
            "Payment pending hone tak appointment hold hai. Secure link use karein, "
            "latest status check karein, ya support request banayein."
        ),
        "check_payment_status": "Check Status",
        "payment_help": "Payment Help",

        # ---------- FEEDBACK ----------
        "feedback_prompt": (
            "Umeed hai consultation useful rahi. Private rating dein—isse NyaySetu ko "
            "behtar banane mein madad milti hai."
        ),
        "feedback_header": "Rate Consultation",
        "feedback_body": "1 se 5 tak rating choose karein.",
        "feedback_section": "Aapki rating",
        "feedback_row_desc": "Rating submit karne ke liye tap karein",
        "feedback_rating_5": "5 ⭐ Bahut achha",
        "feedback_rating_4": "4 ⭐ Achha",
        "feedback_rating_3": "3 ⭐ Theek",
        "feedback_rating_2": "2 ⭐ Sudhar chahiye",
        "feedback_rating_1": "1 ⭐ Kharab",
        "feedback_comment_prompt": "Dhanyavaad. Ek short private comment type karein ya Skip choose karein.",
        "feedback_skip": "Skip",
        "feedback_thanks": "Dhanyavaad—aapka feedback save ho gaya hai.",
        
        # ---------- COMMON ----------
        "select_button": "Chunein",
        "invalid_selection": "Select kiya gaya option valid nahi hai. Kripya dobara koshish karein.",
        "input_not_understood": (
            "Yeh message current step se match nahi hua. Aapki progress safe hai—"
            "neeche option chunein, ya kabhi bhi Menu type karein."
        ),
        "advocate_intake_invalid": (
            "Advocate request ka prepared format badla hua ya adhura tha, isliye "
            "submit nahi hua. nyaysetu.in par Ask an Advocate se naya prepared "
            "message bhejein, ya Support chunein."
        ),
        "booking_record_problem": (
            "Appointment abhi safely open nahi ho pa raha. Koi naya payment nahi "
            "bana hai. Team se check karane ke liye Support chunein."
        ),
        "service_busy": (
            "NyaySetu par abhi traffic zyada hai. "
            "Kripya thoda intezaar karke dobara koshish karein."
        ),
        "unsupported_message_type": (
            "Abhi main text aur menu selection samajh sakta hoon. "
            "Apna sawal type karein, ya madad ke liye Support type karein."
        ),

    },

    # =====================================================
    # 🇮🇳 MARATHI
    # =====================================================
    "mr": {
        "welcome": (
            "🙏 न्यायसेतू मध्ये आपले स्वागत आहे\n"
            "⚖️ न्यायकडे नेणारा मार्ग\n\n"
            "🆔 केस आयडी: {case_id}\n\n"
            "कृपया आपली पसंतीची भाषा निवडा:"
        ),
        "restart": "आपले सत्र रीसेट झाले आहे. खालील मेनूमधून पर्याय निवडा.",
        
        # ---------- LEGAL GUIDANCE ----------
        "ask_ai_or_book": "आपण पुढे कसे जायचे आहे?",
        "ask_ai": "कायदेशीर प्रश्न विचारा",
        "ask_ai_prompt": "कृपया आपला कायदेशीर प्रश्न लिहा",
        "ai_cooldown": "कृपया पुढील संदेश पाठवण्यापूर्वी थोडा वेळ थांबा.",
        "book_consult": "सल्लामसलत बुक करा",

        "rate_limit_exceeded": (
            "आपण खूप वेगाने संदेश पाठवत आहात.\n"
            "कृपया थोडा वेळ थांबून पुन्हा प्रयत्न करा."
        ),
        # ---------- SYSTEM / STATUS ----------
        
        "ai_temporarily_unavailable": (
            "⚠️ AI सेवा सध्या उपलब्ध नाही.\n\n"
            "प्रमाणित वकिलाकडून वैयक्तिक सल्ल्यासाठी,\n"
            "कृपया Book टाइप करा आणि सशुल्क सल्लामसलत सुरू ठेवा."
        ),
        
        "post_payment_ai_start": (
            "🤖 आता आपण आपला कायदेशीर प्रश्न विचारू शकता."
        ),
        
        "consultation_expired": (
            "⏳ आपली सल्लामसलत वेळ संपली आहे.\n\n"
            "आपल्याला अजून मदत हवी असल्यास, कृपया नवी सल्लामसलत बुक करा."
        ),
        
        "consultation_already_confirmed": (
            "✅ आपली सल्लामसलत निश्चित झाली आहे.\n\n"
            "📄 पावतीसाठी RECEIPT टाइप करा.\n"
            "💬 आपण प्रश्न विचारू शकता."
        ),
        "consultation_assistant_header": "सल्लामसलत तयारी सहाय्यक",
        
        "soft_booking_prompt": (
            "⚖️ वैयक्तिक कायदेशीर सल्ला हवा आहे का?"
        ),
        
        "ai_post_payment_cooldown": (
            "⏳ कृपया पुढील प्रश्न विचारण्यापूर्वी थोडा वेळ थांबा."
        ),
        
        "receipt_pending": (
            "📄 पावती लवकरच उपलब्ध होईल.\n"
            "गरज असल्यास सपोर्टशी संपर्क साधा."
        ),
        
        "name_invalid": (
            "❌ कृपया वैध वैयक्तिक नाव नोंदवा.\n"
            "उदाहरण: Prashant Keshav Khaire"
        ),
        
        "verify_details": "कृपया आपली माहिती तपासा:",
        
        "verified_button": "तपासले",
        "edit_details_button": "माहिती बदला",
        
        "welcome_back": (
            "👋 स्वागत आहे, {name}!\n\n"
            "आज आपण काय करू इच्छिता?"
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
          "ask_district_text": (
            "कृपया संबंधित न्यायालय ज्या जिल्ह्यात आहे तो जिल्हा लिहा "
            "(उदा.: Pune, Nagpur)."
        ),
        "district_not_identified": (
            "हा जिल्हा ओळखता आला नाही.\n"
            "कृपया आपला जिल्हा लिहा (उदा.: Pune, Lucknow)."
        ),
         "district_multiple_matches": (
            "एकाहून अधिक जुळणारे जिल्हे सापडले आहेत.\n"
            "कृपया पूर्ण जिल्ह्याचे नाव लिहा."
        ),
           "district_retry": (
            "काही हरकत नाही 🙂\nकृपया आपला जिल्हा पुन्हा लिहा."
        ),
        
        # ---------- LOCATION CONFIRMATION ----------
        "location_found": "आम्हाला खालील ठिकाण सापडले आहे:",
        "confirm_location": "हे बरोबर आहे का?",
        "confirm_yes": "होय",
        "confirm_change": "बदला",
  
        # ---------- CATEGORY ----------
        "select_category": "कायदेशीर श्रेणी निवडा",
        "choose_category": "कृपया आपल्या कायदेशीर विषयाशी संबंधित श्रेणी निवडा",
        "category_retry": "कृपया खाली दिलेल्या यादीतून कायदेशीर श्रेणी निवडा.",
        
        # ---------- SUB-CATEGORY ----------
        "select_subcategory": "उप-श्रेणी निवडा",
        "choose_subcategory": "कृपया आपल्या प्रकरणाशी संबंधित पर्याय निवडा.",
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
            "✅ पेमेंट यशस्वी\n\n"
            "आपली कायदेशीर सल्लामसलत निश्चित झाली आहे.\n\n"
            "📅 तारीख: {date}\n"
            "⏰ वेळ: {slot}\n"
            "💰 भरलेली रक्कम: ₹{amount}\n\n"
            "निश्चित केलेल्या सत्रापूर्वी कायदेशीर तज्ञ आपल्याशी संपर्क करतील.\n\n"
            "न्यायसेतू निवडल्याबद्दल धन्यवाद."
        ),
        "payment_success_reschedule_review": (
            "✅ पेमेंट प्राप्त झाले\n\n"
            "आपले ₹{amount} पेमेंट सुरक्षित आहे. पेमेंट पुष्टीस विलंब झाल्यामुळे "
            "मूळ वेळ ({date}, {slot}) उपलब्ध राहिली नाही. सपोर्ट टीम नवीन वेळ "
            "ठरवेल किंवा परताव्याचा आढावा घेईल. पुन्हा पेमेंट करू नका; आम्ही "
            "याच WhatsApp क्रमांकावर संपर्क करू."
        ),

        "session_start": (
            "पेमेंट यशस्वीरीत्या प्राप्त झाले आहे.\n\n"
            "आता आपण आपले कायदेशीर प्रश्न येथे नोंदवू शकता.\n"
            "आमचे कायदेशीर तज्ञ निश्चित केलेल्या तारीख आणि वेळेला आपल्याशी संपर्क साधतील."
        ),
        "payment_link_text": "कृपया पेमेंट पूर्ण करण्यासाठी खाली दिलेला सुरक्षित लिंक वापरा:",
        "payment_link_error": "⚠️ पेमेंट लिंक तयार करता आली नाही. कृपया पुन्हा प्रयत्न करा.",

        "appointment_summary": (
            "📋 अपॉइंटमेंट सारांश\n\n"
            "नाव: {name}\n"
            "सेवा श्रेणी: {category}\n"
            "ठिकाण: {district}, {state}\n"
            "तारीख: {date}\n"
            "वेळ: {slot}\n"
            "सल्लामसलत शुल्क: ₹{amount} (एकदाच)\n\n"
            "अपॉइंटमेंट निश्चित करण्यासाठी कृपया खालील पेमेंट पूर्ण करा."
        ),

        "receipt_help": "आपल्याला पावती प्राप्त झाली नसेल तर कृपया RECEIPT टाइप करा.",

        # ---------- HOME & SELF-SERVICE ----------
        "home_menu": (
            "आज मी आपली कशी मदत करू शकतो?\n\n"
            "आपण सामान्य कायदेशीर प्रश्न विचारू शकता, सल्लामसलत बुक करू शकता किंवा "
            "स्वयं-सेवा पर्याय उघडू शकता."
        ),
        "more_options": "अधिक पर्याय",
        "more_menu_header": "न्यायसेतू सेवा",
        "more_menu_body": "एक पर्याय निवडा. मुख्य मेनूसाठी कधीही MENU टाइप करा.",
        "more_menu_section": "स्वयं-सेवा",
        "my_appointment": "माझी अपॉइंटमेंट",
        "my_appointment_desc": "नवीनतम बुकिंग पहा",
        "prepare_consultation": "वकिलांसाठी तयारी",
        "prepare_consultation_desc": "कागदपत्रे व प्रश्नांची यादी",
        "legal_guides": "कायदेशीर मार्गदर्शक",
        "legal_guides_desc": "व्यावहारिक पहिले टप्पे",
        "talk_to_support": "सपोर्टशी बोला",
        "talk_to_support_desc": "सपोर्ट विनंती तयार करा",
        "privacy_and_data": "गोपनीयता व माझा डेटा",
        "privacy_and_data_desc": "माहिती कशी वापरली जाते",
        "change_language": "भाषा बदला",
        "change_language_desc": "English, Hindi/Hinglish किंवा मराठी",

        # ---------- BOOKING STATUS & PREPARATION ----------
        "no_appointment_found": (
            "अद्याप कोणतीही अपॉइंटमेंट आढळली नाही. तयार झाल्यावर मुख्य मेनूमधून "
            "सल्लामसलत बुक करा."
        ),
        "booking_status_pending": "पेमेंट प्रलंबित",
        "booking_status_paid": "निश्चित आणि पेमेंट झाले",
        "booking_status_expired": "पेमेंट लिंकची मुदत संपली",
        "booking_status_cancelled": "रद्द",
        "booking_status_refunded": "पेमेंट परत केले",
        "booking_status_completed": "सल्लामसलत पूर्ण",
        "booking_status_unknown": "स्थिती उपलब्ध नाही",
        "booking_status_summary": (
            "📅 *अपॉइंटमेंट #{booking_id}*\n\n"
            "स्थिती: {status}\n"
            "विषय: {category}\n"
            "तारीख: {date}\n"
            "वेळ: {slot} IST\n"
            "शुल्क: ₹{amount}"
        ),
        "preparation_checklist_message": (
            "🗂️ *सल्लामसलतीची तयारी — {category}*\n\n{checklist}\n\n"
            "चॅटमध्ये OTP, पासवर्ड, पूर्ण ओळख क्रमांक किंवा मूळ कागदपत्रे पाठवू नका. "
            "प्रत्यक्षात काय आवश्यक आहे ते वकील निश्चित करतील."
        ),

        # ---------- GUIDES, PRIVACY & SUPPORT ----------
        "guide_row_description": "सामान्य माहिती आणि पुढील टप्पे",
        "guide_language_note": (
            "हा मार्गदर्शक सध्या इंग्रजीत आहे. निवडलेल्या भाषेत सोपे स्पष्टीकरण "
            "हवे असल्यास कायदेशीर प्रश्न विचारा."
        ),
        "guide_disclaimer": (
            "ही फक्त सामान्य कायदेशीर माहिती आहे, कायदेशीर सल्ला नाही. तथ्ये आणि "
            "सध्याच्या कायद्यानुसार नियम/मुदती बदलू शकतात; वकिलांकडून पडताळणी करा."
        ),
        "privacy_notice_short": (
            "🔐 सेवा देण्यासाठी न्यायसेतू आपला संपर्क, प्रकरणाचे तपशील, बुकिंग व "
            "पेमेंट स्थिती वापरते. चॅटमध्ये OTP, पासवर्ड, पूर्ण आधार/PAN क्रमांक, "
            "बँक तपशील किंवा अतिसंवेदनशील पुरावे पाठवू नका. संमतीनंतर AI प्रश्न "
            "कॉन्फिगर केलेल्या AI प्रदात्याकडून प्रक्रिया होऊ शकतात. प्रवेश, दुरुस्ती "
            "किंवा हटवण्याबाबत सपोर्टला विचारू शकता; काही पेमेंट नोंदी कायदेशीर किंवा "
            "लेखा कर्तव्यांसाठी ठेवाव्या लागू शकतात."
        ),
        "privacy_notice_link": "संपूर्ण गोपनीयता सूचना",
        "support_phone": "सपोर्ट फोन",
        "support_email": "सपोर्ट ईमेल",
        "support_prompt": (
            "आपल्याला कोणती मदत हवी आहे ते थोडक्यात लिहा. पासवर्ड, OTP, बँक तपशील "
            "किंवा पूर्ण ओळख क्रमांक लिहू नका. विनंती न्यायसेतू सपोर्ट टीमसाठी जतन होईल."
        ),
        "support_request_saved": (
            "✅ आपली सपोर्ट विनंती *{ticket_id}* नोंदवली आहे. पुढील संपर्कासाठी हा "
            "संदर्भ वापरा."
        ),
        "advocate_intake_saved": (
            "आपली वकील-सल्ला विनंती *{ticket_id}* नोंदवली आहे. ही निश्चित बुकिंग "
            "किंवा वकील-अशील नाते नाही. कोणतेही सल्लामसलत सत्र देण्यापूर्वी "
            "न्यायसेतू टीम उपलब्धता, कामाची व्याप्ती आणि हितसंबंध-विरोध "
            "तपासणीची गरज पाहील."
        ),
        "support_request_retry": "कृपया सपोर्ट समस्या काही शब्दांत स्पष्ट करा.",
        "support_latest_status": "नवीनतम सपोर्ट तिकीट {ticket_id}: {status}",
        "support_cancel": "रद्द करा",

        # ---------- AI CONSENT & BOOKING REVIEW ----------
        "ai_consent_prompt": (
            "AI वापरण्यापूर्वी: न्यायसेतू सामान्य कायदेशीर माहिती देते, कायदेशीर "
            "सल्ला नाही. आपला प्रश्न कॉन्फिगर केलेला AI प्रदाता प्रक्रिया करू शकतो. "
            "नावे, फोन, ओळख क्रमांक, बँक तपशील आणि संवेदनशील तथ्ये काढून टाका.\n\n"
            "गोपनीयता सूचना: {privacy_url}\n"
            "संमती आवृत्ती: {policy_version}\n\n"
            "पुढे जाण्यास आपली संमती आहे का?"
        ),
        "ai_consent_accept": "मी संमती देतो/देते",
        "ai_consent_decline": "नाही, मागे जा",
        "booking_scope": (
            "न्यायसेतू सल्लामसलतीचे शुल्क *₹{amount}* आहे. बुकिंग निवडलेल्या तारीख/"
            "वेळी कायदेशीर-सपोर्ट टीमशी जोडते; निकालाची हमी कधीही दिली जात नाही. "
            "व्यवस्थेसाठी आवश्यक तेवढीच माहिती घेतली जाईल.\n\nपुढे जायचे आहे का?"
        ),
        "continue_booking": "पुढे चला",
        "back_to_home": "मुख्य मेनू",
        "review_before_payment": (
            "पेमेंट लिंक तयार करण्यापूर्वी तपशील तपासा.\n\n"
            "नाव: {name}\n"
            "विषय: {category}\n"
            "ठिकाण: {district}, {state}\n"
            "तारीख: {date}\n"
            "वेळ: {slot} IST\n"
            "शुल्क: ₹{amount}\n\n"
            "अटी: {terms_url}\n"
            "परतावा धोरण: {refund_url}\n"
            "रद्द धोरण: {cancellation_url}\n"
            "गोपनीयता: {privacy_url}\n"
            "धोरण आवृत्ती: {policy_version}\n\n"
            "स्वीकारा आणि पेमेंट करा निवडून आपण ही धोरणे स्वीकारता. पेमेंटपूर्वी "
            "तारीख/वेळ बदलू किंवा बुकिंग रद्द करू शकता."
        ),
        "pay_now": "स्वीकारा व पेमेंट",
        "change_time": "तारीख/वेळ बदला",
        "cancel_booking": "रद्द करा",
        "booking_cancelled_before_payment": "बुकिंग रद्द झाले. पेमेंट लिंक तयार केली नाही.",
        "payment_waiting_help": (
            "पेमेंट प्रलंबित असताना अपॉइंटमेंट राखीव आहे. सुरक्षित लिंक वापरा, नवीनतम "
            "स्थिती तपासा किंवा सपोर्ट विनंती तयार करा."
        ),
        "check_payment_status": "स्थिती तपासा",
        "payment_help": "पेमेंट मदत",

        # ---------- FEEDBACK ----------
        "feedback_prompt": (
            "आपली सल्लामसलत उपयुक्त ठरली अशी आशा आहे. खाजगी रेटिंग द्या—यामुळे "
            "न्यायसेतू सुधारण्यास मदत होते."
        ),
        "feedback_header": "सल्लामसलत रेट करा",
        "feedback_body": "१ ते ५ रेटिंग निवडा.",
        "feedback_section": "आपले रेटिंग",
        "feedback_row_desc": "रेटिंग सबमिट करण्यासाठी टॅप करा",
        "feedback_rating_5": "5 ⭐ उत्कृष्ट",
        "feedback_rating_4": "4 ⭐ चांगले",
        "feedback_rating_3": "3 ⭐ ठीक",
        "feedback_rating_2": "2 ⭐ सुधारणा हवी",
        "feedback_rating_1": "1 ⭐ खराब",
        "feedback_comment_prompt": "धन्यवाद. छोटा खाजगी अभिप्राय लिहा किंवा वगळा.",
        "feedback_skip": "वगळा",
        "feedback_thanks": "धन्यवाद—आपला अभिप्राय जतन केला आहे.",
        
        # ---------- COMMON ----------
        "select_button": "निवडा",
        "invalid_selection": "निवडलेला पर्याय वैध नाही. कृपया पुन्हा प्रयत्न करा.",
        "input_not_understood": (
            "हा संदेश सध्याच्या टप्प्याशी जुळला नाही. आपली प्रगती सुरक्षित आहे—"
            "खालील पर्याय निवडा किंवा कधीही Menu टाइप करा."
        ),
        "advocate_intake_invalid": (
            "वकील विनंतीचा तयार नमुना बदललेला किंवा अपूर्ण असल्याने ती सबमिट "
            "झाली नाही. nyaysetu.in वरील Ask an Advocate मधून नवीन तयार संदेश "
            "पाठवा किंवा Support निवडा."
        ),
        "booking_record_problem": (
            "ही अपॉइंटमेंट सध्या सुरक्षितपणे उघडता आली नाही. नवीन पेमेंट तयार "
            "झालेले नाही. तपासणीसाठी Support निवडा."
        ),
        "service_busy": (
            "न्यायसेतूवर सध्या जास्त रहदारी आहे. "
            "कृपया थोडा वेळ थांबून पुन्हा प्रयत्न करा."
        ),
        "unsupported_message_type": (
            "सध्या मी मजकूर आणि मेनू निवड हाताळू शकतो. "
            "आपला प्रश्न लिहा किंवा मदतीसाठी Support लिहा."
        ),

    },
}
