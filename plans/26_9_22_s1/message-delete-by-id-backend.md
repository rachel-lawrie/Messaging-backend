# Message Delete-by-ID — Backend

_Companion plan: `message-delete-edit-mode-frontend.md` (in `messaging-frontend/messaging-app/plans/26_9_22_s1/`) adds an iMessage-style "Edit" selection mode to the home screen that calls this endpoint to delete one or more selected messages. Both must land for the feature to work end-to-end, but they are separate repos with separate PRs. This plan only replaces the delete route; it does not change any other message endpoint._

## Context

The app currently has no way to delete a draft or sent message from the UI at all. The backend does expose `DELETE /messages/<title>`, but it's unsafe to build a real delete feature on:

- It matches by the user-entered `title` field, which is not unique — two drafts (or a draft and a sent message) can share the same title, so the wrong document can be deleted.
- It uses `delete_one`, which silently deletes only the first document Mongo happens to match.
- It is not scoped to the requesting user's `userID` — any authenticated user who knows (or guesses) another user's message title can delete that user's message.

Every message document already has MongoDB's native `_id` (`ObjectId`), and it's already the primary key used by the existing `GET /messages/<message_id>` and `PUT /messages/<message_id>` handlers. This plan replaces the title-based route with an id-based, user-scoped one, following that existing pattern exactly.

## Repo

`Messaging-backend/` → GitHub remote `rachel-lawrie/Messaging-backend`, currently on `main`.

## Backend: `app.py`

Replace the existing delete route (lines 301–314):

```python
# Delete Message
@app.route('/messages/<title>', methods=['DELETE'])
@jwt_required()
def delete_message(title):
    try:
        result = mongo.db.messages.delete_one({"title": title})

        if result.deleted_count == 1:
            return jsonify({"message": "Message deleted successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except Exception as e:
        return jsonify({"error": "Failed to delete message"}), 500
```

with an id-based, user-scoped version that mirrors the `ObjectId`/`InvalidId` handling already used by `get_message`/`update_message`, and the `userID` filtering already used by `get_messages`:

```python
# Delete message by id (scoped to the requesting user)
@app.route('/messages/<message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    try:
        object_id = ObjectId(message_id)
        user_id = get_jwt_identity()  # match whatever existing routes use for this
        result = mongo.db.messages.delete_one({"_id": object_id, "userID": user_id})

        if result.deleted_count == 1:
            return jsonify({"message": "Message deleted successfully"}), 200
        else:
            return jsonify({"error": "Message not found"}), 404

    except InvalidId:
        return jsonify({"error": "Invalid message ID format"}), 400
    except Exception as e:
        return jsonify({"error": "Failed to delete message"}), 500
```

Notes:

- This reuses the existing `/messages/<param>` DELETE route shape, so it fully replaces the title-based handler — Flask can't register two DELETE handlers on the same path pattern with different param names.
- Confirm the exact call used elsewhere in `app.py` to get the current user's id from the JWT (e.g. `get_jwt_identity()`) and match that convention exactly, rather than assuming the snippet above is verbatim correct.
- No frontend code currently calls the old title-based endpoint, so there is no existing caller to break by swapping the route.
- Both drafts and sent messages live in the same `messages` collection with the same shape (a "draft" is simply a document without `timeSent`), so this single route handles deleting either kind.

## Verification

Manual checks against a running backend, using a valid JWT for a test user:

1. `DELETE /messages/<id>` for a message you own → `200`, and the document is gone from `mongo.db.messages`.
2. `DELETE /messages/<nonexistent-but-valid-ObjectId>` → `404`.
3. `DELETE /messages/<id>` for a message owned by a *different* user (using your own valid token) → `404`, proving the `userID` scoping actually blocks cross-user deletes rather than just filtering the response.
4. `DELETE /messages/not-a-valid-object-id` → `400` (`InvalidId` path).
