begin;

alter table public.emergencies
    add column if not exists idempotency_key uuid;
alter table public.emergencies
    add column if not exists location_accuracy_m double precision;
alter table public.emergencies
    alter column latitude drop not null;
alter table public.emergencies
    alter column longitude drop not null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_coordinates_paired_check'
    ) then
        alter table public.emergencies
            add constraint emergencies_coordinates_paired_check
            check (
                (latitude is null and longitude is null)
                or (latitude is not null and longitude is not null)
            ) not valid;
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_latitude_range_check'
    ) then
        alter table public.emergencies
            add constraint emergencies_latitude_range_check
            check (latitude is null or latitude between -90 and 90)
            not valid;
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_longitude_range_check'
    ) then
        alter table public.emergencies
            add constraint emergencies_longitude_range_check
            check (longitude is null or longitude between -180 and 180)
            not valid;
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.emergencies'::regclass
          and conname = 'emergencies_location_accuracy_check'
    ) then
        alter table public.emergencies
            add constraint emergencies_location_accuracy_check
            check (location_accuracy_m is null or location_accuracy_m >= 0)
            not valid;
    end if;
end;
$$;

create unique index if not exists emergencies_user_id_idempotency_key_idx
    on public.emergencies (user_id, idempotency_key)
    where user_id is not null and idempotency_key is not null;

comment on column public.emergencies.idempotency_key is
    'Per-user retry key for an SOS submission; legacy rows remain NULL.';
comment on column public.emergencies.location_accuracy_m is
    'Browser-reported GPS accuracy in metres; NULL when location is unavailable.';

commit;
