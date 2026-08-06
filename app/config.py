"""Configuration: section aliases, thresholds, regex patterns."""

import re

COLLEGE_EMAIL_DOMAIN = "sst.scaler.com"
COLLEGE_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._+-]+@sst\.scaler\.com", re.IGNORECASE
)
ROLL_NUMBER_PATTERN = re.compile(r"\d{2}bcs\d{5}", re.IGNORECASE)
# Filename stems (after stripping optional " - Display Name" suffix)
FILENAME_PATTERN_BCS_SST = re.compile(
    r"^(.+)_(\d{2}bcs\d{5})_SST$", re.IGNORECASE
)
FILENAME_PATTERN_NUMERIC_SST = re.compile(
    r"^(.+)_(\d+)_SST$", re.IGNORECASE
)
FILENAME_PATTERN_BCS_ROLL = re.compile(
    r"^(.+)_(\d{2}bcs\d{5})$", re.IGNORECASE
)
# Legacy full-filename patterns (kept for reference)
FILENAME_PATTERN = re.compile(
    r"^(.+)_(\d{2}bcs\d{5})_SST\.pdf$", re.IGNORECASE
)
FILENAME_PATTERN_ROLL = re.compile(
    r"^(.+)_(\d{2}bcs\d{5})\.pdf$", re.IGNORECASE
)
PHONE_PATTERN = re.compile(
    r"(?:\+91[\s.-]*)?(?<!\d)[6-9](?:[\s.-]*\d){9}(?!\d)"
)
MAX_FILE_BYTES = 10 * 1024 * 1024
MIN_EXTRACTABLE_CHARS = 200
NAME_FUZZY_THRESHOLD = 85
SECTION_FONT_MULTIPLIER = 1.15

SECTION_ALIASES: dict[str, list[str]] = {
    "education": ["education"],
    "skills": ["skills", "technical skills"],
    "projects": ["projects"],
    "experience": ["experience"],
    "leadership": ["leadership", "leadership & volunteering", "volunteering"],
    "position_of_responsibility": [
        "position of responsibility",
        "positions of responsibility",
    ],
    "achievements": ["achievements"],
}

# Typographic arrows allowed; Unicode emoji blocks blocked in R203
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "]"
)

PLACEHOLDER_URL_PATTERNS = [
    re.compile(r"REPLACE-WITH", re.IGNORECASE),
    re.compile(r"example\.com", re.IGNORECASE),
    re.compile(r"your-github", re.IGNORECASE),
]

BOT_BLOCK_DOMAINS = frozenset(
    {
        "linkedin.com",
        "www.linkedin.com",
        "leetcode.com",
        "www.leetcode.com",
        "github.com",
        "www.github.com",
        "tracxn.com",
        "www.tracxn.com",
    }
)

UTM_PATTERN = re.compile(r"[?&]utm_", re.IGNORECASE)

CGR_PATTERN = re.compile(
    r"(?:current\s+)?cgr(?:\s*\(equivalent\s+to\s+cgpa\))?[\s:.-]*(\d+\.?\d*)",
    re.IGNORECASE,
)
CGPA_PATTERN = re.compile(
    r"(?:current\s+)?cgpa[\s:.-]*(\d+\.?\d*)",
    re.IGNORECASE,
)

LINK_TIMEOUT_SEC = 8.0
LINK_MAX_RETRIES = 1
LINK_PER_DOMAIN_CONCURRENCY = 3
