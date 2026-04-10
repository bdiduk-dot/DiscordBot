create table if not exists public.guild_settings (
    guild_id bigint primary key,
    allowed_channel_id bigint,
    activity_role_id bigint,
    updated_at timestamp with time zone default timezone('utc', now())
);

create index if not exists guild_settings_updated_at_idx
    on public.guild_settings (updated_at desc);
