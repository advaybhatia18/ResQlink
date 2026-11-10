begin;

alter table public.emergencies
    add column if not exists user_id uuid;

do $$
begin
    if exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_user_id_fkey'
          and confdeltype <> 'c'
    ) then
        alter table public.emergencies
            drop constraint emergencies_user_id_fkey;
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_user_id_fkey'
    ) then
        alter table public.emergencies
            add constraint emergencies_user_id_fkey
            foreign key (user_id)
            references public.profiles (id)
            on delete cascade
            not valid;
    end if;
end;
$$;

-- Only copy ownership previously recorded by the authenticated backend.
-- Rows without a known owner deliberately remain NULL for manual review.
do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'emergencies'
          and column_name = 'created_by'
    ) then
        update public.emergencies as emergency
        set user_id = emergency.created_by
        where emergency.user_id is null
          and emergency.created_by is not null
          and exists (
              select 1
              from public.profiles as profile
              where profile.id = emergency.created_by
          );
    end if;
end;
$$;

alter table public.emergencies
    validate constraint emergencies_user_id_fkey;

comment on column public.emergencies.user_id is
    'Authenticated owner. NULL identifies legacy or explicitly unassigned alerts; do not infer ownership.';

create index if not exists emergencies_user_id_idx
    on public.emergencies (user_id);

alter table public.profiles enable row level security;
alter table public.emergencies enable row level security;

revoke all on public.profiles from anon, authenticated;
revoke all on public.emergencies from anon, authenticated;
revoke all on sequence public.emergencies_id_seq from anon, authenticated;
grant select on public.profiles to authenticated, service_role;
grant select on public.emergencies to authenticated;
grant select, insert, update on public.emergencies to service_role;
grant usage, select on sequence public.emergencies_id_seq to service_role;

drop policy if exists "Users read own profile" on public.profiles;
create policy "Users read own profile"
    on public.profiles
    for select
    to authenticated
    using (id = (select auth.uid()));

drop policy if exists "Users read own or admin emergency records"
    on public.emergencies;
create policy "Users read own or admin emergency records"
    on public.emergencies
    for select
    to authenticated
    using (
        user_id = (select auth.uid())
        or exists (
            select 1
            from public.profiles as profile
            where profile.id = (select auth.uid())
              and profile.role = 'ADMIN'
        )
    );

drop policy if exists "Users insert own emergency records"
    on public.emergencies;
drop policy if exists "Admins update emergency status"
    on public.emergencies;

commit;
