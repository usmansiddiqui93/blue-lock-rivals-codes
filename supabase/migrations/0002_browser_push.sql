-- Browser (Web Push) notifications for new codes.
create table if not exists public.push_subscriptions (
  endpoint        text primary key check (length(endpoint) <= 1000),
  p256dh          text not null check (length(p256dh) <= 200),
  auth            text not null check (length(auth) <= 100),
  origin          text not null,
  created_at      timestamptz not null default now(),
  last_success_at timestamptz,
  failures        integer not null default 0
);

-- Private server settings (the VAPID key pair is generated on first use and kept here).
create table if not exists public.app_config (
  key   text primary key,
  value jsonb not null,
  created_at timestamptz not null default now()
);

alter table public.push_subscriptions enable row level security;
alter table public.app_config enable row level security;
revoke all on public.push_subscriptions from anon, authenticated;
revoke all on public.app_config from anon, authenticated;

alter table public.notified_codes add column if not exists push_recipients integer not null default 0;
