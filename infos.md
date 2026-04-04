# Terminal 1 - Backend
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - ngrok
ngrok http 8000

# Terminal 3 - Expo
npx expo start --clear --tunnel

Sometimes I can have to update the `config.ts` file

--

Starter:
 - uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
 - ngrok http 8000
 - npx expo start --clear --tunnel

- Oum pwd: admin123
- Others : password123