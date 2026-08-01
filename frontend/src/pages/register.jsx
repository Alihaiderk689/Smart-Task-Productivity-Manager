import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UserPlus, User, Mail, Lock, Loader2, Eye, EyeOff } from "lucide-react";
import AuthLayout from "@/components/authlayout";
import GoogleLoginButton from "@/components/GoogleLoginButton";
import { cn } from "@/lib/utils";
import {
  validateFullName,
  validateEmail,
  validatePassword,
  validateConfirmPassword,
  getPasswordStrength,
  PASSWORD_STRENGTH_LABELS,
} from "@/lib/validation";
import { getErrorMessage, getFieldErrors, signUpRequest } from "@/services/api";

const STRENGTH_BAR_COLORS = ["bg-destructive", "bg-destructive", "bg-amber-500", "bg-amber-500", "bg-emerald-500"];

function FieldError({ message }) {
  if (!message) return null;
  return <p className="text-xs text-destructive mt-1">{message}</p>;
}

export default function Register() {
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [touched, setTouched] = useState({});
  const [fieldErrors, setFieldErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);

  const clientErrors = {
    first_name: validateFullName(fullName),
    email: validateEmail(email),
    password: validatePassword(password, email),
    password_confirm: validateConfirmPassword(password, confirmPassword),
  };
  const isValid = Object.values(clientErrors).every((message) => !message);

  // Server-side errors (from a failed submit) win until the user edits that
  // field again, at which point the live client-side check takes back over.
  const errorFor = (field) => (touched[field] ? fieldErrors[field] || clientErrors[field] : "");

  const markTouched = (field) => setTouched((prev) => ({ ...prev, [field]: true }));
  const clearFieldError = (field) => setFieldErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));

  const strength = getPasswordStrength(password);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError("");
    setTouched({ first_name: true, email: true, password: true, password_confirm: true });

    if (!isValid) return;

    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      await signUpRequest({
        first_name: fullName.trim(),
        email: normalizedEmail,
        password,
        password_confirm: confirmPassword,
      });
      navigate(`/verify-email?email=${encodeURIComponent(normalizedEmail)}&sent=1`, { replace: true });
    } catch (err) {
      const serverFieldErrors = getFieldErrors(err);
      if (Object.keys(serverFieldErrors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...serverFieldErrors }));
      } else {
        setServerError(getErrorMessage(err, "Registration failed"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      icon={UserPlus}
      title="Create your account"
      subtitle="Sign up to get started"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="text-primary font-medium hover:underline">
            Log in
          </Link>
        </>
      }
    >
      {serverError && (
        <div className="mb-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
          {serverError}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="full_name">Full Name</Label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="full_name"
              type="text"
              autoComplete="name"
              autoFocus
              placeholder="Jane Doe"
              value={fullName}
              onChange={(e) => { setFullName(e.target.value); clearFieldError("first_name"); markTouched("first_name"); }}
              onBlur={() => markTouched("first_name")}
              maxLength={50}
              className={cn("pl-10 h-12", errorFor("first_name") && "border-destructive focus-visible:ring-destructive")}
              aria-invalid={Boolean(errorFor("first_name"))}
            />
          </div>
          <FieldError message={errorFor("first_name")} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); clearFieldError("email"); markTouched("email"); }}
              onBlur={() => markTouched("email")}
              maxLength={254}
              className={cn("pl-10 h-12", errorFor("email") && "border-destructive focus-visible:ring-destructive")}
              aria-invalid={Boolean(errorFor("email"))}
            />
          </div>
          <FieldError message={errorFor("email")} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => { setPassword(e.target.value); clearFieldError("password"); markTouched("password"); }}
              onBlur={() => markTouched("password")}
              maxLength={128}
              className={cn("pl-10 pr-10 h-12", errorFor("password") && "border-destructive focus-visible:ring-destructive")}
              aria-invalid={Boolean(errorFor("password"))}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {password && (
            <div>
              <div className="flex gap-1">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className={cn("h-1 flex-1 rounded-full bg-muted", i < strength && STRENGTH_BAR_COLORS[strength])}
                  />
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-1">{PASSWORD_STRENGTH_LABELS[strength]}</p>
            </div>
          )}
          <FieldError message={errorFor("password")} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirm">Confirm Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <Input
              id="confirm"
              type={showConfirmPassword ? "text" : "password"}
              autoComplete="new-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => { setConfirmPassword(e.target.value); clearFieldError("password_confirm"); markTouched("password_confirm"); }}
              onBlur={() => markTouched("password_confirm")}
              maxLength={128}
              className={cn("pl-10 pr-10 h-12", errorFor("password_confirm") && "border-destructive focus-visible:ring-destructive")}
              aria-invalid={Boolean(errorFor("password_confirm"))}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword((v) => !v)}
              tabIndex={-1}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label={showConfirmPassword ? "Hide password" : "Show password"}
            >
              {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <FieldError message={errorFor("password_confirm")} />
        </div>

        <Button type="submit" className="w-full h-12 font-medium" disabled={loading || !isValid}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Creating account...
            </>
          ) : (
            "Create account"
          )}
        </Button>
      </form>

      <GoogleLoginButton
        onSuccess={() => navigate("/", { replace: true })}
        onError={(message) => setServerError(message)}
      />
    </AuthLayout>
  );
}
