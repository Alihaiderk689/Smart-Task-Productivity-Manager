import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import { Loader2, CheckCircle2, ShieldCheck } from "lucide-react";
import AuthLayout from "@/components/authlayout";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage, resendVerificationEmailRequest, verifyEmailOtpRequest } from "@/services/api";

// Mirrors the backend's users/otp.py limits so the button's cooldown/lockout
// matches what the server will actually allow -- the server is still the
// real source of truth (this is just so the UI doesn't say "sent" when the
// backend silently no-op'd a blocked resend).
const RESEND_COOLDOWN_SECONDS = 60;
const LOCKOUT_SECONDS = 30 * 60;
const MAX_SENDS_PER_CYCLE = 2;

function resendStorageKey(email) {
  return `smart-task-otp-resend:${email.trim().toLowerCase()}`;
}

function readResendState(email) {
  if (!email) return null;
  try {
    const raw = localStorage.getItem(resendStorageKey(email));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed.count !== "number" || typeof parsed.lastSentAt !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeResendState(email, state) {
  if (!email) return;
  localStorage.setItem(resendStorageKey(email), JSON.stringify(state));
}

// The send cycle resets once the lockout window has fully elapsed since the
// last send -- same rule as users/otp.py's issue_otp().
function effectiveResendState(email) {
  const stored = readResendState(email);
  if (!stored) return { count: 0, lastSentAt: 0 };
  if (Date.now() - stored.lastSentAt >= LOCKOUT_SECONDS * 1000) return { count: 0, lastSentAt: 0 };
  return stored;
}

function computeCooldown(state) {
  const elapsedSeconds = (Date.now() - state.lastSentAt) / 1000;
  if (state.count >= MAX_SENDS_PER_CYCLE) {
    return { seconds: Math.max(0, Math.ceil(LOCKOUT_SECONDS - elapsedSeconds)), locked: true };
  }
  return { seconds: Math.max(0, Math.ceil(RESEND_COOLDOWN_SECONDS - elapsedSeconds)), locked: false };
}

function formatCooldown(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function VerifyEmail() {
  const navigate = useNavigate();
  const { applySession } = useAuth();
  const [searchParams] = useSearchParams();
  const emailFromQuery = searchParams.get("email") || "";
  // Only set by register.jsx right after signup already sent the first code
  // -- avoids starting the cooldown when arriving here from the login page's
  // "Enter verification code" link, where no fresh code has just gone out.
  const justSent = searchParams.get("sent") === "1";

  const [email, setEmail] = useState(emailFromQuery);
  const [otp, setOtp] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  // seconds + locked travel together as one value on purpose: they used to
  // be separate state vars cleared by separate effects, which raced on
  // mount (the "clear lock once cooldown hits 0" effect saw cooldown's
  // *initial* value of 0 and cleared the lock the instant the other effect
  // had just set it) -- reloading while locked would silently unlock the
  // button. Single state = one writer, no race.
  const [resend, setResend] = useState({ seconds: 0, locked: false });
  const [resending, setResending] = useState(false);

  // Runs once: if we landed here right after signup, that request already
  // sent code #1 -- record it so the button's cooldown reflects it. Guarded
  // on "no stored state yet" so reloading this page (sent=1 stays in the
  // URL) doesn't re-count the same send on every refresh.
  useEffect(() => {
    if (justSent && emailFromQuery && !readResendState(emailFromQuery)) {
      writeResendState(emailFromQuery, { count: 1, lastSentAt: Date.now() });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recompute the button's cooldown/lock whenever the target email changes.
  useEffect(() => {
    if (!email) {
      setResend({ seconds: 0, locked: false });
      return;
    }
    setResend(computeCooldown(effectiveResendState(email)));
  }, [email]);

  useEffect(() => {
    if (resend.seconds <= 0) return undefined;
    const timer = setInterval(() => {
      setResend((prev) => (prev.seconds <= 1 ? { seconds: 0, locked: false } : { ...prev, seconds: prev.seconds - 1 }));
    }, 1000);
    return () => clearInterval(timer);
  }, [resend.seconds]);

  const submitOtp = useCallback(async (code) => {
    if (!email || code.length !== 6) return;
    setVerifying(true);
    setError("");
    try {
      const data = await verifyEmailOtpRequest({ email, otp: code });
      applySession(data);
      setSuccess(true);
      setTimeout(() => navigate("/", { replace: true }), 1200);
    } catch (err) {
      setError(getErrorMessage(err, "Incorrect or expired code."));
      setOtp("");
    } finally {
      setVerifying(false);
    }
  }, [email, applySession, navigate]);

  const handleResend = async (e) => {
    e?.preventDefault();
    if (!email || resend.seconds > 0) return;
    setResending(true);
    setError("");
    try {
      await resendVerificationEmailRequest(email);
      const effective = effectiveResendState(email);
      const newState = { count: effective.count + 1, lastSentAt: Date.now() };
      writeResendState(email, newState);
      setResend(computeCooldown(newState));
    } catch (err) {
      setError(getErrorMessage(err, "Failed to resend code."));
    } finally {
      setResending(false);
    }
  };

  if (success) {
    return (
      <AuthLayout icon={CheckCircle2} title="Email verified" subtitle="Your account is now active">
        <p className="text-sm text-foreground text-center">
          You're logged in. Redirecting you to your dashboard...
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      icon={ShieldCheck}
      title="Verify your email"
      subtitle={email ? `Enter the code we sent to ${email}` : "Enter your email and the code we sent you"}
      footer={
        <Link to="/login" className="text-primary font-medium hover:underline">
          Back to log in
        </Link>
      }
    >
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm text-center">
          {error}
        </div>
      )}

      <div className="space-y-2 mb-4">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => { setEmail(e.target.value); setOtp(""); }}
          className="h-12"
          required
        />
      </div>

      <div className="flex justify-center my-6">
        <InputOTP
          maxLength={6}
          value={otp}
          onChange={setOtp}
          onComplete={submitOtp}
          disabled={verifying || !email}
        >
          <InputOTPGroup>
            <InputOTPSlot index={0} />
            <InputOTPSlot index={1} />
            <InputOTPSlot index={2} />
            <InputOTPSlot index={3} />
            <InputOTPSlot index={4} />
            <InputOTPSlot index={5} />
          </InputOTPGroup>
        </InputOTP>
      </div>

      <Button
        type="button"
        className="w-full h-12 font-medium"
        disabled={verifying || otp.length !== 6 || !email}
        onClick={() => submitOtp(otp)}
      >
        {verifying ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Verifying...
          </>
        ) : (
          "Verify email"
        )}
      </Button>

      {resend.locked ? (
        <p className="text-center mt-4 text-sm text-muted-foreground">
          You've requested a code twice already. Try again in {formatCooldown(resend.seconds)}.
        </p>
      ) : (
        <div className="text-center mt-4 text-sm text-muted-foreground">
          Didn't get a code?{" "}
          <button
            type="button"
            onClick={handleResend}
            disabled={!email || resending || resend.seconds > 0}
            className="font-medium text-primary underline hover:no-underline disabled:opacity-60 disabled:no-underline disabled:cursor-not-allowed"
          >
            {resending ? "Sending..." : resend.seconds > 0 ? `Resend in ${formatCooldown(resend.seconds)}` : "Resend code"}
          </button>
        </div>
      )}
    </AuthLayout>
  );
}
