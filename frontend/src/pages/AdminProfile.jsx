import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { Camera, Loader2 } from 'lucide-react';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AvatarCropDialog from '@/components/AvatarCropDialog';
import { useAuth } from '@/context/AuthContext';
import { changePasswordRequest, getErrorMessage, updateProfileRequest } from '@/services/api';

// A separate page from pages/Profile.jsx on purpose -- the admin account
// never reaches the regular user routes (see RoleRoute), so it needs its
// own copy of "change my name/password/avatar" living under /admin. Both
// pages call the exact same backend endpoints; only the surrounding chrome
// differs.
function initialsFor(user) {
  const name = user?.first_name || user?.email || '?';
  return name.trim().slice(0, 1).toUpperCase();
}

export default function AdminProfile() {
  const { user, syncProfile } = useAuth();
  const fileInputRef = useRef(null);

  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [savingName, setSavingName] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [cropImageSrc, setCropImageSrc] = useState(null);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  const handleAvatarClick = () => fileInputRef.current?.click();

  const handleFileSelected = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => setCropImageSrc(reader.result);
    reader.readAsDataURL(file);
  };

  const handleCropSave = async (croppedFile) => {
    setUploadingAvatar(true);
    try {
      await updateProfileRequest({ avatarFile: croppedFile });
      await syncProfile();
      toast.success('Avatar updated');
      setCropImageSrc(null);
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to update avatar'));
    } finally {
      setUploadingAvatar(false);
    }
  };

  const handleSaveName = async (e) => {
    e.preventDefault();
    if (!firstName.trim()) return;
    setSavingName(true);
    try {
      await updateProfileRequest({ firstName });
      await syncProfile();
      toast.success('Name updated');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to update name'));
    } finally {
      setSavingName(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match');
      return;
    }
    setChangingPassword(true);
    try {
      await changePasswordRequest({ currentPassword, newPassword });
      toast.success('Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to change password'));
    } finally {
      setChangingPassword(false);
    }
  };

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Admin Profile</h1>

      {/* Avatar */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Avatar</h2>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleAvatarClick}
            disabled={uploadingAvatar}
            className="relative group"
            aria-label="Change avatar"
          >
            <Avatar className="w-20 h-20">
              <AvatarImage src={user?.avatar} alt={user?.first_name || user?.email} />
              <AvatarFallback className="text-xl font-semibold bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                {initialsFor(user)}
              </AvatarFallback>
            </Avatar>
            <span className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
              {uploadingAvatar ? (
                <Loader2 className="w-5 h-5 text-white animate-spin" />
              ) : (
                <Camera className="w-5 h-5 text-white" />
              )}
            </span>
          </button>
          <div className="text-sm text-slate-500 dark:text-slate-400">
            <p>Click the avatar to upload a new photo.</p>
            <p className="text-xs mt-1">You'll be able to zoom and reposition it before saving.</p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileSelected}
          />
        </div>
      </div>

      <AvatarCropDialog
        open={!!cropImageSrc}
        imageSrc={cropImageSrc}
        onCancel={() => setCropImageSrc(null)}
        onSave={handleCropSave}
      />

      {/* Display name */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Display Name</h2>
        <form onSubmit={handleSaveName} className="flex items-end gap-3">
          <div className="flex-1 space-y-2">
            <Label htmlFor="first_name">Name</Label>
            <Input id="first_name" value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="Your name" required />
          </div>
          <Button type="submit" disabled={savingName || !firstName.trim()}>
            {savingName ? 'Saving...' : 'Save'}
          </Button>
        </form>
        <p className="text-xs text-slate-400 mt-3">Email: {user?.email}</p>
      </div>

      {/* Change password */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm p-6">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current_password">Current Password</Label>
            <Input
              id="current_password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="new_password">New Password</Label>
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm_password">Confirm New Password</Label>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
          </div>
          <Button type="submit" disabled={changingPassword || !currentPassword || !newPassword || !confirmPassword}>
            {changingPassword ? 'Changing...' : 'Change Password'}
          </Button>
        </form>
      </div>
    </div>
  );
}
