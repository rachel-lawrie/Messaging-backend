# Event Capacity (limit) Feature — Backend

_Companion plan: `event-capacity-limit-frontend.md` (same directory) adds the "Event capacity:" input UI. Both must land for the feature to work end-to-end, but they are separate repos with separate PRs. This plan assumes drafts can now arrive with a `limit` field set to a positive integer (as a string, per existing frontend convention) or left as `""`/absent._

## Context

Drafts already store a `limit` field — it's sent from the frontend and saved to MongoDB via `POST/PUT /messages` — but nothing on the backend ever reads it. It looks like a "max people who can RSVP yes" feature that was scaffolded but never finished.

This plan:
1. Makes the outgoing SMS mention remaining "spots" when a limit is set (mirroring the existing pattern where `send_messages()` already appends an RSVP instruction sentence server-side).
2. Adds quota-enforcement logic to the Twilio inbound webhook (`/twilio-webhook`), which already tracks confirmations in `responded_yes` via `$addToSet` — once confirmations reach the limit, it notifies the remaining (non-responding) recipients that the quota has been met, firing exactly once.

## Repo

`Messaging-backend/` → GitHub remote `rachel-lawrie/Messaging-backend`, currently checked out on `feature/message-sender-title-branding`.

## Backend: `app.py`

### 1. Append "spots" text when sending (`send_messages()`, the `/twilio` route, ~lines 317–376)

Currently `message_doc` is already fetched to resolve `title` (lines 335–341). Extend that same lookup to also pull `limit`, and build a spots sentence placed **before** the existing RSVP instruction sentence:

```python
title = ""
limit_text = ""
if message_id:
    try:
        message_doc = mongo.db.messages.find_one({"_id": ObjectId(message_id)})
        if message_doc:
            title = message_doc.get("title", "")
            limit_value = message_doc.get("limit")
            if limit_value:
                try:
                    limit_num = int(limit_value)
                    if limit_num > 0:
                        limit_text = " There is 1 spot!" if limit_num == 1 else f" There are {limit_num} spots!"
                except (TypeError, ValueError):
                    pass
    except InvalidId:
        title = ""
```

Then update the SMS body construction (line ~357) to splice `limit_text` in after the message content and before the RSVP instruction:

```python
body=f"{prefix}: {trimmed_content}{limit_text} Respond '{response_id}' to confirm your affirmative response/attendance.",
```

### 2. Quota-met notification (`twilio_webhook()`, the `/twilio-webhook` route, ~lines 378–426)

After the existing `$addToSet` update succeeds (line 411–414), add a check: if this call just pushed `responded_yes` to (or past) the stored `limit`, and the quota-met notice hasn't already been sent, notify everyone in `to` who hasn't confirmed yet. Guard with a one-time `quotaMetNotified` flag (set via an atomic `update_one` matched on `{"quotaMetNotified": {"$ne": True}}`) so the notification fires exactly once even if extra replies keep arriving after the quota is met.

```python
if matching_contact:
    update_result = mongo.db.messages.update_one(
        {"_id": matching_message["_id"]},
        {"$addToSet": {"responded_yes": matching_contact}}
    )

    if update_result.modified_count:
        updated_message = mongo.db.messages.find_one({"_id": matching_message["_id"]})
        limit_value = updated_message.get("limit")
        responded_yes = updated_message.get("responded_yes", [])

        try:
            limit_num = int(limit_value) if limit_value else None
        except (TypeError, ValueError):
            limit_num = None

        if limit_num and limit_num > 0 and len(responded_yes) >= limit_num:
            flag_result = mongo.db.messages.update_one(
                {"_id": updated_message["_id"], "quotaMetNotified": {"$ne": True}},
                {"$set": {"quotaMetNotified": True}}
            )
            if flag_result.modified_count:
                responded_numbers = {c["phoneNumber"] for c in responded_yes}
                remaining = [c for c in updated_message.get("to", []) if c.get("phoneNumber") not in responded_numbers]

                owner = User.find_by_id(updated_message.get("userID"))
                owner_name = ""
                if owner:
                    owner_name = f"{owner.first_name} {owner.last_name}".strip() or owner.username

                quota_prefix = f"{owner_name} via cajAPP" if owner_name else "cajAPP"
                event_title = updated_message.get("title", "")
                if event_title:
                    quota_prefix += f" - {event_title}"

                for recipient in remaining:
                    try:
                        client.messages.create(
                            body=f"{quota_prefix} respondent quota has been met!",
                            messaging_service_sid=messagingServiceSid,
                            to=recipient["phoneNumber"]
                        )
                    except Exception as e:
                        print(f"Error notifying {recipient.get('phoneNumber')} of quota met: {e}")

    return jsonify({"message": "Contact added to responded_yes."}), 200
```

This reuses the same `sender via cajAPP - Title` prefix pattern already established in `send_messages()`, resolving the sender from the message's stored `userID` (via `User.find_by_id`, already imported) rather than a JWT identity, since the webhook has no authenticated user context.

No schema/migration changes are needed — MongoDB is schemaless here and `limit`/`quotaMetNotified` will simply be new fields on existing documents.

## Git workflow

`gh` (GitHub CLI) is not installed on this machine, so the PR will be opened manually in the browser from a pushed branch rather than via `gh pr create`.

1. Branch from an up-to-date `main`, not the currently-checked-out feature branch, so the new PR's diff only contains this task's changes:
   ```
   git checkout main
   git pull origin main
   git checkout -b feature/event-capacity-limit
   ```
2. Make the `app.py` edits described above.
3. Commit with a descriptive message, e.g. `git commit -m "Enforce event capacity limit and send quota-met notifications"`.
4. Push and hand back the compare URL to open and finish the PR manually in the browser:
   ```
   git push -u origin feature/event-capacity-limit
   ```
   Compare link: `https://github.com/rachel-lawrie/Messaging-backend/compare/main...feature/event-capacity-limit?expand=1`

## Verification

1. Start the backend (`Messaging-backend`) as usual.
2. Create/save a draft (directly via API, or using the frontend once its plan is implemented) with a capacity of, say, 2, add 3+ real test recipients, and send it — confirm via Twilio logs/console that the SMS body includes "There are 2 spots!" before the RSVP instruction.
3. Confirm a message saved with capacity = 1 sends "There is 1 spot!" (singular).
4. Simulate two recipients replying with the response code (via the `/twilio-webhook` route, e.g. with curl/Postman spoof or real replies against a test Twilio number) and confirm the remaining recipient(s) receive the "<First Last> via cajAPP - <Title> respondent quota has been met!" message exactly once, and that a third reply afterward does not trigger a duplicate notification.
