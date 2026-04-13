create table if not exists public.guild_settings (
    guild_id bigint primary key,
    allowed_channel_id bigint,
    activity_role_id bigint,
    updated_at timestamp with time zone default timezone('utc', now())
);

create index if not exists guild_settings_updated_at_idx
    on public.guild_settings (updated_at desc);

alter table if exists public.guild_settings disable row level security;

grant usage on schema public to anon, authenticated, service_role;
grant all on table public.guild_settings to anon, authenticated, service_role;
