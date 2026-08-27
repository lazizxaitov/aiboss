"use client";

import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Surface } from "@/components/ui/surface";
import { DashboardShell } from "@/components/shell/dashboard-shell";
import { useUnsavedChangesGuard } from "@/lib/use-unsaved-changes";

const coreApiUrl = process.env.NEXT_PUBLIC_CORE_API_URL ?? "http://127.0.0.1:8000";

export default function ProfilePage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [name, setName] = useState("");
  const [about, setAbout] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [unlockPin, setUnlockPin] = useState("");
  const [unlockPinError, setUnlockPinError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [profileDirty, setProfileDirty] = useState(false);
  const [credentialsDirty, setCredentialsDirty] = useState(false);

  useUnsavedChangesGuard(profileDirty || credentialsDirty);

  useEffect(() => {
    const token = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=");
    if (token) setLogin(decodeURIComponent(token).split(":")[0] ?? "");
    setName(localStorage.getItem("aibos_profile_name") ?? "");
    setAbout(localStorage.getItem("aibos_profile_about") ?? "");
    setPhoto(localStorage.getItem("aibos_profile_photo"));
    const sessionToken = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=");
    if (sessionToken) {
      void fetch(`${coreApiUrl}/api/v1/auth/profile`, {
        headers: { Authorization: `Bearer ${decodeURIComponent(sessionToken)}` },
        cache: "no-store",
      }).then((response) => response.ok ? response.json() : null).then((profile) => {
        if (!profile) return;
        setName(profile.name ?? "");
        setAbout(profile.about ?? "");
        localStorage.setItem("aibos_profile_name", profile.name ?? "");
        localStorage.setItem("aibos_profile_about", profile.about ?? "");
      }).catch(() => undefined);
    }
  }, []);

  const saveAbout = () => {
    localStorage.setItem("aibos_profile_name", name);
    localStorage.setItem("aibos_profile_about", about);
    setProfileDirty(false);
    const token = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=");
    if (token) {
      void fetch(`${coreApiUrl}/api/v1/auth/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${decodeURIComponent(token)}` },
        body: JSON.stringify({ name, about }),
      }).catch(() => undefined);
    }
    window.dispatchEvent(new Event("aibos-profile-updated"));
    setNotice("Профиль сохранён");
  };

  const selectPhoto = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") return;
      localStorage.setItem("aibos_profile_photo", reader.result);
      setPhoto(reader.result);
      window.dispatchEvent(new Event("aibos-profile-updated"));
      setNotice("Фото профиля обновлено");
    };
    reader.readAsDataURL(file);
  };

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordError(null);
    setNotice(null);
    try {
      const response = await fetch(`${coreApiUrl}/api/v1/auth/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login, current_password: currentPassword, new_password: newPassword }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? "Не удалось изменить пароль.");
      setCurrentPassword("");
      setNewPassword("");
      setCredentialsDirty(false);
      setNotice("Пароль изменён");
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : "Не удалось изменить пароль.");
    }
  };

  const saveUnlockPin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setUnlockPinError(null);
    try {
      const token = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("aibos_owner_session="))?.split("=").slice(1).join("=");
      const response = await fetch(`${coreApiUrl}/api/v1/auth/unlock-pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${decodeURIComponent(token)}` } : {}) },
        body: JSON.stringify({ pin: unlockPin }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? "Не удалось сохранить PIN.");
      setUnlockPin("");
      setCredentialsDirty(false);
      setNotice("PIN разблокировки сохранён");
    } catch (error) {
      setUnlockPinError(error instanceof Error ? error.message : "Не удалось сохранить PIN.");
    }
  };

  return (
    <DashboardShell>
      <section className="mx-auto w-full max-w-4xl space-y-4">
      <Surface>
        <div className="rounded-[28px] bg-[#2E3137] p-5 sm:p-6">
          <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Профиль</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-[#f4f7fb]">Личные данные</h1>
          <p className="mt-2 max-w-2xl text-sm leading-5 text-slate-400">Эта информация помогает ИИ лучше понимать вас, ваши задачи и предпочтения в общении.</p>
        </div>
      </Surface>

      <div className="grid gap-4">
        <Surface className="h-fit">
          <div className="rounded-[28px] bg-[#2E3137] p-5 sm:p-6">
            <h2 className="text-xl font-semibold text-[#f4f7fb]">Фото профиля</h2>
            <div className="mt-4 flex flex-col items-center gap-3">
              {photo ? <img src={photo} alt="Фото профиля" className="h-24 w-24 rounded-full object-cover" /> : <div className="flex h-24 w-24 items-center justify-center rounded-full bg-[#f3d5b4] text-2xl text-[#1E1E21]">{(name || login || "А").slice(0, 3).toUpperCase()}</div>}
              <label className="inline-flex cursor-pointer items-center rounded-full border border-[#4a4e56] px-4 py-2 text-sm text-slate-200 transition hover:bg-[#343840]">
                Загрузить фото
                <input type="file" accept="image/*" className="sr-only" onChange={selectPhoto} />
              </label>
            </div>
          </div>
        </Surface>

        <Surface>
          <div className="rounded-[28px] bg-[#2E3137] p-5 sm:p-6">
              <h2 className="text-xl font-semibold text-[#f4f7fb]">О себе для ИИ</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">Напишите, кто вы, чем занимаетесь, какие у вас цели и как с вами лучше общаться.</p>
            <Input value={name} onChange={(event) => { setName(event.target.value); setProfileDirty(true); }} placeholder="Имя" className="mt-4" />
            <textarea value={about} onChange={(event) => { setAbout(event.target.value); setProfileDirty(true); }} placeholder="Например: Я владелец бизнеса..." className="mt-3 min-h-32 w-full resize-y rounded-2xl border border-[#3a3d43] bg-[#343840] px-4 py-3 text-sm leading-6 text-[#f4f7fb] outline-none placeholder:text-slate-400 focus:border-[#6a6f79]" />
            <div className="mt-3 flex items-center gap-3">
              <Button variant="primary" onClick={saveAbout}>Сохранить</Button>
              {notice ? <span className="text-sm text-slate-300">{notice}</span> : null}
            </div>
          </div>
        </Surface>
      </div>

      <Surface>
        <div className="rounded-[28px] bg-[#2E3137] p-5 sm:p-6">
          <h2 className="text-xl font-semibold text-[#f4f7fb]">Данные входа</h2>
          <div className="mt-4 grid gap-3">
            <label className="space-y-2"><span className="text-sm text-slate-300">Логин</span><Input value={login} readOnly /></label>
            <label className="space-y-2"><span className="text-sm text-slate-300">Пароль</span><Input value="••••••••" readOnly /></label>
          </div>
          <form className="mt-4 grid gap-3" onSubmit={changePassword}>
            <Input type="password" value={currentPassword} onChange={(event) => { setCurrentPassword(event.target.value); setCredentialsDirty(true); }} placeholder="Текущий пароль" required />
            <Input type="password" value={newPassword} onChange={(event) => { setNewPassword(event.target.value); setCredentialsDirty(true); }} placeholder="Новый пароль (от 8 символов)" minLength={8} required />
            <div className="flex flex-wrap items-center gap-3"><Button type="submit" variant="secondary">Изменить пароль</Button>{passwordError ? <span className="text-sm text-rose-300">{passwordError}</span> : null}</div>
          </form>
          <form className="mt-6 grid gap-3 border-t border-[#3a3d43] pt-5" onSubmit={saveUnlockPin}>
            <div>
              <h3 className="text-base font-semibold text-[#f4f7fb]">PIN разблокировки</h3>
              <p className="mt-1 text-sm text-slate-400">Отдельный PIN из 4 цифр для снятия блокировки сессии.</p>
            </div>
            <Input type="password" inputMode="numeric" maxLength={4} pattern="[0-9]{4}" value={unlockPin} onChange={(event) => { setUnlockPin(event.target.value.replace(/\D/g, "").slice(0, 4)); setCredentialsDirty(true); }} placeholder="Новый PIN из 4 цифр" required />
            <div className="flex flex-wrap items-center gap-3"><Button type="submit" variant="secondary">Сохранить PIN</Button>{unlockPinError ? <span className="text-sm text-rose-300">{unlockPinError}</span> : null}</div>
          </form>
        </div>
      </Surface>
      </section>
    </DashboardShell>
  );
}
