"""
Swipe-file corpus + cliche-pattern regexes used by SwipeRiskDetector.

Sources for SWIPE_TEMPLATES are public / widely reprinted:
- Classic direct-response openers (Halbert, Kennedy, Sugarman) — reprinted thousands of times
- Public SaaS cold-outreach patterns (Lemlist blog, Apollo sequences library, Woodpecker)
- Breakup / re-engagement templates shared across marketing blogs
- Gmail/Outlook transactional boilerplates that frequently leak into marketing copy

We DO NOT need exhaustive coverage — the goal is to flag verbatim-or-near-verbatim
reuse of templates everyone has seen. Originality LLM rating catches the rest.
"""

# Each template is stored as plain text. The detector will shingle & fingerprint these.
SWIPE_TEMPLATES = [
    {
        "id": "cold_lemlist_01",
        "source": "Lemlist cold outreach (widely reproduced)",
        "text": (
            "Hope this email finds you well. "
            "I noticed you're the head of marketing at {company} and I had a quick idea I wanted to share. "
            "Most companies in your space are struggling with X, and we've helped dozens of teams solve it. "
            "Would you be open to a 15 minute call next week to see if it's a fit?"
        ),
    },
    {
        "id": "cold_breakup_01",
        "source": "Classic breakup email (universally copied)",
        "text": (
            "I've reached out a few times and haven't heard back, so I'll assume the timing isn't right. "
            "I don't want to keep cluttering your inbox. "
            "If anything changes, feel free to reach out. Otherwise I'll close the loop on my end."
        ),
    },
    {
        "id": "cold_permission_01",
        "source": "Permission-based opener (Patel, many copy coaches)",
        "text": (
            "Quick question for you. Are you still the right person to talk to about {topic}? "
            "If not, could you point me in the right direction? I promise not to take much of your time."
        ),
    },
    {
        "id": "cold_9word_01",
        "source": "Dean Jackson '9-word email' (reproduced everywhere)",
        "text": "Are you still interested in {topic}?"
    },
    {
        "id": "dr_halbert_opener_01",
        "source": "Halbert-style direct-response opener (public letters)",
        "text": (
            "Dear friend, I don't usually do this, but I'm writing to you today because I have something important to share. "
            "What I'm about to tell you could change everything for you. Please read this carefully."
        ),
    },
    {
        "id": "dr_kennedy_guarantee_01",
        "source": "Dan Kennedy no-risk guarantee block",
        "text": (
            "Try it risk-free for a full 30 days. If you're not completely thrilled, "
            "just send it back for a full refund. No questions asked. You keep the bonuses. "
            "That's how confident we are that this will work for you."
        ),
    },
    {
        "id": "saas_welcome_01",
        "source": "SaaS welcome email template (dozens of copycats)",
        "text": (
            "Welcome to {product}! We're thrilled to have you on board. "
            "Here are three things you can do right now to get the most out of your account: "
            "1) Complete your profile. 2) Invite your team. 3) Connect your first integration. "
            "If you have any questions, just reply to this email — a real human will get back to you."
        ),
    },
    {
        "id": "saas_trial_ending_01",
        "source": "Trial-ending reminder (universal SaaS template)",
        "text": (
            "Your free trial ends in 3 days. Don't lose access to everything you've built. "
            "Upgrade now to keep your data, your team, and your workflows in one place. "
            "Click below to pick the plan that's right for you."
        ),
    },
    {
        "id": "newsletter_welcome_01",
        "source": "Creator newsletter welcome (Substack / ConvertKit swipe)",
        "text": (
            "Hey there, thanks so much for subscribing. I'm genuinely excited to have you here. "
            "Every week I'll send you one email packed with actionable advice you can use the same day. "
            "No fluff, no spam, just the good stuff. Hit reply and tell me what you're working on — "
            "I read every single reply."
        ),
    },
    {
        "id": "promo_flash_sale_01",
        "source": "Flash-sale urgency email (Black Friday swipe)",
        "text": (
            "This is it. 24 hours left. Our biggest sale of the year ends tonight at midnight. "
            "Save up to 60% on everything. Once it's gone, it's gone. Don't miss out."
        ),
    },
    {
        "id": "webinar_invite_01",
        "source": "Webinar invite template (Russell Brunson style)",
        "text": (
            "I'm hosting a free training this Thursday where I'll reveal the exact system we use to {result}. "
            "Seats are limited. Grab yours before they fill up. "
            "P.S. Everyone who attends live gets a free bonus — you won't want to miss this."
        ),
    },
    {
        "id": "follow_up_bumping_01",
        "source": "'Bumping this' follow-up (cold outreach swipe)",
        "text": (
            "Just bumping this to the top of your inbox in case it got buried. "
            "Did you get a chance to look at my last email? Would love to hear your thoughts."
        ),
    },
    {
        "id": "review_request_01",
        "source": "Post-purchase review request (e-commerce swipe)",
        "text": (
            "How are you enjoying your {product}? We'd love to hear what you think. "
            "Your review helps other customers and helps us keep making great stuff. "
            "It only takes 60 seconds — click the stars below to get started."
        ),
    },
    {
        "id": "cart_abandon_01",
        "source": "Abandoned cart recovery (Shopify swipe)",
        "text": (
            "You left something in your cart. We saved it for you. "
            "Complete your order now before it's gone. "
            "Need help? Just reply to this email — we're here."
        ),
    },
    {
        "id": "content_value_01",
        "source": "Value-first content drop (Ramit Sethi style)",
        "text": (
            "Most people fail at {topic} because they do X. "
            "Here's what actually works: Y. "
            "I'll walk you through the exact system in my new guide — it's free for the next 48 hours."
        ),
    },
    {
        "id": "cold_ai_pitch_01",
        "source": "Generic AI-generated cold pitch (2024+ swipe)",
        "text": (
            "I hope this message finds you well. I came across your company and was impressed by your work in {industry}. "
            "I wanted to reach out because we specialize in helping companies like yours achieve better results with {solution}. "
            "Would you be interested in a brief conversation to explore if there's a fit?"
        ),
    },
]


# Regex + category pairs. Each is compiled lazily by the detector.
SWIPE_CLICHE_PATTERNS = [
    # ── Openers ─────────────────────────────────────────
    (r"(?i)hope\s+this\s+(?:email\s+|message\s+)?finds\s+you\s+well",
     "Opener: 'Hope this finds you well'"),
    (r"(?i)i\s+don'?t\s+usually\s+do\s+this,?\s+but",
     "Opener: 'I don't usually do this, but...'"),
    (r"(?i)quick\s+question\s+for\s+you",
     "Opener: 'Quick question for you'"),
    (r"(?i)i\s+hope\s+(?:this\s+)?message\s+finds\s+you",
     "Opener: Generic 'hope this message finds you'"),
    (r"(?i)i\s+came\s+across\s+your\s+(?:company|profile|website|work)",
     "Opener: 'I came across your company/profile'"),
    (r"(?i)i\s+(?:was|am)\s+impressed\s+by\s+your\s+work",
     "Opener: 'I was impressed by your work'"),
    (r"(?i)are\s+you\s+the\s+right\s+person\s+to\s+(?:talk|speak)\s+to",
     "Opener: 'Are you the right person to talk to'"),
    (r"(?i)dear\s+(?:friend|valued\s+customer|reader)",
     "Opener: Generic salutation ('Dear friend')"),

    # ── Follow-ups ──────────────────────────────────────
    (r"(?i)just\s+(?:bumping|bubbling)\s+this\s+(?:to\s+the\s+top|up)",
     "Follow-up: 'Just bumping this to the top'"),
    (r"(?i)just\s+following\s+up\s+on\s+my\s+(?:previous|last|earlier)\s+email",
     "Follow-up: 'Just following up on my last email'"),
    (r"(?i)in\s+case\s+(?:this|it)\s+got\s+(?:buried|lost)",
     "Follow-up: 'In case this got buried'"),
    (r"(?i)circling\s+back\s+on",
     "Follow-up: 'Circling back'"),
    (r"(?i)touching\s+base\s+(?:on|about|regarding)",
     "Follow-up: 'Touching base'"),

    # ── Breakup / re-engagement ─────────────────────────
    (r"(?i)are\s+you\s+still\s+interested\s+in",
     "Breakup: 'Are you still interested in...'"),
    (r"(?i)i'?ll\s+(?:assume|take\s+it)\s+(?:the\s+)?timing\s+isn'?t\s+right",
     "Breakup: 'I'll assume the timing isn't right'"),
    (r"(?i)i\s+don'?t\s+want\s+to\s+(?:keep\s+)?cluttering\s+your\s+inbox",
     "Breakup: 'Don't want to clutter your inbox'"),
    (r"(?i)close\s+the\s+loop\s+on\s+my\s+end",
     "Breakup: 'Close the loop on my end'"),

    # ── Urgency / scarcity clichés ──────────────────────
    (r"(?i)(?:this\s+is\s+it|last\s+chance).{0,30}(?:\d+\s+hours?\s+left|ends?\s+(?:tonight|today|at\s+midnight))",
     "Urgency: Classic flash-sale clock"),
    (r"(?i)once\s+it'?s\s+gone,?\s+it'?s\s+gone",
     "Urgency: 'Once it's gone, it's gone'"),
    (r"(?i)don'?t\s+miss\s+(?:out|your\s+chance)",
     "Urgency: 'Don't miss out'"),
    (r"(?i)seats?\s+are\s+(?:limited|filling\s+up)",
     "Urgency: 'Seats are limited'"),

    # ── Closers ─────────────────────────────────────────
    (r"(?i)p\.?s\.?\s*[—\-:]?\s*(?:one\s+more|just\s+one\s+more|almost\s+forgot|don'?t\s+forget)",
     "Closer: Classic PS 'one more thing' hook"),
    (r"(?i)just\s+reply\s+to\s+this\s+email\s+[—\-]\s+(?:a\s+real\s+human|we'?re\s+here|i\s+read\s+every)",
     "Closer: 'Just reply — a real human will respond'"),
    (r"(?i)hit\s+reply\s+and\s+tell\s+me\s+what\s+you'?re\s+working\s+on",
     "Closer: 'Hit reply and tell me what you're working on'"),
    (r"(?i)looking\s+forward\s+to\s+hearing\s+(?:back\s+)?from\s+you",
     "Closer: 'Looking forward to hearing from you'"),

    # ── CTA clichés ─────────────────────────────────────
    (r"(?i)would\s+you\s+be\s+(?:open|available)\s+(?:to|for)\s+a\s+(?:quick\s+)?(?:\d+\s+minute\s+)?(?:call|chat|conversation)",
     "CTA: 'Would you be open to a 15-minute call'"),
    (r"(?i)grab\s+your(?:s|\s+spot)\s+(?:before\s+they\s+fill|now)",
     "CTA: 'Grab yours before they fill up'"),
    (r"(?i)click\s+(?:the\s+)?(?:link\s+)?below\s+to\s+get\s+started",
     "CTA: 'Click below to get started'"),
    (r"(?i)what'?s\s+in\s+it\s+for\s+you",
     "CTA/Sub-header: 'What's in it for you'"),

    # ── Subject-line clichés (treated as body-level here too) ─
    (r"(?i)you\s+won'?t\s+believe\s+what",
     "Subject cliché: 'You won't believe what...'"),
    (r"(?i)the\s+secret\s+to\s+(?:\w+\s+){0,3}(?:success|wealth|happiness)",
     "Subject cliché: 'The secret to X'"),
    (r"(?i)(?:one|1)\s+weird\s+trick",
     "Subject cliché: 'One weird trick'"),

    # ── AI/ChatGPT-sounding filler ──────────────────────
    (r"(?i)it'?s\s+worth\s+(?:noting|mentioning)\s+that",
     "LLM filler: 'It's worth noting that'"),
    (r"(?i)in\s+today'?s\s+(?:fast[\s\-]paced|digital|modern)\s+world",
     "LLM filler: 'In today's fast-paced world'"),
    (r"(?i)at\s+the\s+end\s+of\s+the\s+day",
     "LLM filler: 'At the end of the day'"),
    (r"(?i)delve\s+(?:into|deeper)",
     "LLM filler: 'Delve into'"),
    (r"(?i)in\s+the\s+ever[\s\-]evolving\s+(?:landscape|world|field)\s+of",
     "LLM filler: 'In the ever-evolving landscape'"),

    # ── Generic credibility clichés ─────────────────────
    (r"(?i)we'?ve\s+helped\s+(?:dozens|hundreds|thousands)\s+of\s+(?:teams|companies|customers)",
     "Credibility cliché: 'We've helped dozens/hundreds/thousands'"),
    (r"(?i)companies\s+(?:like|such\s+as)\s+yours",
     "Credibility cliché: 'Companies like yours'"),
    (r"(?i)(?:industry[\s\-]leading|best[\s\-]in[\s\-]class|world[\s\-]class)\s+(?:solution|platform|service)",
     "Credibility cliché: 'Industry-leading / best-in-class'"),

    # ── Review / transactional ──────────────────────────
    (r"(?i)it\s+only\s+takes\s+(?:\d+|a\s+few)\s+seconds?",
     "Cliché: 'It only takes X seconds'"),
    (r"(?i)you\s+left\s+something\s+in\s+your\s+cart",
     "Cart abandon: 'You left something in your cart'"),
]
