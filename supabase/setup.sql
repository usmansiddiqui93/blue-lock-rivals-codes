-- Blue Lock Rivals Codes: one-time database setup.
-- Paste this whole file into Supabase > SQL Editor and click Run. Safe to run more than once.

-- Email alerts for new Blue Lock Rivals codes.
-- Only the Edge Function (service role) touches these tables: RLS is on with no public policies.

create table if not exists public.subscribers (
  id            uuid primary key default gen_random_uuid(),
  email         text not null unique check (email = lower(email) and length(email) <= 254),
  status        text not null default 'pending' check (status in ('pending', 'confirmed', 'unsubscribed')),
  confirm_token uuid not null default gen_random_uuid(),
  unsub_token   uuid not null default gen_random_uuid(),
  origin        text not null,
  created_at    timestamptz not null default now(),
  confirm_sent_at timestamptz,
  confirmed_at  timestamptz,
  unsubscribed_at timestamptz
);
create index if not exists subscribers_status_idx on public.subscribers (status);
create unique index if not exists subscribers_confirm_token_idx on public.subscribers (confirm_token);
create unique index if not exists subscribers_unsub_token_idx on public.subscribers (unsub_token);

-- One row per code that has been announced. Inserting first and sending second makes
-- notifications idempotent: a code can never be emailed twice, even if two runs overlap.
create table if not exists public.notified_codes (
  code        text primary key,
  reward      text,
  notified_at timestamptz not null default now(),
  recipients  integer not null default 0
);

alter table public.subscribers enable row level security;
alter table public.notified_codes enable row level security;
revoke all on public.subscribers from anon, authenticated;
revoke all on public.notified_codes from anon, authenticated;

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
