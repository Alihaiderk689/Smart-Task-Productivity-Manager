import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage } from "@/services/api";

// Renders nothing when VITE_GOOGLE_CLIENT_ID isn't set (e.g. local dev before
// it's configured) instead of crashing -- see main.jsx's GoogleOAuthProvider.
export default function GoogleLoginButton({ onSuccess, onError }) {
  const { signInWithGoogle } = useAuth();

  if (!import.meta.env.VITE_GOOGLE_CLIENT_ID) {
    return null;
  }

  return (
    <>
      <div className="relative my-6">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t border-border" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-card px-2 text-muted-foreground">Or continue with</span>
        </div>
      </div>

      <div className="flex justify-center">
        <GoogleLogin
          width="336"
          text="continue_with"
          onSuccess={async (credentialResponse) => {
            try {
              const data = await signInWithGoogle(credentialResponse.credential);
              onSuccess?.(data);
            } catch (err) {
              onError?.(getErrorMessage(err, "Google sign-in failed"));
            }
          }}
          onError={() => onError?.("Google sign-in failed")}
        />
      </div>
    </>
  );
}
