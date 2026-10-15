"What the feature does"# Spec: The feature signs a new user up on our platform. Whilst it leave alone the login - so users can only sign up using this feature



## 2. Interface

Module: `backend/app/profile_service.py`

Entry point:

```python
ProfileService.create_profile(
    display_name: str,
    email: str,
    location_consent: bool = False,
) -> UserProfile
```

input:

| Field | Type | Required | Rules |
|---|---|---|---|
| `display_name` | str | yes | Leading/trailing spaces removed; 2 to 40 characters after trimming |
| `email` | str | yes | Trimmed and lower-cased; must contain one `@` with text on both sides; unique across all profiles (case-insensitive) |
| `location_consent` | bool | no | Defaults to `False` |

The caller never supplies `id` or `created_at`; the service generates them.

output: a `UserProfile`

```python
UserProfile(
    id='3f2b...',                 # str, UUID4, generated, unique
    display_name='John Doe',      # str, trimmed
    email='john@example.com',     # str, trimmed + lower-cased
    location_consent=True,        # bool
    created_at=datetime(..., tzinfo=timezone.utc),  # set at creation, UTC
)
```

Field names are all lower-case (`email`, not `Email`).

Lookup:

```python
ProfileService.get_profile(profile_id: str) -> UserProfile | None   # None if not found
```

errors: `create_profile` raises `ProfileError` with one of these messages, and stores nothing:

| Condition | Message |
|---|---|
| `display_name` shorter than 2 or longer than 40 characters | `display_name must be 2-40 characters` |
| `email` not in a valid form | `invalid email` |
| `email` already used by another profile | `email already registered` |




## 2. true before it runs and guaranteed: 

what must be true bfore it run: The user should be a new user who is signing up to the app for the first time. 

What is guaranteed: That the new user should be able to sign in afterwards


## 4. What can go wrong and what happens when it does: 

What can go wrong: that a new user is not signed up after the whole process as the data is not populated into the database

and what happens when it does: the interface should return to the sign up page. 


## 3. Executable check: 

Given: input form is presented
when: when the user clicks signup
Then: the database is uploaded to the database and a user is created
