"""Shared, versioned teaching style and family-confirmed learner ages."""
from datetime import date
import hashlib
import json
from pathlib import Path

from storage import FileUnavailable, RevisionConflict
from storage.layout import FAMILY_TEACHING_SKILLS

FOLDER = FAMILY_TEACHING_SKILLS
SOURCE = Path(__file__).resolve().parents[2] / 'tutor/skills/child-friendly-tutor/SKILL.md'


def digest(content, profiles):
    return hashlib.sha256(json.dumps([content, profiles], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def current(db):
    row = max(db.all('family_tutor_skills'), key=lambda r:r['version'], default=None)
    if row:
        return row
    content = SOURCE.read_text(encoding='utf-8')
    profiles = {}
    for item in db.all('preferences'):
        value = str(item.get('value', ''))
        if item['key'] == 'age_at_setup' and item.get('confirmed_by') and value.isdigit() and 3 <= int(value) <= 25:
            stamp = item.get('confirmed_at')
            profiles[str(item['child_id'])] = {'age':int(value), 'as_of':stamp.date().isoformat() if stamp else None}
    return {'version':0, 'content':content, 'profiles':profiles, 'sha256':digest(content, profiles), 'file_path':None}


def packet(db, child_id):
    row = current(db)
    # A birth year supports a range, not an exact age or an invented birthday.
    profile = dict(row['profiles'].get(str(child_id), {}))
    if 'birth_date' in profile:
        born = date.fromisoformat(profile['birth_date'])
        today = date.today()
        profile.update(age=today.year-born.year-((today.month,today.day)<(born.month,born.day)), age_basis='birth_date')
    elif 'birth_year' in profile:
        year = date.today().year
        oldest = year-profile['birth_year']
        profile.update(age_range=[max(0,oldest-1),oldest], age_range_year=year)
    return {'version':row['version'], 'content':row['content'], 'learner_profile':profile,
            'sha256':digest(row['content'], profile)}


def instructions(packet):
    return ('Shared family tutoring skill:\n' + packet['content'] +
            '\nSelected learner profile (family-confirmed age or birth year; an age range is not an exact age or ability assessment):\n' +
            json.dumps(packet['learner_profile'], ensure_ascii=False))


def save(tx, content, profiles, expected_version):
    previous = current(tx)
    if previous['version'] != expected_version:
        raise RevisionConflict('The family tutoring skill changed. Reload before saving.', previous)
    content = content.strip()
    if not 1 <= len(content) <= 30000:
        raise ValueError('Teaching instructions must contain 1–30,000 characters')
    checked = {}
    for child_id, profile in profiles.items():
        if not child_id.isdigit() or not tx.get('children', int(child_id)):
            raise ValueError('Choose an existing learner for each profile')
        if 'birth_date' in profile:
            if not isinstance(profile['birth_date'],str) or 'age' in profile or 'birth_year' in profile:
                raise ValueError('Enter a birth date without a separate age or birth year')
            born = date.fromisoformat(profile['birth_date'])
            today = date.today()
            age = today.year-born.year-((today.month,today.day)<(born.month,born.day))
            if born > today or not 0 <= age <= 25:
                raise ValueError('Enter a valid birth date, not in the future')
            values = {'birth_date':born.isoformat()}
        elif 'birth_year' in profile:
            value = profile['birth_year']
            if ('age' in profile or isinstance(value,bool) or not isinstance(value,int)
                    or not date.today().year-25 <= value <= date.today().year):
                raise ValueError('Enter a valid birth year, without a separate age')
            values = {'birth_year':value}
        else:
            age = profile.get('age')
            if isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 25:
                raise ValueError('Learner age must be between 0 and 25')
            values = {'age':age}
        if profile.get('as_of') is None:
            # Imported family ages may have no original confirmation date.
            # Preserve that uncertainty instead of inventing a birthday/date.
            checked[child_id] = {**values, 'as_of':None}
            continue
        if not isinstance(profile.get('as_of'), str):
            raise ValueError('Confirm the date for each learner age')
        stamp = date.fromisoformat(profile['as_of'])
        if stamp > date.today():
            raise ValueError('Age confirmation cannot be in the future')
        checked[child_id] = {**values, 'as_of':stamp.isoformat()}
    if content == previous['content'].strip() and checked == previous['profiles']:
        return previous
    if not tx.all('family_tutor_skills'):
        _save(tx, previous['content'], previous['profiles'], 0)
    return _save(tx, content, checked, previous['version']+1)


def _save(tx, content, profiles, version):
    path = None
    try:
        path, _ = tx.add_blob(content.encode(), FOLDER, f'family-tutor-SKILL-v{version}.md', 'text/markdown')
    except FileUnavailable:
        pass
    return tx.insert('family_tutor_skills', {'version':version, 'content':content, 'profiles':profiles,
        'sha256':digest(content, profiles), 'file_path':path})


def inventory(db):
    return {'skill':current(db), 'history':sorted(db.all('family_tutor_skills'), key=lambda r:r['version'], reverse=True),
            'learners':[{'id':c['id'], 'name':c.get('nickname') or c['name']} for c in db.all('children')]}
