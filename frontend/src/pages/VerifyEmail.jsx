import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MailCheck, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import AuthLayout from "@/components/authlayout";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage, resendVerificationEmailRequest, verifyEmailRequest } from "@/services/api";

export default function VerifyEmail() {
  const navigate = useNavigate();
  const { applySession } = useAuth();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  const [status, setStatus] = useState(uid && token ? "verifying" : "missing");
  const [error, setError] = useState("");

  const [resendEmail, setResendEmail] = useState("");
  const [resendSent, setResendSent] = useState(false);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!uid || !token) return;

    let cancelled = false;

    verifyEmailRequest({ uid, token })
      .then((data) => {
        if (cancelled) return;
        applySession(data);
        setStatus("success");
        setTimeout(() => navigate("/", { replace: true }), 1500);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getErrorMessage(err, "This verification link is invalid or has expired."));
        setStatus("error");
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid, token]);

  const handleResend = async (e) => {
    e.preventDefault();
    setResending(true);
    try {
      await resendVerificationEmailRequest(resendEmail);
      setResendSent(true);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to resend verification email"));
    } finally {
      setResending(false);
    }
  };

  if (status === "missing") {
    return (
      <AuthLayout
        icon={AlertTriangle}
        title="Invalid verification link"
        subtitle="This link is missing required information"
        footer={
          <Link to="/login" className="text-primary font-medium hover:underline">
            Back to log in
          </Link>
        }
      >
        <p className="text-sm text-foreground text-center">
          Request a new verification email below.
        </p>
        <ResendForm
          email={resendEmail}
          setEmail={setResendEmail}
          onSubmit={handleResend}
          sending={resending}
          sent={resendSent}
        />
      </AuthLayout>
    );
  }

  if (status === "verifying") {
    return (
      <AuthLayout icon={Loader2} title="Verifying your email..." subtitle="Just a moment">
        <div className="flex justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
        </div>
      </AuthLayout>
    );
  }

  if (status === "success") {
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
      icon={AlertTriangle}
      title="Verification failed"
      subtitle={error}
      footer={
        <Link to="/login" className="text-primary font-medium hover:underline">
          Back to log in
        </Link>
      }
    >
      <p className="text-sm text-foreground text-center mb-4">
        Enter your email to get a new verification link.
      </p>
      <ResendForm
        email={resendEmail}
        setEmail={setResendEmail}
        onSubmit={handleResend}
        sending={resending}
        sent={resendSent}
      />
    </AuthLayout>
  );
}

function ResendForm({ email, setEmail, onSubmit, sending, sent }) {
  if (sent) {
    return (
      <div className="flex items-center gap-2 justify-center text-sm text-foreground">
        <MailCheck className="w-4 h-4" />
        Check your inbox for a new link.
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="resend_email">Email</Label>
        <Input
          id="resend_email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-12"
          required
        />
      </div>
      <Button type="submit" className="w-full h-12 font-medium" disabled={sending || !email}>
        {sending ? "Sending..." : "Resend verification email"}
      </Button>
    </form>
  );
}
