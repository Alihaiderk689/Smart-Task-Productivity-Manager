// Mirrors backend/tasks/serializers.py's rules. Keep the two in sync; the
// backend is always the real enforcement point, this is just for real-time
// UX (word counters, disabling submit, past-date calendar restrictions).

export const TITLE_MAX_WORDS = 20;
export const TITLE_MAX_CHARS = 200; // Task.title is a CharField(max_length=200) -- a hard DB-level cap independent of the word count above.
export const DESCRIPTION_MAX_WORDS = 200;

const GIBBERISH_MESSAGE = "This doesn't look like real text -- please rewrite it in plain words.";

function wordCount(value) {
  const trimmed = (value || "").trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

// Mirrors backend/tasks/validators.py's heuristic -- see that file for the
// full rationale (short version: in real English, almost every letter-pair
// either touches a vowel or is a recognized consonant cluster; keyboard-
// mashing produces a much higher share of pairs that are neither). Keep
// the cluster set and thresholds identical to the backend copy, which is
// the one that actually enforces this -- this one is just so the error
// shows up before the round trip to the server.
const VOWELS = new Set("aeiouy");
const CONSONANT_CLUSTERS = new Set(
  ("bl br ch ck cl cr dg dr dw fl fr gh gl gn gr kn kh ph pl pr qu " +
    "sc sch scr shr sk sl sm sn sp spl spr squ st str sw th thr tr tw " +
    "wh wr ng nk nt nd nc ns mp mb mn lt ld lf lk lm ln lp ls lv lc lg " +
    "rd rk rl rm rn rp rt rc rg rb rs rv ct pt ft gt xt " +
    "ss ll ff mm nn pp tt zz dd gg bb cc rr ts ds ps cs vs ks"
  ).split(" ")
);

const MIN_JUDGEABLE_WORDS = 2;
const MIN_BIGRAMS = 6;
const IMPLAUSIBLE_RATIO_THRESHOLD = 0.22;

function isPlausibleBigram(bigram) {
  const [a, b] = bigram;
  if (a === b) return true; // doubled letters (ll, ss, ...) are always fine
  if (VOWELS.has(a) || VOWELS.has(b)) return true; // any pair touching a vowel is fine
  return CONSONANT_CLUSTERS.has(bigram);
}

// True if `value` is dominated by letter-pairs that don't look like
// plausible English. Only words of 5+ letters count towards the ratio
// (short words/acronyms are too ambiguous to judge), and fields with too
// little judgeable text always return false rather than guessing off a
// thin sample.
function looksLikeGibberish(value) {
  const words = (value || "")
    .split(/\s+/)
    .map((w) => w.replace(/[^a-zA-Z]/g, ""))
    .filter((w) => w.length >= 5);
  if (words.length < MIN_JUDGEABLE_WORDS) return false;

  let total = 0;
  let implausible = 0;
  for (const word of words) {
    const letters = word.toLowerCase();
    for (let i = 0; i < letters.length - 1; i++) {
      total += 1;
      if (!isPlausibleBigram(letters.slice(i, i + 2))) implausible += 1;
    }
  }
  if (total < MIN_BIGRAMS) return false;
  return implausible / total >= IMPLAUSIBLE_RATIO_THRESHOLD;
}

export function validateTaskTitle(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "Task name is required.";
  if (wordCount(trimmed) > TITLE_MAX_WORDS) return `Task name cannot exceed ${TITLE_MAX_WORDS} words.`;
  if (trimmed.length > TITLE_MAX_CHARS) return `Task name cannot exceed ${TITLE_MAX_CHARS} characters.`;
  if (looksLikeGibberish(trimmed)) return GIBBERISH_MESSAGE;
  return "";
}

export function validateTaskDescription(value) {
  const trimmed = (value || "").trim();
  if (trimmed && wordCount(trimmed) > DESCRIPTION_MAX_WORDS) return `Description cannot exceed ${DESCRIPTION_MAX_WORDS} words.`;
  if (trimmed && looksLikeGibberish(trimmed)) return GIBBERISH_MESSAGE;
  return "";
}

export function validateCategorySelected(value) {
  return value ? "" : "Please select a category.";
}

export function validatePrioritySelected(value) {
  return value ? "" : "Please select a priority.";
}

export function validateStartTimeNotPast(localDatetimeValue) {
  if (!localDatetimeValue) return "Start time is required.";
  const start = new Date(localDatetimeValue);
  if (start <= new Date()) return "Start time cannot be in the past.";
  return "";
}

export function validateEndAfterStart(startLocalDatetimeValue, endLocalDatetimeValue) {
  if (!endLocalDatetimeValue) return "Due time is required.";
  if (!startLocalDatetimeValue) return "";
  const start = new Date(startLocalDatetimeValue);
  const end = new Date(endLocalDatetimeValue);
  if (end <= start) return "Due time must be after the start time.";
  return "";
}

// Mirrors backend/tasks/views.py::create_repeating_tasks's REPEAT_MIN_DAYS/
// REPEAT_MAX_DAYS -- keep in sync.
export const REPEAT_MIN_DAYS = 2;
export const REPEAT_MAX_DAYS = 30;

export function validateRepeatDays(enabled, value) {
  if (!enabled) return "";
  const trimmed = String(value ?? "").trim();
  if (!trimmed) return "Enter how many days to repeat for.";
  const n = Number(trimmed);
  if (!Number.isInteger(n)) return "Enter a whole number of days.";
  if (n < REPEAT_MIN_DAYS || n > REPEAT_MAX_DAYS) return `Repeat for between ${REPEAT_MIN_DAYS} and ${REPEAT_MAX_DAYS} days.`;
  return "";
}

export { wordCount };
