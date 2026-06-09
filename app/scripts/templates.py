"""
Call script templates. Each script_key maps to a set of messages the agent speaks.
All {placeholders} are filled at call time from customer/campaign data.
"""

SCRIPTS = {
    "sale_40_percent": {
        "intro": (
            "Hello, may I speak with {customer_name}? "
            "Hi {customer_name}! This is {agent_name} calling from {business_name}. "
            "I hope I'm not catching you at a bad time. "
            "I'm reaching out because we have an amazing sale happening this weekend only — "
            "40 percent off on all our premium carpets. "
            "This is one of our biggest discounts of the year and we wanted to make sure our valued customers heard about it first. "
            "Press 1 to hear more about the sale, "
            "press 2 if you'd like us to call you at a better time, "
            "or press 3 to be removed from our call list."
        ),
        "more_info": (
            "Our 40 percent off sale includes all carpet styles — "
            "from luxury wool to modern synthetics, and everything in between. "
            "The sale runs this Friday through Sunday at {store_address}. "
            "We also offer free in-home measurement and professional installation. "
            "Press 1 to get our store address sent to you by text, "
            "press 2 to speak with one of our carpet experts right now, "
            "press 3 to book an in-store visit, "
            "or press 9 to end this call."
        ),
        "book_confirm": (
            "Perfect! We've booked you an in-store visit and we'll text you the details. "
            "We can't wait to help you find the perfect carpet, {customer_name}! Goodbye."
        ),
        "callback": (
            "No problem at all! We'll give you a call back at a more convenient time. "
            "Thank you for your time, {customer_name}, and have a wonderful day!"
        ),
        "opt_out": (
            "I completely understand. We'll remove you from our call list right away. "
            "Thank you for your time, {customer_name}, and have a great day!"
        ),
        "sms_confirm": (
            "Great! We'll send our store details to this number right away. "
            "We look forward to seeing you, {customer_name}! Goodbye."
        ),
        "transfer": (
            "Wonderful! Please hold for just a moment while I connect you with one of our carpet specialists. "
            "They'll be happy to answer all your questions!"
        ),
        "no_input": (
            "I'm sorry, I didn't catch that. "
            "Press 1 to hear about our sale, press 2 for a callback, or press 9 to end this call."
        ),
        "goodbye": (
            "Thank you for your time, {customer_name}. Have a wonderful day! Goodbye."
        ),
    },

    "bogo_carpet": {
        "intro": (
            "Hello, may I speak with {customer_name}? "
            "Hi {customer_name}! This is {agent_name} calling from {business_name}. "
            "I have some exciting news — we're running a buy one get one free promotion on selected carpet ranges this week. "
            "That means when you purchase one carpet, you get a second one absolutely free! "
            "Press 1 to hear more, "
            "press 2 for a callback at a better time, "
            "or press 3 to opt out of future calls."
        ),
        "more_info": (
            "Our buy one get one free offer applies to our entire mid-range carpet collection — "
            "perfect for bedrooms, living rooms, and hallways. "
            "The offer is valid in-store at {store_address} until this Sunday. "
            "Press 1 to get our details by text, "
            "press 2 to speak with a specialist, "
            "press 3 to book an in-store visit, "
            "or press 9 to end the call."
        ),
        "book_confirm": (
            "Excellent! Your in-store visit is booked and we'll text you the details. "
            "See you soon, {customer_name}! Goodbye."
        ),
        "callback": (
            "Of course! We'll call you back at a better time. "
            "Thanks so much, {customer_name}. Have a great day!"
        ),
        "opt_out": (
            "Not a problem at all. We'll take you off our list immediately. "
            "Thank you, {customer_name}, and have a wonderful day!"
        ),
        "sms_confirm": (
            "Perfect! Check your texts shortly for our store info. "
            "We hope to see you soon, {customer_name}! Goodbye."
        ),
        "transfer": (
            "Brilliant! Hold on just a second while I connect you with a specialist who can help you choose the perfect carpet!"
        ),
        "no_input": (
            "Sorry about that — I didn't get a response. "
            "Press 1 to learn about the offer, press 2 for a callback, or press 9 to end this call."
        ),
        "goodbye": (
            "Thanks for your time, {customer_name}. Have a lovely day! Goodbye."
        ),
    },
}


def get_script(script_key: str, **kwargs) -> dict:
    template = SCRIPTS.get(script_key)
    if not template:
        raise ValueError(f"Unknown script key: {script_key}")
    return {k: v.format(**kwargs) for k, v in template.items()}
