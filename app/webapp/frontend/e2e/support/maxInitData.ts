import crypto from "node:crypto";

export type LaunchUser = {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
};

export function readLaunchUser(): LaunchUser {
  const raw = process.env.E2E_USER_JSON ?? JSON.stringify({
    id: 71142489,
    first_name: "Алик",
    username: "alik",
  });
  return JSON.parse(raw) as LaunchUser;
}

export function buildSignedMaxInitData(token: string, user: LaunchUser): string {
  const authDate = String(Math.floor(Date.now() / 1000));
  const payload = {
    auth_date: authDate,
    query_id: `codex-${authDate}`,
    user: JSON.stringify(user),
  };
  const dataCheckString = Object.entries(payload)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");
  const secretKey = crypto.createHmac("sha256", "WebAppData").update(token).digest();
  const hash = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");
  return new URLSearchParams({
    ...payload,
    hash,
  }).toString();
}
