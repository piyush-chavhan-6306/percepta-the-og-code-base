import React, { useState, useEffect } from "react";
import { Navigate } from "react-router";
import { authService } from "@/features/auth/authService.adapter";
import { Loader2 } from "lucide-react";

interface ProtectedRouteProps {
  children: React.ReactNode;
  redirectPath?: string;
}

export function ProtectedRoute({
  children,
  redirectPath = "/auth?redirect=/dashboard",
}: ProtectedRouteProps) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    let isMounted = true;
    authService.getCurrentSession().then((session) => {
      if (isMounted) {
        if (!session || !session.access_token) {
          setIsAuthenticated(false);
        } else if (session.expires_at && Date.now() > session.expires_at) {
          authService.logout();
          setIsAuthenticated(false);
        } else {
          setIsAuthenticated(true);
        }
      }
    });
    return () => {
      isMounted = false;
    };
  }, []);

  if (isAuthenticated === null) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#05070a] text-gray-400 font-mono text-xs select-none">
        <Loader2 className="w-5 h-5 animate-spin mr-2 text-[#00e5ff]" />
        <span>AUTHENTICATING OPERATOR CLEARANCE...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={redirectPath} replace />;
  }

  return <>{children}</>;
}
