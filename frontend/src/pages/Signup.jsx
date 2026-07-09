import { useState } from "react";
import {
  FaUser,
  FaEnvelope,
  FaLock,
  FaEye,
  FaEyeSlash,
} from "react-icons/fa";
import { API_ROOT } from "../services/api";
import "../styles/Auth.css";

function Signup() {
  const [formData, setFormData] = useState({
    fullname: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [message, setMessage] = useState("");

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });

    setMessage("");
  };

  // -------------------------
  // PASSWORD CHECKS
  // -------------------------

  const passwordChecks = {
    length: formData.password.length >= 8,
    uppercase: /[A-Z]/.test(formData.password),
    lowercase: /[a-z]/.test(formData.password),
    number: /[0-9]/.test(formData.password),
    special: /[!@#$%^&*]/.test(formData.password),
  };

  const passwordStrength =
    Object.values(passwordChecks).filter(Boolean).length;

  const getStrength = () => {
    if (passwordStrength <= 2) return "Weak";
    if (passwordStrength <= 4) return "Medium";
    return "Strong";
  };

  // -------------------------
  // FORM VALIDATION
  // -------------------------

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
    formData.email
  );

  const nameValid = formData.fullname.trim().length > 2;

  const passwordValid =
    passwordChecks.length &&
    passwordChecks.uppercase &&
    passwordChecks.lowercase &&
    passwordChecks.number &&
    passwordChecks.special;

  const confirmPasswordValid =
    formData.password === formData.confirmPassword &&
    formData.confirmPassword !== "";

  const formValid =
    nameValid &&
    emailValid &&
    passwordValid &&
    confirmPasswordValid;

  // -------------------------
  // SUBMIT
  // -------------------------

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formValid) {
      setMessage("Please complete all required fields correctly.");
      return;
    }

    try {
      const response = await fetch(`${API_ROOT}/signup/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          first_name: formData.fullname,
          email: formData.email,
          password: formData.password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message || "Signup successful!");

        setFormData({
          fullname: "",
          email: "",
          password: "",
          confirmPassword: "",
        });
      } else {
        setMessage(data.message || "Signup failed.");
      }
    } catch (error) {
      console.error(error);
      setMessage("Could not connect to the server.");
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>Create Account</h2>

        {message && <div className="message">{message}</div>}

        <form onSubmit={handleSubmit}>
          {/* Full Name */}
          <div className="input-group">
            <FaUser className="icon" />

            <input
              type="text"
              name="fullname"
              placeholder="Full Name"
              value={formData.fullname}
              onChange={handleChange}
            />
          </div>

          {!nameValid && formData.fullname !== "" && (
            <p className="error">
              Full name must contain at least 3 characters.
            </p>
          )}

          {/* Email */}
          <div className="input-group">
            <FaEnvelope className="icon" />

            <input
              type="email"
              name="email"
              placeholder="Email Address"
              value={formData.email}
              onChange={handleChange}
            />
          </div>

          {!emailValid && formData.email !== "" && (
            <p className="error">
              Please enter a valid email address.
            </p>
          )}

          {/* Password */}
          <div className="input-group">
            <FaLock className="icon" />

            <input
              type={showPassword ? "text" : "password"}
              name="password"
              placeholder="Password"
              value={formData.password}
              onChange={handleChange}
            />

            <span
              className="eye-icon"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <FaEyeSlash /> : <FaEye />}
            </span>
          </div>

          {/* Strength Bar */}
          <div className="strength-bar">
            <div
              className={`strength-fill strength-${getStrength().toLowerCase()}`}
            ></div>
          </div>

          <p className="strength-text">
            Password Strength:
            <strong> {getStrength()}</strong>
          </p>

          {/* Password Requirements */}
          <div className="password-info">
            <h4>Password Requirements</h4>

            <p className={passwordChecks.length ? "success" : "fail"}>
              {passwordChecks.length ? "✔" : "✖"} Minimum 8 characters
            </p>

            <p className={passwordChecks.uppercase ? "success" : "fail"}>
              {passwordChecks.uppercase ? "✔" : "✖"} One uppercase letter
            </p>

            <p className={passwordChecks.lowercase ? "success" : "fail"}>
              {passwordChecks.lowercase ? "✔" : "✖"} One lowercase letter
            </p>

            <p className={passwordChecks.number ? "success" : "fail"}>
              {passwordChecks.number ? "✔" : "✖"} One number
            </p>

            <p className={passwordChecks.special ? "success" : "fail"}>
              {passwordChecks.special ? "✔" : "✖"} One special character
            </p>
          </div>

          {/* Confirm Password */}
          <div className="input-group">
            <FaLock className="icon" />

            <input
              type={showConfirmPassword ? "text" : "password"}
              name="confirmPassword"
              placeholder="Confirm Password"
              value={formData.confirmPassword}
              onChange={handleChange}
            />

            <span
              className="eye-icon"
              onClick={() =>
                setShowConfirmPassword(!showConfirmPassword)
              }
            >
              {showConfirmPassword ? (
                <FaEyeSlash />
              ) : (
                <FaEye />
              )}
            </span>
          </div>

          {!confirmPasswordValid &&
            formData.confirmPassword !== "" && (
              <p className="error">
                Passwords do not match.
              </p>
            )}

          <button
            type="submit"
            disabled={!formValid}
          >
            Create Account
          </button>

          <div className="auth-link">
            Already have an account?{" "}
            <a href="/login">Login</a>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Signup;