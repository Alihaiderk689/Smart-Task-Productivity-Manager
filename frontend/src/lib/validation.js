// Centralized signup/login field validation -- mirrors the backend's rules
// in backend/users/validators.py. Keep the two in sync; the backend is
// always the real enforcement point, this is just for real-time UX.

export const FULL_NAME_MIN_LENGTH = 2;
export const FULL_NAME_MAX_LENGTH = 50;
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;
export const EMAIL_MAX_LENGTH = 254;

const FULL_NAME_RE = /^[A-Za-z][A-Za-z '-]*$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateFullName(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "Full name is required.";
  if (trimmed.length < FULL_NAME_MIN_LENGTH) return `Full name must be at least ${FULL_NAME_MIN_LENGTH} characters.`;
  if (trimmed.length > FULL_NAME_MAX_LENGTH) return `Full name cannot exceed ${FULL_NAME_MAX_LENGTH} characters.`;
  if (!FULL_NAME_RE.test(trimmed)) return "Full name can only contain letters, spaces, hyphens, and apostrophes.";
  return "";
}

export function validateEmail(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "Email is required.";
  if (trimmed.length > EMAIL_MAX_LENGTH) return `Email cannot exceed ${EMAIL_MAX_LENGTH} characters.`;
  if (!EMAIL_RE.test(trimmed)) return "Please enter a valid email address.";
  return "";
}

// Rule labels used by both the strength meter and the error message --
// keeping them as one list avoids the two ever drifting apart.
export function getPasswordRuleFailures(value) {
  const failures = [];
  if (value.length < PASSWORD_MIN_LENGTH) failures.push(`at least ${PASSWORD_MIN_LENGTH} characters`);
  if (value.length > PASSWORD_MAX_LENGTH) failures.push(`no more than ${PASSWORD_MAX_LENGTH} characters`);
  if (/\s/.test(value)) failures.push("no spaces");
  if (!/[A-Z]/.test(value)) failures.push("an uppercase letter");
  if (!/[a-z]/.test(value)) failures.push("a lowercase letter");
  if (!/\d/.test(value)) failures.push("a number");
  if (!/[^A-Za-z0-9\s]/.test(value)) failures.push("a special character");
  return failures;
}

export function validatePassword(value, email) {
  if (!value) return "Password is required.";
  const failures = getPasswordRuleFailures(value);
  if (failures.length > 0) return `Password must have ${failures.join(", ")}.`;
  if (email && value.trim().toLowerCase() === email.trim().toLowerCase()) {
    return "Password cannot be the same as your email.";
  }
  return "";
}

export function validateConfirmPassword(password, confirmPassword) {
  if (!confirmPassword) return "Please confirm your password.";
  if (password !== confirmPassword) return "Passwords do not match.";
  return "";
}

// 0-4 score for the strength meter -- independent of validatePassword's
// pass/fail so partial credit shows up while the user is still typing.
export function getPasswordStrength(value) {
  if (!value) return 0;
  let score = 0;
  if (value.length >= PASSWORD_MIN_LENGTH) score += 1;
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1;
  if (/\d/.test(value)) score += 1;
  if (/[^A-Za-z0-9\s]/.test(value)) score += 1;
  if (value.length >= 12) score += 1;
  return Math.min(score, 4);
}

export const PASSWORD_STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Good", "Strong"];
