import React, { useState, useEffect } from "react";
import {
  X,
  User,
  Shield,
  Phone,
  Building,
  Award,
  Radio,
  Edit2,
  Check,
  LogOut,
  Camera,
  ExternalLink,
  Compass,
} from "lucide-react";
import { authService, AuthUser } from "@/features/auth/authService.adapter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface OfficerProfileData {
  fullName: string;
  avatarUrl: string;
  gender: string;
  contactNumber: string;
  roleRank: string;
  regimentUnit: string;
  division: string;
  organization: string;
  clearanceLevel: string;
  serviceId: string;
}

const DEFAULT_PROFILE: OfficerProfileData = {
  fullName: "Duty Officer Alpha",
  avatarUrl: "",
  gender: "Not configured",
  contactNumber: "TAC-VOIP-7024 (Secure Line)",
  roleRank: "Senior Tactical Surveillance Officer",
  regimentUnit: "14th Border Surveillance Battalion",
  division: "Northern Border Command / Forward Sector",
  organization: "Ministry of Home Affairs / ITBP",
  clearanceLevel: "LEVEL-4 (TOP SECRET // COMMAND SECURE)",
  serviceId: "PERC-SEC-94021",
};

const STORAGE_KEY = "percepta_officer_profile";

export function getStoredOfficerProfile(): OfficerProfileData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...DEFAULT_PROFILE, ...JSON.parse(raw) };
    }
  } catch (e) {
    console.warn("Failed to load officer profile:", e);
  }
  return DEFAULT_PROFILE;
}

export function saveOfficerProfile(data: OfficerProfileData) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (e) {
    console.warn("Failed to save officer profile:", e);
  }
}

interface OfficerProfileModalProps {
  isOpen?: boolean;
  open?: boolean;
  onClose: () => void;
  onLogout?: () => void;
  onRetakeTour?: () => void;
}

export const OfficerProfileModal: React.FC<OfficerProfileModalProps> = ({
  isOpen = true,
  open = true,
  onClose,
  onLogout,
  onRetakeTour,
}) => {
  const isVisible = (isOpen ?? true) && (open ?? true);
  const [profile, setProfile] = useState<OfficerProfileData>(getStoredOfficerProfile);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<OfficerProfileData>(profile);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    if (isVisible) {
      const p = getStoredOfficerProfile();
      setProfile(p);
      setEditForm(p);
      authService.getCurrentSession().then((session) => {
        if (session?.user) {
          setCurrentUser(session.user);
          if (session.user.operatorCallsign && p.fullName === "Duty Officer Alpha") {
            setProfile((prev) => ({
              ...prev,
              fullName: session.user?.operatorCallsign || prev.fullName,
              clearanceLevel: session.user?.clearanceLevel || prev.clearanceLevel,
            }));
          }
        }
      });
    }
  }, [isVisible]);

  if (!isVisible) return null;

  const handleSave = () => {
    setProfile(editForm);
    saveOfficerProfile(editForm);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditForm(profile);
    setIsEditing(false);
  };

  const handleSignOut = async () => {
    await authService.logout();
    onClose();
    if (onLogout) {
      onLogout();
    } else {
      window.location.href = "/auth?redirect=/dashboard";
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="w-full max-w-2xl bg-[#090d14] border border-[#00e5ff]/30 rounded-xl shadow-[0_0_50px_rgba(0,229,255,0.15)] overflow-hidden flex flex-col font-sans relative"
        data-testid="officer-profile-modal"
      >
        {/* HUD Corner Brackets */}
        <div className="absolute top-2 left-2 w-3 h-3 border-t-2 border-l-2 border-[#00e5ff]/60 pointer-events-none" />
        <div className="absolute top-2 right-2 w-3 h-3 border-t-2 border-r-2 border-[#00e5ff]/60 pointer-events-none" />
        <div className="absolute bottom-2 left-2 w-3 h-3 border-b-2 border-l-2 border-[#00e5ff]/60 pointer-events-none" />
        <div className="absolute bottom-2 right-2 w-3 h-3 border-b-2 border-r-2 border-[#00e5ff]/60 pointer-events-none" />

        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-[#00e5ff]/10 border border-[#00e5ff]/30 flex items-center justify-center">
              <Shield className="w-4 h-4 text-[#00e5ff]" />
            </div>
            <div>
              <h2 className="text-sm font-bold font-mono tracking-wider text-white uppercase">
                OFFICER // OPERATOR DOSSIER
              </h2>
              <p className="text-[10px] font-mono text-gray-400">
                PERCEPTA DEFENSE COMMAND PERSONNEL RECORD
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!isEditing ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsEditing(true)}
                className="h-8 text-xs font-mono text-[#00e5ff] hover:bg-[#00e5ff]/10 gap-1"
                data-testid="edit-profile-btn"
              >
                <Edit2 className="w-3.5 h-3.5" />
                <span>EDIT RECORD</span>
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCancel}
                className="h-8 text-xs font-mono text-gray-400 hover:text-white"
              >
                CANCEL
              </Button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
              aria-label="Close"
              data-testid="close-profile-btn"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto max-h-[75vh] space-y-6">
          {/* Top Banner: Avatar + Primary Identity */}
          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-5 p-4 rounded-lg bg-black/40 border border-white/5">
            <div className="relative group">
              <div className="w-20 h-20 rounded-xl bg-gradient-to-br from-[#00e5ff]/20 to-[#0055ff]/10 border border-[#00e5ff]/40 flex items-center justify-center overflow-hidden shadow-lg">
                {profile.avatarUrl ? (
                  <img
                    src={profile.avatarUrl}
                    alt={profile.fullName}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <User className="w-10 h-10 text-[#00e5ff]/80" />
                )}
              </div>
              {isEditing && (
                <div className="absolute inset-0 bg-black/60 rounded-xl flex items-center justify-center cursor-pointer hover:bg-black/70 transition-colors">
                  <Camera className="w-5 h-5 text-white" />
                </div>
              )}
            </div>

            <div className="flex-1 text-center sm:text-left space-y-1.5">
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
                <h3 className="text-base font-bold text-white font-mono">
                  {profile.fullName || "Not configured"}
                </h3>
                <Badge
                  variant="outline"
                  className="text-[10px] px-2 py-0 border-[#00e5ff]/40 text-[#00e5ff] font-mono"
                >
                  {profile.serviceId || "ID NOT CONFIGURED"}
                </Badge>
              </div>
              <p className="text-xs font-mono text-gray-300">
                {profile.roleRank || "Role Not Configured"}
              </p>
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2 pt-1 text-[11px] font-mono text-gray-400">
                <span className="flex items-center gap-1">
                  <Building className="w-3.5 h-3.5 text-gray-400" />
                  {profile.organization || "Not configured"}
                </span>
                <span>•</span>
                <span className="text-[#00e5ff]">
                  {profile.clearanceLevel || "LEVEL-4"}
                </span>
              </div>
            </div>
          </div>

          {/* Form Fields / Read-only View */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Full Name */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <User className="w-3 h-3 text-[#00e5ff]" /> Full Name
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.fullName}
                  onChange={(e) => setEditForm({ ...editForm, fullName: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.fullName || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Sex / Gender Field */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Award className="w-3 h-3 text-[#00e5ff]" /> Sex / Gender
              </label>
              {isEditing ? (
                <select
                  value={editForm.gender}
                  onChange={(e) => setEditForm({ ...editForm, gender: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                >
                  <option value="Not configured">Not configured</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.gender && profile.gender !== "Not configured" ? (
                    profile.gender
                  ) : (
                    <span className="text-gray-500 italic">Not configured</span>
                  )}
                </div>
              )}
            </div>

            {/* Role / Rank */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Shield className="w-3 h-3 text-[#00e5ff]" /> Role / Rank
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.roleRank}
                  onChange={(e) => setEditForm({ ...editForm, roleRank: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.roleRank || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Official / Contact Number */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Phone className="w-3 h-3 text-[#00e5ff]" /> Official Contact / Comms
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.contactNumber}
                  onChange={(e) => setEditForm({ ...editForm, contactNumber: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.contactNumber || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Regiment / Unit */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Radio className="w-3 h-3 text-[#00e5ff]" /> Regiment / Unit
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.regimentUnit}
                  onChange={(e) => setEditForm({ ...editForm, regimentUnit: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.regimentUnit || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Division */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Building className="w-3 h-3 text-[#00e5ff]" /> Operational Division
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.division}
                  onChange={(e) => setEditForm({ ...editForm, division: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.division || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Organization */}
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <Building className="w-3 h-3 text-[#00e5ff]" /> Organization
              </label>
              {isEditing ? (
                <input
                  type="text"
                  value={editForm.organization}
                  onChange={(e) => setEditForm({ ...editForm, organization: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              ) : (
                <div className="text-xs font-mono text-white p-2 rounded bg-black/30 border border-white/5">
                  {profile.organization || <span className="text-gray-500 italic">Not configured</span>}
                </div>
              )}
            </div>

            {/* Avatar URL (if editing) */}
            {isEditing && (
              <div className="space-y-1">
                <label className="text-[10px] font-mono text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                  <Camera className="w-3 h-3 text-[#00e5ff]" /> Avatar Image URL
                </label>
                <input
                  type="text"
                  placeholder="https://... or /avatars/officer.png"
                  value={editForm.avatarUrl}
                  onChange={(e) => setEditForm({ ...editForm, avatarUrl: e.target.value })}
                  className="w-full bg-black/60 border border-white/20 rounded px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-[#00e5ff]"
                />
              </div>
            )}
          </div>

          {/* Action Row when Editing */}
          {isEditing && (
            <div className="flex justify-end gap-3 pt-3 border-t border-white/10">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancel}
                className="text-xs font-mono border-white/10 text-gray-400 hover:text-white"
              >
                DISCARD CHANGES
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                className="text-xs font-mono bg-[#00e5ff] text-black hover:bg-[#00e5ff]/90 gap-1.5 shadow-[0_0_15px_rgba(0,229,255,0.4)]"
                data-testid="save-profile-btn"
              >
                <Check className="w-3.5 h-3.5" />
                <span>SAVE DOSSIER</span>
              </Button>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-white/10 bg-white/[0.02]">
          <div className="text-[10px] font-mono text-gray-500">
            SESSION AUTHENTICATED VIA STRICT CLEARANCE PROTOCOL
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onClose();
                if (onRetakeTour) onRetakeTour();
              }}
              className="h-8 text-xs font-mono border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/60 gap-1.5"
            >
              <Compass className="w-3.5 h-3.5" />
              <span>SYSTEM TOUR</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSignOut}
              className="h-8 text-xs font-mono border-red-500/30 text-red-400 hover:bg-red-500/10 hover:border-red-500/60 gap-1.5"
              data-testid="sign-out-btn"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>TERMINATE SESSION</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
