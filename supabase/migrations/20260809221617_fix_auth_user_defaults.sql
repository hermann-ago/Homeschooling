update auth.users
set instance_id = coalesce(instance_id, '00000000-0000-0000-0000-000000000000'),
    confirmation_token = coalesce(confirmation_token, ''),
    email_change = coalesce(email_change, ''),
    email_change_token_new = coalesce(email_change_token_new, ''),
    recovery_token = coalesce(recovery_token, '');

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
    instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
    confirmation_token, email_change, email_change_token_new, recovery_token,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at
  ) values (
    '00000000-0000-0000-0000-000000000000', new_user_id, 'authenticated', 'authenticated', normalized_email,
    extensions.crypt(p_password, extensions.gen_salt('bf')), now(),
    '', '', '', '',
    jsonb_build_object('provider', 'email', 'providers', jsonb_build_array('email')),
    '{}'::jsonb, now(), now()
  );
  insert into auth.identities (
    provider_id, user_id, identity_data, provider, last_sign_in_at, created_at, updated_at
  ) values (
    normalized_email, new_user_id,
    jsonb_build_object('sub', new_user_id::text, 'email', normalized_email),
    'email', now(), now(), now()
  );
  insert into app.family_accounts (user_id) values (new_user_id);
  return new_user_id;
end;
$$;

revoke all on function app.create_first_family_account(text, text) from public;
grant execute on function app.create_first_family_account(text, text) to homeschool_app;
