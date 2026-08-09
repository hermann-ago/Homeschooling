-- A narrowly scoped, server-only one-time setup operation. The app role can
-- execute this function but cannot directly access auth schema tables.
create or replace function app.create_first_family_account(p_email text, p_password text)
returns uuid
language plpgsql
security definer
set search_path = auth, app, extensions, public
as $$
declare
  new_user_id uuid := gen_random_uuid();
  normalized_email text := lower(trim(p_email));
begin
  if exists (select 1 from app.family_accounts) then
    raise exception 'Family setup has already been completed' using errcode = 'unique_violation';
  end if;
  if exists (select 1 from auth.users where email = normalized_email) then
    raise exception 'Email already exists' using errcode = 'unique_violation';
  end if;

  insert into auth.users (
    id, aud, role, email, encrypted_password, email_confirmed_at, confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
  ) values (
    new_user_id, 'authenticated', 'authenticated', normalized_email,
    extensions.crypt(p_password, extensions.gen_salt('bf')), now(), now(),
    jsonb_build_object('provider', 'email', 'providers', jsonb_build_array('email')),
    '{}'::jsonb, now(), now()
  );
  insert into auth.identities (
    provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at, email
  ) values (
    normalized_email, new_user_id,
    jsonb_build_object('sub', new_user_id::text, 'email', normalized_email),
    'email', now(), now(), now(), normalized_email
  );
  insert into app.family_accounts (user_id) values (new_user_id);
  return new_user_id;
end;
$$;

revoke all on function app.create_first_family_account(text, text) from public;
grant execute on function app.create_first_family_account(text, text) to homeschool_app;
