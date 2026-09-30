/**
 * PERCEPTA SHARED AUTHENTICATION TYPES
 */

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: "ADMIN" | "OPERATOR" | "ANALYST" | "COMMANDER";
  tenant_id?: string;
  created_at: string;
}

export interface AuthSession {
  user: AuthUser;
  access_token: string;
  refresh_token?: string;
  expires_at: number;
}
