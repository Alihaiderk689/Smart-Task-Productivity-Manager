import { useState } from "react";
import "../styles/Auth.css";

function Login() {
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setMessage("");
  };

  const validate = () => {
    let newErrors = {};

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!emailRegex.test(formData.email)) {
      newErrors.email = "Enter valid email";
    }

    if (!formData.password) {
      newErrors.password = "Password required";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!validate()) {
      setMessage("Fix errors");
      return;
    }

    setMessage("Login successful (backend next step)");
    console.log(formData);
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>Login</h2>

        {message && <div className="message">{message}</div>}

        <form onSubmit={handleSubmit}>
          <input
            name="email"
            placeholder="Email"
            value={formData.email}
            onChange={handleChange}
          />
          {errors.email && <p className="error">{errors.email}</p>}

          <div className="password-box">
            <input
              type={showPassword ? "text" : "password"}
              name="password"
              placeholder="Password"
              value={formData.password}
              onChange={handleChange}
            />

            <span onClick={() => setShowPassword(!showPassword)} className="toggle">
              {showPassword ? "🙈" : "👁️"}
            </span>
          </div>

          {errors.password && <p className="error">{errors.password}</p>}

          <button>
            Login
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;