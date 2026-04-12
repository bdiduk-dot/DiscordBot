create table if not exists public.market_guild_states (
    guild_id bigint primary key,
    active_event jsonb,
    next_event_after timestamp with time zone,
    updated_at timestamp with time zone default timezone('utc', now())
);

create index if not exists market_guild_states_updated_at_idx
    on public.market_guild_states (updated_at desc);
