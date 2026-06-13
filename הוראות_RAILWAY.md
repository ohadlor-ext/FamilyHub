# הוראות העלאה ל-Railway — מחדש 🚀

## שלב 1 — GitHub: צור ריפו חדש וריק

1. כנס ל-github.com → "New repository"
2. שם: `FamilyHub` (או כל שם אחר)
3. Public ✅
4. **אל תסמן** "Add README" — השאר ריק לחלוטין
5. לחץ "Create repository"

---

## שלב 2 — העלה את הקבצים מתיקיית NEW

1. בדף הריפו החדש לחץ **"uploading an existing file"**
2. פתח את תיקיית `NEW` בסייר הקבצים
3. בחר **הכל** (Ctrl+A) → גרור לחלון GitHub
4. ⚠️ חשוב: ודא שהקבצים שעולים כוללים גם את התיקיות:
   - `models/`
   - `routers/`
   - `services/`
5. כתוב commit message: `Initial commit`
6. לחץ **"Commit changes"**

> **אסור להעלות**: קובץ `.env` (הוא מוסתר — לא אמור להופיע)

---

## שלב 3 — Railway: מחק פרויקט ישן, צור חדש

1. ב-Railway → הפרויקט הישן → Settings → לחץ **"Delete Project"**
2. לחץ **"New Project"**
3. בחר **"Deploy from GitHub repo"**
4. בחר את הריפו החדש שיצרת
5. Railway יתחיל לבנות — **צפה שזה ייכשל** (עדיין אין Variables)

---

## שלב 4 — הוסף PostgreSQL

1. בפרויקט Railway → לחץ **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway ייצור DB וישמור את `DATABASE_URL` אוטומטית ✅

---

## שלב 5 — Variables (משתני סביבה)

לחץ על שירות ה-GitHub → **"Variables"** → הוסף אחד-אחד:

| Variable | ערך |
|----------|-----|
| `GOOGLE_CLIENT_ID` | `143142840800-7p3l38o6apdm158nqs7oraqgtp3b42te.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | `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` |
| `GOOGLE_REDIRECT_URI` | ← **השאר ריק עד שלב 7** |
| `SECRET_KEY` | כתוב כל מחרוזת ארוכה אקראית, לדוגמה: `familyhub-secret-2024-xyz789` |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` |
| `OPENWEATHER_API_KEY` | ← תמלא אחרי שנרשמת |
| `WEATHER_CITY` | `Ashdod` |
| `WEATHER_COUNTRY` | `IL` |
| `WEATHER_LANG` | `he` |
| `ANTHROPIC_API_KEY` | ← המפתח שלך מ-console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | ← תמלא אחרי שיצרת Bot |
| `FRONTEND_URL` | ← **השאר ריק עד שלב 8** |
| `ENVIRONMENT` | `production` |

> **`DATABASE_URL`** — אל תוסיף! Railway מחבר אותה אוטומטית מה-PostgreSQL.

---

## שלב 6 — Deploy ובדיקת build

1. לאחר הוספת Variables → Railway אמור להתחיל deploy אוטומטית
2. לחץ על ה-deployment ובדוק שהוא מגיע ל-✅ **Deploy**
3. אם מצליח — לחץ **"Settings"** → **"Generate Domain"**
4. תקבל URL כמו: `https://familyhub-production-xxxx.up.railway.app`

---

## שלב 7 — עדכן GOOGLE_REDIRECT_URI

עם ה-URL שקיבלת מ-Railway:

**ב-Railway Variables** עדכן:
```
GOOGLE_REDIRECT_URI = https://familyhub-production-xxxx.up.railway.app/auth/google/callback
```

**ב-Google Cloud Console:**
1. API & Services → Credentials → לחץ על ה-OAuth Client
2. Authorized redirect URIs → הוסף:
   `https://familyhub-production-xxxx.up.railway.app/auth/google/callback`
3. שמור

---

## שלב 8 — בדיקה סופית

פתח בדפדפן:
- `https://YOUR-RAILWAY-URL/` — אמור להחזיר `{"app": "Family Hub API"}`
- `https://YOUR-RAILWAY-URL/docs` — תיעוד API אינטראקטיבי
- `https://YOUR-RAILWAY-URL/health` — בדיקת תקינות

---

## 🎯 אחרי שהכל עובד — השלב הבא: Lovable

1. כנס ל-lovable.dev
2. צור פרויקט חדש
3. השתמש בפרומפט שנמצא ב-`docs/LOVABLE_PROMPT.md`
4. עדכן `FRONTEND_URL` ב-Railway Variables עם ה-URL של Lovable
