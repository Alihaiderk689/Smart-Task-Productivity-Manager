import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Lock, Loader2, Clock } from "lucide-react";
import AuthLayout from "@/components/authlayout";
import { useAuth } from "@/context/AuthContext";
import { confirmPasswordReset, getErrorMessage } from "@/services/api";

// Must match the backend's PASSWORD_RESET_TIMEOUT (config/settings.py) so the
// link visibly expires here at the same moment the server stops accepting it.
const LINK_LIFETIME_SECONDS = 120;

function formatCountdown(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function ResetPassword() {
  const navigate = useNavigate();
  const { applySession } = useAuth();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid");
  const resetToken = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(LINK_LIFETIME_SECONDS);

  useEffect(() => {
    if (!uid || !resetToken || done || secondsLeft <= 0) {
      return undefined;
    }

    const interval = setInterval(() => {
      setSecondsLeft((prev) => Math.max(prev - 1, 0));
    }, 1000);

    return () => clearInterval(interval);
  }, [uid, resetToken, done, secondsLeft]);

  const expired = secondsLeft <= 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const data = await confirmPasswordReset({ uid, token: resetToken, newPassword });
      applySession(data);
      setDone(true);
      setTimeout(() => navigate("/", { replace: true }), 2000);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to reset password"));
    } finally {
      setLoading(false);
    }
  };

  if (!uid || !resetToken) {
    return (
      <AuthLayout
        title="Invalid reset link"
        subtitle="This password reset link is missing or invalid"
        footer={
          <Link to="/forgot-password" className="text-primary font-medium hover:underline">
            Request a new link
          </Link>
        }
      >
        <p className="text-sm text-foreground text-center">
          This link is missing required information. Request a new password reset link.
        </p>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout title="Password reset" subtitle="Your password has been updated">
        <p className="text-sm text-foreground text-center">
          You're logged in. Redirecting you to your dashboard...
        </p>
      </AuthLayout>
    );
  }

  if (expired) {
    return (
      <AuthLayout
        title="Link expired"
        subtitle="This password reset link is only valid for 2 minutes"
        footer={
          <Link to="/forgot-password" className="text-primary font-medium hover:underline">
            Request a new link
          </Link>
        }
      >
        <p className="text-sm text-foreground text-center">
          This reset link has expired. Request a new one to continue.
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="New password"
      subtitle="Enter your new password below"
    >
      <div className="mb-4 flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <Clock className="w-4 h-4" aria-hidden="true" />
        <span>
          Link expires in <span className="font-medium text-foreground">{formatCountdown(secondsLeft)}</span>
        </span>
      </div>
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">New Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              autoFocus
              placeholder="••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="pl-10 h-12"
              required
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">Confirm Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="pl-10 h-12"
              required
            />
          </div>
        </div>
        <Button type="submit" className="w-full h-12 font-medium" disabled={loading || expired}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Resetting...
            </>
          ) : (
            "Reset password"
          )}
        </Button>
      </form>
    </AuthLayout>
  );
}
