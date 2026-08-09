-- app is unexposed; these deny-all policies preserve that boundary if it is ever exposed.
create policy "deny direct access" on app.family_accounts for all using (false) with check (false);
create policy "deny direct access" on app.children for all using (false) with check (false);
create policy "deny direct access" on app.subjects for all using (false) with check (false);
create policy "deny direct access" on app.documents for all using (false) with check (false);
create policy "deny direct access" on app.curriculum_topics for all using (false) with check (false);
create policy "deny direct access" on app.time_windows for all using (false) with check (false);
create policy "deny direct access" on app.blocked_days for all using (false) with check (false);
create policy "deny direct access" on app.scheduled_slots for all using (false) with check (false);
create policy "deny direct access" on app.completions for all using (false) with check (false);
create policy "deny direct access" on app.canvas_inserts for all using (false) with check (false);
create policy "deny direct access" on app.canvas_ai_content for all using (false) with check (false);
create policy "deny direct access" on app.app_settings for all using (false) with check (false);

create index if not exists subjects_child_idx on app.subjects(child_id);
create index if not exists topics_subject_idx on app.curriculum_topics(subject_id);
create index if not exists time_windows_child_idx on app.time_windows(child_id);
create index if not exists blocked_days_child_idx on app.blocked_days(child_id);
create index if not exists slots_subject_idx on app.scheduled_slots(subject_id);
create index if not exists slots_topic_idx on app.scheduled_slots(topic_id);
create index if not exists canvas_inserts_parent_idx on app.canvas_inserts(parent_topic_id);
create index if not exists canvas_inserts_insert_idx on app.canvas_inserts(insert_topic_id);
