# Curated spam trigger word/phrase database organized by category

SPAM_TRIGGER_WORDS = [
    # Urgency & Scarcity
    "act now", "act immediately", "apply now", "before it's too late",
    "call now", "don't delay", "don't hesitate", "do it today", "don't miss",
    "don't wait", "ends tonight", "expires", "final", "hurry", "immediate",
    "instant", "last chance", "limited time", "limited offer", "now or never",
    "offer expires", "once in a lifetime", "only", "please read", "reply asap",
    "respond now", "serious cash", "take action now", "time sensitive",
    "time is running out", "today only", "urgent", "while supplies last",
    "while stocks last", "your response required",

    # Money & Financial
    "100% free", "additional income", "all natural", "auto email removal",
    "avoid bankruptcy", "bargain", "billion", "billion dollars", "biz opportunity",
    "bulk email", "buy direct", "buying judgments", "cable converter",
    "call free", "calling creditors", "cancel at any time", "cannot be combined",
    "cash bonus", "cash back", "check or money order", "claims", "collect",
    "compare rates", "compete for your business", "confidentiality on all orders",
    "consolidate debt", "consolidate your debt", "copy accurately", "costs nothing",
    "credit card offers", "debt", "dig up dirt on friends", "direct email",
    "direct marketing", "discount", "double your", "earn cash", "earn easy money",
    "earn extra cash", "earn per week", "easy money", "eliminate debt",
    "extra cash", "extra income", "extra money", "fast cash", "financial freedom",
    "for free", "for just", "free access", "free gift", "free grant money",
    "free hosting", "free info", "free investment", "free leads",
    "free money", "free membership", "free offer", "free preview",
    "free quote", "free sample", "free trial", "free website",
    "full refund", "get paid", "giveaway", "great offer", "guaranteed",
    "home based business", "home employment", "huge discount", "income from home",
    "increase sales", "increase traffic", "instant earnings", "internet marketing",
    "investment decision", "jackpot", "join millions", "leads", "loan",
    "lower rates", "lower your mortgage rate", "lowest price", "luxury car",
    "make $", "make money", "meet singles", "member", "million", "million dollars",
    "money back", "money making", "mortgage rates", "multi level marketing",
    "multilevel marketing", "name brand", "new customers only", "no catch",
    "no cost", "no credit check", "no disappointment", "no experience",
    "no fees", "no gimmick", "no hidden costs", "no hidden fees",
    "no interest", "no investment", "no middleman", "no obligation",
    "no payment", "no purchase necessary", "no questions asked",
    "no strings attached", "not junk", "not spam", "obligation free",
    "offers a free", "one hundred percent", "one time only", "online biz opportunity",
    "online degree", "only $", "opportunity", "order today", "pennies a day",
    "potential earnings", "prize", "profits", "promise", "pure profit",
    "real thing", "refinance", "refund", "remove in accordance",
    "reversal", "risk free", "save $", "save big money", "save up to",
    "serious cash", "subject to credit", "the best rates", "thousands",
    "trial", "unbeatable offer", "unlimited", "unsecured credit",
    "us dollars", "vacation", "valium", "value", "viagra", "vicodin",
    "we hate spam", "weekend getaway", "win", "winner", "winnings",
    "won", "work at home", "work from home", "xanax", "you are a winner",
    "you have been selected", "your income",

    # Deceptive / Misleading
    "as seen on", "become a member", "being a member",
    "bulk", "buying judgments", "certified", "chance", "click here",
    "collect child support", "compare", "congratulations",
    "cures baldness", "dear email", "dear friend", "dear somebody",
    "dear valued customer", "detailed information", "diagnosed",
    "direct email", "disclaimer", "double your income",
    "earn money online", "f r e e", "famous", "for instant access",
    "form letter", "free consultation", "free online", "freedom",
    "from the desk of", "get it now", "get started now",
    "gift certificate", "gives you the chance", "great",
    "hello", "hidden assets", "hidden charges", "hidden costs",
    "if only it were that easy", "important information",
    "in accordance with laws", "incredible deal", "info you requested",
    "information you requested", "internet market", "investment",
    "its effective", "join millions of americans", "knowledge",
    "legal", "lowest price", "luxury", "mail in order form",
    "mass email", "message contains", "message from",
    "mlm", "money", "month trial offer", "more internet traffic",
    "mortgage", "must", "name brand", "new", "new domain extensions",
    "no age restrictions", "no catch", "no claim forms",
    "no gimmicks", "no hidden costs", "no hidden fees",
    "no strings", "notable", "now", "obligation",
    "offer", "one hundred percent guaranteed", "online marketing",
    "open rate", "opportunity", "opt in", "order now",
    "order status", "outstanding values", "owned", "per week",
    "promise you", "purchase", "pure profit", "real thing",
    "removal instructions", "remove", "request", "reversal of",
    "risk", "round figures", "satisfaction guaranteed",
    "searches", "see for yourself", "sell", "send",
    "serious offer", "shopping spree", "sign up free",
    "special offer", "special promotion", "strong buy",
    "subscribe", "the following form", "this is not junk",
    "this is not spam", "thousands", "to be removed",
    "toll free", "trial offer", "undisclosed recipient",
    "unsolicited", "unsubscribe", "urgent", "valuable",
    "web traffic", "who really wins", "will not believe",
    "winner", "winning", "won", "you are a winner",

    # Manipulative / Psychological pressure
    "don't delete", "don't ignore", "if you don't", "important notice",
    "limited spots", "missing out", "only a few left", "read this",
    "reply urgently", "running out", "seats limited", "slots available",
    "warning", "you must", "your account may", "your account will",
    "your privacy", "you've been pre-approved", "you've been selected",
]

# High-impact standalone trigger words (weighted more heavily)
HIGH_RISK_WORDS = [
    "free", "guaranteed", "winner", "won", "prize", "casino",
    "lottery", "loan", "debt", "mortgage", "refinance",
    "prescription", "medication", "pills", "weight loss",
    "investment", "million", "billion", "rich", "wealth",
    "inheritance", "wire transfer", "western union", "moneygram",
    "urgent", "confidential", "secret", "exclusive", "limited",
    "viagra", "pharmacy", "penis", "enlargement", "herbal",
    "mlm", "multi-level", "pyramid", "income opportunity",
    "make money fast", "earn from home", "work from home",
    "miracle", "cure", "cure baldness", "lose weight",
    "100%", "click here", "buy now",
]

# URL shortener domains (spam indicator)
URL_SHORTENERS = [
    "bit.ly", "tinyurl.com", "t.co", "ow.ly", "is.gd", "buff.ly",
    "adf.ly", "short.to", "tiny.cc", "snip.ly", "rebrand.ly",
    "clk.sh", "cutt.ly", "yourls.org", "bl.ink", "short.io",
    "bc.vc", "mcaf.ee", "qr.ae", "url.ie", "x.co",
]

# Suspicious TLDs
SUSPICIOUS_TLDS = [
    ".xyz", ".click", ".download", ".link", ".win", ".loan",
    ".bid", ".trade", ".stream", ".online", ".site", ".club",
    ".info", ".biz", ".tk", ".ml", ".ga", ".cf", ".gq",
]

# CTA phrases that signal spam
HIGH_RISK_CTA_PHRASES = [
    "click here", "click now", "click below", "click to claim",
    "click to win", "claim your prize", "claim now", "order now",
    "buy now", "purchase now", "subscribe now",
    "give away", "free gift", "free money", "your free",
    "call us now", "call now", "contact us now",
    "to be removed", "to unsubscribe", "remove me",
]

# Deceptive subject line patterns
DECEPTIVE_SUBJECT_PATTERNS = [
    r"(?i)re:\s*re:",          # Fake reply chains
    r"(?i)^re:\s+(?!re:)",     # Fake reply
    r"(?i)^fwd?:\s+(?!fwd?:)", # Fake forward
    r"(?i)you('ve| have) (won|been selected|been chosen)",
    r"(?i)(congratulations|congrats)[,!]",
    r"(?i)your (account|email|inbox) (is|has been|will be)",
    r"(?i)(unclaimed|outstanding|pending) (prize|reward|payment|funds)",
    r"(?i)(bank|wire) transfer",
    r"(?i)atm card",
    r"(?i)nigerian? (prince|king|general)",
    r"(?i)bitcoin (investment|trading|profit)",
]

# Urgency manipulation patterns in body
URGENCY_MANIPULATION_PATTERNS = [
    r"(?i)(you (must|need to) (act|respond|reply|click) (now|immediately|today|asap))",
    r"(?i)(don'?t (miss|ignore|delete) this)",
    r"(?i)(this (offer|deal|price|discount) (expires?|ends?|disappears?))",
    r"(?i)(only \d+ (spots?|seats?|openings?|left|remaining))",
    r"(?i)(counter|countdown|clock) (is (ticking|running))",
    r"(?i)(never (see|get|find) (this|another) (offer|deal|chance) again)",
    r"(?i)(now or never)",
    r"(?i)(your (last|final) (chance|opportunity|warning))",
    r"(?i)(you'?ll (regret|miss out|lose out) if you don'?t)",
    r"(?i)(time('?s | is | )(running out|almost up|nearly up))",
]

# Compliance keywords to detect
UNSUBSCRIBE_PATTERNS = [
    r"(?i)(unsubscribe|opt.?out|opt out|remove me|no longer receive)",
    r"(?i)(click here to (unsubscribe|remove|opt out))",
    r"(?i)(manage (your |)(preferences|subscriptions))",
    r"(?i)(stop receiving|stop emails|stop messages)",
]

ADDRESS_PATTERNS = [
    r"\b\d{1,5}\s+\w+\s+(street|st|avenue|ave|road|rd|drive|dr|lane|ln|blvd|boulevard|way|place|pl|court|ct)\b",
    r"\b(po box|p\.?o\.? box)\s+\d+\b",
    r"\bsuite\s+\d+\b",
    r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b",  # US ZIP
]
