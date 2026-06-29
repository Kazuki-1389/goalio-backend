# Goalio API

FastAPI service for Firebase-authenticated Goalio profiles and football search.

## Run locally

1. Create and activate a virtual environment.
2. Install: `pip install -r requirements.txt`
3. Set `GOOGLE_APPLICATION_CREDENTIALS` to a Firebase service-account JSON file.
4. Enable **Anonymous** sign-in in Firebase Console → Authentication → Sign-in method.
5. Create the default Cloud Firestore database for project `goalio-c42bc`.
6. Run: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Android emulators reach the host at `http://10.0.2.2:8000`. Set Remote Config key
`backend_base_url` to the deployed HTTPS URL for production.

All `/api/v1` routes require `Authorization: Bearer <Firebase ID token>`.
