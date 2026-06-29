from typing import Protocol

from fastapi import HTTPException, status
from firebase_admin import firestore
from google.cloud.firestore_v1 import Client

from app.schemas.profile import ProfileUpsert, UserProfile


class ProfileRepository(Protocol):
    def get(self, uid: str) -> UserProfile | None: ...
    def upsert(self, uid: str, profile: ProfileUpsert) -> UserProfile: ...


class FirestoreProfileRepository:
    def __init__(self, client: Client):
        self.client = client

    def get(self, uid: str) -> UserProfile | None:
        snapshot = self.client.collection("users").document(uid).get()
        if not snapshot.exists:
            return None
        return UserProfile(userId=uid, **snapshot.to_dict())

    def upsert(self, uid: str, profile: ProfileUpsert) -> UserProfile:
        user_ref = self.client.collection("users").document(uid)
        username_ref = self.client.collection("usernames").document(profile.username)
        transaction = self.client.transaction()

        @firestore.transactional
        def save_profile(tx):
            current = user_ref.get(transaction=tx)
            reserved = username_ref.get(transaction=tx)
            if reserved.exists and reserved.to_dict().get("userId") != uid:
                raise HTTPException(status.HTTP_409_CONFLICT, "Username is already taken")

            old_username = current.to_dict().get("username") if current.exists else None
            if old_username and old_username != profile.username:
                tx.delete(self.client.collection("usernames").document(old_username))

            payload = profile.model_dump()
            payload.update(
                {
                    "profileCompleted": True,
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                }
            )
            if not current.exists:
                payload["createdAt"] = firestore.SERVER_TIMESTAMP
            tx.set(user_ref, payload, merge=True)
            tx.set(username_ref, {"userId": uid, "updatedAt": firestore.SERVER_TIMESTAMP})

        save_profile(transaction)
        return self.get(uid)  # type: ignore[return-value]
