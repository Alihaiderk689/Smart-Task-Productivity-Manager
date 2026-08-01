"use client";
import { useTheme } from "@/context/ThemeContext"
import { Toaster as Sonner } from "sonner"

const Toaster = ({
  ...props
}) => {
  // This app manages its own light/dark state (ThemeContext), not
  // next-themes -- that package was never actually wired up (no provider
  // mounted), so useTheme() from it silently returns the "system" fallback
  // forever and toasts never actually followed the in-app theme toggle.
  const { theme } = useTheme()

  return (
    (<Sonner
      theme={theme}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props} />)
  );
}

export { Toaster }
