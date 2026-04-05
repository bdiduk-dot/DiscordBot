create table if not exists public.easter_guild_states (
    guild_id bigint primary key,
    phase text,
    active_rabbit_event_id text,
    rabbit_active_until timestamp with time zone,
    rabbit_last_spawn_at timestamp with time zone,
    rabbit_last_announce_message_id bigint,
    updated_at timestamp with time zone default timezone('utc', now())
);

create index if not exists easter_guild_states_updated_at_idx
    on public.easter_guild_states (updated_at desc);
