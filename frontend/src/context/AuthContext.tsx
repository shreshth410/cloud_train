import React, { createContext, useContext, useState, useEffect } from "react";
import {
  getAuthToken,
  getStoredUser,
  setAuthToken,
} from "@/lib/api";
import {
  cognitoSignIn,
  cognitoSignUp,
  cognitoConfirmSignUp,
  localBypassSignIn,
} from "@/lib/cognito";

interface AuthContextType {
  isAuthenticated: boolean;
  user: { email: string; userId: string } | null;
  login: (email: string, pass: string) => Promise<void>;
  signup: (email: string, pass: string) => Promise<string>;
  confirmSignup: (email: string, code: string) => Promise<void>;
  logout: () => void;
  bypassLogin: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => !!getAuthToken());
  const [user, setUser] = useState<{ email: string; userId: string } | null>(() => {
    return getAuthToken() ? getStoredUser() : null;
  });

  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      setIsAuthenticated(true);
      setUser(getStoredUser());
    } else {
      setIsAuthenticated(false);
      setUser(null);
    }
  }, []);

  const login = async (email: string, pass: string) => {
    await cognitoSignIn(email, pass);
    setIsAuthenticated(true);
    setUser(getStoredUser());
  };

  const signup = async (email: string, pass: string) => {
    return cognitoSignUp(email, pass);
  };

  const confirmSignup = async (email: string, code: string) => {
    await cognitoConfirmSignUp(email, code);
  };

  const logout = () => {
    setAuthToken(null);
    setIsAuthenticated(false);
    setUser(null);
  };

  const bypassLogin = () => {
    localBypassSignIn();
    setIsAuthenticated(true);
    setUser(getStoredUser());
  };

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        user,
        login,
        signup,
        confirmSignup,
        logout,
        bypassLogin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
