# Log Removal and Message Ownership — Backend

_Companion plan: `log-removal-and-token-storage-frontend.md` (in `messaging-frontend/messaging-app/plans/26_9_24_s1/`) removes client debug logs and moves session storage to the device keychain. Both are separate repos with separate PRs. This plan does not change the frontend. Happy-path behavior stays the same: the logged-in user still lists, opens, edits, sends, and deletes their own messages and groups._

## Context

`DELETE /messages/<id>` and `DELETE /groups/<id>` already require `get_jwt_identity()` to match `userID`. The other message and group routes do not. Mongo ObjectIds are not a secret (they embed a timestamp), so knowing another user's id is enough to read or overwrite their data while holding any valid JWT.

`app.py` and `models.py` also `print` request bodies, phone numbers, full message documents, and the Twilio auth token. Several handlers return `str(e)` to the client. Refresh tokens never expire (`JWT_REFRESH_TOKEN_EXPIRES = False`), and `python app.py` starts the Werkzeug debugger on all interfaces.

## Repo

`Messaging-backend/` → GitHub remote `rachel-lawrie/Messaging-backend`.

## 1. Remove every `print`

Do not add a replacement logger. Delete the call and leave the surrounding control flow.

`app.py`:

- `validate_twilio_request`: lines 59–66 print `auth_token`, the request URL, form, Twilio signature, calculated signature, headers, and raw body. Keep the `RequestValidator` check and the 403 abort.
- `register_user` line 116, `create_group` line 156, `update_group` lines 192, 198, 201, 205, 209, `delete_group` line 232, `create_message` line 244, `update_message` lines 256, 262, 265, 269, 273, `delete_message` line 345.
- `send_messages` lines 410 and 413 (recipient phone numbers and exception text).
- `twilio_webhook` lines 422–424, 427, 431, 434, 441, 449, 494, 499, 502, 506 (headers, form, full message documents, phone numbers).

`models.py` line 132 (`Error inserting user`). The `raise ValueError("Failed to create user account")` stays.

## 2. Scope every message and group read/write to the JWT user

Use `user_id = get_jwt_identity()` the same way `delete_message` and `delete_group` already do. A missing document and a document owned by someone else both return 404, so existence is not leaked.

- `GET /messages/<message_id>`: `find_one({"_id": object_id, "userID": user_id})`.
- `PUT /messages/<message_id>`: `update_one({"_id": object_id, "userID": user_id}, {"$set": allowed})`.
- `GET /messages`: ignore `request.args.get('user_id')`. Query `{"userID": user_id}`. Drop the "Missing user_id parameter" 400. The frontend may keep sending `?user_id=`; it is unused.
- `GET /groups`: same change. Query `{"userID": user_id}`.
- `PUT /groups/<group_id>`: `update_one({"_id": object_id, "userID": user_id}, {"$set": allowed})`.
- `POST /messages` and `POST /groups`: copy the JSON, set `data["userID"] = get_jwt_identity()` after the copy so a client-supplied `userID` is overwritten, then `insert_one`.

## 3. Allowlist fields on update and create

`$set` of the raw body lets a caller rewrite `userID`, `responded_yes`, or `quotaMetNotified`. Build the update from an allowlist and ignore every other key.

Messages: `title`, `message`, `to`, `limit`, `timeSent`.

Groups: `groupName`, `members`.

Do not accept `responseId` from the client. Section 4 generates it. Do not accept `userID`, `responded_yes`, or `quotaMetNotified` on create or update. The webhook remains the only writer of `responded_yes` and `quotaMetNotified`.

If the allowlisted body is empty, return 400.

## 4. `POST /twilio` only sends the caller's saved message

Today `messageId` is loaded with no owner check, `responseId` and `recipients` come from the client, and any number can be texted.

- Require `messageId`. Invalid ObjectId → 400. `find_one({"_id": object_id, "userID": get_jwt_identity()})`. Not found → 404.
- Title, limit text, and sender name stay as they are, but they come from this owned document (sender name already comes from the JWT user).
- RSVP code: if the document has no `responseId`, generate one with `secrets.token_hex(4)` (8 hex chars, not the last 6 of the ObjectId), `$set` it on that same owned document, and use the stored value in the SMS body. Ignore `data["responseId"]`.
- Recipients: expand `message_doc["to"]` the same way the client does (a group entry has `members`, a contact has `phoneNumber`). Only call Twilio for numbers in that set that the request also lists. A number that is not on the saved message is skipped, not sent. This matches the current app flow: `DraftMessage` and `SentMessage` save `to` with PUT/POST, then POST `/twilio`.
- Keep per-recipient Twilio errors in the JSON `responses` array. Do not `print` them, and do not put raw exception strings in that array; use a generic `"error": "Failed to send"` per failed recipient.

## 5. Stop returning exception text

These handlers interpolate `str(e)` into the JSON body:

- `get_groups` (`An error occurred: {str(e)}`)
- `get_messages` (same)
- `get_message` (same)
- `twilio_webhook` (`{"error": str(e)}`)

Return a fixed message instead, for example `{"error": "An error occurred"}` with status 500. Leave the existing 400/404 strings that do not include exception text.

## 6. Debugger and refresh-token lifetime

- In `app.py` under `if __name__ == '__main__'`, run with `debug` only when `os.getenv("FLASK_DEBUG") == "1"`. Default is off. Keep `host='0.0.0.0'` and `port=5001` so local device testing still works. `wsgi.py` is unchanged.
- Set `app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)`. Access tokens stay at 1 hour. The frontend already treats a failed refresh as logged-out.

## 7. Rate limit login, register, and send

Add `flask-limiter` to `requirements.txt`. Attach a `Limiter` with a per-IP default that is high enough not to affect normal use, and tighter limits on:

- `POST /login` and `POST /register` (credential stuffing)
- `POST /twilio` (SMS cost)

Use the defaults Flask-Limiter documents for an in-memory backend for this single-process app. A 429 response is enough; no new error shape is required beyond what Flask-Limiter returns.

## Verification

Against a running backend, with two users (A and B), each with a valid JWT. B's message id and group id are known to A.

1. A's `GET /messages/<B's id>` and `PUT` of that id → 404, and B's document is unchanged.
2. A's `GET /messages?user_id=<B's user id>` returns only A's messages.
3. Same two checks for groups (`GET /groups?user_id=`, `PUT /groups/<B's id>`).
4. A's `POST /messages` with `"userID": "<B's id>"` stores A's JWT id, not B's.
5. A's `PUT /messages/<own id>` with `responded_yes` or `userID` in the body does not change those fields.
6. A's `POST /twilio` with B's `messageId` → 404 and no Twilio call. A's `POST /twilio` with A's message id but a phone number not on that message's `to` list does not text that number.
7. `DELETE` of another user's message or group still returns 404.
8. A owned message still loads, updates, lists, and deletes.
9. No `print` remains in `app.py` or `models.py`. Triggering a 500 does not include a traceback or exception string in the JSON body.
10. `JWT_REFRESH_TOKEN_EXPIRES` is 30 days, and `python app.py` does not enable the debugger unless `FLASK_DEBUG=1`.
