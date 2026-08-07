import React from "react";
import authArt from "@/assets/flow-auth.jpg";
import logo from "@/assets/logo.png";

export default function AuthLayout({ title, subtitle, footer = null, children }) {
  return (
    <div className="min-h-screen flex bg-background">
      <div
        className="hidden lg:block lg:w-1/2 bg-cover bg-center"
        style={{ backgroundImage: `url(${authArt})` }}
        role="img"
        aria-label="Flow"
      />

      <div className="flex-1 min-w-0 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="text-center mb-10">
            <img src={logo} alt="TaskFlow" className="w-16 h-16 object-contain mx-auto mb-4" />
            <h1 className="text-3xl font-bold tracking-tight text-foreground">{title}</h1>
            {subtitle && <p className="text-muted-foreground mt-2">{subtitle}</p>}
          </div>
          <div className="bg-card rounded-2xl shadow-sm border border-border p-8">
            {children}
          </div>
          {footer && (
            <p className="text-center text-sm text-muted-foreground mt-6">{footer}</p>
          )}
        </div>
      </div>
    </div>
  );
}
