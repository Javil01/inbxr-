# Power words and copy quality signals for marketing effectiveness scoring

# Action-oriented CTA verbs (high-converting)
STRONG_CTA_VERBS = [
    "get", "start", "claim", "grab", "discover", "unlock", "access",
    "join", "try", "explore", "see", "watch", "read", "learn",
    "download", "sign up", "reserve", "save", "build", "create",
    "transform", "boost", "improve", "master", "launch",
]

# Weak CTA verbs (generic, low-converting)
WEAK_CTA_VERBS = [
    "submit", "click", "send", "go", "continue", "proceed",
    "enter", "press", "push", "hit", "select",
]

# Emotional power words for subject lines and copy
EMOTIONAL_POWER_WORDS = [
    # Curiosity
    "secret", "discover", "revealed", "unknown", "hidden", "surprising",
    "unexpected", "shocking", "little-known", "what nobody tells you",
    "the truth about", "why", "how", "what",
    # Desire
    "amazing", "incredible", "powerful", "game-changing", "breakthrough",
    "revolutionary", "extraordinary", "exceptional", "remarkable",
    # Achievement
    "proven", "results", "success", "achieve", "accomplish",
    "transform", "change", "improve", "boost", "skyrocket",
    # Fear / Problem-aware
    "avoid", "stop", "prevent", "protect", "save", "escape",
    "fix", "solve", "eliminate", "overcome",
    # Trust
    "guaranteed", "proven", "tested", "verified", "trusted",
    "expert", "professional", "certified", "award-winning",
    # Specificity
    "exactly", "precise", "specific", "step-by-step", "blueprint",
    "formula", "system", "framework", "strategy", "roadmap",
]

# Words that indicate benefit framing (positive for copy score)
BENEFIT_WORDS = [
    "save", "gain", "grow", "increase", "boost", "improve",
    "reduce", "eliminate", "simplify", "automate", "accelerate",
    "get more", "stop worrying", "never again", "in minutes",
    "without", "so you can", "which means", "results",
]

# Words that indicate feature framing (weaker for copy score)
FEATURE_WORDS = [
    "features", "includes", "comes with", "built-in", "compatible",
    "integrates", "supports", "provides", "offers",
    "our product", "our service", "our platform", "our solution",
    "we built", "we created", "we designed", "we developed",
]

# Social proof indicators
SOCIAL_PROOF_PATTERNS = [
    r"(?i)(\d[\d,]+\+?\s*(customers?|users?|clients?|members?|people|subscribers?))",
    r"(?i)((over|more than)\s+\d[\d,]*\s*(people|users?|customers?|businesses?))",
    r"(?i)(#\d+\s+(rated|ranked|reviewed))",
    r"(?i)(rated\s+[\d.]+\s*(out of\s+)?5\s*(stars?)?)",
    r"(?i)(\d+%\s+(of\s+)?(customers?|users?|people|businesses?))",
    r"(?i)(as seen in|featured in|mentioned in|covered by)",
    r"(?i)(testimonial|review|case study|success story)",
    r"(?i)(trusted by|used by|loved by|chosen by)",
    r"(?i)(award.?winning|best.?selling|top.?rated|#1)",
    r"(?i)(verified review|verified buyer|verified customer)",
]

# Risk reversal indicators
RISK_REVERSAL_PATTERNS = [
    r"(?i)(\d+.?day\s+(money.?back|refund|guarantee|trial))",
    r"(?i)(money.?back\s+guarantee)",
    r"(?i)(no\s+(risk|commitment|contract|obligation|cost|credit card))",
    r"(?i)(cancel\s+(anytime|any time|at any time|whenever))",
    r"(?i)(free\s+trial|try\s+(it\s+)?free|start\s+free)",
    r"(?i)(if you('?re| are) not (satisfied|happy|thrilled))",
    r"(?i)(100%\s+(satisfaction|refund)\s+guarantee)",
    r"(?i)(risk.?free)",
    r"(?i)(no questions asked)",
]

# Pattern interruption phrases (good for opening hooks)
PATTERN_INTERRUPT_PHRASES = [
    r"(?i)(here('?s| is) (the|a) (truth|thing|secret|problem|reality|catch))",
    r"(?i)(let me (be honest|ask you something|show you|tell you))",
    r"(?i)(what if (you|i told you|there was))",
    r"(?i)(imagine (if|being|having|getting))",
    r"(?i)(stop (doing|trying|struggling|wasting))",
    r"(?i)(most (people|businesses|marketers|founders) (don'?t|never|fail to))",
    r"(?i)(the (#1|biggest|most common|only) (reason|mistake|thing))",
    r"(?i)(it'?s not (about|what you think))",
    r"(?i)(forget everything you (know|thought|heard) about)",
    r"(?i)(i (used to|was once|remember when))",
]

# Pain-aware copy phrases
PAIN_AWARE_PHRASES = [
    r"(?i)(struggle?ing with|frustrated (with|by|about)|tired of|sick of)",
    r"(?i)(spending (too much|hours|days|weeks) (on|trying))",
    r"(?i)(wasted? (time|money|effort|resources))",
    r"(?i)(can'?t (figure out|understand|afford|keep up))",
    r"(?i)((no|without) (results|progress|success|growth))",
    r"(?i)(overwhelming|complicated|confusing|difficult|hard)",
    r"(?i)(missing out on|leaving money on|losing (customers|clients|sales))",
    r"(?i)(the problem (is|with)|your biggest (challenge|problem|obstacle))",
]

# Solution/outcome copy phrases
SOLUTION_PHRASES = [
    r"(?i)((now you can|you'?ll (finally|now|be able to)))",
    r"(?i)(here'?s (how|what|why))",
    r"(?i)(in just \d+ (minutes?|hours?|days?|steps?))",
    r"(?i)(without (spending|needing|having to))",
    r"(?i)(so (you|your business) can (finally|now|easily))",
    r"(?i)(the (solution|answer|fix|way) (is|to))",
    r"(?i)(works? (even if|for|with|without))",
]

# Industries for benchmark context
INDUSTRY_BENCHMARKS = {
    "SaaS": {"avg_open_rate": 21.5, "spam_threshold": 35},
    "Ecommerce": {"avg_open_rate": 15.7, "spam_threshold": 40},
    "Info Products": {"avg_open_rate": 27.8, "spam_threshold": 45},
    "Local Services": {"avg_open_rate": 16.2, "spam_threshold": 30},
    "Finance": {"avg_open_rate": 22.9, "spam_threshold": 25},
    "Health": {"avg_open_rate": 18.4, "spam_threshold": 35},
    "Political": {"avg_open_rate": 24.3, "spam_threshold": 50},
    "Other": {"avg_open_rate": 20.0, "spam_threshold": 35},
}
